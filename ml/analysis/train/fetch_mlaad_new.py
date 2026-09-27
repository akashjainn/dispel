"""Fetch the MLAAD English models our training lacks (150 clips each, seeded). Token read from the HF cache, never printed."""
import json, os, random, subprocess, urllib.parse, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
T = (Path.home() / ".cache/huggingface/token").read_text().strip()
O = Path.home() / "hackgt/data/mlaad_new"; O.mkdir(parents=True, exist_ok=True)
MISSING = [l for l in open("/tmp/mlaad_missing.txt").read().split(";") if l.strip()]
def api(path):
    r = urllib.request.Request("https://huggingface.co/api/datasets/mueller91/MLAAD/tree/main/" + urllib.parse.quote(path), headers={"Authorization": f"Bearer {T}"})
    return json.load(urllib.request.urlopen(r, timeout=60))
jobs = []
for m in MISSING:
    files = sorted(x["path"] for x in api(f"fake/en/{m}") if x["type"] == "file" and x["path"].endswith((".wav", ".flac", ".mp3")))
    random.Random(f"mlaad-{m}").shuffle(files)
    for p in files[:150]: jobs.append(p)
    print(m, len(files), flush=True)
def get(p):
    dst = O / p.replace("fake/en/", "", 1)
    if dst.exists(): return
    dst.parent.mkdir(parents=True, exist_ok=True)
    url = "https://huggingface.co/datasets/mueller91/MLAAD/resolve/main/" + urllib.parse.quote(p)
    subprocess.run(["curl", "-sfL", "-H", f"Authorization: Bearer {T}", "-o", str(dst), url])
with ThreadPoolExecutor(8) as ex: list(ex.map(get, jobs))
print("DONE", len(jobs), flush=True)
