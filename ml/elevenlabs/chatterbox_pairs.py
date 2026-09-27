"""Clone a speaker with Chatterbox (Resemble AI, open source, runs locally) reading sentences.txt.

Usage (own environment, outside the repo; see "Setup"):
    ~/voice/cbenv/bin/python ml/elevenlabs/chatterbox_pairs.py --real ~/voice/anirudh/real \
        --out ~/voice/anirudh/set_cb --speaker anirudh

No training: Chatterbox is a pretrained zero-shot cloner. Same reference scheme as f5_pairs.py:
for sentence N the voice prompt is the speaker's real sentences N+1 and N+2 (edge silence trimmed,
joined), so the clone never hears the sentence it fakes. Writes only fakes (<speaker>_cb_NN.wav,
16 kHz mono) and a manifest. --fake-codec aac128 for speakers recorded lossy.

Chatterbox adds Resemble's inaudible PerTh watermark to every output (left in: it is a safety
feature). Label: chatterbox:ResembleAI/chatterbox. Mix with unwatermarked fakes (F5) when training
so "watermark = fake" can't become a shortcut.

Setup (about 4 GB, once): python3.11 -m venv ~/voice/cbenv && ~/voice/cbenv/bin/pip install chatterbox-tts
Weights: ResembleAI/chatterbox, MIT.
"""

import argparse
import json
import sys
import tempfile
import wave
from pathlib import Path

from f5_pairs import trimmed_ref
from make_pairs import HERE, aac_roundtrip, duration_s, to_wav

MODEL = "ResembleAI/chatterbox"


def write_wav(samples, sr: int, dst: Path):
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", type=Path, required=True, help="folder with the speaker's 01..10 recordings")
    ap.add_argument("--out", type=Path, required=True, help="output folder (outside the repo)")
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--tag", default="cb", help="filename tag, e.g. cbb for a variant run")
    ap.add_argument("--ref-offset", type=int, default=1, help="voice reference = sentences N+k, N+k+1")
    ap.add_argument("--exaggeration", type=float, default=0.5, help="expressiveness (variant)")
    ap.add_argument("--cfg-weight", type=float, default=0.5, help="pacing/guidance (variant)")
    ap.add_argument("--fake-codec", choices=["aac128"], help="give fakes the real side's lossy codec")
    ap.add_argument("--device", default="mps", help="mps (Apple GPU) or cpu")
    args = ap.parse_args()

    out = args.out.expanduser().resolve()
    repo = HERE.parents[1]
    if out == repo or repo in out.parents:
        sys.exit("--out must be outside the repo")

    sentences = [s for s in (HERE / "sentences.txt").read_text().splitlines() if s.strip()]
    recordings = {p.stem: p for p in args.real.expanduser().iterdir()
                  if p.is_file() and not p.name.startswith(".")}
    n = len(sentences)
    if not 1 <= args.ref_offset <= n - 2:  # both reference sentences must differ from sentence N
        sys.exit(f"--ref-offset must be between 1 and {n - 2}")

    import torch
    from chatterbox.tts import ChatterboxTTS  # slow import; after argument checks
    tts = ChatterboxTTS.from_pretrained(device=args.device)
    (out / "fake").mkdir(parents=True, exist_ok=True)
    rows = []

    with tempfile.TemporaryDirectory() as tmp:
        for i, text in enumerate(sentences, start=1):
            nn = f"{i:02d}"
            refs = [((i - 1 + k) % n) + 1 for k in (args.ref_offset, args.ref_offset + 1)]  # sentences N+k, N+k+1 (wrapping)
            ref_files = [recordings.get(f"{r:02d}") for r in refs]
            if recordings.get(nn) is None or None in ref_files:
                print(f"[{nn}] missing real sentence {nn} or its references {refs}, skipping")
                continue
            dst = out / "fake" / f"{args.speaker}_{args.tag}_{nn}.wav"
            # Reuse an existing clip only if it was made with these settings (clips from before this
            # sidecar existed have none and are reused).
            meta = dst.with_suffix(".json")
            settings = {"model": MODEL, "text": text, "exaggeration": args.exaggeration,
                        "cfg_weight": args.cfg_weight, "ref_offset": args.ref_offset, "fake_codec": args.fake_codec}
            stale = meta.exists() and json.loads(meta.read_text()) != settings
            if not dst.exists() or stale:
                meta.write_text(json.dumps(settings))
                ref = Path(tmp) / f"ref_{nn}.wav"
                trimmed_ref(ref_files, ref)
                torch.manual_seed(i)
                wav = tts.generate(text, audio_prompt_path=str(ref), exaggeration=args.exaggeration, cfg_weight=args.cfg_weight)
                raw = Path(tmp) / f"gen_{nn}.wav"
                write_wav(wav.squeeze(0).cpu().numpy(), tts.sr, raw)
                if args.fake_codec:
                    aac_roundtrip(raw, dst, "128k")
                else:
                    to_wav(raw, dst)
            source = (f"chatterbox:{MODEL}@exag{args.exaggeration}@cfg{args.cfg_weight}" if (args.exaggeration, args.cfg_weight) != (0.5, 0.5) else f"chatterbox:{MODEL}") + (f"@ref+{args.ref_offset}" if args.ref_offset != 1 else "") + (f"+{args.fake_codec}" if args.fake_codec else "")
            rows.append((dst.name, "spoof", nn, source, f"{duration_s(dst):.2f}", text))
            print(f"[{nn}] fake  {dst.name}  (voice from real sentences {refs})")

    with open(out / "manifest.tsv", "w") as f:
        f.write("filename\tlabel\tsentence_id\tsource\tduration_s\ttext\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    print(f"wrote {len(rows)} clips to {out}")


if __name__ == "__main__":
    main()
