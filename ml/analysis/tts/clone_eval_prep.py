"""Paired clone eval set: 16 kHz (ffmpeg) clones + their paired real LibriSpeech utterances, clean and NSA-like
(ffmpeg atempo or rubberband stretch + noise, same seeded draws as validation, keyed by uid so a clone and its real
get the same rate/SNR). Out: data/clones16/<cloner|real>/<cond>/<uid>.wav and data/clones16/list_<cloner|real>_<cond>.csv
Usage: python clone_eval_prep.py <cloner> [<cloner> ...]   (clone wavs expected in data/clonesrc/clones/<cloner>/)"""
import csv, subprocess, sys, os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, soundfile as sf
R = Path.home() / "hackgt"
sys.path.insert(0, str(R / "scratch/train"))
from v3_aug import nsa_eval
OUT = R / "data/clones16"
plan = {r["uid"]: r for r in csv.DictReader(open(R / "data/clonesrc/plan.csv"))}
CONDS = ("clean", "atempo", "rubberband")

def ff16(src):
    o = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "16000", "-f", "f32le",
                        "pipe:1"], capture_output=True, check=True).stdout
    return np.frombuffer(o, "<f4").copy()

def job(a):
    kind, uid, src = a
    x = ff16(src)
    for c in CONDS:
        d = OUT / kind / c; d.mkdir(parents=True, exist_ok=True)
        f = d / f"{uid}.wav"
        if f.exists():
            continue
        y = x if c == "clean" else nsa_eval(x, "clonepair/" + uid, c)[0]
        sf.write(f, np.clip(y, -1, 1), 16000, subtype="PCM_16")
    return kind, uid

if __name__ == "__main__":
    todo = []
    for cl in sys.argv[1:]:
        for p in sorted((R / "data/clonesrc/clones" / cl).glob("*.wav")):
            if p.stem in plan:
                todo.append((cl, p.stem, p))
    uids = sorted({u for _, u, _ in todo})
    todo += [("real", u, R / plan[u]["real_path"]) for u in uids]
    with ProcessPoolExecutor(8) as ex:
        done = list(ex.map(job, todo, chunksize=8))
    for kind in sorted({k for k, _ in done}):
        us = sorted(u for k, u in done if k == kind)
        for c in CONDS:
            with open(OUT / f"list_{kind}_{c}.csv", "w") as fh:
                fh.write("path\n" + "".join(f"data/clones16/{kind}/{c}/{u}.wav\n" for u in us))
        print(kind, len(us))
