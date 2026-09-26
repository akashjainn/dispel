"""NSA TSV writer and validator.

  python -m hearsay.cli predict <audio_dir> -o <Team>_predictions.tsv [--template HearsayScoreKey4TeamX.tsv]
  python -m hearsay.cli validate <Team>_predictions.tsv --template HearsayScoreKey4TeamX.tsv

With --template, every template row is kept in its order (NSA: never remove rows) and only column 2 changes.
Header is exactly `filename<TAB>cm-score`, LF line endings, higher score = more likely synthetic.
Clips that cannot be scored go to the bottom of the ranking (the "real" end), because flagging a
real clip costs 4x a miss."""
import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

HEADER = ["filename", "cm-score"]
AUDIO = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".webm"}


def read_template(p):
    with open(p, newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    if rows[0] != HEADER:
        sys.exit(f"template header is {rows[0]!r}, expected {HEADER!r}")
    return [r[0] for r in rows[1:]]


def write_tsv(path, names, scores):
    with open(path, "w", newline="\n") as fh:
        fh.write("\t".join(HEADER) + "\n")
        for n in names:
            fh.write(f"{n}\t{scores[n]:.8f}\n")


def validate(path, template=None):
    errs = []
    raw = open(path, "rb").read()
    if b"\r" in raw:
        errs.append("CR characters found (must be LF only)")
    rows = list(csv.reader(raw.decode().splitlines(), delimiter="\t"))
    if rows[0] != HEADER:
        errs.append(f"bad header {rows[0]!r}")
    names = [r[0] for r in rows[1:]]
    vals = []
    for i, r in enumerate(rows[1:], 2):
        if len(r) != 2:
            errs.append(f"line {i}: {len(r)} columns")
            continue
        try:
            v = float(r[1])
        except ValueError:
            errs.append(f"line {i}: not a number {r[1]!r}")
            continue
        if not (0.0 <= v <= 1.0) or math.isnan(v):
            errs.append(f"line {i}: {v} outside [0, 1]")
        vals.append(v)
    if len(set(names)) != len(names):
        errs.append("duplicate filenames")
    if template:
        t = read_template(template)
        if names != t:
            errs.append(f"rows differ from template (ours {len(names)}, template {len(t)}; "
                        f"missing {len(set(t) - set(names))}, extra {len(set(names) - set(t))}, order same: {names == t})")
    if vals:
        distinct = len(set(vals))
        placeholder = sum(v in (0.5, 0.006) for v in vals)
        print(f"{len(vals)} rows, {distinct} distinct scores, min {min(vals):.6f} max {max(vals):.6f}, "
              f"placeholder-valued rows {placeholder}, share > 0.5: {sum(v > 0.5 for v in vals) / len(vals):.1%}")
        if distinct < 0.95 * len(vals):
            errs.append(f"only {distinct} distinct scores for {len(vals)} rows (ties hurt ranking)")
    for e in errs:
        print("ERROR:", e)
    print("OK" if not errs else f"{len(errs)} problem(s)")
    return not errs


def predict(a):
    from .orchestrator import Pipeline
    d = Path(a.audio_dir)
    names = read_template(a.template) if a.template else sorted(p.name for p in d.iterdir() if p.suffix.lower() in AUDIO)
    pipe = Pipeline(a.model_dir, profile=a.profile)
    scores, failed, t0 = {}, [], time.time()
    for i, n in enumerate(names, 1):
        p = d / n
        s = pipe.tsv_score(str(p)) if p.exists() else None
        if s is None:
            failed.append(n)
        else:
            scores[n] = s
        if i % 100 == 0:
            print(f"{i}/{len(names)} ({i / (time.time() - t0):.1f} clips/s), unscorable so far {len(failed)}", flush=True)
    floor = min(scores.values(), default=0.5)
    for j, n in enumerate(failed):  # bottom of the ranking, still distinct
        scores[n] = max(floor * 0.5 * (1 - 1e-4 * j), 1e-7)
    write_tsv(a.out, names, scores)
    print(f"wrote {a.out}: {len(names)} rows, {len(failed)} unscorable -> real end: {failed[:10]}")
    return validate(a.out, a.template)


def main():
    ap = argparse.ArgumentParser(prog="hearsay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict")
    p.add_argument("audio_dir")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--template")
    p.add_argument("--model-dir", default=os.getenv("MODEL_DIR", "/models"))
    p.add_argument("--profile", default="nsa", choices=["nsa", "app"])
    v = sub.add_parser("validate")
    v.add_argument("tsv")
    v.add_argument("--template")
    a = ap.parse_args()
    ok = predict(a) if a.cmd == "predict" else validate(a.tsv, a.template)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
