// Builds the macOS helpers before `npm start`. Skips quietly elsewhere; the
// app still runs without them (file checks and "Simulate call" work).
const { execSync } = require('node:child_process');

if (process.platform !== 'darwin') process.exit(0);
for (const [script, what] of [
  ['build:callwatch', 'call detection is off'],
  ['build:callcapture', 'the wizard can’t listen to calls'],
]) {
  try {
    execSync(`npm run ${script}`, { stdio: 'inherit' });
  } catch {
    console.warn(`[prestart] ${script} failed, so ${what}. Needs Xcode command line tools.`);
  }
}
