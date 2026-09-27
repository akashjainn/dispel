// Packages "Call Simulator.app" with its own bundle ID (tech.hocuspocus.callsim),
// which the wizard's callwatch lists as a call app. `electron .` would run as
// com.github.Electron, which the wizard ignores. `--open` launches it afterwards.
//
// Usage: node build.js [--open]

const { packager } = require('@electron/packager');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const NAME = 'Call Simulator';

(async () => {
  if (process.platform !== 'darwin') {
    console.error('The call simulator is macOS only (the wizard\'s call detection is).');
    process.exit(1);
  }
  const [dir] = await packager({
    dir: __dirname,
    name: NAME,
    appBundleId: 'tech.hocuspocus.callsim',
    platform: 'darwin',
    arch: process.arch,
    out: path.join(__dirname, 'out'),
    overwrite: true,
    prune: true,
    ignore: [/^\/out($|\/)/, /^\/clips($|\/)/, /^\/build\.js$/, /^\/README\.md$/],
    extendInfo: {
      NSMicrophoneUsageDescription:
        'Holding the mic during a simulated call is how the Dispel wizard knows a call is on. Nothing is recorded.',
    },
  });
  const appPath = path.join(dir, `${NAME}.app`);
  // Ad-hoc sign: the plist edits break Electron's signature, and Apple Silicon won't run unsigned code.
  execFileSync('codesign', ['--force', '--deep', '--sign', '-', appPath], { stdio: 'inherit' });
  console.log(`Built ${path.relative(process.cwd(), appPath)}`);
  if (process.argv.includes('--open')) {
    // `open` hands our environment to the app; VS Code's ELECTRON_RUN_AS_NODE would start it as plain Node.
    const { ELECTRON_RUN_AS_NODE, ...env } = process.env;
    execFileSync('open', [appPath], { env });
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
