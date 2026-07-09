"""
安全版 turn_on：逐个舵机上扭矩、缓慢移到站立姿态，每步确认。
低速转动避免扭坏零件。
"""
from mini_bdx_runtime.rustypot_position_hwi import HWI
from mini_bdx_runtime.duck_config import DuckConfig
import time, sys

config = DuckConfig(ignore_default=True)
hwi = HWI(config)

ids = [int(v) for v in hwi.joints.values()]
names = list(hwi.joints.keys())

print("=== 逐个舵机上电 ===\n")

for i, name in enumerate(names):
    jid = ids[i]
    target = hwi.init_pos[name] + hwi.joints_offsets[name]

    r = input(f"[{i+1}/14] {name} ID:{jid} -> {target:.3f}rad | 回车继续 s跳过 q退出: ")
    if r == 'q': hwi.turn_off(); sys.exit(0)
    if r == 's': continue

    hwi.io.set_kps([jid], [2])
    hwi.io.enable_torque([jid]); time.sleep(0.1)
    cur = hwi.io.read_present_position([jid])[0]
    print(f"  当前 {cur:.3f} -> {target:.3f} (差 {target-cur:.3f}rad)")

    for s in range(1, 31):
        hwi.io.write_goal_position([jid], [cur + (target-cur)*s/30])
        time.sleep(0.02)
    hwi.io.set_kps([jid], [hwi.kps[i]])
    print(f"  OK {name}\n")

print("=== 完成 ===")
