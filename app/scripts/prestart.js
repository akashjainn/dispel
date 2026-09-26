// Builds the macOS call watcher before `npm start`. Skips quietly elsewhere;
// the app still runs without it (file checks and "Simulate call" work).
const { execSync } = require('node:child_process');

if (process.platform !== 'darwin') process.exit(0);
try {
  execSync('npm run build:callwatch', { stdio: 'inherit' });
} catch {
  console.warn('[prestart] could not build callwatch; call detection is off. Needs Xcode command line tools.');
}
