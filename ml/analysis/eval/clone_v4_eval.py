import sys, numpy as np, pandas as pd
from pathlib import Path
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from ml.fit_fusion import min_dcf
from sklearn.metrics import roc_auc_score
plan = pd.read_csv(R / "data/clonesrc/plan.csv")[["uid", "spk", "split", "subset"]]
z = np.load(R / "data/checkpoints/v4/val_scores_ep0.npz"); val = pd.read_csv(R / "data/splits/v3_val.csv")
def thr(s, y, p=0.3, c=4.0):
    o = np.argsort(-s); ys = y[o]; P, N = ys.sum(), (1 - ys).sum()
    d = p * (1 - np.r_[0, np.cumsum(ys)] / P) + c * (1 - p) * np.r_[0, np.cumsum(1 - ys)] / N; k = int(np.argmin(d)); ss = s[o]
    return (ss[k - 1] + ss[k]) / 2 if 0 < k < len(ss) else ss[0] + 1
for c in ("clean", "atempo", "rubberband"):
    f = pd.read_csv(R / f"results/clone_v4_f5_{c}.csv"); r = pd.read_csv(R / f"results/clone_v4_real_{c}.csv")
    for d in (f, r): d["uid"] = d.path.str.split("/").str[-1].str[:-4]
    m = plan.merge(f[["uid", "s_v3"]].rename(columns={"s_v3": "fake"}), on="uid").merge(r[["uid", "s_v3"]].rename(columns={"s_v3": "real"}), on="uid")
    t = thr(z["atempo" if c != "clean" else "clean"], val.label.values)
    for sp in ("all", "eval"):
        k = m if sp == "all" else m[m.split == "eval"]
        s = np.r_[k.fake, k.real]; y = np.r_[np.ones(len(k)), np.zeros(len(k))]
        print(f"{c:10s} {sp:4s} n={len(k):4d} minDCF {min_dcf(s, y):.3f} AUC {roc_auc_score(y, s):.4f} | pair fake>real {np.mean(k.fake > k.real):.3f} | at val thr {t:+.1f}: clones caught {np.mean(k.fake > t):.3f}, reals flagged {np.mean(k.real > t):.4f} | med fake {k.fake.median():+.1f} real {k.real.median():+.1f}")
