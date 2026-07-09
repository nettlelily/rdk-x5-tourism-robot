"""
读取所有舵机当前角度（弧度）
通过 rustypot 读取，自动将 0-4095 编码器值转换为弧度。
"""
from mini_bdx_runtime.rustypot_position_hwi import HWI
from mini_bdx_runtime.duck_config import DuckConfig
import time

config = DuckConfig(config_json_path=None, ignore_default=True)
config.joints_offset = {k: 0.0 for k in config.joints_offset}

hwi = HWI(config)
hwi.io.enable_torque(list(hwi.joints.values()))
time.sleep(0.3)

positions = hwi.io.read_present_position(list(hwi.joints.values()))

print("\n=== init_pos 格式 (弧度) ===\n")
print("self.init_pos = {")
for (name, _), pos in zip(hwi.joints.items(), positions):
    print(f'    "{name}": {round(pos, 4)},')
print("}")

print("\n=== 角度对照 ===\n")
for (name, _), pos in zip(hwi.joints.items(), positions):
    deg = round(pos * 57.3, 1)
    print(f"  {name:20s}  {pos:8.4f} rad  =  {deg:7.1f}°")

hwi.io.disable_torque(list(hwi.joints.values()))
