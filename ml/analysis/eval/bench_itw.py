"""In-the-Wild benchmark on the 16 held-out test speakers (never trained on by any of our models; asserted in the
training scripts). Scores every clip with each model and writes results/bench_itw/<model>.csv (file,speaker,label,score),
score = log-odds that the clip is synthetic (higher = more synthetic). Resumable.

Models
  v5c          our shipped network, hearsay windowing: mean over up to 3 non-overlapping 4 s windows, fp32
  ad1b         NII AntiDeepfake XLS-R-1B, the authors' protocol: whole clip (capped at 30 s), layer-normed waveform
  ad1b_win     the same model with hearsay windowing (same input as v5c)
  admms        NII AntiDeepfake MMS-300M, whole clip
  stock        mo-thecreator/Deepfake-audio-detection (wav2vec2-base) at the commit our server pinned, hearsay windowing

Usage: python bench_itw.py <model> [<model> ...]"""
import csv, sys, time
from pathlib import Path
import numpy as np, torch

H = Path.home() / "hackgt"; D = H / "data"
sys.path.insert(0, str(H / "dispel_pr8fix")); sys.path.insert(0, str(H / "scratch/eval"))
from hearsay import audio as A
from hearsay.analyzers.dl_detector import Detector, windows

OUT = H / "results/bench_itw"; OUT.mkdir(parents=True, exist_ok=True)
DEV = "cuda"
MAX_WHOLE = 30 * 16000


def clips():
    test = {l.strip() for l in open(D / "splits/itw_test_speakers.txt") if l.strip()}
    for s in (D / "splits/ft_itw_train_speakers.txt", D / "splits/ft_itw_val_speakers.txt"):
        assert not test & {l.strip() for l in open(s) if l.strip()}, f"test speaker in {s.name}"
    return [r for r in csv.DictReader(open(D / "release_in_the_wild/meta.csv")) if r["speaker"] in test]


def load_model(name):
    if name == "v5c":
        rel = D / "release/v5c"
        net = Detector(rel / "backbone_config")
        net.load_state_dict(torch.load(rel / "v3.pt", map_location="cpu", weights_only=False)["model"])
        net = net.to(DEV).eval()

        @torch.inference_mode()
        def f(x):
            w, _ = windows(x); lg = net(torch.from_numpy(w).to(DEV)).float()
            return float((lg[:, 1] - lg[:, 0]).mean())
        return f
    if name.startswith("ad"):
        from antideepfake import AntiDeepfake
        d = D / "models/antideepfake" / ("xls-r-1b-anti-deepfake" if name.startswith("ad1b") else "mms-300m-anti-deepfake")
        m = AntiDeepfake(d).to(DEV).eval()
        assert not m.missing, m.missing[:5]
        if name.endswith("_win"):
            return lambda x: float(np.mean([m.score(w) for w in windows(x)[0]]))
        return lambda x: m.score(x[:MAX_WHOLE])
    if name == "stock":
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        repo, rev = "mo-thecreator/Deepfake-audio-detection", "e4d9874b493362149cec96ced85f00b00b1a04c0"
        fe = AutoFeatureExtractor.from_pretrained(repo, revision=rev)
        m = AutoModelForAudioClassification.from_pretrained(repo, revision=rev).to(DEV).eval()
        lab = {str(v).lower(): int(k) for k, v in m.config.id2label.items()}
        fake = [lab[n] for n in ("fake", "spoof", "synthetic", "deepfake") if n in lab][0]; real = 1 - fake
        print("stock labels", m.config.id2label, flush=True)

        @torch.inference_mode()
        def f(x):
            w, _ = windows(x)
            inp = {k: v.to(DEV) for k, v in fe(list(w), sampling_rate=16000, return_tensors="pt").items()}
            lg = m(**inp).logits.float()
            return float((lg[:, fake] - lg[:, real]).mean())
        return f
    raise SystemExit(f"unknown model {name}")


def run(name, rows):
    out = OUT / f"{name}.csv"
    done = {r["file"] for r in csv.DictReader(open(out))} if out.exists() else set()
    todo = [r for r in rows if r["file"] not in done]
    print(f"{name}: {len(done)} done, {len(todo)} to score", flush=True)
    if not todo:
        return
    f = load_model(name)
    new = not out.exists()
    with open(out, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["file", "speaker", "label", "score"])
        t0 = time.time()
        for i, r in enumerate(todo):
            x, _ = A.load(str(D / "release_in_the_wild" / r["file"]))
            w.writerow([r["file"], r["speaker"], 1 if r["label"] == "spoof" else 0, f"{f(x):.6f}"])
            if i % 250 == 0:
                fh.flush(); print(f"{name} {i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print(f"{name}: done in {time.time() - t0:.0f}s", flush=True)
    del f; torch.cuda.empty_cache()


if __name__ == "__main__":
    rows = clips()
    print(len(rows), "clips,", sum(r["label"] == "spoof" for r in rows), "spoof", flush=True)
    for name in sys.argv[1:]:
        run(name, rows)
    print("ALLDONE", flush=True)
