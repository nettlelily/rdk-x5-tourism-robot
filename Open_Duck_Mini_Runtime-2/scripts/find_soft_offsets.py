"""
Find the offsets to set in joints_offsets in duck_config.json.
Uses standing position (init_pos) as reference instead of zero_pos.
"""
from mini_bdx_runtime.rustypot_position_hwi import HWI
from mini_bdx_runtime.duck_config import DuckConfig
import time

dummy_config = DuckConfig(config_json_path=None, ignore_default=True)

print("======")
print("此脚本将以站立姿态(init_pos)为参考，逐个关节校准偏移量")
print("请确保机器人有足够空间，运行前先断开舵机电源再重新上电")
print("======")
input("按回车开始。机器人将移动到站立姿态。随时按 Ctrl+C 停止。")

hwi = HWI(dummy_config)

# 不替换 init_pos，直接以站立姿态作为参考
hwi.set_kds([0] * len(hwi.joints))
hwi.turn_on()
time.sleep(1)

try:
    for i, joint_name in enumerate(hwi.joints.keys()):
        joint_id = hwi.joints[joint_name]
        ok = False
        while not ok:
            res = input(f" === 校准 {joint_name} (ID:{joint_id}) === 回车继续 / s跳过: ").lower()
            if res == "s":
                break

            # 回到站立参考位
            hwi.set_position_all(hwi.init_pos)
            time.sleep(0.5)
            current_pos = hwi.get_present_positions()[i]
            if current_pos is None:
                continue

            # 释放该关节扭矩，手动摆到目标位置
            hwi.io.disable_torque([joint_id])
            input(f"{joint_name} 已释放扭矩。手动摆到目标位置后按回车记录偏移量")
            new_pos = hwi.get_present_positions()[i]
            offset = new_pos - current_pos
            print(f" ---> 偏移量 = {offset:.4f} rad")

            # 上扭矩验证
            hwi.joints_offsets[joint_name] = offset
            input("按回车将舵机移回站立参考位（加偏移）")
            hwi.io.enable_torque([joint_id])
            hwi.set_position_all(hwi.init_pos)
            time.sleep(0.5)

            res = input("位置正确？(Y/n): ").lower()
            if res in ("y", ""):
                print(f"✓ {joint_name} offset = {offset:.4f}")
                ok = True
                print("------")
                print("当前 offsets:")
                for k, v in hwi.joints_offsets.items():
                    if v != 0:
                        print(f"  {k}: {v:.4f}")
                print("------\n")
            else:
                hwi.joints_offsets[joint_name] = 0.0
                print("重来\n")

    print("完成！将上面 offsets 写入 duck_config.json 的 joints_offsets")

except KeyboardInterrupt:
    hwi.turn_off()
