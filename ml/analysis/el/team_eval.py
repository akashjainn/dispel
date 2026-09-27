import sys, numpy as np, pandas as pd, soundfile as sf
from pathlib import Path
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from ml.fit_fusion import min_dcf
from sklearn.metrics import roc_auc_score
D = R / "data/consent/team"
def llr(p): p = p.clip(1e-9, 1 - 1e-9); return 10 * np.log(p / (1 - p))
t = pd.concat([pd.read_csv(D / f"v4p6_{k}.tsv", sep="\t").assign(kind=k) for k in ("real", "fake")])
t["llr"] = llr(t["cm-score"]); t["spk"] = t.filename.str.rsplit("_", n=1).str[0]; t["n"] = t.filename.str.rsplit("_", n=1).str[1].str[:2]
t["dur"] = [sf.info(D / k / f).duration for k, f in zip(t.kind, t.filename)]
y = (t.kind == "fake").astype(int).values
print(f"200 clips (10 speakers x 10 pairs): minDCF {min_dcf(t.llr.values, y):.3f}  AUC {roc_auc_score(y, t.llr):.3f}")
print(f"LLR>0 (called synthetic): fakes {np.mean(t.llr[y==1] > 0):.2f}, reals {np.mean(t.llr[y==0] > 0):.2f}")
p = t.pivot_table(index=["spk", "n"], columns="kind", values="llr").dropna()
print(f"paired: fake > its real in {np.mean(p.fake > p.real):.2f} of {len(p)} pairs")
print(t.groupby(["spk", "kind"]).llr.median().unstack().round(1).assign(auc=[roc_auc_score((g.kind == "fake").astype(int), g.llr) for _, g in t.groupby("spk")]).to_string())
print("duration median real %.2f fake %.2f; corr(llr, dur) within real %.2f within fake %.2f" % (t.dur[y==0].median(), t.dur[y==1].median(), np.corrcoef(t.llr[y==0], t.dur[y==0])[0,1], np.corrcoef(t.llr[y==1], t.dur[y==1])[0,1]))
