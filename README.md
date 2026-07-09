Project Name:Intelligent bipedal companion robot based on RDK X5 and AI automatic composition optimization.
Contains 3 subdirectories: Basic_Bipedal_Movement_Demo, Claude_Smart_QA_Demo, and Command_Photography_Upload_Demo.

Basic_Bipedal_Movement_Demo
This contains the runtime code for the robot's motion control. The robot adopts a bipedal structure design, possesses basic physical spatial mobility, and can stably execute commands to walk straight, turn left, and turn right. See the documentation in the corresponding subdirectory for details.

Claude_Smart_QA_Demo
This contains the runtime code for the robot's intelligent interaction. The system backend integrates the Claude Large Language Model API. The robot serves as an interaction hub, calling Claude in real-time to analyze and answer various questions raised by visitors, providing a smooth consultation experience. See the documentation in the corresponding subdirectory for details.

Command_Photography_Upload_Demo
This contains the runtime code for the robot's visual acquisition and network transmission. The device is equipped with a visual capture module and supports command triggering. Upon receiving the "take a photo" input command, the robot will invoke the camera to capture an image, and subsequently upload the generated picture automatically to a pre-configured specified network server address. See the documentation in the corresponding subdirectory for details.
