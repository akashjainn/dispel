// The demo's pretend call window: a running timer, and the red button hangs
// up (closing the window ends the simulated call; see main.js).

const started = Date.now();
const timer = document.getElementById('timer');
setInterval(() => {
  const s = Math.floor((Date.now() - started) / 1000);
  timer.textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}, 500);

document.getElementById('hangup').addEventListener('click', () => window.close());
