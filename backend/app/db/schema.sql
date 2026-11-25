PRAGMA foreign_keys = ON;

-- 15개 data_group ← sensor_ifc_mapping_final.csv. IFC 바인딩·계통도 노드의 근거.
CREATE TABLE IF NOT EXISTS data_groups (
    data_group        TEXT PRIMARY KEY,          -- AHU, VAV_1.., Room_1.., Chiller, Pump_*, CoolingTower
    data_side         TEXT,                      -- WATER/AIR/USER SIDE
    ifc_file          TEXT,                      -- 어느 IFC 파일에 있는 요소인지(Arch / Eng-HVAC). 프론트 모델 선택에 필수
    ifc_element_type  TEXT,                      -- IfcEnergyConversionDevice / IfcFlowController / IfcSpace / LOGICAL
    ifc_type_name     TEXT,
    ifc_ref           TEXT,                      -- global_id 또는 logical node id
    ifc_ref_kind      TEXT,                      -- global_id | logical_node
    space_name        TEXT,                      -- 3D 하이라이트 대상 실명(Room만)
    notes             TEXT
);

-- 84개 센서 카탈로그 ← sensor_code_to_data_group.csv.
-- data_group NULL = UNMAPPED(FAU/FCU/수측VAV 환수온도): DB엔 적재하되 IFC·계통도 바인딩 없음.
CREATE TABLE IF NOT EXISTS sensors (
    sensor_code   TEXT PRIMARY KEY,              -- '1-1' .. '5-12' (UI 태그와 1:1)
    side          TEXT NOT NULL,
    sensor_name   TEXT NOT NULL,
    unit          TEXT,                          -- ℃ / kW / kWh / % / Pa / kPa / ppm / M3/h
    data_group    TEXT REFERENCES data_groups(data_group),
    confidence    TEXT,                          -- high/medium/low/n-a (매핑 신뢰도)
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_sensors_group ON sensors(data_group);

-- hourly: long/tidy. 이상탐지·센서별 시계열 조회에 최적.
CREATE TABLE IF NOT EXISTS readings_hourly (
    timestamp   TEXT NOT NULL,                   -- ISO8601
    sensor_code TEXT NOT NULL REFERENCES sensors(sensor_code),
    value       REAL,
    PRIMARY KEY (timestamp, sensor_code)
);
CREATE INDEX IF NOT EXISTS idx_hourly_sensor ON readings_hourly(sensor_code, timestamp);

-- readings_fine(wide, timestamp PK + 84개 REAL 컬럼)는 ingest.py에서 동적 생성.
-- 용도: 특정 시각의 전체 상태 1행 조회(스트리밍 replay). 컬럼명 = sensor_code.
