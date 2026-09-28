# Benchmark: In-the-Wild (held-out speakers)

In-the-Wild ([Müller et al., 2022](https://arxiv.org/abs/2203.16263)) is the standard real-world audio deepfake
benchmark: genuine and deepfaked speech of 58 public figures collected from the web. We scored the **16 speakers that
none of our models ever trained on** (our training scripts assert this; `ml/analysis/eval/bench_itw.py` checks it
again): 6,567 clips, 2,466 of them synthetic. Run on Mon 28 Sep 2026 on the team PC (RTX 3060).

## Models compared

| Model | Size | Training data | Scoring protocol |
|---|---|---|---|
| **v5c** (ours, shipped) | XLS-R 300M | our mix (see [ARCHITECTURE.md](../ARCHITECTURE.md)); includes 32 *other* In-the-Wild speakers | up to 3 x 4 s windows, mean |
| AntiDeepfake XLS-R-1B (NII, [arXiv:2506.21090](https://arxiv.org/abs/2506.21090)) | 1B | about 74k hours; In-the-Wild is not in it (its model card lists it as a permitted evaluation set) | whole clip (authors' protocol), and our windows |
| AntiDeepfake MMS-300M (NII) | 300M | same as above | whole clip |
| mo-thecreator/Deepfake-audio-detection | wav2vec2-base, 95M | not documented | our windows (as our server ran it) |

Scores are log-odds of "synthetic". Metrics: AUC, EER and the challenge minDCF (P(synthetic) 0.3, false alarm costs
4x a miss). 95% confidence intervals come from a speaker-level bootstrap: the 16 speakers are resampled 2,000 times, so
an interval reflects how much the result depends on which voices are in the test. Every number below was recomputed
with independent code before publishing.

## Results

In-the-Wild, 16 held-out speakers: 6,567 clips (2,466 synthetic). 95% CIs: speaker-level bootstrap.

| Model | AUC | EER | minDCF (P 0.3, FA 4x) |
|---|---|---|---|
| v5c (ours, shipped) | 0.9997 (0.999-1.000) | 0.50% (0.2-1.0) | 0.020 (0.004-0.044) |
| AntiDeepfake XLS-R-1B (authors' whole-clip protocol) | 0.9997 (1.000-1.000) | 0.67% (0.5-0.9) | 0.029 (0.014-0.040) |
| AntiDeepfake XLS-R-1B (our 3 x 4 s windows) | 0.9945 (0.989-0.998) | 3.08% (2.0-4.5) | 0.081 (0.056-0.111) |
| AntiDeepfake MMS-300M (whole clip) | 0.9977 (0.996-0.999) | 2.23% (1.2-3.0) | 0.107 (0.064-0.150) |
| mo-thecreator wav2vec2-base (stock, server stand-in) | 0.9172 (0.814-0.982) | 14.63% (5.5-25.8) | 0.814 (0.197-1.000) |

Paired difference, model minus v5c (95% CI; an interval that excludes 0 is a real difference):

| Model | AUC | EER (points) | minDCF |
|---|---|---|---|
| AntiDeepfake XLS-R-1B (authors' whole-clip protocol) | -0.000 to +0.001 | -0.4 to +0.6 | -0.021 to +0.031 |
| AntiDeepfake XLS-R-1B (our 3 x 4 s windows) | -0.011 to -0.002 | +1.5 to +3.9 | +0.029 to +0.095 |
| AntiDeepfake MMS-300M (whole clip) | -0.004 to -0.000 | +0.5 to +2.6 | +0.032 to +0.135 |
| mo-thecreator wav2vec2-base (stock, server stand-in) | -0.186 to -0.018 | +4.9 to +25.2 | +0.177 to +0.992 |

Per speaker, EER (speakers with at least 10 real and 10 synthetic clips):

| Speaker | real | synthetic | v5c | ad1b | ad1b_win | admms | stock |
|---|---|---|---|---|---|---|---|
| Arnold Schwarzenegger | 243 | 108 | 0.0% | 0.0% | 0.4% | 0.0% | 8.9% |
| Bob Ross | 60 | 48 | 0.0% | 0.0% | 4.6% | 0.0% | 5.6% |
| Boris Johnson | 209 | 86 | 0.0% | 0.0% | 0.6% | 0.0% | 0.0% |
| Calvin Coolidge | 58 | 15 | 0.0% | 0.0% | 0.0% | 0.9% | 0.0% |
| Christopher Hitchens | 798 | 541 | 0.0% | 0.8% | 1.6% | 1.1% | 2.0% |
| FDR | 308 | 163 | 0.9% | 0.3% | 4.4% | 3.6% | 31.7% |
| Frank Sinatra | 17 | 38 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| George Carlin | 164 | 84 | 0.0% | 0.0% | 0.6% | 0.6% | 0.9% |
| George W. Bush | 55 | 175 | 0.0% | 0.0% | 7.9% | 0.0% | 6.2% |
| JFK | 396 | 273 | 0.0% | 0.7% | 5.4% | 4.5% | 45.7% |
| Louis Farrakhan | 302 | 108 | 0.0% | 0.5% | 0.8% | 2.1% | 0.2% |
| Mark Zuckerberg | 321 | 261 | 0.0% | 0.2% | 0.7% | 0.5% | 6.5% |
| Martin Luther King | 516 | 283 | 0.8% | 1.1% | 3.1% | 1.4% | 33.2% |
| Winston Churchill | 625 | 257 | 0.0% | 0.7% | 3.2% | 2.1% | 0.9% |

## How to read this

- **v5c matches AntiDeepfake-1B**, a research model about 3x its size trained on far more data: EER 0.50% vs 0.67%,
  minDCF 0.020 vs 0.029. The paired intervals include zero, so this is a tie, not a win.
- **It is not a clean tie in our favor.** v5c trained on 32 other In-the-Wild speakers, so it knows this benchmark's
  recording style; AntiDeepfake never saw the dataset. The fair summary is "on par with a much larger model, with some
  home advantage".
- **v5c clearly beats the same-size AntiDeepfake MMS-300M** (EER +0.5 to +2.6 points worse for MMS; interval excludes
  zero) and **the stock download our server used before v5c**: EER 14.6% to 0.5%, minDCF 0.81 to 0.02. The stock model
  is also a smaller backbone with undocumented training data, so that gap reflects both factors, not fine-tuning alone.
- **Protocol matters.** AntiDeepfake-1B scored on our 3 x 4 s windows drops from 0.67% to 3.08% EER, because it was
  trained on whole clips. Each model is therefore compared on its own protocol above.
- Per speaker, v5c's largest errors are on FDR and Martin Luther King (0.8-0.9% EER): old, degraded archival
  recordings, which are also among the hardest speakers for the other models.

## Reproduce

```bash
python ml/analysis/eval/bench_itw.py v5c stock ad1b admms ad1b_win   # writes results/bench_itw/<model>.csv
python ml/analysis/eval/bench_itw_metrics.py                         # writes metrics.md / metrics.json
```
Paths assume the team PC's `~/hackgt` layout (data in `data/release_in_the_wild`, speaker lists in `data/splits`).
AntiDeepfake weights are CC BY-NC-SA 4.0 and loaded without fairseq by `ml/analysis/eval/antideepfake.py`.
