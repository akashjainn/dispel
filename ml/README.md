# ml/: fitting and checking the hearsay release

Weights and data never go in git. Everything here runs on the training PC (`~/hackgt`).

## The pipeline: six analyzers, one additive fusion
| analyzer | what it measures | model |
|---|---|---|
| `dl_detector` | learned artifacts | XLS-R 300M fine-tuned on DiffSSD with noise + time-stretch augmentation (v3) |
| `lfcc` | linear-frequency cepstra | LFCC + light CNN (0.27M params), `ml/train_lfcc.py` |
| `prosody` | pitch contour and voice quality (15 features) | Praat F0, jitter, shimmer, HNR |
| `spectral` | band energies, roll-off, spectral change, voice periodicity (15) | STFT, cepstral peak prominence |
| `voice` | formant movement, pitch-loudness coupling (8) | Praat formants and intensity |
| `rhythm` | syllable timing, loudness dynamics, modulation shape (11) | band-passed envelope, peak picking |

`LLR = b + sum_i w_i * t_i`: `t_i` is the raw score for the two neural models and the clipped (±3) logit of a small
gradient-boosted model for each feature analyzer. Weights come from a class-balanced logistic regression, so the
LLR is prior-free, and each analyzer's contribution to a clip is exactly `w_i * t_i` (shown in the app's report).

## Fitting a release
Reported fusion numbers are out-of-fold with nested cross-fitting (`fit_fusion.py`): the per-analyzer models that
feed the fusion are refit inside each outer training fold, so no outer-test label reaches them. The earlier
single-level scheme let those labels in indirectly; re-running with nesting changed the headline numbers by at most
0.003 (v4p6: ffmpeg 0.007 -> 0.006, librosa 0.088 -> 0.089). The per-feature ablation tables below used the
single-level scheme.

```sh
python ml/fit_fusion.py --v3-scores data/checkpoints/v3_diffssd/val_scores_ep2.npz \
  --lfcc-scores results/lfcc_val_scores.npz --prosody results/pitch_v3val.csv --feats results/feats3_v3val.csv \
  --checkpoint data/checkpoints/v3_diffssd/best.pt --lfcc-checkpoint scratch/lfcc_eval/lfcc1_best.pt \
  --backbone-config data/release/v2e/backbone_config --out data/release/v3p6_ep2 --name v3p6-ep2
MODEL_DIR=data/release/v3p6_ep2 python ml/check_clips.py data/teammates     # evaluation only
```
Validation data: `data/splits/v3_val.csv` (4,523 DiffSSD validation clips: LJ Speech + LibriSpeech real, 7 generators),
each in three versions: clean, ffmpeg `atempo` stretch + noise (a stretch method no model trained on), and librosa
phase-vocoder stretch + noise. The versions of a clip always share a cross-validation fold.

## Results (out-of-fold; minDCF at P(synthetic)=0.3 with a false alarm costing 4x a miss; lower is better)
v3 epoch-2 checkpoint (its selection-best), LFCC run 1 best, run 2026-09-26 ~04:00 ET:

| system | clean | ffmpeg stretch | librosa stretch |
|---|---|---|---|
| v3 alone | 0.010 | 0.032 | 0.392 |
| v3 + prosody + LFCC | 0.000 | 0.010 | 0.181 |
| **all 6 (shipped)** | **0.000** | **0.008** | **0.085** |

Plain language, librosa stretch, at the cost-optimal threshold (v3 epoch 3, seed 0; `scratch/features/success_rates.py`):
v3 alone catches 70.7% of fakes with 0.7% of real clips flagged; the four interpretable analyzers alone (no neural
model) 78.6% / 1.0%; all six fused 94.7% / 0.3%.

### How each feature group earned its place (`feature_ablation.py`, `feature_tweak.py`)
Base = v3 + prosody + LFCC. Each group was added as one more additive term; mean of 3 CV seeds. A control of six
random-noise features moved minDCF by at most 0.001 (0.003 within the LJ voice), so larger changes are signal.
"LJ" = LJ Speech reals vs same-voice fakes (GradTTS, ProDiff, WaveGrad2), the hard case if the test reals are all LJ.

| added to base | clean | ffmpeg | ffmpeg LJ | librosa | librosa LJ |
|---|---|---|---|---|---|
| (base) | 0.0005 | 0.014 | 0.020 | 0.177 | 0.226 |
| spectral | 0.0000 | 0.005 | 0.011 | 0.092 | 0.174 |
| spectral without > 5.5 kHz features | 0.004 | 0.007 | 0.013 | 0.123 | 0.231 |
| voice, all 14 features | 0.005 | 0.013 | 0.025 | 0.108 | 0.202 |
| voice, formant movement + coupling (8, shipped) | 0.004 | 0.012 | 0.017 | 0.136 | 0.211 |
| rhythm | 0.0006 | 0.014 | 0.021 | 0.165 | 0.210 |
| rhythm inside the prosody model instead | 0.0006 | 0.016 | 0.025 | 0.180 | 0.239 |
| spectral + voice (8) + rhythm | 0.0000 | 0.005 | 0.010 | 0.082 | 0.159 |

Dropped: spectral flatness (overall and 4-8 kHz) and formant bandwidth B2. They differ between NSA's real clips
(`LJRealResampled`, resampled by NSA with ffmpeg) and our copies of the same clips (resampled with soxr) by 0.56, 1.76
and 0.37 standard deviations, so they partly measure the resampler rather than the voice.

### Safety check on NSA's real clips (`nsa_safety.py`)
All 242 clips in NSA's `LJRealResampled.zip` scored through each fused system (fit on DiffSSD validation only):
they land where our validation LJ reals do (all 6: median LLR -16.7 vs -16.6), none is above the cost-optimal
threshold, and none is above the lowest 1% of same-voice fakes. The > 5.5 kHz spectral features therefore stay.

## v4 (2026-09-26 morning): new generators, warm start from v3
v4 = v3's best checkpoint trained ~3 h more with 111 ElevenLabs stock-voice clips (Flash v2.5, Turbo v2.5,
Multilingual v2) and 736 Kokoro clips added as 10% of the fake sampling mass (`scratch/train/train_v4.py`).
Best checkpoint = its first epoch (DiffSSD val selection 0.0203 vs v3 0.0208). On data neither model trained on
(caught = share of fakes above the 1% false-alarm threshold on DiffSSD validation reals):

| test set | clean: v3 -> v4 | ffmpeg stretch + noise: v3 -> v4 |
|---|---|---|
| ElevenLabs eleven_v3 (55, frontier model) | 100% -> 100% | 89% -> 100% |
| ElevenLabs multilingual_v2 (27) | 100% -> 100% | 37% -> 85% |
| held-out ElevenLabs stock voices (28) | 100% -> 100% | 75% -> 100% |
| held-out Kokoro voices (70) | 100% -> 100% | 93% -> 97% |
| teammates' consented clones (20) | 30% -> 65% | 10% -> 35% |
| teammates' real recordings flagged (20) | 0% -> 0% | 0% -> 0% |

Release `v4p6` (v4 + the same five other analyzers) fused on validation: clean 0.000, ffmpeg 0.006, librosa 0.089
(nested cross-fitting, see below; 0.007 / 0.088 with the earlier single-level scheme).
NSA's 242 real LJ clips: median LLR -18.4, max -8.8, none above 0. Teammate AUC: `nsa` profile 0.948, `app` 1.000.

DiffSSD official test split (41,113 clips, clean, v3, scored once): minDCF 0.0068; the three generators absent from
training (DiffGAN-TTS, PlayHT, UnitSpeech) 0.0016 / 0.0020 / 0.0012.

## Two fusion profiles: DiffSSD-like audio vs unfamiliar voices
The six-analyzer fusion is the best system on DiffSSD-style audio (the NSA task), but it transferred worse to the
teammate check (20 real laptop-mic recordings + 20 consented ElevenLabs clones of the same two people; evaluation
only, and it already influenced an earlier design choice, so treat it as a warning, not a measurement):

| on the teammate clips | AUC |
|---|---|
| v3 alone | 1.000 (epoch 2) |
| v3 + prosody | 0.980 (epoch 1) |
| all 6 | 0.935 |
| each term alone: LFCC / prosody / rhythm / spectral / voice | 0.885 / 0.741 / 0.700 / 0.625 / 0.486 |

The spectral and voice features learned cues specific to DiffSSD's recordings and generators; on a new mic and new
voices they add noise. So a release carries two fusions:
- `nsa` (all six): `python -m hearsay predict` uses it for the TSV.
- `app` (neural detector + prosody): the server uses it (`FUSION_PROFILE=app`, the default).

## Known gap: calibration on new voices
With either profile, all 20 real teammate clips are "likely real", but most clones are too (all 6: 17 of 20; 2
inconclusive, 1 likely synthetic). The ranking is mostly right; the absolute scores sit below the validation decision
boundary. The NSA TSV needs only the ranking; the app's verdicts need training data from new voices and recording
setups.
