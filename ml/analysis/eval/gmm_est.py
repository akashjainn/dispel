"""Unsupervised check: fit a 2-component GMM to each system's NSA-test scores, treat the component posteriors as soft
labels, and compute the expected minDCF of that system's ranking. Validate on the interim: v4p6 fused scored 0.258."""
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.mixture import GaussianMixture
H = Path.home() / "hackgt"; E = H / "results/evalbundle"
A = pd.read_csv(E / "lap_ad_xlsr1b.csv"); A["v4"] = pd.read_csv(E / "lap_v4.csv").v4; A["mms"] = pd.read_csv(E / "lap_ad_mms300m.csv").ad_mms300m
T = A[A.set == "NSA_TEST"].copy()
d = pd.read_csv(H / "submissions/HearsayScoreKey4Gemini.tsv", sep="\t"); p = d["cm-score"].clip(1e-9, 1 - 1e-9); d["v4p6_fused"] = np.log(p / (1 - p))
T = T.merge(d[["filename", "v4p6_fused"]], left_on="file", right_on="filename")
def soft_dcf(s, q, P=0.3, C=4.0):
    o = np.argsort(-s); q = q[o]; Pf, Pr = q.sum(), (1 - q).sum()
    tp = np.r_[0, np.cumsum(q)]; fp = np.r_[0, np.cumsum(1 - q)]
    return float((P * (1 - tp / Pf) + C * (1 - P) * fp / Pr).min() / min(P, C * (1 - P)))
rv = T[["v4", "ad_xlsr1b", "mms"]]
T["ens"] = ((T.v4 - T.v4.median()) / T.v4.std() + (T.ad_xlsr1b - T.ad_xlsr1b.median()) / T.ad_xlsr1b.std()) / 2
for c in ("v4p6_fused", "v4", "ad_xlsr1b", "mms", "ens"):
    s = T[c].values; g = GaussianMixture(2, random_state=0, n_init=3).fit(s.reshape(-1, 1)); hi = np.argmax(g.means_.ravel())
    q = g.predict_proba(s.reshape(-1, 1))[:, hi]
    # cross-check: soft labels from the OTHER strongest model (ad_xlsr1b) - avoids a model grading itself
    g2 = GaussianMixture(2, random_state=0, n_init=3).fit(T.ad_xlsr1b.values.reshape(-1, 1)); hi2 = np.argmax(g2.means_.ravel())
    q2 = g2.predict_proba(T.ad_xlsr1b.values.reshape(-1, 1))[:, hi2]
    print(f"{c:11s} own-GMM est minDCF {soft_dcf(s, q):.3f} (fake share {q.mean():.2f}) | graded by AD1b GMM {soft_dcf(s, q2):.3f}")
