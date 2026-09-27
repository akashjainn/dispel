"""NSA-hint feature test: breaths/pauses, spectrogram 'ribs' (harmonic structure extent), and start-vs-middle drift.
For each feature: AUC (fake vs real) on several independent pairings; a useful feature points the SAME way everywhere.
Out: results/hint_feats.csv (per clip), results/hint_feats.md (table)."""
import zlib
import csv, sys, glob
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd, soundfile as sf, librosa
R = Path.home() / "hackgt"; sys.path.insert(0, str(R / "scratch/features"))
SR = 16000
def load(p):
    p = str(p)
    try:
        x, sr = sf.read(p, dtype="float32")
    except Exception:
        x, sr = librosa.load(p, sr=None, mono=True)
    if x.ndim > 1: x = x.mean(1)
    if sr != SR: x = librosa.resample(x, orig_sr=sr, target_sr=SR)
    return x / (np.abs(x).max() + 1e-9)
def runs(m):
    m = np.concatenate([[0], m.astype(int), [0]]); d = np.diff(m); return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))
def feats(x):
    hop, win = 160, 400; o = {}
    rms = librosa.feature.rms(y=x, frame_length=win, hop_length=hop)[0]; db = 20 * np.log10(rms + 1e-7); peak = np.percentile(db, 95)
    speech = db > peak - 30; idx = np.where(speech)[0]
    if len(idx) < 30: return o
    a, b = idx[0], idx[-1]; dur = (b - a + 1) * 0.01
    inner = ~speech[a:b + 1]; pauses = [(s, e) for s, e in runs(inner) if e - s >= 8]
    o["pauses_per_s"] = len(pauses) / dur; o["pause_frac"] = sum(e - s for s, e in pauses) * 0.01 / dur
    o["longest_pause_s"] = max([(e - s) * 0.01 for s, e in pauses], default=0.0)
    br = 0; lv = []
    for s, e in pauses:
        seg = db[a + s:a + e]; lv.append(np.median(seg) - peak)
        bump = (seg > np.percentile(seg, 10) + 6) & (seg < peak - 12); br += any(e2 - s2 >= 6 for s2, e2 in runs(bump))
    o["breaths_per_s"] = br / dur; o["pause_level_rel_db"] = float(np.median(lv)) if lv else -60.0
    o["floor_db"] = float(np.percentile(db, 5) - peak)
    # F0 + harmonic structure per band (the 'ribs')
    f0, vf, vp = librosa.pyin(x, fmin=65, fmax=400, sr=SR, frame_length=1024, hop_length=hop)
    S = np.abs(librosa.stft(x, n_fft=2048, hop_length=hop, win_length=1024)); fr = librosa.fft_frequencies(sr=SR, n_fft=2048)
    n = min(S.shape[1], len(f0)); vi = [i for i in range(n) if vf[i] and np.isfinite(f0[i])]
    if len(vi) >= 10:
        bands = [(0, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 5000), (5000, 6000), (6000, 8000)]
        H = np.zeros((len(vi), len(bands)))
        for j, i in enumerate(vi):
            spec = S[:, i] ** 2 + 1e-12; F = f0[i]
            for k, (lo, hi) in enumerate(bands):
                hs = np.arange(np.ceil(lo / F), np.floor(hi / F) + 1) * F
                hs = hs[(hs > 0) & (hs < 7990)]
                if len(hs) == 0: continue
                on = np.mean([spec[np.argmin(np.abs(fr - h))] for h in hs]); off = np.mean([spec[np.argmin(np.abs(fr - h - F / 2))] for h in hs])
                H[j, k] = 10 * np.log10(on / off)
        med = np.median(H, 0)
        for k, v in enumerate(med): o[f"harm_db_b{k}"] = float(v)
        o["ribs_bands"] = int(np.sum(med > 6))          # how many 1-kHz-ish bands show clear harmonics
        o["harm_hi_minus_lo"] = float(np.mean(med[4:]) - np.mean(med[:2]))
        # start vs middle drift (does the voice 'run out of breath'?)
        v = np.array(vi); T = len(vi); fz = np.log(f0[v])
        o["f0_slope"] = float(np.polyfit(np.linspace(0, 1, T), fz, 1)[0])
        e = db[v[v < len(db)]]; o["energy_slope"] = float(np.polyfit(np.linspace(0, 1, len(e)), e, 1)[0])
        q = max(3, T // 5); o["f0_start_minus_mid"] = float(np.median(fz[:q]) - np.median(fz[2 * q:3 * q]))
        tilt = np.log(S[fr > 4000][:, v[v < S.shape[1]]].sum(0) + 1e-9) - np.log(S[fr < 1000][:, v[v < S.shape[1]]].sum(0) + 1e-9)
        o["tilt_start_minus_mid"] = float(np.median(tilt[:q]) - np.median(tilt[2 * q:3 * q]))
        o["f0_sd_st"] = float(np.std(12 * np.log2(f0[v])))
    return o
def job(it):
    s, y, p = it
    try: return {"set": s, "label": y, "path": p, **feats(load(p))}
    except Exception as e: return {"set": s, "label": y, "path": p, "err": str(e)[:80]}
if __name__ == "__main__":
    train_spk = {r["spk"] for r in csv.DictReader(open(R / "data/splits/v5_team.csv")) if r["split"] == "train"}
    I = []
    M = pd.read_csv(R / "evalbundle/manifest.csv")
    for r in M.itertuples():
        if r.set == "diffssd_test_holdout" and zlib.crc32(r.file.encode()) % 3: continue   # 1/3 subsample, same every run
        I.append((r.set if r.set != "libri_clone" else "libri_clone_" + r.detail, r.label, str(R / "evalbundle" / r.file)))
    for r in csv.DictReader(open(R / "data/consent/sts/meta.csv")): I.append(("voice_changer", 1, str(R / r["file"])))
    for r in csv.DictReader(open(R / "data/el_matrix/meta.csv")):
        if r["avenue"].startswith("tts_") or r["avenue"] in ("voice_design", "v3_tags"): I.append(("el_tts", int(r["label"]), str(R / r["file"])))
        if r["avenue"] == "isolator_real": I.append(("isolator_real", 0, str(R / r["file"])))
    for p in sorted(glob.glob(str(R / "data/consent/team/real/*.wav"))): I.append(("team_real_all", 0, p))
    for p in sorted(glob.glob(str(R / "data/consent/team/fake/*.wav"))): I.append(("team_clone_given_all", 1, p))
    with Pool(8) as pool: rows = pool.map(job, I, chunksize=4)
    D = pd.DataFrame(rows); D.to_csv(R / "results/hint_feats.csv", index=False); print("saved", len(D), flush=True)
