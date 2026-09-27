"""v5c data via ElevenLabs (team decision 2026-09-26: isolator-cleaned real speech counts as REAL).
  isolator_real : ElevenLabs Voice Isolator on real speech (label 0). Sources: LibriSpeech reals from DiffSSD's TRAIN
                  split (>= 5 s) + consenting teammates' reals (>= 4.8 s). split = eval for held-out teammates
                  (v5_team eval speakers) and for a fixed 15-clip LibriSpeech slice; train otherwise.
  sts_libri     : speech-to-speech of LibriSpeech TRAIN reals into premade voices (label 1, train)
  voice_design  : more text-to-voice design previews (label 1, train)
Out: data/el_extra/<kind>/..., data/el_extra/meta.csv (file,kind,label,split,src,spk). Credit cap EL_BUDGET on the ledger."""
import base64, csv, glob, os, random, sys, time
from pathlib import Path
import requests, soundfile as sf
R = Path.home() / "hackgt"; O = R / "data/el_extra"; O.mkdir(parents=True, exist_ok=True); LEDGER = R / "data/consent/credits.csv"
KEY = (Path.home() / ".config/hackgt/elevenlabs_key3").read_text().strip(); API = "https://api.elevenlabs.io/v1"; H = {"xi-api-key": KEY}
BUDGET = float(os.getenv("EL_BUDGET", "89000"))
spent = lambda: sum(float(r["credits"]) for r in csv.DictReader(open(LEDGER)))
def log(kind, c):
    with open(LEDGER, "a", newline="") as f: csv.writer(f).writerow([time.strftime("%F %T"), "el_extra", kind, round(c, 1)])
meta = O / "meta.csv"; new = not meta.exists(); mf = open(meta, "a", newline="")
w = csv.DictWriter(mf, fieldnames=["file", "kind", "label", "split", "src", "spk"]); new and w.writeheader()
done = {r["file"] for r in csv.DictReader(open(meta))} if not new else set()
dur = {r["filename"]: float(r["dur"]) for r in csv.DictReader(open(R / "results/scores/diffssd_profile_headers.csv"))}
libri = [r["filename"] for r in csv.DictReader(open(R / "data/diffssd_hf/train_val_test_splits.csv"))
         if r["set"] == "train" and r["method_name"] == "librispeech" and dur.get(r["filename"], 0) >= 5.0]
random.Random(9).shuffle(libri)
team_eval = {r["spk"] for r in csv.DictReader(open(R / "data/splits/v5_team.csv")) if r["split"] == "eval"}
team = [p for p in sorted(glob.glob(str(R / "data/consent/team/real/*.wav"))) if sf.info(p).duration >= 4.8]
random.Random(10).shuffle(team)
def post_file(url, src, data=None):
    with open(src, "rb") as fh:
        return requests.post(url, headers=H, data=data or {}, files={"audio": (Path(src).name, fh)}, timeout=240)
# isolator: 45 teammate + 110 libri (first 15 libri -> eval)
iso = [(p, Path(p).stem.rsplit("_", 1)[0]) for p in team[:45]] + [(str(R / "data/diffssd" / f), "libri") for f in libri[:110]]
d = O / "isolator_real"; d.mkdir(exist_ok=True)
for k, (src, spk) in enumerate(iso):
    f = d / f"{k:03d}.mp3"; rel = str(f.relative_to(R))
    if rel in done: continue
    cost = sf.info(src).duration / 60 * 1000
    if spent() + cost > BUDGET: sys.exit(f"budget at isolator {k}")
    q = post_file(API + "/audio-isolation", src)
    if q.status_code != 200: print("ERR iso", q.status_code, q.text[:160], flush=True); continue
    f.write_bytes(q.content); log("isolator", cost)
    split = "eval" if (spk in team_eval or spk == "akash" or (spk == "libri" and k - 45 < 15)) else "train"
    w.writerow({"file": rel, "kind": "isolator_real", "label": 0, "split": split, "src": str(Path(src).relative_to(R)), "spk": spk}); mf.flush()
print("isolator done, ledger", round(spent()), flush=True)
voices = [v for v in requests.get(API + "/voices", headers=H, timeout=60).json()["voices"] if v.get("category") == "premade"]
d = O / "sts_libri"; d.mkdir(exist_ok=True)
for k, fn in enumerate(libri[110:170]):
    f = d / f"{k:03d}.mp3"; rel = str(f.relative_to(R))
    if rel in done: continue
    src = R / "data/diffssd" / fn; cost = sf.info(src).duration / 60 * 1000
    if spent() + cost > BUDGET: sys.exit(f"budget at sts {k}")
    v = voices[(k * 5) % len(voices)]; m = ["eleven_multilingual_sts_v2", "eleven_english_sts_v2"][k % 2]
    q = post_file(f"{API}/speech-to-speech/{v['voice_id']}?output_format=mp3_44100_128", src, {"model_id": m})
    if q.status_code != 200: print("ERR sts", q.status_code, q.text[:160], flush=True); continue
    f.write_bytes(q.content); log("sts", cost)
    w.writerow({"file": rel, "kind": "sts_libri", "label": 1, "split": "train", "src": str(src.relative_to(R)), "spk": v["name"]}); mf.flush()
print("sts done, ledger", round(spent()), flush=True)
d = O / "voice_design"; d.mkdir(exist_ok=True)
descs = ["A man in his 50s with a warm Midwestern accent, relaxed storyteller", "A young woman with a light Spanish accent speaking English, upbeat",
         "A deep-voiced older British man, formal lecture style", "A nervous young man, fast and slightly stuttering delivery",
         "A calm female meditation guide, soft and slow", "A middle-aged Nigerian English speaker, confident and clear",
         "A gruff construction foreman, loud and direct", "A teenage boy, bored and mumbling"]
lj = [r[-1].strip() for r in csv.reader(open(R / "data/diffssd/real_speech/ljspeech/metadata.csv"), delimiter="|", quoting=csv.QUOTE_NONE) if 100 <= len(r[-1].strip()) <= 180]
random.Random(12).shuffle(lj); k = len(list(d.glob("*.mp3")))
for i, desc in enumerate(descs):
    t = lj[i]
    if spent() + len(t) * 3 > BUDGET: sys.exit("budget at design")
    q = requests.post(API + "/text-to-voice/design", headers=H, json={"voice_description": desc, "text": t, "model_id": "eleven_multilingual_ttv_v2"}, timeout=180)
    if q.status_code != 200: print("ERR design", q.status_code, q.text[:160], flush=True); continue
    for p in q.json().get("previews", []):
        f = d / f"{k:03d}.mp3"; f.write_bytes(base64.b64decode(p["audio_base_64"]))
        w.writerow({"file": str(f.relative_to(R)), "kind": "voice_design", "label": 1, "split": "train", "src": "", "spk": desc[:30]}); mf.flush(); k += 1
    log("voice_design", len(t) * 3)
print("ALLDONE ledger", round(spent()), flush=True)
