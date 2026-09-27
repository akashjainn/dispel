"""Generate paired clones from data/clonesrc/plan.csv with one zero-shot cloner.
  python clone_gen.py f5 <root> [shard k/n]     (F5-TTS, laptop)
  python clone_gen.py chatterbox <root> [k/n]   (Chatterbox, PC)
<root> holds plan.csv and refs/<spk>.wav. Output: <root>/clones/<cloner>/<uid>.wav (native rate) + meta_<cloner>.csv.
The reference audio and its transcript come from one chapter; the target text is a different utterance of the same
speaker, whose real recording is the paired real clip."""
import csv, sys, time
from pathlib import Path
import numpy as np, soundfile as sf
cloner, root = sys.argv[1], Path(sys.argv[2])
k, n = (map(int, sys.argv[3].split("/")) if len(sys.argv) > 3 else (0, 1))
import os
rows = [r for i, r in enumerate(csv.DictReader(open(root / "plan.csv"))) if i % n == k and r["split"] in os.getenv("SPLITS", "train,val,eval").split(",")]
out = root / "clones" / cloner; out.mkdir(parents=True, exist_ok=True)
meta = open(root / f"meta_{cloner}_{k}.csv", "a", newline="")
w = csv.DictWriter(meta, fieldnames=["uid", "spk", "split", "cloner", "sr", "dur", "secs"])
if meta.tell() == 0:
    w.writeheader()
if cloner == "f5":
    import torch, torchaudio
    def _sf_load(path, *a, **k):  # torchaudio>=2.9 needs torchcodec + FFmpeg DLLs on Windows; read with soundfile
        x, sr = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(x.T.copy()), sr
    torchaudio.load = _sf_load
    from f5_tts.api import F5TTS
    m = F5TTS()
    def gen(r):
        wav, sr, _ = m.infer(ref_file=str(root / "refs" / Path(r["ref_wav"]).name), ref_text=r["ref_text"],
                             gen_text=r["text"], seed=int(r["uid"].split("-")[-1]) + 7, remove_silence=False)
        return np.asarray(wav, np.float32), sr
elif cloner == "chatterbox":
    import torch, perth
    # No watermark: Chatterbox normally embeds a Perth watermark, which a detector could learn as a shortcut, and a
    # real attacker would strip or skip it. (The implicit watermarker also fails to import here.)
    class _NoMark:
        def apply_watermark(self, wav, sample_rate=None, **k): return wav
    perth.PerthImplicitWatermarker = _NoMark
    from chatterbox.tts import ChatterboxTTS
    m = ChatterboxTTS.from_pretrained(device="cuda")
    def gen(r):
        torch.manual_seed(int(r["uid"].split("-")[-1]) + 7)
        x = m.generate(r["text"], audio_prompt_path=str(root / "refs" / Path(r["ref_wav"]).name))
        return x.squeeze().cpu().numpy().astype(np.float32), m.sr
t0 = time.time()
for i, r in enumerate(rows):
    f = out / f"{r['uid']}.wav"
    if f.exists():
        continue
    s = time.time()
    try:
        x, sr = gen(r)
    except Exception as e:
        print("ERR", r["uid"], e, flush=True); continue
    sf.write(f, x, sr, subtype="PCM_16")
    w.writerow({"uid": r["uid"], "spk": r["spk"], "split": r["split"], "cloner": cloner, "sr": sr,
                "dur": round(len(x) / sr, 2), "secs": round(time.time() - s, 2)}); meta.flush()
    if (i + 1) % 20 == 0:
        print(f"{i + 1}/{len(rows)} {(i + 1) / (time.time() - t0):.2f} clips/s", flush=True)
print("DONE", flush=True)
