// 백엔드 /groups 실제 응답 + 실제 IFC 파일 → 프론트 _buildGlobalIdIndex 로직 그대로 재현.
// ifc_file 누락 버그(4일차) 수정이 실제로 하이라이트를 살리는지 end-to-end 검증.
import { IfcAPI } from "web-ifc";
import fs from "fs";

// main.js와 동일한 상수/맵 (web-ifc 브라우저 빌드가 export 안 하므로 하드코딩)
const IFCSPACE = 3856911033;
const IFCENERGYCONVERSIONDEVICE = 1658829314;
const IFCFLOWCONTROLLER = 2058353004;
const IFC_TYPE_BY_NAME = {
  IfcSpace: IFCSPACE,
  IfcEnergyConversionDevice: IFCENERGYCONVERSIONDEVICE,
  IfcFlowController: IFCFLOWCONTROLLER,
};
const FILE_KEY = {
  "NBU_MedicalClinic_Arch.ifc": "arch",
  "NBU_MedicalClinic_Eng-HVAC.ifc": "eng",
};

const groups = JSON.parse(fs.readFileSync("/tmp/groups.json", "utf8"));

const api = new IfcAPI();
api.SetWasmPath("", true);
await api.Init();
const D = "/home/claude/frontend/public/models/";
const models = {
  arch: api.OpenModel(new Uint8Array(fs.readFileSync(D + "NBU_MedicalClinic_Arch.ifc"))),
  eng: api.OpenModel(new Uint8Array(fs.readFileSync(D + "NBU_MedicalClinic_Eng-HVAC.ifc"))),
};

// ---- 프론트 _buildGlobalIdIndex와 동일 로직 ----
const globalIdIndex = {};
const typeCache = new Map();
const diag = { scanned: 0, matched: 0, byType: {} };

for (const g of groups) {
  if (g.ifc_ref_kind !== "global_id") continue;
  const modelKey = FILE_KEY[g.ifc_file];
  const modelID = models[modelKey];
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
      globalIdIndex[g.data_group] = { modelKey, modelID, expressID };
      diag.matched++;
      break;
    }
  }
}
// ------------------------------------------------

console.log("타입별 요소수:", diag.byType);
console.log(`매칭: ${diag.matched} / 스캔: ${diag.scanned}\n`);
const geomGroups = groups.filter((g) => g.ifc_ref_kind === "global_id");
for (const g of geomGroups) {
  const hit = globalIdIndex[g.data_group];
  console.log(`  ${hit ? "OK " : "MISS"} ${g.data_group.padEnd(8)} ${g.ifc_file.replace("NBU_MedicalClinic_", "").padEnd(14)} ${hit ? "expressID " + hit.expressID : ""}`);
}
const n = Object.keys(globalIdIndex).length;
console.log(`\n하이라이트 가능: ${n}/${groups.length} (형상 있는 그룹 ${geomGroups.length}개 기준 ${n}/${geomGroups.length})`);
process.exit(n === geomGroups.length ? 0 : 1);
