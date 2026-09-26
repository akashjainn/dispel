"""Fusion: combine analyzer outputs into one calibrated log-likelihood ratio (synthetic vs real).

Additive by design (fit by ml/fit_fusion.py on DiffSSD validation, out-of-fold):
    LLR = b + sum_i w_i * t_i
  t_i for a neural detector ("raw" term) = its score (logit difference): dl_detector (v3), lfcc
  t_i for a feature analyzer ("gbm" term) = logit of a small gradient-boosted model on that analyzer's features,
      clipped to +-qclip: prosody, spectral, voice, rhythm
Weights come from a class-balanced logistic regression, so LLR is prior-free. Additive keeps each term's ranking
intact on unfamiliar audio (a single GBM over everything flattened the neural score: teammate check AUC 0.985 -> 0.742),
and it makes the report exact: each analyzer's contribution is w_i * t_i, and they sum to the LLR.
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
        self.terms = self.m["terms"]

    def llr_v3(self, s):
        a, b = self.m["platt_v3"]
        return a * s + b

    def term_values(self, feats):
        vals = {}
        for t in self.terms:
            if t["type"] == "raw":
                v = feats.get(t["feature"], np.nan)
                vals[t["name"]] = float(v) if v is not None and np.isfinite(v) else float(t["impute"])
            else:
                row = np.array([[feats.get(k, np.nan) for k in t["features"]]], dtype=float)
                p = float(t["model"].predict_proba(row)[0, 1])
                vals[t["name"]] = float(np.clip(logit(p), -self.m["qclip"], self.m["qclip"]))
        return vals

    def fuse(self, feats):
        """None if the neural detector did not run (the clip is then unscorable)."""
        v3 = feats.get("v3")
        if v3 is None or not np.isfinite(v3):
            return None
        vals = self.term_values(feats)
        contrib = {t["name"]: float(w * vals[t["name"]]) for t, w in zip(self.terms, self.m["weights"])}
        contrib[self.terms[0]["name"]] += float(self.m["bias"])  # bias shown with the first (neural) term
        r = float(sum(contrib.values()))
        return {"llr_raw": r, "llr": float(np.clip(r, -CAP, CAP)),
                "llr_v3": float(np.clip(self.llr_v3(v3), -CAP, CAP)), "contrib": contrib}
