"""RDK X5 摄像头模块 — 采集 + Web 实时画面 + 拍照"""
import os
import time
import threading
import http.server
import socketserver
import socket
import cv2
import numpy as np
from hobot_vio import libsrcampy


class Camera:
    """RDK X5 MIPI CSI 摄像头，自带 HTTP 实时画面服务

    用法:
        cam = Camera(photo_dir="/home/sunrise/Pictures")
        cam.start()          # 打开摄像头 + 启动 Web 服务
        filename, err = cam.take_photo()   # 拍照
        cam.stop()           # 关闭
    """

    def __init__(self, photo_dir="/home/sunrise/Pictures", port=8080,
                 width=1920, height=1080, fps=30, rotation=270):
        self.photo_dir = photo_dir
        self.port = port
        self.width = width
        self.height = height
        self.fps = fps
        self.rotation = rotation  # 0, 90, 180, 270

        self._lock = threading.Lock()
        self._latest_frame = None    # JPEG bytes
        self._running = False
        self._cam = None
        self._enc = None
        self._use_hw = False
        self._server = None

    # ─── public API ───────────────────────────────────────────

    def start(self):
        """启动摄像头 + HTTP 服务（后台 daemon 线程）"""
        threading.Thread(target=self._camera_loop, daemon=True).start()
        time.sleep(1.5)  # 等摄像头就绪
        threading.Thread(target=self._http_loop, daemon=True).start()

        ip = self._get_ip()
        print(f"[摄像头] {self.width}x{self.height} @ {self.fps}fps")
        print(f"[Web]    http://{ip}:{self.port}")

    def stop(self):
        """关闭摄像头和 HTTP 服务"""
        self._running = False
        if self._server:
            self._server.shutdown()

    def take_photo(self):
        """保存当前帧为 JPEG，返回 (filename, error_msg)"""
        os.makedirs(self.photo_dir, exist_ok=True)
        with self._lock:
            frame = self._latest_frame
        if frame is None:
            return None, "没有可用的画面"

        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"photo_{ts}.jpg"
        filepath = os.path.join(self.photo_dir, filename)
        with open(filepath, "wb") as f:
            f.write(frame)
        # 同时存一份 latest.jpg 方便取用
        with open(os.path.join(self.photo_dir, "latest.jpg"), "wb") as f:
            f.write(frame)
        return filename, None

    # ─── 内部 ──────────────────────────────────────────────────

    def _camera_loop(self):
        """后台线程：摄像头采集 + MJPEG 编码"""
        self._cam = libsrcampy.Camera()
        ret = self._cam.open_cam(0, -1, self.fps, self.width, self.height)
        if ret != 0:
            print("[!] 摄像头打开失败")
            return

        # 尝试硬件 MJPEG 编码
        self._enc = libsrcampy.Encoder()
        enc_ret = self._enc.encode(0, 3, self.width, self.height)
        self._use_hw = (enc_ret == 0)
        if self._use_hw:
            print(f"[摄像头] 硬件 MJPEG 编码")
        else:
            print(f"[摄像头] 软件编码 (cv2)")

        self._running = True
        while self._running:
            img = self._cam.get_img(2, self.width, self.height)
            if img is not None:
                try:
                    if self._use_hw:
                        self._enc.encode_file(img)
                        jpeg = self._enc.get_img()
                        if jpeg is not None:
                            jpeg_data = self._apply_rotation(bytes(jpeg))
                        else:
                            jpeg_data = self._nv12_to_jpeg(img)
                        with self._lock:
                            self._latest_frame = jpeg_data
                    else:
                        jpeg_data = self._nv12_to_jpeg(img)
                        with self._lock:
                            self._latest_frame = jpeg_data
                except Exception:
                    pass
            time.sleep(1 / self.fps)

        self._cam.close_cam()

    def _nv12_to_jpeg(self, nv12_data):
        """NV12 → JPEG（软件回退）"""
        expected = self.width * self.height * 3 // 2
        actual = len(nv12_data)
        w, h = self.width, self.height
        if actual != expected:
            for tw, th in [(3264, 2464), (1920, 1080), (1280, 720), (960, 540), (640, 480)]:
                if tw * th * 3 // 2 == actual:
                    w, h = tw, th
                    break
        nv12 = np.frombuffer(nv12_data, dtype=np.uint8).reshape(h * 3 // 2, w)
        bgr = cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
        bgr = cv2.resize(bgr, (self.width, self.height), interpolation=cv2.INTER_NEAREST)
        _, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return self._apply_rotation(jpeg.tobytes())

    def _apply_rotation(self, jpeg_data):
        """对 JPEG 做旋转（decode → rotate → re-encode）"""
        if self.rotation == 0:
            return jpeg_data
        nparr = np.frombuffer(jpeg_data, np.uint8)
        bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if self.rotation == 90:
            bgr = cv2.rotate(bgr, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotation == 180:
            bgr = cv2.rotate(bgr, cv2.ROTATE_180)
        elif self.rotation == 270:
            bgr = cv2.rotate(bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
        _, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()

    # ─── HTTP 服务 ─────────────────────────────────────────────

    def _http_loop(self):
        """后台线程：HTTP 服务器"""
        # 把 self 注入 handler
        cam_self = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(s, *args):
                pass  # 安静模式

            def do_GET(s):
                if s.path == "/":
                    s._send_index()
                elif s.path == "/stream":
                    s._send_stream()
                elif s.path == "/snapshot":
                    s._send_snapshot()
                elif s.path == "/take_photo":
                    s._send_take_photo()
                elif s.path.startswith("/photos/"):
                    s._send_photo(s.path[8:])
                else:
                    s.send_error(404)

            def _send_index(s):
                os.makedirs(cam_self.photo_dir, exist_ok=True)
                try:
                    photos = sorted(
                        [f for f in os.listdir(cam_self.photo_dir)
                         if f.endswith(".jpg") and f != "latest.jpg"],
                        reverse=True)
                except Exception:
                    photos = []
                photo_html = "".join(
                    f'<a href="/photos/{p}"><img src="/photos/{p}"></a>'
                    for p in photos[:20])

                html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>RDK X5 实时画面</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:sans-serif;background:#1a1a1a;color:#fff;margin:0;padding:20px;text-align:center}}
h1{{margin:10px 0;font-size:1.4em}}
.live{{border:2px solid #4CAF50;border-radius:8px;max-width:95%;margin:10px auto;display:block}}
button{{background:#4CAF50;color:#fff;border:none;padding:12px 24px;font-size:16px;border-radius:8px;cursor:pointer;margin:10px}}
button:hover{{background:#45a049}}
.grid{{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:20px}}
.grid img{{max-width:160px;border-radius:8px}}
#status{{color:#4CAF50;margin:5px}}
</style></head><body>
<h1>RDK X5 {cam_self.width}x{cam_self.height}</h1>
<img class="live" id="live" src="/stream" alt="loading...">
<br>
<button onclick="capture()">拍照</button>
<span id="status"></span>
<h3>已拍照片</h3>
<div class="grid" id="photos">{photo_html}</div>
<script>
function capture(){{
  fetch('/take_photo').then(()=>{{
    document.getElementById('status').textContent='已拍照!';
    setTimeout(()=>location.reload(),1500);
  }});
}}
</script></body></html>"""
                s.send_response(200)
                s.send_header("Content-Type", "text/html; charset=utf-8")
                s.end_headers()
                s.wfile.write(html.encode())

            def _send_snapshot(s):
                with cam_self._lock:
                    frame = cam_self._latest_frame
                if frame is None:
                    s.send_error(503)
                    return
                s.send_response(200)
                s.send_header("Content-Type", "image/jpeg")
                s.send_header("Content-Length", str(len(frame)))
                s.send_header("Cache-Control", "no-cache")
                s.end_headers()
                s.wfile.write(frame)

            def _send_stream(s):
                s.send_response(200)
                s.send_header("Content-Type",
                              "multipart/x-mixed-replace; boundary=frame")
                s.send_header("Cache-Control", "no-cache")
                s.end_headers()
                try:
                    while cam_self._running:
                        with cam_self._lock:
                            frame = cam_self._latest_frame
                        if frame:
                            s.wfile.write(b"--frame\r\n")
                            s.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                            s.wfile.write(frame)
                            s.wfile.write(b"\r\n")
                            s.wfile.flush()
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _send_photo(s, filename):
                filepath = os.path.join(cam_self.photo_dir, filename)
                if not os.path.isfile(filepath) or ".." in filename:
                    s.send_error(404)
                    return
                with open(filepath, "rb") as f:
                    data = f.read()
                s.send_response(200)
                s.send_header("Content-Type", "image/jpeg")
                s.send_header("Content-Length", str(len(data)))
                s.end_headers()
                s.wfile.write(data)

            def _send_take_photo(s):
                filename, err = cam_self.take_photo()
                msg = err if err else f"OK: {filename}"
                s.send_response(200)
                s.send_header("Content-Type", "text/plain")
                s.end_headers()
                s.wfile.write(msg.encode())

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self._server = socketserver.ThreadingTCPServer(("0.0.0.0", self.port), Handler)
        self._server.daemon_threads = True
        self._server.serve_forever()

    @staticmethod
    def _get_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("192.168.128.100", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "unknown"
