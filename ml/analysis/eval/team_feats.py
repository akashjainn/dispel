"""Analyzer features (exact release pipeline, v4p6) for the consenting-teammate set, Akash's set and NSA LJ reals.
Out: results/team_feats.csv (one row per clip: set, spk, label, split, detail + every fusion input feature)."""
import sys, glob
from pathlib import Path
import pandas as pd
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from hearsay.orchestrator import Pipeline
from hearsay import audio as A
pipe = Pipeline(str(R / "data/release/v4p6"), profile="nsa")
t = pd.read_csv(R / "data/splits/v5_team.csv")
items = [dict(set="team", spk=r.spk, label=r.label, split=r.split, detail=r.detail, path=str(R / "data" / r.path)) for r in t.itertuples()]
items += [dict(set="akash", spk="akash", label=0, split="test", detail="real", path=p) for p in sorted(glob.glob(str(R / "data/consent/akash/real/*.wav")))]
items += [dict(set="akash", spk="akash", label=1, split="test", detail=Path(p).parent.name, path=p) for p in sorted(glob.glob(str(R / "data/consent/akash/fake/*/*.mp3")))]
items += [dict(set="nsa_lj", spk="lj", label=0, split="test", detail="", path=p) for p in sorted(glob.glob(str(R / "data/nsa/LJRealResampled/resampled/*.wav")))]
rows = []
for i, it in enumerate(items):
    x, info = A.load(it["path"]); res, f = pipe._run(x, info)
    feats = {}
    for r in res.values(): feats.update(r["features"])
    rows.append({**it, **feats, "llr_v4p6": f["llr_raw"]})
    if i % 100 == 0: print(i, len(items), flush=True)
pd.DataFrame(rows).to_csv(R / "results/team_feats.csv", index=False); print("DONE")
