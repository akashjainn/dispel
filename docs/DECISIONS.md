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
- **Sat. Hosting (supersedes the "inference runs locally" line above):** the API
  and inference run on a Vultr instance provisioned by Terraform (`infra/vultr/`).
  Audio is uploaded to it only on a user action. The server keeps no audio.
  Deployed access is HTTPS (Caddy) plus a bearer API key. `main` stays free of
  keys; weights are rsynced to the instance, never committed. (israel/backend-infra-setup)
- **Sat. Deploys:** merges to `main` that touch `server/` or `docker/` deploy over SSH from GitHub
  Actions. The runner opens a temporary firewall rule for its own IP, logs in as `deploy` (its key
  can only run `/opt/dispel/deploy.sh`), then closes the rule. Adding this replaced the server once
  (new IP, so a new sslip.io URL). `/` serves a "Team Gemini" landing page.
