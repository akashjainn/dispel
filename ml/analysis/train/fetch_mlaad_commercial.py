"""Extra clips (up to 600 per system) of the COMMERCIAL / API TTS systems in MLAAD English - NSA tip: vendor diversity
(ElevenLabs, Polly, Grok, Gemini...). Skips files already present in data/mlaad_full. Token from HF cache, never printed."""
import json, random, subprocess, urllib.parse, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
T = (Path.home() / ".cache/huggingface/token").read_text().strip(); R = Path.home() / "hackgt"
O = R / "data/mlaad_commercial"; O.mkdir(parents=True, exist_ok=True)
SYS = ["Cartesia.ai (Sonic-3)", "DeepGram", "ElevenLabs-Turbo-v2.5", "ElevenLabs-v2-Multilingual", "ElevenLabs-v3", "Gemini-3.1-Flash-TTS",
       "Hume TADA-3B-ML", "Inworld-TTS-2", "MiniMax-Speech-2.8-Turbo", "OpenAI TTS-1 HD", "Rime-Coda", "Smallest-Lightning-v3.1",
       "minimax_speech-02-turbo", "minimax_speech-2.6-hd", "Resemble.ai (April 12th, 2025)", "Edge-TTS", "PrimeTTS", "Ringg Squirrel TTS v1.0"]
have = {l.split(",")[0].split("/")[-1] for l in open(R / "data/splits/mlaad_full_train.csv") if "/en/" in l}
def api(p):
    r = urllib.request.Request("https://huggingface.co/api/datasets/mueller91/MLAAD/tree/main/" + urllib.parse.quote(p), headers={"Authorization": f"Bearer {T}"})
    return json.load(urllib.request.urlopen(r, timeout=60))
jobs = []
for m in SYS:
    fs = sorted(x["path"] for x in api(f"fake/en/{m}") if x["type"] == "file")
    random.Random(f"com-{m}").shuffle(fs); fs = [f for f in fs if f.split("/")[-1] not in have][:600]; jobs += fs; print(m, len(fs), flush=True)
def get(p):
    dst = O / p.replace("fake/en/", "", 1)
    if dst.exists(): return
    dst.parent.mkdir(parents=True, exist_ok=True); part = dst.with_name(dst.name + ".part")
    url = "https://huggingface.co/datasets/mueller91/MLAAD/resolve/main/" + urllib.parse.quote(p)
    # token goes in through curl's config on stdin, never on the command line (visible in process listings)
    r = subprocess.run(["curl", "-sfL", "-K", "-", "-o", str(part), url], input=f'header = "Authorization: Bearer {T}"\n', text=True)
    if r.returncode == 0: part.replace(dst)
    else: part.unlink(missing_ok=True); print("FAILED", r.returncode, p, flush=True)
with ThreadPoolExecutor(8) as ex: list(ex.map(get, jobs))
print("DONE", len(jobs), flush=True)
