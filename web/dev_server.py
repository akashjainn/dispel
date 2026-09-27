"""Run the website locally with the same routes Caddy serves on hocuspocus.tech (docker/remote-deploy.sh):

    /                 web/
    /Assets/*         app/Assets/
    /shared/<4 js>    app/src/renderer/{sprites,magic,voice,lessons}.js
    /web/analyze      proxied to the API server
    /health           proxied to the API server

Usage (from the repo root; standard library only):
    cd server && uvicorn app.main:app --port 8765     # the API, in another terminal
    python web/dev_server.py [--port 8080] [--api http://127.0.0.1:8765]
"""
import argparse
import http.server
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = {"sprites.js", "magic.js", "voice.js", "lessons.js"}
PROXIED = {"/web/analyze", "/health"}


class Handler(http.server.SimpleHTTPRequestHandler):
    api = "http://127.0.0.1:8765"

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/Assets/"):
            return self._inside(ROOT / "app" / "Assets", path[len("/Assets/"):])
        if path.startswith("/shared/"):
            name = path[len("/shared/"):]
            return str(ROOT / "app/src/renderer" / name) if name in SHARED else str(ROOT / "web" / "__missing__")
        return self._inside(ROOT / "web", path.lstrip("/"))

    @staticmethod
    def _inside(base: Path, rel: str) -> str:
        p = (base / rel).resolve()
        return str(p) if p.is_relative_to(base.resolve()) else str(base / "__missing__")

    def _proxy(self):
        body = None
        if self.command == "POST":
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        req = urllib.request.Request(self.api + self.path, data=body, method=self.command)
        if self.headers.get("Content-Type"):
            req.add_header("Content-Type", self.headers["Content-Type"])
        req.add_header("X-Forwarded-For", self.client_address[0])
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                status, ctype, data = r.status, r.headers.get("Content-Type", "application/json"), r.read()
        except urllib.error.HTTPError as e:
            status, ctype, data = e.code, e.headers.get("Content-Type", "application/json"), e.read()
        except OSError:
            status, ctype, data = 502, "application/json", b'{"error":"internal","message":"API server not reachable"}'
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?", 1)[0] in PROXIED:
            return self._proxy()
        super().do_GET()

    def do_POST(self):
        if self.path.split("?", 1)[0] in PROXIED:
            return self._proxy()
        self.send_error(405)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--api", default="http://127.0.0.1:8765")
    args = ap.parse_args()
    Handler.api = args.api.rstrip("/")
    print(f"http://127.0.0.1:{args.port}  (API: {Handler.api})")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
