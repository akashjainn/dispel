"""FastAPI wrapper around the hearsay pipeline. Contract: docs/INTERFACES.md.

If MODEL_DIR contains hearsay.json the real pipeline is loaded at startup (mock: false).
Otherwise, if HF_MODEL is set, a third-party Hugging Face detector stands in (hf_model.py, mock: false).
Otherwise a demo answer built from the canned example is returned (mock: true), so the app and tests work
without weights: about 70% likely synthetic, 30% likely real. Calls may omit the file while mocked (no call
audio is captured yet).
Requests that carry X-Dispel-Client (an anonymous per-install UUID) are recorded in store.py for GET /history."""
import hmac
import json
import logging
import math
import os
import random
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from . import store

VERSION = "0.6"
# Anything ffmpeg can decode; video containers keep only their audio track.
ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".oga", ".opus", ".flac", ".aac", ".mp4", ".mov"}
SOURCES = {"file", "call"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "analyze_response.example.json"
MOCK_SYNTHETIC_SHARE = 0.7  # demo answers only: share that come out likely synthetic, the rest likely real
log = logging.getLogger("dispel")

_PIPE = None
_HF = None  # stand-in used only when _PIPE did not load
_LOAD_ERRS: list[str] = []
_LOCK = threading.Lock()  # one inference at a time: bounded memory on a small CPU instance


def _model_dir():
    d = os.getenv("MODEL_DIR")
    return Path(d) if d else None


def _load_pipeline():
    global _PIPE
    d = _model_dir()
    if not d or not (d / "hearsay.json").is_file():
        return
    try:
        from hearsay.orchestrator import Pipeline  # heavy imports (torch) only when weights exist
        _PIPE = Pipeline(d, device=None if os.getenv("DEVICE", "cpu") == "cuda" else "cpu",
                         profile=os.getenv("FUSION_PROFILE", "app"))
        log.info("hearsay pipeline loaded from %s", d)
    except Exception as e:  # keep serving the mock rather than crash-looping
        _LOAD_ERRS.append(f"hearsay: {type(e).__name__}: {e}")
        log.exception("could not load hearsay pipeline")


def _load_hf():
    global _HF
    repo = os.getenv("HF_MODEL")
    if _PIPE is not None or not repo:
        return
    try:
        from .hf_model import HFDetector  # heavy imports (torch); first run downloads the weights into HF_HOME
        _HF = HFDetector(repo, os.getenv("HF_REVISION") or None)
        log.info("stand-in model %s loaded", repo)
    except Exception as e:
        _LOAD_ERRS.append(f"{repo}: {type(e).__name__}: {e}")
        log.exception("could not load %s", repo)


def _load_models():
    _load_pipeline()
    _load_hf()


def _active():
    """The model answering checks, or None when answers are demo data."""
    return _PIPE if _PIPE is not None else _HF


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(_load_models)  # ~20 s on CPU: sha256 checks + model load (+ a one-time HF download)
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


def client_id(x_dispel_client: str | None = Header(default=None)) -> str | None:
    """The app's anonymous per-install id. Optional on /analyze (curl, tests); must be a UUID if sent."""
    if x_dispel_client is None:
        return None
    try:
        return str(uuid.UUID(x_dispel_client))
    except ValueError:
        raise ApiError(400, "bad_request", "X-Dispel-Client must be a UUID")


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
    name = _PIPE.spec["name"] if _PIPE else _HF.name if _HF else "mock"
    body = {"ok": True, "model": name, "device": os.getenv("DEVICE", "cpu"),
            "version": VERSION, "mock": _active() is None, "weights_found": _weights_present()}
    if _LOAD_ERRS:
        body["load_error"] = "; ".join(_LOAD_ERRS)
    return body


def _run(data: bytes, prior: float):
    with _LOCK:
        return _active().analyze(data, prior)


@app.post("/analyze", dependencies=[Depends(require_key)])
async def analyze(file: UploadFile | None = File(None), prior: float = Form(0.5), source: str = Form("file"),
                  client: str | None = Depends(client_id)):
    resp = await _analyze(file, prior, source)
    if client:
        try:
            await run_in_threadpool(store.record, client, source, resp)
        except Exception:  # history is a convenience; never fail a check over it
            log.exception("could not record check")
    return resp


@app.get("/history", dependencies=[Depends(require_key)])
async def history(limit: int = Query(20, ge=1, le=100), client: str | None = Depends(client_id)):
    if not client:
        raise ApiError(400, "bad_request", "X-Dispel-Client header is required")
    return {"client_id": client, "items": await run_in_threadpool(store.history, client, limit)}


def _sigmoid(t: float) -> float:
    return 1.0 / (1.0 + math.exp(-t))


def _mock(prior: float, t0: float) -> dict:
    """The canned example, turned into a likely-synthetic or likely-real demo answer (MOCK_SYNTHETIC_SHARE)."""
    resp = json.loads(EXAMPLE.read_text())
    synthetic = random.random() < MOCK_SYNTHETIC_SHARE
    llr = round(random.uniform(1.8, 3.5) if synthetic else -random.uniform(1.8, 3.5), 2)
    p = _sigmoid(llr + math.log(prior / (1 - prior))) if 0 < prior < 1 else prior
    verdict = "likely_synthetic" if p >= 0.75 else "likely_real" if p <= 0.25 else "inconclusive"
    dl, prosody = resp["analyzers"]
    dl["llr_contribution"], prosody["llr_contribution"] = round(llr * 0.75, 2), round(llr * 0.25, 2)
    if not synthetic:
        for seg in resp["segments"]:
            seg["llr"] = round(-random.uniform(1.2, 3.5), 2)
            seg["probability"] = round(_sigmoid(seg["llr"]), 3)
        dl["finding"] = f"Neural detector score {llr * 1.1:+.1f} over 3 window(s) of 4 s."
        prosody["finding"] = "Prosody: pitch range, pitch movement, shimmer and jitter all typical of real speech."
        resp["limitations"] = [
            "This model has not been validated on every commercial voice generator.",
            "A 'likely real' result is not proof the voice is genuine: new voice clones can score low.",
        ]
    resp["overall"] = {"llr": llr, "prior": prior, "probability": round(p, 3), "verdict": verdict}
    resp["version"] = VERSION
    resp["clip_id"] = str(uuid.uuid4())
    resp["timing_ms"] = int((time.perf_counter() - t0) * 1000)
    resp["mock"] = True
    return resp


async def _analyze(file: UploadFile | None, prior: float, source: str) -> dict:
    t0 = time.perf_counter()
    if not 0.0 <= prior <= 1.0:
        raise ApiError(400, "bad_request", "prior must be between 0 and 1")
    if source not in SOURCES:
        raise ApiError(400, "bad_request", "source must be file or call")
    if file is None:  # calls have no captured audio yet; only the mock can answer them
        if source != "call":
            raise ApiError(400, "bad_request", "file is required")
        if _active() is not None:
            raise ApiError(400, "too_short", "no call audio sent")
        return _mock(prior, t0)
    if Path(file.filename or "").suffix.lower() not in ALLOWED_EXT:
        raise ApiError(400, "decode_failed", "unsupported file type")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "too_long", "file too large")
    if not data:
        raise ApiError(400, "too_short", "empty file")

    if _active() is None:
        return _mock(prior, t0)
    try:
        resp = await run_in_threadpool(_run, data, prior)  # audio lives only in memory / a deleted temp file
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
    resp["version"] = VERSION
    resp["mock"] = False
    return resp
