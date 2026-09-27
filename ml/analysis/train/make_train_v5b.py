"""Derive train_v5b.py from train_v5.py: additionally trains on 80% of DiffSSD's TEST split (all methods, incl. the
generators DiffSSD train lacks: diffgantts, playht, unitspeech). The other 20% per method stays held out
(data/splits/v5b_diffssd_test_holdout.csv). Team decision 2026-09-26: DiffSSD's test split is fair game for training."""
from pathlib import Path
d = Path.home() / "hackgt/scratch/train"
s = (d / "train_v5.py").read_text()
s = s.replace('"""v5 (derived', '"""v5b (derived from train_v5.py by make_train_v5b.py): + 80% of DiffSSD\'s test split (all methods).\n\nv5 (derived', 1)
old = '''    ds_rows, short = diffssd_rows()
'''
assert old in s
s = s.replace(old, old + '''    dur = {r["filename"]: float(r["dur"]) for r in csv.DictReader(open(DATA.parent / "results/scores/diffssd_profile_headers.csv"))}
    ho = {r["filename"] for r in csv.DictReader(open(DATA / "splits/v5b_diffssd_test_holdout.csv"))}
    extra, missing = [], 0
    for r in csv.DictReader(open(DATA / "splits/v5b_diffssd_test_train.csv")):
        assert r["filename"] not in ho
        if r["filename"] not in dur:
            missing += 1
        elif dur[r["filename"]] < 3.0:
            short += 1; continue
        extra.append({"path": "diffssd/" + r["filename"], "label": int(r["target"]), "group": r["method_name"], "source": "diffssd"})
    ds_rows += extra
    log.info("diffssd test split: +%d training clips (%d without a duration header, kept); holdout %d", len(extra), missing, len(ho))
''')
s = s.replace('ap.add_argument("--run", default="v5")', 'ap.add_argument("--run", default="v5b")')
(d / "train_v5b.py").write_text(s)
print("wrote", d / "train_v5b.py")
