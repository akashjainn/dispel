"""Fused v4p6 on 1,600 NSA-like short crops (400 per condition, same crops as cond_control.py/shortclip_eval.py):
current windowing (tile < 4 s, first 4 s otherwise) vs native (whole clip, one window) for the neural terms.
Caveat: the GBM terms were fit on the full-length versions of these val clips (in-sample), so absolute numbers are
optimistic; the tile-vs-native comparison is the point. Metric: NSA instructions (P(synth) .3, FA on real costs 4)."""
import sys, csv
from pathlib import Path
import numpy as np, pandas as pd, torch
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from hearsay.analyzers.dl_detector import Detector, CROP
from hearsay.analyzers.lfcc import LCNN, SEG
from hearsay.fusion import Fusion
from ml.fit_fusion import min_dcf
exec(open(R / "scratch/eval/cond_control.py").read().split("def job")[0].split("CONDS =")[1].join(["CONDS =", ""]) if False else "")
durs = np.load(R / "results/nsa_test_durations.npy")
def crop(c, i):
    x = np.load(R / f"data/eval_cache/v3_val/{c}/{i}.npy").astype(np.float32)
    rng = np.random.default_rng([99, int(i)]); d = int(float(rng.choice(durs)) * 16000)
    s0 = int(rng.integers(0, max(1, len(x) - d + 1))); y = x[s0:s0 + d]; return y / (np.abs(y).max() + 1e-9)
F = pd.read_csv(R / "results/cond_control_short.csv")
lab = pd.read_csv(R / "data/splits/v3_val.csv").label.values; y = lab[F.idx.values]
net = Detector(R / "data/release/v4p6/backbone_config")
net.load_state_dict(torch.load(R / "data/release/v4p6/v3.pt", map_location="cpu", weights_only=False)["model"]); net = net.cuda().eval()
lfs = {}
for n, p in (("lfcc1", "scratch/lfcc_eval/lfcc1_best.pt"), ("lfcc2", "scratch/lfcc_eval/lfcc2_best.pt")):
    m = LCNN(); m.load_state_dict(torch.load(R / p, map_location="cpu", weights_only=False)["model"]); m.eval(); lfs[n] = m
nat, l2t, l1n, l2n = [], [], [], []
for c, i in zip(F.cond, F.idx):
    x = crop(c, i); t = np.tile(x, CROP // len(x) + 1)[:CROP] if len(x) < CROP else x[:CROP]
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        lg = net(torch.from_numpy(x)[None].cuda()).float(); nat.append((lg[0, 1] - lg[0, 0]).item())
    with torch.inference_mode():
        lg = lfs["lfcc2"](torch.from_numpy(t)[None]); l2t.append((lg[0, 1] - lg[0, 0]).item())
        try:
            lg = lfs["lfcc1"](torch.from_numpy(x)[None]); l1n.append((lg[0, 1] - lg[0, 0]).item())
            lg = lfs["lfcc2"](torch.from_numpy(x)[None]); l2n.append((lg[0, 1] - lg[0, 0]).item())
        except Exception as e:
            l1n.append(np.nan); l2n.append(np.nan)
F["v4_tile"], F["v4_native"], F["lfcc1_tile"], F["lfcc2_tile"], F["lfcc1_native"], F["lfcc2_native"] = F.v3, nat, F.lfcc, l2t, l1n, l2n
F.to_csv(R / "results/short_fused_inputs.csv", index=False)
feats = [c for c in F.columns if c not in ("cond", "idx")]
def fused(fz, dl, lf):
    out = []
    for _, r in F.iterrows():
        d = {k: r[k] for k in feats}; d["v3"], d["lfcc"] = r[dl], r[lf]; out.append(fz.fuse(d)["llr_raw"])
    return np.array(out)
rows = {"v4 alone tile": F.v4_tile.values, "v4 alone native": F.v4_native.values}
fz6 = Fusion(R / "data/release/v4p6/fusion.joblib")
rows["v4p6 fused tile/tile (current)"] = fused(fz6, "v4_tile", "lfcc1_tile")
rows["v4p6 fused native/tile"] = fused(fz6, "v4_native", "lfcc1_tile")
if np.isfinite(F.lfcc1_native).all(): rows["v4p6 fused native/native"] = fused(fz6, "v4_native", "lfcc1_native")
p7 = R / "data/release/v4p7cand/fusion.joblib"
if p7.exists():
    fz7 = Fusion(p7)
    rows["v4p7 fused tile/tile"] = fused(fz7, "v4_tile", "lfcc2_tile")
    rows["v4p7 fused native/tile"] = fused(fz7, "v4_native", "lfcc2_tile")
    if np.isfinite(F.lfcc2_native).all(): rows["v4p7 fused native/native"] = fused(fz7, "v4_native", "lfcc2_native")
C = ["clean", "atempo", "rubberband", "pv"]
print(f"{'system':32s} " + " ".join(f"{c:>10s}" for c in C) + "     pooled")
for n, s in rows.items():
    print(f"{n:32s} " + " ".join(f"{min_dcf(s[F.cond.values == c], y[F.cond.values == c]):10.3f}" for c in C) + f" {min_dcf(s, y):10.3f}")
