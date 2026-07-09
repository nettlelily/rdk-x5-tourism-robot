"""
MPU6050 IMU driver for RDK X5
Replaces raw_imu.py (BNO055) with identical Imu class interface.

Uses I2C5 (pins 3/5, /dev/i2c-5, addr 0x68).
Output format matches raw_imu.py exactly: {"gyro": [x,y,z], "accelero": [x,y,z]}
"""

import smbus2
import numpy as np
import time
import os
import pickle
from queue import Queue
from threading import Thread

MPU6050_ADDR = 0x68

# Registers
PWR_MGMT_1 = 0x6B
ACCEL_CONFIG = 0x1C
GYRO_CONFIG = 0x1B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H = 0x43
SMPLRT_DIV = 0x19
CONFIG = 0x1A

# Conversion factors
# Accel: ±2g -> 16384 LSB/g -> m/s^2
ACCEL_SCALE = 9.81 / 16384.0
# Gyro: ±250 deg/s -> 131 LSB/(deg/s) -> rad/s
GYRO_SCALE = np.pi / 180.0 / 131.0


class Imu:
    def __init__(
        self, sampling_freq, user_pitch_bias=0, calibrate=False, upside_down=True
    ):
        self.sampling_freq = sampling_freq
        self.calibrate = calibrate
        self.upside_down = upside_down

        # Open I2C bus 5 (pins 3/5 on RDK X5)
        self.bus = smbus2.SMBus(5)

        # Wake up MPU6050 (clear sleep bit in PWR_MGMT_1)
        self.bus.write_byte_data(MPU6050_ADDR, PWR_MGMT_1, 0x00)
        time.sleep(0.1)

        # Configure accelerometer: ±2g
        self.bus.write_byte_data(MPU6050_ADDR, ACCEL_CONFIG, 0x00)
        # Configure gyroscope: ±250 deg/s
        self.bus.write_byte_data(MPU6050_ADDR, GYRO_CONFIG, 0x00)
        # Set sample rate divider: 0 -> 1kHz / (1+0) = 1kHz internal sampling
        self.bus.write_byte_data(MPU6050_ADDR, SMPLRT_DIV, 0x00)
        # Digital low-pass filter: DLPF_CFG=0 -> 260Hz bandwidth (gyro), 260Hz (accel)
        self.bus.write_byte_data(MPU6050_ADDR, CONFIG, 0x00)

        # Calibration: collect static samples to compute gyro bias
        self.gyro_bias = np.zeros(3)
        self.accel_bias = np.zeros(3)

        calib_file = "mpu6050_calib_data.pkl"

        if calibrate:
            print("Calibrating MPU6050: keep the robot STILL...")
            gyro_samples = []
            accel_samples = []
            for _ in range(200):
                gx, gy, gz = self._read_gyro_raw()
                ax, ay, az = self._read_accel_raw()
                gyro_samples.append([gx, gy, gz])
                accel_samples.append([ax, ay, az])
                time.sleep(0.01)
            self.gyro_bias = np.mean(gyro_samples, axis=0)
            self.accel_bias = np.mean(accel_samples, axis=0)
            # Z accel bias should read 1g, subtract that
            self.accel_bias[2] -= 9.81

            calib_data = {
                "gyro_bias": self.gyro_bias.tolist(),
                "accel_bias": self.accel_bias.tolist(),
            }
            pickle.dump(calib_data, open(calib_file, "wb"))
            print("Calibration done. Saved to", calib_file)
            print("Gyro bias:", self.gyro_bias)
            print("Accel bias:", self.accel_bias)
            exit()

        if os.path.exists(calib_file):
            calib_data = pickle.load(open(calib_file, "rb"))
            self.gyro_bias = np.array(calib_data["gyro_bias"])
            self.accel_bias = np.array(calib_data["accel_bias"])
            print("Loaded MPU6050 calibration from", calib_file)
        else:
            print("mpu6050_calib_data.pkl not found, running uncalibrated")

        self.last_imu_data = {
            "gyro": [0.0, 0.0, 0.0],
            "accelero": [0.0, 0.0, 0.0],
        }
        self.imu_queue = Queue(maxsize=1)
        Thread(target=self.imu_worker, daemon=True).start()

    def _read_gyro_raw(self):
        """Read raw gyroscope values and convert to rad/s"""
        data = self.bus.read_i2c_block_data(MPU6050_ADDR, GYRO_XOUT_H, 6)
        gx = self._combine_bytes(data[0], data[1]) * GYRO_SCALE
        gy = self._combine_bytes(data[2], data[3]) * GYRO_SCALE
        gz = self._combine_bytes(data[4], data[5]) * GYRO_SCALE
        return gx, gy, gz

    def _read_accel_raw(self):
        """Read raw accelerometer values and convert to m/s^2"""
        data = self.bus.read_i2c_block_data(MPU6050_ADDR, ACCEL_XOUT_H, 6)
        ax = self._combine_bytes(data[0], data[1]) * ACCEL_SCALE
        ay = self._combine_bytes(data[2], data[3]) * ACCEL_SCALE
        az = self._combine_bytes(data[4], data[5]) * ACCEL_SCALE
        return ax, ay, az

    @staticmethod
    def _combine_bytes(high, low):
        """Combine two bytes into signed 16-bit integer"""
        val = (high << 8) | low
        if val >= 0x8000:
            val -= 0x10000
        return val

    def imu_worker(self):
        while True:
            s = time.time()
            try:
                gx, gy, gz = self._read_gyro_raw()
                ax, ay, az = self._read_accel_raw()
            except Exception as e:
                print("[MPU6050]:", e)
                continue

            # Apply calibration bias
            gyro = np.array([gx, gy, gz]) - self.gyro_bias
            accelero = np.array([ax, ay, az]) - self.accel_bias

            # Axis remapping for upside_down mounting
            if self.upside_down:
                # Same axis remap as original BNO055 upside_down mode:
                # Y->X, X->Y, Z->Z, all negated
                gyro = np.array([gyro[1], gyro[0], gyro[2]]) * -1
                accelero = np.array([accelero[1], accelero[0], accelero[2]]) * -1
            else:
                # Right-side-up: Y->X, X->Y, Z->Z, X negated, Y/Z positive
                gyro = np.array([-gyro[1], gyro[0], gyro[2]])
                accelero = np.array([-accelero[1], accelero[0], accelero[2]])

            data = {
                "gyro": gyro,
                "accelero": accelero,
            }

            self.imu_queue.put(data)
            took = time.time() - s
            time.sleep(max(0, 1 / self.sampling_freq - took))

    def get_data(self):
        try:
            self.last_imu_data = self.imu_queue.get(False)  # non-blocking
        except Exception:
            pass
        return self.last_imu_data

    def tare_x(self):
        """Stub: MPU6050 doesn't have BNO055's tare feature.
        Calibration bias handles this role."""
        pass


if __name__ == "__main__":
    imu = Imu(50, upside_down=False)
    while True:
        data = imu.get_data()
        print("gyro", np.around(data["gyro"], 3))
        print("accelero", np.around(data["accelero"], 3))
        print("---")
        time.sleep(1 / 25)
