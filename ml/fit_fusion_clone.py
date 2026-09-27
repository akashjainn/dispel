"""Clone-aware fusion candidate (v4p6c): same six terms and additive form as v4p6, but the four feature GBMs and the
fusion weights are fit on DiffSSD validation PLUS the train-fold teammates (5 consenting speakers: real clips and
ElevenLabs clones of them), team rows weighted to W_TEAM of the validation mass, classes balanced within the team rows.
Evaluation (nothing below is used for fitting):
  * DiffSSD val, nested out-of-fold exactly like ml/fit_fusion.py (team rows always in the training side, grouped by speaker)
  * held-out teammates (5 other speakers), Akash, NSA LJRealResampled reals
Usage: python fit_fusion_clone.py [W_TEAM=0.10] [--write OUTDIR]"""
import sys, shutil, json, datetime
from pathlib import Path
import numpy as np, pandas as pd, joblib, sklearn
from sklearn.model_selection import StratifiedGroupKFold, GroupKFold
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from ml.fit_fusion import GROUPS, gbm, qlogit, min_dcf, QCLIP
W_TEAM = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else 0.10
val = pd.read_csv(R / "results/pitch_v3val.csv").merge(pd.read_csv(R / "results/feats3_v3val.csv").drop(columns=["label", "group"]), on=["idx", "cond"])
z4, zl = np.load(R / "data/checkpoints/v4/val_scores_ep0.npz"), np.load(R / "results/lfcc_val_scores.npz")
val["v3"] = [z4[c][i] for c, i in zip(val.cond, val.idx)]; val["lfcc"] = [zl[c][i] for c, i in zip(val.cond, val.idx)]
T = pd.read_csv(R / "results/team_feats.csv")
for _, fs in GROUPS:
    for f in fs:
        for d in (val, T):
            if f not in d: d[f] = np.nan
tr_team = T[(T.set == "team") & (T.split == "train")].reset_index(drop=True)
test = T[~((T.set == "team") & (T.split == "train"))].reset_index(drop=True)
def weights(d_val, d_team):
    wt = np.where(d_team.label == 1, 0.5 / max((d_team.label == 1).sum(), 1), 0.5 / max((d_team.label == 0).sum(), 1))
    return np.r_[np.ones(len(d_val)), wt * W_TEAM * len(d_val)]
def stack(d_val, d_team): return pd.concat([d_val, d_team], ignore_index=True)
def fit_terms(D, y, w, grp):
    """GBMs fit on all of D; training-side Q terms from inner folds (group = clip idx / speaker)."""
    inner = list(GroupKFold(5).split(D, y, grp))
    Qtr, models = [], []
    for name, fs in GROUPS:
        X = D[fs].values.astype(float); q = np.zeros(len(D))
        for a, b in inner: q[b] = qlogit(gbm().fit(X[a], y[a], sample_weight=w[a]).predict_proba(X[b])[:, 1])
        Qtr.append(q); models.append(gbm().fit(X, y, sample_weight=w))
    Ztr = np.c_[tuple([D.v3.values, D.lfcc.values] + Qtr)]
    lr = LogisticRegression(class_weight="balanced", C=1e6, max_iter=3000).fit(Ztr, y, sample_weight=w)
    return models, lr
def score(models, lr, E):
    Z = np.c_[tuple([E.v3.values, E.lfcc.values] + [qlogit(m.predict_proba(E[fs].values.astype(float))[:, 1]) for m, (_, fs) in zip(models, GROUPS)])]
    return lr.decision_function(Z)
# 1) DiffSSD val nested OOF
y = val.label.values; g = val.idx.values
o = np.zeros(len(val))
for a, b in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(val, y, g):
    D = stack(val.iloc[a], tr_team); yy = D.label.values.astype(int); w = weights(val.iloc[a], tr_team)
    grp = np.r_[val.idx.values[a], ("spk_" + tr_team.spk).values].astype(str)
    m, lr = fit_terms(D, yy, w, grp); o[b] = score(m, lr, val.iloc[b])
print(f"W_TEAM={W_TEAM}")
print("DiffSSD val OOF minDCF  " + "  ".join(f"{c} {min_dcf(o[val.cond == c], y[val.cond == c]):.3f}" for c in ("clean", "atempo", "pv")) + "   (v4p6: clean 0.000 atempo 0.007 pv 0.088)")
# 2) held-out sets, fit on all val + train-fold team
D = stack(val, tr_team); yy = D.label.values.astype(int); w = weights(val, tr_team)
grp = np.r_[val.idx.values, ("spk_" + tr_team.spk).values].astype(str)
models, lr = fit_terms(D, yy, w, grp)
test["llr_c"] = score(models, lr, test)
names = ["dl_detector", "lfcc"] + [n for n, _ in GROUPS]
print("weights: " + ", ".join(f"{n} {v:.3f}" for n, v in zip(names, lr.coef_[0])) + f", bias {lr.intercept_[0]:.3f}")
lj = test[test.set == "nsa_lj"]
for col in ("llr_v4p6", "llr_c"):
    print(f"-- {col}")
    for s in ("team", "akash"):
        d = test[test.set == s]; yy = d.label.values
        print(f"  {s:6s} n={len(d):3d} minDCF {min_dcf(d[col].values, yy):.3f} AUC {roc_auc_score(yy, d[col]):.3f} | med real {d[col][yy==0].median():+.1f} fake {d[col][yy==1].median():+.1f} | fakes > 0: {np.mean(d[col][yy==1] > 0):.2f}")
    P = test[(test.set != "nsa_lj")]; Q = pd.concat([P[P.label == 1], lj, P[P.label == 0]])
    print(f"  pooled (held-out+akash clones vs NSA LJ + held-out + akash reals) minDCF {min_dcf(Q[col].values, Q.label.values):.3f} | NSA LJ reals med {lj[col].median():+.1f} max {lj[col].max():+.1f}")
if "--write" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--write") + 1]); src = R / "data/release/v4p6"
    shutil.copytree(src, out, dirs_exist_ok=True)
    blob = joblib.load(src / "fusion.joblib")
    for t, m in zip(blob["terms"][2:], models): t["model"] = m
    blob["weights"] = [float(v) for v in lr.coef_[0]]; blob["bias"] = float(lr.intercept_[0])
    blob["fit"] = {**blob.get("fit", {}), "date": datetime.date.today().isoformat(), "clone_aware": {"team_train_speakers": sorted(tr_team.spk.unique()), "w_team": W_TEAM}}
    blob["report_md"] = "clone-aware refit of v4p6 (fit_fusion_clone.py)"
    joblib.dump(blob, out / "fusion.joblib")
    import hashlib
    spec = json.load(open(out / "hearsay.json")); spec["name"] = out.name
    spec["fusion"]["sha256"] = hashlib.sha256(open(out / "fusion.joblib", "rb").read()).hexdigest()
    spec["weights"] = dict(zip(names, blob["weights"])); spec["bias"] = blob["bias"]
    json.dump(spec, open(out / "hearsay.json", "w"), indent=2); print("wrote", out)
