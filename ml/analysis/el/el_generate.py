"""Generate ElevenLabs training clips with premade (stock) voices via the API. Never clones anyone.
Key: ~/.config/hackgt/elevenlabs_key (chmod 600; never printed). Texts: LJ Speech sentences (80-170 chars),
excluding NSA's 242 LJRealResampled clips and every LJ clip in our validation split, so no validation text leaks.
Models alternate over the cheaper flash/turbo models (0.5 credit/char) plus some multilingual_v2 for variety.
Voices are split by voice: ~20% held out for validation (never trained on). Stops before the credit floor.
Out: data/el_stock/<voice_id>/<n>.mp3 and data/el_stock/meta.csv"""
import csv, json, os, random, sys, time, urllib.request, urllib.error
from pathlib import Path
ROOT = Path.home() / "hackgt"
KEY = (Path.home() / ".config/hackgt" / os.getenv("EL_KEY_FILE", "elevenlabs_key")).read_text().strip()
OUT = ROOT / os.getenv("EL_OUT", "data/el_stock"); OUT.mkdir(parents=True, exist_ok=True)
SPLIT_ALL = os.getenv("EL_SPLIT_ALL")  # e.g. "test": every clip is evaluation-only
EXCL_META = os.getenv("EL_EXCLUDE_META")  # meta.csv of an earlier run whose texts must not be reused
API = "https://api.elevenlabs.io/v1"
FLOOR = int(sys.argv[1]) if len(sys.argv) > 1 else 300  # stop when fewer credits than this remain
MODELS = os.getenv("EL_MODELS", "eleven_flash_v2_5,eleven_turbo_v2_5,eleven_flash_v2_5,eleven_turbo_v2_5,eleven_multilingual_v2").split(",")
HALF = {"eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_flash_v2", "eleven_turbo_v2"}  # 0.5 credit/char

def req(path, data=None, accept="application/json"):
    r = urllib.request.Request(API + path, data=None if data is None else json.dumps(data).encode(),
                               headers={"xi-api-key": KEY, "Content-Type": "application/json", "Accept": accept})
    with urllib.request.urlopen(r, timeout=60) as f:
        return f.read()

START = int(os.getenv("EL_CREDITS", "10000"))  # used when the key lacks user_read (tracked locally instead)


def credits_left(spent=0.0):
    try:
        s = json.loads(req("/user/subscription"))
        return s["character_limit"] - s["character_count"], s.get("tier")
    except urllib.error.HTTPError:
        return START - spent, "unknown (key has no user_read; tracking locally)"

voices = [v for v in json.loads(req("/voices"))["voices"] if v.get("category") == "premade"]
rng = random.Random(13)
rng.shuffle(voices)
n_val = max(2, len(voices) // 5)
split = {v["voice_id"]: ("val" if i < n_val else "train") for i, v in enumerate(voices)}
excl = {Path(p).stem for p in (ROOT / "data/nsa/LJRealResampled/resampled").glob("*.wav")}
excl |= {Path(r["path"]).stem for r in csv.DictReader(open(ROOT / "data/splits/v3_val.csv")) if r["group"] == "ljspeech"}
texts = []
for row in csv.reader(open(ROOT / "data/diffssd/real_speech/ljspeech/metadata.csv"), delimiter="|", quoting=csv.QUOTE_NONE):
    t = row[-1].strip()
    if row[0] not in excl and 80 <= len(t) <= 170:
        texts.append((row[0], t))
if EXCL_META:
    used = {r["text_id"] for r in csv.DictReader(open(ROOT / EXCL_META))}
    texts = [t for t in texts if t[0] not in used]
rng.shuffle(texts)
left, tier = credits_left()
print(f"tier {tier}, credits left {left}, premade voices {len(voices)} (val {n_val}), candidate texts {len(texts)}", flush=True)
meta_path = OUT / "meta.csv"
spent = 0.0
if meta_path.exists():  # credits already spent by earlier runs of this script
    for r in csv.DictReader(open(meta_path)):
        spent += int(r["chars"]) * (0.5 if r["model"] in HALF else 1.0)
left, tier = credits_left(spent)
done = {(r["voice_id"], r["text_id"]) for r in csv.DictReader(open(meta_path))} if meta_path.exists() else set()
mf = open(meta_path, "a", newline="")
w = csv.DictWriter(mf, fieldnames=["file", "voice_id", "voice_name", "gender", "accent", "age", "model", "text_id",
                                   "chars", "split"])
if not done:
    w.writeheader()
k, made = 0, 0
while True:
    if k >= len(texts):
        break  # texts exhausted before the credit floor
    v = voices[k % len(voices)]; tid, t = texts[k]; model = MODELS[k % len(MODELS)]; k += 1
    if (v["voice_id"], tid) in done:
        continue
    cost = len(t) * (0.5 if model in HALF else 1.0)
    if left - cost < FLOOR:
        break
    try:
        audio = req(f"/text-to-speech/{v['voice_id']}?output_format=mp3_44100_128",
                    {"text": t, "model_id": model}, accept="audio/mpeg")
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read()[:200], flush=True)
        if e.code in (401, 402, 429):
            time.sleep(5)
            if e.code != 429:
                break
        continue
    d = OUT / v["voice_id"]; d.mkdir(exist_ok=True)
    f = d / f"{tid}_{model}.mp3"; f.write_bytes(audio)
    lab = v.get("labels") or {}
    w.writerow({"file": str(f.relative_to(ROOT)), "voice_id": v["voice_id"], "voice_name": v.get("name"),
                "gender": lab.get("gender"), "accent": lab.get("accent"), "age": lab.get("age"), "model": model,
                "text_id": tid, "chars": len(t), "split": SPLIT_ALL or split[v["voice_id"]]}); mf.flush()
    left -= cost; spent += cost; made += 1
    if made % 20 == 0:
        left, _ = credits_left(spent)
        print(f"{made} clips, credits left {left}", flush=True)
print(f"DONE {made} clips; credits left ~{int(left)}", flush=True)
