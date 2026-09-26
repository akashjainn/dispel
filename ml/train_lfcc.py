"""LFCC + LCNN spoof detector (hand-crafted spectral front end), robust to NSA-style
noise and time-stretch. Runs on Windows (MSI RTX 4070 laptop) or Linux.

Run from a repo checkout (the model is imported from hearsay/analyzers/lfcc.py).
Data: make_lfcc_subset.py output (meta.csv + train/, val_clean/, val_atempo/ 16 kHz WAVs).
Training augmentation (identical for real and fake, labels unchanged):
  silence trim + random pad, random gain, time-stretch p=0.7 rate U(0.85,1.15) via
  {librosa phase vocoder, audiotsm WSOLA, resample speed change}, noise p=0.7
  (white/pink/brown, SNR U(5,35) dB). ffmpeg atempo is NEVER used here: val_atempo holds it out.
Selection: lowest mean of minDCF@P(syn)=0.3 (4x cost on real flagged) on val_clean and val_atempo.
Score convention: higher = more synthetic (logit[fake] - logit[real]).
"""
import argparse, csv, math, os, random, time, json
import numpy as np, soundfile as sf, torch, torch.nn as nn, torch.nn.functional as F
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for hearsay/
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler

SR, SEG = 16000, 64000


# ---------------- augmentation (CPU, in workers) ----------------
def trim_pad(x, rng):
    import librosa
    y, _ = librosa.effects.trim(x, top_db=40)
    if len(y) < SR // 2:
        y = x
    a, b = (int(rng.uniform(0, 0.4) * SR) for _ in range(2))
    lvl = rng.uniform(1e-5, 3e-4)
    return np.concatenate([rng.standard_normal(a) * lvl, y, rng.standard_normal(b) * lvl]).astype(np.float32)


def stretch(x, rate, method):
    if method == "pv":
        import librosa
        return librosa.effects.time_stretch(x, rate=rate)
    if method == "speed":  # tape-style: faster and higher pitch
        import librosa
        return librosa.resample(x, orig_sr=int(round(SR * rate)), target_sr=SR, res_type="soxr_hq")
    if method == "wsola":
        from audiotsm import wsola
        from audiotsm.io.array import ArrayReader, ArrayWriter
        r, w = ArrayReader(x[None, :].astype(np.float32)), ArrayWriter(1)
        wsola(1, speed=rate).run(r, w)
        return w.data[0].astype(np.float32)
    raise ValueError(method)


def colored_noise(n, color, rng):
    w = rng.standard_normal(n)
    if color == "white":
        return w
    f = np.fft.rfftfreq(n)
    f[0] = f[1] if n > 1 else 1.0
    s = np.fft.rfft(w) / (np.sqrt(f) if color == "pink" else f)
    y = np.fft.irfft(s, n)
    return y / (np.std(y) + 1e-9)


def augment(x, rng, methods):
    x = trim_pad(x, rng)
    if rng.random() < 0.7:
        try:
            x = stretch(x, rng.uniform(0.85, 1.15), methods[rng.integers(len(methods))])
        except Exception:
            pass
    if rng.random() < 0.7:
        snr = rng.uniform(5, 35)
        n = colored_noise(len(x), ["white", "pink", "brown"][rng.integers(3)], rng)
        x = x + n * np.sqrt((np.mean(x ** 2) + 1e-12) / 10 ** (snr / 10))
    x = x * 10 ** (rng.uniform(-12, 6) / 20)
    return np.clip(x, -1, 1).astype(np.float32)


def crop(x, rng):
    if len(x) < SEG:
        x = np.tile(x, int(math.ceil(SEG / max(len(x), 1))))
    s = rng.integers(0, len(x) - SEG + 1)
    return x[s:s + SEG]


class TrainSet(Dataset):
    def __init__(self, root, rows, methods, seed):
        self.root, self.rows, self.methods, self.seed = root, rows, methods, seed

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        rng = np.random.default_rng([self.seed, i, int(time.time() * 1e6) % 2**31])
        x, _ = sf.read(os.path.join(self.root, "train", r["id"] + ".wav"), dtype="float32")
        try:
            y = augment(x, rng, self.methods)
            if not np.all(np.isfinite(y)) or len(y) < 1600:
                raise ValueError("bad augmented audio")
        except Exception:  # one bad augmentation must not kill the worker pool (lfcc1 died this way)
            y = x
        return torch.from_numpy(crop(y, rng).astype(np.float32)), int(r["target"])


class EvalSet(Dataset):  # up to 3 non-overlapping 4 s windows per clip, no augmentation
    def __init__(self, root, sub, rows):
        self.root, self.sub, self.rows = root, sub, rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        x, _ = sf.read(os.path.join(self.root, self.sub, r["id"] + ".wav"), dtype="float32")
        if len(x) < SEG:
            x = np.tile(x, int(math.ceil(SEG / max(len(x), 1))))
        k = min(3, len(x) // SEG)
        return torch.from_numpy(np.stack([x[j * SEG:(j + 1) * SEG] for j in range(k)])), int(r["target"]), i


def eval_collate(b):
    w = torch.cat([x[0] for x in b])
    owner = torch.cat([torch.full((len(x[0]),), j) for j, x in enumerate(b)])
    return w, torch.tensor([x[1] for x in b]), torch.tensor([x[2] for x in b]), owner


# ---------------- model ----------------
# One definition for training and inference: hearsay/analyzers/lfcc.py (front end + LCNN).
from hearsay.analyzers.lfcc import LCNN  # noqa: E402


# ---------------- metrics ----------------
def min_dcf(s, y, p_syn=0.3, c_fp=4.0):
    """s: higher = synthetic; y: 1 = synthetic. DCF = c_fp*(1-p)*P(real flagged) + p*P(syn missed),
    minimized over thresholds, normalized by the better trivial system."""
    o = np.argsort(-s)
    ys = y[o]
    nf, nr = ys.sum(), len(ys) - ys.sum()
    tp = np.concatenate([[0], np.cumsum(ys)])  # flag top-k
    fp = np.concatenate([[0], np.cumsum(1 - ys)])
    dcf = c_fp * (1 - p_syn) * fp / nr + p_syn * (1 - tp / nf)
    return float(dcf.min() / min(p_syn, c_fp * (1 - p_syn)))


def eer(s, y):
    from sklearn.metrics import roc_curve
    fpr, tpr, _ = roc_curve(y, s)
    i = np.nanargmin(np.abs(fpr - (1 - tpr)))
    return float((fpr[i] + 1 - tpr[i]) / 2)


@torch.no_grad()
def score(model, dl, n, dev):
    model.eval()
    out = np.zeros(n, np.float32)
    for w, y, idx, owner in dl:
        with torch.autocast("cuda", dtype=torch.float16, enabled=dev == "cuda"):
            lg = model(w.to(dev)).float()
        s = (lg[:, 1] - lg[:, 0]).cpu()
        for j in range(len(idx)):
            out[idx[j]] = s[owner == j].mean().item()
    model.train()
    return out


def report(s, rows):
    y = np.array([int(r["target"]) for r in rows])
    src = np.array([r["method_name"] for r in rows])
    res = {"minDCF@0.3": min_dcf(s, y, 0.3), "minDCF@0.05": min_dcf(s, y, 0.05), "EER": eer(s, y)}
    thr = np.quantile(s[y == 0], 0.99)  # threshold at 1% real flagged (pooled)
    res["det@FPR1%"] = float((s[y == 1] > thr).mean())
    for k in ("ljspeech", "librispeech"):
        m = src == k
        if m.any():
            res[f"FPR1%thr_{k}"] = float((s[m] > thr).mean())
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hours", type=float, default=2.0)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--eval-min", type=float, default=12.0)
    ap.add_argument("--methods", default="pv,wsola,speed")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--init", default="", help="warm-start weights from a checkpoint (e.g. runs/lfcc1/best.pt)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    log = open(os.path.join(a.out, "train.log"), "a", buffering=1)
    P = lambda *m: (print(*m, flush=True), print(*m, file=log))
    rows = list(csv.DictReader(open(os.path.join(a.data, "meta.csv"))))
    tr = [r for r in rows if r["subset"] == "train"]
    va = [r for r in rows if r["subset"] == "val"]
    methods = a.methods.split(",")
    try:
        import audiotsm  # noqa
    except ImportError:
        methods = [m for m in methods if m != "wsola"]
    P(f"train {len(tr)} (fake {sum(r['target']=='1' for r in tr)}), val {len(va)}, methods {methods}, dev {dev}")
    lab = np.array([int(r["target"]) for r in tr])
    wts = np.where(lab == 1, 0.5 / lab.sum(), 0.5 / (len(lab) - lab.sum()))
    sampler = WeightedRandomSampler(torch.tensor(wts, dtype=torch.double), num_samples=10**7, replacement=True)
    dl = DataLoader(TrainSet(a.data, tr, methods, a.seed), batch_size=a.batch, sampler=sampler,
                    num_workers=a.workers, persistent_workers=True, drop_last=True, prefetch_factor=4)
    evals = {sub: DataLoader(EvalSet(a.data, sub, va), batch_size=32, num_workers=2, collate_fn=eval_collate)
             for sub in ("val_clean", "val_atempo")}
    model = LCNN().to(dev)
    if a.init:
        model.load_state_dict(torch.load(a.init, map_location="cpu", weights_only=False)["model"])
        P("warm start from", a.init)
    P("params", sum(p.numel() for p in model.parameters()) / 1e6, "M")
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    t0, last_eval, best, step, run = time.time(), time.time(), 9.0, 0, 0.0
    budget = a.hours * 3600
    for w, y in dl:
        frac = min((time.time() - t0) / budget, 1.0)
        for g in opt.param_groups:
            g["lr"] = a.lr * min(1.0, step / 300) * 0.5 * (1 + math.cos(math.pi * frac))
        with torch.autocast("cuda", dtype=torch.float16, enabled=dev == "cuda"):
            loss = F.cross_entropy(model(w.to(dev)), y.to(dev))
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        scaler.step(opt); scaler.update()
        step += 1; run = 0.98 * run + 0.02 * loss.item()
        if step % 100 == 0:
            P(f"step {step} loss {run:.4f} lr {opt.param_groups[0]['lr']:.2e} {step*a.batch/(time.time()-t0):.0f} samples/s {(time.time()-t0)/3600:.2f} h")
        done = time.time() - t0 >= budget
        if done or time.time() - last_eval >= a.eval_min * 60:
            last_eval = time.time()
            res = {sub: report(score(model, d, len(va), dev), va) for sub, d in evals.items()}
            sel = (res["val_clean"]["minDCF@0.3"] + res["val_atempo"]["minDCF@0.3"]) / 2
            P(f"EVAL step {step} sel {sel:.4f} " + json.dumps(res))
            torch.save({"model": model.state_dict(), "step": step, "sel": sel, "res": res, "args": vars(a)},
                       os.path.join(a.out, "last.pt"))
            if sel < best:
                best = sel
                torch.save({"model": model.state_dict(), "step": step, "sel": sel, "res": res, "args": vars(a)},
                           os.path.join(a.out, "best.pt"))
                P(f"  new best {sel:.4f}")
        if done:
            break
    P(f"DONE best sel {best:.4f}")


if __name__ == "__main__":
    main()
