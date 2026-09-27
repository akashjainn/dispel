"""v3 validation subset (DiffSSD set==val only) and its fixed-seed cached conditions.
List: data/splits/v3_val.csv (path rel. to data/, label, group=method_name, source=diffssd): all val reals + up to 300
per val generator (numpy seed 13). Cache: data/eval_cache/v3_val/<cond>/<i>.npy, 16 kHz mono float32, cond in
clean | atempo (NSA-like, held-out ffmpeg atempo) | pv (NSA-like, librosa phase vocoder); see v3_aug.nsa_eval."""
import csv, sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from train import DATA, load_audio
from v3_aug import nsa_eval
OUT = DATA / "eval_cache/v3_val"

def job(a):
    i, p = a
    x = load_audio(DATA / p)
    np.save(OUT / "clean" / f"{i}.npy", x)
    for c in ("atempo", "pv"):
        np.save(OUT / c / f"{i}.npy", nsa_eval(x, "data/" + p, c)[0])
    return i

if __name__ == "__main__":
    R = [r for r in csv.DictReader(open(DATA / "diffssd_hf/train_val_test_splits.csv")) if r["set"] == "val"]
    rng = np.random.default_rng(13); rows = []
    for m in sorted({r["method_name"] for r in R}):
        rs = [r for r in R if r["method_name"] == m]
        if rs[0]["target"] == "1" and len(rs) > 300:
            rs = [rs[i] for i in sorted(rng.choice(len(rs), 300, replace=False))]
        rows += [{"path": "diffssd/" + r["filename"], "label": int(r["target"]), "group": m, "source": "diffssd"} for r in rs]
    with open(DATA / "splits/v3_val.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "label", "group", "source"]); w.writeheader(); w.writerows(rows)
    print(len(rows), Counter(r["group"] for r in rows))
    for c in ("clean", "atempo", "pv"): (OUT / c).mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(7) as ex: n = sum(1 for _ in ex.map(job, list(enumerate(r["path"] for r in rows)), chunksize=16))
    print("cached", n)
