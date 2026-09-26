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
