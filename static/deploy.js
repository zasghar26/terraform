(() => {
    const BASE_URL =
        document.querySelector('meta[name="app-base-url"]')?.content?.trim() ||
        window.location.origin;

    const form = document.getElementById('deploy-form');
    const textarea = document.getElementById('tf-code');
    const statusEl = document.getElementById('deploy-status');

    function setStatus(msg) {
        statusEl.textContent = msg;
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const code = (textarea.value || '').trim();
        if (!code) {
            setStatus('Please paste Terraform code before deploying.');
            return;
        }

        setStatus('Deploying… this may take a moment.');

        try {
            // Use FormData so you don’t need to change your current backend
            const body = new FormData();
            body.append('tf_code', code);

            const res = await fetch(`${BASE_URL}/trigger-deploy`, {
                method: 'POST',
                body
            });

            // Try to parse JSON, but don’t crash if it isn’t JSON
            let data = null;
            try {
                data = await res.json();
            } catch (_) {}

            if (!res.ok) {
                const msg =
                    (data && (data.error || data.message)) ||
                    `HTTP ${res.status} ${res.statusText}`;
                throw new Error(msg);
            }

            const status = (data && (data.status || data.result || 'success')) || 'success';
            const message = (data && (data.message || data.detail)) || 'Deployment triggered.';
            setStatus(`✅ ${status}: ${message}`);
        } catch (err) {
            setStatus(`❌ Deployment failed: ${err.message}`);
        }
    });
})();
