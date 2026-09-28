"""Metrics for bench_itw.py: AUC, EER and the challenge minDCF (P(synthetic) 0.3, false alarm 4x a miss; same definition
as diffssd_eval.py), with 95% CIs from a speaker-level bootstrap (the 16 speakers are resampled with replacement,
2,000 times), paired differences against v5c, and a per-speaker table. Writes results/bench_itw/metrics.md + .json."""
import csv, json, sys
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score, roc_curve

R = Path.home() / "hackgt/results/bench_itw"
P = 0.3
NAMES = {"v5c": "v5c (ours, shipped)", "ad1b": "AntiDeepfake XLS-R-1B (authors' whole-clip protocol)",
         "ad1b_win": "AntiDeepfake XLS-R-1B (our 3 x 4 s windows)", "admms": "AntiDeepfake MMS-300M (whole clip)",
         "stock": "mo-thecreator wav2vec2-base (stock, server stand-in)"}


def mindcf(y, s):
    t = np.concatenate([[-np.inf], np.unique(s)])
    r, f = np.sort(s[y == 0]), np.sort(s[y == 1])
    pfa = 1 - np.searchsorted(r, t, side="right") / len(r)
    pmiss = np.searchsorted(f, t, side="right") / len(f)
    return float(np.min((4 * (1 - P) * pfa + P * pmiss) / min(4 * (1 - P), P)))


def eer(y, s):
    fpr, tpr, _ = roc_curve(y, s); fnr = 1 - tpr; i = int(np.nanargmin(np.abs(fnr - fpr)))
    return float((fpr[i] + fnr[i]) / 2)


def metrics(y, s):
    return {"auc": float(roc_auc_score(y, s)), "eer": eer(y, s), "mindcf": mindcf(y, s)}


def load(name):
    rows = list(csv.DictReader(open(R / f"{name}.csv")))
    return {r["file"]: (r["speaker"], int(r["label"]), float(r["score"])) for r in rows}


models = [m for m in NAMES if (R / f"{m}.csv").exists()]
data = {m: load(m) for m in models}
files = sorted(set.intersection(*(set(d) for d in data.values())))
spk = np.array([data[models[0]][f][0] for f in files]); y = np.array([data[models[0]][f][1] for f in files])
S = {m: np.array([data[m][f][2] for f in files]) for m in models}
speakers = sorted(set(spk)); idx = {s: np.where(spk == s)[0] for s in speakers}
print(f"{len(files)} clips scored by all of {models}; {int(y.sum())} spoof, {len(speakers)} speakers", flush=True)

rng = np.random.default_rng(0); B = 2000
boot = {m: {k: [] for k in ("auc", "eer", "mindcf")} for m in models}
diff = {m: {k: [] for k in ("auc", "eer", "mindcf")} for m in models if m != "v5c"}
for _ in range(B):
    ii = np.concatenate([idx[s] for s in rng.choice(speakers, len(speakers))])
    if y[ii].min() == y[ii].max():
        continue
    mv = {m: metrics(y[ii], S[m][ii]) for m in models}
    for m in models:
        for k in boot[m]:
            boot[m][k].append(mv[m][k])
    for m in diff:
        for k in diff[m]:
            diff[m][k].append(mv[m][k] - mv["v5c"][k])

ci = lambda a: (float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5)))
res = {"n_clips": len(files), "n_spoof": int(y.sum()), "speakers": speakers, "models": {}}
L = [f"In-the-Wild, 16 held-out speakers: {len(files):,} clips ({int(y.sum()):,} synthetic). 95% CIs: speaker-level bootstrap.", "",
     "| Model | AUC | EER | minDCF (P 0.3, FA 4x) |", "|---|---|---|---|"]
for m in models:
    v = metrics(y, S[m]); c = {k: ci(boot[m][k]) for k in v}
    res["models"][m] = {"name": NAMES[m], **v, "ci": c}
    L.append(f"| {NAMES[m]} | {v['auc']:.4f} ({c['auc'][0]:.3f}-{c['auc'][1]:.3f}) | {100*v['eer']:.2f}% "
             f"({100*c['eer'][0]:.1f}-{100*c['eer'][1]:.1f}) | {v['mindcf']:.3f} ({c['mindcf'][0]:.3f}-{c['mindcf'][1]:.3f}) |")
L += ["", "Paired difference, model minus v5c (95% CI; an interval that excludes 0 is a real difference):", "",
      "| Model | AUC | EER (points) | minDCF |", "|---|---|---|---|"]
for m in diff:
    c = {k: ci(diff[m][k]) for k in diff[m]}; res["models"][m]["diff_vs_v5c_ci"] = c
    L.append(f"| {NAMES[m]} | {c['auc'][0]:+.3f} to {c['auc'][1]:+.3f} | {100*c['eer'][0]:+.1f} to {100*c['eer'][1]:+.1f} | "
             f"{c['mindcf'][0]:+.3f} to {c['mindcf'][1]:+.3f} |")
L += ["", "Per speaker, EER (speakers with at least 10 real and 10 synthetic clips):", "",
      "| Speaker | real | synthetic | " + " | ".join(models) + " |", "|---|---|---|" + "---|" * len(models)]
res["per_speaker"] = {}
for s in speakers:
    ii = idx[s]; nr, nf = int((y[ii] == 0).sum()), int(y[ii].sum())
    if min(nr, nf) < 10:
        continue
    e = {m: eer(y[ii], S[m][ii]) for m in models}; res["per_speaker"][s] = {"real": nr, "spoof": nf, **e}
    L.append(f"| {s} | {nr} | {nf} | " + " | ".join(f"{100*e[m]:.1f}%" for m in models) + " |")
(R / "metrics.md").write_text("\n".join(L) + "\n"); (R / "metrics.json").write_text(json.dumps(res, indent=1))
print("\n".join(L))
