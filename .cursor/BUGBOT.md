# Bugbot review rules for this repo

Project context: this is an Electron desktop app (`app/`) that calls a local
Python FastAPI inference server (`server/`) to detect AI-generated audio. The
API contract is in `docs/INTERFACES.md`. Hackathon code: flag real bugs and
risks, not style.

## Always flag
- **Secrets:** any committed API key or token (ElevenLabs, Hugging Face,
  GitHub), any `.env` file, or a hard-coded credential.
- **Committed binaries:** audio files (wav/mp3/flac/m4a/webm/ogg), model
  weights (pt/pth/onnx/safetensors/bin), or datasets.
- **Electron security:**
  - `nodeIntegration: true`, `contextIsolation: false`, or a disabled sandbox
  - `webSecurity: false`
  - loading remote URLs into a BrowserWindow
  - IPC handlers that don't validate their arguments
  - exposing `ipcRenderer` or Node APIs directly through the preload
  - `shell.openExternal` called with unvalidated input
- **Privacy:**
  - audio captured without a user action
  - audio written to disk and never deleted
  - audio or results sent anywhere other than 127.0.0.1
- **Interface drift:**
  - request or response fields that don't match `docs/INTERFACES.md`
  - a PR that changes the API without updating INTERFACES.md and bumping its version
- **Server:**
  - loading the model per request instead of once at startup
  - blocking the event loop with inference in an async handler (use a thread
    or executor)
  - temp files that aren't cleaned up
  - skipping resampling to 16 kHz mono
  - missing error handling for undecodable, too-short or too-long audio
- **Honesty in UI copy:**
  - strings that present a result as certain ("this is fake", "100% real")
  - showing a manipulation type without its confidence, or when the type is
    "unknown"
- **Evaluation code in `ml/`:**
  - thresholds or calibration tuned on test data
  - speakers or generators leaking between train and test splits

## Don't flag
- Formatting, naming, or missing docstrings
- Missing tests in prototype UI code
- TODOs that are already listed in `docs/STATUS.md`
