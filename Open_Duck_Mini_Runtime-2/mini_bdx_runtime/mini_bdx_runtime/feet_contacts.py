"""
Foot contact sensors for RDK X5 via Hobot.GPIO.

Replaces CircuitPython (board/digitalio) with Hobot.GPIO.
Uses BOARD pin numbering on RDK X5 40-pin header.

Left foot  = Pin 37 (BCM GPIO 26)
Right foot = Pin 13 (BCM GPIO 27)

HARDWARE: Connect a 10kΩ pull-up resistor between each GPIO pin and 3.3V.
Switch closure pulls pin LOW → contact=True (active low).
（微动开关一端接GPIO，一端接GND，GPIO到3.3V之间接10kΩ上拉电阻）
"""

import Hobot.GPIO as GPIO
import time

LEFT_FOOT_PIN = 37   # BOARD mode: physical pin 37 = GPIO 26
RIGHT_FOOT_PIN = 13  # BOARD mode: physical pin 13 = GPIO 27

DEBOUNCE_COUNT = 3   # Number of consecutive consistent readings before state change


class FeetContacts:
    def __init__(self):
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(LEFT_FOOT_PIN, GPIO.IN)
        GPIO.setup(RIGHT_FOOT_PIN, GPIO.IN)

        # Stable output state
        self._left_stable = False
        self._right_stable = False

        # Debounce counters
        self._left_cnt = 0
        self._right_cnt = 0

    def get(self):
        raw_left = not GPIO.input(LEFT_FOOT_PIN)
        raw_right = not GPIO.input(RIGHT_FOOT_PIN)

        # Left foot debounce
        if raw_left == self._left_stable:
            self._left_cnt = 0
        else:
            self._left_cnt += 1
            if self._left_cnt >= DEBOUNCE_COUNT:
                self._left_stable = raw_left
                self._left_cnt = 0

        # Right foot debounce
        if raw_right == self._right_stable:
            self._right_cnt = 0
        else:
            self._right_cnt += 1
            if self._right_cnt >= DEBOUNCE_COUNT:
                self._right_stable = raw_right
                self._right_cnt = 0

        return [self._left_stable, self._right_stable]

    def stop(self):
        GPIO.cleanup()


if __name__ == "__main__":
    feet_contacts = FeetContacts()
    try:
        while True:
            print(feet_contacts.get())
            time.sleep(0.05)
    finally:
        feet_contacts.stop()
