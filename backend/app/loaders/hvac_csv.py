"""HVAC 원본 CSV 로더 (Step 1).

hourly(m_dd_hh, 연도 없음)와 fine(Time, DD.MM.YYYY HH:MM) 두 파일을
동일한 API로 파싱·정규화한다.

- 3줄 헤더(side / code / name)를 파싱해 센서코드를 정규화된 키로 사용
  ('1-1' .. '5-12', UI 태그와 1:1 대응)
- 시간 컬럼명으로 포맷 자동판별: 'Time' → DD.MM.YYYY HH:MM,
  'm_dd_hh' → "M DD HH" (연도 없음 → INJECT_YEAR 주입)
- 결함 sentinel(<= SENTINEL_MAX)만 NaN 처리. 도메인 이상치
  (예: 7# VAV 상시 음수 차압, 비단조 kWh 카운터)는 그대로 보존해
  다운스트림 이상탐지 레이어로 이관한다.
- tidy(long: timestamp, sensor_code, value) 또는 wide(timestamp + 센서코드 컬럼) 출력.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.config import ENCODING, HEADER_ROWS, SENTINEL_MAX, INJECT_YEAR


def _read_header(path: str | Path) -> pd.DataFrame:
    """3줄 헤더를 파싱해 [side, code, name] 카탈로그로 반환 (1열=시간 컬럼 제외)."""
    h = pd.read_csv(path, header=None, nrows=HEADER_ROWS, encoding=ENCODING, dtype=str)
    time_col_name = h.iloc[2, 0]
    sides = h.iloc[0, 1:].ffill()
    codes = h.iloc[1, 1:].str.strip("() ")
    names = h.iloc[2, 1:].str.strip()
    cat = pd.DataFrame({"side": sides.values, "sensor_code": codes.values, "sensor_name": names.values})
    cat.attrs["time_col_name"] = time_col_name
    return cat


def _parse_timestamp(raw: pd.Series, time_col_name: str) -> pd.Series:
    if time_col_name == "Time":
        # fine: "DD.MM.YYYY HH:MM"
        return pd.to_datetime(raw, format="%d.%m.%Y %H:%M", errors="coerce")
    if time_col_name == "m_dd_hh":
        # hourly: "M DD HH" (공백 구분, 연도 없음) -> INJECT_YEAR 주입
        parts = raw.str.split(r"\s+", expand=True)
        month, day, hour = parts[0], parts[1], parts[2]
        composed = f"{INJECT_YEAR}-" + month.str.zfill(2) + "-" + day.str.zfill(2) + " " + hour.str.zfill(2) + ":00"
        return pd.to_datetime(composed, format="%Y-%m-%d %H:%M", errors="coerce")
    raise ValueError(f"알 수 없는 시간 컬럼 포맷: {time_col_name!r}")


def list_sensors(path: str | Path) -> pd.DataFrame:
    """헤더에서 추출한 센서 카탈로그(side, sensor_code, sensor_name)."""
    return _read_header(path).reset_index(drop=True)


def load_hvac_csv(path: str | Path, tidy: bool = True) -> pd.DataFrame:
    """HVAC CSV를 로드해 정규화된 DataFrame 반환.

    tidy=True  -> [timestamp, sensor_code, value] (long)
    tidy=False -> [timestamp, <sensor_code 컬럼...>] (wide)
    """
    cat = _read_header(path)
    time_col_name = cat.attrs["time_col_name"]

    body = pd.read_csv(
        path, header=None, skiprows=HEADER_ROWS, encoding=ENCODING, dtype=str
    )
    timestamp = _parse_timestamp(body[0], time_col_name)

    values = body.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    values.columns = cat["sensor_code"].values
    values = values.mask(values <= SENTINEL_MAX)  # 결함 sentinel만 NaN

    wide = pd.concat([pd.Series(timestamp, name="timestamp"), values], axis=1)
    wide = wide.dropna(subset=["timestamp"]).reset_index(drop=True)

    if not tidy:
        return wide

    long = wide.melt(id_vars="timestamp", var_name="sensor_code", value_name="value")
    long = long.sort_values(["timestamp", "sensor_code"]).reset_index(drop=True)
    return long
