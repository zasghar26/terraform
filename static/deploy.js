(() => {
  const BASE_URL =
    document.querySelector('meta[name="app-base-url"]')?.content?.trim() ||
    window.location.origin;

  const form = document.getElementById('deploy-form');
  const textarea = document.getElementById('tf-code');
  const tokenInput = document.getElementById('do-token');
  const statusEl = document.getElementById('deploy-status');

  const setStatus = (msg) => { statusEl.textContent = msg; };

  async function pollStatus(url, maxMs = 10 * 60 * 1000, intervalMs = 2000) {
    const start = Date.now();
    while (Date.now() - start < maxMs) {
      const r = await fetch(url, { method: 'GET' });
      let data = null; try { data = await r.json(); } catch {}
      if (r.ok && data) {
        if (data.status === 'done') return data;
        if (data.status === 'error') throw new Error(data.details || data.message || 'deployment failed');
      }
      await new Promise(res => setTimeout(res, intervalMs));
    }
    throw new Error('Timed out waiting for deployment status');
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const code = textarea.value.trim();
    const token = tokenInput.value.trim();
    if (!code) { setStatus('Terraform code is empty.'); return; }
    if (!token) { setStatus('DigitalOcean token is required.'); return; }

    setStatus('Submitting deployment...');
    try {
      const r = await fetch('/trigger-deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body: new URLSearchParams({ tf_code: code, do_token: token })
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || 'submission failed');

      const statusUrl = data.status_url.startsWith('http')
        ? data.status_url
        : `${BASE_URL}${data.status_url}`;

      setStatus('Deployment started… tracking progress.');
      const final = await pollStatus(statusUrl);
      setStatus(`✅ ${final.message || 'Deployment completed.'}`);
    } catch (err) {
      setStatus(`❌ Deployment failed: ${err.message}`);
    }
  });

  // Bridge function your chat button can call:
  // window.useTerraformFromChat(codeString)
  window.useTerraformFromChat = function (code) {
    if (typeof code !== 'string') return;
    textarea.value = code;
    document.getElementById('deploy-form').scrollIntoView({ behavior: 'smooth' });
  };
})();
