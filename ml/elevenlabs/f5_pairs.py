"""Clone a speaker with F5-TTS (open source, runs locally) and have the clone read sentences.txt.

Usage (runs in its own environment, outside the repo; see "Setup"):
    ~/voice/f5env/bin/python ml/elevenlabs/f5_pairs.py --real ~/voice/anirudh/real \
        --out ~/voice/anirudh/set_f5 --speaker anirudh

No training: F5-TTS is a pretrained zero-shot cloner. For sentence N the voice reference is the
speaker's own real sentences N+1 and N+2 (edge silence trimmed, joined), with their known text as
the transcript, so the clone never hears the sentence it is faking. Writes only fakes
(<speaker>_f5_NN.wav, 16 kHz mono) and a manifest; the real clips already exist in the speaker's
ElevenLabs set. --fake-codec aac128 for speakers recorded lossy (e.g. Raj's Android).

Setup (about 3 GB, once): python3.11 -m venv ~/voice/f5env && ~/voice/f5env/bin/pip install f5-tts
Weights: SWivid/F5-TTS F5TTS_v1_Base, CC BY-NC 4.0 (non-commercial, like the rest of the project).
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from make_pairs import HERE, aac_roundtrip, duration_s, to_wav

MODEL = "F5TTS_v1_Base"
REF_SR = 24000


def trimmed_ref(clips: list[Path], dst: Path):
    """Join reference clips with edge silence cut, and 0.3 s of silence between them."""
    edge = "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.05"
    trim = f"{edge},areverse,{edge},areverse,apad=pad_dur=0.3"
    inputs = sum((["-i", str(c)] for c in clips), [])
    chains = ";".join(f"[{i}:a]aformat=channel_layouts=mono,aresample={REF_SR},{trim}[a{i}]"
                      for i in range(len(clips)))
    joined = "".join(f"[a{i}]" for i in range(len(clips)))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex",
                    f"{chains};{joined}concat=n={len(clips)}:v=0:a=1[out]", "-map", "[out]",
                    "-c:a", "pcm_s16le", str(dst)], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", type=Path, required=True, help="folder with the speaker's 01..10 recordings")
    ap.add_argument("--out", type=Path, required=True, help="output folder (outside the repo)")
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--fake-codec", choices=["aac128"], help="give fakes the real side's lossy codec")
    args = ap.parse_args()

    out = args.out.expanduser().resolve()
    repo = HERE.parents[1]
    if out == repo or repo in out.parents:
        sys.exit("--out must be outside the repo")

    sentences = [s for s in (HERE / "sentences.txt").read_text().splitlines() if s.strip()]
    recordings = {p.stem: p for p in args.real.expanduser().iterdir()
                  if p.is_file() and not p.name.startswith(".")}
    n = len(sentences)

    from f5_tts.api import F5TTS  # slow import; after argument checks
    tts = F5TTS(model=MODEL)
    (out / "fake").mkdir(parents=True, exist_ok=True)
    rows = []

    with tempfile.TemporaryDirectory() as tmp:
        for i, text in enumerate(sentences, start=1):
            nn = f"{i:02d}"
            refs = [((i - 1 + k) % n) + 1 for k in (1, 2)]  # sentences N+1, N+2 (wrapping)
            ref_files = [recordings.get(f"{r:02d}") for r in refs]
            if recordings.get(nn) is None or None in ref_files:
                print(f"[{nn}] missing real sentence {nn} or its references {refs}, skipping")
                continue
            dst = out / "fake" / f"{args.speaker}_f5_{nn}.wav"
            if not dst.exists():
                ref = Path(tmp) / f"ref_{nn}.wav"
                trimmed_ref(ref_files, ref)
                ref_text = " ".join(sentences[r - 1] for r in refs)
                raw = Path(tmp) / f"gen_{nn}.wav"
                tts.infer(ref_file=str(ref), ref_text=ref_text, gen_text=text, file_wave=str(raw),
                          seed=i, show_info=lambda *a, **k: None)
                if args.fake_codec:
                    aac_roundtrip(raw, dst, "128k")
                else:
                    to_wav(raw, dst)
            source = f"f5tts:{MODEL}" + (f"+{args.fake_codec}" if args.fake_codec else "")
            rows.append((dst.name, "spoof", nn, source, f"{duration_s(dst):.2f}", text))
            print(f"[{nn}] fake  {dst.name}  (voice from real sentences {refs})")

    with open(out / "manifest.tsv", "w") as f:
        f.write("filename\tlabel\tsentence_id\tsource\tduration_s\ttext\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    print(f"wrote {len(rows)} clips to {out}")


if __name__ == "__main__":
    main()
