"""Held-out evaluation for v5 candidates vs v4 (neural term only, production windowing from hearsay.dl_detector).
Sets: held-out teammates (real / provided clone / generated clone), Akash (own recording + his clone; never in training),
ElevenLabs frontier test clips, NSA LJRealResampled reals, F5 + Chatterbox paired clones (eval speakers, clean).
Usage: python eval_v5.py <name>=<checkpoint> [...]   -> results/eval_v5.csv (appends) + printed summary"""
import csv, sys
from pathlib import Path
import numpy as np, pandas as pd, torch
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from hearsay.analyzers.dl_detector import Detector, windows
from hearsay import audio as A
from ml.fit_fusion import min_dcf
from sklearn.metrics import roc_auc_score
sets = []
t = pd.read_csv(R / "data/splits/v5_team.csv"); t = t[t.split == "eval"]
for _, r in t.iterrows(): sets.append(("team_heldout", r.label, str(R / "data" / r.path), r.detail))
for p in sorted((R / "data/consent/akash/real").glob("*.wav")): sets.append(("akash", 0, str(p), "real"))
for p in sorted((R / "data/consent/akash/fake").glob("*/*.mp3")): sets.append(("akash", 1, str(p), p.parent.name))
for p in sorted((R / "data/el_frontier").rglob("*.mp3")): sets.append(("el_frontier", 1, str(p), ""))
for p in sorted((R / "data/nsa/LJRealResampled/resampled").glob("*.wav")): sets.append(("nsa_lj_real", 0, str(p), ""))
plan = pd.read_csv(R / "data/clonesrc/plan.csv"); ev = set(plan.uid[plan.split == "eval"])
for k in ("f5", "chatterbox", "real"):
    for p in sorted((R / f"data/clones16/{k}/clean").glob("*.wav")):
        if p.stem in ev: sets.append(("libri_clone", int(k != "real"), str(p), k))
S = pd.DataFrame(sets, columns=["set", "label", "path", "detail"])
cache = {}
def load(p):
    if p not in cache: cache[p] = A.load(p)[0]
    return cache[p]
out = []
for arg in sys.argv[1:]:
    name, ck = arg.split("=", 1)
    net = Detector(R / "data/release/v4p6/backbone_config")
    net.load_state_dict(torch.load(ck, map_location="cpu", weights_only=False)["model"]); net = net.cuda().eval()
    sc = []
    for p in S.path:
        w, _ = windows(load(p))
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            lg = net(torch.from_numpy(w).cuda()).float()
        sc.append(float((lg[:, 1] - lg[:, 0]).mean()))
    S[name] = sc; del net; torch.cuda.empty_cache()
S.to_csv(R / "results/eval_v5_scores.csv", index=False)
names = [a.split("=")[0] for a in sys.argv[1:]]
lj = S[S.set == "nsa_lj_real"]
for n in names:
    print(f"\n== {n}")
    thr = np.percentile(lj[n], 99)   # operating point: 1% of NSA's LJ reals flagged
    for st in ("team_heldout", "akash", "libri_clone"):
        d = S[S.set == st]; y = d.label.values
        print(f"{st:13s} n={len(d):4d} minDCF {min_dcf(d[n].values, y):.3f} AUC {roc_auc_score(y, d[n]):.3f} | med real {d[n][y==0].median():+.1f} fake {d[n][y==1].median():+.1f} | fakes > LJ-p99 {np.mean(d[n][y==1] > thr):.2f}, reals > LJ-p99 {np.mean(d[n][y==0] > thr):.2f}")
    fr = S[S.set == "el_frontier"][n]
    print(f"el_frontier   n={len(fr):4d} med {fr.median():+.1f} | > LJ-p99 {np.mean(fr > thr):.2f} | vs NSA LJ reals: minDCF {min_dcf(np.r_[fr, lj[n]], np.r_[np.ones(len(fr)), np.zeros(len(lj))]):.3f}")
    print(f"nsa_lj_real   n={len(lj):4d} med {lj[n].median():+.1f} p99 {thr:+.1f} max {lj[n].max():+.1f}")
