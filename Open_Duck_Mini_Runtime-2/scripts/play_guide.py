import os
import subprocess
from gtts import gTTS

# ---------------- 配置区 ----------------
# 你想播报的固定文本
GUIDE_TEXT = """
大家好，欢迎来到黄鹤楼。
"""

# 音频文件保存路径
AUDIO_FILE = "huanghelou_intro.mp3"

# 你的 I2S 声卡设备名称（可通过 aplay -l 查看）
# 如果系统默认声卡就是 I2S，可以将其留空。如果要强制指定硬件，比如 hw:1,0，请修改此处。
ALSA_DEVICE = "plughw:0,0"# ----------------------------------------

def generate_speech():
    """将文本转换为语音文件并保存"""
    if not os.path.exists(AUDIO_FILE):
        print("未检测到本地音频，正在生成语音文件（请确保设备已联网）...")
        try:
            # lang='zh-cn' 代表使用中文
            tts = gTTS(text=GUIDE_TEXT, lang='zh-cn')
            tts.save(AUDIO_FILE)
            print(f"语音生成成功，已保存至: {AUDIO_FILE}")
        except Exception as e:
            print(f"语音生成失败，请检查网络: {e}")
            return False
    else:
        print("检测到本地已有语音文件，跳过生成步骤。")
    return True

def play_audio():
    """使用 mpg123 通过 I2S 播放音频"""
    if not os.path.exists(AUDIO_FILE):
        print("错误：音频文件不存在，无法播放。")
        return
        
    print("开始播放讲解...")
    
    # 构建播放命令
    # 选项 -q 表示静默模式（不打印播放进度条）
    if ALSA_DEVICE:
        cmd = ["mpg123", "-q", "-a", ALSA_DEVICE, AUDIO_FILE]
    else:
        cmd = ["mpg123", "-q", AUDIO_FILE]
        
    try:
        # 使用 subprocess 调用系统播放器，阻塞直到播放完成
        subprocess.run(cmd, check=True)
        print("播放结束。")
    except subprocess.CalledProcessError as e:
        print(f"播放失败，请检查声卡配置或依赖是否正确安装: {e}")
    except FileNotFoundError:
        print("未找到 mpg123，请使用 sudo apt install mpg123 安装。")

if __name__ == "__main__":
    # 1. 生成语音（如果已存在则跳过）
    if generate_speech():
        # 2. 播放语音
        play_audio()