// One-time OBS setup for the rig's video calls: `npm run setup-obs`.
// Builds, in the running OBS (WebSocket server on), from scenarios.local.json:
//   - an "Idle" scene (dark "camera off" card) shown between clips
//   - one scene per caller with `video.file`: that video as a muted Media
//     Source, fitted to the canvas, restarting each time the scene is shown
// then starts the Virtual Camera. Safe to re-run: existing scenes are reused
// and their video file is updated.
//
// The video is muted in OBS because the voice goes into the call through
// BlackHole (server.js), started together with the scene switch.

const path = require('node:path');
const { obsRequests } = require('./obs');
const { config, videoOf, ROOT } = require('./scenarios');

async function main() {
  if (!config.obs) throw new Error('scenarios.local.json has no "obs" section');
  const obs = (reqs) => obsRequests(config.obs, reqs);
  const [video] = await obs([['GetVideoSettings', {}]]);
  const W = video.baseWidth;
  const H = video.baseHeight;
  const fit = { positionX: 0, positionY: 0, alignment: 5, boundsType: 'OBS_BOUNDS_SCALE_INNER', boundsWidth: W, boundsHeight: H, boundsAlignment: 0 };

  // Idle: what the other side sees before and after a clip.
  const idle = config.obs.idleScene || 'Idle';
  await obs([
    ['CreateScene', { sceneName: idle }, { allowExisting: true }],
    ['CreateInput', { sceneName: idle, inputName: 'Idle background', inputKind: 'color_source_v3', inputSettings: { color: 0xff201c1c, width: W, height: H } }, { allowExisting: true }],
    ['CreateInput', { sceneName: idle, inputName: 'Idle text', inputKind: 'text_ft2_source_v2', inputSettings: { text: 'Camera off', font: { face: 'Helvetica', size: 64, style: 'Regular', flags: 0 }, color1: 0xffaaaaaa, color2: 0xffaaaaaa } }, { allowExisting: true }],
  ]);
  const [items] = await obs([['GetSceneItemList', { sceneName: idle }]]);
  const text = items.sceneItems.find((i) => i.sourceName === 'Idle text');
  if (text) {
    await obs([['SetSceneItemTransform', { sceneName: idle, sceneItemId: text.sceneItemId, sceneItemTransform: { positionX: W / 2, positionY: H / 2, alignment: 0 } }]]);
  }
  console.log(`✓ scene "${idle}"`);

  for (const c of config.callers || []) {
    const v = videoOf(c);
    if (!v) continue;
    const settings = {
      local_file: path.resolve(ROOT, v.file),
      is_local_file: true,
      looping: false,
      restart_on_activate: true,
      close_when_inactive: true,
      hw_decode: true,
    };
    const [, created] = await obs([
      ['CreateScene', { sceneName: v.scene }, { allowExisting: true }],
      ['CreateInput', { sceneName: v.scene, inputName: v.input, inputKind: 'ffmpeg_source', inputSettings: settings }, { allowExisting: true }],
    ]);
    const reqs = [
      ['SetInputSettings', { inputName: v.input, inputSettings: settings }],
      ['SetInputMute', { inputName: v.input, inputMuted: true }],
    ];
    const id = created?.sceneItemId ?? (await obs([['GetSceneItemId', { sceneName: v.scene, sourceName: v.input }]]))[0].sceneItemId;
    reqs.push(['SetSceneItemTransform', { sceneName: v.scene, sceneItemId: id, sceneItemTransform: fit }]);
    await obs(reqs);
    console.log(`✓ scene "${v.scene}" plays ${v.file}`);
  }

  const [cam] = await obs([['GetVirtualCamStatus', {}]]);
  await obs([['SetCurrentProgramScene', { sceneName: idle }], ...(cam.outputActive ? [] : [['StartVirtualCam', {}]])]);
  console.log('✓ Virtual Camera on. In FaceTime / Teams / Discord, pick "OBS Virtual Camera" as the camera.');
}

main().catch((err) => {
  console.error(`✗ ${err.message}`);
  process.exit(1);
});
