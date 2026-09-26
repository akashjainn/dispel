# STATUS: update this at the end of every task

## Owners
Fill this in at kickoff. One owner per directory. The owner approves changes to it.

| Person | GitHub | Owns | Current task | Branch | Blocked on |
|---|---|---|---|---|---|
| Akash (repo owner) | akashjainn | `ml/`, model loading in `server/` | NSA data profiling; score v0/v2/v2e on public ElevenLabs sets | | NSA metric and labels |
| Aniket | aniketgarg1 | TBD | | | |
| David | DavidPopesc | `app/` | Wizard app: menu-bar wizard, file check, call watch (mock results) | david-frontend | `server/` for real scores |
| Teammate 4 | TBD | TBD (pitch, demo clips, Devpost) | | | |

## Current state
- Model: v2e frozen before the event (see DECISIONS.md). The server is not built yet.
- App: `app/` runs on macOS. Menu-bar wizard; drop or pick a file to check it; detects calls (Zoom, FaceTime, Teams, Discord, Slack, browsers holding the mic) and highlights the call window purple when flagged. **All scores are mocks** that always say likely synthetic. No audio is captured yet. Results are logged to `~/Library/Application Support/dispel-wizard/results.jsonl`.
- NSA submission: not started. The scoring metric is unknown (see CHALLENGE.md).

## Requests (changes needed outside your own directory)
- David → Akash: approve INTERFACES.md 0.2 (IPC section rewritten to match the app) and the call-watch decision in DECISIONS.md.

## Log (newest first; one line each: time · who · what · branch/PR)
- Sat · David · app: file drop works during calls too (drops were ignored while any app held the mic); flagged calls ask "end the call?" and Yes quits the call app (not browsers) · david-frontend
- Sat · David · app: sprites drawn like focus-wizard (one 80x120 canvas, shared origin), shown at 2x (160x240); cauldron recolored on load to an empty pot with no stew or gems · david-frontend
- Sat 02:50 · David · app: fix file drop (handled in preload), wizard now sits inside the cauldron, purple call ring drawn outside the call window and tracks it every 80 ms · david-frontend
- Sat 02:25 · David · app: Electron menu-bar wizard, mock analyzer, results log, macOS call detection helper (`native/callwatch.swift`), purple call highlight; INTERFACES 0.2 · david-frontend
- Sat · David · CHALLENGE.md: add Discord post as source [D], correct the slides' 50/50 split to ~70/30, log [D]-vs-[I] conflicts (CSV, 0–100%, manipulation type) under Unknown · david-frontend
| David | DavidPopesc | TBD | | | |
| Israel | | `server/`, `infra/`, `docker/Dockerfile.server` | Backend + Vultr infra | israel/backend-infra-setup | Vultr API key; weights from Akash |
| Teammate 4 | TBD | TBD (pitch, demo clips, Devpost) | | | |

## Current state
- Model: v3p (v3 + prosody fusion), see DECISIONS.md and ml/README.md. Calibration on new voices is a known gap.
- Live server: see the latest `infra` run summary or `terraform output base_url` (the URL changes when the server is replaced). Deploys to it are automatic on merge to `main`.
- Server: scaffolded on `israel/backend-infra-setup`. `/health` and `/analyze` exist and return the mock example (`mock: true`) until hearsay/ is wired in. Vultr Terraform written and validated, **not yet applied**.
- App: not started.
- NSA submission: TSV writer + validator in `hearsay/cli.py`; metric known (minDCF, see CHALLENGE.md). Test audio delivery still unknown.

## Requests (changes needed outside your own directory)
- Akash: please review the AGENTS.md privacy-rule change (audio now goes to our Vultr server).
- Akash: `hearsay/` should expose one function the server can call; then replace the mock in `server/app/main.py`.

## Log (newest first; one line each: time · who · what · branch/PR)
- Sat 02:50 · Akash · hearsay/ pipeline (v3 + prosody fusion, TSV writer/validator), server wired to it (mock when no weights), CPU torch in Dockerfile.server, INTERFACES 0.3 · akash/hearsay-pipeline
- Sat · Israel · server/ API scaffold (mock), Vultr Terraform, INTERFACES 0.2, AGENTS/DECISIONS updated for Vultr hosting · israel/backend-infra-setup
- Sat · Israel · landing page at /, deploy-on-merge workflow (SSH via temporary firewall rule), `deploy` user on the server · israel/deploy-workflow
- Sat · Israel · repo-driven server (docker/remote-deploy.sh, compose.prod.yml), persistent models volume, replace_server guard, settings push for GEMINI_* · israel/repo-driven-server
- Fri 20:00 · Akash · repo initialized with docs only ·
