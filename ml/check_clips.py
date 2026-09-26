"""Run the full pipeline on labelled clips (label from the file name: 'fake'/'real') and print verdicts.
Evaluation only (e.g. teammates' own recordings vs their ElevenLabs clones). Never train on these.
  MODEL_DIR=data/release/v3p python ml/check_clips.py <dir> [<dir> ...]"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hearsay.orchestrator import Pipeline  # noqa: E402

pipe = Pipeline(os.environ["MODEL_DIR"])
rows = []
for d in sys.argv[1:]:
    for p in sorted(Path(d).glob("*")):
        if p.suffix.lower() not in {".wav", ".mp3", ".flac", ".m4a"}:
            continue
        r = pipe.analyze(str(p), prior=0.5)
        a = {x["name"]: x["llr_contribution"] for x in r["analyzers"]}
        lab = "fake" if "fake" in p.name.lower() else "real" if "real" in p.name.lower() else "?"
        rows.append((lab, r["overall"]["verdict"]))
        print(f"{p.name:28s} {lab:5s} p={r['overall']['probability']:.3f} {r['overall']['verdict']:17s} "
              f"dl={a['dl_detector']:+.2f} prosody={a['prosody']:+.2f} {r['timing_ms']} ms")
for lab in ("real", "fake"):
    v = [x[1] for x in rows if x[0] == lab]
    if v:
        print(lab, {k: v.count(k) for k in ("likely_real", "inconclusive", "likely_synthetic")})
