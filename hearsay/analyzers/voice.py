"""Formant and pitch-intensity coupling features (Praat via parselmouth). voice_features(x, sr) -> dict."""
import numpy as np


def voice_features(x, sr=16000):
    import parselmouth
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    out = {}
    pitch = snd.to_pitch_ac(time_step=0.02, pitch_floor=70, pitch_ceiling=450)
    f0 = pitch.selected_array["frequency"]
    ts = pitch.xs()
    v = f0 > 0
    if v.sum() < 15:
        return out
    fm = snd.to_formant_burg(time_step=0.02, max_number_of_formants=5, maximum_formant=5500)
    F = np.array([[fm.get_value_at_time(n, t) for n in (1, 2, 3)] for t in ts[v]])
    B = np.array([[fm.get_bandwidth_at_time(n, t) for n in (1, 2, 3)] for t in ts[v]])
    for n in range(3):
        f, b = F[:, n], B[:, n]
        ok = np.isfinite(f) & np.isfinite(b)
        if ok.sum() < 10:
            continue
        out[f"B{n+1}_med"] = float(np.median(b[ok]))
        out[f"F{n+1}_cv"] = float(np.std(f[ok]) / np.mean(f[ok]))
        d = np.abs(np.diff(f)) / f[:-1]
        d = d[np.isfinite(d)]
        out[f"F{n+1}_jump_med"] = float(np.median(d))  # relative frame-to-frame change (20 ms)
        out[f"F{n+1}_jump_p90"] = float(np.percentile(d, 90))
    # pitch-intensity coupling in voiced frames
    inten = snd.to_intensity(minimum_pitch=70, time_step=0.02)
    I = np.array([inten.get_value(t) for t in ts[v]])
    ok = np.isfinite(I)
    if ok.sum() > 10:
        st = 12 * np.log2(f0[v][ok] / np.median(f0[v][ok]))
        out["f0_int_corr"] = float(np.corrcoef(st, I[ok])[0, 1])
        out["int_voiced_std"] = float(np.std(I[ok]))
    return out


# ---------------- analyzer wrapper ----------------
import time  # noqa: E402

# Only formant movement and pitch-loudness coupling are used. Formant bandwidths hurt clean-audio results and B2
# differs between NSA's resampled reals and ours (ml/README.md).
FEATURES = ["F1_jump_med", "F1_jump_p90", "F2_jump_med", "F2_jump_p90", "F3_jump_med", "F3_jump_p90",
            "f0_int_corr", "int_voiced_std"]
NAME = "voice"


def _finding(f, ref):
    parts = []
    for k, label in (("F2_jump_p90", "fast vowel-resonance (F2) transitions"), ("f0_int_corr", "pitch-loudness coupling")):
        if k in f and k in ref and np.isfinite(f[k]):
            z = (f[k] - ref[k]) / (abs(ref.get(k + "__iqr", 1.0)) or 1.0)
            if abs(z) >= 1:
                parts.append(f"{label} {'higher' if z > 0 else 'lower'} than typical real speech")
    return "Voice: " + ("; ".join(parts) + "." if parts else "formant movement within the range of real speech.")


def analyze(audio, sr, meta, context):
    t0 = time.perf_counter()
    try:
        f = voice_features(audio[: 30 * sr], sr)
        return {"features": {k: f.get(k, np.nan) for k in FEATURES}, "ran": True,
                "finding": _finding(f, (context or {}).get("ref", {}).get(NAME, {})),
                "ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"features": {k: np.nan for k in FEATURES}, "ran": False, "finding": f"Voice did not run: {e}",
                "ms": int((time.perf_counter() - t0) * 1000)}
