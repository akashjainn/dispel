# Dispel wizard (desktop app)

A menu-bar wizard that tells you whether a voice is likely synthetic.

```
npm install
npm start                      # wizard appears; click the menu-bar icon to hide or summon it
npm start -- --simulate-call   # runs the call flow with a fake call window (real calls are ignored)
```

- **Check a file:** drop an audio file on the wizard or on the menu-bar icon,
  or click the wizard to pick a file. The wizard answers with a verdict and a score.
- **Calls (macOS 14.2+):** when Zoom, FaceTime, Teams, Discord, Slack or a
  browser is using the mic, the wizard sits small and grayed out just outside
  the call window (right side, else left; inside the top-right corner and
  click-through only when the call fills the screen), so it never covers the
  call's End button. The wizard and the colored outline hide while another app
  is in front and come back when you return to the call. If the voice scores likely real, the call
  window gets a steady green outline and the wizard stays small and gray. If
  the call is flagged, it comes out in full color, the
  call window gets a purple outline, and a speech bubble asks whether to end the
  call. "Yes, hang up" quits Zoom, FaceTime, Teams, Discord or Slack (like ⌘Q);
  for a browser call it asks you to close the tab instead. Turn call watching
  off with "Watch calls" in the tray menu (right-click the icon).
- **Learn:** the wizard explains what a deepfake is, common deepfake scams, and
  how to protect yourself and your family (safe word, call back, slow down,
  where to report). Open it from the tray menu, by right-clicking the wizard, or
  with "How do these scams work?" after a file check. Text: `src/renderer/lessons.js`.
- **Log:** every result is appended to
  `~/Library/Application Support/dispel-wizard/results.jsonl` (score, verdict,
  file name or call app; never audio). Tray menu → "Open results log".

## Connecting to the server

File checks go to our server (Vultr) once it's configured:

```
cp config.example.json config.local.json   # gitignored
# set serverUrl (the latest infra run summary shows it) and apiKey (ask Israel)
```

`DISPEL_SERVER_URL` and `DISPEL_API_KEY` override the file. The file is
uploaded only when you drop or pick it. The server answers with demo data
(`mock: true`, shown in the bubble) until the model weights are on it.

On first launch the app makes an anonymous install id (a random UUID in
`~/Library/Application Support/dispel-wizard/client-id`) and sends it with each
check, so the server can keep this install's history (`GET /history`). No
account, nothing personal; delete the file to start over.

With no server set, file checks use the local mock, and **calls always do**
(no call audio is captured yet): it waits 2.5 s for a file or 3.5 s for a
call, then reports **"likely real"** (2–14%). To demo the deepfake flow, pick
tray menu → "Mock result (no model)" → "Likely synthetic" (86–98%), or start
with `DISPEL_MOCK_VERDICT=synthetic npm start`.

## Layout

| Path | What |
|---|---|
| `src/main/main.js` | tray, windows, the file and call flows |
| `src/main/analyzer.js` | `POST /analyze` for files when a server is set; local mock otherwise |
| `src/main/config.js` | server URL and key, and the anonymous install id |
| `src/main/callwatch.js` | runs the Swift helper and emits call start, move and end |
| `native/callwatch.swift` | asks Core Audio which apps are using the mic, and finds their window |
| `src/renderer/` | wizard page (sprites, speech bubble) and the purple overlay |
| `Assets/` | sprite sheets (80×128 frames, drawn at 2×) |

`npm start` builds `bin/callwatch` with `swiftc`, which needs the Xcode
command line tools. Without it the app still runs, but real calls aren't
detected; `--simulate-call` still works.
