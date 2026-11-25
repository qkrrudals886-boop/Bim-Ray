"""DB 적재 레이어 (Step 2).

로더(파싱·정규화) 위에서 semantic 바인딩을 붙인다:
  - data_groups      : 매핑표(15행) → IFC 참조의 근거
  - sensors          : 룩업표(84행) → 센서코드 ↔ data_group ↔ 단위
  - readings_hourly  : hourly tidy(long)
  - readings_fine    : fine wide(timestamp PK + 84컬럼, 동적 생성)

실행:  python -m app.db.ingest [<fine.csv> <hourly.csv>]
       인자 없으면 config의 DEFAULT_FINE_CSV / DEFAULT_HOURLY_CSV 사용.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from app.config import DB_PATH, LOOKUP_CSV, MAPPING_CSV, DEFAULT_FINE_CSV, DEFAULT_HOURLY_CSV
from app.loaders.hvac_csv import load_hvac_csv

SCHEMA_SQL = Path(__file__).with_name("schema.sql")
_UNIT_RE = re.compile(r"\(([^()]*)\)\s*$")  # 이름 끝 괄호 = 단위


def _unit_of(name: str) -> Optional[str]:
    m = _UNIT_RE.search(name or "")
    return m.group(1) if m else None


def _init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))


def _load_data_groups(con: sqlite3.Connection) -> None:
    m = pd.read_csv(MAPPING_CSV)
    cols = ["data_group", "data_side", "ifc_file", "ifc_element_type", "ifc_type_name",
            "ifc_ref", "ifc_ref_kind", "space_name", "notes"]
    m = m[[c for c in cols if c in m.columns]].drop_duplicates("data_group")
    m.to_sql("data_groups", con, if_exists="append", index=False)


def _load_sensors(con: sqlite3.Connection) -> None:
    lut = pd.read_csv(LOOKUP_CSV)
    lut["unit"] = lut["sensor_name"].map(_unit_of)
    # UNMAPPED → data_group NULL (FK 위반 방지, 계통도/IFC 미바인딩)
    lut["data_group"] = lut["data_group"].replace("UNMAPPED", pd.NA)
    out = lut[["sensor_code", "side", "sensor_name", "unit",
               "data_group", "confidence", "notes"]]
    out.to_sql("sensors", con, if_exists="append", index=False)


def _load_hourly(con: sqlite3.Connection, hourly_csv: str) -> int:
    df = load_hvac_csv(hourly_csv, tidy=True)      # long
    df = df.dropna(subset=["value"])                 # 결측은 행 미생성(희소 저장)
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df[["timestamp", "sensor_code", "value"]].to_sql(
        "readings_hourly", con, if_exists="append", index=False
    )
    return len(df)


def _load_fine(con: sqlite3.Connection, fine_csv: str) -> tuple[int, int]:
    wide = load_hvac_csv(fine_csv, tidy=False)       # [timestamp, <84 codes>]
    # sub-minute 중복 timestamp는 분당 평균으로 collapse
    wide = wide.groupby("timestamp", as_index=False).mean(numeric_only=True)
    wide["timestamp"] = wide["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    codes = [c for c in wide.columns if c != "timestamp"]

    # 동적 DDL: 컬럼명 = sensor_code(하이픈 포함 → 따옴표)
    col_defs = ", ".join(f'"{c}" REAL' for c in codes)
    con.execute("DROP TABLE IF EXISTS readings_fine")
    con.execute(f'CREATE TABLE readings_fine (timestamp TEXT PRIMARY KEY, {col_defs})')
    wide.to_sql("readings_fine", con, if_exists="append", index=False)
    return len(wide), len(codes)


def build(fine_csv: str, hourly_csv: str, db_path: Path = DB_PATH) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    stats = {}
    try:
        con.execute("PRAGMA foreign_keys = ON")
        _init_schema(con)
        _load_data_groups(con)
        _load_sensors(con)
        stats["hourly_rows"] = _load_hourly(con, hourly_csv)
        fine_rows, fine_cols = _load_fine(con, fine_csv)
        stats["fine_rows"], stats["fine_cols"] = fine_rows, fine_cols
        con.commit()
        stats["data_groups"] = con.execute("SELECT COUNT(*) FROM data_groups").fetchone()[0]
        stats["sensors"] = con.execute("SELECT COUNT(*) FROM sensors").fetchone()[0]
    finally:
        con.close()
    return stats


if __name__ == "__main__":
    fine = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_FINE_CSV)
    hourly = sys.argv[2] if len(sys.argv) > 2 else str(DEFAULT_HOURLY_CSV)
    result = build(fine, hourly)
    print(f"DB built at {DB_PATH}")
    for k, v in result.items():
        print(f"  {k}: {v}")
