"""Held-out evaluation bundle for the laptop: everything converted to 16 kHz mono PCM wav (ffmpeg), manifest.csv.
Sets: diffssd_test_holdout (200 per method, from the 20% v5b holdout), team_heldout, akash, nsa_lj_real, el_frontier,
libri_clone (100 f5 + 100 chatterbox + 100 real, eval speakers, clean)."""
import csv, random, subprocess, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
R = Path.home() / "hackgt"; O = R / "evalbundle"; (O / "a").mkdir(parents=True, exist_ok=True)
items = []
ho = list(csv.DictReader(open(R / "data/splits/v5b_diffssd_test_holdout.csv")))
by = {}
for r in ho: by.setdefault(r["method_name"], []).append(r)
for m, rr in sorted(by.items()):
    for r in random.Random(f"bundle-{m}").sample(rr, 200):
        items.append(("diffssd_test_holdout", int(r["target"]), R / "data/diffssd" / r["filename"], m))
t = pd.read_csv(R / "data/splits/v5_team.csv")
for r in t[t.split == "eval"].itertuples(): items.append(("team_heldout", r.label, R / "data" / r.path, r.detail))
for p in sorted(glob.glob(str(R / "data/consent/akash/real/*.wav"))): items.append(("akash", 0, Path(p), "real"))
for p in sorted(glob.glob(str(R / "data/consent/akash/fake/*/*.mp3"))): items.append(("akash", 1, Path(p), Path(p).parent.name))
for p in sorted(glob.glob(str(R / "data/nsa/LJRealResampled/resampled/*.wav"))): items.append(("nsa_lj_real", 0, Path(p), ""))
for p in sorted((R / "data/el_frontier").rglob("*.mp3")): items.append(("el_frontier", 1, p, ""))
plan = pd.read_csv(R / "data/clonesrc/plan.csv"); ev = sorted(plan.uid[plan.split == "eval"])
for k in ("f5", "chatterbox", "real"):
    for u in random.Random(f"bundle-{k}").sample(ev, 100):
        p = R / f"data/clones16/{k}/clean/{u}.wav"
        if p.exists(): items.append(("libri_clone", int(k != "real"), p, k))
def conv(a):
    i, (s, y, src, d) = a; dst = O / "a" / f"{i:05d}.wav"
    if not dst.exists():
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)], check=True)
    return {"file": f"a/{i:05d}.wav", "set": s, "label": y, "detail": d, "src": str(src.relative_to(R))}
with ThreadPoolExecutor(6) as ex: rows = list(ex.map(conv, enumerate(items)))
pd.DataFrame(rows).to_csv(O / "manifest.csv", index=False)
print(pd.DataFrame(rows).groupby(["set", "label"]).size())
