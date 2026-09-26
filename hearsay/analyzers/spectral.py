"""Spectral / vocoder-artifact features (interpretable). spectral_features(x, sr=16000) -> dict.
Computed on speech frames only (loudest half), relative quantities where possible."""
import numpy as np

BANDS = [(0, 500), (500, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 5500), (5500, 7000), (7000, 8000)]


def _stft(x, n=512, hop=160):
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    fr = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    return np.abs(np.fft.rfft(fr, axis=1)) ** 2 + 1e-12  # T, F


def spectral_features(x, sr=16000):
    P = _stft(x)
    f = np.fft.rfftfreq(512, 1 / sr)
    e = P.sum(1)
    sp = e > np.percentile(e, 50)
    S = P[sp]
    out = {}
    tot = S.sum()
    for lo, hi in BANDS:  # long-term average spectrum shape (dB share of energy per band)
        m = (f >= lo) & (f < hi)
        out[f"ltas_{lo}_{hi}"] = float(10 * np.log10(S[:, m].sum() / tot))
    logS = np.log(S)
    flat = np.exp(logS.mean(1)) / S.mean(1)
    out["flatness_med"] = float(np.median(flat))
    hb = f >= 4000
    flat_hi = np.exp(logS[:, hb].mean(1)) / S[:, hb].mean(1)
    out["flatness_hi_med"] = float(np.median(flat_hi))
    c = np.cumsum(S, 1)
    out["rolloff95_med"] = float(np.median(f[(c < 0.95 * c[:, -1:]).sum(1)]))
    # spectral flux (normalized spectra), median and coefficient of variation
    Sn = S / S.sum(1, keepdims=True)
    flux = np.sqrt((np.diff(Sn, axis=0) ** 2).sum(1)) if len(Sn) > 2 else np.array([np.nan])
    out["flux_med"] = float(np.median(flux))
    out["flux_cv"] = float(np.std(flux) / (np.mean(flux) + 1e-12))
    # coupling of low- and high-band envelopes over all frames (fricatives vs voicing structure)
    lo_env = np.log(P[:, (f >= 100) & (f < 1000)].sum(1))
    hi_env = np.log(P[:, (f >= 4000)].sum(1))
    out["lo_hi_env_corr"] = float(np.corrcoef(lo_env, hi_env)[0, 1])
    # high-band dynamic range (quiet vs loud frames), noise floor structure
    out["hi_dyn_db"] = float(10 * np.log10(np.percentile(np.exp(hi_env), 90) / np.percentile(np.exp(hi_env), 10)))
    # cepstral peak prominence (voice periodicity), on speech frames
    L = 10 * np.log10(S)
    ceps = np.abs(np.fft.irfft(L, axis=1))
    q = np.arange(ceps.shape[1]) / sr
    band = (q >= 1 / 450) & (q <= 1 / 70)
    qi = np.where(band)[0]
    cpp = []
    for row in ceps[::2]:
        seg = row[qi]
        k = seg.argmax()
        a, b = np.polyfit(q[qi], seg, 1)
        cpp.append(seg[k] - (a * q[qi][k] + b))
    cpp = np.array(cpp)
    out["cpp_med"] = float(np.median(cpp))
    out["cpp_iqr"] = float(np.subtract(*np.percentile(cpp, [75, 25])))
    return out


# ---------------- analyzer wrapper ----------------
import time  # noqa: E402

# flatness_med / flatness_hi_med are computed but NOT used: they differ between NSA's ffmpeg-resampled real clips and
# ours (0.56 and 1.76 SD), i.e. they partly measure the resampler, not the voice (ml/README.md).
FEATURES = [f"ltas_{lo}_{hi}" for lo, hi in BANDS] + ["rolloff95_med", "flux_med", "flux_cv", "lo_hi_env_corr",
                                                      "hi_dyn_db", "cpp_med", "cpp_iqr"]
NAME = "spectral"
_TALK = [("ltas_5500_7000", "energy at 5.5-7 kHz"), ("ltas_7000_8000", "energy at 7-8 kHz"),
         ("rolloff95_med", "spectral roll-off"), ("cpp_med", "voice periodicity (CPP)")]


def _finding(f, ref):
    parts = []
    for k, label in _TALK:
        if k in f and k in ref and np.isfinite(f[k]):
            d = f[k] - ref[k]
            scale = abs(ref.get(k + "__iqr", 1.0)) or 1.0
            z = d / scale
            if abs(z) >= 1:
                parts.append(f"{label} {'higher' if z > 0 else 'lower'} than typical real speech")
    return "Spectral: " + ("; ".join(parts) + "." if parts else "band energies and roll-off within the range of real speech.")


def analyze(audio, sr, meta, context):
    t0 = time.perf_counter()
    try:
        f = spectral_features(audio[: 30 * sr], sr)
        return {"features": {k: f.get(k, np.nan) for k in FEATURES}, "ran": True,
                "finding": _finding(f, (context or {}).get("ref", {}).get(NAME, {})),
                "ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"features": {k: np.nan for k in FEATURES}, "ran": False, "finding": f"Spectral did not run: {e}",
                "ms": int((time.perf_counter() - t0) * 1000)}
