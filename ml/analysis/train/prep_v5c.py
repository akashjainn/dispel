"""v5c data prep (NSA tips: diversity of real speakers/conditions and of commercial TTS). Every source is converted to
16 kHz mono PCM wav under data/v5c/<source>/ and listed in data/splits/v5c_new.csv
(path,label,group,source,split,detail); split=train|eval, eval slices are held out by video / file / voice / model / speaker.
Run: python prep_v5c.py <step> [...]  steps: tf ups gary cmu mlaad el grok real"""
import csv, hashlib, io, json, subprocess, sys, tarfile, random, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np, soundfile as sf, librosa
R = Path.home() / "hackgt"; D = R / "data"; O = D / "v5c"; O.mkdir(parents=True, exist_ok=True)
SR = 16000
def h(s, mod=5): return int(hashlib.md5(s.encode()).hexdigest(), 16) % mod        # deterministic 1-in-mod holdout
def dec(src=None, data=None, maxs=None):
    a = ["ffmpeg", "-nostdin", "-v", "error"] + (["-t", str(maxs)] if maxs else []) + ["-i", "pipe:0" if data is not None else str(src), "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"]
    return np.frombuffer(subprocess.run(a, input=data, capture_output=True).stdout, "<f4").copy()
def save(x, rel):
    p = O / rel; p.parent.mkdir(parents=True, exist_ok=True); sf.write(p, x, SR, subtype="PCM_16"); return str(p.relative_to(D))
def out(step, rows):
    with open(O / f"rows_{step}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["path", "label", "group", "source", "split", "detail"]); w.writerows(rows)
    print(step, len(rows), "rows:", {(r[3], r[4], r[1]): 0 for r in rows}.__len__(), flush=True)
    import collections; print(collections.Counter((r[3], r[4], r[1]) for r in rows), flush=True)
def speech_windows(x, win_s=8.0, k=3):
    """up to k non-overlapping windows with the most voiced-energy (simple, fast)."""
    hop = 160; rms = librosa.feature.rms(y=x, frame_length=400, hop_length=hop)[0]; db = 20 * np.log10(rms + 1e-7)
    act = (db > np.percentile(db, 95) - 25).astype(float); W = int(win_s * 100)
    if len(act) < W: return [(0, len(x))] if len(x) >= 3 * SR else []
    c = np.convolve(act, np.ones(W), "valid"); out, used = [], np.zeros(len(c), bool)
    for i in np.argsort(-c):
        if c[i] < 0.6 * W or len(out) >= k: break
        if used[max(0, i - W):i + W].any(): continue
        used[i] = True; out.append((i * hop, i * hop + int(win_s * SR)))
    return out
step = sys.argv[1:]
if "tf" in step:
    import pyarrow as pa
    rows = []
    for f in sorted(glob.glob(str(D / "talkingface/*.arrow"))):
        with pa.memory_map(f) as src:
            t = pa.ipc.open_stream(src).read_all()
        for r in t.to_pylist():
            x = dec(data=r["audio"]["bytes"]); vid = r["id"].split("-scene")[0]; sp = "eval" if h(vid) == 0 else "train"
            for j, (a, b) in enumerate(speech_windows(x, 8.0, 2)):
                rows.append([save(x[a:b], f"talkingface/{r['id']}_{j}.wav"), 0, "tf_" + vid, "talkingface", sp, f"{r['gender']}|{r['age']}|{r['race']}"])
    out("tf", rows)
if "gary" in step:
    import pyarrow.parquet as pq
    rows = []
    for f in sorted(glob.glob(str(D / "hf_premade/gary_train*.parquet"))):
        for r in pq.read_table(f).to_pylist():
            name = Path(r["audio"]["path"]).stem; pre = name.split("_")[0]; x = dec(data=r["audio"]["bytes"])
            if r["label"] == 0:
                vid = "_".join(name.split("_")[:2]); sp = "eval" if h(vid, 4) == 0 else "train"
                rows.append([save(x, f"gary/real/{name}.wav"), 0, "gary_" + vid, "yt_real", sp, "youtube"])
            else:
                vend = {"el": "elevenlabs", "po": "polly", "hg": "kokoro", "hu": "hume", "lv": "luvvoice", "sp": "speechify"}.get(pre, pre)
                sp = "eval" if h(name) == 0 else "train"
                rows.append([save(x, f"gary/fake/{name}.wav"), 1, "gary_" + vend, "el" if vend == "elevenlabs" else "commercial", sp, vend])
    out("gary", rows)
if "cmu" in step:
    import pyarrow.parquet as pq
    rows = []
    for f in ("cmu_test", "cmu_val"):
        for r in pq.read_table(D / f"hf_premade/{f}.parquet").to_pylist():
            x = dec(data=r["audio"]["bytes"]); lab = 0 if r["label"] == "real" else 1; sp = "eval" if h(r["id"]) == 0 else "train"
            rows.append([save(x, f"cmu/{'real' if lab == 0 else 'fake'}/{r['id']}.wav"), lab, "dfadd" if lab else "dfadd_real", "dfadd" if lab else "vctk_real", sp, f])
    out("cmu", rows)
if "mlaad" in step:
    rows = []; HELD = {"Higgs-Audio-V3", "Index-TTS-2.0", "Step-Audio-EditX", "supertonic-3"}
    jobs = []
    for p in sorted(glob.glob(str(D / "mlaad_new/*/*"))):
        m = Path(p).parent.name; jobs.append((p, f"mlaad_new/{m}/{Path(p).stem}.wav", "mlaad_new/" + m, "mlaad_new", "eval" if m in HELD else "train", m))
    for p in sorted(glob.glob(str(D / "mlaad_commercial/*/*"))):
        m = Path(p).parent.name; jobs.append((p, f"mlaad_com/{m}/{Path(p).stem}.wav", "com/" + m, "el" if "ElevenLabs" in m else "commercial", "eval" if h(p) == 0 else "train", m))
    def cv(j):
        p, rel, g, s, sp, det = j; x = dec(p)
        return [save(x, rel), 1, g, s, sp, det] if len(x) > SR else None
    with ThreadPoolExecutor(8) as ex: rows = [r for r in ex.map(cv, jobs) if r]
    out("mlaad", rows)
if "grok" in step:
    rows = []
    for r in csv.DictReader(open(D / "grok_tts/meta.csv")):
        x = dec(R / r["file"]); rows.append([save(x, f"grok/{r['voice']}_{Path(r['file']).stem}.wav"), 1, "grok/" + r["voice"], "commercial", r["split"], "grok"])
    out("grok", rows)
if "el" in step:
    train_spk = {r["spk"] for r in csv.DictReader(open(D / "splits/v5_team.csv")) if r["split"] == "train"}
    spk = lambda stem: stem.rsplit("_", 1)[0]
    J = []
    for r in csv.DictReader(open(D / "el_matrix/meta.csv")):
        if r["avenue"] == "isolator_real":
            J.append((R / r["file"], 0, "isolator", "real_processed", "train" if spk(r["text_id"]) in train_spk else "eval", "isolator"))
        else: J.append((R / r["file"], 1, "el/" + r["avenue"], "el", "eval" if h(r["file"], 4) == 0 else "train", r["avenue"]))
    for r in csv.DictReader(open(D / "consent/sts/meta.csv")):
        J.append((R / r["file"], 1, "el/voice_changer", "el", "train" if spk(Path(r["src"]).stem) in train_spk else "eval", "sts"))
    seen = set()
    for r in csv.DictReader(open(D / "el_extra/meta.csv")):
        if r["file"] in seen: continue
        seen.add(r["file"])
        J.append((R / r["file"], int(r["label"]), "isolator" if r["kind"] == "isolator_real" else "el/" + r["kind"], "real_processed" if r["kind"] == "isolator_real" else "el", r["split"], r["kind"]))
    for r in csv.DictReader(open(D / "el_stock/meta.csv")): J.append((R / r["file"], 1, "el/stock", "el", "train" if r["split"] == "train" else "eval", r["model"]))
    for p in sorted((D / "el_frontier").rglob("*.mp3")): J.append((p, 1, "el/frontier", "el", "eval", "frontier"))
    for r in csv.DictReader(open(D / "splits/v5_team.csv")):
        J.append((D / r["path"], int(r["label"]), ("team_real/" if r["label"] == "0" else "el/clone_") + r["spk"], "team_real" if r["label"] == "0" else "el", r["split"], r["detail"]))
    for p in sorted(glob.glob(str(D / "consent/akash/real/*.wav"))): J.append((Path(p), 0, "team_real/akash", "team_real", "eval", "akash"))
    for p in sorted(glob.glob(str(D / "consent/akash/fake/*/*.mp3"))): J.append((Path(p), 1, "el/clone_akash", "el", "eval", "akash"))
    plan = {r["uid"]: r["split"] for r in csv.DictReader(open(D / "clonesrc/plan.csv"))}
    for p in sorted(glob.glob(str(D / "clonesrc/clones/f5/*.wav"))):
        s = plan.get(Path(p).stem, "eval"); J.append((Path(p), 1, "f5clone", "f5clone", "train" if s == "train" else "eval", "f5"))
    def cv(j):
        p, y, g, s, sp, det = j; x = dec(p)
        if len(x) < SR: return None
        rel = "el_all/" + hashlib.md5(str(p).encode()).hexdigest()[:16] + ".wav"
        return [save(x, rel), y, g, s, sp, det + "|" + str(Path(p).relative_to(D))]
    with ThreadPoolExecutor(8) as ex: rows = [r for r in ex.map(cv, J) if r]
    out("el", rows)
if "ups" in step:
    lang = {}
    for l in open(D / "ups/lang_id_results.jsonl"):
        try: j = json.loads(l)
        except Exception: continue
        if j.get("tar_number") != "000001": continue
        lang[j["filepath"].replace("/data/", "", 1)] = j.get("prediction")
    print("lang entries", len(lang), "example", list(lang.items())[:2], flush=True)
    tf = tarfile.open(D / "ups/000001.tar"); rows = []; files = 0
    from transformers import pipeline
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-small.en", device=0)
    for m in tf:
        if not m.name.endswith(".mp3") or m.size < 200_000: continue
        lg = lang.get(m.name) or lang.get(Path(m.name).name) or lang.get("audio/000001.tar/" + m.name)
        if lg != "en": continue   # Whisper-large-v3 language ID from the dataset (also drops "nospeech")
        data = tf.extractfile(m).read(); x = dec(data=data, maxs=600)
        if len(x) < 10 * SR: continue
        segs = speech_windows(x[30 * SR:] if len(x) > 90 * SR else x, 8.0, 3); off = 30 * SR if len(x) > 90 * SR else 0
        src = m.name.split("/")[0]; sp = "eval" if h(src) == 0 else "train"; kept = 0
        for j, (a, b) in enumerate(segs):
            seg = x[off + a:off + b]; txt = asr({"raw": seg, "sampling_rate": SR})["text"]
            if len(txt.split()) < 10: continue
            rows.append([save(seg, f"ups/{hashlib.md5(m.name.encode()).hexdigest()[:12]}_{j}.wav"), 0, "ups_" + src, "ups", sp, txt[:60].replace(",", " ")]); kept += 1
        files += 1
        if files % 50 == 0: print("ups files", files, "segments", len(rows), flush=True)
        if len(rows) >= 2000: break
    out("ups", rows)
