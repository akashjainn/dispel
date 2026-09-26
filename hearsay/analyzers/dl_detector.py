"""Deep-learning detector: XLS-R 300M fine-tuned on DiffSSD with noise + time-stretch augmentation (v3).

Score s = mean over up to 3 non-overlapping 4 s windows (16 kHz mono; clips < 4 s tile-repeated) of
logit[synthetic] - logit[real]. This is exactly how the validation scores that fusion was fit on were
computed (scratch/eval/score_v3.py on the training PC), so do not change the windowing without refitting fusion."""
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

SR, CROP, MAXW = 16000, 4 * 16000, 3


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Detector(nn.Module):
    """SSL backbone, softmax layer weights, mean+std pooling, MLP head (identical to training)."""

    def __init__(self, cfg_dir):
        super().__init__()
        from transformers import AutoConfig, AutoModel
        cfg = AutoConfig.from_pretrained(cfg_dir, layerdrop=0.0)
        self.backbone = AutoModel.from_config(cfg)
        self.normalize = bool(json.load(open(Path(cfg_dir) / "preprocessor_config.json")).get("do_normalize", False))
        with torch.no_grad():
            n_hs = len(self.backbone.eval()(torch.zeros(1, SR), output_hidden_states=True).hidden_states)
        self.layer_w = nn.Parameter(torch.zeros(n_hs))
        self.head = nn.Sequential(nn.Linear(2 * cfg.hidden_size, 256), nn.GELU(), nn.Dropout(0.2), nn.Linear(256, 2))

    def forward(self, x):
        if self.normalize:
            x = (x - x.mean(1, keepdim=True)) / torch.sqrt(x.var(1, keepdim=True) + 1e-7)
        hs = self.backbone(x, output_hidden_states=True).hidden_states
        h = (torch.softmax(self.layer_w, 0)[:, None, None, None] * torch.stack(hs)).sum(0)
        return self.head(torch.cat([h.mean(1), h.std(1)], -1).float())


def windows(x, maxw=MAXW):
    """Returns (windows [k, CROP], starts_s). Short clips are tile-repeated to one window."""
    if len(x) < CROP:
        return np.tile(x, CROP // max(len(x), 1) + 1)[None, :CROP].astype(np.float32), [0.0]
    k = min(maxw, len(x) // CROP)
    return np.stack([x[j * CROP:(j + 1) * CROP] for j in range(k)]).astype(np.float32), [j * 4.0 for j in range(k)]


class DLDetector:
    name = "dl_detector"

    def __init__(self, model_dir, spec, device=None):
        ck = Path(model_dir) / spec["checkpoint"]
        if spec.get("sha256") and sha256(ck) != spec["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {ck}")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if self.device == "cpu":
            torch.set_num_threads(int(os.getenv("TORCH_THREADS", os.cpu_count() or 4)))
        net = Detector(Path(model_dir) / spec.get("backbone_config", "backbone_config"))
        net.load_state_dict(torch.load(ck, map_location="cpu", weights_only=False)["model"])
        self.net = net.to(self.device).eval()

    @torch.inference_mode()
    def window_scores(self, w):
        x = torch.from_numpy(w).to(self.device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=self.device == "cuda"):
            lg = self.net(x).float()
        return (lg[:, 1] - lg[:, 0]).cpu().numpy()

    def analyze(self, audio, sr, meta, context):
        t0 = time.perf_counter()
        try:
            assert sr == SR
            w, starts = windows(audio)
            s = self.window_scores(w)
            return {"features": {"v3": float(s.mean())}, "windows": [(t, t + 4.0, float(v)) for t, v in zip(starts, s)],
                    "finding": f"Neural detector score {s.mean():+.1f} over {len(s)} window(s) of 4 s.",
                    "ran": True, "ms": int((time.perf_counter() - t0) * 1000)}
        except Exception as e:
            return {"features": {}, "finding": f"Neural detector did not run: {e}", "ran": False,
                    "ms": int((time.perf_counter() - t0) * 1000)}
