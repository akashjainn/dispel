import pandas as pd, numpy as np, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "hackgt/dispel_pr8fix")); from ml.fit_fusion import min_dcf
from sklearn.mixture import GaussianMixture
H = Path.home() / "hackgt/results/evalbundle"
A = pd.read_csv(H / "lap_ad_xlsr1b.csv"); A["v4"] = pd.read_csv(H / "lap_v4.csv").v4; A["mms"] = pd.read_csv(H / "lap_ad_mms300m.csv").ad_mms300m
real = A[A.set == "v5c_vctk_real"]
fams = {"dfadd": A[A.set == "v5c_dfadd"], "diffssd": A[(A.set == "diffssd_test_holdout") & (A.label == 1)], "commercial": A[A.set == "v5c_commercial"],
        "el_mixed": A[A.set == "v5c_el"], "team_clones": A[(A.set == "team_heldout") & (A.label == 1)], "mlaad_new": A[A.set == "v5c_mlaad_new"]}
z = lambda c, x: (x - real[c].mean()) / real[c].std()
A["ens_ad1b_v4"] = (z("ad_xlsr1b", A.ad_xlsr1b) + z("v4", A.v4)) / 2
real = A[A.set == "v5c_vctk_real"]
for c in ("v4", "ad_xlsr1b", "mms", "ens_ad1b_v4"):
    out = []
    for k, f in fams.items():
        f = A.loc[f.index]; out.append(f"{k} {min_dcf(np.r_[f[c], real[c]], np.r_[np.ones(len(f)), np.zeros(len(real))]):.3f}")
    T = A[A.set == "NSA_TEST"][c].values.reshape(-1, 1)
    g = GaussianMixture(2, random_state=0).fit(T); mu = g.means_.ravel(); hiw = g.weights_[np.argmax(mu)]
    print(f"{c:12s} VCTK-reals vs: " + " | ".join(out) + f" || NSA-test GMM: fake-comp weight {hiw:.2f}, means {np.round(np.sort(mu),1)}")
