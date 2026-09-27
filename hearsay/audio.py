"""Decode any supported file to 16 kHz mono float32, and describe the input channel.

Resampling uses soxr 'HQ', the same resampler training used (librosa res_type='soxr_hq')."""
import json
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf
import soxr

SR = 16000
MAX_DECODE_S = 121.0  # decode at most this much; Pipeline.analyze still rejects > 120 s as too_long


def _probe(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                              "stream=codec_name,sample_rate,channels", "-of", "json", path],
                             capture_output=True, text=True, timeout=20, check=True).stdout
        s = json.loads(out)["streams"][0]
        return {"sample_rate": int(s.get("sample_rate", 0)), "channels": int(s.get("channels", 0)),
                "codec": s.get("codec_name", "unknown")}
    except Exception:
        return None


def _ffmpeg_decode(path, sr=48000):
    # -t caps the decoded duration: a 25 MB low-bitrate upload can hold hours of audio (GBs as float32)
    out = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr),
                          "-t", str(MAX_DECODE_S), "-f", "f32le", "pipe:1"],
                         stdin=subprocess.DEVNULL, capture_output=True, timeout=120, check=True).stdout
    return np.frombuffer(out, dtype="<f4").copy(), sr


MAX_CHANNELS, MAX_SR = 32, 384000


def _sf_decode_mono(path):
    """Read at most MAX_DECODE_S seconds with soundfile, downmixing block by block so memory stays at one block of
    all channels plus the mono result (a many-channel, high-rate file cannot blow up the allocation)."""
    nfo = sf.info(path)
    if nfo.channels > MAX_CHANNELS or nfo.samplerate > MAX_SR:
        raise ValueError(f"unsupported layout: {nfo.channels} ch at {nfo.samplerate} Hz")
    limit = int(MAX_DECODE_S * nfo.samplerate)
    parts = []  # frames=limit bounds the read
    for blk in sf.blocks(path, blocksize=nfo.samplerate, dtype="float32", always_2d=True, frames=limit):
        parts.append(blk.mean(1))
    x = np.concatenate(parts) if parts else np.zeros(0, np.float32)
    return x, nfo.samplerate, nfo.channels


def load(src):
    """src: path or bytes. Returns (x 16 kHz mono float32, info dict). Raises ValueError if undecodable.
    Bytes are written to a temp file that is deleted before returning (the server keeps no audio)."""
    tmp = None
    if isinstance(src, (bytes, bytearray)):
        fd, tmp = tempfile.mkstemp(suffix=".audio")
        with os.fdopen(fd, "wb") as fh:
            fh.write(src)
        path = tmp
    else:
        path = str(src)
    try:
        info = _probe(path)
        try:
            x, sr, ch = _sf_decode_mono(path)
            if info is None:
                info = {"sample_rate": sr, "channels": ch, "codec": "pcm"}
        except Exception:
            try:
                x, sr = _ffmpeg_decode(path)
            except Exception as e:
                raise ValueError(f"decode_failed: {e}") from e
        if info is None:
            info = {"sample_rate": sr, "channels": 1, "codec": "unknown"}
        if sr != SR:
            x = soxr.resample(x, sr, SR, quality="HQ").astype(np.float32)
        return np.ascontiguousarray(x, dtype=np.float32), info
    finally:
        if tmp:
            os.remove(tmp)


def channel_note(x, info):
    """Rough bandwidth (99% spectral roll-off, median over frames) and a phone-like flag. Report only."""
    try:
        import numpy.fft as F
        n = 512
        fr = np.lib.stride_tricks.sliding_window_view(x, n)[::256] * np.hanning(n)
        P = np.abs(F.rfft(fr, axis=1)) ** 2
        loud = P.sum(1) > np.percentile(P.sum(1), 50)
        c = np.cumsum(P[loud], 1)
        roll = (c < 0.99 * c[:, -1:]).sum(1) * SR / n
        bw = int(np.median(roll))
    except Exception:
        bw = 0
    orig = info.get("sample_rate", SR)
    phone = 0 < bw < 4000 or orig <= 8000
    lossy = info.get("codec", "") not in ("pcm_s16le", "pcm_s24le", "pcm_f32le", "pcm", "flac")
    parts = ["narrowband (phone-like)" if phone else "wideband",
             "lossy codec" if lossy else "uncompressed",
             f"original {orig} Hz" if orig else ""]
    return {"bandwidth_hz": bw, "phone_like": bool(phone), "note": ", ".join(p for p in parts if p)}
