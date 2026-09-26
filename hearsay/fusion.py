"""Fusion: combine analyzer features into one calibrated log-likelihood ratio (synthetic vs real).

Additive by design (ml/fit_fusion.py):  LLR = w_v3 * v3 + w_p * q + b
  v3  neural detector score (logit difference)
  q   logit of a prosody-only gradient-boosted model, clipped to +-qclip
Weights come from a class-balanced logistic regression on out-of-fold validation scores, so LLR is prior-free.
Being additive in v3 keeps the neural ranking intact on audio unlike the validation set (a single GBM on
v3 + prosody flattened it: teammates' clips AUC 0.985 -> 0.742), and the clip bounds how far prosody can move it.
"""
import math

import joblib
import numpy as np

CAP = math.log(100.0)


def logit(p):
    p = min(max(p, 1e-12), 1 - 1e-12)
    return math.log(p / (1 - p))


class Fusion:
    def __init__(self, path):
        self.m = joblib.load(path)
        self.features = self.m["features"]

    def llr_v3(self, s):
        a, b = self.m["platt_v3"]
        return a * s + b

    def prosody_q(self, feats):
        row = np.array([[feats.get(k, np.nan) for k in self.features]], dtype=float)
        p = float(self.m["prosody_gbm"].predict_proba(row)[0, 1])
        return float(np.clip(logit(p), -self.m["qclip"], self.m["qclip"]))

    def raw(self, feats):
        """Uncapped fused LLR. None if the neural detector did not run (clip is then unscorable)."""
        if feats.get("v3") is None or not np.isfinite(feats["v3"]):
            return None
        w0, w1, b = self.m["weights"]
        return w0 * feats["v3"] + w1 * self.prosody_q(feats) + b

    def fuse(self, feats):
        r = self.raw(feats)
        if r is None:
            return None
        w0, w1, b = self.m["weights"]
        cap = lambda t: float(np.clip(t, -CAP, CAP))
        # contributions are the two additive terms (uncapped), so they sum exactly to llr_raw
        return {"llr_raw": r, "llr": cap(r), "llr_v3": cap(self.llr_v3(feats["v3"])),
                "contrib": {"dl_detector": float(w0 * feats["v3"] + b), "prosody": float(w1 * self.prosody_q(feats))}}
