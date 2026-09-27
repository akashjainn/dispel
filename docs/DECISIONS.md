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
  consenting HackGT volunteers' ElevenLabs clones: network +2.8, spectral -3.2, prosody -2.0.
- **Sat 17:30. Notify a contact (David, app):** on a flagged call the wizard offers "Notify trusted
  contact" (personal) or "Notify my manager" (work), chosen in the app's Settings. It sends a text
  from the user's own Mac through Messages (iMessage, else SMS relay), only when the user presses
  the button. Nothing goes through our server; the contact's name and number stay in the app's
  local settings file. The text says "likely AI-generated" with the score, never that the caller
  is certainly fake, and marks mock results as a test.
- **Sat 18:15. Real call checks, on request only (David, app):** calls are no longer scored automatically. When a
  call starts the wizard offers to listen; only "Listen" (or the tray item, or ⌘⇧L) records, for 12 s. It taps the
  call app's audio **output** (the other person, not the user's mic) with a Core Audio process tap
  (`app/native/callcapture.swift`, macOS 14.2+, "System Audio Recording" permission). If that app isn't playing sound
  itself (e.g. its audio runs in a WebKit process), it taps all system audio except Dispel and logs that. The WAV goes to
  our server as `source=call` and is deleted from a temp folder right after. A silent capture is reported as "couldn't
  hear anything", never scored.
- **Sat 18:15. Demo caller rig (David, `demo/caller/`):** an iPhone web page tells a second "caller" laptop to dial the
  judge's laptop (Teams/FaceTime links; Discord by hand), play a prepared clip into BlackHole as the call's mic, and
  optionally switch OBS to a matching deepfake video. Demo prop only; not part of the product or the server. Clips are
  gitignored. Voices must be consented clones or published dataset clips, not new deepfakes of real public figures.
- **Sat 18:40. Final is network-first (supersedes the two fusion profiles for scoring):** new profile `nn` in
  `hearsay/orchestrator.py`. The neural detector alone sets the score. Prosody, spectral, voice and rhythm still run
  and are shown as evidence (`role: "evidence"`, llr_contribution 0). Additive change to the response; old profiles kept.
- **Sat 18:45. Call checks: one-time opt-in (David, app; supersedes "on request only" above):** on the first detected
  call the wizard asks once, "Check my calls automatically?". "Yes, always" saves `autoCheckCalls: true` and from then
  on every call is checked as it starts (12 s, "Listening…" bubble shown while recording, clip deleted after the
  server answers). "Only when I ask" saves false: checks only from the tray or ⌘⇧L. Closing the bubble leaves it
  unanswered, so it asks again next call. Changeable in Settings. AGENTS.md's capture rule updated to match.
- **Sat 19:45. NSA hints tested, not used for scoring:** breaths, pauses, harmonic "ribs", start-vs-middle drift
  (20 features, 2,160 clips, `ml/analysis/features/hint_feats.py`). None points the same way across mic recordings,
  studio audio, voice changer and DiffSSD. Speaking rate (clones +29% syllables/s on the HackGT volunteers) is app evidence and a
  reference check only.
- **Sat 20:00. Isolator-cleaned real speech counts as real** (team decision). Every model flags it (97-100%), so v5c
  trains on it as real.
- **Sat 20:00. v5c training data (diversity, NSA's advice):** see README "What we learned" 5; every source keeps a held-out
  slice, 4 new MLAAD systems are held out entirely, the HackGT volunteers are split by speaker. DiffSSD's test split (80%) is used for
  training (NSA: fair game); nothing is matched against NSA's test files.
- **Sat 20:20. Hugging Face stand-in model (proposed by Israel, needs Akash's OK):** while `MODEL_DIR` has no `hearsay.json`,
  the server answers with a third-party open detector instead of demo data: `mo-thecreator/Deepfake-audio-detection`
  (wav2vec2-base, Apache-2.0) pinned to commit `e4d9874b493362149cec96ced85f00b00b1a04c0` (`HF_MODEL`/`HF_REVISION` in
  `docker/compose.prod.yml`). Order: hearsay release > HF stand-in > mock. Weights are downloaded once into
  `/opt/dispel/data/hf`; inference runs on our server, so audio is never sent to Hugging Face. Scored with hearsay's
  windowing (up to 3 x 4 s), window LLR = logit[fake] - logit[real], mean over windows, capped at +/-ln(100); same
  0.25/0.75 band. Check run (`server/tools/score_folder.py`): 8 LibriSpeech clean clips vs 6 macOS `say` TTS clips:
  fakes 6/6 likely_synthetic; reals 6 likely_real, 1 inconclusive, 1 likely_synthetic; AUC 1.000. Rejected on the same
  clips: `MelodyMachine/Deepfake-audio-detection-V2` (called all 6 TTS clips real at p ~ 1e-5, also through the stock HF
  pipeline) and `Gustking/wav2vec2-large-xlsr-deepfake-audio-classification` (ranked well but 4 of 8 reals >= 0.75, and
  3-4x slower on CPU). Not yet checked on ElevenLabs clones or phone audio. (israel/hf-model)
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
- **Sat 22:45. Wizard voice lines committed as app assets (proposed by Israel, needs Akash's and David's OK):** the wizard
  and witch speak short ElevenLabs TTS lines at big moments only (file verdicts, the hang-up spell; nothing while idle or
  listening). The 26 mp3s (1.3 MB) live in `app/Assets/voice/<wizard|witch>/` and are the one exception to "never commit
  audio": they are UI sound effects, not recordings of anyone, and every teammate needs them for the demo. `.gitignore`
  allows only `app/Assets/voice/*/*.mp3`; AGENTS.md says so. Voices, model and script: `app/Assets/voice/README.md`.
  Lines say "likely synthetic" / "likely real", never "fake" or "real" as a certainty. (israel/wizard-voice)
- **Sat 23:30. Domain hocuspocus.tech, DNS on Vultr (Israel):** registered at get.tech, nameservers ns1/ns2.vultr.com;
  the zone and records are Terraform (`infra/vultr/dns.tf`) so they follow the server's IP. Apex and www serve the static
  site in `web/` (Israel owns it; the upload web app goes there), `api.` is the API base. The sslip.io name keeps working (health check, old configs).
- **Sun 01:30. Public website with an open file check (Israel, needs Akash's and David's OK):** hocuspocus.tech runs the
  wizard's file check in a browser (`web/`). A page can't hide a key, so the server has `POST /web/analyze` with no key,
  no install id and no history, limited per client IP per hour (`WEB_CHECKS_PER_HOUR`: code default 30, set to 300 on the server for the expo,
  where many visitors share one venue IP); audio handling is
  the same as `/analyze` (memory/temp file, deleted, never sent to a third party). The site reuses the app's art, voice
  lines and sprite scripts through read-only mounts of `app/` instead of copies. Copy says "sent to our server". (israel/web-app)
- **Sun 10:30. Final result (NSA):** minDCF **0.1027** for the v5c final (interim 0.258). NSA keeps the better of the two.
