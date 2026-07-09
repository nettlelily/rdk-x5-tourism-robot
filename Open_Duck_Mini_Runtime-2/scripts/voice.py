"""RDK X5 语音模块 — edge_tts 微软中文神经语音"""
import os
import subprocess
import threading
import tempfile
import asyncio
import edge_tts


class Voice:
    """中文语音合成（edge_tts），音质自然，需联网

    用法:
        voice = Voice()
        voice.speak("你好")
        voice.speak("一，二，三，茄子！")
    """

    def __init__(self, voice="zh-CN-XiaoxiaoNeural"):
        self._voice = voice

    def speak(self, text):
        """朗读文字，后台线程执行，不阻塞主程序"""
        print(f"[语音] {text}")

        def _run():
            try:
                # 合成到临时文件
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    mp3_path = f.name
                asyncio.run(self._synthesize(text, mp3_path))
                # 播放
                subprocess.run(
                    ["mpg123", "-q", mp3_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # 清理
                os.unlink(mp3_path)
            except FileNotFoundError:
                print("[语音错误] 请安装: pip install edge_tts && sudo apt install mpg123")
            except Exception as e:
                print(f"[语音错误] {e}")

        threading.Thread(target=_run, daemon=True).start()

    async def _synthesize(self, text, output_path):
        communicate = edge_tts.Communicate(text, self._voice)
        await communicate.save(output_path)
