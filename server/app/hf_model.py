"""Third-party stand-in detector from Hugging Face, used only while our own release (hearsay/, MODEL_DIR) is not loaded.

HF_MODEL names a two-label audio-classification checkpoint (docker/compose.prod.yml sets
mo-thecreator/Deepfake-audio-detection, wav2vec2-base, Apache-2.0) and HF_REVISION pins its commit.
Weights are downloaded once into HF_HOME and inference runs on this server: audio never goes to Hugging Face.
Windowing is hearsay's (up to 3 non-overlapping 4 s windows at 16 kHz), so the segment timeline means the same thing."""
import math
import time
import uuid

import torch
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

from hearsay import __version__, audio as A
from hearsay.analyzers.dl_detector import windows

MIN_S, MAX_S = 1.0, 120.0
LLR_CAP = math.log(100)
LO, HI = 0.25, 0.75  # same placeholder verdict band as hearsay/orchestrator.py
FAKE_LABELS = ("fake", "spoof", "synthetic", "deepfake")


def _sigmoid(t):
    return 1 / (1 + math.exp(-t))


def _cap(t):
    return max(min(t, LLR_CAP), -LLR_CAP)


class HFDetector:
    def __init__(self, repo, revision=None):
        self.repo = repo
        self.fe = AutoFeatureExtractor.from_pretrained(repo, revision=revision)
        self.model = AutoModelForAudioClassification.from_pretrained(repo, revision=revision).eval()
        labels = {str(v).lower(): int(k) for k, v in self.model.config.id2label.items()}
        fake = [labels[n] for n in FAKE_LABELS if n in labels]
        if len(labels) != 2 or not fake:
            raise RuntimeError(f"{repo}: expected two labels, one of {FAKE_LABELS}; got {sorted(labels)}")
        self.fake, self.real = fake[0], 1 - fake[0]
        self.name = f"hf:{repo}"
        self.release = (revision or "main")[:7]

    @torch.inference_mode()
    def window_scores(self, w):
        """Per-window logit[fake] - logit[real], i.e. the model's log-odds that the window is synthetic."""
        inp = self.fe(list(w), sampling_rate=A.SR, return_tensors="pt")
        logits = self.model(**inp).logits.float()
        return (logits[:, self.fake] - logits[:, self.real]).numpy()

    def analyze(self, src, prior=0.5):
        """Same response shape as hearsay.orchestrator.Pipeline.analyze. ValueError("too_short"/"too_long"/...) on bad input."""
        t0 = time.perf_counter()
        x, info = A.load(src)  # ValueError -> decode_failed; bytes go to a temp file that is deleted
        dur = len(x) / A.SR
        if dur < MIN_S:
            raise ValueError("too_short")
        if dur > MAX_S:
            raise ValueError("too_long")
        t1 = time.perf_counter()
        w, starts = windows(x)
        s = self.window_scores(w)
        ms = int((time.perf_counter() - t1) * 1000)
        raw = float(s.mean())
        llr = _cap(raw)
        lp = math.log(prior / (1 - prior)) if 0 < prior < 1 else (-50.0 if prior <= 0 else 50.0)
        prob = _sigmoid(llr + lp)
        verdict = "likely_synthetic" if prob >= HI else "likely_real" if prob <= LO else "inconclusive"
        segs = [{"start_s": a, "end_s": min(a + 4.0, dur), "llr": round(float(v), 3),
                 "probability": round(_sigmoid(_cap(float(v)) + lp), 4)} for a, v in zip(starts, s)]
        ch = A.channel_note(x, info)
        lim = ["Only the first 12 s are scored.",
               "A single 'likely synthetic' result is not proof on its own. Corroborate it with the source and context."]
        if ch["phone_like"]:
            lim.insert(0, "Phone-like or narrowband audio: reliability is lower.")
        if len(segs) > 1 and max(g["llr"] for g in segs) - min(g["llr"] for g in segs) > 4:
            lim.insert(0, "Segments disagree strongly, which could mean an edit. This is a lead to check, not proof.")
        return {
            "clip_id": str(uuid.uuid4()),
            "duration_s": round(dur, 3),
            "input": info,
            "model": {"name": self.name, "release": self.release},
            "overall": {"llr": round(llr, 3), "prior": prior, "probability": round(prob, 4), "verdict": verdict,
                        "fusion_bias": 0.0},
            "segments": segs,
            "analyzers": [{"name": "hf_detector", "ran": True, "llr_contribution": round(raw, 3), "ms": ms,
                           "finding": f"Neural detector score {raw:+.1f} over {len(s)} window(s) of 4 s."}],
            "manipulation": {"type": "unknown", "confidence": 0.0},
            "channel": ch,
            "transcript": None,
            "limitations": lim,
            "timing_ms": int((time.perf_counter() - t0) * 1000),
            "pipeline_version": __version__,
        }
