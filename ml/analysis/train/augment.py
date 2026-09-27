"""On-the-fly waveform augmentation (16 kHz mono float32).

Applied identically to both classes, so channel effects carry no label signal.

- gain:   U(-12, +6) dB, then peak-limited to 0.99
- reverb: synthetic RIR (exponentially decaying noise, RT60 U(0.15, 0.8) s)
          -- no RIR corpus is downloaded, so this is a stand-in
- noise:  white / pink / brown noise at SNR U(5, 30) dB -- synthetic, no MUSAN
- codec:  ffmpeg round-trip, one of
            mp3  (libmp3lame, 16-128 kbps)
            aac  (ADTS stream, 24-128 kbps; same codec as M4A, no MP4 container
                  because piped output can't be seeked)
            opus (libopus in Ogg, 8-48 kbps)
            mulaw (resample to 8 kHz, G.711 mu-law, back to 16 kHz)
"""
import subprocess

import numpy as np
from scipy.signal import fftconvolve

SR = 16000
CODECS = {
    "mp3": lambda r: (["-c:a", "libmp3lame", "-b:a", f"{r.choice([16, 24, 32, 48, 64, 96, 128])}k", "-f", "mp3"], []),
    "aac": lambda r: (["-c:a", "aac", "-b:a", f"{r.choice([24, 32, 48, 64, 96, 128])}k", "-f", "adts"], []),
    "opus": lambda r: (["-c:a", "libopus", "-b:a", f"{r.choice([8, 12, 16, 24, 32, 48])}k", "-f", "ogg"], []),
    "mulaw": lambda r: (["-ar", "8000", "-c:a", "pcm_mulaw", "-f", "wav"], []),
}


def codec_roundtrip(x, codec, rng):
    enc_args, _ = CODECS[codec](rng)
    raw = ["-f", "f32le", "-ar", str(SR), "-ac", "1"]
    enc = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", *raw, "-i", "pipe:0", *enc_args, "pipe:1"],
                         input=x.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    dec = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", *raw, "pipe:1"],
                         input=enc, capture_output=True, check=True).stdout
    y = np.frombuffer(dec, dtype=np.float32)
    # MP3/AAC prepend encoder delay (~1-2k samples); undo it by cross-correlation
    lag = _delay(x, y)
    y = y[lag:]
    if len(y) >= len(x):
        return y[: len(x)].copy()
    return np.pad(y, (0, len(x) - len(y)))


def _delay(x, y, max_lag=4096):
    n = len(x) + len(y)
    c = np.fft.irfft(np.fft.rfft(y, n) * np.conj(np.fft.rfft(x, n)), n)[: max_lag + 1]
    return int(np.argmax(c))


def colored_noise(n, kind, rng):
    w = rng.standard_normal(n)
    if kind == "white":
        return w
    f = np.fft.rfft(w)
    k = np.arange(len(f))
    k[0] = 1
    f = f / (np.sqrt(k) if kind == "pink" else k)
    y = np.fft.irfft(f, n)
    return y / (y.std() + 1e-9)


def synthetic_rir(rng):
    rt60 = rng.uniform(0.15, 0.8)
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    rir = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)  # -60 dB at rt60
    rir[0] = 1.0
    return rir / np.sqrt((rir ** 2).sum())


def augment(x, rng, p_gain=0.5, p_reverb=0.25, p_noise=0.3, p_codec=0.5):
    """Returns (augmented waveform, list of applied ops) for logging."""
    ops = []
    x = x.astype(np.float64)
    if rng.random() < p_reverb:
        x = fftconvolve(x, synthetic_rir(rng))[: len(x)]
        ops.append("reverb")
    if rng.random() < p_noise:
        kind = rng.choice(["white", "pink", "brown"])
        snr = rng.uniform(5, 30)
        p_sig = (x ** 2).mean() + 1e-12
        x = x + colored_noise(len(x), kind, rng) * np.sqrt(p_sig / 10 ** (snr / 10))
        ops.append(f"noise-{kind}")
    if rng.random() < p_gain:
        x = x * 10 ** (rng.uniform(-12, 6) / 20)
        ops.append("gain")
    peak = np.abs(x).max()
    if peak > 0.99:
        x = x * (0.99 / peak)
    if rng.random() < p_codec:
        c = rng.choice(list(CODECS))
        x = codec_roundtrip(x, c, rng)
        ops.append(c)
    return x.astype(np.float32), ops
