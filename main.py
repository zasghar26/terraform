from flask import Flask, request, jsonify
import os
import subprocess
import uuid
import shutil
import threading

app = Flask(__name__)

# Env vars (must be set in App Platform)
DO_TOKEN = os.environ.get("DO_TOKEN")  # DigitalOcean API token

# In-memory job store (simple for single-instance)
JOBS = {}  # {job_id: {"status": "pending|running|done|error", "message": str, "details": str}}

@app.route('/')
def index():
    base_url = os.environ.get("APP_BASE_URL", "")
    return f"""
    <html>
    <head>
      <title>TerraformGen Manual Deployment</title>
      <meta name="app-base-url" content="{base_url}">
    </head>
    <body>
      <h2>TerraformGen</h2>

      <div style="margin-top:24px;max-width:840px;">
        <h3>Deploy Terraform Code</h3>

        <form id="deploy-form">
          <label style="display:block;margin:8px 0 4px;">DigitalOcean API Token</label>
          <input id="do-token" name="do_token" type="password" autocomplete="off"
                 placeholder="dop_v1_..." style="width:100%;padding:8px;" required />

          <label style="display:block;margin:12px 0 4px;">Terraform Configuration</label>
          <textarea id="tf-code" name="tf_code" rows="18" cols="100"
            placeholder="Paste your Terraform code here..." style="width:100%;padding:8px;" required></textarea>

          <div style="margin-top:12px;">
            <button type="submit">🚀 Deploy</button>
          </div>
        </form>

        <div id="deploy-status" style="margin-top:12px;font-family:system-ui,Arial,sans-serif;"></div>
      </div>

      <script src="/static/deploy.js"></script>
    </body>
    </html>
    """

def run_terraform_apply(tf_code: str, do_token: str) -> dict:
    deploy_id = str(uuid.uuid4())
    deploy_dir = os.path.join("/tmp", deploy_id)
    os.makedirs(deploy_dir, exist_ok=True)

    try:
        cwd_before = os.getcwd()
        os.chdir(deploy_dir)

        # Write user's Terraform
        with open("main.tf", "w") as f:
            f.write(tf_code)

        # Inject minimal provider if missing; token will come from env
        if "provider" not in tf_code:
            with open("provider.tf", "w") as f:
                f.write('provider "digitalocean" {}\n')

        # Prepare environment with the user-supplied token
        env = os.environ.copy()
        # Both names are recognized; keeping both for compatibility
        env["DIGITALOCEAN_TOKEN"] = do_token
        env["DIGITALOCEAN_ACCESS_TOKEN"] = do_token

        # Run terraform (no tfvars, no prompting)
        init_res = subprocess.run(["terraform", "init", "-no-color", "-input=false"],
                            check=False, text=True, capture_output=True, env=env)
        if init_res.returncode != 0:
            return {"error": "Terraform init failed", "details": init_res.stderr or init_res.stdout}

        apply_res = subprocess.run([
                "terraform", "apply",
                "-auto-approve",
                "-no-color",
                "-input=false",
            ],
            check=False, text=True, capture_output=True, env=env
        )
        if apply_res.returncode != 0:
            return {"error": "Terraform apply failed", "details": apply_res.stderr or apply_res.stdout}

        return {"message": "✅ Terraform applied successfully!"}

    except Exception as e:
        return {"error": "Server error", "details": str(e)}
    finally:
        try:
            os.chdir(cwd_before)
        except Exception:
            pass
        shutil.rmtree(deploy_dir, ignore_errors=True)

def check_do_droplet_quota(token: str) -> dict:
    """Return {'ok': True} or {'ok': False, 'reason': '...'}"""
    headers = {"Authorization": f"Bearer {token}"}
    # 1) Get account droplet_limit
    acc = requests.get("https://api.digitalocean.com/v2/account", headers=headers, timeout=15)
    acc.raise_for_status()
    limit = acc.json().get("account", {}).get("droplet_limit", 0)

    # 2) Count current droplets (paginate just in case)
    total = 0
    url = "https://api.digitalocean.com/v2/droplets?per_page=200"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        total += len(data.get("droplets", []))
        url = data.get("links", {}).get("pages", {}).get("next")

    if total >= limit:
        return {"ok": False, "reason": f"Droplet limit reached ({total}/{limit}). Destroy one or request a limit increase."}
    return {"ok": True, "usage": total, "limit": limit}

@app.route("/trigger-deploy", methods=["POST"])
def trigger_deploy():
    tf_code = (request.form.get("tf_code") or "").strip()
    do_token = (request.form.get("do_token") or "").strip()

    if not do_token:
        return jsonify({"status": "error", "message": "DigitalOcean token is required"}), 400
    if not tf_code:
        return jsonify({"status": "error", "message": "Terraform code is empty"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "pending", "message": "Queued"}

    def worker():
        # IMPORTANT: do NOT log the token
        JOBS[job_id] = {"status": "running", "message": "Running terraform…"}
        result = run_terraform_apply(tf_code, do_token)
        if "error" in result:
            JOBS[job_id] = {"status": "error", "message": result["error"], "details": result.get("details", "")}
        else:
            JOBS[job_id] = {"status": "done", "message": result.get("message", "Done")}

    threading.Thread(target=worker, daemon=True).start()

    # Return a relative URL to avoid mixed content
    return jsonify({
        "status": "accepted",
        "job_id": job_id,
        "status_url": f"/jobs/{job_id}"
    }), 202

@app.route("/jobs/<job_id>", methods=["GET"])
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job), 200

if __name__ == "__main__":
    # Make sure terraform is available in the container/image
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
