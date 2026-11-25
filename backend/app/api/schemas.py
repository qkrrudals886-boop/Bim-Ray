"""API 응답 스키마.

Python 3.9+ 호환을 위해 `X | None` 대신 typing.Optional 사용
(로컬 pydantic 환경에서 `|` 문법이 실패하는 이슈 회피).
"""
from typing import Optional

from pydantic import BaseModel


class DataGroup(BaseModel):
    data_group: str
    data_side: Optional[str] = None
    ifc_file: Optional[str] = None  # 프론트가 Arch/Eng 중 어느 모델을 조회할지 결정
    ifc_element_type: Optional[str] = None
    ifc_type_name: Optional[str] = None
    ifc_ref: Optional[str] = None
    ifc_ref_kind: Optional[str] = None
    space_name: Optional[str] = None
    notes: Optional[str] = None


class SensorReading(BaseModel):
    sensor_code: str
    sensor_name: str
    unit: Optional[str] = None
    value: Optional[float] = None


class GroupSensors(BaseModel):
    data_group: str
    ifc_ref: Optional[str] = None
    ifc_ref_kind: Optional[str] = None
    timestamp: Optional[str] = None
    sensors: list[SensorReading]


class StateSnapshot(BaseModel):
    timestamp: str
    values: dict


class TimeseriesPoint(BaseModel):
    timestamp: str
    value: Optional[float] = None


class TimeRange(BaseModel):
    fine_min: Optional[str] = None
    fine_max: Optional[str] = None
    hourly_min: Optional[str] = None
    hourly_max: Optional[str] = None
