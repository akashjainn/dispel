"""v5 data: consenting teammates' real clips + ElevenLabs clones of them, split by SPEAKER into train / held-out.
Everything converted to 16 kHz mono wav with ffmpeg (same as other sources; codec augmentation in training covers mp3).
Out: data/v5team/{real,given_fake,gen_fake}/..., data/splits/v5_team.csv (path,label,group,source,split,detail,spk)"""
import csv, random, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
D = Path.home() / "hackgt/data"; C = D / "consent"; O = D / "v5team"
spks = sorted({p.name.rsplit("_", 1)[0] for p in (C / "team/real").glob("*.wav")})
rng = random.Random(5); order = spks[:]; rng.shuffle(order)
held = set(order[:5]); split = {s: ("eval" if s in held else "train") for s in spks}
jobs, rows = [], []
for kind, lab, src in (("real", 0, "team_real"), ("fake", 1, "team_clone")):
    for p in sorted((C / f"team/{kind}").glob("*.wav")):
        s = p.name.rsplit("_", 1)[0]; dst = O / ("real" if lab == 0 else "given_fake") / p.name
        jobs.append((p, dst)); rows.append([str(dst.relative_to(D)), lab, "team_" + kind, src, split[s], "provided", s])
for r in csv.DictReader(open(C / "team_gen/meta.csv")):
    p = D.parent / r["file"]; dst = O / "gen_fake" / r["spk"] / (p.stem + ".wav")
    jobs.append((p, dst)); rows.append([str(dst.relative_to(D)), 1, "team_clone", "team_clone", split[r["spk"]], r["model"], r["spk"]])
def conv(a):
    src, dst = a; dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)], check=True)
with ThreadPoolExecutor(8) as ex: list(ex.map(conv, jobs))
with open(D / "splits/v5_team.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["path", "label", "group", "source", "split", "detail", "spk"]); w.writerows(rows)
print("held-out speakers:", sorted(held)); print("train speakers:", sorted(set(spks) - held))
import collections; print(collections.Counter((r[4], r[1]) for r in rows))
