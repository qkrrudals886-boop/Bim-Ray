import * as THREE from "three";

// subsetWorldBox (main.js와 동일 로직)
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
    for (let i = start; i < end; i++) { v.fromBufferAttribute(pos, index.getX(i)); box.expandByPoint(v); }
  } else {
    for (let i = 0; i < pos.count; i++) { v.fromBufferAttribute(pos, i); box.expandByPoint(v); }
  }
  mesh.updateWorldMatrix(true, false);
  if (!box.isEmpty()) box.applyMatrix4(mesh.matrixWorld);
  return box;
}

// 시나리오: 건물 전체(0..100) 정점 버퍼를 공유하고, index는 작은 VAV(0..1)만 가리킴
const positions = new Float32Array([
  0,0,0,  1,0,0,  1,1,0,   // VAV (작은 요소) 정점 0,1,2
  0,0,0, 100,0,0, 100,80,0, // 건물 반대편 정점 3,4,5
  50,40,60,                 // 먼 정점 6
]);
const geom = new THREE.BufferGeometry();
geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
geom.setIndex([0,1,2]);           // subset = VAV 삼각형만
const mesh = new THREE.Mesh(geom, new THREE.MeshBasicMaterial());

const wrong = new THREE.Box3().setFromObject(mesh);   // 기존 방식
const right = subsetWorldBox(mesh);                    // 수정 방식
const s = (b) => `min(${b.min.x},${b.min.y},${b.min.z}) max(${b.max.x},${b.max.y},${b.max.z})`;
console.log("기존 setFromObject :", s(wrong));
console.log("수정 subsetWorldBox:", s(right));
const ok = right.max.x === 1 && right.max.y === 1 && wrong.max.x === 100;
console.log("\n결과:", ok ? "OK — 수정본만 subset 실제 범위를 반환" : "FAIL");
process.exit(ok ? 0 : 1);
