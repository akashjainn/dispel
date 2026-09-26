# ml/: fitting and checking the hearsay release

Weights and data never go in git. Everything here runs on the training PC (`~/hackgt`).

## Release v3p = v3 neural detector + prosody, fused
1. Score DiffSSD validation with the chosen v3 checkpoint (done by training at each epoch:
   `data/checkpoints/v3_diffssd/val_scores_ep<N>.npz`; 4,523 clips x {clean, ffmpeg atempo stretch + noise,
   librosa phase-vocoder stretch + noise}).
2. Prosody features for the same cached audio: `results/pitch_v3val.csv` (13,569 rows).
3. Fit and write the release folder:
   ```sh
   python ml/fit_fusion.py --v3-scores data/checkpoints/v3_diffssd/val_scores_ep1.npz \
     --prosody results/pitch_v3val.csv --checkpoint data/checkpoints/v3_diffssd/best.pt \
     --backbone-config data/release/v2e/backbone_config --out data/release/v3p_ep1 --name v3p-ep1
   ```
4. Sanity check on labelled outside clips (evaluation only, never training):
   `MODEL_DIR=data/release/v3p_ep1 python ml/check_clips.py data/teammates`

## Results so far (out-of-fold, 5 folds grouped by clip; minDCF at P(synthetic)=0.3, false alarm cost 4)
v3 epoch 1 checkpoint, `val_scores_ep1.npz`, run 2026-09-26 ~03:00 ET:

| condition | v3 alone | v3 + prosody, additive (shipped) | v3 + prosody, one GBM (not shipped) |
|---|---|---|---|
| clean | 0.011 | 0.006 | 0.006 |
| ffmpeg atempo stretch + noise (held out from training) | 0.039 | 0.025 | 0.026 |
| librosa phase-vocoder stretch + noise | 0.396 | 0.245 | 0.233 |

Shipped fusion: `LLR = 0.567 * v3 + 1.028 * q - 1.690`, where `q` is the logit of a prosody-only
gradient-boosted model, clipped to ±3.

**Why additive and not one GBM on everything.** The single GBM was marginally better on validation, but
it flattens the neural score wherever v3 is confidently "real", because no validation fakes live there.
New voices land exactly there. On the teammate check (20 real recordings + 20 consented ElevenLabs clones,
one laptop mic; evaluation only) the AUC was v3 alone 0.985, one GBM 0.742, additive 0.980.
Note this check influenced the design choice, so it is no longer a fully independent test.

## Known gap (2026-09-26): calibration on new voices
With the additive release, all 20 real teammate clips are "likely real", but 18 of 20 clones are also
"likely real" (2 "likely synthetic"). The ranking is right (AUC 0.98); the absolute scores are not:
the clones score as fake-ish relative to the real recordings, yet still below validation's decision
boundary. The NSA TSV only needs the ranking; the app's verdicts need more training data from new
voices and recording setups before a live demo.
