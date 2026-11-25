"""API 엔드포인트 (Step 3).

| method | path | 용도 |
|---|---|---|
| GET | /groups | data_group 15개 + IFC 참조 |
| GET | /sensors/{data_group}?t= | 그룹별 센서값(특정 시각/최신) — 3D 하이라이트·계통도 노드 |
| GET | /state?t= | 특정 시각 전체 스냅샷 — replay 프레임 |
| GET | /timeseries/{sensor_code}?from=&to= | 센서 시계열 — 차트/이상탐지 |
| GET | /meta/timerange | 재생 가능 시간 범위 |
| GET | /health | 헬스체크 |
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import DataGroup, GroupSensors, SensorReading, StateSnapshot, TimeRange
from app.db.session import get_connection

router = APIRouter()


def _con():
    con = get_connection()
    try:
        yield con
    finally:
        con.close()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/groups", response_model=list[DataGroup])
def get_groups(con: sqlite3.Connection = Depends(_con)):
    rows = con.execute("SELECT * FROM data_groups ORDER BY data_group").fetchall()
    return [dict(r) for r in rows]


def _nearest_fine_row(con: sqlite3.Connection, t: Optional[str]) -> Optional[sqlite3.Row]:
    if t is None:
        row = con.execute("SELECT * FROM readings_fine ORDER BY timestamp DESC LIMIT 1").fetchone()
    else:
        row = con.execute(
            "SELECT * FROM readings_fine WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,)
        ).fetchone()
        if row is None:  # 요청 시각이 데이터 범위보다 이르면 가장 이른 행으로 폴백
            row = con.execute("SELECT * FROM readings_fine ORDER BY timestamp ASC LIMIT 1").fetchone()
    return row


@router.get("/sensors/{data_group}", response_model=GroupSensors)
def get_group_sensors(
    data_group: str, t: Optional[str] = Query(None), con: sqlite3.Connection = Depends(_con)
):
    group = con.execute("SELECT * FROM data_groups WHERE data_group = ?", (data_group,)).fetchone()
    if group is None:
        raise HTTPException(404, f"unknown data_group: {data_group}")

    sensors = con.execute(
        "SELECT sensor_code, sensor_name, unit FROM sensors WHERE data_group = ? ORDER BY sensor_code",
        (data_group,),
    ).fetchall()

    row = _nearest_fine_row(con, t)
    ts = row["timestamp"] if row else None

    readings = []
    for s in sensors:
        value = row[s["sensor_code"]] if row and s["sensor_code"] in row.keys() else None
        readings.append(SensorReading(
            sensor_code=s["sensor_code"], sensor_name=s["sensor_name"], unit=s["unit"], value=value
        ))

    return GroupSensors(
        data_group=data_group, ifc_ref=group["ifc_ref"], ifc_ref_kind=group["ifc_ref_kind"],
        timestamp=ts, sensors=readings,
    )


@router.get("/state", response_model=StateSnapshot)
def get_state(t: Optional[str] = Query(None), con: sqlite3.Connection = Depends(_con)):
    row = _nearest_fine_row(con, t)
    if row is None:
        raise HTTPException(404, "no data")
    values = {k: row[k] for k in row.keys() if k != "timestamp"}
    return StateSnapshot(timestamp=row["timestamp"], values=values)


@router.get("/timeseries/{sensor_code}")
def get_timeseries(
    sensor_code: str,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    con: sqlite3.Connection = Depends(_con),
):
    exists = con.execute("SELECT 1 FROM sensors WHERE sensor_code = ?", (sensor_code,)).fetchone()
    if not exists:
        raise HTTPException(404, f"unknown sensor_code: {sensor_code}")

    sql = "SELECT timestamp, value FROM readings_hourly WHERE sensor_code = ?"
    params: list = [sensor_code]
    if from_:
        sql += " AND timestamp >= ?"
        params.append(from_)
    if to:
        sql += " AND timestamp <= ?"
        params.append(to)
    sql += " ORDER BY timestamp ASC"

    rows = con.execute(sql, params).fetchall()
    return [{"timestamp": r["timestamp"], "value": r["value"]} for r in rows]


@router.get("/meta/timerange", response_model=TimeRange)
def get_timerange(con: sqlite3.Connection = Depends(_con)):
    fine = con.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings_fine").fetchone()
    hourly = con.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings_hourly").fetchone()
    return TimeRange(
        fine_min=fine[0], fine_max=fine[1], hourly_min=hourly[0], hourly_max=hourly[1]
    )
