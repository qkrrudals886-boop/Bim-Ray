"""이상탐지 임계값 실험 스크립트. 실행(레포 루트): backend/.venv/bin/python backend/scripts/anomaly_lab.py

임계값을 바꿔보고 싶으면 아래 EXPERIMENT 블록의 숫자만 고친다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analytics import anomaly as A  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HOURLY = ROOT / "data" / "HVAC operational dataset for final prj (hourly final).csv"
LOOKUP = ROOT / "backend" / "data" / "sensor_code_to_data_group.csv"

# ===== EXPERIMENT: 여기 숫자를 바꿔보며 결과 변화를 관찰 =====
A.SIBLING_Z_THRESHOLD = 3.5   # 2.0으로 내리면? 25로 올리면?
A.MIN_OUTLIER_RATIO = 0.30    # 0.01로 내리면 몇 건?
A.STUCK_MIN_POINTS = 24
# ===========================================================


def load():
    raw = pd.read_csv(HOURLY, encoding="cp949", header=None, low_memory=False)
    codes = [str(c).strip("()") for c in raw.iloc[1]][1:]
    df = raw.iloc[3:, 1:].apply(pd.to_numeric, errors="coerce")
    df.columns = codes
    df = df.mask(df <= -3000)                       # sentinel(-3276.7) 제거
    hours = raw.iloc[3:, 0].astype(str).str.split().str[2].astype(int).to_numpy()
    df["timestamp"] = range(len(df))
    long = df.melt(id_vars="timestamp", var_name="sensor_code", value_name="value").dropna()
    lk = pd.read_csv(LOOKUP)
    lk = lk[lk["data_group"] != "UNMAPPED"][["sensor_code", "sensor_name", "data_group"]]
    return df, hours, long, lk


def main():
    df, hours, long, lk = load()

    print("== 실습1: VAV 차압 7개, 일반 Z vs Robust Z ==")
    cols = ["3-4", "3-7", "4-4", "4-7", "5-4", "5-7", "5-10"]
    means = np.array([df[c].mean() for c in cols])
    plain = (means - means.mean()) / means.std()
    robust = A._robust_z(means)
    med = np.median(means)
    mad = np.median(np.abs(means - med))
    print(f"중앙값 {med:.2f}  MAD {mad:.2f}")
    for c, m, p, r in zip(cols, means, plain, robust):
        print(f"  {c:5} 평균 {m:8.2f}  일반Z {p:6.2f}  robustZ {r:7.2f}")

    print("\n== 실습2: 고착(std=0) 센서 ==")
    for c in df.columns.drop("timestamp"):
        v = df[c].dropna()
        if len(v) >= A.STUCK_MIN_POINTS and v.std() < 1e-9:
            print(f"  {c:5} 값 {v.iloc[0]}")

    print("\n== 실습3: VAV_1 차압 시간대별 평균 (주야간 사이클) ==")
    prof = df["3-4"].groupby(hours).mean().round(1)
    print("  " + "  ".join(f"{h}시:{v}" for h, v in prof.items()))

    print("\n== 실습4: 전체 이상탐지 ==")
    res = A.analyze(long, lk)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 70)
    print(res[["sensor_code", "data_group", "idle", "severity", "detail"]].to_string(index=False))
    print(f"\n총 {len(res)}건 / 센서 {lk.shape[0]}개")


if __name__ == "__main__":
    main()
