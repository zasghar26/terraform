from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import os
import subprocess
import uuid
import shutil
import threading
import tempfile
import requests
import html

app = Flask(__name__)
CORS(app)

# In-memory job store (simple for single-instance)
# {job_id: {"status": "pending|running|done|error", "message": str, "details": str}}
JOBS = {}

# ---------- UI ----------
@app.get("/")
def index():
    base_url = request.host_url.rstrip("/")
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>TerraformGen</title>
      <meta name="app-base-url" content="{html.escape(base_url)}">
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
        .row {{ display:flex; gap:18px; align-items:center; }}
      </style>
    </head>
    <body>
      <h2>TerraformGen</h2>
      <p class="hint">Paste Terraform code, set your token, and click Deploy. You can also fill this textarea from your chat UI button.</p>

      <div class="wrap">
        <form id="deploy-form">
          <label for="do-token">DigitalOcean API Token</label>
          <input id="do-token" name="do_token" type="password" autocomplete="off" placeholder="dop_v1_..." required />

          <label for="tf-code">Terraform Configuration</label>
          <textarea id="tf-code" name="tf_code" class="code-area" placeholder="Paste your Terraform code here..." required></textarea>

          <div style="margin-top:12px;">
            <button type="submit">🚀 Deploy</button>
            <button id="download-btn" type="button">Download .tf</button>
            <button id="copy-btn" type="button">Copy</button>
          </div>
        </form>

        <div id="deploy-status" class="status"></div>
      </div>

      <script src="/static/deploy.js"></script>
      <script>
        // Optional small helpers for the page itself
        document.getElementById('download-btn').addEventListener('click', () => {{
          const code = document.getElementById('tf-code').value || '';
          const blob = new Blob([code], {{ type: 'text/plain' }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = 'main.tf'; a.click();
          URL.revokeObjectURL(url);
        }});
        document.getElementById('copy-btn').addEventListener('click', async () => {{
          const code = document.getElementById('tf-code').value || '';
          await navigator.clipboard.writeText(code);
          alert('Copied to clipboard');
        }});
      </script>
    </body>
    </html>
    """

# ---------- Helpers ----------
def check_do_droplet_quota(token: str) -> dict:
    """Return { ok: bool, usage:int, limit:int } or { ok: False, reason:str }."""
    headers = { "Authorization": f"Bearer {token}" }
    # Account limit
    acc = requests.get("https://api.digitalocean.com/v2/account", headers=headers, timeout=20)
    acc.raise_for_status()
    limit = acc.json().get("account", {}).get("droplet_limit", 0)

    # Count droplets (paginate)
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
    # Inject minimal provider block only if no DigitalOcean provider is present.
    if 'provider "digitalocean"' in tf_code:
        return
    with open(os.path.join(workdir, "provider.tf"), "w", encoding="utf-8") as f:
        f.write('provider "digitalocean" {}\n')

def run_terraform_apply(tf_code: str, do_token: str) -> dict:
    """Run terraform init/apply in a temp dir; always cleans up; return result dict."""
    workdir = tempfile.mkdtemp(prefix="tfjob-")
    try:
        # Write user's Terraform
        main_tf = os.path.join(workdir, "main.tf")
        with open(main_tf, "w", encoding="utf-8") as f:
            f.write(tf_code)

        ensure_provider_file(tf_code, workdir)

        # Prepare environment with the user-supplied token
        env = os.environ.copy()
        env["DIGITALOCEAN_TOKEN"] = do_token
        env["DIGITALOCEAN_ACCESS_TOKEN"] = do_token  # some providers read this name

        # Init
        init_res = subprocess.run(
            ["terraform", "init", "-no-color", "-input=false"],
            check=False, text=True, capture_output=True, cwd=workdir, env=env
        )
        if init_res.returncode != 0:
            return { "error": "Terraform init failed", "details": (init_res.stderr or init_res.stdout) }

        # Apply
        apply_res = subprocess.run(
            ["terraform", "apply", "-auto-approve", "-no-color", "-input=false"],
            check=False, text=True, capture_output=True, cwd=workdir, env=env
        )
        if apply_res.returncode != 0:
            return { "error": "Terraform apply failed", "details": (apply_res.stderr or apply_res.stdout) }

        # Try to extract a short summary line
        summary = ""
        for line in (apply_res.stdout or "").splitlines():
            if line.strip().startswith("Apply complete!"):
                summary = line.strip()
                break
        return { "message": summary or "Apply complete." }

    finally:
        shutil.rmtree(workdir, ignore_errors=True)

# ---------- API ----------
@app.post("/trigger-deploy")
def trigger_deploy():
    tf_code = (request.form.get("tf_code") or request.json.get("code") if request.is_json else "" or "").strip()
    do_token = (request.form.get("do_token") or request.json.get("do_token") if request.is_json else "" or "").strip()

    if not do_token:
        return jsonify({ "status": "error", "message": "DigitalOcean token is required" }), 400
    if not tf_code:
        return jsonify({ "status": "error", "message": "Terraform code is empty" }), 400

    # Optional guard: quota check before running anything
    try:
        q = check_do_droplet_quota(do_token)
        if not q.get("ok"):
            return jsonify({ "status": "error", "message": q.get("reason", "Quota check failed") }), 400
    except Exception:
        # Don't block deploys purely on quota API errors; you can change this to hard-fail if you prefer.
        pass

    job_id = str(uuid.uuid4())
    JOBS[job_id] = { "status": "pending", "message": "Queued" }

    def worker():
        # IMPORTANT: do NOT log the token
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
