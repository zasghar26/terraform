(() => {
  // UI: add a checkbox next to your buttons
  const row = document.querySelector('.btns');
  if (!row) return;
  const label = document.createElement('label');
  label.style.display = 'flex';
  label.style.alignItems = 'center';
  label.style.gap = '6px';
  label.style.fontSize = '14px';
  label.style.userSelect = 'none';
  label.innerHTML = `<input id="auto-fetch" type="checkbox"> Auto-fetch from Chat`;
  row.appendChild(label);

  const textarea = document.getElementById('tf-code');
  const statusEl = document.getElementById('deploy-status');

  let timer = null;
  let lastTs = 0;

  async function tick() {
    try {
      const r = await fetch('/agent/latest', { method: 'GET' });
      const data = await r.json();
      if (!r.ok) return;
      // Only update when a *newer* snippet arrives
      if (data && data.code && typeof data.ts === 'number' && data.ts > lastTs) {
        textarea.value = data.code;
        lastTs = data.ts;
        if (statusEl) statusEl.textContent = 'Loaded code from chat.';
      }
    } catch { /* ignore */ }
  }

  document.getElementById('auto-fetch').addEventListener('change', (e) => {
    if (e.target.checked) {
      tick();                       // fetch immediately
      timer = setInterval(tick, 3000); // then poll every 3s
    } else {
      clearInterval(timer);
      timer = null;
    }
  });
})();
