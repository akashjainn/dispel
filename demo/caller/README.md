# Caller rig (demo only)

An iPhone remote that makes a prepared "caller" phone the judge's laptop on
Teams, FaceTime or Discord and speak a deepfake (or a real control clip). The
judge's laptop runs the Dispel wizard, which checks the call as it starts and shows the verdict.

```
iPhone (Safari / home-screen app)  ──tap──▶  caller laptop: npm start
                                             ├─ opens the Teams / FaceTime call link
                                             ├─ plays the clip into BlackHole (the call app's mic)
                                             └─ switches OBS to the caller's video scene (optional)
                                                     │ a real call
                                                     ▼
                                             judge's laptop: Dispel wizard listens 12 s → verdict
```

This is a demo prop, not part of the product. It runs only on the caller
laptop and sends nothing anywhere except into the call you placed.

## Setup (caller laptop, macOS, Node 22+)

1. Install [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole)
   (`brew install blackhole-2ch`), then reboot (or `sudo killall coreaudiod`)
   so macOS loads it. If a tap on the phone says "no output device named
   BlackHole 2ch", this step didn't take.
2. In Teams, FaceTime and Discord on the caller laptop, set the **microphone to
   "BlackHole 2ch"**. For video, install OBS, set its scenes up (below), click
   **Start Virtual Camera**, and set each app's camera to **OBS Virtual Camera**.
3. `cp scenarios.example.json scenarios.local.json`, then fill it in:
   - `dial` / `dialVideo`: who to call. Teams uses
     `msteams:/l/call/0/0?users=<judge's Teams account>`; FaceTime uses
     `facetime-audio://<Apple ID email or phone>` (audio) or `facetime://…` (video).
     Discord has no call link: start that call by hand.
   - `app`: the app name that "Hang up" quits (like ⌘Q).
   - `callers[]`: one button per clip. `audio` is a path under `clips/`.
   - `monitor: true` also plays the clip on the caller laptop's speakers.
   - Remove `obs` if you aren't doing video.
4. Put the clips in `clips/` (gitignored). WAV, AIFF, M4A or MP3.
5. `npm start`. It builds `bin/playto` (Xcode command line tools) and prints a
   URL with a token. Open it on the iPhone, then Share → **Add to Home Screen**.

The phone and the caller laptop must reach each other. Hackathon Wi-Fi often
blocks device-to-device traffic, so put the laptop on the **iPhone's hotspot**.

## Video (optional)

The caller's video goes to the other side through **OBS Virtual Camera**; its
voice goes through BlackHole, started at the same moment.

1. Give the caller a `video` in `scenarios.local.json`, and extract its audio
   track as the caller's `audio` (the rig plays the voice separately):
   ```
   afconvert -f WAVE -d LEI16@48000 -c 1 clips/boss.mov clips/boss.wav
   ```
   ```json
   "video": { "file": "clips/boss.mov", "scene": "Boss", "input": "Boss video" }
   ```
   `scene` and `input` are optional (default: the caller's label).
2. Open OBS (28+) → Tools → **WebSocket Server Settings** → Enable, port 4455.
   Leave `obs.password` out of the config: the rig reads OBS's own password
   from this Mac's OBS settings.
3. `npm run setup-obs`. It creates an `Idle` scene ("Camera off" card) and one
   scene per video caller (the video muted, fitted to the canvas, restarting
   each time it's shown), then starts the Virtual Camera. Safe to re-run.
4. In FaceTime / Teams / Discord on the caller laptop, set the camera to
   **OBS Virtual Camera**.

On the phone, tick **Video** and tap the caller: OBS switches to their scene and
restarts the video as the voice starts, then goes back to `Idle` when it ends.

Our detector is audio-only. The video is there so the judges can see what a
convincing call looks like; don't claim Dispel checks the video.

## Choosing clips

- **Include a real control clip.** The wizard staying calm on a real voice is
  half the demo.
- **Use consented voices.** Clone a teammate who agrees (the "boss"). For a
  public figure, use a clip from a published deepfake dataset under its
  license, not a new one you generated: TTS vendors ban cloning politicians,
  and the judges include the NSA.
- **Test every clip over the real call path first.** Call codecs lower
  reliability, and cloned voices of real people on ordinary mics are our known
  weak spot (AGENTS.md). Keep only clips that score reliably through the call.
  Aim for 12 s or more of speech: the wizard listens for 12 s.

## Demo run

1. Before the demo, on the judge's laptop: `cd app && npm start` with the server
   in `config.local.json`. Make one test call and answer **Yes, always** to
   "Check my calls automatically?" (or tick it in Settings). It never asks again.
2. Phone: pick Teams, tap **Call on Teams**; answer on the judge's laptop.
3. **Right after the call connects**, tap **Your boss** on the phone. The wizard
   starts its 12 s listen as soon as the call is detected, so the clip must be
   playing then. If you're late, press ⌘⇧L on the judge's laptop (or "Listen
   again") to check once more.
4. After the 12 s plus the server check, the wizard shows its verdict. A
   likely-synthetic call gets the purple ring, "end the call?", and "Notify my
   manager".
5. Phone: **Hang up**, then repeat with **Real voice (control)**.
