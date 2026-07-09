"""手柄行走 + 拍照 + 语音：左摇杆移动 | A 暂停 | X 拍照 | 方向键 语音"""
import time, sys, os
import numpy as np
import pygame
from mini_bdx_runtime.rustypot_position_hwi import HWI
from mini_bdx_runtime.onnx_infer import OnnxInfer
from mini_bdx_runtime.mpu6050_imu import Imu
from mini_bdx_runtime.poly_reference_motion import PolyReferenceMotion
from mini_bdx_runtime.feet_contacts import FeetContacts
from mini_bdx_runtime.rl_utils import make_action_dict
from mini_bdx_runtime.duck_config import DuckConfig
from camera import Camera
from voice import Voice

# ====== 配置 ======
X_RANGE = [-0.08, 0.08]
Y_RANGE = [-0.15, 0.15]
YAW_RANGE = [-0.5, 0.5]

control_freq = 50
action_scale = 0.25

# ====== 摄像头 + 语音 ======
cam = Camera(photo_dir="/home/sunrise/Pictures") 
voice = Voice()

# ====== 初始化 ======
config = DuckConfig(ignore_default=True)

hwi = HWI(config)
hwi.set_kps([30] * 14)
hwi.set_kds([0] * 14)
hwi.turn_on()
time.sleep(2)

imu = Imu(sampling_freq=control_freq, upside_down=config.imu_upside_down)
feet = FeetContacts()
policy = OnnxInfer(os.path.join(os.path.dirname(__file__), "..", "BEST_WALK_ONNX_2.onnx"), awd=True)
prm = PolyReferenceMotion(os.path.join(os.path.dirname(__file__), "..", "polynomial_coefficients.pkl"))

cam.start()

# 初始化 pygame 后立即释放音频设备，避免与 espeak-ng 冲突
pygame.init()
pygame.mixer.quit()
joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"[手柄] {joystick.get_name()}")

init_pos = list(hwi.init_pos.values())
num_dofs = 14
motor_targets = np.array(init_pos)
last_action = np.zeros(num_dofs)
last_last_action = np.zeros(num_dofs)
last_last_last_action = np.zeros(num_dofs)

commands = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
imitation_i = 0
imitation_phase = np.array([0.0, 0.0])
paused = False
a_released = True
x_released = True
hat_x_prev = 0
hat_y_prev = 0

print("=== 手柄行走模式 ===")
print("左摇杆: 移动 | A: 暂停 | X: 拍照 | 方向键: 语音 | Ctrl+C: 退出")

try:
    i = 0
    while True:
        t = time.time()

        # ── 手柄 ──
        pygame.event.pump()

        l_x = -joystick.get_axis(0)
        l_y = -joystick.get_axis(1)
        r_x = -joystick.get_axis(2)
        if abs(l_x) < 0.05:
            l_x = 0.0
        if abs(l_y) < 0.05:
            l_y = 0.0
        if abs(r_x) < 0.05:
            r_x = 0.0

        commands[0] = l_y * (X_RANGE[1] if l_y >= 0 else abs(X_RANGE[0]))
        commands[1] = l_x * (Y_RANGE[1] if l_x >= 0 else abs(Y_RANGE[0]))
        commands[2] = r_x * (YAW_RANGE[1] if r_x >= 0 else abs(YAW_RANGE[0]))

        # A 键：暂停/继续
        a_now = joystick.get_button(0)
        if a_now and a_released:
            paused = not paused
            print("暂停" if paused else "继续")
        a_released = not a_now

        # X 键：拍照 + 语音
        x_now = joystick.get_button(3)
        if x_now and x_released:
            voice.speak("一，二，三，茄子！")
            filename, err = cam.take_photo()
            print(f"[!] {err}" if err else f"[拍照] {filename}")
        x_released = not x_now

        # 方向键：方向语音（消抖，只在按下瞬间触发）
        hat_x, hat_y = joystick.get_hat(0)
        if hat_y == 1 and hat_y_prev != 1:
            voice.speak("黄鹤楼雄踞武汉蛇山，为江南三大名楼之一。享有“天下江山第一楼”美誉，是闻名千古的历史文化地标。")
        elif hat_y == -1 and hat_y_prev != -1:
            voice.speak("后退")
        if hat_x == 1 and hat_x_prev != 1:
            voice.speak("右转")
        elif hat_x == -1 and hat_x_prev != -1:
            voice.speak("左转")
        hat_x_prev, hat_y_prev = hat_x, hat_y

        if paused:
            time.sleep(0.1)
            continue

        # ── 观测 ──
        imu_data = imu.get_data()
        dof_pos = hwi.get_present_positions()
        dof_vel = hwi.get_present_velocities()

        if dof_pos is None or dof_vel is None:
            time.sleep(0.02)
            continue

        imitation_i = (imitation_i + 1) % prm.nb_steps_in_period
        imitation_phase = np.array([
            np.cos(imitation_i / prm.nb_steps_in_period * 2 * np.pi),
            np.sin(imitation_i / prm.nb_steps_in_period * 2 * np.pi),
        ])

        obs = np.concatenate([
            imu_data["gyro"], imu_data["accelero"],
            commands,
            dof_pos - init_pos, dof_vel * 0.05,
            last_action, last_last_action, last_last_last_action,
            motor_targets,
            feet.get(),
            imitation_phase,
        ])

        # ── 推理 ──
        action = policy.infer(obs)
        last_last_last_action = last_last_action.copy()
        last_last_action = last_action.copy()
        last_action = action.copy()

        motor_targets = init_pos + action * action_scale
        hwi.set_position_all(make_action_dict(motor_targets, list(hwi.joints.keys())))

        if i % 50 == 0:
            print(f"[{i:4d}] vx={commands[0]:.2f} vy={commands[1]:.2f} | feet={feet.get()}")

        i += 1
        took = time.time() - t
        if 1 / control_freq - took > 0:
            time.sleep(1 / control_freq - took)

except KeyboardInterrupt:
    print("\n停止...")
    cam.stop()
    feet.stop()
    hwi.turn_off()
    pygame.quit()
    print("已退出")
