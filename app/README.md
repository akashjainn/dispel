# Dispel wizard (desktop app)

A menu-bar wizard that tells you whether a voice is likely synthetic.

```
npm install
npm start                      # wizard appears; click the menu-bar icon to hide or summon it
npm start -- --simulate-call   # runs the call flow with a fake call window (real calls are ignored);
                               # "Listen" then records system audio, so play a clip to test
```

- **Check a file:** drop an audio file on the wizard or on the menu-bar icon,
  or click the wizard to pick a file. The wizard answers with a verdict and a score.
- **Calls (macOS 14.2+):** when Zoom, FaceTime, Teams, Discord, Slack or a
  browser is using the mic, a small grayed-out wizard sits in the call window's
  bottom-right corner. It's click-through, so the call's buttons under it
  still work. The warning bubble (which has buttons) opens in the top-right
  corner instead, away from the End button. The wizard and the colored outline hide while another app
  is in front and come back when you return to the call.
- **Checking calls:** on the first call, the wizard asks once, "Check my calls
  automatically?" After **Yes, always**, every call is checked as it starts;
  after **Only when I ask**, use tray → "Listen to this call" or ⌘⇧L during a
  call. Change it in Settings. A check records 12 s of what the call app
  plays (the other person, not your mic), sends the clip to our server, and
  deletes it. The first time, macOS asks to allow **System Audio Recording**; if
  it's denied, the wizard says it couldn't hear anything. If the voice scores likely real, the call
  window gets a steady green outline and the wizard stays small and gray. If
  the call is flagged, it comes out in full color, the
  call window gets a purple outline, and a speech bubble asks whether to end the
  call. "Yes, hang up" quits Zoom, FaceTime, Teams, Discord or Slack (like ⌘Q);
  for a browser call it asks you to close the tab instead. Turn call watching
  off with "Watch calls" in the tray menu (right-click the icon).
- **Notify someone:** on a flagged call, the warning bubble has "Notify
  trusted contact" (Personal) or "Notify my manager" (Work). It texts that
  person from your Mac's Messages app, only when you press it. Set Personal or
  Work, the contact's name and number (or iMessage email), and send a test
  text in Settings (tray menu or right-click the wizard → Settings…). The first
  text makes macOS ask to let Dispel control Messages. Settings are saved in
  `~/Library/Application Support/dispel-wizard/settings.json`.
- **Learn:** the wizard explains what a deepfake is, common deepfake scams, and
  how to protect yourself and your family (safe word, call back, slow down,
  where to report). Open it from the tray menu, by right-clicking the wizard, or
  with "How do these scams work?" after a file check. Text: `src/renderer/lessons.js`.
- **Demo calls:** `demo/caller/` makes a second laptop call this one and play a
  prepared deepfake on a tap from an iPhone. See its README.
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

Tray menu → **Results from** picks where scores come from:
- **Server** (default): files are uploaded to the server in
  `config.local.json`, and so are the 12 s call clips. Until the model
  weights are on the server, its answers are demo data (`mock: true`, about
  70% likely synthetic), and the bubble says so.
- **Mock: likely real** (2–14%) or **Mock: likely synthetic** (86–98%): local
  fixed answers for demos, after a 2.5 s (file) or 3.5 s (call) pause. Nothing
  is recorded or uploaded. Start
  with one using `DISPEL_RESULTS=real npm start` or `DISPEL_RESULTS=synthetic`.

## Layout

| Path | What |
|---|---|
| `src/main/main.js` | tray, windows, the file and call flows |
| `src/main/analyzer.js` | `POST /analyze` for files and call clips; local mock when picked in the tray |
| `src/main/config.js` | server URL and key, and the anonymous install id |
| `src/main/callwatch.js` | runs the Swift helper and emits call start, move and end |
| `native/callwatch.swift` | asks Core Audio which apps are using the mic, and finds their window |
| `src/main/callcapture.js`, `native/callcapture.swift` | on "Listen": records 12 s of the call app's output (Core Audio process tap) to a temp WAV |
| `src/renderer/` | wizard page (sprites, speech bubble) and the purple overlay |
| `Assets/` | sprite sheets (80×128 frames, drawn at 2×) |

`npm start` builds `bin/callwatch` and `bin/callcapture` with `swiftc`, which needs the Xcode
command line tools. Without it the app still runs, but real calls aren't
detected; `--simulate-call` still works.
