# HVAC 디지털 트윈 백엔드

실험실 HVAC 운영 데이터(WATER/AIR/USER SIDE, 84센서)를 IFC/BIM 모델·계통도에
연결하는 통합 모니터링 백엔드.

## 구조
    backend/
    ├── app/
    │   ├── config.py              # 전역 설정(인코딩·헤더·경로·sentinel)
    │   ├── loaders/hvac_csv.py    # (Step 1) CSV 파싱·정규화 → tidy/wide
    │   ├── db/
    │   │   ├── schema.sql         # (Step 2) 정적 테이블 DDL
    │   │   ├── ingest.py          # (Step 2) CSV→SQLite 적재
    │   │   └── session.py         # (Step 3) DB 연결 의존성
    │   ├── api/
    │   │   ├── routes.py          # (Step 3) 엔드포인트
    │   │   └── schemas.py         # (Step 3) 응답 스키마
    │   └── main.py                # (Step 3) FastAPI 앱
    ├── data/
    │   ├── sensor_code_to_data_group.csv   # 84센서 → 15 data_group 룩업
    │   ├── sensor_ifc_mapping_final.csv    # 15 data_group → IFC 참조(GlobalId 검증본)
    │   └── build_lookup.py                 # 룩업표 생성 스크립트(1회성)
    ├── tests/                     # pytest (loader 6 + ingest 7 + api 8 = 21)
    ├── requirements.txt
    └── README.md

## 설치
    pip install -r requirements.txt

## 1) DB 빌드
    python -m app.db.ingest <fine.csv> <hourly.csv>
    # 인자 생략 시 data/fine.csv, data/hourly.csv 사용
    # → data/hvac.db (data_groups=15, sensors=84,
    #   readings_hourly=86,184, readings_fine=56,840×84)

## 2) API 서버 실행
    uvicorn app.main:app --reload
    # 문서: http://127.0.0.1:8000/docs

### 엔드포인트
| method | path | 용도 |
|--------|------|------|
| GET | /groups | data_group 15개 + IFC 참조 |
| GET | /sensors/{data_group}?t= | 그룹별 센서값(특정 시각/최신) — 3D 하이라이트·계통도 노드 |
| GET | /state?t= | 특정 시각 전체 스냅샷 — replay 프레임 |
| GET | /timeseries/{sensor_code}?from=&to= | 센서 시계열 — 차트/이상탐지 |
| GET | /meta/timerange | 재생 가능 시간 범위 |
| GET | /health | 헬스체크 |

## 3) 테스트
    python -m pytest tests/ -q      # 22 passed

## 테이블 요약
- data_groups (15) — IFC 바인딩/계통도 노드 근거. `ifc_file`은 프론트가
  Arch/Eng 중 어느 모델을 조회할지 정하는 키라 반드시 API로 노출돼야 함(누락 시 3D 하이라이트 전멸)
- sensors (84) — 센서코드↔data_group↔단위. data_group NULL = UNMAPPED(1-6/1-7/1-8)
- readings_hourly — long, 이상탐지·센서별 시계열
- readings_fine — wide(timestamp PK + 84열), 특정 시각 전체 상태

## IFC 참조 (GlobalId, 실측 검증 완료)
- Room_1 `0ztdC3L1HAzhbhMHypqcYI` (PHARM. OFFICE) / Room_2 `0ztdC3L1HAzhbhMHypqcYF` (COUNSELING) / Room_3 `0uLn6BSvvEB8kgChiujNHm` (SEC. OFFICE)
- AHU `0rcx3NRlHCjxDJbhLB_yA3` / Chiller `1Hk4$wKjPFLAM7$8qJgCUa`
- VAV_1~7: IfcFlowController, GlobalId 7종
