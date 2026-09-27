"""Feasibility: are NSA's test clips (resampled) copies of DiffSSD files? For each test clip, candidates = DiffSSD files
whose header duration is within 1 ms; each candidate is decoded + resampled to 16 kHz with ffmpeg, and compared by
max normalized cross-correlation (lags up to +-20 ms). Out: results/nsa_match.csv (best candidate per test clip)."""
import csv, subprocess, sys
from pathlib import Path
from multiprocessing import Pool
import numpy as np, soundfile as sf
R = Path.home() / "hackgt"; TD = R / "data/nsa/test/HackGTHearsayTesting"
H = list(csv.DictReader(open(R / "results/scores/diffssd_profile_headers.csv")))
meta = {r["filename"]: r for r in csv.DictReader(open(R / "data/diffssd_hf/train_val_test_splits.csv"))}
dd = np.array([float(r["dur"]) for r in H]); names = [r["filename"] for r in H]; o = np.argsort(dd); dds = dd[o]
names_test = sorted(p.name for p in TD.glob("*.wav"))
def ff16(p):
    b = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(p), "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"], capture_output=True).stdout
    return np.frombuffer(b, "<f4")
def ncc(a, b, maxlag=320):
    n = min(len(a), len(b)); a = a[:n] - a[:n].mean(); b = b[:n] - b[:n].mean()
    L = 1 << int(np.ceil(np.log2(2 * n)))
    c = np.fft.irfft(np.fft.rfft(a, L) * np.conj(np.fft.rfft(b, L)), L)
    c = np.r_[c[-maxlag:], c[:maxlag + 1]]
    return float(np.abs(c).max() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
def job(tn):
    x, sr = sf.read(TD / tn, dtype="float32"); t = len(x) / sr
    i = np.searchsorted(dds, t - 0.001); j = np.searchsorted(dds, t + 0.001)
    best = (0.0, "", 0)
    for k in o[i:j]:
        y = ff16(R / "data/diffssd" / names[k])
        if len(y) == 0: continue
        s = ncc(x, y)
        if s > best[0]: best = (s, names[k], j - i)
    return tn, round(t, 4), best[0], best[1], best[2]
if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else len(names_test)
    with Pool(4) as p:
        res = p.map(job, names_test[:lim], chunksize=4)
    with open(R / "results/nsa_match.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["file", "dur", "ncc", "match", "n_cand", "set", "method", "target"])
        for tn, t, s, m, n in res:
            mm = meta.get(m, {}); w.writerow([tn, t, round(s, 4), m, n, mm.get("set"), mm.get("method_name"), mm.get("target")])
    s = np.array([r[2] for r in res]); print(f"{len(res)} clips: ncc>0.9 {np.mean(s > 0.9):.3f}, >0.5 {np.mean(s > 0.5):.3f}, median {np.median(s):.3f}")
