# NSA HEARSAY: what we know and what we don't

Sources:
- **[I]** the official instructions, `HEARSAY_HackGT2026_Instructions.pdf` (NSA Google Drive folder, read Fri 9:03 PM)
- **[B]** the challenge brief PDF, "HEARSAY: The Audio Authentication Challenge"
- **[T]** the NSA kickoff talk and slides, Fri ~8:00–9:00 PM (notes by Akash)
- **[D]** the HEARSAY challenge post in the HexLabs Discord (pasted by David, Sat)

If [I] conflicts with [B], [T] or [D], trust [I].

**Correction to [T]:** the slides say the data is "~50% real, ~50% synthetic". That is wrong; it is **about 70% real, 30% synthetic** (see Test set below).

## Known

### Scoring (the 60%): minDCF
- **Metric:** the minimum Detection Cost Function (minDCF) from ASVspoof 5 Track 1. Lower is better: 0.0 is best, 1.0 is worst. [I][T]
- **Cost weights:** flagging a **real clip as synthetic costs 4×** what a missed synthetic clip costs. This is the "analyst scenario", where every false alarm wastes an analyst's time. [I][T]
- **Only ranking matters.** minDCF tries every threshold and keeps the best one, so calibration doesn't affect this score; the order of our scores does. [T: "(Minimized)"]
- **Points:** yours = (1 − your minDCF) / (1 − best minDCF) × 60. The best team gets 60. [I]
- Slide formula [T]:
  `DCF = C_miss·(1 − P(attack))·P(miss) + C_fa·P(attack)·P(false alarm)`.
  ASVspoof's own code reads this with **real** as the positive class, so "miss" = a real clip rejected. See the questions under Unknown.

### The rest of the 40%
- **20%:** creativity, quality, innovation and depth. [I] The brief's list of forensic techniques and its "agentic orchestration" bonus are still the best guide to what earns these points. [B]
- **20%:** documentation in the GitHub repo. Judges want to know **exactly what we did**. [I][T]

### Test set and answer key
- 1,671 `.wav` files at **16 kHz**, English, each **more than 3 s** long. **About 70% are real.** [I]
- NSA supplies a TSV answer key that we fill in:
  - every row is pre-filled with the placeholder **0.006** (it means "not done yet", nothing more)
  - **never remove rows**
  - rename the file with our team name
  - column 2 is the score: 0.0 = confidently real, 1.0 = confidently synthetic [I]
- Clips have varying noise and **moderate time-stretching or squeezing**. **A clip's label is where it started:** a real clip with noise added is still real. [T]
- No partial fakes. We don't need to identify augmentations or manipulation types. [T]
- **Files we can't score:** NSA says to choose their default score strategically. Since flagging a real clip is expensive, place an uncertain file at the **"real" end** of the ranking. [I, and our reasoning]

### Training data
- **DiffSSD** (Purdue), given as `DiffSSD.zip`, 18.1 GB. [I] From the paper (arXiv 2409.13049):
  - 5 zero-shot cloning generators: **ElevenLabs**, OpenVoice2, XTTSv2, YourTTS, **PlayHT**
  - 5 generators trained on LJ Speech: GradTTS, ProDiff, WaveGrad2, DiffGAN-TTS, UnitSpeech
  - real speech: LJ Speech (13,100 clips) and LibriSpeech (11,126), 74 speakers
  - official split: real 40/10/50 for train/val/test. **DiffGAN-TTS, PlayHT and UnitSpeech appear only in test.**
  - sample rates range from 16 to 44.1 kHz, so **resample everything to 16 kHz** before training (the test set is all 16 kHz)
- **LJ Speech** is also provided. The HexLabs paths will be posted in Discord. [I]
- **Other datasets we're permitted to use are allowed**, including Hugging Face. [I] **Pre-trained models are allowed.** [T]

### Required submissions [B]
1. A GitHub repo with a README covering the approach, the architecture and how to run it.
2. A Docker image that runs inference on the test set.
3. The completed TSV answer key.

## Unknown (ask in the Discord HEARSAY channel, then move the answer to Known with the date)
- [ ] **Score direction:** does the scorer treat a **higher cm-score as synthetic**? ASVspoof's code assumes higher = real. If it's flipped, our score is close to the worst possible.
- [ ] **Which error the 4× penalty applies to in the code:** confirm that `C = 4` is on real clips flagged as synthetic.
- [ ] The **P(attack)** value in the scorer: 0.3 (the data's mix) or ASVspoof's default 0.05?
- [ ] Can we have the **exact scoring script**?
- [ ] Is the test set drawn from DiffSSD's test portion? Is **matching test files to DiffSSD clips** (fingerprinting) allowed, or does it count as cheating? **Don't do it until NSA answers.**
- [ ] How much stretching and what kind (tempo only, or speed change that also shifts pitch)? What noise SNR range? Are real and synthetic clips processed the same way?
- [ ] The one-time review of a draft TSV: when, how to submit, and what feedback comes back?
- [ ] Docker: GPU or CPU, internet access, time limit?
- [ ] Final deadline, and the HexLabs submission format.
- [ ] [D] conflicts with [I]: it asks for a **CSV** with a **0–100%** score and optionally the **type of manipulation**. [I] says TSV, 0.0–1.0, no manipulation type. Until NSA confirms, follow [I]; a manipulation type (if we ever add one) stays "unknown" unless we're confident.

## Our results on NSA-like data
(Record the exact data, sample count and command for each result.)
