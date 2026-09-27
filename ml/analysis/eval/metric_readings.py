"""Our val scores under three readings of NSA's minDCF. y=1 spoof, higher s = more spoof.
C = NSA instructions as we implemented: 0.3*P(miss spoof) + 4*0.7*P(real flagged)
A = stock calculate_metrics.py, Pspoof .3, Cmiss 1, Cfa 4, bona fide target, scores flipped so higher = real
B = stock script with labels swapped (spoof as target) and our scores unflipped"""
import sys, csv
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.linear_model import LogisticRegression
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from ml.fit_fusion import GROUPS, gbm, qlogit
def dcf(s, y, wm, wf):
    o = np.argsort(-s); ys = y[o]; P, N = ys.sum(), (1 - ys).sum()
    tp = np.r_[0, np.cumsum(ys)]; fp = np.r_[0, np.cumsum(1 - ys)]
    d = wm * (1 - tp / P) + wf * fp / N; k = int(np.argmin(d))
    return d[k] / min(wm, wf), 1 - tp[k] / P, fp[k] / N
M = {"C ours": (0.3, 2.8), "A stock+flip": (1.2, 0.7), "B swapped": (0.7, 1.2)}
val = pd.read_csv(R / "data/splits/v3_val.csv"); lab = val.label.values
df = pd.read_csv(R / "results/pitch_v3val.csv").merge(pd.read_csv(R / "results/feats3_v3val.csv").drop(columns=["label", "group"]), on=["idx", "cond"])
z4, zl = np.load(R / "data/checkpoints/v4/val_scores_ep0.npz"), np.load(R / "results/lfcc_val_scores.npz")
df["v3"] = [z4[c][i] for c, i in zip(df.cond, df.idx)]; df["lfcc"] = [zl[c][i] for c, i in zip(df.cond, df.idx)]
y, g = df.label.values, df.idx.values
folds = list(StratifiedGroupKFold(5, shuffle=True, random_state=0).split(df, y, g))
cols = [df.v3.values, df.lfcc.values]
for _, fs in GROUPS:
    for f in fs:
        if f not in df: df[f] = np.nan
    X, q = df[fs].values.astype(float), np.zeros(len(df))
    for tr, te in folds: q[te] = qlogit(gbm().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1])
    cols.append(q)
Z = np.c_[tuple(cols)]; o = np.zeros(len(df))
for tr, te in folds:
    o[te] = LogisticRegression(class_weight="balanced", C=1e6, max_iter=2000).fit(Z[tr], y[tr]).decision_function(Z[te])
df["fused"] = o
print(f"{'system':8s} {'cond':7s} " + " | ".join(f"{m:>12s}: minDCF (miss, FA)" for m in M))
for sysn, col in (("v4", "v3"), ("lfcc", "lfcc"), ("fused", "fused")):
    for c in ("clean", "atempo", "pv", "pooled"):
        k = np.ones(len(df), bool) if c == "pooled" else df.cond.values == c
        s, yy = df[col].values[k], y[k]
        print(f"{sysn:8s} {c:7s} " + " | ".join("%12s  %.3f (%.3f, %.4f)" % ("", *dcf(s, yy, *w)) for w in M.values()))
zs = R / "results/shortclip_v4.npz"
if zs.exists():
    z = np.load(zs)
    for k in sorted(z.files):
        print(f"short {k:14s} " + " | ".join("%.3f (%.3f, %.4f)" % dcf(z[k], lab, *w) for w in M.values()))
