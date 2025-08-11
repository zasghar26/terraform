(() => {
    const BASE_URL =
        document.querySelector('meta[name="app-base-url"]')?.content?.trim() ||
        window.location.origin;

    const form = document.getElementById('deploy-form');
    const textarea = document.getElementById('tf-code');
    const statusEl = document.getElementById('deploy-status');

    const setStatus = (msg) => {
        statusEl.textContent = msg;
    };

    async function pollStatus(url, maxMs = 10 * 60 * 1000, intervalMs = 2000) {
        const start = Date.now();
        while (Date.now() - start < maxMs) {
            const r = await fetch(url, { method: 'GET' });
            let data = null;
            try {
                data = await r.json();
            } catch {}
            if (r.ok && data) {
                if (data.status === 'done') return data;
                if (data.status === 'error')
                    throw new Error(data.details || data.message || 'deployment failed');
                // pending/running → continue
            }
            await new Promise((res) => setTimeout(res, intervalMs));
        }
        throw new Error('Timed out waiting for deployment status');
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const code = (textarea.value || '').trim();
        if (!code)
            return setStatus('Please paste Terraform code before deploying.');

        setStatus('Submitting deployment…');

        try {
            const body = new FormData();
            body.append('tf_code', code);

            const res = await fetch(`${BASE_URL}/trigger-deploy`, {
                method: 'POST',
                body,
            });
            let data = null;
            try {
                data = await res.json();
            } catch {}
            if (res.status !== 202 || !data?.status_url) {
                const msg =
                    (data && (data.error || data.message)) ||
                    `HTTP ${res.status} ${res.statusText}`;
                throw new Error(msg);
            }

            setStatus('Deployment started… tracking progress.');
            const final = await pollStatus(data.status_url);
            setStatus(`✅ ${final.message || 'Deployment completed.'}`);
        } catch (err) {
            setStatus(`❌ Deployment failed: ${err.message}`);
        }
    });
})();
