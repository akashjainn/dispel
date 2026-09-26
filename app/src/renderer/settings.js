// Settings window: personal vs work, and who "Notify" texts.
const $ = (id) => document.getElementById(id);

const COPY = {
  personal: {
    heading: 'Trusted contact',
    hint: 'On a flagged call, the wizard offers “Notify trusted contact”.',
    name: 'Mom',
  },
  business: {
    heading: 'Manager',
    hint: 'On a flagged call, the wizard offers “Notify my manager”.',
    name: 'Jordan (IT security)',
  },
};

const mode = () => document.querySelector('input[name="mode"]:checked')?.value ?? 'personal';
const current = () => ({ mode: mode(), contact: { name: $('name').value, handle: $('handle').value } });

function showMode() {
  const c = COPY[mode()];
  $('contact-heading').textContent = c.heading;
  $('mode-hint').textContent = c.hint;
  $('name').placeholder = c.name;
}

function status(text, kind = '') {
  $('status').textContent = text;
  $('status').className = `status ${kind}`;
}

async function save() {
  const res = await window.settings.save(current());
  if (!res.ok) status(res.error, 'bad');
  return res.ok;
}

document.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener('change', showMode));

$('save').addEventListener('click', async () => {
  if (await save()) status('Saved.', 'ok');
});

$('test').addEventListener('click', async () => {
  if (!(await save())) return;
  $('test').disabled = true;
  status('Sending…');
  const res = await window.settings.sendTest();
  $('test').disabled = false;
  if (res.ok) status('Test text sent. Check that it arrived.', 'ok');
  else status(res.error, 'bad');
});

window.settings.get().then((s) => {
  document.querySelector(`input[name="mode"][value="${s.mode}"]`).checked = true;
  $('name').value = s.contact.name;
  $('handle').value = s.contact.handle;
  showMode();
});
