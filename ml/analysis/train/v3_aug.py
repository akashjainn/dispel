"""v3 augmentation and NSA-like evaluation corruptions (16 kHz mono float32 in and out).

Training (train_aug, applied identically to real and fake; labels never change):
  trim leading/trailing silence (librosa.effects.trim, top_db 40; untrimmed if < 0.5 s would remain)
  -> pad U(0, 0.4) s at each end with low-level white noise (40-60 dB below the clip RMS)
  -> stretch p=0.7: rate U(0.85, 1.15), method uniform over TRAIN_STRETCH (phase vocoder, WSOLA, speed/resample)
  -> random 4 s crop (tile-repeat if shorter)
  -> noise p=0.7: white/pink/brown, SNR U(5, 35) dB
  -> gain always: U(-18, +6) dB, peak-limited to 0.99
  -> codec p=0.3: augment.codec_roundtrip (mp3/aac/opus/mu-law)
Held out from training, validation/test only: ffmpeg atempo and ffmpeg rubberband.

Evaluation (nsa_eval): rate U(0.9, 1.1) and SNR U(10, 30) dB drawn from default_rng([13, crc32(key)]), key = path
relative to ~/hackgt (e.g. data/diffssd/...). method 'pv' reproduces scratch/eval/score_frozen.py --cond nsalike exactly.
"""
import subprocess
import zlib

import librosa
import numpy as np
from audiotsm import wsola
from audiotsm.io.array import ArrayReader, ArrayWriter

from augment import CODECS, codec_roundtrip, colored_noise

SR, CROP = 16000, 4 * 16000
TRAIN_STRETCH = ("pv", "wsola", "speed")
HELDOUT_STRETCH = ("atempo", "rubberband")


def _ffmpeg(x, af):
    raw = ["-f", "f32le", "-ar", str(SR), "-ac", "1"]
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", *raw, "-i", "pipe:0", "-af", af, *raw, "pipe:1"],
                         input=x.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def stretch(x, rate, method):
    """rate > 1 = faster/shorter (output length ~ len(x) / rate)."""
    x = x.astype(np.float32)
    if method == "pv":
        return librosa.effects.time_stretch(x, rate=rate).astype(np.float32)
    if method == "wsola":
        w = ArrayWriter(1)
        wsola(1, speed=rate).run(ArrayReader(x[None]), w)
        return w.data[0].astype(np.float32)
    if method == "speed":  # plain resample: tempo and pitch change together
        return librosa.resample(x, orig_sr=SR * rate, target_sr=SR, res_type="soxr_hq").astype(np.float32)
    if method == "atempo":
        return _ffmpeg(x, f"atempo={rate:.6f}")
    if method == "rubberband":
        return _ffmpeg(x, f"rubberband=tempo={rate:.6f}")
    raise ValueError(method)


def train_aug(x, rng):
    y, _ = librosa.effects.trim(x, top_db=40)
    if len(y) >= SR // 2:
        x = y
    rms = float(np.sqrt(np.mean(x ** 2))) + 1e-6
    a, b = (int(v) for v in rng.uniform(0, 0.4, 2) * SR)
    lvl = rms * 10 ** (-rng.uniform(40, 60) / 20)
    x = np.concatenate([rng.standard_normal(a) * lvl, x, rng.standard_normal(b) * lvl]).astype(np.float32)
    if rng.random() < 0.7:
        rate = rng.uniform(0.85, 1.15)
        need = int(CROP * rate) + SR // 4
        if len(x) > need:
            s = int(rng.integers(0, len(x) - need + 1))
            x = x[s:s + need]
        x = stretch(x, rate, TRAIN_STRETCH[int(rng.integers(len(TRAIN_STRETCH)))])
    if len(x) > CROP:
        s = int(rng.integers(0, len(x) - CROP + 1))
        x = x[s:s + CROP]
    elif len(x) < CROP:
        x = np.tile(x, CROP // max(len(x), 1) + 1)[:CROP]
    x = x.astype(np.float64)
    if rng.random() < 0.7:
        kind = ["white", "pink", "brown"][int(rng.integers(3))]
        x = x + colored_noise(len(x), kind, rng) * np.sqrt(((x ** 2).mean() + 1e-12) / 10 ** (rng.uniform(5, 35) / 10))
    x = x * 10 ** (rng.uniform(-18, 6) / 20)
    pk = np.abs(x).max()
    if pk > 0.99:
        x = x * (0.99 / pk)
    if rng.random() < 0.3:
        x = codec_roundtrip(x, list(CODECS)[int(rng.integers(len(CODECS)))], rng)
    return x.astype(np.float32)


def nsa_eval(x, key, method):
    """Same draws and ops as score_frozen.py nsalike, with a choice of stretch method."""
    rng = np.random.default_rng([13, zlib.crc32(key.encode())])
    rate, snr = float(rng.uniform(0.9, 1.1)), float(rng.uniform(10, 30))
    x = stretch(x, rate, method)
    pw = float(np.mean(x ** 2)) + 1e-12
    x = (x + rng.standard_normal(len(x)).astype(np.float32) * np.sqrt(pw / 10 ** (snr / 10))).astype(np.float32)
    return x, rate, snr
