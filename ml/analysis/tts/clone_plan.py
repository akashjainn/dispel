"""Clone-set design (paired): for each LibriSpeech speaker, one ~10-15 s reference built from one chapter, and up to
T target utterances (4-12 s) from OTHER chapters. Each target is later synthesized by each cloner from the reference
+ the target's transcript, and paired with the speaker's real recording of that same utterance.
Speaker split follows DiffSSD (speaker-disjoint): speakers whose real audio is in DiffSSD 'train' -> clone split
'train'; DiffSSD 'val' -> 'val'; DiffSSD 'test' -> 'eval' (the detector never trained on their real voice).
Out: data/clonesrc/plan.csv, data/clonesrc/refs/<spk>.wav (16 kHz, ffmpeg)"""
import csv, glob, os, random, re, subprocess
from collections import defaultdict
from pathlib import Path
import soundfile as sf, pandas as pd
R = Path.home() / "hackgt"; LS = R / "data/clonesrc/LibriSpeech"; OUT = R / "data/clonesrc"
T = int(os.getenv("T", "10"))
sp = pd.read_csv(R / "data/diffssd_hf/train_val_test_splits.csv")
sp = sp[sp.method_name == "librispeech"].copy()
sp["spk"] = sp.filename.str.extract(r"librispeech/[^/]+/(\d+)/")[0]
spk_set = sp.groupby("spk").set.agg(lambda s: s.mode()[0]).to_dict()
rng = random.Random(7)
utts = defaultdict(list)  # spk -> [(chapter, uid, path, text, dur)]
for sub in ("dev-clean", "test-clean", "dev-other", "test-other"):
    for tr in glob.glob(str(LS / sub / "*/*/*.trans.txt")):
        spk, ch = Path(tr).parts[-3], Path(tr).parts[-2]
        for line in open(tr):
            uid, text = line.strip().split(" ", 1)
            p = Path(tr).parent / f"{uid}.flac"
            utts[spk].append((ch, uid, str(p), text, sf.info(str(p)).duration, sub))
(OUT / "refs").mkdir(exist_ok=True)
rows = []
for spk, U in sorted(utts.items()):
    if spk not in spk_set:
        continue
    split = {"train": "train", "val": "val", "test": "eval"}[spk_set[spk]]
    bych = defaultdict(list)
    for u in U: bych[u[0]].append(u)
    chs = sorted(bych, key=lambda c: -sum(u[4] for u in bych[c]))
    if len(chs) < 2:
        continue
    ref_ch = chs[0]
    cand = sorted([u for u in bych[ref_ch] if 3 <= u[4] <= 12], key=lambda u: u[1])
    ref, dur = [], 0.0
    for u in cand:
        if dur >= 10: break
        ref.append(u); dur += u[4]
    if dur < 6:
        continue
    lst = OUT / f"refs/{spk}.txt"
    lst.write_text("".join(f"file '{u[2]}'\n" for u in ref))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ac", "1",
                    "-ar", "16000", str(OUT / f"refs/{spk}.wav")], check=True)
    ref_text = " ".join(u[3] for u in ref)
    targets = [u for c in chs[1:] for u in bych[c] if 4 <= u[4] <= 12]
    rng.shuffle(targets)
    for u in targets[:T]:
        rows.append({"spk": spk, "split": split, "subset": u[5], "ref_wav": f"data/clonesrc/refs/{spk}.wav",
                     "ref_dur": round(dur, 2), "ref_text": ref_text.lower(), "uid": u[1], "text": u[3].lower(),
                     "real_path": os.path.relpath(u[2], R), "real_dur": round(u[4], 2)})
pd.DataFrame(rows).to_csv(OUT / "plan.csv", index=False)
d = pd.DataFrame(rows)
print(d.groupby("split").agg(speakers=("spk", "nunique"), targets=("uid", "size")))
print(d.groupby("subset").spk.nunique())
