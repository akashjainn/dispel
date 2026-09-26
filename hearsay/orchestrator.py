"""Runs the analyzers on one clip, fuses them, and builds the INTERFACES.md response.

MODEL_DIR must contain hearsay.json (written by ml/fit_fusion.py), e.g.
  {"name": "v3p", "release": "2026-09-26",
   "detector": {"checkpoint": "v3.pt", "sha256": "...", "backbone_config": "backbone_config"},
   "fusion": {"file": "fusion.joblib", "sha256": "..."}}
"""
import json
import math
import time
import uuid
from pathlib import Path

from . import __version__, audio as A
from .analyzers import prosody
from .analyzers.dl_detector import DLDetector, sha256
from .fusion import Fusion

API_VERSION = "0.3"
MIN_S, MAX_S = 1.0, 120.0
LO, HI = 0.25, 0.75  # verdict band on the posterior; placeholder until set from validation (DECISIONS.md)


def sigmoid(t):
    return 1 / (1 + math.exp(-t))


class Pipeline:
    def __init__(self, model_dir, device=None):
        d = Path(model_dir)
        self.spec = json.load(open(d / "hearsay.json"))
        fz = d / self.spec["fusion"]["file"]
        if self.spec["fusion"].get("sha256") and sha256(fz) != self.spec["fusion"]["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {fz}")
        self.fusion = Fusion(fz)
        self.dl = DLDetector(d, self.spec["detector"], device)
        self.context = {"prosody_ref": self.fusion.m.get("prosody_ref", {})}

    def _run(self, x, info):
        meta = {"input": info}
        dl = self.dl.analyze(x, A.SR, meta, self.context)
        pr = prosody.analyze(x, A.SR, meta, self.context)
        feats = {**dl["features"], **pr["features"]}
        return dl, pr, self.fusion.fuse(feats)

    def tsv_score(self, path):
        """Score for the NSA TSV: a continuous probability, higher = more likely synthetic.
        Only the ranking matters for minDCF, so the uncapped LLR is squashed gently (no ties at the cap).
        Returns None if the clip cannot be scored."""
        try:
            x, info = A.load(path)
        except ValueError:
            return None
        if len(x) < 0.3 * A.SR:
            return None
        _, _, f = self._run(x, info)
        return None if f is None else sigmoid(f["llr_raw"] / 10.0)

    def analyze(self, src, prior=0.5):
        t0 = time.perf_counter()
        x, info = A.load(src)  # ValueError -> decode_failed
        dur = len(x) / A.SR
        if dur < MIN_S:
            raise ValueError("too_short")
        if dur > MAX_S:
            raise ValueError("too_long")
        dl, pr, f = self._run(x, info)
        if f is None:
            raise RuntimeError("internal: neural detector failed: " + dl["finding"])
        lp = math.log(prior / (1 - prior)) if 0 < prior < 1 else (-50.0 if prior <= 0 else 50.0)
        prob = sigmoid(f["llr"] + lp)
        verdict = "likely_synthetic" if prob >= HI else "likely_real" if prob <= LO else "inconclusive"
        segs = [{"start_s": a, "end_s": min(b, dur), "llr": round(self.fusion.llr_v3(s), 3),
                 "probability": round(sigmoid(max(min(self.fusion.llr_v3(s), 4.6), -4.6) + lp), 4)}
                for a, b, s in dl.get("windows", [])]
        ch = A.channel_note(x, info)
        lim = ["Only the first 12 s are scored by the neural detector; prosody uses up to 30 s.",
               "Validated on DiffSSD generators with added noise and time-stretching; new generators may score lower.",
               "A single 'likely synthetic' result is not proof on its own. Corroborate it with the source and context."]
        if ch["phone_like"]:
            lim.insert(0, "Phone-like or narrowband audio: reliability is lower.")
        if len(segs) > 1 and max(s["llr"] for s in segs) - min(s["llr"] for s in segs) > 4:
            lim.insert(0, "Segments disagree strongly, which could mean an edit. This is a lead to check, not proof.")
        return {
            "version": API_VERSION,
            "clip_id": str(uuid.uuid4()),
            "duration_s": round(dur, 3),
            "input": info,
            "model": {"name": self.spec["name"], "release": self.spec.get("release", "")},
            "overall": {"llr": round(f["llr"], 3), "prior": prior, "probability": round(prob, 4), "verdict": verdict},
            "segments": segs,
            "analyzers": [
                {"name": "dl_detector", "ran": dl["ran"], "finding": dl["finding"],
                 "llr_contribution": round(f["contrib"]["dl_detector"], 3), "ms": dl["ms"]},
                {"name": "prosody", "ran": pr["ran"], "finding": pr["finding"],
                 "llr_contribution": round(f["contrib"]["prosody"], 3), "ms": pr["ms"]},
            ],
            "manipulation": {"type": "unknown", "confidence": 0.0},
            "channel": ch,
            "transcript": None,
            "limitations": lim,
            "timing_ms": int((time.perf_counter() - t0) * 1000),
            "pipeline_version": __version__,
        }
