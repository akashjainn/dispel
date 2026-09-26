"""Per-install check history in SQLite. Contract: docs/INTERFACES.md (X-Dispel-Client, GET /history).

Stores result metadata only: never audio, file names or transcripts. The database lives in DATA_DIR
(default server/data; /var/lib/dispel in production, bind-mounted from the host so it survives redeploys)."""
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY,
    client_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    clip_id TEXT NOT NULL,
    source TEXT NOT NULL,
    probability REAL,
    verdict TEXT,
    model TEXT,
    mock INTEGER NOT NULL,
    duration_s REAL
);
CREATE INDEX IF NOT EXISTS checks_client ON checks (client_id, id);"""
_LOCK = threading.Lock()


@contextmanager
def _db():
    d = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
    d.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        conn = sqlite3.connect(d / "dispel.db", timeout=5)
        try:
            conn.executescript(_SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()


def record(client_id: str, source: str, resp: dict) -> None:
    row = (client_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), resp["clip_id"], source,
           resp["overall"]["probability"], resp["overall"]["verdict"], resp["model"]["name"],
           int(bool(resp.get("mock"))), resp.get("duration_s"))
    with _db() as conn:
        conn.execute("INSERT INTO checks (client_id, ts, clip_id, source, probability, verdict, model, mock,"
                     " duration_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row)


def history(client_id: str, limit: int) -> list[dict]:
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT ts, clip_id, source, probability, verdict, model, mock, duration_s FROM checks"
                            " WHERE client_id = ? ORDER BY id DESC LIMIT ?", (client_id, limit)).fetchall()
    return [{**dict(r), "mock": bool(r["mock"])} for r in rows]
