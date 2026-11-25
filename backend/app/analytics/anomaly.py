"""센서 이상탐지 레이어.

라벨 없는 HVAC 데이터라 단일 센서의 자기 이력 학습으로는 "상시 고장"을 놓친다
(예: VAV_7 차압이 -62.50 Pa로 고정 → 자기 이력 기준으론 정상). 그래서 탐지기를 셋으로 나눴다.

  1) stuck        : 분산 0 → 값이 멈춤
  2) sibling      : 동종 센서군(VAV 1~7) 대비 robust z-score (median/MAD)
  3) distribution : 이동중앙값 잔차의 robust z-score → 급변

IsolationForest(고정/auto contamination)는 주야간 주기 때문에 대량 오탐이 나서 폐기했다 (README 참고).
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

SIBLING_PATTERNS = [
    "VAV 공급 공기 차압(Pa)",
    "VAV 댐퍼 개도율(%)",
    "VAV 풍량(M3/h)",
]

STUCK_MIN_POINTS = 24        # 시간 데이터 → 최소 하루
SIBLING_Z_THRESHOLD = 3.5    # Iglewicz & Hoaglin 권장값
RESIDUAL_WINDOW = 25         # 이동중앙값 창(시간) — 주야간 사이클 제거
RESIDUAL_Z_THRESHOLD = 5.0   # 잔차 robust z 임계
MIN_OUTLIER_RATIO = 0.30     # 급변 시점 비율이 이 이상일 때만 보고


def _robust_z(values: np.ndarray) -> np.ndarray:
    med = np.median(values)
    mad = np.median(np.abs(values - med))
    if mad < 1e-12:
        std = values.std()
        if std < 1e-12:
            return np.zeros_like(values)
        return (values - med) / std
    return 0.6745 * (values - med) / mad


def detect_stuck(series: pd.Series) -> Optional[Dict]:
    v = series.dropna()
    if len(v) < STUCK_MIN_POINTS:
        return None
    if float(v.std()) > 1e-9:
        return None
    return {"kind": "stuck", "value": float(v.iloc[0]), "n_points": int(len(v)),
            "detail": f"{len(v)}개 관측이 모두 {float(v.iloc[0]):.2f}로 고정"}


def detect_sibling_outlier(stats_by_code: Dict[str, float], target_code: str) -> Optional[Dict]:
    if len(stats_by_code) < 3:
        return None
    codes = list(stats_by_code.keys())
    values = np.array([stats_by_code[c] for c in codes], dtype=float)
    z = _robust_z(values)
    idx = codes.index(target_code)
    if abs(z[idx]) < SIBLING_Z_THRESHOLD:
        return None
    peers = [stats_by_code[c] for c in codes if c != target_code]
    return {"kind": "sibling", "z_score": float(z[idx]),
            "detail": f"동종 센서 평균 {np.mean(peers):.2f} 대비 {stats_by_code[target_code]:.2f} (z={z[idx]:.1f})"}


def detect_distribution_outliers(series: pd.Series) -> Optional[Dict]:
    v = series.dropna()
    if len(v) < 50 or float(v.std()) < 1e-9:
        return None
    baseline = v.rolling(window=RESIDUAL_WINDOW, center=True, min_periods=3).median()
    residual = (v - baseline).dropna()
    if residual.empty or float(residual.std()) < 1e-12:
        return None
    z = np.abs(_robust_z(residual.to_numpy()))
    n_out = int((z > RESIDUAL_Z_THRESHOLD).sum())
    ratio = n_out / len(residual)
    if n_out == 0 or ratio < MIN_OUTLIER_RATIO:
        return None
    return {"kind": "distribution", "ratio": float(ratio),
            "detail": f"{len(residual)}개 중 {n_out}개 시점({ratio*100:.1f}%)에서 급변"}


def _severity(findings: List[Dict], is_idle: bool) -> str:
    kinds = {f["kind"] for f in findings}
    if "stuck" in kinds and "sibling" in kinds:
        return "critical"
    if "stuck" in kinds:
        return "info" if is_idle else "warning"
    if "sibling" in kinds:
        return "warning"
    return "info"


def analyze(readings: pd.DataFrame, sensors: pd.DataFrame) -> pd.DataFrame:
    """readings: [timestamp, sensor_code, value] / sensors: [sensor_code, sensor_name, data_group]"""
    merged = sensors.merge(readings, on="sensor_code", how="inner")

    sibling_stats: Dict[str, Dict[str, float]] = {}
    for pat in SIBLING_PATTERNS:
        sub = merged[merged["sensor_name"].str.contains(pat, regex=False)]
        if not sub.empty:
            sibling_stats[pat] = sub.groupby("sensor_code")["value"].mean().to_dict()

    # 정지 판정: 같은 data_group의 주파수/풍량이 전 기간 0 (← 그룹 단위라는 한계가 있음)
    idle_groups = set()
    for grp, sub in merged.groupby("data_group"):
        act = sub[sub["sensor_name"].str.contains("주파수|풍량", regex=True)]
        if not act.empty and float(act["value"].abs().max()) < 1e-9:
            idle_groups.add(grp)

    rows = []
    for code, sub in merged.groupby("sensor_code"):
        info = sub.iloc[0]
        series = sub.set_index("timestamp")["value"].sort_index()
        findings: List[Dict] = []
        f = detect_stuck(series)
        if f:
            findings.append(f)
        for pat, stats in sibling_stats.items():
            if code in stats and pat in str(info["sensor_name"]):
                f = detect_sibling_outlier(stats, code)
                if f:
                    findings.append(f)
        f = detect_distribution_outliers(series)
        if f:
            findings.append(f)
        if not findings:
            continue
        is_idle = info["data_group"] in idle_groups
        rows.append({"sensor_code": code, "sensor_name": info["sensor_name"],
                     "data_group": info["data_group"], "idle": is_idle,
                     "severity": _severity(findings, is_idle),
                     "kinds": ",".join(sorted({f["kind"] for f in findings})),
                     "detail": " / ".join(f["detail"] for f in findings)})
    order = {"critical": 0, "warning": 1, "info": 2}
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_o"] = out["severity"].map(order)
    return out.sort_values(["_o", "sensor_code"]).drop(columns="_o").reset_index(drop=True)
