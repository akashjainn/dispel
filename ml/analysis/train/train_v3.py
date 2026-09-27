"""v3: XLS-R fine-tune on DiffSSD (set==train) + 25% of the v2 source mix, robust to noise and time-stretch.

Init: data/release/v2/best.pt (read-only; same Detector as train.py, loaded exactly). Feature encoder frozen.
Data (per class 50/50; each class: diffssd 0.75 + v2 mix x 0.25):
  diffssd: train_val_test_splits.csv set==train only, clips >= 3.0 s (header duration). group = method_name, so every
           generator gets the same sampling mass (CAP) - this caps OpenVoiceV2 (10,000 train clips) to the others'
           share; reals grouped ljspeech / librispeech (equal mass).
  v2 mix : same lists, exclusions and assertions as train.py v2 (ITW, ASVspoof 5, MLAAD-tiny, M-AILABS, VoxPopuli,
           MLAAD-full), with v2's per-class shares scaled by 0.25.
Augmentation: v3_aug.train_aug on every sample (both classes, all sources).
Validation: data/splits/v3_val.csv (DiffSSD set==val) from the fixed cache data/eval_cache/v3_val/{clean,atempo,pv};
  minDCF on raw logit differences. best.pt = lowest mean of minDCF@0.3 over clean and atempo.
"""
import argparse
import csv
import json
import logging
import math
import signal
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).parent))
from train import CROP, DATA, Detector, atomic_save, eer, load_audio, read_rows, sampling_weights  # noqa: E402
from v3_aug import train_aug  # noqa: E402

log = logging.getLogger("v3")
V2_REAL = {"itw": 0.35, "asv5": 0.15, "mlaad": 0.10, "mailabs": 0.15, "voxpopuli": 0.25}
V2_FAKE = {"itw": 0.30, "asv5": 0.15, "mlaad": 0.15, "mlaad_full": 0.40}
CONDS = ("clean", "atempo", "pv")


def v2_rows():
    """v2's training pool, with train.py's guards."""
    rows = read_rows("ft_itw_train.csv") + read_rows("ft_asv5_train.csv")
    test_files = {r["path"] for n in ("mlaad_test_unseen.csv", "mlaad_test_seen.csv", "mlaad_test_unseen_ext.csv",
                                      "mlaad_val.csv") for r in read_rows(n)}
    ml = read_rows("mlaad_train.csv")
    held = {r["group"] for r in read_rows("mlaad_test_unseen.csv") if r["label"] == 1}
    assert not {r["path"] for r in ml} & test_files and not {r["group"] for r in ml} & held
    vx = read_rows("vox2_train.csv")
    assert all(r["label"] == 0 for r in vx) and not {r["group"] for r in vx} & {r["group"] for r in read_rows("vox2_heldout.csv")}
    rows += ml + vx
    for src, lst, lab in (("mailabs", "mailabs_train.csv", 0), ("mlaad_full", "mlaad_full_train.csv", 1)):
        rr = read_rows(lst)
        assert all(r["label"] == lab and r["source"] == src for r in rr) and not {r["path"] for r in rr} & test_files
        rows += rr
    test_spk = {l.strip() for l in open(DATA / "splits/itw_test_speakers.txt") if l.strip()}
    val_spk = {l.strip() for l in open(DATA / "splits/ft_itw_val_speakers.txt") if l.strip()}
    assert not {r["group"] for r in rows if r["source"] == "itw"} & (test_spk | val_spk)
    return rows


def diffssd_rows():
    dur = {r["filename"]: float(r["dur"]) for r in csv.DictReader(open(DATA.parent / "results/scores/diffssd_profile_headers.csv"))}
    rows, short = [], 0
    for r in csv.DictReader(open(DATA / "diffssd_hf/train_val_test_splits.csv")):
        if r["set"] != "train":
            continue
        if dur[r["filename"]] < 3.0:
            short += 1
            continue
        rows.append({"path": "diffssd/" + r["filename"], "label": int(r["target"]), "group": r["method_name"], "source": "diffssd"})
    return rows, short


class TrainSet(Dataset):
    def __init__(self, rows, seed):
        self.rows, self.seed = rows, seed

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, key):
        i, epoch, pos = key
        rng = np.random.default_rng([self.seed, epoch, pos])
        r = self.rows[i]
        x = load_audio(DATA / r["path"])
        if len(x) > 20 * 16000:  # long clips: random 20 s region before trimming (speed)
            s = int(rng.integers(0, len(x) - 20 * 16000 + 1))
            x = x[s:s + 20 * 16000]
        return torch.from_numpy(train_aug(x, rng)), r["label"]


class ValSet(Dataset):
    def __init__(self, ids, cond):
        self.ids, self.cond = ids, cond

    def __len__(self):
        return len(self.ids)

    def __getitem__(self, j):
        i = self.ids[j]
        x = np.load(DATA / "eval_cache/v3_val" / self.cond / f"{i}.npy")
        if len(x) < CROP:
            x = np.tile(x, CROP // max(len(x), 1) + 1)[:CROP]
        k = min(3, len(x) // CROP)
        return torch.from_numpy(np.stack([x[q * CROP:(q + 1) * CROP] for q in range(k)])), j


def val_collate(b):
    return torch.cat([t[0] for t in b]), [len(t[0]) for t in b], [t[1] for t in b]


def min_dcf(y, s, P):
    """min over t of [4 P(real) FPR(t) + P(syn) FNR(t)] / min(4 P(real), P(syn)); flagged = s > t. Returns (dcf, t)."""
    t = np.concatenate([[-np.inf], np.unique(s)])
    r, f = np.sort(s[y == 0]), np.sort(s[y == 1])
    fpr = 1 - np.searchsorted(r, t, side="right") / len(r)
    fnr = np.searchsorted(f, t, side="right") / len(f)
    d = (4 * (1 - P) * fpr + P * fnr) / min(4 * (1 - P), P)
    i = int(np.argmin(d))
    return float(d[i]), float(t[i])


def val_metrics(y, g, s):
    d3, t3 = min_dcf(y, s, 0.3)
    return {"mindcf_0.3": d3, "mindcf_0.05": min_dcf(y, s, 0.05)[0], "eer": eer(y, s),
            "fpr_lj": float(np.mean(s[g == "ljspeech"] > t3)), "fpr_libri": float(np.mean(s[g == "librispeech"] > t3)),
            "fnr": float(np.mean(s[y == 1] <= t3)), "t": t3}


@torch.no_grad()
def score_val(model, ids, workers):
    model.eval()
    out = {}
    for c in CONDS:
        s = np.zeros(len(ids))
        for x, ks, ids_ in DataLoader(ValSet(ids, c), batch_size=12, num_workers=workers, collate_fn=val_collate):
            with torch.autocast("cuda", dtype=torch.bfloat16):
                lg = model(x.cuda(non_blocking=True)).float()
            d = (lg[:, 1] - lg[:, 0]).cpu().numpy()
            o = 0
            for k, i in zip(ks, ids_):
                s[i] = d[o:o + k].mean()
                o += k
        out[c] = s
    model.train()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v3_diffssd")
    ap.add_argument("--init", default=str(DATA / "release/v2/best.pt"))
    ap.add_argument("--epochs", type=int, default=7, help="an 'epoch' = one eval interval")
    ap.add_argument("--samples-per-epoch", type=int, default=28000)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr-backbone", type=float, default=2e-6)
    ap.add_argument("--lr-head", type=float, default=1e-4)
    ap.add_argument("--warmup-frac", type=float, default=0.03)
    ap.add_argument("--diffssd-share", type=float, default=0.75)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-hours", type=float, default=4.5)
    ap.add_argument("--ckpt-minutes", type=float, default=20.0)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--val-stride", type=int, default=1, help="smoke tests only")
    args = ap.parse_args()
    run_dir = DATA / "checkpoints" / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(run_dir / "train.log"), logging.StreamHandler(sys.stdout)])
    log.info("args %s", json.dumps(vars(args)))
    torch.manual_seed(args.seed)

    ds_rows, short = diffssd_rows()
    val = read_rows("v3_val.csv")
    assert not {r["path"] for r in ds_rows} & {r["path"] for r in val}
    rows = ds_rows + v2_rows()
    k = args.diffssd_share
    class_mix = {0: {"diffssd": k, **{s: v * (1 - k) for s, v in V2_REAL.items()}},
                 1: {"diffssd": k, **{s: v * (1 - k) for s, v in V2_FAKE.items()}}}
    w = sampling_weights(rows, None, False, class_mix)
    agg = {}
    for r, wi in zip(rows, w):
        key = (r["source"], r["label"], r["group"] if r["source"] == "diffssd" else "")
        agg.setdefault(key, [0, 0.0])
        agg[key][0] += 1
        agg[key][1] += wi
    log.info("diffssd train: %d clips kept, %d dropped (< 3.0 s)", len(ds_rows), short)
    for (src, lab, g), (n, m) in sorted(agg.items()):
        log.info("pool %-10s %-5s %-12s n=%6d  sampling mass %.4f", src, "spoof" if lab else "bona", g, n, m)
    vid = list(range(0, len(val), args.val_stride))
    yv = np.array([val[i]["label"] for i in vid])
    gv = np.array([val[i]["group"] for i in vid])
    log.info("val: %d clips (%d real) from data/splits/v3_val.csv", len(vid), int((yv == 0).sum()))

    model = Detector(DATA / "models/xls-r-300m", True).cuda()
    ck = torch.load(args.init, map_location="cpu", weights_only=False)
    model.load_state_dict(ck["model"])  # strict: exact architecture match
    log.info("initialized from %s (epoch %s)", args.init, ck.get("epoch"))
    bb = [p for p in model.backbone.parameters() if p.requires_grad]
    hd = list(model.head.parameters()) + [model.layer_w]
    opt = torch.optim.AdamW([{"params": bb, "lr": args.lr_backbone}, {"params": hd, "lr": args.lr_head}], weight_decay=0.01)
    spe = args.samples_per_epoch // args.batch
    total = spe * args.epochs
    warm = max(1, int(args.warmup_frac * total))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total))))
    # class weights = inverse sampled class frequency (sampling is 50/50 by construction, so ~1.0 each)
    ylab = np.array([r["label"] for r in rows])
    pc = np.array([w[ylab == c].sum() for c in (0, 1)])
    cw = torch.tensor(1 / (2 * pc), dtype=torch.float32).cuda()
    log.info("steps/epoch %d, total %d, warmup %d | class weights %s", spe, total, warm, cw.tolist())

    state = {"epoch": 0, "step_in_epoch": 0, "global_step": 0, "best": 9.0, "time_used": 0.0, "history": []}
    last = run_dir / "last.pt"
    if args.resume and last.exists():
        c = torch.load(last, map_location="cuda", weights_only=False)
        model.load_state_dict(c["model"])
        opt.load_state_dict(c["opt"])
        sched.load_state_dict(c["sched"])
        state = c["state"]
        log.info("RESUMED epoch %d step %d", state["epoch"], state["step_in_epoch"])

    def save_last(why):
        atomic_save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "state": state,
                     "args": vars(args)}, last)
        log.info("checkpoint last.pt (%s)", why)

    stop = {"f": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(f=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(f=True))
    ds = TrainSet(rows, args.seed)
    t_sess, t_ck, base = time.time(), time.time(), state["time_used"]
    model.train()
    while state["epoch"] < args.epochs:
        ep = state["epoch"]
        order = np.random.default_rng([args.seed, ep]).choice(len(rows), spe * args.batch, p=w)
        keys = [(int(i), ep, pos) for pos, i in enumerate(order)][state["step_in_epoch"] * args.batch:]
        dl = DataLoader(ds, batch_size=args.batch, sampler=keys, num_workers=args.workers, pin_memory=True,
                        drop_last=True, prefetch_factor=4)
        rl, rn, t0 = 0.0, 0, time.time()
        for x, y in dl:
            x, y = x.cuda(non_blocking=True), y.cuda(non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                lg = model(x)
            loss = nn.functional.cross_entropy(lg.float(), y, weight=cw)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            state["step_in_epoch"] += 1
            state["global_step"] += 1
            rl += loss.item()
            rn += 1
            state["time_used"] = base + time.time() - t_sess
            if state["global_step"] % args.log_every == 0:
                dt = time.time() - t0
                rem = (total - state["global_step"]) * args.batch / (rn * args.batch / dt) / 3600
                log.info("ep %d step %d/%d loss %.4f gnorm %.2f lr %.2e | %.1f samples/s | %.2f h used, ~%.2f h train left",
                         ep, state["step_in_epoch"], spe, rl / rn, gn, sched.get_last_lr()[0], rn * args.batch / dt,
                         state["time_used"] / 3600, rem)
                with open(run_dir / "metrics.jsonl", "a") as f:
                    f.write(json.dumps({"type": "train", "epoch": ep, "step": state["global_step"], "loss": rl / rn,
                                        "time_h": state["time_used"] / 3600}) + "\n")
                rl, rn, t0 = 0.0, 0, time.time()
            if time.time() - t_ck > args.ckpt_minutes * 60:
                save_last("timer")
                t_ck = time.time()
            if stop["f"] or state["time_used"] > args.max_hours * 3600 or (args.max_steps and state["global_step"] >= args.max_steps):
                save_last("stop")
                return
        t = time.time()
        sc = score_val(model, vid, args.workers)
        res = {c: val_metrics(yv, gv, sc[c]) for c in CONDS}
        sel = (res["clean"]["mindcf_0.3"] + res["atempo"]["mindcf_0.3"]) / 2
        np.savez(run_dir / f"val_scores_ep{ep}.npz", **sc)
        rec = {"type": "eval", "epoch": ep, "step": state["global_step"], "time_h": state["time_used"] / 3600, "select": sel, **res}
        state["history"].append(rec)
        with open(run_dir / "metrics.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        for c in CONDS:
            m = res[c]
            log.info("EVAL ep %d %-6s minDCF@0.3 %.3f @0.05 %.3f EER %.4f | FPR LJ %.3f Libri %.3f FNR %.3f", ep, c,
                     m["mindcf_0.3"], m["mindcf_0.05"], m["eer"], m["fpr_lj"], m["fpr_libri"], m["fnr"])
        log.info("EVAL ep %d selection (mean minDCF@0.3 clean+atempo) %.4f (%.0fs)", ep, sel, time.time() - t)
        if sel < state["best"]:
            state["best"] = sel
            atomic_save({"model": model.state_dict(), "epoch": ep, "metrics": res, "args": vars(args)}, run_dir / "best.pt")
            log.info("new best %.4f -> best.pt", sel)
        state["epoch"] += 1
        state["step_in_epoch"] = 0
        save_last("epoch end")
        t_ck = time.time()
    log.info("done: best selection %.4f, %.2f h", state["best"], state["time_used"] / 3600)


if __name__ == "__main__":
    main()
