"""Stretch-condition detector + condition-aware score normalization.
(1) Classify which processing a clip went through: none (clean) / ffmpeg atempo / rubberband / librosa phase vocoder,
    from the interpretable features + the neural scores. GBM, 5-fold grouped by clip on DiffSSD val.
(2) Condition-aware normalization: real clips' fused LLR shifts by condition (rubberband pushes reals toward
    'synthetic'), which hurts when conditions are mixed in one ranking. Subtract the expected real-clip LLR of the
    predicted condition (probability-weighted), estimated on training folds only. Compare pooled minDCF.
(3) Apply the detector to NSA's 1,671 test clips: which stretch method(s) did NSA use?
Caveat (exploratory study, not used by any release): the per-group feature models in (2) are cross-fitted but not
nested inside the outer folds, so the fusion sees features whose models were trained on other folds that include its
test rows' labels. Treat the pooled minDCF here as optimistic; fit_fusion.py has the nested version."""
import sys, glob, os, warnings
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd, soundfile as sf, torch
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
warnings.filterwarnings("ignore")
R = Path.home() / "hackgt"
sys.path.insert(0, str(R / "dispel_pr8fix")); sys.path.insert(0, str(R / "scratch/features"))
from ml.fit_fusion import GROUPS, gbm, qlogit, min_dcf
CONDS = ["clean", "atempo", "rubberband", "pv"]
val = pd.read_csv(R / "data/splits/v3_val.csv"); n = len(val); yv = val.label.values
base = pd.read_csv(R / "results/pitch_v3val.csv").merge(pd.read_csv(R / "results/feats3_v3val.csv").drop(columns=["label", "group"]), on=["idx", "cond"])
df = pd.concat([base, pd.read_csv(R / "results/feats_all_v3val_rubberband.csv")], ignore_index=True)
z4 = np.load(R / "data/checkpoints/v4/val_scores_ep0.npz"); zl = np.load(R / "results/lfcc_val_scores.npz")
v4rb = pd.read_csv(R / "results/v4_val_rubberband.csv").s_v3.values; lfrb = np.load(R / "results/lfcc_val_rubberband.npy")
df["v3"] = [v4rb[i] if c == "rubberband" else z4[c][i] for c, i in zip(df.cond, df.idx)]
df["lfcc"] = [lfrb[i] if c == "rubberband" else zl[c][i] for c, i in zip(df.cond, df.idx)]
FEATS = sorted({f for _, fs in GROUPS for f in fs}) + ["v3", "lfcc"]
for f in FEATS:
    if f not in df: df[f] = np.nan
y, g, cond = df.label.values, df.idx.values, df.cond.values
cidx = np.array([CONDS.index(c) for c in cond])
folds = list(StratifiedGroupKFold(5, shuffle=True, random_state=0).split(np.zeros(n), yv, np.arange(n)))
X = df[FEATS].values.astype(float)
# fused LLR, out-of-fold, fusion fit on clean/atempo/pv only (rubberband never seen), as in rb_analysis.py
fit_rows = cond != "rubberband"; cols = [df.v3.values, df.lfcc.values]
for _, fs in GROUPS:
    Xg, q = df[fs].values.astype(float), np.zeros(len(df))
    for trc, tec in folds:
        tr = fit_rows & np.isin(g, trc); te = np.isin(g, tec)
        q[te] = qlogit(gbm().fit(Xg[tr], y[tr]).predict_proba(Xg[te])[:, 1])
    cols.append(q)
Z = np.c_[tuple(cols)]; llr = np.zeros(len(df)); P = np.zeros((len(df), 4)); adj = np.zeros(len(df))
for trc, tec in folds:
    tr = np.isin(g, trc); te = np.isin(g, tec)
    llr[te] = LogisticRegression(class_weight="balanced", C=1e6, max_iter=2000).fit(Z[tr & fit_rows], y[tr & fit_rows]).decision_function(Z[te])
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0).fit(X[tr], cidx[tr])
    P[te] = clf.predict_proba(X[te])
    # expected real LLR per condition, from training folds
    trllr = LogisticRegression(class_weight="balanced", C=1e6, max_iter=2000).fit(Z[tr & fit_rows], y[tr & fit_rows]).decision_function(Z[tr])
    mu = np.array([np.median(trllr[(cidx[tr] == k) & (y[tr] == 0)]) for k in range(4)])
    adj[te] = llr[te] - P[te] @ mu
pred = P.argmax(1)
print("condition detector, out-of-fold on DiffSSD val (rows = true, cols = predicted):")
cm = pd.crosstab(pd.Series(np.array(CONDS)[cidx], name="true"), pd.Series(np.array(CONDS)[pred], name="pred")).reindex(index=CONDS, columns=CONDS)
print(cm.to_string()); print("accuracy %.3f" % (pred == cidx).mean())
for k, c in enumerate(CONDS):
    print(f"  {c:10s} recall {((pred == k) & (cidx == k)).sum() / (cidx == k).sum():.3f}  (reals {((pred == k) & (cidx == k) & (y == 0)).sum() / ((cidx == k) & (y == 0)).sum():.3f}, fakes {((pred == k) & (cidx == k) & (y == 1)).sum() / ((cidx == k) & (y == 1)).sum():.3f})")
print("\nminDCF (lower is better)            " + "  ".join(f"{c:>10s}" for c in CONDS) + "   pooled(all 4)  pooled(no rb)")
for name, s in (("fused LLR", llr), ("fused LLR, condition-normalized", adj)):
    per = [min_dcf(s[cond == c], y[cond == c]) for c in CONDS]
    nr = cond != "rubberband"
    print(f"{name:35s}" + "  ".join(f"{v:10.3f}" for v in per) + f"   {min_dcf(s, y):12.3f}  {min_dcf(s[nr], y[nr]):12.3f}")
# (3) NSA test clips
clf_all = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0).fit(X, cidx)
tf = R / "results/nsa_test_feats.csv"
if not tf.exists():
    from pitch_features import pitch_features
    from spectral import spectral_features
    from rhythm import rhythm_features
    from voice import voice_features
    D = R / "data/nsa/test/HackGTHearsayTesting"
    def job(p):
        x, sr = sf.read(p, dtype="float32"); o = {"file": os.path.basename(p)}
        for fn in (pitch_features, spectral_features, rhythm_features, voice_features):
            try: o.update(fn(x, sr))
            except Exception: pass
        return o
    with Pool(8) as pool:
        T = pd.DataFrame(pool.map(job, sorted(glob.glob(str(D / "*.wav"))), chunksize=8))
    T.to_csv(tf, index=False)
T = pd.read_csv(tf)
sub = pd.read_csv(R / "submissions/draft_v4p6_nsa.tsv", sep="\t")
nv = pd.read_csv(R / "results/nsa_test_v4.csv") if (R / "results/nsa_test_v4.csv").exists() else None
n_test = len(T); assert T.file.is_unique, "duplicate file names in the NSA feature table"
T = T.merge(nv.assign(file=nv.path.str.split("/").str[-1])[["file", "s_v3"]].rename(columns={"s_v3": "v3"}), on="file", how="left", validate="one_to_one") if nv is not None else T
T = T.merge(pd.read_csv(R / "results/nsa_test_lfcc.csv"), on="file", how="left", validate="one_to_one") if (R / "results/nsa_test_lfcc.csv").exists() else T
assert len(T) == n_test, f"NSA clips lost in a join: {len(T)} of {n_test}"
for c in ("v3", "lfcc"):
    if c in T: print(f"{c}: {T[c].notna().sum()} of {n_test} NSA clips have a score (missing ones are NaN for the GBM)")
for f in FEATS:
    if f not in T: T[f] = np.nan
PT = clf_all.predict_proba(T[FEATS].values.astype(float))
print("\nNSA test set (1,671 clips): predicted processing (share of clips by argmax | mean probability)")
for k, c in enumerate(CONDS):
    print(f"  {c:10s} {(PT.argmax(1) == k).mean():6.1%} | {PT[:, k].mean():.3f}")
print("NB: test clips are short (median 3.4 s) and peak-normalized; the detector was trained on full-length val clips.")
pd.DataFrame(PT, columns=CONDS).assign(file=T.file).to_csv(R / "results/nsa_test_condition_probs.csv", index=False)
