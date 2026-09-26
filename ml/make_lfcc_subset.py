"""Build a compact 16 kHz DiffSSD subset for the LFCC model on the MSI laptop.

train:        all set==train reals + up to 1500 per train generator (16 kHz, first 8 s, int16 WAV)
val_clean:    all set==val reals + up to 300 per val generator
val_atempo:   same val clips, NSA-like with the HELD-OUT stretch method:
              ffmpeg atempo U(0.9,1.1), then white noise SNR U(10,30) dB (seeded per clip)
Writes <out>/{train,val_clean,val_atempo}/<id>.wav and <out>/meta.csv
"""
import csv, os, sys, zlib, subprocess, random
from multiprocessing import Pool
import numpy as np, soundfile as sf, librosa

ROOT = os.path.expanduser("~/hackgt/data/diffssd")
SPLIT = os.path.expanduser("~/hackgt/data/diffssd_hf/train_val_test_splits.csv")
OUT = os.path.expanduser("~/hackgt/data/lfcc_subset")
SR, MAXS = 16000, 8.0

def load16(p):
    x, _ = librosa.load(p, sr=SR, mono=True, res_type="soxr_hq")
    return x[: int(MAXS * SR)].astype(np.float32)

def atempo(x, r):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "pipe:0",
                          "-af", f"atempo={r:.4f}", "-f", "s16le", "pipe:1"], input=pcm, capture_output=True, check=True).stdout
    return np.frombuffer(out, "<i2").astype(np.float32) / 32767

def work(row):
    split, uid, path = row["subset"], row["id"], row["filename"]
    try:
        x = load16(os.path.join(ROOT, path))
        if len(x) < SR:  # < 1 s: skip
            return None
        outs = []
        if split == "train":
            outs.append(("train", x))
        else:
            outs.append(("val_clean", x))
            rng = np.random.default_rng(zlib.crc32(path.encode()) ^ 13)
            y = atempo(x, rng.uniform(0.9, 1.1))
            snr = rng.uniform(10, 30)
            p = np.mean(y ** 2) + 1e-12
            y = y + rng.standard_normal(len(y)).astype(np.float32) * np.sqrt(p / 10 ** (snr / 10))
            outs.append(("val_atempo", y))
        for d, a in outs:
            sf.write(os.path.join(OUT, d, uid + ".wav"), np.clip(a, -1, 1), SR, subtype="PCM_16")
        return row
    except Exception as e:
        print("ERR", path, e, file=sys.stderr)
        return None

if __name__ == "__main__":
    rows = list(csv.DictReader(open(SPLIT)))
    rnd = random.Random(13)
    pick = []
    for s, cap in (("train", 1500), ("val", 300)):
        byk = {}
        for r in rows:
            if r["set"] == s:
                byk.setdefault(r["method_name"], []).append(r)
        for k, v in sorted(byk.items()):
            rnd.shuffle(v)
            keep = v if v[0]["target"] == "0" else v[:cap]
            for r in keep:
                pick.append({**r, "subset": s})
    for i, r in enumerate(pick):
        r["id"] = f"{r['subset']}_{i:06d}"
    for d in ("train", "val_clean", "val_atempo"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    print("clips:", len(pick), flush=True)
    done = []
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 3) as pool:
        for n, r in enumerate(pool.imap_unordered(work, pick, chunksize=32)):
            if r: done.append(r)
            if n % 2000 == 0: print(n, flush=True)
    with open(os.path.join(OUT, "meta.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "subset", "filename", "method_name", "source", "target"])
        w.writeheader()
        for r in sorted(done, key=lambda r: r["id"]):
            w.writerow({k: r[k] for k in w.fieldnames})
    print("DONE", len(done), flush=True)
