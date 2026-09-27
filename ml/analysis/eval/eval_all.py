"""Neural-only comparison of checkpoints on everything NSA-like we have, excluding anything a candidate trained on
(teammates in the v5 train fold, and their clones / voice-changer outputs). Production windowing.
python eval_all.py name=ckpt ...  -> results/eval_all_scores.csv (cached per checkpoint) + results/eval_all.md"""
import csv, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd, torch
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from hearsay.analyzers.dl_detector import Detector, windows
from hearsay import audio as A
from ml.fit_fusion import min_dcf
from sklearn.metrics import roc_auc_score
train_spk = {r["spk"] for r in csv.DictReader(open(R / "data/splits/v5_team.csv")) if r["split"] == "train"}
spk_of = lambda stem: stem.rsplit("_", 1)[0]
I = []
M = pd.read_csv(R / "evalbundle/manifest.csv")
for r in M.itertuples(): I.append((r.set if r.set != "libri_clone" else f"libri_clone_{r.detail}", r.label, str(R / "evalbundle" / r.file)))
for r in csv.DictReader(open(R / "data/el_matrix/meta.csv")):
    av = r["avenue"]
    if av == "isolator_real" and spk_of(r["text_id"]) in train_spk: continue
    I.append(("EL_" + av, int(r["label"]), str(R / r["file"])))
for r in csv.DictReader(open(R / "data/consent/sts/meta.csv")):
    s = Path(r["src"]).stem
    if spk_of(s) in train_spk: continue
    I.append(("EL_voice_changer", 1, str(R / r["file"])))
seen = set()
for r in csv.DictReader(open(R / "data/el_extra/meta.csv")):
    if r["file"] in seen or r["split"] != "eval": continue
    seen.add(r["file"]); I.append(("EL_isolator_real_extra", int(r["label"]), str(R / r["file"])))
for r in csv.DictReader(open(R / "data/el_stock/meta.csv")): I.append(("EL_stock_tts", 1, str(R / r["file"])))
S = pd.DataFrame(I, columns=["set", "label", "path"])
cp = R / "results/eval_all_scores.csv"
if cp.exists():
    old = pd.read_csv(cp); S = S.merge(old.drop(columns=["set", "label"]), on="path", how="left")
def load(p):
    p = Path(p)
    if p.suffix in (".pcm", ".ulaw"):
        tmp = Path(tempfile.gettempdir()) / (p.parent.name + p.stem + "_c.wav")
        a = ["-f", "s16le", "-ar", "16000", "-ac", "1"] if p.suffix == ".pcm" else ["-f", "mulaw", "-ar", "8000", "-ac", "1"]
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *a, "-i", str(p), str(tmp)], check=True); p = tmp
    return A.load(str(p))[0]
X = [load(p) for p in S.path]
for arg in sys.argv[1:]:
    n, ck = arg.split("=", 1)
    if n in S and S[n].notna().all(): continue
    if ck.startswith("ad:"):
        sys.path.insert(0, str(R / "scratch/eval")); from antideepfake import AntiDeepfake
        net = AntiDeepfake(ck[3:]).cuda().eval(); sc = [net.score(x[:16000 * 20]) for x in X]
        S[n] = sc; del net; torch.cuda.empty_cache(); S.to_csv(cp, index=False); print("scored", n, flush=True); continue
    net = Detector(R / "data/release/v4p6/backbone_config"); net.load_state_dict(torch.load(ck, map_location="cpu", weights_only=False)["model"]); net = net.cuda().eval()
    sc = []
    for x in X:
        w, _ = windows(x)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            lg = net(torch.from_numpy(w).cuda()).float()
        sc.append(float((lg[:, 1] - lg[:, 0]).mean()))
    S[n] = sc; del net; torch.cuda.empty_cache(); S.to_csv(cp, index=False); print("scored", n, flush=True)
names = [a.split("=")[0] for a in sys.argv[1:]]
if False: S["avg_v4_v5b"] = S[[c for c in names if c in ("v4", "v5b_ep2")]].mean(1) if {"v4", "v5b_ep2"} <= set(names) else np.nan
cols = names
REAL = ["nsa_lj_real", "team_heldout", "akash"]
realpool = S[(S.label == 0) & S.set.isin(REAL + ["diffssd_test_holdout", "libri_clone_real"])]
lines = ["| set | n | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
fakes = sorted(S[S.label == 1].set.unique())
for st in fakes:
    g = S[(S.set == st) & (S.label == 1)]
    vals = []
    for c in cols:
        y = np.r_[np.ones(len(g)), np.zeros(len(realpool))]; vals.append(f"{min_dcf(np.r_[g[c], realpool[c]], y):.3f}")
    lines.append(f"| {st} (fake) vs real pool | {len(g)} | " + " | ".join(vals) + " |")
lj = S[S.set == "nsa_lj_real"]
for st in ["team_heldout", "akash", "EL_isolator_real", "EL_isolator_real_extra", "libri_clone_real", "diffssd_test_holdout"]:
    g = S[(S.set == st) & (S.label == 0)]
    if len(g): lines.append(f"| {st} REALS flagged @ NSA-LJ 1% FA | {len(g)} | " + " | ".join(f"{np.mean(g[c] > np.percentile(lj[c], 99)):.2f}" for c in cols) + " |")
allf = S[S.label == 1]; y = np.r_[np.ones(len(allf)), np.zeros(len(realpool))]
lines.append(f"| ALL fakes vs real pool | {len(allf)} | " + " | ".join(f"{min_dcf(np.r_[allf[c], realpool[c]], y):.3f}" for c in cols) + " |")
iso = S[S.set.str.startswith("EL_isolator") | S.set.isin(REAL + ["diffssd_test_holdout", "libri_clone_real"])]
iso = iso[iso.label == 0]; y = np.r_[np.ones(len(allf)), np.zeros(len(iso))]
lines.append(f"| ALL fakes vs real pool + isolator reals | {len(allf)}/{len(iso)} | " + " | ".join(f"{min_dcf(np.r_[allf[c], iso[c]], y):.3f}" for c in cols) + " |")
(R / "results/eval_all.md").write_text("\n".join(lines) + "\n"); print("\n".join(lines))
