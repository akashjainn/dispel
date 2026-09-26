# AGENTS.md: instructions for every agent and human on this repo

This file is the single source of truth. Claude Code reads it through CLAUDE.md
(which just imports it); Cursor and Codex read it directly. **Edit only this
file.** Don't put instructions in CLAUDE.md or in a tool-specific rules file.

## What we're building (HackGT 13, Sep 25–27, 2026)

**The core, which is required and scored:** a forensic pipeline, `hearsay/`.
It takes any audio file, decides which analyses to run, runs them, fuses the
results into one synthetic probability (0.0–1.0), and explains the result. It
is packaged as a **Docker image** that writes the NSA TSV. See
`docs/CHALLENGE.md` for the rubric: 60% detection, 20% number of distinct
forensic techniques, 20% documentation and explainability.

**The front end:** a desktop app (Electron) with a **wizard sprite** that
tells you whether audio playing on your computer, or a file you drop on it, is
likely AI-generated or manipulated. It is a thin client over the same pipeline.
It must never hold up the pipeline, the Docker image, or the TSV.

- The sprite is the front door: you summon it, it listens to a clip on request,
  and it reacts with a likely-synthetic, inconclusive, or likely-real verdict.
- Clicking it opens the **evidence report**, which has:
  - a per-segment likelihood timeline
  - a calibrated likelihood with an explicit "inconclusive" band
  - **which forensic techniques ran, what each one found, and how much each
    moved the score**
  - a channel/quality note and a transcript
  - a plain-language "what this can't tell you" section

Tracks: A Marina's Mission (Social Good: healthcare, sustainability; presented
by Aramco) and the NSA HEARSAY sponsor challenge.

### Timeline (Eastern time)
- Fri 8:00 PM: hacking starts
- Sat 12:00 PM, Sat 8:00 PM: team syncs
- **Sun 2:00 AM: feature freeze.** After this, bug fixes only.
- **Sun 6:00 AM: demo freeze.** After this, only fixes needed for the demo.
- Sun 8:00 AM: hacking ends (check Devpost for the exact submission time)
- Sun 9:00–11:15 AM: expo

## Architecture

```
hearsay/            Python package: the forensic pipeline (the core deliverable)
  analyzers/        one module per technique. Each returns features plus a
                    plain-language finding:
                    metadata, compression, spectral, prosody, enf,
                    speaker_drift, splice, dl_detector
  orchestrator.py   picks which analyzers to run from the file type, codec,
                    early findings and confidence (the "agentic" bonus)
  fusion.py         combines analyzer features into cm-score; trained on
                    NSA's training set with cross-validation
  cli.py            `hearsay predict <dir> -o <team>_predictions.tsv`
server/             FastAPI wrapper around hearsay/ (POST /analyze, GET /health); local 127.0.0.1:8765 or on Vultr
infra/vultr/        Terraform for the Vultr instance that hosts server/ + inference (see its README)
app/                Electron wizard client of server/
demo/caller/        demo prop: iPhone remote that plays prepared caller clips into a real call
ml/                 training, calibration, ablations, evaluation scripts (no weights)
docker/             Dockerfiles: the NSA CLI image, and Dockerfile.server + compose.yml for the API
docs/               STATUS.md, INTERFACES.md, DECISIONS.md, CHALLENGE.md, examples/
```

### Rules for analyzers
- Every analyzer has the same signature:
  `analyze(audio, sr, meta, context) -> {"features": {...}, "finding": str, "ran": bool, "ms": int}`.
- It must never crash the pipeline. On failure it returns `ran: false` and a reason.
- An analyzer only counts toward the rubric if **fusion actually uses its
  features** and the ablation table shows what it contributed, even when that
  is "no effect".
- The scoring path must be deterministic and must work offline inside Docker.
  An LLM can write the explanation text, but it must never change the score,
  and a template must be used when no LLM is available.

- The Electron app is a **client** of `server/`. The HTTP API between them is
  defined only in `docs/INTERFACES.md`.
- The UI must work against `docs/examples/analyze_response.example.json` before
  the real model is connected.
- Audio capture happens only when the user asks, over a short window
  (e.g. "check the last 15 s"). **Never** record continuously, and never store
  or upload audio without an explicit user action.
- **Inference and the API run on Vultr** (decided Sat, see DECISIONS.md). The
  app uploads audio to our own Vultr instance over HTTPS, only when the user
  asks; the server must not persist audio (process in memory or a temp file,
  delete after the response) and must not send it to any third party. The pitch
  and UI copy must say "sent to our server", not "never leaves your machine".
  The NSA Docker image still runs fully offline.

## Model facts (don't contradict these in code, UI copy, or the pitch)

- The release (**v4p6**) fuses six analyzers additively (`hearsay/fusion.py`): the v4 neural detector
  (XLS-R 300M fine-tuned on DiffSSD, ElevenLabs stock voices and Kokoro, with noise + time-stretch augmentation), an
  LFCC-LCNN detector, and four interpretable feature analyzers (prosody, spectral, voice, rhythm). Two fusion
  profiles: `nsa` (all six, used for the TSV) and `app` (neural + prosody, used by the server; it held up better on
  unfamiliar voices). Input is 16 kHz mono; the neural models score up to 3 non-overlapping 4 s windows.
  Numbers and ablations: `ml/README.md`.
- **Weights are not in git** (about 1.2 GB for the neural detector, 1 MB for LFCC; non-commercial license).
  Code finds them through the `MODEL_DIR` env var; ask Akash for a copy.
  Release hashes live in `docs/DECISIONS.md`.
- License: MLAAD is CC BY-NC, so the model and demo are **non-commercial**.
- Known weaknesses (the report and pitch must say these plainly):
  - Heavy time-stretching still hurts (librosa phase vocoder: minDCF 0.088 fused vs 0.000 clean). A stretch
    method never seen in training (rubberband) pushes some real clips toward "synthetic"; under investigation.
  - Cloned voices of real people on ordinary mics: v4 flags 65% of teammates' consented ElevenLabs clones on clean
    audio and 35% when stretched, and most still get a "likely real" verdict. Numbers and runs are in `ml/README.md`.

## UI and copy rules
- Never say "fake" or "real" as a certainty. Use "likely synthetic",
  "inconclusive", "likely real", and always show the likelihood.
- If the audio sounds like a phone call or is heavily compressed, say that this
  lowers reliability.
- Any "type of manipulation" hint (TTS, voice conversion, splice, replay, scene) shows "unknown" unless we are confident. A wrong
  label shown with confidence is worse than "unknown".

## Keeping context across agents (required)

At the **start** of any task, read these first:
1. AGENTS.md (this file)
2. `docs/STATUS.md`: who owns what, what's in progress, and what's blocked
3. `docs/INTERFACES.md`, if you touch the API between `app/` and `server/`
4. `docs/CHALLENGE.md`, if you touch the NSA submission, an analyzer, fusion, or Docker

At the **end** of any task:
- Update your row in `docs/STATUS.md` and add one line to its Log, with the
  time, who, what changed, and the branch or PR.
- Any decision that others need to know goes in `docs/DECISIONS.md` (append
  only, dated).
- Changing an interface means updating `docs/INTERFACES.md` **in the same PR**,
  bumping its version, and saying so in the PR description.

Other rules:
- Stay inside the directories your owner is responsible for (see STATUS.md).
  If you need a change somewhere else, note it in STATUS.md under "Requests".
- Don't invent facts about the NSA challenge. Put anything unconfirmed in
  CHALLENGE.md under "Unknown".
- When you report results, say exactly what you ran: data, sample count, and
  command.

## Git workflow

- Repo owner and admin: **@akashjainn**. He handles collaborator invites, the
  ruleset on `main`, and the Bugbot settings. Ask him for access or settings
  changes.
- `main` must always build and run. **No direct pushes to `main`.**
- Branch names: `<name>/<topic>`, for example `akash/nsa-tsv` or
  `david/sprite-anim`.
- Keep PRs small, ideally under about 300 changed lines, and **squash-merge**
  them.
- Before opening a PR:
  - `git fetch && git rebase origin/main`
  - run the smoke test for the part you changed (see Commands)
- **Cursor Bugbot** reviews every PR automatically.
  - Fix each Bugbot comment, or reply explaining why it doesn't apply.
  - Comment `bugbot run` to re-run it.
- Merging:
  - The author merges once Bugbot has no unresolved comments.
  - If the PR touches `docs/INTERFACES.md` or another owner's directory, that
    owner must approve first.
- Commit messages: `area: what changed`, for example
  `server: add /analyze stub` or `app: sprite idle animation`.

### What agents may and may not do in git
- **May:** create branches, commit, and push to their own feature branch.
- **May not:**
  - push to `main`
  - force-push a branch someone else uses
  - merge PRs
  - rewrite shared history
  - delete branches they didn't create
- Opening and merging PRs is a human decision.

### Never commit
- audio files (`*.wav`, `*.mp3`, `*.flac`, `*.m4a`, `*.webm`, `*.ogg`)
- model weights (`*.pt`, `*.pth`, `*.onnx`, `*.safetensors`, `*.bin`)
- datasets, `.env` files, or any key or token (ElevenLabs, Hugging Face,
  GitHub). Use `.env.example` with placeholder values instead.

## Commands

Fill these in when each part is scaffolded. Don't guess them.
- App dev (David): `cd app && npm install && npm start` (`npm start -- --simulate-call` runs the call flow without a real call). To use the Vultr server: `cp app/config.example.json app/config.local.json` and fill it in
- Demo caller rig (on the second laptop): `cd demo/caller && npm start`, then open the printed URL on the phone. Setup: `demo/caller/README.md`
- Server dev: `cd server && pip install -r requirements.txt && uvicorn app.main:app --port 8765`
- Server tests: `cd server && python -m pytest -q`
- Server in Docker: `docker compose -f docker/compose.yml up --build`
- Deploy to Vultr: merging to `main` changes under `server/` or `docker/` deploys automatically (`.github/workflows/deploy.yml`). Deploy logic lives in `docker/remote-deploy.sh` and `docker/compose.prod.yml` (repo-driven). Infra changes: Actions -> infra -> Run workflow; replacing the server needs the `replace_server` box. Weights live on a persistent volume and survive a replacement. Details in `infra/vultr/README.md`.
- Smoke tests: `TBD`
- NSA TSV: `MODEL_DIR=<release> python -m hearsay predict <test_dir> -o <Team>_predictions.tsv --template <NSA template>.tsv` (writes and validates; header `filename<TAB>cm-score`). Check only: `python -m hearsay validate <tsv> --template <template>`
- Docker (NSA): same image as the server; see the header of `docker/Dockerfile.server` for the `docker run` line.
