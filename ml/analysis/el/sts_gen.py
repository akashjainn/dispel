"""ElevenLabs speech-to-speech ("voice changer") test set: consenting teammates' and Akash's REAL recordings converted into
ElevenLabs premade voices. The result keeps the human's timing, pauses and breaths but the voice is synthetic - the
kind of "altered audio" our prosody/rhythm features could mistake for real. Eval only.
Out: data/consent/sts/<model>/<src>__<voice>.mp3 + meta.csv. Credits logged to data/consent/credits.csv (est. 1000/min)."""
import csv, json, os, random, sys, time, glob
from pathlib import Path
import requests, soundfile as sf
R = Path.home() / "hackgt"; C = R / "data/consent"; OUT = C / "sts"; OUT.mkdir(parents=True, exist_ok=True)
KEY = (Path.home() / ".config/hackgt/elevenlabs_key3").read_text().strip(); API = "https://api.elevenlabs.io/v1"; H = {"xi-api-key": KEY}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60; BUDGET = float(os.getenv("EL_BUDGET", "50000"))
LEDGER = C / "credits.csv"
spent = lambda: sum(float(r["credits"]) for r in csv.DictReader(open(LEDGER))) if LEDGER.exists() else 0.0  # header: time,person,kind,credits
voices = [v for v in requests.get(API + "/voices", headers=H, timeout=60).json()["voices"] if v.get("category") == "premade"]
srcs = sorted(glob.glob(str(C / "team/real/*.wav"))) + sorted(glob.glob(str(C / "akash/real/*.wav")))
rng = random.Random(41); rng.shuffle(srcs)
models = ["eleven_multilingual_sts_v2", "eleven_english_sts_v2"]
meta = OUT / "meta.csv"; new = not meta.exists(); mf = open(meta, "a", newline="")
w = csv.DictWriter(mf, fieldnames=["file", "src", "voice", "model", "dur"]); new and w.writeheader()
made = 0
for i, s in enumerate(srcs[:N]):
    v = voices[i % len(voices)]; m = models[i % 2]; dur = sf.info(s).duration; cost = dur / 60 * 1000
    if spent() + cost > BUDGET: sys.exit("budget")
    if (OUT / m / f"{Path(s).stem}__{v['name'].split()[0]}.mp3").exists(): continue
    with open(s, "rb") as fh:
        q = requests.post(f"{API}/speech-to-speech/{v['voice_id']}?output_format=mp3_44100_128", headers=H,
                          data={"model_id": m}, files={"audio": (Path(s).name, fh, "audio/wav")}, timeout=180)
    if q.status_code != 200: print("ERR", q.status_code, q.text[:200], flush=True); continue
    d = OUT / m; d.mkdir(exist_ok=True); f = d / f"{Path(s).stem}__{v['name'].split()[0]}.mp3"; f.write_bytes(q.content)
    new_ledger = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as lf:
        lw = csv.writer(lf); new_ledger and lw.writerow(["time", "person", "kind", "credits"]); lw.writerow([time.strftime("%F %T"), "sts", m, round(cost, 1)])
    w.writerow({"file": str(f.relative_to(R)), "src": str(Path(s).relative_to(R)), "voice": v["name"], "model": m, "dur": round(dur, 2)}); mf.flush(); made += 1
print("DONE", made, "ledger", round(spent()))
