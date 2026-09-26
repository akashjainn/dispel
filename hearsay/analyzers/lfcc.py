"""LFCC-LCNN detector: linear-frequency cepstral coefficients (hand-crafted spectral front end) + a light CNN with
max-feature-map activations and a BiLSTM (0.27M parameters), the classic ASVspoof baseline family. Trained on DiffSSD
with noise and time-stretch augmentation (ml/train_lfcc.py). Score = mean over up to 3 non-overlapping 4 s windows of
logit[synthetic] - logit[real], exactly as its validation scores were computed."""
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

SR, SEG = 16000, 64000


class LFCC(nn.Module):
    def __init__(self, n_fft=512, win=320, hop=160, n_filt=20, n_ceps=20):
        super().__init__()
        self.n_fft, self.win, self.hop = n_fft, win, hop
        self.register_buffer("window", torch.hann_window(win))
        nb = n_fft // 2 + 1
        edges = np.linspace(0, nb - 1, n_filt + 2)
        fb = np.zeros((n_filt, nb), np.float32)
        for m in range(n_filt):
            l, c, r = edges[m], edges[m + 1], edges[m + 2]
            k = np.arange(nb)
            fb[m] = np.clip(np.minimum((k - l) / (c - l), (r - k) / (r - c)), 0, None)
        self.register_buffer("fb", torch.from_numpy(fb))
        n = np.arange(n_filt)
        dct = np.cos(np.pi / n_filt * (n[None, :] + 0.5) * np.arange(n_ceps)[:, None]) * np.sqrt(2 / n_filt)
        dct[0] /= np.sqrt(2)
        self.register_buffer("dct", torch.from_numpy(dct.astype(np.float32)))

    @staticmethod
    def delta(x):  # x: B,C,T
        p = F.pad(x, (1, 1), mode="replicate")
        return (p[..., 2:] - p[..., :-2]) / 2

    def forward(self, wav):  # B,N -> B,60,T
        wav = wav - wav.mean(-1, keepdim=True)
        wav = torch.cat([wav[:, :1], wav[:, 1:] - 0.97 * wav[:, :-1]], 1)  # pre-emphasis
        spec = torch.stft(wav, self.n_fft, self.hop, self.win, self.window, return_complex=True).abs() ** 2
        fbe = torch.log(torch.matmul(self.fb, spec) + 1e-7)
        c = torch.matmul(self.dct, fbe)
        d1 = self.delta(c)
        feat = torch.cat([c, d1, self.delta(d1)], 1)
        return (feat - feat.mean(-1, keepdim=True)) / (feat.std(-1, keepdim=True) + 1e-5)  # per-utterance CMVN


class MFM(nn.Module):
    def forward(self, x):
        a, b = x.chunk(2, 1)
        return torch.max(a, b)


def cm(i, o, k):
    return nn.Sequential(nn.Conv2d(i, 2 * o, k, padding=k // 2), MFM())


class LCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.front = LFCC()
        self.net = nn.Sequential(
            cm(1, 32, 5), nn.MaxPool2d(2),
            cm(32, 32, 1), nn.BatchNorm2d(32), cm(32, 48, 3), nn.MaxPool2d(2), nn.BatchNorm2d(48),
            cm(48, 48, 1), nn.BatchNorm2d(48), cm(48, 64, 3), nn.MaxPool2d(2),
            cm(64, 64, 1), nn.BatchNorm2d(64), cm(64, 32, 3), nn.BatchNorm2d(32),
            cm(32, 32, 1), nn.BatchNorm2d(32), cm(32, 32, 3), nn.MaxPool2d(2), nn.Dropout(0.3))
        self.lstm = nn.LSTM(32 * 3, 48, num_layers=2, batch_first=True, bidirectional=True)
        self.out = nn.Linear(96, 2)

    def forward(self, wav):
        x = self.net(self.front(wav).unsqueeze(1))  # B,32,F',T'
        x = x.permute(0, 3, 1, 2).flatten(2)  # B,T',32*F'
        x = x[..., :96] if x.shape[-1] >= 96 else F.pad(x, (0, 96 - x.shape[-1]))
        h, _ = self.lstm(x)
        return self.out((h + x).mean(1))


class LFCCDetector:
    name = "lfcc"

    def __init__(self, model_dir, spec, device="cpu"):
        from .dl_detector import sha256
        ck = Path(model_dir) / spec["checkpoint"]
        if spec.get("sha256") and sha256(ck) != spec["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {ck}")
        self.net = LCNN()
        self.net.load_state_dict(torch.load(ck, map_location="cpu", weights_only=False)["model"])
        self.net.eval()

    @torch.inference_mode()
    def analyze(self, audio, sr, meta, context):
        t0 = time.perf_counter()
        try:
            x = audio
            if len(x) < SEG:
                x = np.tile(x, int(np.ceil(SEG / max(len(x), 1))))
            k = min(3, len(x) // SEG)
            lg = self.net(torch.from_numpy(np.stack([x[j * SEG:(j + 1) * SEG] for j in range(k)]).astype(np.float32)))
            s = float((lg[:, 1] - lg[:, 0]).mean())
            return {"features": {"lfcc": s}, "ran": True,
                    "finding": f"LFCC spectral-cepstral detector score {s:+.1f} over {k} window(s) of 4 s.",
                    "ms": int((time.perf_counter() - t0) * 1000)}
        except Exception as e:
            return {"features": {"lfcc": np.nan}, "ran": False, "finding": f"LFCC detector did not run: {e}",
                    "ms": int((time.perf_counter() - t0) * 1000)}
