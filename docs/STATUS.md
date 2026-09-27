# STATUS: update this at the end of every task

## Owners
Fill this in at kickoff. One owner per directory. The owner approves changes to it.

| Person | GitHub | Owns | Current task | Branch | Blocked on |
|---|---|---|---|---|---|
| Akash (repo owner) | akashjainn | `ml/`, `hearsay/`, model loading in `server/` | hearsay pipeline (six analyzers, fusion, TSV); v4 training | akash/hearsay-pipeline (PR #8) | NSA test-set download location |
| Aniket | aniketgarg1 | TBD | | | |
| David | DavidPopesc | `app/` | Wizard app: menu-bar wizard, file check, call watch (mock results) | david-frontend | `server/` for real scores |
| Israel | Israel-Jauregui | `server/`, `infra/`, `docker/Dockerfile.server` | Wizard presence + hang-up spell (wand out, bolt, call window shatters) | israel/wizard-presence (on top of israel/3d-sprites) | weights on the Vultr volume (server serves mock until then) |
| Teammate 4 | TBD | TBD (pitch, demo clips, Devpost) | | | |

## Current state
- Model: v4p6 (six analyzers; nsa/app profiles), see DECISIONS.md and ml/README.md. Calibration on new voices is a known gap.
- Live server: see the latest `infra` run summary or `terraform output base_url` (the URL changes when the server is replaced). Deploys to it are automatic on merge to `main`.
- Server: `/health`, `/analyze` and (0.4) `/history` run on Vultr with bearer auth. It loads the hearsay pipeline (`app` profile) when `MODEL_DIR/hearsay.json` exists; no weights are on the volume yet, so every answer is demo data (`mock: true`) built from the canned example: about 70% likely synthetic, 30% likely real (0.5).
- App: `app/` runs on macOS. Menu-bar wizard; drop or pick a file to check it; detects calls (Zoom, FaceTime, Teams, Discord, Slack, browsers holding the mic) and highlights the call window purple when flagged. With a server configured (`app/config.local.json`), file and call checks go to it with an anonymous install id; otherwise scores are local mocks (same 70/30 mix). No call audio is captured yet, so call checks send no file. Results are logged to `~/Library/Application Support/dispel-wizard/results.jsonl`.
- NSA submission: TSV writer + validator in `hearsay/cli.py`; metric known (minDCF, see CHALLENGE.md). Test audio delivery still unknown.

## Requests (changes needed outside your own directory)
- David → Akash: approve INTERFACES.md 0.2 (IPC section rewritten to match the app) and the call-watch decision in DECISIONS.md.
- Israel → David: review the `app/` part of israel/app-server-link (`src/main/analyzer.js`, new `src/main/config.js`, two lines in `main.js`).
- Israel → Akash, David: approve INTERFACES.md 0.4 and the install-id decision in DECISIONS.md.
- Israel → Akash, David: approve INTERFACES.md 0.5 (file-less call checks, 70/30 demo answers); David: review `app/src/main/analyzer.js` and one comment in `main.js` · israel/mock-verdict-mix
- Israel → David: review the wizard's presence and hang-up spell in `app/` (new `src/renderer/magic.js`, `obliterate.*`, `src/main/obliterate.js`, `src/preload/obliterate.js`; hooks in `sprites.js`, `wizard.js`, `main.js`) and the IPC note in INTERFACES.md · israel/wizard-presence
- Israel → David: review the 3D look in `app/` (`Assets/3d/`, `scripts/make_3d_sprites.py`, stage now 4x with sweep/sparkle effects in `sprites.js`) · israel/3d-sprites
- Israel → David: review the witch character in `app/` (new `Assets/witch-sprites.png`, `scripts/make_witch_sprites.py`, `src/main/prefs.js`; sprite layer can switch sheets) and the IPC note in INTERFACES.md · israel/witch-skin
- Akash: please review the AGENTS.md privacy-rule change (audio now goes to our Vultr server).
- Akash: put the v4p6 release on the Vultr volume (`/opt/dispel/models`) so the server stops serving mock data.

## Handoff: israel/wizard-presence (paused Sat 20:10, Israel moved to backend)
Goal: make the wizard/witch feel present, and make "Yes, hang up" a spell: the character pulls a wand out of the cauldron, charges, casts; a bolt hits the call window, it turns into bricks (the app quits behind them), then they shatter. Everything must look like the sprites: pixel grid + Endesga-32 colors in 2D, smooth and lit like the 3D sprites in 3D. Only add new things; don't remove existing features.
- Where: `app/src/renderer/magic.js` (idle life + the wand half of the spell), `app/src/renderer/obliterate.*` + `app/src/main/obliterate.js` + `app/src/preload/obliterate.js` (the bolt/bricks/shatter window), hooks in `sprites.js` (fx passes, shake, layer offset/clip/row swap), `wizard.js`, `main.js` (spell flow, `greet` mode), `native/callwatch.swift` (`end <app>`, `focus <app>`).
- Verified by the user on screen: idle life, wand spell in both looks, Discord focused and quit on hang-up (when the helper's app list was fresh).
- Fixed in the last commit, NOT yet seen by the user: (1) the helper slept instead of running its run loop, so NSWorkspace's app list froze and a reopened Discord was never quit (and the ring stayed); it now runs the run loop (reproduced and fix checked with TextEdit). (2) The purple ring now hides when the spell hits and only comes back if the hang-up fails. (3) The bricks were restyled to match the sprites (robe purples, lit top-left, ink outline, some with a gold robe star; beveled blocks in 3D) and the pale diagonal "glint" band was replaced with a few twinkling bricks. The new bricks have not been looked at: render them first (load `obliterate.html` with its preload and send `spell:cast`; one style per Electron process, a second window in the same process failed to load).
- Known gaps: the spell hits the call window's bounds even if other windows cover it (we bring the app to the front first; if activation is refused, it still lands on whatever is on top). Discord drops the mic for moments, so its call can "end" and "start" again mid-call, making new sessions. PR not opened yet (open it against `israel/3d-sprites`; ~1,000 lines; David and Akash approve `app/` and INTERFACES.md).

## Log (newest first; one line each: time · who · what · branch/PR)
- Sat 20:10 · Israel (Claude) · app: helper runs its run loop so it quits the current Discord (not a stale one), ring hides when the spell hits, bricks restyled to match the sprites (untested on screen); paused, see Handoff · israel/wizard-presence
- Sat 19:15 · Israel (Claude) · app: fixed the 3D stage getting stuck zoomed (an effect threw mid-draw); "Yes, hang up" brings the call app to the front first (the spell was hitting whatever window was on top of it) and falls back to SIGTERM if the app ignores the polite quit (Discord did) · israel/wizard-presence
- Sat 19:10 · Israel (Claude) · app: the wizard/witch has more presence: blinks, cauldron bubbles, wand tricks when idle, smiles and hops on hover, gets its wand out when a file is dragged over, verdict reactions, an aura when a call is flagged, a hello when summoned. "Yes, hang up" is now a spell: wand out of the cauldron, charge, cast; a bolt hits the call window, it turns to crystal (the app quits behind it) and shatters. Effects follow the look (pixel grid in 2D, smooth in 3D). The wand's magic is stepped at 12 fps in the wand star's colors. The helper now takes `end <app>` so a call app that drops the mic for a moment (Discord) still hangs up · israel/wizard-presence
- Sat 18:11 · Israel (Claude) · app: 3D look is now smooth pre-rendered 3D sprites, not voxels (`app/scripts/sprite3d.py`: sprites modeled as smoothed distance fields from the pixel art, cauldron as an exact one; soft shadows, AO, fill/rim light, gloss; sparkles as glowing points) · israel/3d-sprites
- Sat 18:01 · Israel (Claude) · app: 3D look redone as ray-traced voxels (`app/scripts/voxel_render.py`): characters/wand/poof voxelized from the pixel art with rounded depth, cauldron built in 3D (rim, hollow inside, lugs, feet); shadows, AO, 22° turn · israel/3d-sprites
- Sat 17:48 · Israel (Claude) · app: "3D look" option. Every sheet has a pre-rendered 3D version in `app/Assets/3d/` (4x, made by `app/scripts/make_3d_sprites.py`); the stage canvas is now 4x (320x480) so both looks draw crisp. Transitions: new character = sink into the hat, poof + sparkle burst, rise; 2D↔3D = glowing line sweeps up from the cauldron. Look saved in prefs.json; IPC is now `wizard.onLook` · israel/3d-sprites
- Sat 17:31 · Israel (Claude) · app: witch character. Right-click (or tray) → "Turn into a witch/wizard" morphs via the sink-into-hat animation; choice saved in `<userData>/prefs.json`; tray icon and menu copy follow it. Witch sheet is generated from the wizard's frames (`app/scripts/make_witch_sprites.py`) so it lines up with the cauldron · israel/witch-skin
- Sat 17:00 · Israel (Claude) · mock answers are now ~70% likely synthetic / 30% likely real (server and app mock); app sends call checks to the server with no file, falls back to the local mock; INTERFACES 0.5 · israel/mock-verdict-mix
- Sat 12:15 · David · app: Learn mode (the wizard teaches what deepfakes are, common scams, and how to protect family), right-click menu on the wizard · david-frontend
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
