# web/: the Hocus Pocus website (https://hocuspocus.tech)

The desktop wizard's file check in a browser: drop or pick an audio file, the wizard (or witch) checks it on our
server and shows the verdict, then the evidence report (likelihood with the inconclusive band, per-window timeline,
what each technique found and how much it moved the score, channel note, transcript, what this can't tell you).
Click the character to switch between the 2D and 3D look. No call listening, no microphone.

- `index.html`, `style.css`, `app.js`: the page. Plain HTML/CSS/JS, no build step.
- Voice lines always play (no mute). They go through one reused audio element that the first tap unlocks, because iOS
  Safari blocks sound that starts after a network wait on a fresh element.
- The mascot is the app's own code and art, not a copy: Caddy serves `app/Assets/` at `/Assets/` and
  `app/src/renderer/{sprites,magic,voice,lessons}.js` at `/shared/`. Changing those in `app/` changes the site
  too (merges touching them redeploy it).
- Checks go to `POST /web/analyze` (same origin; no key, no history, a per-IP hourly limit: 300 on the server via compose.prod.yml; docs/INTERFACES.md).
  The file is sent to our server, checked in memory and deleted.

## Run it locally
```sh
cd server && uvicorn app.main:app --port 8765     # API (demo data without weights)
python web/dev_server.py                          # http://127.0.0.1:8080, same routes as Caddy
```

## Deploy
Merging to `main` deploys it (`.github/workflows/deploy.yml`). Routes: `docker/remote-deploy.sh` (Caddyfile),
mounts: `docker/compose.prod.yml`.
