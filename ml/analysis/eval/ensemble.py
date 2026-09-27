"""Pick the final network(s) on a family-balanced held-out proxy, then write the NSA TSV.
Inputs: results/evalbundle/{pc,lap}_<model>.csv (same row order: manifest.csv, manifest2.csv, NSA test sorted).
Proxy minDCF (instructions' cost) with every fake family and every real family given equal weight inside its class,
so 2,000 DiffSSD clips don't drown 14 of Akash's. Ensembles = mean of per-model z-scores (z from the real pool).
python ensemble.py [--write name] -> results/ensemble.md (+ submissions/<name>.tsv)"""
import sys, glob, itertools
from pathlib import Path
import numpy as np, pandas as pd
H = Path.home() / "hackgt"
F = {}
for f in sorted(glob.glob(str(H / "results/evalbundle/pc_*.csv")) + glob.glob(str(H / "results/evalbundle/lap_*.csv"))):
    n = Path(f).stem.split("_", 1)[1]; d = pd.read_csv(f)
    if n not in F: F[n] = d
base = next(iter(F.values()))[["set", "label"]].copy()
for n, d in F.items():
    assert len(d) == len(base) and (d.set.values == base.set.values).all(), n
    base[n] = d[n].values
def fam(s, y):
    m = {"team_heldout": "team", "akash": "team", "v5c_team_real": "team", "nsa_lj_real": "lj", "diffssd_test_holdout": "diffssd",
         "libri_clone_real": "libri", "v5c_talkingface": "talkingface", "v5c_ups": "ups", "v5c_vctk_real": "vctk", "v5c_yt_real": "yt",
         "v5c_real_processed": "isolator", "EL_isolator_real": "isolator", "el_frontier": "el_tts", "libri_clone_f5": "oss_clone",
         "libri_clone_chatterbox": "oss_clone", "v5c_f5clone": "oss_clone", "v5c_el": "el_mixed", "v5c_commercial": "commercial",
         "v5c_mlaad_new": "mlaad_new_heldout_models", "v5c_dfadd": "dfadd"}
    f = m.get(s, s)
    if s in ("team_heldout", "akash") and y == 1: f = "el_clone_team"
    if s == "libri_clone": f = "oss_clone" if y == 1 else "libri"
    return f
B = base[base.set != "NSA_TEST"].copy(); T = base[base.set == "NSA_TEST"].copy()
B["fam"] = [fam(s, y) for s, y in zip(B.set, B.label)]
def wdcf(s, y, w, p=0.3, c=4.0):
    o = np.argsort(-s); y, w = y[o], w[o]; P, N = w[y == 1].sum(), w[y == 0].sum()
    tp = np.r_[0, np.cumsum(w * (y == 1))]; fp = np.r_[0, np.cumsum(w * (y == 0))]
    return float((p * (1 - tp / P) + c * (1 - p) * fp / N).min() / min(p, c * (1 - p)))
# isolator-cleaned reals: every model flags them (a known, separate failure); reported as a column, not in the proxy
ISO = (B.fam == "isolator").values
y = B.label.values; w = np.array([1.0 / (B.fam == f).sum() for f in B.fam]); w[ISO] = 0.0
models = list(F)
real = B.label.values == 0
Z = {n: (base[n] - base.loc[B.index[real], n].mean()) / (base.loc[B.index[real], n].std() + 1e-9) for n in models}
cands = {n: Z[n] for n in models}
for k in (2, 3):
    for c in itertools.combinations(models, k): cands["+".join(c)] = sum(Z[n] for n in c) / k
rows = []
for n, z in cands.items():
    s = z.loc[B.index].values
    r = {"system": n, "proxy_minDCF": wdcf(s, y, w)}
    for f in sorted(B.fam.unique()):
        k = (B.fam == f).values
        if B.label.values[k][0] == 1:   # fake family vs all reals (balanced)
            kk = k | real; r[f] = wdcf(s[kk], y[kk], w[kk])
    lj = s[(B.fam == "lj").values]; thr = np.percentile(lj, 99)
    for f in ("team", "isolator", "talkingface", "ups", "vctk", "yt", "diffssd", "libri"):
        k = ((B.fam == f) & (B.label == 0)).values
        if k.any(): r["FA@LJ1%_" + f] = float(np.mean(s[k] > thr))
    rows.append(r)
R = pd.DataFrame(rows).sort_values("proxy_minDCF").round(3)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
print(B.groupby(["fam", "label"]).size().to_string()); print(R.to_string(index=False))
(H / "results/ensemble.md").write_text(R.to_string(index=False) + "\n")
if "--write" in sys.argv:
    n = sys.argv[sys.argv.index("--write") + 1]; z = cands[n].loc[T.index].values
    files = F[next(iter(F))].loc[T.index, "file"].values
    tmpl = [l.rstrip("\n").split("\t")[0] for l in open(H / "submissions/HearsayScoreKey4TeamX.tsv")][1:]
    sc = dict(zip([Path(f).name for f in files], 1 / (1 + np.exp(-z / 3))))
    out = H / f"submissions/final_{n.replace('+', '_')}.tsv"
    with open(out, "w", newline="\n") as fh:
        fh.write("filename\tcm-score\n"); [fh.write(f"{t}\t{sc[t]:.8f}\n") for t in tmpl]
    print("wrote", out, "share>0.5", np.mean(np.array(list(sc.values())) > 0.5))
