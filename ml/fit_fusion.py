"""Fit hearsay fusion (neural score + prosody) on DiffSSD validation and write a release folder.

Run on the training PC after scoring validation with the final checkpoint:
  python ml/fit_fusion.py --v3-scores data/checkpoints/v3_diffssd/val_scores_<ep>.npz \
      --prosody results/pitch_v3val.csv --checkpoint data/checkpoints/v3_diffssd/best.pt \
      --backbone-config data/release/v2e/backbone_config --out data/release/v3p

Data: data/splits/v3_val.csv (4,523 clips: LJ Speech + LibriSpeech real, 7 DiffSSD generators) in three
versions each: clean, ffmpeg atempo stretch + noise, librosa phase-vocoder stretch + noise.
The three versions of a clip always share a CV fold. Reported numbers are out-of-fold. Validation only:
nothing here touches DiffSSD test or the NSA hold-out set."""
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
from hearsay.analyzers.dl_detector import sha256  # noqa: E402
from hearsay.analyzers.prosody import FEATURES as PROSODY  # noqa: E402

CONDS = ("clean", "atempo", "pv")


def min_dcf(s, y, p=0.3, cfp=4.0):
    o = np.argsort(-s)
    y = y[o]
    P, N = y.sum(), (1 - y).sum()
    tp = np.concatenate([[0], np.cumsum(y)])
    fp = np.concatenate([[0], np.cumsum(1 - y)])
    dcf = p * (1 - tp / P) + cfp * (1 - p) * fp / N
    return float(dcf.min() / min(p, cfp * (1 - p)))


QCLIP = 3.0  # bound on the prosody model's logit, so prosody can shift a score but never dominate it


def gbm(n_feats, monotonic_first=False):
    cst = [1] + [0] * (n_feats - 1) if monotonic_first else None
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                          l2_regularization=1.0, monotonic_cst=cst, random_state=0)


def platt(z, y):
    lr = LogisticRegression(class_weight="balanced", C=1e6, max_iter=1000).fit(z.reshape(-1, 1), y)
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def qlogit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.clip(np.log(p / (1 - p)), -QCLIP, QCLIP)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v3-scores", required=True)
    ap.add_argument("--prosody", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--backbone-config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="v3p")
    a = ap.parse_args()

    z = np.load(a.v3_scores)
    df = pd.read_csv(a.prosody)
    df["v3"] = [z[c][i] for c, i in zip(df.cond, df.idx)]
    feats = ["v3"] + PROSODY
    for f in PROSODY:
        if f not in df:
            df[f] = np.nan
    X, y, g = df[feats].values.astype(float), df.label.values, df.idx.values

    Xp, v3 = df[PROSODY].values.astype(float), df.v3.values
    folds = list(StratifiedGroupKFold(5, shuffle=True, random_state=0).split(X, y, g))

    # (reference only) one GBM on v3 + prosody. Strong in-domain, but it flattens v3's ranking wherever v3 is
    # confidently "real" (no validation fakes live there), which is exactly where new voices land.
    ref_oof = np.zeros(len(df))
    for tr, te in folds:
        ref_oof[te] = gbm(len(feats), True).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]

    # shipped: additive fusion. LLR = w_v3 * v3 + w_p * q + b, q = clipped logit of a prosody-only GBM.
    # Additive in v3, so the neural ranking is preserved everywhere; prosody shifts it by a bounded amount.
    q = np.zeros(len(df))
    for tr, te in folds:
        q[te] = qlogit(gbm(len(PROSODY)).fit(Xp[tr], y[tr]).predict_proba(Xp[te])[:, 1])
    Z = np.c_[v3, q]
    llr_f = np.zeros(len(df))
    for tr, te in folds:
        m = LogisticRegression(class_weight="balanced", C=1e6, max_iter=1000).fit(Z[tr], y[tr])
        llr_f[te] = m.decision_function(Z[te])
    lin = LogisticRegression(class_weight="balanced", C=1e6, max_iter=1000).fit(Z, y)
    w = [float(lin.coef_[0, 0]), float(lin.coef_[0, 1]), float(lin.intercept_[0])]
    assert w[0] > 0 and w[1] > 0, f"unexpected fusion weights {w}"
    pv = platt(v3, y)

    lines = ["| condition | v3 alone | v3 + prosody, additive (shipped) | v3 + prosody, one GBM (reference) | "
             "reals 'likely real' @50% prior | fakes 'likely synthetic' @50% prior |", "|---|---|---|---|---|---|"]
    for c in CONDS:
        k = df.cond.values == c
        post = 1 / (1 + np.exp(-np.clip(llr_f[k], -4.6, 4.6)))
        lines.append(f"| {c} | {min_dcf(v3[k], y[k]):.3f} | {min_dcf(llr_f[k], y[k]):.3f} | "
                     f"{min_dcf(ref_oof[k], y[k]):.3f} | {(post[y[k] == 0] <= 0.25).mean():.1%} | "
                     f"{(post[y[k] == 1] >= 0.75).mean():.1%} |")
    lines.append(f"\nweights: LLR = {w[0]:.3f} * v3 + {w[1]:.3f} * q + {w[2]:.3f}  (q = prosody logit, clipped to ±{QCLIP})")
    report = "\n".join(lines)
    print(report)

    final = gbm(len(PROSODY)).fit(Xp, y)
    ref = df[(df.cond == "clean") & (df.label == 0)][PROSODY].median().to_dict()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    blob = {"kind": "additive", "features": PROSODY, "prosody_gbm": final, "weights": w, "qclip": QCLIP,
            "platt_v3": pv, "prosody_ref": ref,
            "report_md": report, "sklearn": sklearn.__version__,
            "fit": {"date": datetime.date.today().isoformat(), "rows": int(len(df)), "v3_scores": a.v3_scores}}
    joblib.dump(blob, out / "fusion.joblib")
    ck = out / "v3.pt"
    if ck.exists():
        ck.unlink()
    shutil.copy2(a.checkpoint, ck)  # a copy, never a hardlink: training rewrites best.pt in place
    shutil.copytree(a.backbone_config, out / "backbone_config", dirs_exist_ok=True)
    spec = {"name": a.name, "release": datetime.date.today().isoformat(),
            "detector": {"checkpoint": "v3.pt", "sha256": sha256(ck), "backbone_config": "backbone_config"},
            "fusion": {"file": "fusion.joblib", "sha256": sha256(out / "fusion.joblib")},
            "weights": w, "platt_v3": pv}
    json.dump(spec, open(out / "hearsay.json", "w"), indent=2)
    (out / "REPORT.md").write_text(report + "\n")
    print(f"wrote {out}: {json.dumps(spec, indent=2)}")


if __name__ == "__main__":
    main()
