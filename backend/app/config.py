"""전역 설정: 인코딩·헤더 구조·경로·sentinel 임계값."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DB_PATH = DATA_DIR / "hvac.db"
LOOKUP_CSV = DATA_DIR / "sensor_code_to_data_group.csv"
MAPPING_CSV = DATA_DIR / "sensor_ifc_mapping_final.csv"

DEFAULT_FINE_CSV = DATA_DIR / "fine.csv"
DEFAULT_HOURLY_CSV = DATA_DIR / "hourly.csv"

# 원본 CSV는 CP949(EUC-KR 계열), 3줄 헤더(side / code / name)
ENCODING = "cp949"
HEADER_ROWS = 3

# 결함 sentinel: 이 이하 값은 결측으로 간주해 NaN 처리 (도메인 이상치는 보존)
SENTINEL_MAX = -3000.0

# fine 데이터의 연도 정보가 없는 시간포맷(m_dd_hh)에 주입할 연도
INJECT_YEAR = 2022
