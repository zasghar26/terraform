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

@app.route("/")
def index():
    base_url = os.environ.get("APP_BASE_URL", "")  # optional; leave blank for same-origin
    return f"""
    <html>
    <head>
      <title>TerraformGen Manual Deployment</title>
      <meta name="app-base-url" content="{base_url}">
    </head>
    <body>
      <h2>TerraformGen</h2>

      <div style="margin-top: 24px;">
        <h3>Deploy Terraform Code</h3>
        <form id="deploy-form">
          <textarea id="tf-code" name="tf_code" rows="20" cols="100"
            placeholder="Paste your Terraform code here..."></textarea><br><br>
          <button type="submit">🚀 Deploy</button>
        </form>
        <div id="deploy-status" style="margin-top:12px;font-family:system-ui,Arial,sans-serif;"></div>
      </div>

      <script src="/static/deploy.js"></script>
    </body>
    </html>
    """

def run_terraform_apply(tf_code: str) -> dict:
    if not DO_TOKEN:
        return {"error": "Server misconfigured: DO_TOKEN not set"}

    deploy_id = str(uuid.uuid4())
    deploy_dir = os.path.join("/tmp", deploy_id)
    os.makedirs(deploy_dir, exist_ok=True)

    try:
        cwd_before = os.getcwd()
        os.chdir(deploy_dir)

        # Write TF files
        with open("main.tf", "w") as f:
            f.write(tf_code)

        with open("terraform.tfvars", "w") as f:
            f.write(f'do_token = "{DO_TOKEN}"\n')

        # Inject provider if missing (basic check)
        if "provider" not in tf_code:
            with open("provider.tf", "w") as f:
                f.write(
                    'variable "do_token" {}\n\n'
                    'provider "digitalocean" {\n'
                    '  token = var.do_token\n'
                    '}\n'
                )

        # Terraform init/apply
        subprocess.run(["terraform", "init", "-no-color"], check=True)
        subprocess.run([
            "terraform", "apply",
            "-var-file=terraform.tfvars",
            "-auto-approve",
            "-no-color"
        ], check=True)

        return {"message": "✅ Terraform applied successfully!"}

    except subprocess.CalledProcessError as e:
        return {"error": "Terraform failed", "details": str(e)}
    except Exception as e:
        return {"error": "Server error", "details": str(e)}
    finally:
        try:
            os.chdir(cwd_before)
        except Exception:
            pass
        shutil.rmtree(deploy_dir, ignore_errors=True)

@app.route("/trigger-deploy", methods=["POST"])
def trigger_deploy():
    tf_code = (request.form.get("tf_code") or "").strip()
    if not tf_code:
        return jsonify({"status": "error", "message": "Terraform code is empty"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "pending", "message": "Queued"}

    def worker():
        JOBS[job_id] = {"status": "running", "message": "Running terraform…"}
        result = run_terraform_apply(tf_code)
        if "error" in result:
            JOBS[job_id] = {"status": "error", "message": result["error"], "details": result.get("details", "")}
        else:
            JOBS[job_id] = {"status": "done", "message": result.get("message", "Done")}

    threading.Thread(target=worker, daemon=True).start()

    return jsonify({
        "status": "accepted",
        "job_id": job_id,
        "status_url": f"{request.host_url.rstrip('/')}/jobs/{job_id}"
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
