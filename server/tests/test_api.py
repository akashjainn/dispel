import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FILE = {"file": ("clip.wav", b"RIFFxxxx", "audio/wav")}


def test_landing_page():
    r = client.get("/")
    assert r.status_code == 200 and "Team Gemini" in r.text


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_analyze_matches_contract():
    r = client.post("/analyze", files=FILE, data={"prior": "0.3"})
    assert r.status_code == 200
    body = r.json()
    assert body["overall"]["prior"] == 0.3
    assert body["overall"]["verdict"] in {"likely_synthetic", "inconclusive", "likely_real"}
    assert body["segments"] and body["limitations"]


def test_bad_extension():
    r = client.post("/analyze", files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 400 and r.json()["error"] == "decode_failed"


def test_bad_prior():
    r = client.post("/analyze", files=FILE, data={"prior": "2"})
    assert r.status_code == 400


def test_auth(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_KEY", "secret")
    assert client.post("/analyze", files=FILE).status_code == 401
    ok = client.post("/analyze", files=FILE, headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200
    assert client.get("/health").status_code == 200  # health stays public


def test_health_reports_mock_without_weights(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MODEL_DIR", raising=False)
    body = client.get("/health").json()
    assert body["mock"] is True and body["model"] == "mock"


def test_empty_volume_is_not_weights(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    (tmp_path / "lost+found").mkdir()
    assert client.get("/health").json()["weights_found"] is False
    (tmp_path / "v3p").mkdir()
    assert client.get("/health").json()["weights_found"] is True
