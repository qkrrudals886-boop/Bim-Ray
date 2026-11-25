# Bim-Ray

> X-ray vision for building systems: HVAC sensor anomalies, located inside the IFC model.

BIM-based HVAC digital twin: map sensor time series onto IFC elements and spot anomalies in 3D.

의료시설(NBU Medical Clinic)의 **한 공조 계통**(AHU + VAV 7 + Room 3 + Chiller)을 대상으로, 센서 시계열을 IFC 요소의 `GlobalId`에 연결하고 브라우저 3D 뷰어에서 값에 따라 하이라이트합니다. 이상탐지 모듈은 별도로 구현·검증돼 있습니다 (아래 *현황* 참고).

## 구성

```
backend/    FastAPI + SQLite — CSV 로더, 적재, 시계열 API, 이상탐지 모듈
frontend/   Vite + three.js + web-ifc-three — IFC 3D 뷰어
data/       (git 제외) 원본 센서 CSV
models/     (git 제외) IFC 모델
```

센서 코드 → 설비 그룹(data_group) → IFC 참조 3단 매핑: `backend/data/sensor_ifc_mapping_final.csv`

## 백엔드

- **CSV 로더** — CP949, 3행 헤더, 시간 포맷 2종(hourly / fine) 정규화, 센티널(≤ −3000) 제거
- **SQLite** — `data_groups`(15) / `sensors`(84) / `readings_hourly` / `readings_fine`
- **API** — `/health` `/groups` `/sensors/{data_group}` `/state?t=` `/timeseries/{sensor_code}` `/meta/timerange`
- **테스트** — `pytest` 22개

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.db.ingest <fine.csv> <hourly.csv>
uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs
```

## 프론트엔드

IFC(건축 + 설비) 로드 → `GlobalId` → expressID 인덱싱 → 타임라인으로 `/state` 재생 → 요소별 색상 하이라이트. 3D 형상이 있는 12개(Room 3, AHU, Chiller, VAV 7)를 표시하고, 형상이 없는 펌프·냉각탑은 논리 노드로 분리했습니다.

`H` 건축 숨김 · `I` 격리(하이라이트만) · 선택 시 벽을 뚫고 보이는 위치 마커

```bash
cd frontend && npm install --legacy-peer-deps && npm run dev   # http://localhost:5173
```

> `three@0.152.0`으로 고정: web-ifc-three가 `mergeGeometries`(0.152+)를 쓰지만 peerDependency는 낡음. IFC 두 개는 뷰어 UI에서 직접 선택합니다.

### 렌더링 이슈 두 건

- **Z-fighting** — `logarithmicDepthBuffer`는 `gl_FragDepth`를 직접 써서 `polygonOffset`을 무효화합니다. 로그 깊이를 끄고 건축(+1)/하이라이트(−2)에 반대 방향 offset을 줘서 해결.
- **바운딩 박스 왜곡** — web-ifc-three의 subset은 부모의 병합 geometry(position 버퍼)를 공유해 `Box3.setFromObject()`가 모델 전체 범위를 반환. subset의 index 범위만 순회하는 `subsetWorldBox()`로 교체 (`frontend/test_subset_bbox.mjs`).

## 이상탐지 (`backend/app/analytics/anomaly.py`)

정답 라벨이 없고, 단일 센서의 자기 이력 학습은 "상시 고장"을 놓칩니다(VAV_7 차압이 −62.50 Pa로 고정 → 자기 이력 기준으론 정상). 탐지기를 셋으로 나눴습니다.

| 탐지기 | 방식 |
|---|---|
| stuck | 분산 0 → 값 고정 |
| sibling | 동종 센서군(VAV 1~7) 대비 robust z-score (median/MAD) |
| distribution | 이동중앙값 잔차의 robust z-score → 급변 |

실데이터(hourly) 결과: **81개 센서 중 7건** — 예) VAV_7 차압 1,026개 관측이 전부 −62.50 (robust z = −21.55). 

폐기한 접근: IsolationForest는 고정 contamination에서 77/81, auto에서 20–58%를 이상으로 판정했습니다. 원시값의 주야간 주기 때문입니다. 임계값 실험: `python backend/scripts/anomaly_lab.py`.

## 현황 / 한계

- 이상탐지는 독립 모듈 — **API·3D 하이라이트에는 아직 연결 전**
- 계통도(SVG) 패널, 시계열 차트 패널 미구현
- 실시간 스트림이 아니라 CSV 시간순 replay
- 단일 공조 계통 범위 (건물 전체 아님)

## 데이터 출처

원본은 저장소에 포함하지 않습니다.

- IFC: [Open IFC Model Repository](https://openifcmodel.cs.auckland.ac.nz/) — NBU Medical Clinic (Arch, Eng-HVAC; IFC2X3)
- 센서 데이터: 대련이공대(DUT) 건물 에너지 연구실 HVAC 운영 데이터 (2022-06~08, 1분/시간 단위)
