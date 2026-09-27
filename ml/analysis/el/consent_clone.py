"""Consented voice clone test set (ElevenLabs Instant Voice Clone). ONLY for people who recorded themselves for this and
agreed (python consent_clone.py <person>): data/consent/<person>/raw16.wav -> utterance segments (real), whisper
transcripts, one IVC voice from the full recording, then the clone speaks each segment's transcript (paired, same text)
with the frontier models. Eval-only. Credits are tracked locally in data/consent/credits.csv (key lacks user_read).
Out: data/consent/<person>/real/<k>.wav, fake/<model>/<k>.mp3, segments.csv"""
import csv, json, os, sys, time
from pathlib import Path
import numpy as np, soundfile as sf, librosa, requests
R = Path.home() / "hackgt"; person = sys.argv[1]; D = R / "data/consent" / person
KEY = (Path.home() / ".config/hackgt" / os.getenv("EL_KEY_FILE", "elevenlabs_key3")).read_text().strip()
API = "https://api.elevenlabs.io/v1"; H = {"xi-api-key": KEY}
MODELS = os.getenv("EL_MODELS", "eleven_v3,eleven_multilingual_v2").split(",")
LEDGER = R / "data/consent/credits.csv"; BUDGET = int(os.getenv("EL_BUDGET", "5000"))

def spent():
    return sum(float(r["credits"]) for r in csv.DictReader(open(LEDGER))) if LEDGER.exists() else 0.0
def log(kind, n):
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        w = csv.writer(f); new and w.writerow(["time", "person", "kind", "credits"]); w.writerow([time.strftime("%F %T"), person, kind, n])

# 1. segments
seg_csv = D / "segments.csv"
if not seg_csv.exists():
    x, sr = sf.read(D / "raw16.wav", dtype="float32")
    iv = librosa.effects.split(x, top_db=35, frame_length=1024, hop_length=160)
    merged = []
    for s, e in iv:  # merge gaps < 0.5 s; cut into 2.5-8 s utterances
        if merged and s - merged[-1][1] < 0.5 * sr and e - merged[-1][0] < 8 * sr: merged[-1][1] = e
        else: merged.append([s, e])
    merged = [(max(0, s - 1600), min(len(x), e + 1600)) for s, e in merged if e - s >= 1.5 * sr]
    from transformers import pipeline
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-small.en", device=0)
    (D / "real").mkdir(exist_ok=True); rows = []
    for k, (s, e) in enumerate(merged):
        c = x[s:e]; sf.write(D / "real" / f"{k:02d}.wav", c, sr, subtype="PCM_16")
        t = asr({"raw": c, "sampling_rate": sr})["text"].strip()
        rows.append({"k": f"{k:02d}", "start": round(s / sr, 2), "dur": round((e - s) / sr, 2), "text": t})
    with open(seg_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
rows = list(csv.DictReader(open(seg_csv)))
print(len(rows), "segments"); [print(r["k"], r["dur"], r["text"]) for r in rows]
if os.getenv("DRY"): sys.exit()
# 2. voice
vf = D / "voice_id.txt"
if not vf.exists():
    src = D / "raw.m4a" if (D / "raw.m4a").exists() else D / "raw16.wav"  # original recording if kept, else the 16 kHz input
    with open(src, "rb") as fh:
        r = requests.post(API + "/voices/add", headers=H, data={"name": f"hackgt-{person}-consented", "remove_background_noise": "false"},
                          files=[("files", (src.name, fh, "audio/mp4" if src.suffix == ".m4a" else "audio/wav"))], timeout=120)
    r.raise_for_status(); vf.write_text(r.json()["voice_id"]); print("voice created")
vid = vf.read_text().strip()
# 3. paired generation
for m in MODELS:
    od = D / "fake" / m; od.mkdir(parents=True, exist_ok=True)
    for r in rows:
        f = od / f"{r['k']}.mp3"
        if f.exists(): continue
        n = len(r["text"])
        if spent() + n > BUDGET: sys.exit(f"budget {BUDGET} reached ({spent():.0f} spent)")
        q = requests.post(f"{API}/text-to-speech/{vid}?output_format=mp3_44100_128", headers={**H, "Accept": "audio/mpeg"},
                          json={"text": r["text"], "model_id": m}, timeout=120)
        if q.status_code != 200: print("ERR", m, r["k"], q.status_code, q.text[:200]); continue
        f.write_bytes(q.content); log(m, n)
print("done; credits spent (ledger total):", spent())
