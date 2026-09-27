"""Score a folder of clips with the Hugging Face stand-in detector (server/app/hf_model.py), locally.

Usage (from the repo root, with server/requirements-ml.txt and CPU torch installed):
    PYTHONPATH=.:server python server/tools/score_folder.py <dir> [--model org/name] [--revision sha]

<dir> is either a flat folder of clips, or ml/elevenlabs/make_pairs.py output with real/ and fake/ subfolders,
in which case it also prints how many of each got each verdict and the ranking AUC. Keep audio outside the repo.
"""
import argparse
import os
import sys
from pathlib import Path

from app.hf_model import HFDetector

EXT = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".oga", ".opus", ".flac", ".aac", ".mp4", ".mov"}


def auc(pos, neg):
    """P(score of a random fake > score of a random real), ties count half."""
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--model", default=os.getenv("HF_MODEL", "mo-thecreator/Deepfake-audio-detection"))
    ap.add_argument("--revision", default=os.getenv("HF_REVISION"))
    a = ap.parse_args()
    det = HFDetector(a.model, a.revision)
    groups = {g: sorted(p for p in (a.dir / g).iterdir() if p.suffix.lower() in EXT)
              for g in ("real", "fake") if (a.dir / g).is_dir()} or \
             {"": sorted(p for p in a.dir.iterdir() if p.suffix.lower() in EXT)}
    raw = {}
    for g, files in groups.items():
        raw[g] = []
        for f in files:
            try:
                r = det.analyze(str(f))
            except ValueError as e:
                print(f"{g:4} {f.name:32} skipped: {e}")
                continue
            o = r["overall"]
            raw[g].append(r["analyzers"][0]["llr_contribution"])
            print(f"{g:4} {f.name:32} p_synthetic={o['probability']:.3f} {o['verdict']:16} {r['timing_ms']} ms")
    print(f"\nmodel {det.name} @ {det.release}")
    if "real" in raw and "fake" in raw and raw["real"] and raw["fake"]:
        for g in ("real", "fake"):
            n = len(raw[g])
            syn = sum(s >= 1.0986 for s in raw[g])  # prior 0.5: probability >= 0.75
            ok = sum(s <= -1.0986 for s in raw[g])
            print(f"{g}: {n} clips, {syn} likely_synthetic, {n - syn - ok} inconclusive, {ok} likely_real")
        print(f"AUC (fake ranked above real): {auc(raw['fake'], raw['real']):.3f}")


if __name__ == "__main__":
    sys.exit(main())
