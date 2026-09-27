"""Convert new v4 data to 16 kHz mono PCM WAV with ffmpeg (NSA's resampler) and write split lists.
Sources: data/el_stock (ElevenLabs stock voices; split by voice), data/kokoro (Kokoro voices; split by voice),
data/el_frontier (ElevenLabs eleven_v3 / multilingual_v2; test only), data/teammates (eval only).
Out: data/v4new/<source>/..., data/splits/v4_new_train.csv, data/splits/v4_new_eval.csv (path,label,group,source)"""
import csv, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path.home() / "hackgt"; DATA = ROOT / "data"
OUT = DATA / "v4new"

def conv(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
                        str(dst)], check=True)
    return dst

jobs, train, ev = [], [], []
for name, group in (("el_stock", "elevenlabs_stock"), ("kokoro", "kokoro"), ("el_frontier", "elevenlabs_frontier")):
    meta = DATA / name / "meta.csv"
    if not meta.exists():
        continue
    for r in csv.DictReader(open(meta)):
        src = ROOT / r["file"]
        dst = OUT / name / Path(r["file"]).relative_to(f"data/{name}").with_suffix(".wav")
        row = {"path": str(dst.relative_to(DATA)), "label": 1, "group": group if name != "el_stock" else group,
               "source": "el" if name.startswith("el") else "kokoro", "split": r["split"],
               "detail": r.get("model") or r.get("voice")}
        jobs.append((src, dst))
        (train if r["split"] == "train" else ev).append(row)
for p in sorted((DATA / "teammates").glob("*.wav")):
    dst = conv(p, OUT / "teammates" / p.name)  # already 16 kHz; copied through ffmpeg for uniformity
    ev.append({"path": str(dst.relative_to(DATA)), "label": int("fake" in p.name), "group": "teammates",
               "source": "teammates", "split": "eval", "detail": p.name.split("_")[0]})
with ThreadPoolExecutor(8) as ex:
    list(ex.map(lambda a: conv(*a), jobs))
for fn, rows in (("v4_new_train.csv", train), ("v4_new_eval.csv", ev)):
    with open(DATA / "splits" / fn, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "label", "group", "source", "split", "detail"])
        w.writeheader(); w.writerows(rows)
    print(fn, len(rows))
