# STATUS: update this at the end of every task

## Owners
Fill this in at kickoff. One owner per directory. The owner approves changes to it.

| Person | GitHub | Owns | Current task | Branch | Blocked on |
|---|---|---|---|---|---|
| Akash (repo owner) | akashjainn | `ml/`, model loading in `server/` | NSA data profiling; score v0/v2/v2e on public ElevenLabs sets | | NSA metric and labels |
| Aniket | aniketgarg1 | TBD | | | |
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
- Fri 20:00 · Akash · repo initialized with docs only ·
