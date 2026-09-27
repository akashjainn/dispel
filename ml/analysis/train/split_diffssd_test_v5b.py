"""Split DiffSSD's own test split for v5b: 80% joins training (all 12 methods incl. the 3 generators absent from
DiffSSD train: diffgantts, playht, unitspeech), 20% per method is held out as an honest in-distribution check.
Out: data/splits/v5b_diffssd_test_{train,holdout}.csv (filename,method_name,target)"""
import csv, random
from pathlib import Path
D = Path.home() / "hackgt/data"
rows = [r for r in csv.DictReader(open(D / "diffssd_hf/train_val_test_splits.csv")) if r["set"] == "test"]
by = {}
for r in rows: by.setdefault(r["method_name"], []).append(r)
tr, ho = [], []
for m, rr in sorted(by.items()):
    rr = sorted(rr, key=lambda r: r["filename"]); random.Random(f"v5b-{m}").shuffle(rr)
    k = len(rr) // 5; ho += rr[:k]; tr += rr[k:]
for name, rr in (("train", tr), ("holdout", ho)):
    with open(D / f"splits/v5b_diffssd_test_{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "method_name", "target"]); w.writeheader()
        w.writerows({k: r[k] for k in ("filename", "method_name", "target")} for r in rr)
print("train", len(tr), "holdout", len(ho))
