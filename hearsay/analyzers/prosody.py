"""Prosody analyzer: pitch (F0) contour and voice-quality features (Praat via parselmouth).

Study (DiffSSD val, 615 clips + 4,523 x 3 conditions): zero-shot voice cloners (ElevenLabs, OpenVoice, YourTTS)
are flatter and smoother than real speech; some LJ-voice generators (GradTTS) swing more. Features are
relative (semitones vs the clip's own median, rates per voiced second), so time-stretching barely moves them.
Alone: minDCF 0.47 clean / 0.62 stretched. Added to the neural detector it cuts stretched-audio minDCF
0.485 -> 0.279 (5-fold CV). See ml/README.md for the exact runs."""
import time

import numpy as np

FEATURES = ["voiced_frac", "st_std", "st_iqr", "st_range90", "dst_abs_med", "dst_abs_p90", "rise_frac",
            "reversals_per_s", "voiced_runs_per_s", "run_slope_abs_med", "run_slope_pos_frac", "declination",
            "jitter_local", "shimmer_local", "hnr_med"]
MAX_S = 30.0  # analyze at most the first 30 s (speed); fusion was fit on clips of up to ~8-15 s


def pitch_features(x, sr=16000):
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=70, pitch_ceiling=450)
    f0 = p.selected_array["frequency"]
    v = f0 > 0
    out = {"voiced_frac": float(v.mean())}
    if v.sum() < 30:
        return out
    st = np.full_like(f0, np.nan)
    st[v] = 12 * np.log2(f0[v] / np.median(f0[v]))
    sv = st[v]
    out["st_std"] = float(np.std(sv))
    out["st_iqr"] = float(np.subtract(*np.percentile(sv, [75, 25])))
    out["st_range90"] = float(np.subtract(*np.percentile(sv, [95, 5])))
    d = np.diff(st)
    d = d[np.isfinite(d) & (np.abs(d) < 3)]
    out["dst_abs_med"] = float(np.median(np.abs(d)))
    out["dst_abs_p90"] = float(np.percentile(np.abs(d), 90))
    out["rise_frac"] = float((d > 0.05).mean())
    rev, runs, slopes = 0, 0, []
    idx = np.where(v)[0]
    breaks = np.where(np.diff(idx) > 1)[0]
    for seg in np.split(idx, breaks + 1):
        if len(seg) < 8:
            continue
        s = np.convolve(st[seg], np.ones(5) / 5, mode="valid")
        ds = np.sign(np.diff(s)[np.abs(np.diff(s)) > 0.02])
        rev += int((np.diff(ds) != 0).sum())
        runs += 1
        slopes.append(np.polyfit(np.arange(len(seg)) * 0.01, st[seg], 1)[0])
    vs = v.sum() * 0.01
    out["reversals_per_s"] = rev / vs
    out["voiced_runs_per_s"] = runs / vs
    if slopes:
        out["run_slope_abs_med"] = float(np.median(np.abs(slopes)))
        out["run_slope_pos_frac"] = float(np.mean(np.array(slopes) > 0))
    t = np.arange(len(f0))[v] * 0.01
    out["declination"] = float(np.polyfit(t, sv, 1)[0])
    try:
        pp = call(snd, "To PointProcess (periodic, cc)", 70, 450)
        out["jitter_local"] = float(call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3))
        out["shimmer_local"] = float(call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6))
        h = snd.to_harmonicity_cc(0.01, 70, 0.1, 1.0)
        hv = h.values[h.values > -200]
        out["hnr_med"] = float(np.median(hv)) if len(hv) else np.nan
    except Exception:
        pass
    return out


def describe(f, ref):
    """Plain-language finding: compare the most telling features to the median of real validation speech."""
    parts = []
    for k, label in (("st_range90", "pitch range"), ("dst_abs_med", "moment-to-moment pitch movement"),
                     ("shimmer_local", "loudness roughness (shimmer)"), ("jitter_local", "pitch roughness (jitter)")):
        if k in f and k in ref and ref[k]:
            r = f[k] / ref[k]
            word = "much lower than" if r < 0.7 else "lower than" if r < 0.9 else "much higher than" if r > 1.4 \
                else "higher than" if r > 1.1 else "typical of"
            parts.append(f"{label} {word} real speech")
    return ("Prosody: " + "; ".join(parts) + ".") if parts else "Prosody: too little voiced speech to measure pitch."


def analyze(audio, sr, meta, context):
    t0 = time.perf_counter()
    try:
        f = pitch_features(audio[: int(MAX_S * sr)], sr)
        return {"features": {k: f.get(k, np.nan) for k in FEATURES},
                "finding": describe(f, (context or {}).get("prosody_ref", {})),
                "ran": True, "ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"features": {k: np.nan for k in FEATURES}, "finding": f"Prosody did not run: {e}", "ran": False,
                "ms": int((time.perf_counter() - t0) * 1000)}
