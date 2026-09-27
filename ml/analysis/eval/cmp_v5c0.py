import numpy as np, pandas as pd, sys
from pathlib import Path
from sklearn.mixture import GaussianMixture
sys.path.insert(0, str(Path.home() / "hackgt/dispel_pr8fix")); from ml.fit_fusion import min_dcf
E = Path.home() / "hackgt/results/evalbundle"
A = pd.read_csv(E / "lap_ad_xlsr1b.csv")
for n, f in (("v4", "lap_v4.csv"), ("mms", "lap_ad_mms300m.csv"), ("v5c0", "lap_v5c_ep0.csv")): A[n] = pd.read_csv(E / f).iloc[:, 3]
real = A[A.set == "v5c_vctk_real"]
fams = {"dfadd": A.set == "v5c_dfadd", "diffssd": (A.set == "diffssd_test_holdout") & (A.label == 1), "commercial": A.set == "v5c_commercial",
        "el_mixed": A.set == "v5c_el", "team_clones": (A.set == "team_heldout") & (A.label == 1), "akash_clone": (A.set == "akash") & (A.label == 1),
        "mlaad_new(heldout models)": A.set == "v5c_mlaad_new", "el_frontier": A.set == "el_frontier"}
for c in ("v4", "v5c0", "ad_xlsr1b"):
    print(c, " | ".join(f"{k} {min_dcf(np.r_[A[m][c], real[c]], np.r_[np.ones(m.sum()), np.zeros(len(real))]):.3f}" for k, m in fams.items()))
    for s in ("nsa_lj_real", "v5c_talkingface", "team_heldout", "v5c_yt_real", "v5c_ups", "diffssd_test_holdout"):
        d = A[(A.set == s) & (A.label == 0)][c]; print(f"     reals {s:22s} > VCTK p99: {np.mean(d > np.percentile(real[c], 99)):.2f}")
T = A[A.set == "NSA_TEST"]
for c in ("v4", "v5c0", "ad_xlsr1b"):
    s = T[c].values.reshape(-1, 1); g = GaussianMixture(2, random_state=0, n_init=3).fit(s); print(c, "NSA GMM fake share", round(g.weights_[np.argmax(g.means_)], 3), "means", np.round(np.sort(g.means_.ravel()), 1), "q10/50/70/90", np.round(np.percentile(s, [10, 50, 70, 90]), 1))
m = (T.ad_xlsr1b < 0) & (T.v4 > 0); print("disputed 204: v5c0 median", round(T[m].v5c0.median(), 1), " v5c0>0:", round((T[m].v5c0 > 0).mean(), 2))
