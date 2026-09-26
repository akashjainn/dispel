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
server/             FastAPI wrapper around hearsay/ on 127.0.0.1:8765 (POST /analyze, GET /health)
app/                Electron wizard client of server/
ml/                 training, calibration, ablations, evaluation scripts (no weights)
docker/             Dockerfile and entrypoint that run the CLI on a mounted test set
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
- Inference runs locally. Audio never leaves the machine.

## Model facts (don't contradict these in code, UI copy, or the pitch)

- The default model is **v2e**: an average of two calibrated XLS-R 300M
  detectors (v0 and v2). Each takes 16 kHz mono audio, up to 3 non-overlapping
  4 s windows per segment.
- **Weights are not in git** (about 1.2 GB each; non-commercial license).
  Code finds them through the `MODEL_DIR` env var; ask Akash for a copy.
  Release hashes live in `docs/DECISIONS.md`.
- License: MLAAD is CC BY-NC, so the model and demo are **non-commercial**.
- Known weaknesses (the report and pitch must say these plainly):
  - Some real voices get over-flagged. On one real politician's phone-quality
    audio, about 1 in 3 clips come out "likely synthetic" at a 50% prior.
  - The model has not been validated on current commercial generators such as
    ElevenLabs yet. Check `docs/STATUS.md` for the latest numbers.

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
- App dev: `TBD`
- Server dev: `TBD`
- Smoke tests: `TBD`
- NSA TSV: `TBD` (the header is exactly `filename<TAB>cm-score`; see CHALLENGE.md)
- Docker: `TBD`
