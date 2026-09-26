# NSA HEARSAY: what we know and what we don't

Source: the challenge brief "HEARSAY: The Audio Authentication Challenge"
(PDF, received Fri 7:58 PM). Everything under "Known" comes from that brief
unless it says otherwise.

## Known

### Task
- Take any audio file as input: WAV, MP3, M4A, MP4 audio, OGG, and others.
- Output a synthetic probability from **0.0 to 1.0**, where 1.0 means synthetic.
- The system should automatically run several forensic analyses on the audio,
  spectrograms, signal, and file metadata.
- Clips are **at least 2 s long and in English**.
- Real clips may have noise and other perturbations added, so we need low false
  alarms on degraded real audio.
- Results must be explainable: which techniques flagged a clip, and **what
  worked and what had no effect** (we need an ablation table).
- We're free to use cloud services, open-source LLMs, speech models,
  signal-processing toolkits, and open-source or commercial tools.
- **Pre-trained models are allowed** (NSA mentor told Akash, Fri ~8:00 PM).
- Recording our own audio is explicitly allowed. NSA also hinted that ElevenLabs
  is fair to use.

### Data
- **Labeled training set**: synthetic (`spoof`) vs real (`bonafide`).
- **Sample test set**: labels are held back and used to score us.
- The data may include:
  - real speech: studio, smartphone, telephony, and field recordings, across
    codecs and bitrates
  - fully synthetic speech: zero-shot TTS and neural vocoders
  - voice conversion: a real source speaker converted to a cloned target voice
  - replay attacks: a recording of a playback
  - scene manipulation: a real voice with a fabricated or replaced background
  - laundered fakes: synthetic speech passed through transcoding,
    band-limiting, or noise
  - metadata-spoofed containers
- NSA will do a **one-time review of one draft TSV** per team. It's optional.
  Use it after the fusion model exists, with enough time left to fix gaps.

### Scoring
1. **Detection performance: 60%.** Scored on the cm-score from the sample test set.
2. **Forensic diversity: 20%.** Points for each distinct technique the system
   *actually uses*:
   - container, file and metadata forensics: encoder tags, timestamps, codec
     chain, MAC times
   - spectral and frequency-domain analysis: band-limiting, vocoder harmonics
   - prosody and phonetics: breath, pauses, coarticulation, pitch-contour
     naturalness, monotony, emotion
   - acoustic-environment consistency: ENF (mains hum)
   - compression forensics: double encoding, transcoding artifacts
   - speaker-embedding consistency: does the voice drift across the clip?
   - deep-learning anti-spoofing detectors
   - splice and discontinuity detection: phase breaks, DC offset, background seams
   - **Agentic orchestration bonus:** the system chooses which analyses to run
     based on file type, codec, early findings, or confidence, instead of
     running everything.
3. **Documentation and presentation: 20%.** How clearly we explain the
   approach, and whether the system can explain *why* a clip is synthetic or real.

### Required submissions
1. A **GitHub repo** with a README covering the approach, the
   architecture/design, and how to run it.
2. A **Docker image** that runs inference on the provided test set without
   major configuration changes.
3. A **TSV** generated from the sample test set, with a header row and exactly
   these columns:
   ```
   filename	cm-score
   file1.wav	0.80
   ```
   `filename` includes the extension. `cm-score` is a float from 0.0 to 1.0.
   The file is named `<teamName>_predictions.tsv`.

## Unknown (ask the NSA mentors at the booth or on Discord, then move the answer to Known with who said it and when)
- [ ] **How is detection performance calculated?** EER, AUC or minDCF (ranking
  only) vs log loss, Brier or accuracy at 0.5 (calibration matters)? This
  decides v2 vs v2e and how much calibration work to do.
- [ ] **How are scene-manipulated, metadata-spoofed and replayed clips labeled:
  `spoof` or `bonafide`?** A real voice with a fake background, or real audio
  in a spoofed container, won't look fake to a speech detector.
- [ ] How large is the training set, and does it cover the same categories and
  sources as the test set?
- [ ] Do the files keep their original metadata and MAC times, or did
  packaging reset them? Are those timestamps a legitimate signal?
- [ ] How will judges run the Docker image: GPU or CPU, with or without
  internet? How big is the test set, and is there a time limit?
- [ ] When is the one-time review available, and what's the final submission deadline?
- [ ] How do they verify that a technique is "actually leveraged"? Is an
  ablation table enough?

## Our results on NSA data
(Record the exact data, sample count and command for each result.)
