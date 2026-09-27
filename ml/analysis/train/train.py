"""Fine-tune an SSL backbone (WavLM / wav2vec2 / XLS-R) as a spoof detector.

Data (never touches the 16 ITW test speakers; asserted below)
  train:  ITW 32 train speakers + ASVspoof 5 train (A01-A08)
          + optionally MLAAD-tiny mlaad_train.csv (--mix mlaad=...), the leave-generators-out
          split from make_mlaad_splits.py: train speakers x train generators, split by
          original_file. Asserted disjoint from every MLAAD test file and held-out generator.
  val:    ITW 6 val speakers, also scored through 8 kHz mu-law; MLAAD val (mlaad_val.csv).
          Model selection: mean EER over --select sets (default val_itw_clean).
  MLAAD test sets are scored only by eval_mlaad_test.py, on best.pt, after training.
  heldout-generator check: ASVspoof 5 dev attacks A09-A16 (+ dev bona fide), never trained on;
          only once all flac_D tars are marked extracted (avoids half-written files)
  legacy modern-TTS check (--mlaad-test-per-model N > 0): MLAAD fakes of all generators, fakes only
Sampling: source mix (itw/asv5/mlaad), 50/50 class within each source, and within
  (source, class) each group (ITW speaker, ASVspoof attack or speaker, MLAAD TTS model or narrator)
  gets mass proportional to min(n_group, CAP). Caps Trump/Obama/etc.
Resumable: last.pt every --ckpt-minutes, at each epoch end, on SIGTERM/SIGINT, and
  at the wall-clock limit. `--resume` continues mid-epoch deterministically.
"""
import argparse
import csv
import json
import logging
import math
import os
import random
import signal
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score, roc_curve
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModel

sys.path.insert(0, str(Path(__file__).parent))
from augment import augment, codec_roundtrip  # noqa: E402

ROOT = Path.home() / "hackgt"
DATA = ROOT / "data"
SR = 16000
CROP = 4 * SR
CAP = 150
log = logging.getLogger("train")


# ---------------------------------------------------------------- data lists
def read_rows(name):
    return [{**r, "label": int(r["label"])} for r in csv.DictReader(open(DATA / "splits" / name))]


def mlaad_fake_rows(langs=("en", "de"), per_model=0, seed=13):
    """MLAAD-tiny fakes only, group = '<lang>/<TTS model>'. Test set, never trained on."""
    base = DATA / "mlaad_tiny" / "fake"
    rng = np.random.default_rng(seed)
    rows = []
    for lang in langs:
        for d in sorted(p for p in (base / lang).iterdir() if p.is_dir()) if (base / lang).exists() else []:
            files = sorted(d.glob("*.wav"))
            if per_model and len(files) > per_model:
                files = [files[i] for i in sorted(rng.choice(len(files), per_model, replace=False))]
            rows += [{"path": str(p.relative_to(DATA)), "label": 1, "group": f"{lang}/{d.name}",
                      "source": "mlaad"} for p in files]
    return rows


def keep_existing(rows, name, allow_missing):
    ok = [r for r in rows if (DATA / r["path"]).exists()]
    miss = len(rows) - len(ok)
    if miss:
        msg = f"{name}: {miss}/{len(rows)} files missing"
        if not allow_missing:
            raise SystemExit(msg + " (use --allow-missing for smoke tests)")
        log.warning(msg + "; dropped")
    return ok


def sampling_weights(rows, mix, global_balance=False, class_mix=None):
    """class_mix = {0: {src: share}, 1: {src: share}}: explicit per-class source shares (each class gets 50%)."""
    w = np.zeros(len(rows))
    present = {r["source"] for r in rows}
    tot = sum(mix[s] for s in present) if mix else 1.0
    idx = {}
    for i, r in enumerate(rows):
        idx.setdefault((r["source"], r["label"]), {}).setdefault(r["group"], []).append(i)
    if class_mix:
        for lab in (0, 1):
            have = {s for (s, l) in idx if l == lab}
            assert have == set(class_mix[lab]), f"class {lab}: sources {sorted(have)} != mix {sorted(class_mix[lab])}"
    for (src, lab), groups in idx.items():
        if class_mix:
            mass = class_mix[lab][src] / sum(class_mix[lab].values()) * 0.5
        else:
            mass = mix[src] / tot * 0.5
        gm = {g: min(len(ii), CAP) for g, ii in groups.items()}
        z = sum(gm.values())
        for g, ii in groups.items():
            w[ii] = mass * gm[g] / z / len(ii)
    if global_balance:  # real-only sources (VoxPopuli) would otherwise tilt the prior towards real
        y = np.array([r["label"] for r in rows])
        for c in (0, 1):
            w[y == c] *= 0.5 / w[y == c].sum()
    return w / w.sum()


# ---------------------------------------------------------------- datasets
def load_audio(path, crop=None, rng=None):
    info = sf.info(path)
    n = info.frames
    if crop and info.samplerate == SR and n > crop:
        start = int(rng.integers(0, n - crop + 1))
        x, _ = sf.read(path, start=start, stop=start + crop, dtype="float32", always_2d=True)
    else:
        x, sr = sf.read(path, dtype="float32", always_2d=True)
        if sr != SR:
            import librosa
            x = librosa.resample(x.T, orig_sr=sr, target_sr=SR, res_type="soxr_hq").T
    x = x.mean(1)
    if crop:
        if len(x) > crop:
            s = int(rng.integers(0, len(x) - crop + 1))
            x = x[s: s + crop]
        elif len(x) < crop:
            x = np.tile(x, crop // max(len(x), 1) + 1)[:crop]
    return x.astype(np.float32)


class TrainSet(Dataset):
    def __init__(self, rows, seed, aug=True):
        self.rows, self.seed, self.aug = rows, seed, aug

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, key):
        i, epoch, pos = key
        rng = np.random.default_rng([self.seed, epoch, pos])
        r = self.rows[i]
        x = load_audio(DATA / r["path"], CROP, rng)
        if self.aug:
            x, _ = augment(x, rng)
        return torch.from_numpy(x), r["label"]


class EvalSet(Dataset):
    """Up to 3 non-overlapping 4 s windows per clip (tile-repeat short clips)."""

    def __init__(self, rows, codec=None, max_windows=3):
        self.rows, self.codec, self.max_windows = rows, codec, max_windows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        x = load_audio(DATA / r["path"])
        if self.codec:
            x = codec_roundtrip(x, self.codec, np.random.default_rng([7, i]))
        if len(x) < CROP:
            x = np.tile(x, CROP // max(len(x), 1) + 1)[:CROP]
        k = min(self.max_windows, len(x) // CROP)
        w = np.stack([x[j * CROP:(j + 1) * CROP] for j in range(k)])
        return torch.from_numpy(w), r["label"], i


def eval_collate(batch):
    w = torch.cat([b[0] for b in batch])
    owner = torch.cat([torch.full((len(b[0]),), j) for j, b in enumerate(batch)])
    return w, torch.tensor([b[1] for b in batch]), torch.tensor([b[2] for b in batch]), owner


# ---------------------------------------------------------------- model
class Detector(nn.Module):
    def __init__(self, backbone_dir, grad_ckpt):
        super().__init__()
        # layerdrop skips layers during training and drops them from hidden_states,
        # which breaks the learned per-layer weighting -> disable it
        self.backbone = AutoModel.from_pretrained(backbone_dir, layerdrop=0.0)
        self.backbone.freeze_feature_encoder()
        if grad_ckpt:
            self.backbone.gradient_checkpointing_enable()
        pre = json.load(open(Path(backbone_dir) / "preprocessor_config.json"))
        self.normalize = bool(pre.get("do_normalize", False))
        c = self.backbone.config
        with torch.no_grad():  # hidden_states count differs by model/version (L or L+1)
            n_hs = len(self.backbone.eval()(torch.zeros(1, SR), output_hidden_states=True).hidden_states)
        self.backbone.train()
        self.layer_w = nn.Parameter(torch.zeros(n_hs))
        self.head = nn.Sequential(nn.Linear(2 * c.hidden_size, 256), nn.GELU(), nn.Dropout(0.2), nn.Linear(256, 2))

    def forward(self, x):
        if self.normalize:
            x = (x - x.mean(1, keepdim=True)) / torch.sqrt(x.var(1, keepdim=True) + 1e-7)
        hs = self.backbone(x, output_hidden_states=True).hidden_states
        h = (torch.softmax(self.layer_w, 0)[:, None, None, None] * torch.stack(hs)).sum(0)
        return self.head(torch.cat([h.mean(1), h.std(1)], -1).float())


# ---------------------------------------------------------------- metrics
def eer(y, s):
    fpr, tpr, _ = roc_curve(y, s)
    i = np.nanargmin(np.abs(1 - tpr - fpr))
    return float((fpr[i] + 1 - tpr[i]) / 2)


def binary_metrics(y, s):
    y, s = np.asarray(y), np.asarray(s)
    p = s > 0  # argmax; the sampler trains at a 50/50 class prior
    return {"eer": eer(y, s), "auc": float(roc_auc_score(y, s)),
            "bal_acc": float((p[y == 1].mean() + (~p[y == 0]).mean()) / 2), "n": int(len(y)),
            "bona_fpr": float(p[y == 0].mean())}  # false-alarm rate at the same threshold as MLAAD det_rate


@torch.no_grad()
def score(model, rows, codec, args):
    model.eval()
    dl = DataLoader(EvalSet(rows, codec), batch_size=args.eval_batch, num_workers=args.workers,
                    collate_fn=eval_collate)
    out = np.zeros(len(rows))
    for w, _, ids, owner in dl:
        with torch.autocast("cuda", dtype=torch.bfloat16):
            lg = model(w.cuda(non_blocking=True))
        s = (lg[:, 1] - lg[:, 0]).float().cpu()
        for j, i in enumerate(ids.tolist()):
            out[i] = s[owner == j].mean().item()
    model.train()
    return out


def evaluate(model, sets, args):
    res = {}
    for name, (rows, codec) in sets.items():
        t = time.time()
        s = score(model, rows, codec, args)
        y = np.array([r["label"] for r in rows])
        if name == "mlaad_fake":  # fakes only: detection rate at the argmax threshold, per TTS model
            g = np.array([r["group"] for r in rows])
            res[name] = {"det_rate": float((s > 0).mean()), "n": int(len(y)),
                         "per_model": {k: float((s[g == k] > 0).mean()) for k in sorted(set(g))}}
            res[name]["sec"] = round(time.time() - t, 1)
            continue
        res[name] = binary_metrics(y, s)
        if name == "heldout_asv5":
            bona = y == 0
            for g in sorted({r["group"] for r in rows if r["label"] == 1}):
                k = bona | np.array([r["group"] == g for r in rows])
                res[name][f"eer_{g}"] = eer(y[k], s[k])
        res[name]["sec"] = round(time.time() - t, 1)
    return res


# ---------------------------------------------------------------- checkpointing
def atomic_save(obj, path):
    tmp = path.with_suffix(".tmp")
    torch.save(obj, tmp)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--backbone", required=True, help="dir under data/models")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--samples-per-epoch", type=int, default=20000)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--eval-batch", type=int, default=16)
    ap.add_argument("--lr-backbone", type=float, default=1e-5)
    ap.add_argument("--lr-head", type=float, default=1e-3)
    ap.add_argument("--warmup-frac", type=float, default=0.05)
    ap.add_argument("--grad-ckpt", action="store_true")
    ap.add_argument("--mix", default="itw=0.5,asv5=0.5")
    ap.add_argument("--mlaad-test-per-model", type=int, default=0,
                    help="legacy: MLAAD fakes per TTS model scored every epoch, all generators (0 = off)")
    ap.add_argument("--mix-real", default="", help="per-class mix for bona fide, e.g. itw=0.35,voxpopuli=0.25 (with --mix-fake)")
    ap.add_argument("--mix-fake", default="", help="per-class mix for spoof, e.g. itw=0.3,mlaad_full=0.4")
    ap.add_argument("--global-class-balance", action="store_true",
                    help="rescale sampling so each class gets 50%% overall (needed with real-only sources)")
    ap.add_argument("--vox-list", default="vox_train.csv", help="VoxPopuli train list (v1: vox_train.csv, v2: vox2_train.csv)")
    ap.add_argument("--select", default="val_itw_clean",
                    help="comma-separated eval sets; best.pt = lowest mean EER over them")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-hours", type=float, default=7.0)
    ap.add_argument("--ckpt-minutes", type=float, default=30.0)
    ap.add_argument("--log-every", type=int, default=50)
    ap.add_argument("--max-steps", type=int, default=0, help="stop after N optimizer steps (probe)")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--allow-missing", action="store_true")
    ap.add_argument("--val-n", type=int, default=0, help="subsample val (smoke)")
    ap.add_argument("--heldout-per-attack", type=int, default=250)
    ap.add_argument("--heldout-bona", type=int, default=2000)
    ap.add_argument("--train-n", type=int, default=0, help="subsample train pool (smoke)")
    args = ap.parse_args()

    run_dir = DATA / "checkpoints" / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(run_dir / "train.log"), logging.StreamHandler(sys.stdout)])
    log.info("args %s", json.dumps(vars(args)))
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    # ---- data, with test-speaker guard
    test_spk = {l.strip() for l in open(DATA / "splits/itw_test_speakers.txt") if l.strip()}
    val_spk = {l.strip() for l in open(DATA / "splits/ft_itw_val_speakers.txt") if l.strip()}
    parse = lambda m: {k: float(v) for k, v in (kv.split("=") for kv in m.split(","))} if m else {}
    class_mix = {0: parse(args.mix_real), 1: parse(args.mix_fake)} if args.mix_real else None
    mix = parse(args.mix) if not class_mix else {s: 1.0 for s in set(class_mix[0]) | set(class_mix[1])}
    if set(mix) - {"itw", "asv5", "mlaad", "voxpopuli", "mailabs", "mlaad_full"}:
        raise SystemExit(f"--mix {args.mix}: unknown source")
    train_rows = read_rows("ft_itw_train.csv") + read_rows("ft_asv5_train.csv")
    if mix.get("mlaad", 0) > 0:
        ml = read_rows("mlaad_train.csv")
        test_files = {r["path"] for n in ("mlaad_test_unseen.csv", "mlaad_test_seen.csv", "mlaad_test_unseen_ext.csv",
                                          "mlaad_val.csv") for r in read_rows(n)}
        heldout_models = {r["group"] for r in read_rows("mlaad_test_unseen.csv") if r["label"] == 1}
        assert not {r["path"] for r in ml} & test_files, "MLAAD test/val file in train"
        assert not {r["group"] for r in ml} & heldout_models, "held-out MLAAD generator in train"
        train_rows += ml
    if mix.get("voxpopuli", 0) > 0:  # bona fide only; Merkel-guarded, held-out speakers excluded (make_v1_splits.py)
        vx = read_rows(args.vox_list)
        assert all(r["label"] == 0 for r in vx)
        assert not {r["group"] for r in vx} & {r["group"] for r in read_rows(args.vox_list.replace("train", "heldout"))}
        train_rows += vx
    for src, lst, lab in (("mailabs", "mailabs_train.csv", 0), ("mlaad_full", "mlaad_full_train.csv", 1)):
        if mix.get(src, 0) > 0:  # v2 sources; exclusions asserted in make_v2_splits.py and re-checked here
            rr = read_rows(lst)
            assert all(r["label"] == lab and r["source"] == src for r in rr), lst
            test_files = {r["path"] for n in ("mlaad_test_unseen.csv", "mlaad_test_seen.csv", "mlaad_test_unseen_ext.csv",
                                              "mlaad_val.csv") for r in read_rows(n)}
            assert not {r["path"] for r in rr} & test_files, f"{lst}: test/val file in train"
            train_rows += rr
    val_rows = read_rows("ft_itw_val.csv")
    mlaad_val = read_rows("mlaad_val.csv")
    itw_train_spk = {r["group"] for r in train_rows if r["source"] == "itw"}
    assert not itw_train_spk & test_spk and not val_spk & test_spk and not itw_train_spk & val_spk
    assert {r["group"] for r in val_rows} == val_spk
    train_rows = keep_existing(train_rows, "train", args.allow_missing)
    rng = np.random.default_rng(args.seed)
    if args.train_n:
        train_rows = [train_rows[i] for i in rng.choice(len(train_rows), args.train_n, replace=False)]
    if args.val_n:
        val_rows = [val_rows[i] for i in rng.choice(len(val_rows), args.val_n, replace=False)]
    d_tars = ["flac_D_aa.tar", "flac_D_ab.tar", "flac_D_ac.tar"]
    if all((DATA / "asvspoof5/.extracted" / t).exists() for t in d_tars):
        held = keep_existing(read_rows("ft_asv5_dev_heldout.csv"), "heldout", args.allow_missing)
    else:
        held = []  # tars still downloading/extracting: files may be half-written
    hb = [r for r in held if r["label"] == 0]
    hs = {}
    for r in held:
        if r["label"] == 1:
            hs.setdefault(r["group"], []).append(r)
    held = [hb[i] for i in rng.choice(len(hb), min(args.heldout_bona, len(hb)), replace=False)]
    for g in sorted(hs):
        held += [hs[g][i] for i in rng.choice(len(hs[g]), min(args.heldout_per_attack, len(hs[g])), replace=False)]
    train_attacks = {r["group"] for r in train_rows if r["source"] == "asv5" and r["label"] == 1}
    assert not train_attacks & {r["group"] for r in held if r["label"] == 1}, "held-out attack leaked"

    w = sampling_weights(train_rows, mix, args.global_class_balance, class_mix)
    by_src = {}
    for r, wi in zip(train_rows, w):
        by_src.setdefault((r["source"], r["label"]), [0, 0.0])
        by_src[(r["source"], r["label"])][0] += 1
        by_src[(r["source"], r["label"])][1] += wi
    for (src, lab), (n, m) in sorted(by_src.items()):
        log.info("train pool %-5s %-5s n=%6d  sampling mass %.3f", src, "spoof" if lab else "bona", n, m)
    heavy = ["Donald Trump", "Barack Obama", "The Notorious B.I.G.", "Nick Offerman", "Jeff Goldblum", "Mitch Hedberg"]
    for h in heavy:
        k = [i for i, r in enumerate(train_rows) if r["group"] == h]
        if k:
            sp = sum(w[i] for i in k if train_rows[i]["label"] == 1)
            log.info("heavy speaker %-22s clips=%5d mass=%.4f (spoof share of its mass %.2f)", h, len(k), w[k].sum(), sp / w[k].sum())
    log.info("val: %d clips, %d speakers | heldout: %d clips, attacks %s | train attacks %s",
             len(val_rows), len(val_spk), len(held), sorted(hs), sorted(train_attacks))
    eval_sets = {"val_itw_clean": (val_rows, None), "val_itw_mulaw": (val_rows, "mulaw"),
                 "mlaad_val": (mlaad_val, None)}
    select = args.select.split(",")
    assert set(select) <= set(eval_sets), f"--select {args.select}: unknown eval set"
    log.info("mlaad_val: %d clips (%d fake) | selection: mean EER of %s",
             len(mlaad_val), sum(r["label"] for r in mlaad_val), select)
    if held:
        eval_sets["heldout_asv5"] = (held, None)
    else:
        log.warning("ASVspoof 5 dev (flac_D) not fully extracted yet; held-out-generator check skipped")
    mlaad = mlaad_fake_rows(per_model=args.mlaad_test_per_model, seed=args.seed) if args.mlaad_test_per_model > 0 else []
    if mlaad:
        eval_sets["mlaad_fake"] = (mlaad, None)
        log.info("modern-TTS test: %d MLAAD fakes, %d TTS models (test only)", len(mlaad), len({r["group"] for r in mlaad}))

    # ---- model / optim
    model = Detector(DATA / "models" / args.backbone, args.grad_ckpt).cuda()
    bb = [p for p in model.backbone.parameters() if p.requires_grad]
    hd = list(model.head.parameters()) + [model.layer_w]
    opt = torch.optim.AdamW([{"params": bb, "lr": args.lr_backbone}, {"params": hd, "lr": args.lr_head}], weight_decay=0.01)
    steps_per_epoch = args.samples_per_epoch // args.batch
    total = steps_per_epoch * args.epochs
    warm = max(1, int(args.warmup_frac * total))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total))))
    log.info("backbone %s: %.1fM params (%.1fM trainable) | steps/epoch %d, total %d",
             args.backbone, sum(p.numel() for p in model.parameters()) / 1e6,
             sum(p.numel() for p in model.parameters() if p.requires_grad) / 1e6, steps_per_epoch, total)

    state = {"epoch": 0, "step_in_epoch": 0, "global_step": 0, "best_eer": 1.0, "time_used": 0.0, "history": []}
    last = run_dir / "last.pt"
    if args.resume and last.exists():
        ck = torch.load(last, map_location="cuda", weights_only=False)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        state = ck["state"]
        log.info("RESUMED from %s: epoch %d step %d (global %d), time used %.2f h, best val EER %.4f",
                 last, state["epoch"], state["step_in_epoch"], state["global_step"], state["time_used"] / 3600, state["best_eer"])

    def save_last(reason):
        atomic_save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                     "state": state, "args": vars(args)}, last)
        log.info("checkpoint last.pt (%s) epoch %d step %d", reason, state["epoch"], state["step_in_epoch"])

    stop = {"flag": False}

    def on_signal(sig, _):
        log.warning("signal %s: will checkpoint and exit after this step", sig)
        stop["flag"] = True
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    ds = TrainSet(train_rows, args.seed)
    t_session = time.time()
    t_last_ckpt = time.time()
    time_base = state["time_used"]
    model.train()
    while state["epoch"] < args.epochs:
        ep = state["epoch"]
        order = np.random.default_rng([args.seed, ep]).choice(len(train_rows), steps_per_epoch * args.batch, p=w)
        keys = [(int(i), ep, pos) for pos, i in enumerate(order)][state["step_in_epoch"] * args.batch:]
        dl = DataLoader(ds, batch_size=args.batch, sampler=keys, num_workers=args.workers,
                        pin_memory=True, drop_last=True, prefetch_factor=4, persistent_workers=False)
        run_loss, run_n, t0 = 0.0, 0, time.time()
        for x, y in dl:
            x, y = x.cuda(non_blocking=True), y.cuda(non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(x)
            loss = nn.functional.cross_entropy(logits, y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            state["step_in_epoch"] += 1
            state["global_step"] += 1
            run_loss += loss.item()
            run_n += 1
            state["time_used"] = time_base + time.time() - t_session
            if state["global_step"] % args.log_every == 0:
                dt = time.time() - t0
                log.info("ep %d step %d/%d loss %.4f gnorm %.2f lr %.2e | %.1f samples/s | gpu mem %.1f GB | %.2f h used",
                         ep, state["step_in_epoch"], steps_per_epoch, run_loss / run_n, gn, sched.get_last_lr()[0],
                         run_n * args.batch / dt, torch.cuda.max_memory_allocated() / 2**30, state["time_used"] / 3600)
                with open(run_dir / "metrics.jsonl", "a") as f:
                    f.write(json.dumps({"type": "train", "epoch": ep, "step": state["global_step"],
                                        "loss": run_loss / run_n, "time_h": state["time_used"] / 3600}) + "\n")
                run_loss, run_n, t0 = 0.0, 0, time.time()
            if time.time() - t_last_ckpt > args.ckpt_minutes * 60:
                save_last("timer")
                t_last_ckpt = time.time()
            if stop["flag"] or state["time_used"] > args.max_hours * 3600 or \
                    (args.max_steps and state["global_step"] >= args.max_steps):
                save_last("stop: signal" if stop["flag"] else "stop: limit")
                log.info("stopped at epoch %d step %d", ep, state["step_in_epoch"])
                return
        # ---- end of epoch: evaluate, select, checkpoint
        res = evaluate(model, eval_sets, args)
        v = float(np.mean([res[k]["eer"] for k in select]))
        rec = {"type": "eval", "epoch": ep, "step": state["global_step"], "time_h": state["time_used"] / 3600, **res}
        state["history"].append(rec)
        with open(run_dir / "metrics.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        for name, m in res.items():
            if name == "mlaad_fake":
                log.info("EVAL ep %d %-14s det.rate %.4f n=%d (%.0fs) | per model %s", ep, name, m["det_rate"], m["n"],
                         m["sec"], " ".join(f"{k}={v:.2f}" for k, v in m["per_model"].items()))
                continue
            log.info("EVAL ep %d %-14s EER %.4f AUC %.4f balAcc %.4f n=%d (%.0fs)%s", ep, name, m["eer"], m["auc"], m["bal_acc"],
                     m["n"], m["sec"], "" if name != "heldout_asv5" else
                     " | per-attack EER " + " ".join(f"{k[4:]}={m[k]:.3f}" for k in m if k.startswith("eer_")))
        if v < state["best_eer"]:
            state["best_eer"] = v
            atomic_save({"model": model.state_dict(), "epoch": ep, "metrics": res, "args": vars(args)}, run_dir / "best.pt")
            log.info("new best selection EER %.4f (%s) -> best.pt", v, "+".join(select))
        state["epoch"] += 1
        state["step_in_epoch"] = 0
        save_last("epoch end")
        t_last_ckpt = time.time()
    log.info("done: %d epochs, best val EER %.4f, %.2f h", args.epochs, state["best_eer"], state["time_used"] / 3600)


if __name__ == "__main__":
    main()
