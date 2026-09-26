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
- Sat 02:25 · David · app: Electron menu-bar wizard, mock analyzer, results log, macOS call detection helper (`native/callwatch.swift`), purple call highlight; INTERFACES 0.2 · david-frontend
- Sat · David · CHALLENGE.md: add Discord post as source [D], correct the slides' 50/50 split to ~70/30, log [D]-vs-[I] conflicts (CSV, 0–100%, manipulation type) under Unknown · david-frontend
- Fri 20:00 · Akash · repo initialized with docs only ·
