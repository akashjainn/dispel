"""Runs the analyzers on one clip, fuses them, and builds the INTERFACES.md response.

MODEL_DIR must contain hearsay.json (written by ml/fit_fusion.py), e.g.
  {"name": "v3p", "release": "2026-09-26",
   "detector": {"checkpoint": "v3.pt", "sha256": "...", "backbone_config": "backbone_config"},
   "lfcc": {"checkpoint": "lfcc.pt", "sha256": "..."},
   "fusion": {"file": "fusion.joblib", "sha256": "..."}, "fusion_app": {"file": "fusion_app.joblib", "sha256": "..."}}
"""
import json
import math
import time
import uuid
from pathlib import Path

from . import __version__, audio as A
from .analyzers import prosody, rhythm, spectral, voice
from .analyzers.lfcc import LFCCDetector
from .analyzers.dl_detector import DLDetector, sha256
from .fusion import Fusion

API_VERSION = "0.3"
MIN_S, MAX_S = 1.0, 120.0
LO, HI = 0.25, 0.75  # verdict band on the posterior; placeholder until set from validation (DECISIONS.md)


def sigmoid(t):
    return 1 / (1 + math.exp(-t))


class Pipeline:
    def __init__(self, model_dir, device=None, profile="nsa"):
        """profile "nsa": all six analyzers (best on DiffSSD-like audio; used for the TSV).
        profile "app": neural detector + prosody only (held up better on unfamiliar voices and mics; used by the server)."""
        d = Path(model_dir)
        self.spec = json.load(open(d / "hearsay.json"))
        key = "fusion_app" if profile == "app" and "fusion_app" in self.spec else "fusion"
        self.profile = "app" if key == "fusion_app" else "nsa"
        fz = d / self.spec[key]["file"]
        if self.spec[key].get("sha256") and sha256(fz) != self.spec[key]["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {fz}")
        self.fusion = Fusion(fz)
        self.dl = DLDetector(d, self.spec["detector"], device)
        used = {t["name"] for t in self.fusion.terms}
        self.lfcc = LFCCDetector(d, self.spec["lfcc"]) if "lfcc" in self.spec and "lfcc" in used else None
        self.context = {"prosody_ref": self.fusion.m.get("prosody_ref", {}), "ref": self.fusion.m.get("ref", {})}
        self.feature_analyzers = [(n, m) for n, m in (("prosody", prosody), ("spectral", spectral), ("voice", voice),
                                                       ("rhythm", rhythm)) if n in used]

    def _run(self, x, info):
        """Runs every analyzer the fusion uses. Returns (results by name, fused dict or None)."""
        meta = {"input": info}
        res = {"dl_detector": self.dl.analyze(x, A.SR, meta, self.context)}
        if self.lfcc is not None:
            res["lfcc"] = self.lfcc.analyze(x, A.SR, meta, self.context)
        for n, mod in self.feature_analyzers:
            res[n] = mod.analyze(x, A.SR, meta, self.context)
        feats = {}
        for r in res.values():
            feats.update(r["features"])
        return res, self.fusion.fuse(feats)

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
        _, f = self._run(x, info)
        return None if f is None else sigmoid(f["llr_raw"] / 10.0)

    def analyze(self, src, prior=0.5):
        t0 = time.perf_counter()
        x, info = A.load(src)  # ValueError -> decode_failed
        dur = len(x) / A.SR
        if dur < MIN_S:
            raise ValueError("too_short")
        if dur > MAX_S:
            raise ValueError("too_long")
        res, f = self._run(x, info)
        dl = res["dl_detector"]
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
            "model": {"name": f'{self.spec["name"]}/{self.profile}', "release": self.spec.get("release", "")},
            "overall": {"llr": round(f["llr"], 3), "prior": prior, "probability": round(prob, 4), "verdict": verdict,
                        "fusion_bias": round(f["bias"], 3)},
            "segments": segs,
            "analyzers": [{"name": n, "ran": r["ran"], "finding": r["finding"],
                           "llr_contribution": round(f["contrib"].get(n, 0.0), 3), "ms": r["ms"]} for n, r in res.items()],
            "manipulation": {"type": "unknown", "confidence": 0.0},
            "channel": ch,
            "transcript": None,
            "limitations": lim,
            "timing_ms": int((time.perf_counter() - t0) * 1000),
            "pipeline_version": __version__,
        }
