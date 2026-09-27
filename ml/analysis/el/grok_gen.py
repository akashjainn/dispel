"""Grok (xAI) TTS clips via https://api.x.ai/v1/tts (hackathon promo credits). Texts: LJ sentences not used anywhere else.
Voices split: last 6 of the list are held out (eval only). Key: ~/.config/hackgt/grok_key (never printed).
Out: data/grok_tts/<voice>/<k>.<ext>, data/grok_tts/meta.csv"""
import csv, os, random, sys, time
from pathlib import Path
import requests
R = Path.home() / "hackgt"; O = R / "data/grok_tts"; O.mkdir(parents=True, exist_ok=True)
KEY = (Path.home() / ".config/hackgt/grok_key").read_text().strip(); N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
VOICES = ["eve", "ara", "rex", "sal", "leo", "carina", "zagan", "helix", "orion", "luna", "iris", "altair", "zenith", "perseus", "helios", "lux",
          "kepler", "rigel", "cosmo", "celeste", "ursa", "sirius", "lumen", "castor", "naksh", "atlas", "aurora", "liora"]
HELD = set(VOICES[-6:])
excl = {Path(p).stem for p in (R / "data/nsa/LJRealResampled/resampled").glob("*.wav")}
excl |= {Path(r["path"]).stem for r in csv.DictReader(open(R / "data/splits/v3_val.csv")) if r["group"] == "ljspeech"}
for m in ("data/el_stock/meta.csv", "data/el_frontier/meta.csv", "data/consent/team_gen/meta.csv", "data/el_matrix/meta.csv"):
    if (R / m).exists(): excl |= {r["text_id"] for r in csv.DictReader(open(R / m))}
texts = [(r[0], r[-1].strip()) for r in csv.reader(open(R / "data/diffssd/real_speech/ljspeech/metadata.csv"), delimiter="|", quoting=csv.QUOTE_NONE)
         if r[0] not in excl and 60 <= len(r[-1].strip()) <= 170]
random.Random(99).shuffle(texts)
meta = O / "meta.csv"; new = not meta.exists(); mf = open(meta, "a", newline="")
w = csv.DictWriter(mf, fieldnames=["file", "voice", "split", "fmt", "speed", "text_id", "chars"]); new and w.writeheader()
FMTS = [({"codec": "mp3", "sample_rate": 24000, "bit_rate": 128000}, "mp3"), ({"codec": "wav", "sample_rate": 16000}, "wav"), ({"codec": "mp3", "sample_rate": 44100, "bit_rate": 64000}, "mp3")]
made, chars = 0, 0
for k in range(N):
    v = VOICES[k % len(VOICES)]; tid, t = texts[k]; fmt, ext = FMTS[k % 3]; sp = [1.0, 1.0, 0.9, 1.15][k % 4]
    f = O / v / f"{k:04d}.{ext}"
    if f.exists(): continue
    f.parent.mkdir(exist_ok=True)
    q = requests.post("https://api.x.ai/v1/tts", headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                      json={"text": t, "voice_id": v, "language": "en", "output_format": fmt, "speed": sp}, timeout=120)
    if q.status_code != 200: print("ERR", v, q.status_code, q.text[:200], flush=True); time.sleep(2); continue
    f.write_bytes(q.content); made += 1; chars += len(t)
    w.writerow({"file": str(f.relative_to(R)), "voice": v, "split": "eval" if v in HELD else "train", "fmt": ext, "speed": sp, "text_id": tid, "chars": len(t)}); mf.flush()
print("DONE made", made, "chars", chars, flush=True)
