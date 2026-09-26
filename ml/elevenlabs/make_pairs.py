"""Build a matched real/fake set: your recordings vs an ElevenLabs clone of your voice.

Usage:
    python ml/elevenlabs/make_pairs.py --real ~/voice/real --out ~/voice/set --speaker ani

--real holds your recordings named 01.m4a ... 10.m4a (any audio extension), where
NN matches line NN of sentences.txt. Output (16 kHz mono WAV, same as the NSA test set):
    <out>/real/<speaker>_real_NN.wav
    <out>/fake/<speaker>_fake_NN.wav
    <out>/manifest.tsv
Needs ffmpeg on PATH and ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID (env or ml/elevenlabs/.env).
Keep --out outside the repo: audio must never be committed.

If the real recordings are lossy (e.g. an Android recorder's AAC 128 kbps .mp4), pass
--fake-codec aac128 so the fakes get the same compression history; otherwise "has codec
artifacts" becomes a free real-vs-fake shortcut. The untouched ElevenLabs audio is kept in
<out>/fake_pcm/ (reruns reuse it, so no credits are spent twice).
"""

import tempfile

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
SR = 16000
API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_16000"


def load_env():
    env_file = HERE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def to_wav(src: Path, dst: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), str(dst)],
        check=True,
    )


def aac_roundtrip(src: Path, dst: Path, bitrate: str):
    """Encode like a phone recorder (AAC, 44.1 kHz mono), then decode back to 16 kHz WAV."""
    with tempfile.TemporaryDirectory() as tmp:
        m4a = Path(tmp) / "x.m4a"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "44100",
                        "-c:a", "aac", "-b:a", bitrate, str(m4a)], check=True)
        to_wav(m4a, dst)


def tts(text: str, voice_id: str, api_key: str, model: str) -> bytes:
    req = urllib.request.Request(
        API.format(voice_id=voice_id),
        data=json.dumps({"text": text, "model_id": model}).encode(),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs error {e.code}: {e.read().decode(errors='replace')}")


def write_pcm_wav(pcm: bytes, dst: Path):
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # pcm_16000 is signed 16-bit little-endian mono
        w.setframerate(SR)
        w.writeframes(pcm)


def duration_s(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", type=Path, required=True, help="folder with 01.m4a ... NN.m4a")
    ap.add_argument("--out", type=Path, required=True, help="output folder (outside the repo)")
    ap.add_argument("--speaker", required=True, help="short speaker tag used in filenames")
    ap.add_argument("--model", default="eleven_multilingual_v2", help="ElevenLabs model_id")
    ap.add_argument("--skip-fake", action="store_true", help="only convert the real recordings")
    ap.add_argument("--fake-codec", choices=["aac128"], help="give fakes the real side's lossy codec")
    args = ap.parse_args()

    repo = HERE.parents[1]
    out = args.out.expanduser().resolve()
    if out == repo or repo in out.parents:
        sys.exit("--out must be outside the repo")

    load_env()
    sentences = [s for s in (HERE / "sentences.txt").read_text().splitlines() if s.strip()]
    recordings = {p.stem: p for p in args.real.iterdir() if p.is_file() and not p.name.startswith(".")}

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID")
    if not args.skip_fake and not (api_key and voice_id):
        sys.exit("Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID (see ml/elevenlabs/.env.example)")

    (args.out / "real").mkdir(parents=True, exist_ok=True)
    (args.out / "fake").mkdir(parents=True, exist_ok=True)
    if args.fake_codec:
        (args.out / "fake_pcm").mkdir(exist_ok=True)
    rows = []

    for i, text in enumerate(sentences, start=1):
        nn = f"{i:02d}"
        src = recordings.get(nn)
        if src is None:
            print(f"[{nn}] no recording named {nn}.* in {args.real}, skipping real")
        else:
            dst = args.out / "real" / f"{args.speaker}_real_{nn}.wav"
            to_wav(src, dst)
            rows.append((dst.name, "bonafide", nn, src.name, f"{duration_s(dst):.2f}", text))
            print(f"[{nn}] real  {dst.name}")

        if not args.skip_fake:
            dst = args.out / "fake" / f"{args.speaker}_fake_{nn}.wav"
            pcm = args.out / "fake_pcm" / dst.name if args.fake_codec else dst
            if not pcm.exists():  # don't spend credits twice on reruns
                write_pcm_wav(tts(text, voice_id, api_key, args.model), pcm)
            source = f"elevenlabs:{args.model}"
            if args.fake_codec:
                aac_roundtrip(pcm, dst, "128k")
                source += f"+{args.fake_codec}"
            rows.append((dst.name, "spoof", nn, source, f"{duration_s(dst):.2f}", text))
            print(f"[{nn}] fake  {dst.name}")

    with open(args.out / "manifest.tsv", "w") as f:
        f.write("filename\tlabel\tsentence_id\tsource\tduration_s\ttext\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    print(f"wrote {len(rows)} clips to {args.out}")


if __name__ == "__main__":
    main()
