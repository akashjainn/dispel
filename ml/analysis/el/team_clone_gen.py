"""ElevenLabs clones of the 10 consenting teammates (all agreed to voice cloning for this project): one Instant Voice
Clone per person from their 10 real clips (data/consent/team/real/<spk>_NN.wav), then N new lines per voice spread
over eleven_v3 / eleven_multilingual_v2 / eleven_flash_v2_5. Texts: LJ Speech sentences (80-170 chars) excluding NSA's
LJRealResampled clips, our validation LJ clips, and texts already used by el_stock / el_frontier.
Credits tracked locally (key lacks user_read) in data/consent/credits.csv; hard cap EL_BUDGET over that whole ledger.
Out: data/consent/team_gen/<spk>/<model>__<text_id>.mp3, data/consent/team_gen/meta.csv, data/consent/team/voices.json"""
import csv, json, os, random, sys, time
from pathlib import Path
import requests
R = Path.home() / "hackgt"; C = R / "data/consent"; OUT = C / "team_gen"; OUT.mkdir(parents=True, exist_ok=True)
KEY = (Path.home() / ".config/hackgt" / os.getenv("EL_KEY_FILE", "elevenlabs_key3")).read_text().strip()
API = "https://api.elevenlabs.io/v1"; H = {"xi-api-key": KEY}
N = int(os.getenv("N_PER_VOICE", "30")); BUDGET = float(os.getenv("EL_BUDGET", "40000"))
MODELS = ["eleven_v3", "eleven_multilingual_v2", "eleven_flash_v2_5"]
RATE = {"eleven_flash_v2_5": 0.5}
LEDGER = C / "credits.csv"
def spent():
    return sum(float(r["credits"]) for r in csv.DictReader(open(LEDGER))) if LEDGER.exists() else 0.0
def log(kind, n):
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        w = csv.writer(f); new and w.writerow(["time", "person", "kind", "credits"]); w.writerow([time.strftime("%F %T"), "team", kind, n])
spks = sorted({p.name.rsplit("_", 1)[0] for p in (C / "team/real").glob("*.wav")})
vf = C / "team/voices.json"; voices = json.loads(vf.read_text()) if vf.exists() else {}
for s in spks:
    if s in voices: continue
    fs = sorted((C / "team/real").glob(f"{s}_*.wav"))
    r = requests.post(API + "/voices/add", headers=H, data={"name": f"hackgt-{s}-consented", "remove_background_noise": "false"},
                      files=[("files", (f.name, open(f, "rb"), "audio/wav")) for f in fs], timeout=180)
    if r.status_code != 200: sys.exit(f"voice add failed for {s}: {r.status_code} {r.text[:300]}")
    voices[s] = r.json()["voice_id"]; vf.write_text(json.dumps(voices, indent=1)); print("voice", s, flush=True)
excl = {Path(p).stem for p in (R / "data/nsa/LJRealResampled/resampled").glob("*.wav")}
excl |= {Path(r["path"]).stem for r in csv.DictReader(open(R / "data/splits/v3_val.csv")) if r["group"] == "ljspeech"}
for m in ("data/el_stock/meta.csv", "data/el_frontier/meta.csv"):
    if (R / m).exists(): excl |= {r["text_id"] for r in csv.DictReader(open(R / m))}
texts = [(row[0], row[-1].strip()) for row in csv.reader(open(R / "data/diffssd/real_speech/ljspeech/metadata.csv"), delimiter="|", quoting=csv.QUOTE_NONE)
         if row[0] not in excl and 80 <= len(row[-1].strip()) <= 170]
random.Random(27).shuffle(texts)
meta = OUT / "meta.csv"; done = {(r["spk"], r["text_id"]) for r in csv.DictReader(open(meta))} if meta.exists() else set()
mf = open(meta, "a", newline=""); w = csv.DictWriter(mf, fieldnames=["file", "spk", "voice_id", "model", "text_id", "chars", "text"])
if not done: w.writeheader()
print(f"{len(spks)} voices, {len(texts)} texts, ledger {spent():.0f} of budget {BUDGET:.0f}", flush=True)
made = 0
for j in range(N):
    for i, s in enumerate(spks):
        tid, t = texts[j * len(spks) + i]; m = MODELS[(j + i) % 3]
        if (s, tid) in done: continue
        cost = len(t) * RATE.get(m, 1.0)
        if spent() + cost > BUDGET: sys.exit(f"budget reached: {spent():.0f}")
        for attempt in range(3):
            q = requests.post(f"{API}/text-to-speech/{voices[s]}?output_format=mp3_44100_128", headers={**H, "Accept": "audio/mpeg"},
                              json={"text": t, "model_id": m}, timeout=180)
            if q.status_code == 429: time.sleep(10); continue
            break
        if q.status_code != 200: print("ERR", s, m, q.status_code, q.text[:200], flush=True); continue
        d = OUT / s; d.mkdir(exist_ok=True); f = d / f"{m}__{tid}.mp3"; f.write_bytes(q.content); log(m, cost)
        w.writerow({"file": str(f.relative_to(R)), "spk": s, "voice_id": voices[s], "model": m, "text_id": tid, "chars": len(t), "text": t}); mf.flush()
        made += 1
    print(f"round {j + 1}/{N}: made {made}, ledger {spent():.0f}", flush=True)
print("DONE", made, spent())
