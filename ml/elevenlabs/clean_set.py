"""Trim edge silence and match loudness so real vs fake can't be told apart by recording setup.

Usage:
    python ml/elevenlabs/clean_set.py ~/voice/set ~/voice/d/set --out ~/voice/set_clean

Reads each <set>/manifest.tsv from make_pairs.py and writes, identically for real and fake:
    <out>/real/*.wav, <out>/fake/*.wav, <out>/manifest.tsv (all input sets merged)
Steps per clip:
  1. cut leading and trailing audio quieter than REL_THRESH_DB below the clip's own peak
     (but never a threshold below MIN_THRESH_DB), keeping PAD_S of it at each end. Pauses
     between words are kept: they are evidence for prosody analysis. Per-clip, because
     room noise differs per recording (-46 dBFS in a quiet room, ~-37 dBFS in a louder one).
  2. apply one constant gain so mean volume is TARGET_DB (never above PEAK_CEIL_DB peak);
     a constant gain, not dynamic normalization, so the waveform shape is untouched
Output stays 16 kHz mono 16-bit WAV. Keep --out outside the repo.
"""

import argparse
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SR = 16000
REL_THRESH_DB = 30
MIN_THRESH_DB = -35  # quiet recordings: never trim at a level below typical room noise
PAD_S = 0.15
TARGET_DB = -26.0
PEAK_CEIL_DB = -1.0
REPO = Path(__file__).resolve().parents[2]


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def trim_edges(src: Path, dst: Path):
    _, peak = volume_stats(src)
    thresh = max(peak - REL_THRESH_DB, MIN_THRESH_DB)
    edge = f"silenceremove=start_periods=1:start_threshold={thresh:.1f}dB:start_silence={PAD_S}"
    ffmpeg("-i", str(src), "-af", f"{edge},areverse,{edge},areverse", "-ac", "1", "-ar", str(SR), str(dst))


def volume_stats(path: Path) -> tuple[float, float]:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr
    mean = float(re.search(r"mean_volume: (-?[\d.]+) dB", out).group(1))
    peak = float(re.search(r"max_volume: (-?[\d.]+) dB", out).group(1))
    return mean, peak


def duration_s(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sets", nargs="+", type=Path, help="set folders made by make_pairs.py")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    out = args.out.expanduser().resolve()
    if out == REPO or REPO in out.parents:
        sys.exit("--out must be outside the repo")
    for sub in ("real", "fake"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    header, rows = None, []
    with tempfile.TemporaryDirectory() as tmp:
        for set_dir in args.sets:
            set_dir = set_dir.expanduser()
            lines = (set_dir / "manifest.tsv").read_text().splitlines()
            header = lines[0].split("\t")
            for line in lines[1:]:
                row = dict(zip(header, line.split("\t")))
                sub = "real" if row["label"] == "bonafide" else "fake"
                src = set_dir / sub / row["filename"]
                dst = out / sub / row["filename"]

                trimmed = Path(tmp) / row["filename"]
                trim_edges(src, trimmed)
                mean, peak = volume_stats(trimmed)
                gain = min(TARGET_DB - mean, PEAK_CEIL_DB - peak)
                ffmpeg("-i", str(trimmed), "-af", f"volume={gain:.2f}dB", "-ac", "1", "-ar", str(SR),
                       "-c:a", "pcm_s16le", str(dst))

                before, after = duration_s(src), duration_s(dst)
                row["duration_s"] = f"{after:.2f}"
                rows.append(row)
                print(f"{row['filename']:18} {before:5.2f}s -> {after:5.2f}s  gain {gain:+5.1f} dB")

    with open(out / "manifest.tsv", "w") as f:
        f.write("\t".join(header) + "\n")
        for row in rows:
            f.write("\t".join(row[h] for h in header) + "\n")
    print(f"wrote {len(rows)} clips to {out}")


if __name__ == "__main__":
    main()
