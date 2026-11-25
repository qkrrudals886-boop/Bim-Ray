"""sensor_code_to_data_group.csv 생성 스크립트 (1회성, 결과물은 커밋해서 재사용).

WATER SIDE(32)는 배관 계통상 위치로, AIR SIDE(22)는 전부 AHU로,
USER SIDE(30)는 Room/VAV 쌍으로 그룹을 배정한다.
FAU/FCU/수측 VAV 환수온도(1-6/1-7/1-8)는 대응되는 data_group이 없어 UNMAPPED.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from app.loaders.hvac_csv import list_sensors

cat = list_sensors(Path(__file__).parent / "fine.csv")

GROUP_MAP = {
    # WATER SIDE
    "1-1": "Chiller", "1-2": "Chiller",
    "1-3": "CoolingTower", "1-4": "CoolingTower",
    "1-5": "AHU",
    "1-6": "UNMAPPED", "1-7": "UNMAPPED", "1-8": "UNMAPPED",
    "1-9": "Pump_CoolingWater", "1-10": "Pump_ChilledWater",
    "1-11": "Pump_CoolingWater", "1-12": "Pump_CoolingWater",
    "1-13": "Pump_CoolingWater", "1-14": "Pump_CoolingWater", "1-15": "Pump_CoolingWater",
    "1-16": "Pump_CoolingWater", "1-17": "Pump_CoolingWater", "1-18": "Pump_CoolingWater",
    "1-19": "Pump_ChilledWater", "1-20": "Pump_ChilledWater", "1-21": "Pump_ChilledWater",
    "1-22": "Pump_ChilledWater", "1-23": "Pump_ChilledWater", "1-24": "Pump_ChilledWater",
    "1-25": "Pump_ChilledWater", "1-26": "Pump_ChilledWater", "1-27": "Pump_ChilledWater",
    "1-28": "CoolingTower", "1-29": "CoolingTower", "1-30": "CoolingTower",
    "1-31": "Chiller", "1-32": "Chiller",
    # USER SIDE
    "3-1": "Room_1", "3-2": "Room_1", "3-3": "Room_1",
    "3-4": "VAV_1", "3-5": "VAV_1", "3-6": "VAV_1",
    "3-7": "VAV_2", "3-8": "VAV_2", "3-9": "VAV_2",
    "4-1": "Room_2", "4-2": "Room_2", "4-3": "Room_2",
    "4-4": "VAV_3", "4-5": "VAV_3", "4-6": "VAV_3",
    "4-7": "VAV_4", "4-8": "VAV_4", "4-9": "VAV_4",
    "5-1": "Room_3", "5-2": "Room_3", "5-3": "Room_3",
    "5-4": "VAV_5", "5-5": "VAV_5", "5-6": "VAV_5",
    "5-7": "VAV_6", "5-8": "VAV_6", "5-9": "VAV_6",
    "5-10": "VAV_7", "5-11": "VAV_7", "5-12": "VAV_7",
}
# AIR SIDE(2-1 .. 2-22)는 전부 AHU 계통 센서
for i in range(1, 23):
    GROUP_MAP[f"2-{i}"] = "AHU"

assert len(GROUP_MAP) == 84, len(GROUP_MAP)

cat["data_group"] = cat["sensor_code"].map(GROUP_MAP)
cat["confidence"] = cat["data_group"].map(lambda g: "high" if g != "UNMAPPED" else "n/a")
cat["notes"] = cat["sensor_code"].map(
    lambda c: "대응 data_group 없음 (IFC/계통도 미바인딩)" if GROUP_MAP[c] == "UNMAPPED" else ""
)

out_path = Path(__file__).parent / "sensor_code_to_data_group.csv"
cat.to_csv(out_path, index=False, encoding="utf-8")
print(f"wrote {out_path} ({len(cat)} rows)")
print(cat["data_group"].value_counts())
