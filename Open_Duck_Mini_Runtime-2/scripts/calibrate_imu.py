"""
MPU6050 IMU calibration for RDK X5.
Run: sudo python3 scripts/calibrate_imu.py
Keep the robot STILL during calibration.
"""
from mini_bdx_runtime.mpu6050_imu import Imu

if __name__ == "__main__":
    imu = Imu(50, calibrate=True, upside_down=False)