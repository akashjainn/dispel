"""Fit hearsay fusion on DiffSSD validation and write a release folder (weights + fusion + manifest with sha256s).

Run on the training PC once the final checkpoints are scored on validation:
  python ml/fit_fusion.py --v3-scores data/checkpoints/v3_diffssd/val_scores_<ep>.npz \
      --lfcc-scores results/lfcc_val_scores.npz --prosody results/pitch_v3val.csv --feats results/feats3_v3val.csv \
      --checkpoint data/checkpoints/v3_diffssd/best.pt --lfcc-checkpoint <lfcc best.pt> \
      --backbone-config data/release/v2e/backbone_config --out data/release/v3p6 --name v3p6

Data: data/splits/v3_val.csv (4,523 clips: LJ Speech + LibriSpeech real, 7 DiffSSD generators) in three versions:
clean, ffmpeg atempo stretch + noise, librosa phase-vocoder stretch + noise. The versions of a clip share a CV fold.
Reported numbers are out-of-fold. Validation only: nothing touches DiffSSD test or the NSA hold-out set."""
import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hearsay.analyzers import prosody, rhythm, spectral, voice  # noqa: E402
from hearsay.analyzers.dl_detector import sha256  # noqa: E402

CONDS = ("clean", "atempo", "pv")
QCLIP = 3.0  # bound on each feature model's logit, so one analyzer can shift a score but never dominate it
GROUPS = [("prosody", prosody.FEATURES), ("spectral", spectral.FEATURES), ("voice", voice.FEATURES),
          ("rhythm", rhythm.FEATURES)]


def min_dcf(s, y, p=0.3, cfp=4.0):
    """Normalized minDCF for NSA's analyst scenario: y=1 synthetic, higher s = more synthetic, P(synthetic)=0.3,
    a false alarm on a real clip costs 4x a missed synthetic (NSA instructions)."""
    o = np.argsort(-s)
    y = y[o]
    P, N = y.sum(), (1 - y).sum()
    tp = np.concatenate([[0], np.cumsum(y)])
    fp = np.concatenate([[0], np.cumsum(1 - y)])
    dcf = p * (1 - tp / P) + cfp * (1 - p) * fp / N
    return float(dcf.min() / min(p, cfp * (1 - p)))


def gbm(n_feats=None):
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                          l2_regularization=1.0, random_state=0)


def qlogit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.clip(np.log(p / (1 - p)), -QCLIP, QCLIP)


def lr_fit(Z, y):
    return LogisticRegression(class_weight="balanced", C=1e6, max_iter=2000).fit(Z, y)


def main():
    ap = argparse.ArgumentParser()
    for k in ("--v3-scores", "--lfcc-scores", "--prosody", "--feats", "--checkpoint", "--lfcc-checkpoint",
              "--backbone-config", "--out"):
        ap.add_argument(k, required=True)
    ap.add_argument("--name", default="v3p6")
    a = ap.parse_args()

    df = pd.read_csv(a.prosody).merge(pd.read_csv(a.feats).drop(columns=["label", "group"]), on=["idx", "cond"])
    z3, zl = np.load(a.v3_scores), np.load(a.lfcc_scores)
    df["v3"] = [z3[c][i] for c, i in zip(df.cond, df.idx)]
    df["lfcc"] = [zl[c][i] for c, i in zip(df.cond, df.idx)]
    for _, fs in GROUPS:
        for f in fs:
            if f not in df:
                df[f] = np.nan
    y, g, cond = df.label.values, df.idx.values, df.cond.values
    folds = list(StratifiedGroupKFold(5, shuffle=True, random_state=0).split(df, y, g))

    Q = {}
    for name, fs in GROUPS:
        X, q = df[fs].values.astype(float), np.zeros(len(df))
        for tr, te in folds:
            q[te] = qlogit(gbm().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1])
        Q[name] = q
    names = ["dl_detector", "lfcc"] + [n for n, _ in GROUPS]
    Z = np.c_[tuple([df.v3.values, df.lfcc.values] + [Q[n] for n, _ in GROUPS])]

    def oof(cols):
        """Out-of-fold fused LLR with nested cross-fitting: for each outer fold, the analyzer GBMs that produce the
        fusion model's training features are fit by inner folds inside the outer training set only, and the outer
        test fold is scored by analyzers fit on the whole outer training set. No label from the outer test fold
        reaches either the analyzer terms or the fusion weights."""
        raw = [df.v3.values, df.lfcc.values]
        o = np.zeros(len(df))
        for tr, te in folds:
            tr_terms, te_terms = [r[tr] for r in raw], [r[te] for r in raw]
            inner = list(StratifiedGroupKFold(5, shuffle=True, random_state=1).split(tr, y[tr], g[tr]))
            for name, fs in GROUPS:
                X = df[fs].values.astype(float)
                qi = np.zeros(len(tr))
                for itr, ite in inner:
                    qi[ite] = qlogit(gbm().fit(X[tr][itr], y[tr][itr]).predict_proba(X[tr][ite])[:, 1])
                tr_terms.append(qi)
                te_terms.append(qlogit(gbm().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]))
            Ztr, Zte = np.c_[tuple(tr_terms)][:, cols], np.c_[tuple(te_terms)][:, cols]
            o[te] = lr_fit(Ztr, y[tr]).decision_function(Zte)
        return o

    systems = {"v3 alone": df.v3.values, "v3 + prosody + lfcc": oof([0, 1, 2]), "all 6 (shipped)": oof(list(range(6)))}
    lines = ["| system | " + " | ".join(CONDS) + " | reals 'likely real' @50% (librosa) | fakes 'likely synthetic' @50% (librosa) |",
             "|---|" + "---|" * (len(CONDS) + 2)]
    for n, s in systems.items():
        k = cond == "pv"
        post = 1 / (1 + np.exp(-np.clip(s[k], -4.6, 4.6)))
        extra = (f"{(post[y[k] == 0] <= 0.25).mean():.1%} | {(post[y[k] == 1] >= 0.75).mean():.1%}"
                 if n != "v3 alone" else "- | -")
        lines.append(f"| {n} | " + " | ".join(f"{min_dcf(s[cond == c], y[cond == c]):.3f}" for c in CONDS) + f" | {extra} |")
    lin = lr_fit(Z, y)
    w, b = [float(v) for v in lin.coef_[0]], float(lin.intercept_[0])
    assert all(v > 0 for v in w), f"a fusion weight is not positive: {dict(zip(names, w))}"
    lines.append("\nweights: " + ", ".join(f"{n} {v:.3f}" for n, v in zip(names, w)) + f", bias {b:.3f}; "
                 f"feature terms are clipped logits (±{QCLIP}) of per-analyzer gradient-boosted models")
    report = "\n".join(lines)
    print(report)

    terms = [{"name": "dl_detector", "type": "raw", "feature": "v3", "impute": float(np.median(df.v3))},
             {"name": "lfcc", "type": "raw", "feature": "lfcc", "impute": float(np.median(df.lfcc))}]
    for name, fs in GROUPS:
        terms.append({"name": name, "type": "gbm", "features": list(fs),
                      "model": gbm().fit(df[fs].values.astype(float), y)})
    realc = df[(df.cond == "clean") & (df.label == 0)]
    ref = {n: {**realc[fs].median().to_dict(),
               **{f + "__iqr": float(realc[f].quantile(.75) - realc[f].quantile(.25)) for f in fs}} for n, fs in GROUPS}
    ca = LogisticRegression(class_weight="balanced", C=1e6, max_iter=1000).fit(df[["v3"]].values, y)
    app_lin = lr_fit(Z[:, [0, 2]], y)
    app_blob = {"kind": "additive_v2", "terms": [terms[0], terms[2]], "weights": [float(v) for v in app_lin.coef_[0]],
                "bias": float(app_lin.intercept_[0]), "qclip": QCLIP}
    blob = {"kind": "additive_v2", "terms": terms, "weights": w, "bias": b, "qclip": QCLIP,
            "platt_v3": (float(ca.coef_[0, 0]), float(ca.intercept_[0])), "ref": ref,
            "prosody_ref": ref["prosody"], "report_md": report, "sklearn": sklearn.__version__,
            "fit": {"date": datetime.date.today().isoformat(), "rows": int(len(df)), "v3_scores": a.v3_scores,
                    "lfcc_scores": a.lfcc_scores}}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(blob, out / "fusion.joblib")
    for k in ("platt_v3", "ref", "prosody_ref", "sklearn", "fit"):
        app_blob[k] = blob[k]
    app_blob["report_md"] = "app profile: dl_detector + prosody only (robust on unfamiliar voices; see ml/README.md)"
    joblib.dump(app_blob, out / "fusion_app.joblib")
    shutil.copy2(a.checkpoint, out / "v3.pt")  # copies, never hardlinks: training rewrites best.pt in place
    shutil.copy2(a.lfcc_checkpoint, out / "lfcc.pt")
    shutil.copytree(a.backbone_config, out / "backbone_config", dirs_exist_ok=True)
    spec = {"name": a.name, "release": datetime.date.today().isoformat(),
            "detector": {"checkpoint": "v3.pt", "sha256": sha256(out / "v3.pt"), "backbone_config": "backbone_config"},
            "lfcc": {"checkpoint": "lfcc.pt", "sha256": sha256(out / "lfcc.pt")},
            "fusion": {"file": "fusion.joblib", "sha256": sha256(out / "fusion.joblib")},
            "fusion_app": {"file": "fusion_app.joblib", "sha256": sha256(out / "fusion_app.joblib")},
            "weights": dict(zip(names, w)), "bias": b}
    json.dump(spec, open(out / "hearsay.json", "w"), indent=2)
    (out / "REPORT.md").write_text(report + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
