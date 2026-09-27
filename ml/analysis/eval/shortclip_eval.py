"""NSA test clips are short (median 3.4 s; most < 4 s) and peak-normalized. Our pipeline tiles clips < 4 s up to one
4 s window. Does that hurt? Build test-like DiffSSD val: take each val clip (clean / atempo / pv cache), crop to a
duration drawn from the NSA test duration distribution (seeded per clip), peak-normalize, then score v4 with
(a) tile to 4 s (current), (b) the clip's native length, one window, (c) zero-pad to 4 s. Evaluation only."""
import csv, sys
from pathlib import Path
import numpy as np, torch
R = Path.home() / "hackgt"
sys.path.insert(0, str(R / "dispel_pr8fix"))
from hearsay.analyzers.dl_detector import Detector, CROP
from ml.fit_fusion import min_dcf
from sklearn.metrics import roc_auc_score
val = list(csv.DictReader(open(R / "data/splits/v3_val.csv"))); y = np.array([int(r["label"]) for r in val])
durs = np.load(R / "results/nsa_test_durations.npy")
net = Detector(R / "data/release/v4p6/backbone_config")
net.load_state_dict(torch.load(R / "data/checkpoints/v4/best.pt", map_location="cpu", weights_only=False)["model"])
net = net.cuda().eval()
@torch.inference_mode()
def score(batch):  # list of 1-D arrays, equal length within call
    x = torch.from_numpy(np.stack(batch)).cuda()
    with torch.autocast("cuda", dtype=torch.bfloat16):
        lg = net(x).float()
    return (lg[:, 1] - lg[:, 0]).cpu().numpy()
out = {}
for cond in ("clean", "atempo", "pv"):
    S = {m: np.zeros(len(val)) for m in ("tile", "native", "pad", "full")}
    for i in range(len(val)):
        x = np.load(R / f"data/eval_cache/v3_val/{cond}/{i}.npy").astype(np.float32)
        rng = np.random.default_rng([99, i])
        d = int(float(rng.choice(durs)) * 16000)
        s0 = int(rng.integers(0, max(1, len(x) - d + 1))); c = x[s0:s0 + d]
        c = c / (np.abs(c).max() + 1e-9)
        t = np.tile(c, CROP // len(c) + 1)[:CROP] if len(c) < CROP else c[:CROP]
        p = np.pad(c, (0, max(0, CROP - len(c))))[:CROP] if len(c) < CROP else c[:CROP]
        S["tile"][i] = score([t])[0]; S["native"][i] = score([c])[0]; S["pad"][i] = score([p])[0]
        full = x[:CROP] if len(x) >= CROP else np.tile(x, CROP // len(x) + 1)[:CROP]
        S["full"][i] = score([full / (np.abs(full).max() + 1e-9)])[0]
    out[cond] = S
    print(cond + ": " + " | ".join(f"{m} minDCF {min_dcf(s, y):.3f} AUC {roc_auc_score(y, s):.4f}" for m, s in S.items()), flush=True)
np.savez(R / "results/shortclip_v4.npz", **{f"{c}_{m}": out[c][m] for c in out for m in out[c]})
