"""PC twin of the laptop scorer: python score_pc.py <name> <ad|dl> <path> -> results/evalbundle/pc_<name>.csv"""
import sys, glob
from pathlib import Path
import numpy as np, pandas as pd, torch, soundfile as sf
H = Path.home() / "hackgt"; R = H / "evalbundle"; sys.path.insert(0, str(H / "scratch/eval")); sys.path.insert(0, str(H / "dispel_pr8fix"))
name, kind, path = sys.argv[1:4]
rows = []
for man in ("manifest.csv", "manifest2.csv"):
    M = pd.read_csv(R / man)
    for r in M.itertuples(): rows.append((r.set, r.label, "evalbundle/" + r.file, str(R / r.file)))
for p in sorted(glob.glob(str(H / "data/nsa/test/HackGTHearsayTesting/*.wav"))): rows.append(("NSA_TEST", -1, Path(p).name, p))
if kind == "ad":
    from antideepfake import AntiDeepfake
    net = AntiDeepfake(path).cuda().eval()
    def score(x):
        with torch.autocast("cuda", dtype=torch.bfloat16): return net.score(x[:16000 * 20])
else:
    from hearsay.analyzers.dl_detector import Detector, windows
    net = Detector(H / "data/release/v4p6/backbone_config"); net.load_state_dict(torch.load(path, map_location="cpu", weights_only=False)["model"]); net = net.cuda().eval()
    def score(x):
        w, _ = windows(x)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            lg = net(torch.from_numpy(w).cuda()).float()
        return float((lg[:, 1] - lg[:, 0]).mean())
out = []
for i, (s, y, key, p) in enumerate(rows):
    x, sr = sf.read(p, dtype="float32")
    if x.ndim > 1: x = x.mean(1)
    out.append((s, y, key, score(x)))
    if i % 1000 == 0: print(i, len(rows), flush=True)
(H / "results/evalbundle").mkdir(exist_ok=True)
pd.DataFrame(out, columns=["set", "label", "file", name]).to_csv(H / f"results/evalbundle/pc_{name}.csv", index=False); print("DONE", flush=True)
