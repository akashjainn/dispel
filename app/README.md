# Dispel wizard (desktop app)

A menu-bar wizard that tells you whether a voice is likely synthetic.

```
npm install
npm start                      # wizard appears; click the menu-bar icon to hide or summon it
npm start -- --simulate-call   # also runs the call flow with a fake call window
```

- **Check a file:** drop an audio file on the wizard or on the menu-bar icon,
  or click the wizard to pick a file. The wizard answers with a verdict and a score.
- **Calls (macOS 14.2+):** when Zoom, FaceTime, Teams, Discord, Slack or a
  browser is using the mic, the wizard sits grayed out in the call window's
  bottom-right corner. If the call is flagged, it comes out in full color, the
  call window gets a purple outline, and a speech bubble asks whether to end the
  call. "Yes, hang up" quits Zoom, FaceTime, Teams, Discord or Slack (like ⌘Q);
  for a browser call it asks you to close the tab instead. Turn call watching
  off with "Watch calls" in the tray menu (right-click the icon).
- **Log:** every result is appended to
  `~/Library/Application Support/dispel-wizard/results.jsonl` (score, verdict,
  file name or call app; never audio). Tray menu → "Open results log".

**Right now every score is a mock** (`src/main/analyzer.js`): it waits 2.5 s
for a file or 3.5 s for a call, then reports "likely synthetic". No audio is
captured or read.

## Layout

| Path | What |
|---|---|
| `src/main/main.js` | tray, windows, the file and call flows |
| `src/main/analyzer.js` | mock AnalyzeResponse; swap it for `POST /analyze` |
| `src/main/callwatch.js` | runs the Swift helper and emits call start, move and end |
| `native/callwatch.swift` | asks Core Audio which apps are using the mic, and finds their window |
| `src/renderer/` | wizard page (sprites, speech bubble) and the purple overlay |
| `Assets/` | sprite sheets (80×128 frames, drawn at 2×) |

`npm start` builds `bin/callwatch` with `swiftc`, which needs the Xcode
command line tools. Without it the app still runs, but real calls aren't
detected; `--simulate-call` still works.
