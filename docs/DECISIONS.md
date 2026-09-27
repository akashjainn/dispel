# DECISIONS (append only, dated; newest at the bottom)

- **Fri 20:00. Product:** an Electron desktop app with a wizard sprite as the
  front door and an evidence report behind it. Capture only happens when the
  user asks. Inference runs locally.
- **Fri 20:00. Model:** v2e (the v0 + v2 XLS-R ensemble) is the default. v2
  alone may be used for the NSA TSV if the metric only rewards ranking (AUC or
  EER); that choice will be made on NSA data, not on our own test sets.
  - Release hashes: v0 `best.pt` df51d252…, v2 `best.pt` 223d3c05…
  - v2e is defined by `ensemble.json`. The full hashes are in the PC's
    `data/release/*/SHA256SUMS`.
- **Fri 20:00. Weights stay out of git.** Code loads them through `MODEL_DIR`.
  The model is non-commercial (MLAAD is CC BY-NC).
- **Fri 20:00. ElevenLabs:** we generate voices only from consenting teammates
  and stock library voices. We never clone public figures, including for the
  demo. All generated data is disclosed.
- **Sat 02:25. Call watch (proposed by David, needs Akash's OK):** the app
  starts watching automatically when a call app (Zoom, FaceTime, Teams, Discord,
  Slack, or a browser) is using the microphone. It finds out by asking macOS
  which process is running audio input, and never opens the mic itself. The
  wizard shows a gray "watching" state so the user can see it. It can be turned
  off from the tray ("Watch calls"). Right now no audio is captured and call
  results are mocks. Capturing call audio will change the "only when the user
  asks" rule, so it needs its own decision (in-memory buffer, never saved).
- **Sat. Hosting (supersedes the "inference runs locally" line above):** the API
  and inference run on a Vultr instance provisioned by Terraform (`infra/vultr/`).
  Audio is uploaded to it only on a user action. The server keeps no audio.
  Deployed access is HTTPS (Caddy) plus a bearer API key. `main` stays free of
  keys; weights are rsynced to the instance, never committed. (israel/backend-infra-setup)
- **Sat. Deploys:** merges to `main` that touch `server/` or `docker/` deploy over SSH from GitHub
  Actions. The runner opens a temporary firewall rule for its own IP, logs in as `deploy` (its key
  can only run `/opt/dispel/deploy.sh`), then closes the rule. Adding this replaced the server once
  (new IP, so a new sslip.io URL). `/` serves a "Team Gemini" landing page.
- **Sat 02:50. Model (supersedes v2e as default):** release `v3p` = v3 (XLS-R 300M fine-tuned on DiffSSD
  with noise and time-stretch augmentation) fused with prosody features additively
  (LLR = w * v3 + w' * q + b, q = clipped logit of a prosody-only GBM), which keeps v3's ranking intact on
  unfamiliar audio. Fit on DiffSSD validation only (`ml/fit_fusion.py`); numbers in
  `ml/README.md`. v2e is retired: v2 flagged about 90% of real LJ Speech clips as synthetic.
  The server, the NSA TSV (`python -m hearsay predict`) and the Docker image all use the same `hearsay/` code.
- **Sat 02:50. Verdict band:** placeholder 0.25 / 0.75 on the posterior stays until calibration on
  new voices is fixed (teammate check: 18 of 20 consented ElevenLabs clones scored "likely real", although the ranking was right, AUC 0.98).
- **Sat. Repo-driven server:** the Vultr server's first-boot script is a fixed bootstrap; deploy logic and the container stack
  live in the repo (`docker/remote-deploy.sh`, `docker/compose.prod.yml`) and ship on merge. Model weights sit on a separate
  NVMe block-storage volume (`/opt/dispel/models`, 10 GB) that survives server replacement. `ignore_changes = [user_data]`, a
  `replace_server` gate in the infra workflow and `prevent_destroy` on the volume stop accidental wipes. (israel/repo-driven-server)
- **Sat. App ↔ server link and anonymous install id (proposed by Israel, needs David's and Akash's OK):** the app sends
  file checks to the configured server (Vultr) instead of its local mock; call checks stay local mocks until audio
  capture exists. There is no registration: on first launch the app makes a random UUID (`<userData>/client-id`) and sends
  it as `X-Dispel-Client`. The server records one row per check in SQLite (`/opt/dispel/data`, survives redeploys but not a
  server replacement) with result metadata only: never audio, file names or transcripts. `GET /history` returns an
  install's own rows. The id groups checks; it is not authentication. The app's bearer key ships inside the app, so treat
  it as a speed bump, not a secret. (israel/app-server-link)
- **Sat 04:10. Release v3p6 (supersedes v3p):** six analyzers fused additively: v3, LFCC-LCNN, prosody, spectral,
  voice (formant movement + pitch-loudness coupling), rhythm. Out-of-fold minDCF on DiffSSD val: clean 0.000,
  ffmpeg stretch 0.008, librosa stretch 0.085 (v3 alone 0.010 / 0.032 / 0.392). Spectral flatness and formant
  bandwidth B2 are excluded because they differ between NSA's ffmpeg-resampled real clips and ours. All 242 NSA
  LJRealResampled clips score like our validation reals (none near the threshold).
- **Sat 04:10. Two fusion profiles:** `nsa` (all six) for the TSV; `app` (v3 + prosody) for the server, because on
  the teammate check the six-way fusion ranked worse: AUC 0.935 vs 0.992 for the `app` profile, both refit on the v3
  epoch-2 checkpoint (the earlier 0.98 above is v3p on the epoch-1 checkpoint). Details in ml/README.md.
- **Sat 09:10. Release v4p6 (supersedes v3p6):** v4 (v3 + ElevenLabs stock voices and Kokoro, 3 h warm start) replaces
  v3 as the neural detector. Same on DiffSSD validation; clearly better on generators and voices it never trained on
  (ffmpeg-stretched frontier ElevenLabs 89% -> 100% caught, teammate clones 10% -> 35%, no new false alarms). Table in ml/README.md.
- **Sat 16:10. Interim submission:** `HearsayScoreKey4Gemini.tsv` from release v4p6 (profile `nsa`), sha256
  05adaf1e…. NSA rating: **minDCF 0.258, EER 10.2%** (instructions' metric: 0 = real, 1 = synthetic, P(synthetic) 0.3,
  false alarm on a real clip costs 4x). Leaderboard of interims: 0.058, 0.075, 0.258 (us), 0.267. NSA keeps the better
  of interim and final.
- **Sat 16:30. Diagnosis (no test labels used):** noise and short clips do not explain it (DiffSSD test clips cropped to
  NSA durations, peak-normalized, noise matched to NSA's noise floor: v4 alone 0.049). On the test set the network calls
  664 clips synthetic and the fusion 332; the fusion demotes 134 clips the network scores above +10. Same pattern on
  consenting teammates' ElevenLabs clones: network +2.8, spectral -3.2, prosody -2.0.
- **Sat 18:40. Final is network-first (supersedes the two fusion profiles for scoring):** new profile `nn` in
  `hearsay/orchestrator.py`. The neural detector alone sets the score. Prosody, spectral, voice and rhythm still run
  and are shown as evidence (`role: "evidence"`, llr_contribution 0). Additive change to the response; old profiles kept.
- **Sat 19:45. NSA hints tested, not used for scoring:** breaths, pauses, harmonic "ribs", start-vs-middle drift
  (20 features, 2,160 clips, `ml/analysis/features/hint_feats.py`). None points the same way across mic recordings,
  studio audio, voice changer and DiffSSD. Speaking rate (clones +29% syllables/s on teammates) is app evidence and a
  reference check only.
- **Sat 20:00. Isolator-cleaned real speech counts as real** (team decision). Every model flags it (97-100%), so v5c
  trains on it as real.
- **Sat 20:00. v5c training data (diversity, NSA's advice):** see README "What we learned" 5; every source keeps a held-out
  slice, 4 new MLAAD systems are held out entirely, teammates are split by speaker. DiffSSD's test split (80%) is used for
  training (NSA: fair game); nothing is matched against NSA's test files.
- **Sat 21:30. NSA's real clips look like VCTK:** v4, AntiDeepfake-1B and MMS-300M all place the test set's low cluster
  on VCTK reals, not LJ/LibriSpeech. Model selection therefore uses VCTK reals as the main real reference.
- **Sat 22:30. Final submission: v5c, first epoch (`ep0.pt`), profile `nn` (supersedes v4p6):** chosen on held-out
  data only (table in README, "How we chose the final system"; diagrams in docs/ARCHITECTURE.md). TSV
  `HearsayScoreKey4Gemini.tsv` from `HEARSAY_FP32=1 python -m hearsay predict --profile nn`: 1,671 rows, all scores
  distinct, 32.8% above 0.5, sha256 048b2a2e6778f57e…. Held-out pooled minDCF 0.157, EER 2.86% (v4: 0.191, 4.03%).
  Known gap: isolator-cleaned real speech (47% flagged at VCTK's 1% false-alarm threshold).
- **Sat 22:30. Release v5c pins its profile:** `hearsay.json` carries `"profile_override": "nn"` (v3.pt sha256
  d3defcbd…), so the server scores exactly like the TSV whatever `FUSION_PROFILE` says. The Platt map
  (LLR = 0.696 s - 2.035, fit on DiffSSD validation) only affects the app's probability, never the ranking.
- **Sat 22:45. Weights reach Vultr from the team PC** (rsync over SSH to `/opt/dispel/models`). Israel added the PC's
  key and a firewall rule for its IP for this; both are removed after the event.
