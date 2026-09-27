"""Paired pattern analysis: clone vs the same speaker's real recording of the same sentence.
For every interpretable feature (pitch/prosody, spectral, voice, rhythm, + duration/pauses) report per cloner and
condition: share of pairs where clone > real (0.5 = no systematic difference), median relative change, and the
UNPAIRED AUC (what a detector can actually use: it never sees the real twin). Eval + val speakers only for the AUC
(the detector's fusion never saw them); all speakers for the paired stats.
Usage: python clone_patterns.py <cloner> [...]   Out: results/clone_feats.csv, results/clone_patterns.txt"""
import csv, sys, warnings
from multiprocessing import Pool
from pathlib import Path
import numpy as np, pandas as pd, soundfile as sf
warnings.filterwarnings("ignore")
R = Path.home() / "hackgt"
sys.path.insert(0, str(R / "scratch/features"))
from pitch_features import pitch_features
from spectral import spectral_features
from rhythm import rhythm_features
from voice import voice_features
plan = {r["uid"]: r for r in csv.DictReader(open(R / "data/clonesrc/plan.csv"))}
CONDS = ("clean", "atempo")

def lead_trail(x, sr=16000):
    e = np.convolve(x ** 2, np.ones(160) / 160, mode="same"); db = 10 * np.log10(e + 1e-10)
    on = np.where(db > db.max() - 35)[0]
    if len(on) == 0: return {}
    dur = len(x) / sr; speech = (on[-1] - on[0]) / sr
    return {"dur_s": dur, "speech_s": speech, "lead_s": on[0] / sr, "trail_s": dur - on[-1] / sr}

def job(a):
    kind, c, uid = a
    x, sr = sf.read(R / f"data/clones16/{kind}/{c}/{uid}.wav", dtype="float32")
    o = {"kind": kind, "cond": c, "uid": uid, "spk": plan[uid]["spk"], "split": plan[uid]["split"],
         "chars": len(plan[uid]["text"])}
    for fn in (pitch_features, spectral_features, rhythm_features, voice_features, lead_trail):
        try: o.update(fn(x, sr) if fn is not lead_trail else fn(x))
        except Exception: pass
    if "speech_s" in o: o["chars_per_s"] = o["chars"] / max(o["speech_s"], 0.1)
    return o

if __name__ == "__main__":
    from sklearn.metrics import roc_auc_score
    cloners = sys.argv[1:]
    todo = []
    for kind in cloners + ["real"]:
        for c in CONDS:
            for p in sorted((R / f"data/clones16/{kind}/{c}").glob("*.wav")):
                todo.append((kind, c, p.stem))
    with Pool(8) as pool:
        df = pd.DataFrame(pool.map(job, todo, chunksize=8))
    df.to_csv(R / "results/clone_feats.csv", index=False)
    F = [c for c in df.columns if c not in ("kind", "cond", "uid", "spk", "split", "chars", "dur_s", "lead_s", "trail_s")]
    lines = []
    for cl in cloners:
        for c in CONDS:
            a = df[(df.kind == cl) & (df.cond == c)].set_index("uid"); b = df[(df.kind == "real") & (df.cond == c)].set_index("uid")
            u = a.index.intersection(b.index); ev = [x for x in u if plan[x]["split"] != "train"]
            lines.append(f"\n=== {cl} vs paired real, {c}: {len(u)} pairs ({len(ev)} eval/val)")
            lines.append(f"{'feature':20s} {'clone>real':>10s} {'median rel chg':>15s} {'unpaired AUC (eval)':>20s}")
            rows = []
            for f in F:
                if f not in a or a.loc[u, f].notna().mean() < 0.8: continue
                d = (a.loc[u, f] - b.loc[u, f]).dropna()
                rel = (d / b.loc[d.index, f].abs().replace(0, np.nan)).median()
                s = pd.concat([a.loc[ev, f], b.loc[ev, f]]); yy = np.r_[np.ones(len(ev)), np.zeros(len(ev))]
                k = s.notna().values
                auc = roc_auc_score(yy[k], s.values[k]) if k.sum() > 20 else np.nan
                rows.append((f, (d > 0).mean(), rel, auc))
            rows.sort(key=lambda r: -abs(r[3] - 0.5) if np.isfinite(r[3]) else 0)
            for f, gt, rel, auc in rows[:18]:
                lines.append(f"{f:20s} {gt:10.2f} {rel:+15.1%} {auc:20.3f}")
    txt = "\n".join(lines); print(txt); (R / "results/clone_patterns.txt").write_text(txt)
