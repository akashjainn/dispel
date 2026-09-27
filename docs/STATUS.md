# STATUS: update this at the end of every task

## Owners
Fill this in at kickoff. One owner per directory. The owner approves changes to it.

| Person | GitHub | Owns | Current task | Branch | Blocked on |
|---|---|---|---|---|---|
| Akash (repo owner) | akashjainn | `ml/`, `hearsay/`, model loading in `server/` | hearsay pipeline (six analyzers, fusion, TSV); v4 training | akash/hearsay-pipeline (PR #8) | NSA test-set download location |
| Aniket | aniketgarg1 | TBD | | | |
| David | DavidPopesc | `app/` | Wizard app: menu-bar wizard, file check, call watch (mock results) | david-frontend | `server/` for real scores |
| Israel | Israel-Jauregui | `server/`, `infra/`, `docker/Dockerfile.server` | App ↔ server link (install id, history, file checks to Vultr) | israel/app-server-link | weights on the Vultr volume (server serves mock until then) |
| Teammate 4 | TBD | TBD (pitch, demo clips, Devpost) | | | |

## Current state
- Model: **v5c** (XLS-R network alone, profile `nn`; final NSA TSV built from it). Scoring and training diagrams: docs/ARCHITECTURE.md; choice and numbers: DECISIONS.md, README.md.
- Live server: see the latest `infra` run summary or `terraform output base_url` (the URL changes when the server is replaced). Deploys to it are automatic on merge to `main`.
- Server: `/health`, `/analyze` and (0.4) `/history` run on Vultr with bearer auth. It loads the hearsay pipeline (the release can pin the profile; v5c pins `nn`) when `MODEL_DIR/hearsay.json` exists; no weights are on the volume yet, so every answer is the canned example with `mock: true`.
- App: `app/` runs on macOS. Menu-bar wizard; drop or pick a file to check it; detects calls (Zoom, FaceTime, Teams, Discord, Slack, browsers holding the mic) and highlights the call window purple when flagged. With a server configured (`app/config.local.json`), file checks go to it with an anonymous install id; otherwise, and for calls, scores are local mocks. No call audio is captured yet. Results are logged to `~/Library/Application Support/dispel-wizard/results.jsonl`.
- NSA submission: interim (v4p6) rated minDCF 0.258 / EER 10.2%; final TSV from v5c (sha256 048b2a2e…). NSA keeps the better of the two.

## Requests (changes needed outside your own directory)
- David → Akash: approve INTERFACES.md 0.2 (IPC section rewritten to match the app) and the call-watch decision in DECISIONS.md.
- Israel → David: review the `app/` part of israel/app-server-link (`src/main/analyzer.js`, new `src/main/config.js`, two lines in `main.js`).
- Israel → Akash, David: approve INTERFACES.md 0.4 and the install-id decision in DECISIONS.md.
- Akash: please review the AGENTS.md privacy-rule change (audio now goes to our Vultr server).
- Akash: v5c release is being copied to the Vultr volume from the PC; then restart `server` and check `/health` shows `weights_found: true`.
- Israel: after the event, remove the PC's SSH key from `/root/.ssh/authorized_keys` and its firewall rule.

## Log (newest first; one line each: time · who · what · branch/PR)
- Sat 22:45 · Akash (Claude) · docs/ARCHITECTURE.md (scoring + training diagrams), README results and figure, DECISIONS for interim/final; v5c release uploading to Vultr · PR #8
- Sat 22:30 · Akash (Claude) · v5c trained (2.2 h, warm start v4), chosen on held-out families; release v5c pins profile `nn`; final TSV built · PR #8
- Sat 18:40 · Akash (Claude) · profile `nn` (network alone; feature analyzers as evidence only), HEARSAY_FP32 · PR #8
- Sat 16:10 · Akash · interim TSV submitted (v4p6): minDCF 0.258, EER 10.2% ·
- Sat 11:40 · Akash (Claude) · merged main into akash/hearsay-pipeline (kept Israel's 0.4 server, re-applied FUSION_PROFILE; hearsay/ml from the branch) · PR #8
- Sat 10:10 · Israel · server replaced via infra `replace_server` (#6 bootstrap + models volume; new URL `https://66-42-83-221.sslip.io`); `/health` no longer counts `lost+found` on the empty volume as weights (it failed the deploy health check) · israel/weights-found-fix (#9)
- Sat 09:40 · Israel · server: `X-Dispel-Client` install id, check history in SQLite + `GET /history`, `mock` flag in responses, more containers accepted; app: file checks POST to the configured server; INTERFACES 0.4; STATUS.md de-duplicated after the #7 merge · israel/app-server-link
- Sat 09:10 · Akash (Claude overnight) · v4 trained, release v4p6 on the PC (data/release/v4p6); DiffSSD test-split result; ml/README v4 table · PR #8
- Sat 05:00 · Akash · PR #8 review fixes: bounded audio decode, model.name format documented, LFCC model defined once, docs · PR #8
- Sat 04:10 · Akash · six analyzers (lfcc, spectral, voice, rhythm added), nsa/app fusion profiles, ablation + NSA-reals safety check in ml/README.md · akash/hearsay-pipeline
- Sat 03:14 · Israel · repo-driven server (docker/remote-deploy.sh, compose.prod.yml), persistent models volume (deploys refuse without it), replace_server guard; no settings push/Gemini yet · israel/repo-driven-server (#6)
- Sat 02:50 · Akash · hearsay/ pipeline (v3 + prosody fusion, TSV writer/validator), server wired to it (mock when no weights), CPU torch in Dockerfile.server, INTERFACES 0.3 · akash/hearsay-pipeline
- Sat 02:50 · David · app: fix file drop (handled in preload), wizard now sits inside the cauldron, purple call ring drawn outside the call window and tracks it every 80 ms · david-frontend
- Sat 02:25 · David · app: Electron menu-bar wizard, mock analyzer, results log, macOS call detection helper (`native/callwatch.swift`), purple call highlight; INTERFACES 0.2 · david-frontend
- Sat · David · app: file drop works during calls too (drops were ignored while any app held the mic); flagged calls ask "end the call?" and Yes quits the call app (not browsers) · david-frontend
- Sat · David · app: sprites drawn like focus-wizard (one 80x120 canvas, shared origin), shown at 2x (160x240); cauldron recolored on load to an empty pot with no stew or gems · david-frontend
- Sat · David · CHALLENGE.md: add Discord post as source [D], correct the slides' 50/50 split to ~70/30, log [D]-vs-[I] conflicts (CSV, 0–100%, manipulation type) under Unknown · david-frontend
- Sat · Israel · landing page at /, deploy-on-merge workflow (SSH via temporary firewall rule), `deploy` user on the server · israel/deploy-workflow
- Sat · Israel · server/ API scaffold (mock), Vultr Terraform, INTERFACES 0.2, AGENTS/DECISIONS updated for Vultr hosting · israel/backend-infra-setup
- Fri 20:00 · Akash · repo initialized with docs only ·
