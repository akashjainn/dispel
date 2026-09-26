# Caller rig (demo only)

An iPhone remote that makes a prepared "caller" phone the judge's laptop on
Teams, FaceTime or Discord and speak a deepfake (or a real control clip). The
judge's laptop runs the Dispel wizard; they click **Listen** and see the verdict.

```
iPhone (Safari / home-screen app)  ──tap──▶  caller laptop: npm start
                                             ├─ opens the Teams / FaceTime call link
                                             ├─ plays the clip into BlackHole (the call app's mic)
                                             └─ switches OBS to the caller's video scene (optional)
                                                     │ a real call
                                                     ▼
                                             judge's laptop: Dispel wizard → Listen → verdict
```

This is a demo prop, not part of the product. It runs only on the caller
laptop and sends nothing anywhere except into the call you placed.

## Setup (caller laptop, macOS, Node 22+)

1. Install [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole)
   (`brew install blackhole-2ch`).
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

In OBS (28+), turn on Tools → WebSocket Server Settings (port 4455, and copy the
password into `obs.password`). Make an `Idle` scene (a still image or "camera
off" card) and one scene per video caller with a **Media Source** playing that
caller's deepfake video, muted, with "Restart playback when source becomes
active" on. Set `video.scene` and `video.input` (the media source's name) for
that caller. Tap a caller with **Video** checked and the scene switches and
restarts in sync with the audio, then goes back to `Idle` when the clip ends.

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

1. Judge's laptop: `cd app && npm start`, server configured in `config.local.json`.
2. Phone: pick Teams, tap **Call on Teams**; answer on the judge's laptop. The
   wizard pops up: "You're on a call in Microsoft Teams. Want me to listen?"
3. Phone: tap **Your boss**. On the judge's laptop, click **Listen** (or ⌘⇧L).
4. After about 12 s plus the server check, the wizard shows its verdict. A
   likely-synthetic call gets the purple ring, "end the call?", and "Notify my
   manager".
5. Phone: **Hang up**, then repeat with **Real voice (control)**.
