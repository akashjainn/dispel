"""Score every ElevenLabs avenue with the release pipeline (v4p6: neural term + fused LLR) against a real pool
(NSA LJRealResampled 242 + teammates' real 100 + Akash 7, from results/team_feats.csv, same pipeline).
Per avenue: median neural / fused, minDCF vs the real pool (instructions' cost), share caught at the NSA-LJ 1% FA point.
Cache: results/el_eval_cache.csv (per file). Out: results/el_avenues.md"""
import csv, glob, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "dispel_pr8fix"))
from ml.fit_fusion import min_dcf
items = []
if (R / "data/el_matrix/meta.csv").exists():
    for r in csv.DictReader(open(R / "data/el_matrix/meta.csv")): items.append((r["avenue"], int(r["label"]), r["file"]))
if (R / "data/consent/sts/meta.csv").exists():
    for r in csv.DictReader(open(R / "data/consent/sts/meta.csv")): items.append(("sts_" + r["model"].replace("eleven_", "").replace("_sts_v2", ""), 1, r["file"]))
for r in csv.DictReader(open(R / "data/el_stock/meta.csv")): items.append(("stock_tts_" + r["model"].replace("eleven_", ""), 1, r["file"]))
for p in sorted((R / "data/el_frontier").rglob("*.mp3")): items.append(("frontier_tts", 1, str(p.relative_to(R))))
for r in csv.DictReader(open(R / "data/consent/team_gen/meta.csv")): items.append(("ivc_clone_generated", 1, r["file"]))
for p in sorted(glob.glob(str(R / "data/consent/team/fake/*.wav"))): items.append(("ivc_clone_teammate_given", 1, str(Path(p).relative_to(R))))
cp = R / "results/el_eval_cache.csv"
cache = pd.read_csv(cp) if cp.exists() else pd.DataFrame(columns=["file", "nn", "llr"])
done = set(cache.file)
todo = [it for it in items if it[2] not in done]
print(len(items), "items,", len(todo), "to score", flush=True)
if todo:
    from hearsay.orchestrator import Pipeline
    from hearsay import audio as A
    pipe = Pipeline(str(R / "data/release/v4p6"), profile="nsa")
    rows = []
    for i, (av, y, f) in enumerate(todo):
        p = R / f
        try:
            if p.suffix in (".pcm", ".ulaw"):
                tmp = Path(tempfile.gettempdir()) / (p.stem + "_conv.wav")
                args = ["-f", "s16le", "-ar", "16000", "-ac", "1"] if p.suffix == ".pcm" else ["-f", "mulaw", "-ar", "8000", "-ac", "1"]
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args, "-i", str(p), str(tmp)], check=True); p = tmp
            x, info = A.load(str(p)); res, fu = pipe._run(x, info)
            rows.append({"file": f, "nn": res["dl_detector"]["features"]["v3"], "llr": fu["llr_raw"]})
        except Exception as e:
            print("fail", f, e, flush=True)
        if i % 50 == 0: print(i, flush=True); pd.concat([cache, pd.DataFrame(rows)]).to_csv(cp, index=False)
    cache = pd.concat([cache, pd.DataFrame(rows)]); cache.to_csv(cp, index=False)
S = pd.DataFrame(items, columns=["avenue", "label", "file"]).merge(cache, on="file")
T = pd.read_csv(R / "results/team_feats.csv")
reals = T[(T.label == 0)][["set", "v3", "llr_v4p6"]].rename(columns={"v3": "nn", "llr_v4p6": "llr"})
lj = reals[reals.set == "nsa_lj"]; t_nn, t_llr = np.percentile(lj.nn, 99), np.percentile(lj.llr, 99)
lines = ["| avenue | n | neural median | fused median | neural minDCF | fused minDCF | caught @1% LJ FA: neural | fused |", "|---|---|---|---|---|---|---|---|"]
out = []
for av, g in S.groupby("avenue"):
    if g.label.iloc[0] == 0:
        lines.append(f"| {av} (REAL, false-alarm check) | {len(g)} | {g.nn.median():+.1f} | {g.llr.median():+.1f} | - | - | flagged {np.mean(g.nn > t_nn):.2f} | flagged {np.mean(g.llr > t_llr):.2f} |"); continue
    y = np.r_[np.ones(len(g)), np.zeros(len(reals))]
    a, b = min_dcf(np.r_[g.nn, reals.nn], y), min_dcf(np.r_[g.llr, reals.llr], y)
    out.append((b, f"| {av} | {len(g)} | {g.nn.median():+.1f} | {g.llr.median():+.1f} | {a:.3f} | {b:.3f} | {np.mean(g.nn > t_nn):.2f} | {np.mean(g.llr > t_llr):.2f} |"))
lines += [l for _, l in sorted(out, reverse=True)]
lines.append(f"\nreal pool: {len(reals)} clips (NSA LJ {len(lj)}, teammates+Akash {len(reals) - len(lj)}); LJ 99th pct: neural {t_nn:+.1f}, fused {t_llr:+.1f}. Sorted worst fused first.")
(R / "results/el_avenues.md").write_text("\n".join(lines) + "\n"); print("\n".join(lines))
