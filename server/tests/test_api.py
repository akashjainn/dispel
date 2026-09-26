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


CLIENT = "3f2b8c1e-9a4d-4e6f-8b7a-1c2d3e4f5a6b"


@pytest.fixture
def data_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_mock_response_is_flagged():
    assert client.post("/analyze", files=FILE).json()["mock"] is True


def test_history_is_per_client(data_dir):
    h = {"X-Dispel-Client": CLIENT}
    clip = client.post("/analyze", files=FILE, data={"source": "call"}, headers=h).json()["clip_id"]
    items = client.get("/history", headers=h).json()["items"]
    assert [(i["clip_id"], i["source"], i["mock"]) for i in items] == [(clip, "call", True)]
    other = {"X-Dispel-Client": "00000000-0000-4000-8000-000000000000"}
    assert client.get("/history", headers=other).json()["items"] == []


def test_analyze_without_client_is_not_recorded(data_dir):
    assert client.post("/analyze", files=FILE).status_code == 200
    assert client.get("/history", headers={"X-Dispel-Client": CLIENT}).json()["items"] == []


def test_bad_client_id_and_source(data_dir):
    bad = {"X-Dispel-Client": "not-a-uuid"}
    assert client.post("/analyze", files=FILE, headers=bad).json()["error"] == "bad_request"
    assert client.post("/analyze", files=FILE, data={"source": "mic"}).status_code == 400
    assert client.get("/history").status_code == 400


def test_video_container_accepted():
    assert client.post("/analyze", files={"file": ("call.mp4", b"xxxx", "video/mp4")}).status_code == 200


@pytest.mark.parametrize("roll,verdict", [(0.1, "likely_synthetic"), (0.9, "likely_real")])
def test_mock_verdict_mix(monkeypatch: pytest.MonkeyPatch, roll, verdict):
    import app.main as m
    monkeypatch.setattr(m.random, "random", lambda: roll)
    body = client.post("/analyze", files=FILE).json()
    assert body["mock"] is True and body["overall"]["verdict"] == verdict
    total = sum(a["llr_contribution"] for a in body["analyzers"])
    assert abs(total - body["overall"]["llr"]) < 0.02


def test_mock_is_mostly_synthetic():
    import app.main as m
    m.random.seed(0)
    verdicts = [client.post("/analyze", files=FILE).json()["overall"]["verdict"] for _ in range(300)]
    assert 0.6 < verdicts.count("likely_synthetic") / len(verdicts) < 0.8
    assert set(verdicts) == {"likely_synthetic", "likely_real"}


def test_call_without_audio_gets_mock():
    r = client.post("/analyze", data={"source": "call"})
    assert r.status_code == 200 and r.json()["mock"] is True
    assert client.post("/analyze", data={"source": "file"}).json()["error"] == "bad_request"
