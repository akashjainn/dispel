"""ElevenLabs avenue matrix (eval-only): how does the detector fare on each kind of ElevenLabs audio?
Avenues (N clips each, premade stock voices only - no cloning of anyone new):
  tts_v3, tts_multilingual_v2, tts_flash_v2_5, tts_turbo_v2_5      plain TTS per model
  v3_tags            eleven_v3 with expressive audio tags ([whispers], [laughs], [sighs], [excited], ...)
  speed_slow/fast    multilingual_v2 with voice_settings.speed 0.75 / 1.15 (EL's own time-scaling)
  unstable_style     multilingual_v2, stability 0.0, similarity 0.3, style 1.0 (most expressive/least stable)
  pcm16k             multilingual_v2 delivered as raw pcm_16000 (no mp3 codec at all)
  ulaw8k             multilingual_v2 delivered as ulaw_8000 (telephony)
  mp3_lowbit         multilingual_v2 as mp3_22050_32
  voice_design       text-to-voice design previews (brand-new synthetic voices from a description)
  isolator_real      REAL teammate clips run through ElevenLabs voice isolator (label real: false-alarm check)
(speech-to-speech is scripts/el/sts_gen.py). Credits: TTS logged at 1/char (0.5 flash/turbo), isolator 1000/min,
design logged at 1/char of preview text; ledger data/consent/credits.csv, hard cap EL_BUDGET.
Out: data/el_matrix/<avenue>/<k>.<ext>, data/el_matrix/meta.csv"""
import base64, csv, glob, json, os, random, sys, time
from pathlib import Path
import requests, soundfile as sf
R = Path.home() / "hackgt"; O = R / "data/el_matrix"; O.mkdir(parents=True, exist_ok=True); LEDGER = R / "data/consent/credits.csv"
KEY = (Path.home() / ".config/hackgt/elevenlabs_key3").read_text().strip(); API = "https://api.elevenlabs.io/v1"; H = {"xi-api-key": KEY}
N = int(os.getenv("N", "30")); BUDGET = float(os.getenv("EL_BUDGET", "80000")); ONLY = os.getenv("ONLY")
spent = lambda: sum(float(r["credits"]) for r in csv.DictReader(open(LEDGER)))
def log(kind, c):
    with open(LEDGER, "a", newline="") as f: csv.writer(f).writerow([time.strftime("%F %T"), "el_matrix", kind, round(c, 1)])
voices = [v for v in requests.get(API + "/voices", headers=H, timeout=60).json()["voices"] if v.get("category") == "premade"]
excl = {Path(p).stem for p in (R / "data/nsa/LJRealResampled/resampled").glob("*.wav")}
excl |= {Path(r["path"]).stem for r in csv.DictReader(open(R / "data/splits/v3_val.csv")) if r["group"] == "ljspeech"}
for m in ("data/el_stock/meta.csv", "data/el_frontier/meta.csv", "data/consent/team_gen/meta.csv"):
    if (R / m).exists(): excl |= {r["text_id"] for r in csv.DictReader(open(R / m))}
texts = [(r[0], r[-1].strip()) for r in csv.reader(open(R / "data/diffssd/real_speech/ljspeech/metadata.csv"), delimiter="|", quoting=csv.QUOTE_NONE)
         if r[0] not in excl and 60 <= len(r[-1].strip()) <= 150]
random.Random(77).shuffle(texts)
TAGS = ["[whispers]", "[laughs]", "[sighs]", "[excited]", "[sarcastic]", "[curious]", "[crying]", "[shouts]"]
MV2 = "eleven_multilingual_v2"
AV = {  # name: (model, output_format, extra json, ext, rate)
    "tts_v3": ("eleven_v3", "mp3_44100_128", {}, "mp3", 1.0),
    "tts_multilingual_v2": (MV2, "mp3_44100_128", {}, "mp3", 1.0),
    "tts_flash_v2_5": ("eleven_flash_v2_5", "mp3_44100_128", {}, "mp3", 0.5),
    "tts_turbo_v2_5": ("eleven_turbo_v2_5", "mp3_44100_128", {}, "mp3", 0.5),
    "v3_tags": ("eleven_v3", "mp3_44100_128", {"_tags": True}, "mp3", 1.0),
    "speed_slow": (MV2, "mp3_44100_128", {"voice_settings": {"speed": 0.75, "stability": 0.5, "similarity_boost": 0.75}}, "mp3", 1.0),
    "speed_fast": (MV2, "mp3_44100_128", {"voice_settings": {"speed": 1.15, "stability": 0.5, "similarity_boost": 0.75}}, "mp3", 1.0),
    "unstable_style": (MV2, "mp3_44100_128", {"voice_settings": {"stability": 0.0, "similarity_boost": 0.3, "style": 1.0}}, "mp3", 1.0),
    "pcm16k": (MV2, "pcm_16000", {}, "pcm", 1.0),
    "ulaw8k": (MV2, "ulaw_8000", {}, "ulaw", 1.0),
    "mp3_lowbit": (MV2, "mp3_22050_32", {}, "mp3", 1.0),
}
meta = O / "meta.csv"; new = not meta.exists(); mf = open(meta, "a", newline="")
w = csv.DictWriter(mf, fieldnames=["file", "avenue", "label", "voice", "model", "text_id", "text"]); new and w.writeheader()
def row(f, av, lab, voice, model, tid, text):
    w.writerow({"file": str(f.relative_to(R)), "avenue": av, "label": lab, "voice": voice, "model": model, "text_id": tid, "text": text}); mf.flush()
ti = 0
for av, (model, fmt, extra, ext, rate) in AV.items():
    if ONLY and av not in ONLY.split(","): ti += N; continue
    d = O / av; d.mkdir(exist_ok=True)
    for k in range(N):
        tid, t = texts[ti]; ti += 1; v = voices[(k * 7 + len(av)) % len(voices)]
        f = d / f"{k:03d}.{ext}"
        if f.exists(): continue
        if extra.get("_tags"):
            t = f"{TAGS[k % len(TAGS)]} {t}"
        cost = len(t) * rate
        if spent() + cost > BUDGET: sys.exit("budget")
        body = {"text": t, "model_id": model, **{a: b for a, b in extra.items() if not a.startswith("_")}}
        q = requests.post(f"{API}/text-to-speech/{v['voice_id']}?output_format={fmt}", headers=H, json=body, timeout=180)
        if q.status_code != 200: print("ERR", av, q.status_code, q.text[:200], flush=True); continue
        f.write_bytes(q.content); log(av, cost); row(f, av, 1, v["name"], model, tid, t)
    print(av, "done, ledger", round(spent()), flush=True)
# voice design previews
if not ONLY or "voice_design" in ONLY:
    d = O / "voice_design"; d.mkdir(exist_ok=True)
    descs = ["A middle-aged American man with a deep, slightly gravelly voice, calm news-anchor delivery",
             "A young British woman, bright and fast-paced, podcast host", "An elderly man with a soft Southern US accent, slow and warm",
             "A teenage girl, energetic, casual American English", "A woman in her 40s with an Indian English accent, clear and professional",
             "A tired male call-center agent, flat monotone, slightly muffled phone quality", "A cheerful Australian man in his 30s",
             "A raspy older woman, smoker's voice, New York accent", "A soft-spoken young man, gentle, slightly breathy", "A confident female lawyer, crisp articulation"]
    k = len(list(d.glob("*.mp3")))
    for i, desc in enumerate(descs):
        if k >= N: break
        tid, t = texts[ti + i]; t = (t + " " + texts[ti + i + 50][1])[:180]
        if len(t) < 100: t = (t + " " + texts[ti + i + 99][1])[:180]
        q = requests.post(API + "/text-to-voice/design", headers=H, json={"voice_description": desc, "text": t, "model_id": "eleven_multilingual_ttv_v2"}, timeout=180)
        if q.status_code != 200: print("ERR design", q.status_code, q.text[:300], flush=True); continue
        for p in q.json().get("previews", []):
            f = d / f"{k:03d}.mp3"; f.write_bytes(base64.b64decode(p["audio_base_64"])); row(f, "voice_design", 1, desc[:40], "ttv_v2", tid, t); k += 1
        log("voice_design", len(t) * 3)
    print("voice_design done", k, "ledger", round(spent()), flush=True)
# voice isolator on REAL speech (label 0)
if not ONLY or "isolator_real" in ONLY:
    d = O / "isolator_real"; d.mkdir(exist_ok=True)
    srcs = [x for x in sorted(glob.glob(str(R / "data/consent/team/real/*.wav"))) if sf.info(x).duration >= 4.8]; random.Random(5).shuffle(srcs)  # isolator minimum 4.6 s
    for k, s in enumerate(srcs[:N]):
        f = d / f"{k:03d}.mp3"
        if f.exists(): continue
        cost = sf.info(s).duration / 60 * 1000
        if spent() + cost > BUDGET: sys.exit("budget")
        with open(s, "rb") as fh:
            q = requests.post(API + "/audio-isolation", headers=H, files={"audio": (Path(s).name, fh, "audio/wav")}, timeout=180)
        if q.status_code != 200: print("ERR iso", q.status_code, q.text[:200], flush=True); continue
        f.write_bytes(q.content); log("isolator", cost); row(f, "isolator_real", 0, "", "audio-isolation", Path(s).stem, "")
    print("isolator done, ledger", round(spent()), flush=True)
print("ALLDONE", round(spent()))
