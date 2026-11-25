# HVAC 디지털 트윈 3D 뷰어 (프론트엔드)

BIM(IFC) 모델을 브라우저에서 파싱하고, 백엔드 API의 센서값을 시각에 따라
3D 요소(방·냉동기·AHU·VAV)에 색상으로 하이라이트하는 뷰어.

## 스택
- Vite + Three.js (`0.152.0`) + web-ifc-three (`0.0.126`) + web-ifc

## 실행
    npm install --legacy-peer-deps
    npm run dev        # http://localhost:5173

> `--legacy-peer-deps`: web-ifc-three의 peerDependency는 three@^0.149로 낡았지만
> 실제 코드는 three 0.152+의 `mergeGeometries`를 import하므로 0.152.0로 고정.

## 사용 흐름
1. 백엔드 기동: `uvicorn app.main:app --reload` (기본 http://127.0.0.1:8000)
2. 뷰어에서 IFC 2개 선택 — 건축(`NBU_MedicalClinic_Arch.ifc`), 설비(`NBU_MedicalClinic_Eng-HVAC.ifc`)
3. 두 모델이 로드되면 자동으로 `/groups`·`/meta/timerange` 조회 후
   IFC에서 GlobalId를 expressID로 인덱싱
4. 타임라인 슬라이더로 시각 이동 → `/state?t=`가 반환한 값으로 요소 색상 갱신
   (온도 센서가 있는 그룹은 파랑→빨강 그라디언트)
5. 좌측 그룹 클릭 → 카메라 포커스 + 해당 그룹 센서 상세값

## 하이라이트 대상 (12개, global_id 검증 완료)
- Room_1/2/3 (IfcSpace) · Chiller/AHU (IfcEnergyConversionDevice) · VAV_1~7 (IfcFlowController)
- Pump_*, CoolingTower는 모델에 형상이 없어 계통도 노드(추후 SVG 패널)로 표현 예정

## 검증 (브라우저 없이 인덱싱 체인 확인)
백엔드 `/groups` 실제 응답 + 실제 IFC로 `_buildGlobalIdIndex` 로직을 그대로 재현한다.

    # 1) 백엔드에서 실제 응답 덤프
    cd ../backend && PYTHONPATH=. python -c "
    from fastapi.testclient import TestClient; from app.main import app; import json
    json.dump(TestClient(app).get('/groups').json(), open('/tmp/groups.json','w'), ensure_ascii=False)"

    # 2) public/models/에 IFC 2개 두고, web-ifc 디렉토리에서 실행(wasm 경로 때문)
    cd ../frontend/node_modules/web-ifc && node ../../test_e2e_index.mjs
    # → 매칭 12 / 스캔 168, 하이라이트 12/12

## 알려진 함정 (해결됨)
- **subset의 bbox는 `Box3.setFromObject()`로 구하면 안 된다.** web-ifc-three의 subset은
  원본 모델의 병합 지오메트리를 공유하고 index만 다르므로, `geometry.boundingBox`가
  모델 전체 범위다 → 선택 표식이 건물 전체를 감싸고 카메라 포커스도 빗나간다.
  `subsetWorldBox()`로 index 범위만 순회할 것. 회귀 테스트: `node test_subset_bbox.mjs`
- **`logarithmicDepthBuffer`와 `polygonOffset`은 함께 못 쓴다.** 전자가 gl_FragDepth를
  직접 쓰기 때문에 polygonOffset이 무효화된다. 동일 평면(벽↔마감재) z-fighting은
  polygonOffset이 정답이므로 로그 깊이는 끈 상태를 유지할 것.
- **`/groups`에 `ifc_file`이 없으면 하이라이트가 전부 죽는다.** 프론트가 Arch/Eng 중
  어느 모델을 조회할지 결정하는 키라, 누락되면 모든 그룹이 인덱싱 전에 스킵되어
  "스캔 0"이 된다. 백엔드 `test_groups_expose_ifc_file_for_3d_highlighting`로 계약 고정.
- **web-ifc 0.0.39 브라우저 빌드는 IFC 타입 상수를 export하지 않는다.**
  `import { IFCSPACE } from "web-ifc"` → undefined. 타입코드를 직접 사용할 것.
- **modelID는 0부터 시작.** `if (!modelID)` 같은 falsy 체크 금지.
- **DB 타임스탬프는 타임존 없는 로컬 시각.** `toISOString()`으로 질의하면 KST 기준
  9시간 밀린다. `toLocalIso()`를 쓸 것.

## 조작
- **H** — 건축(Arch) 표시 토글
- **I** — 격리 모드(건물·설비 숨기고 하이라이트만)
- 그룹 클릭 — 카메라 포커스 + 흰색 bbox·수직 빔 표식(벽 뚫고 보임)

## WASM
`public/wasm/`에 web-ifc.wasm이 복사돼 있어야 함(IFCLoader.setWasmPath("/wasm/")).
`npm install` 후 다음으로 갱신:
    cp node_modules/web-ifc/*.wasm public/wasm/
