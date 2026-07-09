from pypot.feetech import FeetechSTS3215IO
import time

joints = {
    "right_hip_yaw": 10,
    "right_hip_roll": 11,
    "right_hip_pitch": 12,
    "right_knee": 13,
    "right_ankle": 14,
    "left_hip_yaw": 20,
    "left_hip_roll": 21,
    "left_hip_pitch": 22,
    "left_knee": 23,
    "left_ankle": 24,
    "neck_pitch": 30,
    "head_pitch": 31,
    "head_yaw": 32,
    "head_roll": 33,
}

io = FeetechSTS3215IO("/dev/ttyACM0", baudrate=1000000)

for name, motor_id in joints.items():
    for attempt in range(3):
        try:
            time.sleep(0.1)
            io.set_lock({motor_id: 0})
            time.sleep(0.05)
            io.set_acceleration({motor_id: 0})
            time.sleep(0.05)
            io.set_maximum_acceleration({motor_id: 0})
            time.sleep(0.05)
            io.set_lock({motor_id: 1})
            time.sleep(0.05)
            acc = io.get_acceleration([motor_id])
            time.sleep(0.05)
            max_acc = io.get_maximum_acceleration([motor_id])
            print(f"[{motor_id:2d}] {name:20s}  acc={acc}  max_acc={max_acc}")
            break
        except Exception as e:
            print(f"[{motor_id:2d}] {name:20s}  attempt {attempt+1} failed: {e}")
            time.sleep(0.3)
    else:
        print(f"[{motor_id:2d}] {name:20s}  FAILED after 3 attempts")

print("\nDone.")
