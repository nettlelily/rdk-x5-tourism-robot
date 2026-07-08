#!/usr/bin/env python3
import os
import re
import sys
import io
import time
import tempfile
import asyncio
import subprocess
import threading
import http.server
import socketserver
import numpy as np
import cv2
import anthropic
import edge_tts
from hobot_vio import libsrcampy

# ─── 配置 ───────────────────────────────────────────────
API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://agentrouter.org")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
TTS_VOICE = "zh-CN-XiaoxiaoNeural"
SYSTEM_PROMPT = "你是一个友好的中文语音助手。你的回答会被语音朗读，所以请注意：1. 用纯文本回答，不要使用任何Markdown格式（不要用#、*、>、-等符号）2. 回答简洁，控制在两三句话以内 3. 用口语化的表达方式"
MAX_HISTORY = 10

PHOTO_DIR = "/root/photos"
HTTP_PORT = 8080
CAM_WIDTH = 640
CAM_HEIGHT = 480
CAM_FPS = 30

# 全局：摄像头和最新帧
camera_lock = threading.Lock()
latest_frame = None  # JPEG bytes
cam_instance = None
cam_running = False


def strip_markdown(text):
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text.strip()


async def _synthesize(text, output_path):
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(output_path)


def speak(text):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    try:
        asyncio.run(_synthesize(text, mp3_path))
        subprocess.run(["mpg123", "-q", mp3_path], check=True)
    except Exception:
        pass
    finally:
        try:
            os.unlink(mp3_path)
        except OSError:
            pass


def nv12_to_jpeg(nv12_data, width, height):
    expected = width * height * 3 // 2
    actual = len(nv12_data)
    if actual != expected:
        height = actual * 2 // (width * 3)
        if width * height * 3 // 2 != actual:
            for w, h in [(3264, 2464), (1920, 1080), (1280, 720), (960, 540), (640, 480)]:
                if w * h * 3 // 2 == actual:
                    width, height = w, h
                    break
            else:
                for w in range(4096, 320, -16):
                    h = actual * 2 // (w * 3)
                    if h > 0 and w * h * 3 // 2 == actual:
                        width, height = w, h
                        break
    nv12 = np.frombuffer(nv12_data, dtype=np.uint8).reshape(height * 3 // 2, width)
    bgr = cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
    bgr = cv2.resize(bgr, (640, 480), interpolation=cv2.INTER_NEAREST)
    _, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 50])
    return jpeg.tobytes(), bgr


def camera_loop():
    global latest_frame, cam_instance, cam_running
    cam = libsrcampy.Camera()
    ret = cam.open_cam(0, -1, CAM_FPS, CAM_WIDTH, CAM_HEIGHT)
    if ret != 0:
        print("  [!] 摄像头打开失败", flush=True)
        return

    enc = libsrcampy.Encoder()
    enc_ret = enc.encode(0, 3, CAM_WIDTH, CAM_HEIGHT)

    cam_instance = cam
    cam_running = True
    use_hw = (enc_ret == 0)
    if use_hw:
        print(f"  [摄像头] 硬件MJPEG编码 {CAM_WIDTH}x{CAM_HEIGHT}", flush=True)
    else:
        print(f"  [摄像头] 软件编码 {CAM_WIDTH}x{CAM_HEIGHT}", flush=True)

    while cam_running:
        img = cam.get_img(2, CAM_WIDTH, CAM_HEIGHT)
        if img is not None:
            try:
                if use_hw:
                    enc.encode_file(img)
                    jpeg = enc.get_img()
                    if jpeg is not None:
                        with camera_lock:
                            latest_frame = bytes(jpeg)
                    else:
                        jpeg_data, _ = nv12_to_jpeg(img, CAM_WIDTH, CAM_HEIGHT)
                        with camera_lock:
                            latest_frame = jpeg_data
                else:
                    jpeg_data, _ = nv12_to_jpeg(img, CAM_WIDTH, CAM_HEIGHT)
                    with camera_lock:
                        latest_frame = jpeg_data
            except Exception:
                pass
        time.sleep(0.03)

    cam.close_cam()


def take_photo():
    global latest_frame
    os.makedirs(PHOTO_DIR, exist_ok=True)

    with camera_lock:
        frame = latest_frame

    if frame is None:
        return None, "没有可用的画面"

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"photo_{timestamp}.jpg"
    filepath = os.path.join(PHOTO_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(frame)
    with open(os.path.join(PHOTO_DIR, "latest.jpg"), "wb") as f:
        f.write(frame)

    return filename, None


class CameraHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_index()
        elif self.path == "/stream":
            self.send_stream()
        elif self.path == "/snapshot":
            self.send_snapshot()
        elif self.path == "/take_photo":
            self.send_take_photo()
        elif self.path.startswith("/photos/"):
            self.send_photo(self.path[8:])
        else:
            self.send_error(404)

    def send_index(self):
        os.makedirs(PHOTO_DIR, exist_ok=True)
        photos = sorted(
            [f for f in os.listdir(PHOTO_DIR) if f.endswith(".jpg") and f != "latest.jpg"],
            reverse=True
        )
        photo_html = "".join(f'<a href="/photos/{p}"><img src="/photos/{p}"></a>' for p in photos[:20])

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>RDK X5 摄像头</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:sans-serif;background:#1a1a1a;color:#fff;margin:0;padding:20px;text-align:center}}
h1{{margin:10px 0}}
.live{{border:2px solid #4CAF50;border-radius:8px;max-width:90%;margin:10px auto;display:block}}
button{{background:#4CAF50;color:#fff;border:none;padding:12px 24px;font-size:16px;border-radius:8px;cursor:pointer;margin:10px}}
button:hover{{background:#45a049}}
.grid{{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:20px}}
.grid img{{max-width:200px;border-radius:8px}}
#status{{color:#4CAF50;margin:5px}}
</style></head><body>
<h1>RDK X5 实时画面</h1>
<img class="live" id="live" src="/stream" alt="loading...">
<br>
<button onclick="capture()">拍照</button>
<span id="status"></span>
<h3>已拍照片</h3>
<div class="grid" id="photos">{photo_html}</div>
<script>
setInterval(()=>{{}}, 5000);
function capture(){{
  fetch('/take_photo').then(()=>{{
    document.getElementById('status').textContent='已拍照！';
    setTimeout(()=>location.reload(),1500);
  }});
}}
</script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def send_snapshot(self):
        with camera_lock:
            frame = latest_frame
        if frame is None:
            self.send_error(503, "No frame available")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(frame)

    def send_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while cam_running:
                with camera_lock:
                    frame = latest_frame
                if frame:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_photo(self, filename):
        filepath = os.path.join(PHOTO_DIR, filename)
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_take_photo(self):
        filename, err = take_photo()
        msg = err if err else f"OK: {filename}"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(msg.encode())


def start_http_server():
    os.makedirs(PHOTO_DIR, exist_ok=True)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("0.0.0.0", HTTP_PORT), CameraHandler)
    server.daemon_threads = True
    server.serve_forever()


def get_board_ip():
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.128.100", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.128.10"


def main():
    global cam_running

    if not API_KEY:
        print("错误：未设置 ANTHROPIC_AUTH_TOKEN")
        print("请运行：export ANTHROPIC_AUTH_TOKEN=你的密钥")
        return

    client = anthropic.Anthropic(api_key=API_KEY, base_url=BASE_URL)
    history = []
    board_ip = get_board_ip()

    # 启动摄像头线程
    cam_thread = threading.Thread(target=camera_loop, daemon=True)
    cam_thread.start()
    time.sleep(2)

    # 启动 HTTP 服务
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    print()
    print("═" * 48)
    print("  Claude 助手（文本 + 语音 + 实时摄像头）")
    print(f"  实时画面：http://{board_ip}:{HTTP_PORT}")
    print(f"  视频流：  http://{board_ip}:{HTTP_PORT}/stream")
    print("  输入问题回车发送 | 输入 拍照 保存当前画面")
    print("  输入 q 退出")
    print("═" * 48)
    print()

    try:
        while True:
            if not sys.stdin.isatty():
                time.sleep(1)
                continue
            try:
                text = input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                if not sys.stdin.isatty():
                    while cam_running:
                        time.sleep(1)
                break

            if not text:
                continue
            if text.lower() == "q":
                break

            if text in ("拍照", "拍照片", "拍一张", "capture", "photo"):
                print("  [拍] 正在拍照...", flush=True)
                filename, err = take_photo()
                if err:
                    print(f"  [!] {err}")
                else:
                    url = f"http://{board_ip}:{HTTP_PORT}/photos/{filename}"
                    print(f"  [OK] 拍照成功！")
                    print(f"  [链接] {url}")
                    speak("拍照成功")
                print()
                continue

            history.append({"role": "user", "content": text})
            if len(history) > MAX_HISTORY * 2:
                history[:] = history[-(MAX_HISTORY * 2):]

            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=300,
                    system=SYSTEM_PROMPT,
                    messages=history,
                )
                reply = ""
                for block in resp.content:
                    if hasattr(block, "text"):
                        reply += block.text
                if not reply:
                    reply = "收到了，但没有生成文本回复。"
                history.append({"role": "assistant", "content": reply})
            except Exception as e:
                reply = f"调用失败：{e}"

            print(f"助手> {reply}")
            speak(strip_markdown(reply))
            print()

    finally:
        cam_running = False
        print("再见！")


if __name__ == "__main__":
    main()
