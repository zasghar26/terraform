from flask import Flask, request, jsonify
from flask_cors import CORS
import os, subprocess, uuid, shutil, threading, tempfile, requests, html, time

app = Flask(__name__)
CORS(app)

# ===== Security headers (CSP) =====
# Allow our own JS + the agent widget to load and connect.
WIDGET_HOSTS = "https://sofmaucktvjaphia4c424wki.agents.do-ai.run https://*.do-ai.run"

@app.after_request
def add_security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'unsafe-inline' {WIDGET_HOSTS}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        f"connect-src 'self' {WIDGET_HOSTS}; "
        f"frame-src {WIDGET_HOSTS}; "
        "font-src 'self' data:;"
    )
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp

# ===== In-memory stores =====
JOBS = {}
LATEST_FROM_AGENT = {"code": "", "ts": 0}

AGENT_PUSH_SECRET = os.environ.get("AGENT_PUSH_SECRET")  # set this in DO App Platform

# ===== UI =====
@app.get("/")
def index():
    # Use only relative URLs on the frontend so scheme matches the page (fixes CSP "connect-src 'self'")
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>TerraformGen</title>
      <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px; }}
        h2 {{ margin: 0 0 8px; }}
        .wrap {{ max-width: 900px; }}
        label {{ display:block; margin: 12px 0 6px; font-weight: 600; }}
        input, textarea {{ width: 100%; padding: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
        button {{ padding: 10px 14px; cursor: pointer; }}
        .code-area {{ min-height: 360px; }}
        .status {{ margin-top: 12px; }}
        .hint {{ color: #666; font-size: 13px; }}
        .btns {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }}
      </style>
    </head>
    <body>
      <h2>TerraformGen</h2>
      <p class="hint">Paste Terraform code, set your token, and click Deploy — or click <i>Fetch from Chat</i> to pull the last snippet your agent sent.</p>

      <div class="wrap">
        <form id="deploy-form">
          <label for="do-token">DigitalOcean API Token</label>
          <input id="do-token" name="do_token" type="password" autocomplete="off" placeholder="dop_v1_..." required />

          <label for="tf-code">Terraform Configuration</label>
          <textarea id="tf-code" name="tf_code" class="code-area" placeholder="Paste your Terraform code here..." required></textarea>

          <div class="btns">
            <button type="submit">🚀 Deploy</button>
            <button id="download-btn" type="button">Download .tf</button>
          </div>
        </form>

        <div id="deploy-status" class="status"></div>
      </div>

      <!-- Agent widget -->
      <script async
        src="https://sofmaucktvjaphia4c424wki.agents.do-ai.run/static/chatbot/widget.js"
        data-agent-id="c9344a89-6be3-11f0-bf8f-4e013e2ddde4"
        data-chatbot-id="pzXfg1TbVl2Toyr_B2FPnMAtMgHaZZZZ"
        data-name="agent-07282025 Chatbot"
        data-primary-color="#031B4E"
        data-secondary-color="#E5E8ED"
        data-button-background-color="#0061EB"
        data-starting-message="Hello! How can I help you today?"
        data-logo="/static/chatbot/icons/default-agent.svg">
      </script>

      <script src="/static/deploy.js"></script>

      <!-- Helpers + postMessage bridge + fetch logger -->
      <script>
        document.getElementById('download-btn').addEventListener('click', () => {{
          const code = document.getElementById('tf-code').value || '';
          const blob = new Blob([code], {{ type: 'text/plain' }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = 'main.tf'; a.click();
          URL.revokeObjectURL(url);
        }});
        function isAllowedAgentOrigin(origin) {{
          try {{ return /\\.do-ai\\.run$/.test(new URL(origin).host); }}
          catch {{ return false; }}
        }}
        window.addEventListener('message', (event) => {{
          if (!isAllowedAgentOrigin(event.origin)) return;
          const data = event.data || {{}};
          if ((data.type === 'agent:terraform' || data.type === 'agent:terraform:deploy') && typeof data.code === 'string') {{
            if (typeof window.useTerraformFromChat === 'function') {{
              window.useTerraformFromChat(data.code);
            }} else {{
              const ta = document.getElementById('tf-code');
              ta.value = data.code;
              document.getElementById('deploy-form').scrollIntoView({{ behavior: 'smooth' }});
            }}
            if (data.type === 'agent:terraform:deploy') {{
              document.getElementById('deploy-form').dispatchEvent(new Event('submit', {{ cancelable: true, bubbles: true }}));
            }}
          }}
        }});

        // Simple fetch logger to surface network issues in console
        (function(){{
          const _fetch = window.fetch;
          window.fetch = async function(input, init){{
            try {{
              const res = await _fetch(input, init);
              if (!res.ok) console.warn('[deploy-debug] fetch', input, '->', res.status, res.statusText);
              return res;
            }} catch (e) {{
              console.error('[deploy-debug] fetch error', input, e);
              throw e;
            }}
          }};
        }})();
      </script>
    </body>
    </html>
    """

# ===== Helpers =====
def check_do_droplet_quota(token: str) -> dict:
    headers = { "Authorization": f"Bearer {token}" }
    acc = requests.get("https://api.digitalocean.com/v2/account", headers=headers, timeout=20)
    acc.raise_for_status()
    limit = acc.json().get("account", {}).get("droplet_limit", 0)
    total = 0
    url = "https://api.digitalocean.com/v2/droplets?per_page=200"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        total += len(data.get("droplets", []))
        url = data.get("links", {}).get("pages", {}).get("next")
    if total >= limit:
        return { "ok": False, "reason": f"Droplet limit reached ({total}/{limit})." }
    return { "ok": True, "usage": total, "limit": limit }

def ensure_provider_file(tf_code: str, workdir: str):
    if 'provider "digitalocean"' in tf_code:
        return
    with open(os.path.join(workdir, "provider.tf"), "w", encoding="utf-8") as f:
        f.write('provider "digitalocean" {}\n')

def run_terraform_apply(tf_code: str, do_token: str) -> dict:
    workdir = tempfile.mkdtemp(prefix="tfjob-")
    try:
        main_tf = os.path.join(workdir, "main.tf")
        with open(main_tf, "w", encoding="utf-8") as f:
            f.write(tf_code)

        ensure_provider_file(tf_code, workdir)

        env = os.environ.copy()
        env["DIGITALOCEAN_TOKEN"] = do_token
        env["DIGITALOCEAN_ACCESS_TOKEN"] = do_token

        init_res = subprocess.run(
            ["terraform", "init", "-no-color", "-input=false"],
            check=False, text=True, capture_output=True, cwd=workdir, env=env
        )
        if init_res.returncode != 0:
            return { "error": "Terraform init failed", "details": (init_res.stderr or init_res.stdout) }

        apply_res = subprocess.run(
            ["terraform", "apply", "-auto-approve", "-no-color", "-input=false"],
            check=False, text=True, capture_output=True, cwd=workdir, env=env
        )
        if apply_res.returncode != 0:
            return { "error": "Terraform apply failed", "details": (apply_res.stderr or apply_res.stdout) }

        summary = ""
        for line in (apply_res.stdout or "").splitlines():
            if line.strip().startswith("Apply complete!"):
                summary = line.strip()
                break
        return { "message": summary or "Apply complete." }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

def _parse_payload():
    tf_code = ""
    do_token = ""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        tf_code = (data.get("code") or data.get("tf_code") or "").strip()
        do_token = (data.get("do_token") or "").strip()
    else:
        tf_code = (request.form.get("tf_code") or "").strip()
        do_token = (request.form.get("do_token") or "").strip()
    return tf_code, do_token

# ===== API =====
@app.post("/trigger-deploy")
def trigger_deploy():
    tf_code, do_token = _parse_payload()
    if not do_token:
        return jsonify({ "status": "error", "message": "DigitalOcean token is required" }), 400
    if not tf_code:
        return jsonify({ "status": "error", "message": "Terraform code is empty" }), 400

    try:
        q = check_do_droplet_quota(do_token)
        if not q.get("ok"):
            return jsonify({ "status": "error", "message": q.get("reason", "Quota check failed") }), 400
    except Exception:
        pass

    job_id = str(uuid.uuid4())
    JOBS[job_id] = { "status": "pending", "message": "Queued" }

    def worker():
        JOBS[job_id] = { "status": "running", "message": "Running terraform…" }
        try:
            result = run_terraform_apply(tf_code, do_token)
            if "error" in result:
                JOBS[job_id] = { "status": "error", "message": result["error"], "details": result.get("details", "") }
            else:
                JOBS[job_id] = { "status": "done", "message": result.get("message", "Done") }
        except Exception as e:
            JOBS[job_id] = { "status": "error", "message": "Unhandled server error", "details": str(e) }

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({ "status": "accepted", "job_id": job_id, "status_url": f"/jobs/{job_id}" }), 202

@app.get("/jobs/<job_id>")
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({ "error": "job not found" }), 404
    return jsonify(job), 200

# ===== Webhooks for the agent =====
def _agent_auth_ok(req_json):
    # Accept header or field. Require env var if set.
    provided = request.headers.get("X-Agent-Secret") or (req_json or {}).get("secret")
    if AGENT_PUSH_SECRET:  # if configured, enforce it
        return provided == AGENT_PUSH_SECRET
    return True  # if not configured, allow (dev only)

@app.post("/agent/push")
def agent_push():
    """Agent sends: { "code": "<HCL>", "deploy": false } with X-Agent-Secret header."""
    payload = request.get_json(silent=True) or {}
    if not _agent_auth_ok(payload):
        return jsonify({"error": "unauthorized"}), 401
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"error": "missing code"}), 400

    # Save latest for the UI button to fetch
    LATEST_FROM_AGENT["code"] = code
    LATEST_FROM_AGENT["ts"] = int(time.time())

    # Optional: deploy immediately if requested
    if bool(payload.get("deploy")):
        do_token = (payload.get("do_token") or "").strip()
        if not do_token:
            return jsonify({"error": "deploy requested but no do_token provided"}), 400
        job_id = str(uuid.uuid4())
        JOBS[job_id] = {"status": "pending", "message": "Queued by agent"}
        def worker():
            JOBS[job_id] = {"status": "running", "message": "Running terraform…"}
            try:
                result = run_terraform_apply(code, do_token)
                if "error" in result:
                    JOBS[job_id] = {"status": "error", "message": result["error"], "details": result.get("details", "")}
                else:
                    JOBS[job_id] = {"status": "done", "message": result.get("message", "Done")}
            except Exception as e:
                JOBS[job_id] = {"status": "error", "message": "Unhandled server error", "details": str(e)}
        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"ok": True, "job_id": job_id, "status_url": f"/jobs/{job_id}"}), 202

    return jsonify({"ok": True, "stored": True, "ts": LATEST_FROM_AGENT["ts"]})

@app.get("/agent/latest")
def agent_latest():
    """UI calls this to get the last code pushed by the agent."""
    return jsonify({"code": LATEST_FROM_AGENT["code"], "ts": LATEST_FROM_AGENT["ts"]})

@app.get("/healthz")
def health():
    return jsonify({"ok": True}), 200

@app.errorhandler(500)
def on_500(err):
    return jsonify({"status": "error", "message": "Internal Server Error", "details": str(err)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
