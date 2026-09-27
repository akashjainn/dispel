"""Clone-aware fusion candidate: refit the v4p6 fusion (same 6 terms, same GBMs, same LR) on DiffSSD validation PLUS
the train-fold teammates (real clips + ElevenLabs clones), team rows weighted to `alpha` of the total training weight.
Evaluated without touching any NSA/DiffSSD test data:
  DiffSSD val  : nested out-of-fold (team train rows are in every training fold, never in a test fold)
  held-out     : 5 held-out teammates, Akash's recording + clone, NSA LJRealResampled reals (fit on all training rows)
Usage: python fit_fusion_clone.py [--write alpha]   (--write saves a release dir data/release/v4p6c_<alpha>)"""
import sys, json, shutil, datetime
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from ml.fit_fusion import GROUPS, gbm, qlogit, min_dcf, QCLIP, sha256
CONDS = ("clean", "atempo", "pv")
df = pd.read_csv(R / "results/pitch_v3val.csv").merge(pd.read_csv(R / "results/feats3_v3val.csv").drop(columns=["label", "group"]), on=["idx", "cond"])
z4, zl = np.load(R / "data/checkpoints/v4/val_scores_ep0.npz"), np.load(R / "results/lfcc_val_scores.npz")
df["v3"] = [z4[c][i] for c, i in zip(df.cond, df.idx)]; df["lfcc"] = [zl[c][i] for c, i in zip(df.cond, df.idx)]
T = pd.read_csv(R / "results/team_feats.csv")
for _, fs in GROUPS:
    for f in fs:
        for d in (df, T):
            if f not in d: d[f] = np.nan
TR = T[(T.set == "team") & (T.split == "train")].reset_index(drop=True)
HO = T[~((T.set == "team") & (T.split == "train"))].reset_index(drop=True)
y, g = df.label.values, df.idx.values
folds = list(StratifiedGroupKFold(5, shuffle=True, random_state=0).split(df, y, g))
FEATS = ["v3", "lfcc"]
def lr(Z, yy, w): return LogisticRegression(class_weight="balanced", C=1e6, max_iter=3000).fit(Z, yy, sample_weight=w)
def fit_terms(X, yy, w, groups_idx):
    """GBMs on (X,yy,w); returns fitted models and OOF terms for the rows (5 folds over groups_idx)."""
    models, oof = {}, np.zeros((len(yy), len(GROUPS)))
    inner = list(StratifiedGroupKFold(5, shuffle=True, random_state=1).split(X, yy, groups_idx))
    for j, (name, fs) in enumerate(GROUPS):
        Xf = X[fs].values.astype(float)
        for itr, ite in inner:
            oof[ite, j] = qlogit(gbm().fit(Xf[itr], yy[itr], sample_weight=w[itr]).predict_proba(Xf[ite])[:, 1])
        models[name] = gbm().fit(Xf, yy, sample_weight=w)
    return models, oof
def terms_for(models, X):
    return np.c_[tuple(qlogit(models[n].predict_proba(X[fs].values.astype(float))[:, 1]) for n, fs in GROUPS)]
def train_set(val_rows, alpha):
    A = pd.concat([val_rows.assign(_g=val_rows.idx.astype(str)), TR.assign(_g="team_" + TR.spk)], ignore_index=True) if alpha > 0 else val_rows.assign(_g=val_rows.idx.astype(str))
    w = np.ones(len(A))
    if alpha > 0:
        nv = len(val_rows); w[nv:] = alpha * nv / (1 - alpha) / (len(A) - nv)
    return A, A.label.values, w
def run(alpha, write=False):
    # DiffSSD val, nested OOF
    o = np.zeros(len(df))
    for tr, te in folds:
        A, yy, w = train_set(df.iloc[tr], alpha)
        models, oof = fit_terms(A, yy, w, A._g.values)
        lin = lr(np.c_[A[FEATS].values, oof], yy, w)
        B = df.iloc[te]; o[te] = lin.decision_function(np.c_[B[FEATS].values, terms_for(models, B)])
    # held-out: fit on everything
    A, yy, w = train_set(df, alpha)
    models, oof = fit_terms(A, yy, w, A._g.values)
    lin = lr(np.c_[A[FEATS].values, oof], yy, w)
    h = lin.decision_function(np.c_[HO[FEATS].values, terms_for(models, HO)])
    out = {"alpha": alpha, **{f"val_{c}": min_dcf(o[df.cond.values == c], y[df.cond.values == c]) for c in CONDS}}
    lj = h[HO.set.values == "nsa_lj"]; thr = np.percentile(lj, 99)
    for st in ("team", "akash"):
        k = HO.set.values == st; s, yy2 = h[k], HO.label.values[k]
        out[f"{st}_minDCF"] = min_dcf(s, yy2); out[f"{st}_auc"] = roc_auc_score(yy2, s)
        out[f"{st}_fake_med"] = float(np.median(s[yy2 == 1])); out[f"{st}_real_med"] = float(np.median(s[yy2 == 0]))
        out[f"{st}_fakes>LJp99"] = float(np.mean(s[yy2 == 1] > thr)); out[f"{st}_reals>LJp99"] = float(np.mean(s[yy2 == 0] > thr))
    kc = (HO.set.values != "akash") & ((HO.label.values == 1) | (HO.set.values == "nsa_lj"))
    out["heldout_clones_vs_LJreals_minDCF"] = min_dcf(h[kc], HO.label.values[kc])
    out["lj_med"], out["lj_max"] = float(np.median(lj)), float(lj.max())
    out["weights"] = dict(zip(["dl_detector", "lfcc"] + [n for n, _ in GROUPS], np.round(lin.coef_[0], 3).tolist()))
    print(json.dumps(out), flush=True)
    if write:
        base = R / "data/release/v4p6"; outd = R / f"data/release/v4p6c_{alpha}"
        shutil.copytree(base, outd, dirs_exist_ok=True)
        blob = joblib.load(base / "fusion.joblib")
        for t in blob["terms"]:
            if t["type"] == "gbm": t["model"] = models[t["name"]]
        blob["weights"] = [float(v) for v in lin.coef_[0]]; blob["bias"] = float(lin.intercept_[0])
        blob["report_md"] = f"clone-aware refit (alpha {alpha}): " + json.dumps(out)
        blob["fit"] = {**blob.get("fit", {}), "date": datetime.date.today().isoformat(), "team_train_rows": int(len(TR)), "alpha": alpha}
        joblib.dump(blob, outd / "fusion.joblib")
        spec = json.load(open(outd / "hearsay.json")); spec["name"] = f"v4p6c_{alpha}"
        spec["fusion"]["sha256"] = sha256(outd / "fusion.joblib"); spec["weights"] = out["weights"]; spec["bias"] = float(lin.intercept_[0])
        json.dump(spec, open(outd / "hearsay.json", "w"), indent=2); (outd / "REPORT.md").write_text(blob["report_md"] + "\n")
        print("wrote", outd)
    # baseline check: the shipped v4p6 on the same held-out rows
if "--write" in sys.argv:
    run(float(sys.argv[sys.argv.index("--write") + 1]), write=True)
else:
    k = HO.set.values
    for st in ("team", "akash"):
        m = k == st; print(f"v4p6 shipped {st}: minDCF {min_dcf(HO.llr_v4p6.values[m], HO.label.values[m]):.3f} AUC {roc_auc_score(HO.label.values[m], HO.llr_v4p6.values[m]):.3f}")
    for a in (0.0, 0.05, 0.15, 0.3):
        run(a)
