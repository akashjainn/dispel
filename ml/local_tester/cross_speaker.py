"""Can simple, explainable features tell real from ElevenLabs clone on a voice they never saw?

Usage:
    .venv/bin/python ml/local_tester/cross_speaker.py ~/voice/set_clean

Reads <set>/manifest.tsv (from ml/elevenlabs/clean_set.py), measures a few forensic
features per clip, then trains a logistic regression on one speaker and tests on the
other (both directions). Speaker = filename prefix before "_real_"/"_fake_".
"""

import sys
from pathlib import Path

import librosa
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SR = 16000
N_FFT, HOP = 512, 160  # 32 ms windows, 10 ms hop

FEATURES = {
    "gap_noise_db": "loudness of the quietest 10% of frames (room noise in pauses)",
    "gap_flatness": "how noise-like (flat) the spectrum is in those quiet frames",
    "pause_frac": "fraction of the clip that is pause (>30 dB below the loudest frame)",
    "pitch_std_st": "pitch variation, in semitones",
    "pitch_range_st": "pitch range (5th to 95th percentile), in semitones",
    "voiced_frac": "fraction of frames with a detectable pitch",
    "hf_ratio_db": "energy above 4 kHz relative to 0-4 kHz",
    "top_band_drop_db": "energy in 7.5-8 kHz vs 6-7.5 kHz (sharpness of the top cutoff)",
    "flatness_speech": "spectral flatness during speech",
    "centroid_hz": "spectral centroid during speech (brightness)",
}


def features(path: Path) -> dict:
    y, _ = librosa.load(path, sr=SR, mono=True)
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=N_FFT)
    frame_db = 10 * np.log10(S.sum(axis=0) + 1e-12)

    quiet = frame_db <= np.percentile(frame_db, 10)
    speech = frame_db > frame_db.max() - 30
    flat = librosa.feature.spectral_flatness(S=np.sqrt(S))[0]

    f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=400, sr=SR, frame_length=1024, hop_length=HOP)
    st = 12 * np.log2(f0[voiced] / np.median(f0[voiced])) if voiced.sum() > 5 else np.zeros(1)

    def band(lo, hi):
        return S[(freqs >= lo) & (freqs < hi)][:, speech].sum() + 1e-12

    return {
        "gap_noise_db": frame_db[quiet].mean(),
        "gap_flatness": flat[quiet].mean(),
        "pause_frac": 1 - speech.mean(),
        "pitch_std_st": st.std(),
        "pitch_range_st": np.percentile(st, 95) - np.percentile(st, 5),
        "voiced_frac": voiced.mean(),
        "hf_ratio_db": 10 * np.log10(band(4000, 8001) / band(0, 4000)),
        "top_band_drop_db": 10 * np.log10(band(7500, 8001) / band(6000, 7500)),
        "flatness_speech": flat[speech].mean(),
        "centroid_hz": librosa.feature.spectral_centroid(S=np.sqrt(S), sr=SR)[0][speech].mean(),
    }


def main():
    set_dir = Path(sys.argv[1]).expanduser()
    lines = (set_dir / "manifest.tsv").read_text().splitlines()
    header = lines[0].split("\t")
    rows = [dict(zip(header, l.split("\t"))) for l in lines[1:]]

    names = list(FEATURES)
    X, y, spk = [], [], []
    for r in rows:
        sub = "real" if r["label"] == "bonafide" else "fake"
        f = features(set_dir / sub / r["filename"])
        X.append([f[n] for n in names])
        y.append(int(r["label"] == "spoof"))
        spk.append(r["filename"].split(f"_{sub}_")[0])
    X, y, spk = np.array(X), np.array(y), np.array(spk)
    speakers = sorted(set(spk))

    print(f"{len(y)} clips, speakers {speakers}, {y.sum()} fake / {len(y) - y.sum()} real\n")

    # 1. Each feature alone: AUC per speaker. >0.5 means "higher value = more likely fake".
    # A feature is only trustworthy if it points the same way for every speaker.
    print("Per-feature AUC (1.0 = perfectly separates, 0.5 = useless, 0.0 = perfectly reversed)")
    print(f"{'feature':18}" + "".join(f"{s:>8}" for s in speakers) + "  mean real -> mean fake")
    for j, n in enumerate(names):
        aucs = [roc_auc_score(y[spk == s], X[spk == s, j]) for s in speakers]
        real_m, fake_m = X[y == 0, j].mean(), X[y == 1, j].mean()
        agree = "same way" if all(a > 0.5 for a in aucs) or all(a < 0.5 for a in aucs) else "DISAGREE"
        print(f"{n:18}" + "".join(f"{a:8.2f}" for a in aucs) + f"  {real_m:9.3f} -> {fake_m:9.3f}  {agree}")

    # 2. Cross-speaker test: train on one voice, test on the other.
    print("\nCross-speaker logistic regression")
    for test in speakers:
        tr, te = spk != test, spk == test
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
        clf.fit(X[tr], y[tr])
        p = clf.predict_proba(X[te])[:, 1]
        acc = ((p > 0.5) == y[te]).mean()
        print(f"  train on {','.join(s for s in speakers if s != test):6} -> test on {test:6}: "
              f"AUC {roc_auc_score(y[te], p):.2f}, accuracy {acc:.0%} ({te.sum()} clips)")
        coefs = clf[-1].coef_[0]
        top = np.argsort(-np.abs(coefs))[:3]
        print("    strongest cues: " + ", ".join(f"{names[k]} ({coefs[k]:+.2f})" for k in top))

    print("\nFeature meanings:")
    for n, d in FEATURES.items():
        print(f"  {n:18} {d}")


if __name__ == "__main__":
    main()
