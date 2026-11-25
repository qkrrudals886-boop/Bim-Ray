import sqlite3

import pytest

from app.config import DEFAULT_FINE_CSV, DEFAULT_HOURLY_CSV
from app.db import ingest


@pytest.fixture(scope="module")
def built_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test_hvac.db"
    stats = ingest.build(str(DEFAULT_FINE_CSV), str(DEFAULT_HOURLY_CSV), db_path=db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    yield con, stats
    con.close()


def test_data_groups_count(built_db):
    con, _ = built_db
    n = con.execute("SELECT COUNT(*) FROM data_groups").fetchone()[0]
    assert n == 15


def test_sensors_count(built_db):
    con, _ = built_db
    n = con.execute("SELECT COUNT(*) FROM sensors").fetchone()[0]
    assert n == 84


def test_unmapped_sensors_have_null_data_group(built_db):
    con, _ = built_db
    rows = con.execute(
        "SELECT sensor_code, data_group FROM sensors WHERE sensor_code IN ('1-6','1-7','1-8')"
    ).fetchall()
    assert len(rows) == 3
    assert all(r["data_group"] is None for r in rows)


def test_readings_hourly_row_count(built_db):
    con, stats = built_db
    n = con.execute("SELECT COUNT(*) FROM readings_hourly").fetchone()[0]
    assert n == stats["hourly_rows"]
    assert n > 0


def test_readings_fine_dedup_collapses_subminute_dupes(built_db):
    con, stats = built_db
    n = con.execute("SELECT COUNT(*) FROM readings_fine").fetchone()[0]
    assert n == stats["fine_rows"]
    assert n < 56957  # 원본보다 적어야 함(중복 timestamp collapse)


def test_data_group_sensor_ifc_join_chain(built_db):
    con, _ = built_db
    row = con.execute(
        """
        SELECT s.sensor_code, g.ifc_ref FROM sensors s
        JOIN data_groups g ON s.data_group = g.data_group
        WHERE g.data_group = 'Chiller' LIMIT 1
        """
    ).fetchone()
    assert row is not None
    assert row["ifc_ref"] == "1Hk4$wKjPFLAM7$8qJgCUa"


def test_readings_fine_column_count(built_db):
    con, stats = built_db
    cols = [r[1] for r in con.execute("PRAGMA table_info(readings_fine)").fetchall()]
    assert len(cols) == stats["fine_cols"] + 1  # +timestamp
