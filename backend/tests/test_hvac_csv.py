import pandas as pd
import pytest

from app.config import DEFAULT_FINE_CSV, DEFAULT_HOURLY_CSV
from app.loaders.hvac_csv import list_sensors, load_hvac_csv


def test_sensor_catalog_has_84_codes():
    cat = list_sensors(DEFAULT_FINE_CSV)
    assert len(cat) == 84
    assert cat["sensor_code"].is_unique


def test_fine_wide_shape_and_timestamp_parsing():
    w = load_hvac_csv(DEFAULT_FINE_CSV, tidy=False)
    assert w.shape[1] == 85  # timestamp + 84 sensors
    assert w["timestamp"].notna().all()
    assert w["timestamp"].dt.year.eq(2022).all()


def test_hourly_wide_shape_and_year_injection():
    w = load_hvac_csv(DEFAULT_HOURLY_CSV, tidy=False)
    assert w.shape[1] == 85
    assert w["timestamp"].notna().all()
    assert w["timestamp"].dt.year.eq(2022).all()


def test_tidy_long_format():
    long = load_hvac_csv(DEFAULT_HOURLY_CSV, tidy=True)
    assert set(long.columns) == {"timestamp", "sensor_code", "value"}
    assert long["sensor_code"].nunique() == 84


def test_sentinel_removed_domain_anomaly_preserved():
    wide = load_hvac_csv(DEFAULT_FINE_CSV, tidy=False)
    # 하드 sentinel(-3276.7)은 전부 NaN 처리되어야 함
    assert not (wide.select_dtypes("number") <= -3000).any().any()
    # 7# VAV(5-10) 상시 음수 차압 같은 도메인 이상치는 보존 (완전히 사라지지 않음)
    assert (wide["5-10"] < 0).sum() > 0


def test_sensor_codes_match_ui_tags_format():
    cat = list_sensors(DEFAULT_FINE_CSV)
    assert set(cat["sensor_code"]) >= {"1-1", "2-1", "3-1", "4-1", "5-12"}
