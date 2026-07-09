"""打印 Xbox 手柄原始按键编号和摇杆轴值"""
import pygame, time

pygame.init(); pygame.joystick.init()
j = pygame.joystick.Joystick(0); j.init()
print(f"手柄: {j.get_name()} | 轴数:{j.get_numaxes()} 按键数:{j.get_numbuttons()}")
print("逐个按键按一遍，记录编号")

while True:
    pygame.event.pump()
    btns = [i for i in range(j.get_numbuttons()) if j.get_button(i)]
    axes = {i: round(j.get_axis(i), 3) for i in range(j.get_numaxes()) if abs(j.get_axis(i)) > 0.05}
    hat = j.get_hat(0)
    if btns or axes or hat != (0, 0):
        if btns: print(f"按键编号: {btns}")
        if axes: print(f"摇杆轴:   {axes}")
        if hat != (0, 0): print(f"方向键:   {hat}")
        print("-" * 30)
    time.sleep(0.05)
