# Call Simulator (demo only)

A desktop app that fakes an incoming phone call on the **same laptop** as the
Dispel wizard. Pick a caller, the phone rings, you answer, and the caller's clip
plays while the wizard listens and gives its verdict. No second laptop,
BlackHole or real call needed (for a real Teams/FaceTime call, use `../caller/`).

How the wizard sees it: while a call is "connected" the app holds the
microphone (it never reads or records it), so the wizard's call detection lists
it as a call app (`tech.hocuspocus.callsim` in `app/native/callwatch.swift`) and
taps its audio for the usual 12 s check. **End** releases the mic, which ends the
call; the wizard's "end the call?" quits the app, like a real call app.

## Run (macOS, Node 22+)

```
cd demo/call-sim && npm install && npm start
```

`npm start` packages `out/Call Simulator-darwin-*/Call Simulator.app` and opens
it. It has to run packaged: `npm run dev` runs it as plain Electron, which the
wizard ignores (fine for UI work, useless for the demo). After the first build
you can open the .app from Finder or keep it in the Dock.

The app is just an iPhone floating on the desktop (a frameless, transparent
window). Drag it by its bezel or status bar; ⌘W or ⌘Q closes it.

1. Add clips (gitignored, never committed):
   - drag audio files onto the phone and drop them on **Drop as real** or
     **Drop as synthetic** (copied into `clips/real/` and `clips/synthetic/`), or
   - put files in those folders yourself (**Folder** on the Recents screen). The list updates on its own.
   - files directly in `clips/` have no answer key.

   The file name is the caller's name (`mom.wav` → "Mom"). WAV, MP3, M4A,
   AAC, FLAC, OGG, WebM or AIFF.
2. Start the wizard (`cd app && npm start`; restart it so it picks up the call
   simulator in its call list) and turn on **Check calls automatically** (or
   press ⌘⇧L once the call is up).
3. Tap a caller in Recents (or **Surprise**), then **Accept**. The first time, allow
   the microphone. The clip starts right away, so the 12 s listen hears it; use
   12 s or more of speech.
4. **Answers** reveals real/synthetic on the list and the call screen, so the
   key can stay hidden while the audience guesses.

Smoke test: `npm run smoke` (loads the window, checks the clip list, quits).
