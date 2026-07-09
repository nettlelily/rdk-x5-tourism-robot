import json
from typing import Optional
import os

# 默认配置路径：项目根目录下的 duck_config.json
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG_PATH = os.path.join(_PROJECT_DIR, "duck_config.json")


class DuckConfig:

    def __init__(
        self,
        config_json_path: Optional[str] = None,
        ignore_default: bool = False,
    ):
        if config_json_path is None:
            config_json_path = DEFAULT_CONFIG_PATH
        """
        Looks for duck_config.json in the home directory by default.
        If not found, uses default values.
        """
        self.default = False
        try:
            self.json_config = (
                json.load(open(config_json_path, "r")) if config_json_path else {}
            )
        except FileNotFoundError:
            print(
                f"Warning : didn't find the config json file at {config_json_path}, using default values"
            )
            self.json_config = {}
            self.default = True

        if config_json_path is None:
            print("Warning : didn't provide a config json path, using default values")
            self.default = True

        if self.default and not ignore_default:
            print("")
            print("")
            print("")
            print("")
            print("======")
            print(
                "WARNING : Running with default values probably won't work well. Please make a duck_config.json file and set the parameters."
            )
            res = input("Do you still want to run ? (y/N)")
            if res.lower() != "y":
                print("Exiting...")
                exit(1)

        self.start_paused = self.json_config.get("start_paused", False)
        self.imu_upside_down = self.json_config.get("imu_upside_down", False)
        self.phase_frequency_factor_offset = self.json_config.get(
            "phase_frequency_factor_offset", 0.0
        )

        expression_features = self.json_config.get("expression_features", {})

        self.eyes = expression_features.get("eyes", False)
        self.projector = expression_features.get("projector", False)
        self.antennas = expression_features.get("antennas", False)
        self.speaker = expression_features.get("speaker", False)
        self.microphone = expression_features.get("microphone", False)
        self.camera = expression_features.get("camera", False)

        # default joints offsets are 0.0
        self.joints_offset = self.json_config.get(
            "joints_offsets",
            {
                "left_hip_yaw": 0.0,
                "left_hip_roll": 0.0,
                "left_hip_pitch": 0.0,
                "left_knee": 0.0,
                "left_ankle": 0.0,
                "neck_pitch": 0.0,
                "head_pitch": 0.0,
                "head_yaw": 0.0,
                "head_roll": 0.00,
                "right_hip_yaw": 0.0,
                "right_hip_roll": 0.0,
                "right_hip_pitch": 0.0,
                "right_knee": 0.0,
                "right_ankle": 0.0,
            },
        )
