import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_groups_returns_15():
    r = client.get("/groups")
    assert r.status_code == 200
    assert len(r.json()) == 15


def test_meta_timerange():
    r = client.get("/meta/timerange")
    assert r.status_code == 200
    body = r.json()
    assert body["fine_min"] < body["fine_max"]
    assert body["hourly_min"] < body["hourly_max"]


def test_sensors_by_group_latest():
    r = client.get("/sensors/AHU")
    assert r.status_code == 200
    body = r.json()
    assert body["ifc_ref"] == "0rcx3NRlHCjxDJbhLB_yA3"
    assert len(body["sensors"]) == 23


def test_groups_expose_ifc_file_for_3d_highlighting():
    """프론트 하이라이트 계약: global_id 그룹은 ifc_file/ifc_element_type/ifc_ref가 모두 있어야 함.

    ifc_file이 빠지면 프론트가 Arch/Eng 중 어느 모델을 조회할지 몰라 인덱싱이 전부 스킵된다
    (3일차 하이라이트 0개 버그의 실제 원인).
    """
    groups = client.get("/groups").json()
    geom = [g for g in groups if g["ifc_ref_kind"] == "global_id"]
    assert len(geom) == 12  # Room 3 + AHU + Chiller + VAV 7
    for g in geom:
        assert g["ifc_file"] in (
            "NBU_MedicalClinic_Arch.ifc",
            "NBU_MedicalClinic_Eng-HVAC.ifc",
        ), f"{g['data_group']}: ifc_file 누락/오류 -> {g.get('ifc_file')}"
        assert g["ifc_element_type"] in (
            "IfcSpace", "IfcEnergyConversionDevice", "IfcFlowController",
        )
        assert g["ifc_ref"]


def test_sensors_by_group_unknown_404():
    r = client.get("/sensors/NotAGroup")
    assert r.status_code == 404


def test_state_snapshot_has_84_values():
    tr = client.get("/meta/timerange").json()
    r = client.get("/state", params={"t": tr["fine_min"]})
    assert r.status_code == 200
    body = r.json()
    assert body["timestamp"] == tr["fine_min"]
    assert len(body["values"]) == 84


def test_timeseries_returns_points_in_range():
    tr = client.get("/meta/timerange").json()
    r = client.get("/timeseries/1-1", params={"from": tr["hourly_min"], "to": tr["hourly_max"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    assert body[0]["timestamp"] >= tr["hourly_min"]


def test_timeseries_unknown_sensor_404():
    r = client.get("/timeseries/9-99")
    assert r.status_code == 404
