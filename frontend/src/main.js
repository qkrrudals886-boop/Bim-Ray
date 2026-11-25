import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { IFCLoader } from "web-ifc-three/IFCLoader";

// web-ifc 0.0.39 브라우저 빌드(web-ifc-api.js)는 IFC 타입 상수를 export하지 않음
// (내부 var로만 존재) → import하면 undefined. 실제 타입코드를 직접 사용.
const IFCSPACE = 3856911033;
const IFCENERGYCONVERSIONDEVICE = 1658829314;
const IFCFLOWCONTROLLER = 2058353004;
import { HvacApi } from "./api.js";

const IFC_TYPE_BY_NAME = {
  IfcSpace: IFCSPACE,
  IfcEnergyConversionDevice: IFCENERGYCONVERSIONDEVICE,
  IfcFlowController: IFCFLOWCONTROLLER,
};

// data_groups.ifc_file 값 -> 로드된 모델 키
const FILE_KEY = {
  "NBU_MedicalClinic_Arch.ifc": "arch",
  "NBU_MedicalClinic_Eng-HVAC.ifc": "eng",
};

const CATEGORY_COLOR = {
  AHU: 0x4da3ff,
  VAV: 0x53c98b,
  Room: 0xe8c14a,
  Chiller: 0xff8a4d,
};
const HOVER_COLOR = 0xffffff;

function categoryOf(groupName) {
  if (groupName.startsWith("VAV")) return "VAV";
  if (groupName.startsWith("Room")) return "Room";
  return CATEGORY_COLOR[groupName] !== undefined ? groupName : "AHU";
}

// DB 타임스탬프는 타임존 없는 로컬 시각(2022-06-01T07:47:00).
// toISOString()은 UTC로 변환해 KST 기준 9시간 밀리므로 로컬 필드로 직접 포맷한다.
function toLocalIso(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T` +
         `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** web-ifc-three의 subset은 원본 모델의 병합 지오메트리를 공유하고 index만 다르다.
 *  따라서 geometry.boundingBox는 '모델 전체' 범위 → Box3.setFromObject()를 쓰면
 *  건물 전체를 감싸는 박스가 나온다. 실제 index 범위만 순회해 정확한 bbox를 구한다. */
function subsetWorldBox(mesh) {
  const box = new THREE.Box3();
  if (!mesh || !mesh.geometry) return box;
  const geom = mesh.geometry;
  const pos = geom.attributes && geom.attributes.position;
  if (!pos) return box;

  const v = new THREE.Vector3();
  const index = geom.index;
  if (index) {
    const start = (geom.drawRange && geom.drawRange.start) || 0;
    const range = geom.drawRange ? geom.drawRange.count : Infinity;
    const end = Math.min(index.count, start + (isFinite(range) ? range : index.count));
    for (let i = start; i < end; i++) {
      v.fromBufferAttribute(pos, index.getX(i));
      box.expandByPoint(v);
    }
  } else {
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      box.expandByPoint(v);
    }
  }
  mesh.updateWorldMatrix(true, false);
  if (!box.isEmpty()) box.applyMatrix4(mesh.matrixWorld);
  return box;
}

function tempGradient(value, min = 15, max = 32) {
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  // 파랑(차가움) -> 빨강(뜨거움)
  const c1 = new THREE.Color(0x4da3ff);
  const c2 = new THREE.Color(0xff4d4d);
  return c1.clone().lerp(c2, t);
}

class App {
  constructor() {
    this.el = {
      viewer: document.getElementById("viewer"),
      status: document.getElementById("status"),
      legend: document.getElementById("legend"),
      archFile: document.getElementById("archFile"),
      engFile: document.getElementById("engFile"),
      apiBase: document.getElementById("apiBase"),
      timeline: document.getElementById("timeline"),
      timeLabel: document.getElementById("timeLabel"),
      groupList: document.getElementById("groupList"),
      detail: document.getElementById("detail"),
    };

    this.models = {}; // key -> modelID
    this.globalIdIndex = {}; // groupName -> { modelKey, expressID }
    this.subsets = {}; // groupName -> THREE.Mesh
    this.groups = [];
    this.timeRange = null;
    this.selectedGroup = null;

    this._initScene();
    this._initEvents();
    this.setStatus("IFC 파일 2개를 선택하세요 (Arch, Eng-HVAC).");
  }

  setStatus(msg) { this.el.status.textContent = msg; }

  _initScene() {
    const w = this.el.viewer.clientWidth;
    const h = this.el.viewer.clientHeight;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x10161c);

    this.camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 2000);
    this.camera.position.set(30, 30, 30);

    // 주의: logarithmicDepthBuffer는 gl_FragDepth를 직접 쓰기 때문에 polygonOffset이 무효화된다.
    // 동일 평면(벽/마감재) z-fighting의 표준 해법은 polygonOffset이므로 로그 깊이는 끈다.
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(w, h);
    this.el.viewer.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(50, 80, 30);
    this.scene.add(dir);
    this.scene.add(new THREE.AxesHelper(5));

    this.ifcLoader = new IFCLoader();
    this.ifcLoader.ifcManager.setWasmPath("/wasm/");

    window.addEventListener("resize", () => {
      const w2 = this.el.viewer.clientWidth, h2 = this.el.viewer.clientHeight;
      this.camera.aspect = w2 / h2;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w2, h2);
    });

    const animate = () => {
      requestAnimationFrame(animate);
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
    };
    animate();
  }

  _initEvents() {
    this.el.archFile.addEventListener("change", (e) => this._loadModel(e.target.files[0], "arch"));
    this.el.engFile.addEventListener("change", (e) => this._loadModel(e.target.files[0], "eng"));
    this.el.timeline.addEventListener("input", () => this._onTimelineChange());
    // H: 건축 표시 토글 / I: 격리 모드(건물·설비 숨기고 하이라이트만)
    window.addEventListener("keydown", (e) => {
      const k = e.key.toLowerCase();
      if (k === "h") {
        if (this._archModel) {
          this._archModel.visible = !this._archModel.visible;
          this.setStatus(`건축 표시: ${this._archModel.visible ? "ON" : "OFF"} (H로 토글)`);
        }
      } else if (k === "i") {
        this._isolate = !this._isolate;
        if (this._archModel) this._archModel.visible = !this._isolate;
        if (this._engModel) this._engModel.visible = !this._isolate;
        this.setStatus(`격리 모드: ${this._isolate ? "ON — 하이라이트만 표시" : "OFF"} (I로 토글)`);
      }
    });
  }

  async _loadModel(file, key) {
    if (!file) return;
    this.setStatus(`${key === "arch" ? "건축" : "설비"} IFC 파싱 중... (수 초 소요)`);
    const url = URL.createObjectURL(file);
    const model = await this.ifcLoader.loadAsync(url);

    // 건축(Arch)은 반투명 고스트로 → 내부 설비/하이라이트가 보이고, 겹침 z-fighting 완화
    if (key === "arch") this._prepareArch(model);
    else this._engModel = model;

    this.scene.add(model);
    this.models[key] = model.modelID;
    URL.revokeObjectURL(url);
    this.setStatus(`모델 로드 완료: ${key}`);
    this._frameAll();
    await this._maybeConnect();
  }

  _prepareArch(model) {
    // 건축 모델은 벽(2145) 위에 마감재(IfcCovering 250)가 정확히 겹쳐 있어
    // 깊이값이 동일 → z-fighting(얼룩). polygonOffset으로 살짝 뒤로 밀어 분리한다.
    const applyOffset = (mat) => {
      mat.polygonOffset = true;
      mat.polygonOffsetFactor = 1;
      mat.polygonOffsetUnits = 1;
      return mat;
    };
    model.traverse((child) => {
      if (!child.isMesh) return;
      child.renderOrder = -1;
      if (Array.isArray(child.material)) child.material = child.material.map(applyOffset);
      else if (child.material) applyOffset(child.material);
    });
    this._archModel = model;
  }

  _frameAll() {
    const box = new THREE.Box3();
    this.scene.traverse((obj) => { if (obj.isMesh) box.expandByObject(obj); });
    if (box.isEmpty()) return;
    this._sceneBox = box.clone();
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    this.controls.target.copy(center);
    this.camera.position.copy(center).add(new THREE.Vector3(size * 0.5, size * 0.5, size * 0.5));
    // near를 너무 작게 잡으면 깊이 정밀도가 무너져 z-fighting 악화.
    // 건물 규모 대비 충분히 크게(약 1/500 → 벽 두께보다 크게) 잡는다.
    this.camera.near = Math.max(size / 500, 0.5);
    this.camera.far = size * 8;
    this.camera.updateProjectionMatrix();
  }

  async _maybeConnect() {
    // 두 모델이 다 로드돼야 GlobalId 인덱싱 + 백엔드 연결 진행.
    // 주의: web-ifc modelID는 0부터라 falsy 체크(!this.models.arch) 금지 → "key in obj"로만 판정.
    if (!("arch" in this.models) || !("eng" in this.models)) {
      const missing = !("arch" in this.models) ? "건축(Arch)" : "설비(Eng-HVAC)";
      this.setStatus(`${missing} IFC를 마저 선택하면 센서 하이라이트가 시작됩니다.`);
      return;
    }

    this.api = new HvacApi(this.el.apiBase.value);
    try {
      this.groups = await this.api.groups();
      this.timeRange = await this.api.timerange();
    } catch (err) {
      this.setStatus(`백엔드 연결 실패: ${err.message} (uvicorn app.main:app 기동 확인)`);
      return;
    }

    this.setStatus(`IFC에서 GlobalId 인덱싱 중...`);
    await this._buildGlobalIdIndex();
    this._renderGroupList();
    this._setupTimeline();
    const nIdx = Object.keys(this.globalIdIndex).length;
    const nGeom = this.groups.filter((g) => g.ifc_ref_kind === "global_id").length;
    if (nIdx < nGeom && this._indexDiag) {
      const bt = Object.entries(this._indexDiag.byType).map(([k, v]) => `${k}:${v}`).join(", ");
      this.setStatus(`하이라이트 ${nIdx}/${nGeom} — 타입스캔[${bt}]. F12 콘솔 확인`);
    } else {
      this.setStatus(`준비 완료 — 3D 하이라이트 ${nIdx}개 · 계통도 ${this.groups.length - nGeom}개 (H: 건축 표시 토글)`);
    }
    await this._refreshAtCurrentTime();
  }

  async _buildGlobalIdIndex() {
    const manager = this.ifcLoader.ifcManager;
    // 저수준 web-ifc API 직접 사용(getItemProperties의 jsonData 경로 우회).
    // web-ifc 0.0.39의 GetLineIDsWithType/GetLine은 동기.
    const api = manager.ifcAPI || manager.state.api;

    const typeCache = new Map(); // `${modelID}:${type}` -> [expressID...]
    const diag = { scanned: 0, matched: 0, byType: {} };

    for (const g of this.groups) {
      if (g.ifc_ref_kind !== "global_id") continue; // LOGICAL 노드는 3D 형상 없음
      const modelKey = FILE_KEY[g.ifc_file];
      const modelID = this.models[modelKey];
      const typeConst = IFC_TYPE_BY_NAME[g.ifc_element_type];
      if (modelID === undefined || typeConst === undefined) continue;

      const cacheKey = `${modelID}:${typeConst}`;
      let ids = typeCache.get(cacheKey);
      if (!ids) {
        const vec = api.GetLineIDsWithType(modelID, typeConst);
        ids = [];
        const n = vec.size ? vec.size() : 0;
        for (let i = 0; i < n; i++) ids.push(vec.get(i));
        typeCache.set(cacheKey, ids);
        diag.byType[`${g.ifc_element_type}@${modelKey}`] = ids.length;
      }

      for (const expressID of ids) {
        diag.scanned++;
        const line = api.GetLine(modelID, expressID);
        const gid = line && line.GlobalId && line.GlobalId.value;
        if (gid === g.ifc_ref) {
          this.globalIdIndex[g.data_group] = { modelKey, modelID, expressID };
          diag.matched++;
          break;
        }
      }
    }

    // 브라우저 콘솔 + 화면 진단(0이면 원인 파악용)
    console.log("[GlobalId 인덱싱] 타입별 요소수:", diag.byType,
                "| 매칭:", diag.matched, "/ 스캔:", diag.scanned,
                "| 인덱스:", this.globalIdIndex);
    this._indexDiag = diag;
  }

  _renderGroupList() {
    this.el.groupList.innerHTML = "";
    this.el.legend.innerHTML =
      Object.entries(CATEGORY_COLOR)
        .map(([k, c]) => `<span class="dot" style="background:#${c.toString(16).padStart(6, "0")}"></span>${k}&nbsp;&nbsp;`)
        .join("") +
      `<span style="color:#7d8ea3;margin-left:8px;">|&nbsp; H 건축 숨김 · I 격리</span>`;

    for (const g of this.groups) {
      const li = document.createElement("li");
      const hasGeom = !!this.globalIdIndex[g.data_group];
      const cat = categoryOf(g.data_group);
      const color = CATEGORY_COLOR[cat] ?? 0x888888;
      li.innerHTML = `<span><span class="dot" style="background:#${color.toString(16).padStart(6, "0")}"></span>${g.data_group}</span>` +
        `<span style="color:#7d8ea3;font-size:11px;">${hasGeom ? "3D" : "계통도"}</span>`;
      li.addEventListener("click", () => this._selectGroup(g.data_group));
      this.el.groupList.appendChild(li);
    }
  }

  _setupTimeline() {
    if (!this.timeRange) return;
    this._tMin = new Date(this.timeRange.fine_min).getTime();
    this._tMax = new Date(this.timeRange.fine_max).getTime();
    this.el.timeline.value = 0;
    this._onTimelineChange();
  }

  _currentTimestamp() {
    if (!this._tMin) return undefined;
    const frac = Number(this.el.timeline.value) / 1000;
    const t = new Date(this._tMin + frac * (this._tMax - this._tMin));
    return toLocalIso(t);
  }

  async _onTimelineChange() {
    const ts = this._currentTimestamp();
    this.el.timeLabel.textContent = `시각: ${ts ?? "-"}`;
    await this._refreshAtCurrentTime();
  }

  async _refreshAtCurrentTime() {
    if (!this.api) return;
    const ts = this._currentTimestamp();
    const state = await this.api.state(ts);

    for (const g of this.groups) {
      const idx = this.globalIdIndex[g.data_group];
      if (!idx) continue; // LOGICAL 노드는 계통도 패널에서 별도 표현 (TODO)

      const sensors = this._sensorsOfGroup(g.data_group);
      const tempCode = sensors.find((s) => (s.unit || "").includes("℃"))?.sensor_code;
      const color = tempCode && state.values[tempCode] != null
        ? tempGradient(state.values[tempCode])
        : new THREE.Color(CATEGORY_COLOR[categoryOf(g.data_group)] ?? 0x888888);

      this._highlight(g.data_group, idx, color);
    }

    if (this.selectedGroup) await this._showDetail(this.selectedGroup, ts);
  }

  _sensorsOfGroup(groupName) {
    // sensor_code_to_data_group 매핑은 백엔드에만 있으므로, /sensors/{group} 캐시로 대체
    return this._sensorCache?.[groupName] ?? [];
  }

  _highlight(groupName, idx, color) {
    const manager = this.ifcLoader.ifcManager;
    const material = new THREE.MeshLambertMaterial({
      color,
      emissive: new THREE.Color(color).multiplyScalar(0.35),
      transparent: false,
      // 건축(+1)과 반대로 앞으로 당겨, 방 표면과 겹쳐도 하이라이트가 이긴다
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    });
    const mesh = manager.createSubset({
      modelID: idx.modelID,
      ids: [idx.expressID],
      scene: this.scene,
      removePrevious: true,
      customID: `hl-${groupName}`,
      material,
    });
    if (mesh) mesh.renderOrder = 2; // 건축(-1)·설비(0)보다 앞
    this.subsets[groupName] = mesh;
  }

  /** 선택 요소의 위치 표식: 벽을 뚫고 보이는 바운딩박스 + 지붕 위로 솟는 수직 빔.
   *  건물 내부의 VAV/Room을 밖에서도 즉시 찾을 수 있게 한다. */
  _setSelectionMarker(mesh) {
    if (this._marker) {
      this.scene.remove(this._marker);
      this._marker.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) o.material.dispose();
      });
      this._marker = null;
    }
    if (!mesh) return;
    const box = subsetWorldBox(mesh);
    if (box.isEmpty()) return;

    const group = new THREE.Group();
    const MARK = 0xffffff;

    const helper = new THREE.Box3Helper(box, new THREE.Color(MARK));
    helper.material.depthTest = false;   // 벽 뒤에서도 보이게
    helper.material.transparent = true;
    helper.material.opacity = 0.95;
    helper.renderOrder = 999;
    group.add(helper);

    // 지붕 위까지 솟는 수직 빔(핀) — 멀리서도 위치 파악
    const c = box.getCenter(new THREE.Vector3());
    const topY = (this._sceneBox ? this._sceneBox.max.y : box.max.y) + box.getSize(new THREE.Vector3()).y;
    const beamGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(c.x, box.min.y, c.z),
      new THREE.Vector3(c.x, topY, c.z),
    ]);
    const beam = new THREE.Line(
      beamGeo,
      new THREE.LineBasicMaterial({ color: MARK, depthTest: false, transparent: true, opacity: 0.6 })
    );
    beam.renderOrder = 999;
    group.add(beam);

    this.scene.add(group);
    this._marker = group;
  }

  async _selectGroup(groupName) {
    this.selectedGroup = groupName;
    [...this.el.groupList.children].forEach((li, i) =>
      li.classList.toggle("active", this.groups[i].data_group === groupName)
    );
    await this._showDetail(groupName, this._currentTimestamp());

    const idx = this.globalIdIndex[groupName];
    if (idx) {
      const mesh = this.subsets[groupName];
      this._setSelectionMarker(mesh);
      if (mesh) {
        const box = subsetWorldBox(mesh);
        if (!box.isEmpty()) {
          const center = box.getCenter(new THREE.Vector3());
          // VAV/AHU는 수십 cm급이라 bbox가 작음 → 최소 거리 확보해 화면에 잡히게
          const size = Math.max(box.getSize(new THREE.Vector3()).length(), 4);
          const dist = size * 2.5;
          this.controls.target.copy(center);
          this.camera.position.copy(center).add(new THREE.Vector3(dist, dist * 0.8, dist));
          this.camera.updateProjectionMatrix();
        }
      }
      this.setStatus(`${groupName} 선택 — I: 격리(건물 숨김), H: 건축 표시`);
    } else {
      this._setSelectionMarker(null);
      this.setStatus(`${groupName}은 모델에 형상이 없습니다 (계통도 노드)`);
    }
  }

  async _showDetail(groupName, ts) {
    const data = await this.api.sensorsByGroup(groupName, ts);
    this._sensorCache = this._sensorCache ?? {};
    this._sensorCache[groupName] = data.sensors;

    const rows = data.sensors
      .map((s) => `<tr><td class="name">${s.sensor_name}</td><td class="val">${s.value ?? "-"}</td></tr>`)
      .join("");
    this.el.detail.innerHTML = `
      <div style="font-weight:600;margin-bottom:6px;">${groupName} <span style="color:#7d8ea3;font-weight:400;">(${data.timestamp ?? "-"})</span></div>
      <table>${rows}</table>
    `;
  }
}

new App();
