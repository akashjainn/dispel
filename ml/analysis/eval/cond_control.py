"""Control: does the condition detector still recognise stretching on SHORT, peak-normalized clips (like NSA's test)?
400 val clips per condition, cropped to test-like durations; detector trained on full-length val clips (as applied
to the test set)."""
import sys, warnings
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd, torch
warnings.filterwarnings("ignore")
R = Path.home() / "hackgt"
sys.path.insert(0, str(R / "dispel_pr8fix")); sys.path.insert(0, str(R / "scratch/features"))
from pitch_features import pitch_features
from spectral import spectral_features
from rhythm import rhythm_features
from voice import voice_features
CONDS = ["clean", "atempo", "rubberband", "pv"]
durs = np.load(R / "results/nsa_test_durations.npy")
ids = np.random.default_rng(3).choice(4523, 400, replace=False)
def crop(c, i):
    x = np.load(R / f"data/eval_cache/v3_val/{c}/{i}.npy").astype(np.float32)
    rng = np.random.default_rng([99, int(i)]); d = int(float(rng.choice(durs)) * 16000)
    s0 = int(rng.integers(0, max(1, len(x) - d + 1))); y = x[s0:s0 + d]; return y / (np.abs(y).max() + 1e-9)
def job(a):
    c, i = a; x = crop(c, i); o = {"cond": c, "idx": int(i)}
    for fn in (pitch_features, spectral_features, rhythm_features, voice_features):
        try: o.update(fn(x, 16000))
        except Exception: pass
    return o
if __name__ == "__main__":
    with Pool(8) as p:
        F = pd.DataFrame(p.map(job, [(c, i) for c in CONDS for i in ids], chunksize=8))
    from hearsay.analyzers.dl_detector import Detector, CROP
    from hearsay.analyzers.lfcc import LCNN, SEG
    net = Detector(R / "data/release/v4p6/backbone_config"); net.load_state_dict(torch.load(R / "data/checkpoints/v4/best.pt", map_location="cpu", weights_only=False)["model"]); net = net.cuda().eval()
    lf = LCNN(); lf.load_state_dict(torch.load(R / "scratch/lfcc_eval/lfcc1_best.pt", map_location="cpu", weights_only=False)["model"]); lf.eval()
    v, l = [], []
    for c, i in zip(F.cond, F.idx):
        x = crop(c, i); t = np.tile(x, CROP // len(x) + 1)[:CROP] if len(x) < CROP else x[:CROP]
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            lg = net(torch.from_numpy(t)[None].cuda()).float(); v.append((lg[0, 1] - lg[0, 0]).item())
        with torch.inference_mode():
            lg = lf(torch.from_numpy(t)[None]); l.append((lg[0, 1] - lg[0, 0]).item())
    F["v3"], F["lfcc"] = v, l
    F.to_csv(R / "results/cond_control_short.csv", index=False)
    print("saved", len(F))
