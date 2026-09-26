"""Rhythm / energy-dynamics features, built to be time-stretch invariant (ratios, not rates).
rhythm_features(x, sr=16000) -> dict."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks


def rhythm_features(x, sr=16000):
    out = {}
    sos = butter(4, [300, 3000], btype="band", fs=sr, output="sos")
    y = sosfiltfilt(sos, x)
    hop = 80  # 5 ms
    fr = np.lib.stride_tricks.sliding_window_view(y ** 2, 400)[::hop].mean(1)
    env = 10 * np.log10(fr + 1e-10)
    k = np.ones(8) / 8  # ~40 ms smoothing
    env = np.convolve(env, k, mode="same")
    fs_env = sr / hop
    pk, prop = find_peaks(env, prominence=3, distance=int(0.08 * fs_env), height=np.percentile(env, 50))
    dur = len(x) / sr
    if len(pk) < 4:
        return {"n_nuclei_per_s": len(pk) / dur}
    iv = np.diff(pk) / fs_env
    out["n_nuclei_per_s"] = len(pk) / dur  # stretch-dependent (kept for completeness)
    out["ioi_cv"] = float(np.std(iv) / np.mean(iv))  # stretch-invariant
    out["ioi_npvi"] = float(100 * np.mean(np.abs(np.diff(iv)) / ((iv[1:] + iv[:-1]) / 2)))
    out["peak_db_std"] = float(np.std(env[pk]))
    out["prom_med"] = float(np.median(prop["prominences"]))
    out["prom_cv"] = float(np.std(prop["prominences"]) / np.mean(prop["prominences"]))
    t = pk / fs_env
    out["peak_db_slope_norm"] = float(np.polyfit(t / t[-1], env[pk], 1)[0])  # intensity declination per utterance
    # envelope modulation spectrum, normalized to the dominant syllable rate (stretch-invariant shape)
    e = env - env.mean()
    M = np.abs(np.fft.rfft(e * np.hanning(len(e)))) ** 2
    fm = np.fft.rfftfreq(len(e), 1 / fs_env)
    m = (fm >= 1) & (fm <= 20)
    if m.sum() > 5:
        fpk = fm[m][M[m].argmax()]
        r = fm / fpk
        tot = M[m].sum()
        out["mod_peak_hz"] = float(fpk)
        out["mod_below_half"] = float(M[m & (r < 0.5)].sum() / tot)
        out["mod_above_2x"] = float(M[m & (r > 2)].sum() / tot)
        out["mod_peakiness"] = float(M[m].max() / M[m].mean())
    return out


# ---------------- analyzer wrapper ----------------
import time  # noqa: E402

FEATURES = ["n_nuclei_per_s", "ioi_cv", "ioi_npvi", "peak_db_std", "prom_med", "prom_cv", "peak_db_slope_norm",
            "mod_peak_hz", "mod_below_half", "mod_above_2x", "mod_peakiness"]
NAME = "rhythm"


def _finding(f, ref):
    parts = []
    for k, label in (("ioi_npvi", "syllable-to-syllable timing variability"),
                     ("peak_db_slope_norm", "loudness decline across the utterance")):
        if k in f and k in ref and np.isfinite(f[k]):
            z = (f[k] - ref[k]) / (abs(ref.get(k + "__iqr", 1.0)) or 1.0)
            if abs(z) >= 1:
                parts.append(f"{label} {'higher' if z > 0 else 'lower'} than typical real speech")
    return "Rhythm: " + ("; ".join(parts) + "." if parts else "syllable timing within the range of real speech.")


def analyze(audio, sr, meta, context):
    t0 = time.perf_counter()
    try:
        f = rhythm_features(audio[: 30 * sr], sr)
        return {"features": {k: f.get(k, np.nan) for k in FEATURES}, "ran": True,
                "finding": _finding(f, (context or {}).get("ref", {}).get(NAME, {})),
                "ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"features": {k: np.nan for k in FEATURES}, "ran": False, "finding": f"Rhythm did not run: {e}",
                "ms": int((time.perf_counter() - t0) * 1000)}
