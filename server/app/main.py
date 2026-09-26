"""FastAPI wrapper around the hearsay pipeline. Contract: docs/INTERFACES.md.

If MODEL_DIR contains hearsay.json the real pipeline is loaded at startup (mock: false).
Otherwise the canned example is returned (mock: true), so the app and tests work without weights."""
import hmac
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

VERSION = "0.3"
ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "analyze_response.example.json"
log = logging.getLogger("dispel")

_PIPE = None
_PIPE_ERR = None
_LOCK = threading.Lock()  # one inference at a time: bounded memory on a small CPU instance


def _model_dir():
    d = os.getenv("MODEL_DIR")
    return Path(d) if d else None


def _load_pipeline():
    global _PIPE, _PIPE_ERR
    d = _model_dir()
    if not d or not (d / "hearsay.json").is_file():
        return
    try:
        from hearsay.orchestrator import Pipeline  # heavy imports (torch) only when weights exist
        _PIPE = Pipeline(d, device=None if os.getenv("DEVICE", "cpu") == "cuda" else "cpu")
        log.info("hearsay pipeline loaded from %s", d)
    except Exception as e:  # keep serving the mock rather than crash-looping
        _PIPE_ERR = f"{type(e).__name__}: {e}"
        log.exception("could not load hearsay pipeline")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(_load_pipeline)  # ~20 s on CPU: sha256 checks + model load
    yield


app = FastAPI(title="dispel server", version=VERSION, lifespan=lifespan)


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
    d = _model_dir()  # lost+found etc.: a freshly formatted volume is not "weights found"
    return bool(d) and d.is_dir() and any(p.name != "lost+found" and not p.name.startswith(".") for p in d.iterdir())


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
    body = {"ok": True, "model": _PIPE.spec["name"] if _PIPE else "mock", "device": os.getenv("DEVICE", "cpu"),
            "version": VERSION, "mock": _PIPE is None, "weights_found": _weights_present()}
    if _PIPE_ERR:
        body["load_error"] = _PIPE_ERR
    return body


def _run(data: bytes, prior: float):
    with _LOCK:
        return _PIPE.analyze(data, prior)


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

    if _PIPE is None:
        resp = json.loads(EXAMPLE.read_text())
        resp["version"] = VERSION
        resp["clip_id"] = str(uuid.uuid4())
        resp["overall"]["prior"] = prior
        resp["timing_ms"] = int((time.perf_counter() - t0) * 1000)
        return resp
    try:
        return await run_in_threadpool(_run, data, prior)  # audio lives only in memory / a deleted temp file
    except ValueError as e:
        code = str(e).split(":")[0]
        if code == "too_short":
            raise ApiError(400, "too_short", "clip shorter than 1 s")
        if code == "too_long":
            raise ApiError(413, "too_long", "clip longer than 120 s")
        raise ApiError(400, "decode_failed", "could not decode audio")
    except Exception:
        log.exception("analyze failed")
        raise ApiError(500, "internal", "analysis failed")
