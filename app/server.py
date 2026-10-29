"""TAAS 로컬 서버 — 노트북에서 실행하고 브라우저로 http://localhost:8765 접속

실행:
    python -m app.server              # 가상 로스터 (연습·개발)
    python -m app.server --speed 5    # 5배속
    python -m app.server --port 9000
외부 라이브러리 없이 파이썬 기본 기능만 사용 (인터넷 없어도 동작)
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.session import RoastSession  # noqa: E402
from app.sources import SimulatedRoaster  # noqa: E402

STATIC = Path(__file__).with_name("static")
SESSION: RoastSession | None = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/api/state":
            return self._json(SESSION.state(int(q.get("since", 0)), int(q.get("alerts_since", 0))))
        if u.path == "/api/batches":
            return self._json(SESSION.list_batches())
        name = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        f = (STATIC / name).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}.get(f.suffix, "application/octet-stream")
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        b = self._body()
        routes = {
            "/api/charge": lambda: SESSION.charge(b.get("name", ""), float(b.get("weight") or 1.2), b.get("note", "")),
            "/api/control": lambda: SESSION.control(b["name"], float(b["value"]), bool(b.get("force"))),
            "/api/event": lambda: SESSION.event(b["type"]),
            "/api/finish": lambda: SESSION.finish(b.get("weight_out") and float(b["weight_out"]),
                                                  b.get("color_whole") and float(b["color_whole"]),
                                                  b.get("color_ground") and float(b["color_ground"]),
                                                  b.get("cup", "")),
            "/api/new": lambda: SESSION.new_batch(),
            "/api/speed": lambda: SESSION.set_speed(float(b["speed"])),
            "/api/reference": lambda: SESSION.set_reference(b.get("file")),
        }
        fn = routes.get(urlparse(self.path).path)
        if not fn:
            return self._json({"error": "not found"}, 404)
        try:
            return self._json(fn())
        except Exception as e:  # 화면에 이유를 보여주기 위해
            return self._json({"ok": False, "error": str(e)}, 400)


def main():
    global SESSION
    ap = argparse.ArgumentParser(description="TAAS 로스팅 프로그램")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--speed", type=float, default=1.0, help="가상 로스터 배속")
    args = ap.parse_args()
    SESSION = RoastSession(SimulatedRoaster(), speed=args.speed)
    SESSION.start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"TAAS 실행 중 → 브라우저에서 http://localhost:{args.port}  (끄려면 Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
