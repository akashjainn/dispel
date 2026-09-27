import numpy as np, pandas as pd
from pathlib import Path
E = Path.home() / "hackgt/results/evalbundle"
A = pd.read_csv(E / "lap_ad_xlsr1b.csv"); A["v4"] = pd.read_csv(E / "lap_v4.csv").v4; A["mms"] = pd.read_csv(E / "lap_ad_mms300m.csv").ad_mms300m
T = A[A.set == "NSA_TEST"].copy()
d = pd.read_csv(Path.home() / "hackgt/submissions/HearsayScoreKey4Gemini.tsv", sep="\t"); p = d["cm-score"].clip(1e-9, 1 - 1e-9); d["fused"] = np.log(p / (1 - p))
T = T.merge(d[["filename", "fused"]], left_on="file", right_on="filename")
dur = np.load(Path.home() / "hackgt/results/nsa_test_durations.npy"); 
groups = {"agree real (ad1b<0, v4<0)": (T.ad_xlsr1b < 0) & (T.v4 < 0), "DISPUTED (ad1b<0, v4>0)": (T.ad_xlsr1b < 0) & (T.v4 > 0),
          "disputed-2 (ad1b>0, v4<0)": (T.ad_xlsr1b > 0) & (T.v4 < 0), "agree fake (ad1b>0, v4>0)": (T.ad_xlsr1b > 0) & (T.v4 > 0)}
for k, m in groups.items():
    g = T[m]; print(f"{k:28s} n={len(g):4d} | ad1b med {g.ad_xlsr1b.median():+.1f} | v4 med {g.v4.median():+.1f} | mms med {g.mms.median():+.1f} | mms>0 {np.mean(g.mms > 0):.2f} | fused>0 {np.mean(g.fused > 0):.2f}")
print("files (disputed, top v4):", T[groups["DISPUTED (ad1b<0, v4>0)"]].sort_values("v4", ascending=False).file.head(8).tolist())
T.to_csv(Path.home() / "hackgt/results/nsa_test_models.csv", index=False)
