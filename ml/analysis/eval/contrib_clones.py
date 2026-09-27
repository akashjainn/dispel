"""Per-analyzer contributions of the v4p6 fusion on the teammate + Akash clone sets (why fused scores fall below 0)."""
import sys, glob
from pathlib import Path
import numpy as np, pandas as pd
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from hearsay.orchestrator import Pipeline
from hearsay import audio as A
pipe = Pipeline(str(R / "data/release/v4p6"), profile="nsa")
files = [(p, "team", 0) for p in sorted(glob.glob(str(R / "data/consent/team/real/*.wav")))] + \
        [(p, "team", 1) for p in sorted(glob.glob(str(R / "data/consent/team/fake/*.wav")))] + \
        [(p, "team_gen", 1) for p in sorted(glob.glob(str(R / "data/v5team/gen_fake/*/*.wav")))[::3]] + \
        [(p, "akash", 0) for p in sorted(glob.glob(str(R / "data/consent/akash/real/*.wav")))] + \
        [(p, "akash", 1) for p in sorted(glob.glob(str(R / "data/consent/akash/fake/*/*.mp3")))] + \
        [(p, "nsa_lj", 0) for p in sorted(glob.glob(str(R / "data/nsa/LJRealResampled/resampled/*.wav")))[::4]]
rows = []
for p, s, y in files:
    x, info = A.load(p); _, f = pipe._run(x, info)
    rows.append({"path": p, "set": s, "label": y, "llr": f["llr_raw"], **f["contrib"]})
D = pd.DataFrame(rows); D.to_csv(R / "results/contrib_clones.csv", index=False)
terms = [c for c in D.columns if c not in ("path", "set", "label", "llr")]
print(D.groupby(["set", "label"])[["llr"] + terms].median().round(1).to_string())
