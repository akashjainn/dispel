# Architecture: how a clip is scored, and how the model was trained

Two halves meet at one folder: the **release** (`hearsay.json` plus weights). Training produces it on the team PC,
and everything that scores audio loads it: the NSA TSV (`python -m hearsay predict`), the Vultr server (`server/`)
and the Docker image. All three use the same `hearsay/` code, so the app scores a clip exactly as the submission did.

## 1. Scoring one voice clip (release v5c, profile `nn`)

```mermaid
flowchart TD
    A["Voice clip<br/>wav, mp3, m4a, flac, ogg, webm; any sample rate"] --> B["Decode to mono 16 kHz<br/>hearsay/audio.py"]
    B --> C["Up to 3 non-overlapping 4 s windows<br/>(first 12 s; clips under 4 s are tile-repeated)"]

    subgraph NN["Neural detector: hearsay/analyzers/dl_detector.py"]
        C --> D["wav2vec 2.0 XLS-R 300M<br/>24 transformer layers, fine-tuned end to end"]
        D --> E["Learned softmax weighting<br/>of all 25 hidden states"]
        E --> F["Mean + std pooling over time"]
        F --> G["MLP head 2048 → 256 → 2"]
        G --> H["Window score<br/>logit(synthetic) − logit(real)"]
    end

    H --> I["Clip score s = mean of window scores<br/>(this alone sets the ranking)"]
    I --> J["Calibrated log-likelihood ratio<br/>LLR = 0.696 · s − 2.035<br/>(Platt fit on DiffSSD validation scores)"]
    J --> K["NSA TSV: sigmoid(LLR / 10)<br/>0.0 = real, 1.0 = synthetic"]
    J --> L["App: probability = sigmoid(LLR + prior log-odds)<br/>verdict: ≥ 0.75 likely synthetic, ≤ 0.25 likely real,<br/>otherwise inconclusive"]

    B --> M["Evidence analyzers, weight 0<br/>prosody · spectral · voice quality · rhythm"]
    M --> N["App report<br/>score, per-window scores,<br/>evidence findings"]
    L --> N
    H --> N
```

What each part is for:

| Step | Why it is there |
|---|---|
| 16 kHz mono decode | XLS-R was pretrained on 16 kHz audio, and NSA's test set is 16 kHz. |
| 4 s windows, up to 3 | Training crops were 4 s. Averaging three windows steadies the score, and the app shows each window's score so a spliced clip stands out. |
| Weighted mix of all layers | The top layer is tuned for speech content, not recording artifacts. A learned weight per layer lets the head use whichever layers separate real from synthetic. |
| Mean + std pooling | The std term captures how the frames vary over time, not just their average. |
| One network, no fusion | In the interim release, hand-built feature models outvoted the network on ElevenLabs clones. Now they only explain the verdict (see [DECISIONS.md](DECISIONS.md), Sat 18:40). |
| `sigmoid(LLR / 10)` for the TSV | minDCF depends only on the ranking. The gentle squash keeps every clip distinct: no ties at 0 or 1. We score in full precision (`HEARSAY_FP32=1`) so that bf16 rounding creates no ties either. |

## 2. How the model was trained

Each generation warm-starts from the previous best checkpoint and adds the data the previous one failed on.

```mermaid
flowchart LR
    P["XLS-R 300M<br/>self-supervised pretraining<br/>(Meta, 128 languages)"] --> V2["v2<br/>In-the-Wild, ASVspoof 5,<br/>MLAAD, M-AILABS, VoxPopuli"]
    V2 --> V3["v3<br/>+ DiffSSD train split<br/>(diffusion TTS and voice cloning)<br/>+ stretch, noise, codec augmentation"]
    V3 --> V4["v4 (interim submission)<br/>+ ElevenLabs stock voices, Kokoro"]
    V4 --> V5C["v5c (final)<br/>diverse reals, 18 commercial TTS,<br/>ElevenLabs clone matrix, new MLAAD"]
    V4 -.-> V5B["v5, v5b<br/>experiments, not shipped"]
```

### The v5c training run (`ml/analysis/train/train_v5c.py`)

```mermaid
flowchart TD
    subgraph REAL["Real speech (sampling share within the real class)"]
        R1["DiffSSD reals: LJ Speech + LibriSpeech · 40%"]
        R2["TalkingFace YouTube vloggers · 6%"]
        R3["Unsupervised People's Speech, English only<br/>(Whisper language ID + ASR check) · 5%"]
        R4["ElevenLabs Voice Isolator-cleaned reals · 5%"]
        R5["VCTK · YouTube · consenting teammates · 3% each"]
        R6["v2 mix: In-the-Wild, ASVspoof 5, ... · 35%"]
    end
    subgraph FAKE["Synthetic speech (sampling share within the fake class)"]
        F1["DiffSSD fakes, incl. 80% of its test split · 35%"]
        F2["ElevenLabs: TTS models, instant clones of consenting<br/>teammates, voice changer, voice design · 15%"]
        F3["Commercial TTS: 18 API systems from MLAAD (OpenAI, Gemini,<br/>Cartesia, MiniMax, ...) + Grok, Polly, Speechify, Hume · 12%"]
        F4["new MLAAD systems · DFADD · 3% each"]
        F5["F5-TTS clones · Kokoro · 2% each"]
        F6["v2 mix · 28%"]
    end
    REAL --> S["Balanced sampler<br/>50/50 real vs synthetic; inside each source every<br/>generator or speaker group gets capped, equal mass"]
    FAKE --> S
    S --> AUG["Augmentation, identical for both classes<br/>trim + pad silence · stretch 0.85-1.15x (p 0.7)<br/>noise 5-35 dB SNR (p 0.7) · gain · mp3/aac/opus/mu-law (p 0.3)<br/>random 4 s crop"]
    AUG --> T["Fine-tune from v4 best<br/>AdamW, lr 1e-6 backbone / 1e-4 head, cosine, 3% warm-up<br/>CNN feature encoder frozen · batch 16 · 3 × 36,000 clips · 2.2 h"]
    T --> CK["Checkpoint after each epoch<br/>DiffSSD validation: clean, ffmpeg atempo (unseen stretch), phase vocoder"]
```

Held out from training entirely, so they give honest numbers: 4 MLAAD systems (Higgs-Audio-V3, Index-TTS-2.0,
Step-Audio-EditX, supertonic-3), 6 Grok voices, a speaker-disjoint set of teammates (real voices and their clones),
20% of DiffSSD's test split, and a slice of every other source. Epoch 3 was checked on DiffSSD validation only
(slightly worse), so it was not a candidate.

### Choosing the checkpoint and shipping it

```mermaid
flowchart LR
    CK["Candidates<br/>v4 · v5c epochs 1-2 ·<br/>AntiDeepfake 1B / MMS-300M ·<br/>ensembles"] --> E1["Held-out minDCF<br/>each fake family vs VCTK reals<br/>(NSA's reals look like VCTK)"]
    CK --> E2["Pooled: all held-out fakes<br/>vs all held-out reals"]
    CK --> E3["Sanity check with no labels:<br/>2-Gaussian fit to NSA test scores<br/>should give about 30% synthetic"]
    E1 --> SEL["v5c, first epoch"]
    E2 --> SEL
    E3 --> SEL
    SEL --> REL["ml/make_release_nn.py<br/>Platt calibration, sha256 of every file,<br/>profile_override: nn"]
    REL --> TSV["NSA TSV<br/>HearsayScoreKey4Gemini.tsv"]
    REL --> VOL["Vultr models volume<br/>/opt/dispel/models"]
    VOL --> API["server/ /analyze → desktop app"]
```

NSA's test labels were never available to us, and the test audio was never used for training or uploaded to
any third party. The mixture check reads only the shape of our own score distribution.

## Held-out results for the shipped network

minDCF with P(synthetic) = 0.3 and a false alarm costing 4x a miss (the challenge metric; lower is better).

| Test set (never trained on) | v4 (interim) | v5c (final) |
|---|---|---|
| All held-out fakes (3,546) vs all held-out reals (1,364): AUC | 0.9934 | **0.9966** |
| same: EER | 4.03% | **2.86%** |
| same: minDCF | 0.191 | **0.157** |
| ElevenLabs, mixed methods, vs VCTK reals | 0.237 | **0.087** |
| Consenting teammates' instant clones vs VCTK reals | 0.480 | **0.180** |
| 4 MLAAD systems never seen | 0.007 | **0.000** |
| New clips we generated from the Gemini (13) and Inworld (61) APIs after training* | n/a | **0.000** |
| Teammates' real recordings flagged at VCTK's 1% false-alarm threshold | n/a | **0** |
| Isolator-cleaned real speech flagged at the same threshold | 41% | 47% |

\* The clips are new, but both systems appear in MLAAD's commercial set, which v5c trained on. This row shows that
the network generalizes to new sentences and voices, not to new systems; the 4 unseen MLAAD systems test that.

The last row is the known weakness: speech run through a noise remover looks synthetic to every model we tried
(see Limitations in the [README](../README.md)).
