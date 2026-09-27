"""evalbundle2: every held-out ElevenLabs/voice-changer/isolator clip plus a sample (<=150 per group source) of the v5c
held-out slices, as 16 kHz wav + manifest2.csv (file,set,label,detail). Items a v5b/v5c model trained on are excluded."""
import csv, subprocess, random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
R = Path.home() / "hackgt"; O = R / "evalbundle"; (O / "b").mkdir(parents=True, exist_ok=True)
train_spk = {r["spk"] for r in csv.DictReader(open(R / "data/splits/v5_team.csv")) if r["split"] == "train"}
spk = lambda s: s.rsplit("_", 1)[0]
I = []
for r in csv.DictReader(open(R / "data/el_matrix/meta.csv")):
    if r["avenue"] == "isolator_real":
        if spk(r["text_id"]) not in train_spk: I.append(("EL_isolator_real", 0, R / r["file"], ""))
V = pd.read_csv(R / "data/splits/v5c_new.csv"); V = V[V.split == "eval"]
for (src, lab), g in V.groupby(["source", "label"]):
    g = g.sample(min(len(g), 300 if src in ("el", "commercial") else 150), random_state=0)
    for r in g.itertuples(): I.append((f"v5c_{src}", lab, R / "data" / r.path, r.detail.split("|")[0] if isinstance(r.detail, str) else ""))
def conv(a):
    i, (s, y, src, d) = a; dst = O / "b" / f"{i:05d}.wav"
    if not dst.exists():
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)], check=True)
    return {"file": f"b/{i:05d}.wav", "set": s, "label": y, "detail": d}
with ThreadPoolExecutor(6) as ex: rows = list(ex.map(conv, enumerate(I)))
M = pd.DataFrame(rows); M.to_csv(O / "manifest2.csv", index=False); print(M.groupby(["set", "label"]).size().to_string())
