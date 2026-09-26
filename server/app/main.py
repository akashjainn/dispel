"""FastAPI wrapper around the hearsay pipeline. Contract: docs/INTERFACES.md."""
import hmac
import json
import os
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

VERSION = "0.2"
ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "analyze_response.example.json"

app = FastAPI(title="dispel server", version=VERSION)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)


@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail, "message": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "bad_request", "message": "invalid request"}, status_code=400)


def require_key(authorization: str | None = Header(default=None)) -> None:
    key = os.getenv("API_KEY")
    if not key:  # local dev: auth off
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, key):
        raise HTTPException(status_code=401, detail="unauthorized")


def _weights_present() -> bool:
    d = os.getenv("MODEL_DIR")
    return bool(d) and Path(d).is_dir() and any(Path(d).iterdir())


LANDING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Team Gemini</title>
<style>html,body{height:100%;margin:0}body{display:grid;place-items:center;background:#0b0d12;color:#e8eaf0;
font:600 clamp(2rem,8vw,4rem) system-ui,sans-serif;letter-spacing:.02em}</style></head>
<body><h1>Team Gemini</h1></body></html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing():
    return LANDING


@app.get("/health")
def health():
    # `mock` is true until hearsay/ is wired in and weights are mounted.
    return {"ok": True, "model": "v2e", "device": os.getenv("DEVICE", "cpu"),
            "version": VERSION, "mock": True, "weights_found": _weights_present()}


@app.post("/analyze", dependencies=[Depends(require_key)])
async def analyze(file: UploadFile = File(...), prior: float = Form(0.5)):
    t0 = time.perf_counter()
    if not 0.0 <= prior <= 1.0:
        raise ApiError(400, "bad_request", "prior must be between 0 and 1")
    if Path(file.filename or "").suffix.lower() not in ALLOWED_EXT:
        raise ApiError(400, "decode_failed", "unsupported file type")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "too_long", "file too large")
    if not data:
        raise ApiError(400, "too_short", "empty file")

    # TODO(hearsay): decode with ffmpeg, run hearsay.orchestrator, return the real result.
    resp = json.loads(EXAMPLE.read_text())
    resp["version"] = VERSION
    resp["clip_id"] = str(uuid.uuid4())
    resp["overall"]["prior"] = prior
    resp["timing_ms"] = int((time.perf_counter() - t0) * 1000)
    return resp
