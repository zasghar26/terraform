from flask import Flask, request, jsonify
import os
import subprocess
import uuid
import shutil
import requests

app = Flask(__name__)

# Load environment variables
AGENT_KEY = os.environ.get("AGENT_KEY")
DO_TOKEN = os.environ.get("DO_TOKEN")

@app.route('/')
def index():
    base_url = os.environ.get("APP_BASE_URL", "")  # optional: set in App Platform
    return f'''
    <html>
    <head>
        <title>TerraformGen Manual Deployment</title>
        <!-- Optional: if set, JS will use this; otherwise defaults to same-origin -->
        <meta name="app-base-url" content="{base_url}">
    </head>
    <body>
        <h2>TerraformGen Chatbot</h2>

        <!-- Chatbot Widget -->
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

        <!-- Deploy Form -->
        <div style="margin-top: 40px;">
          <h3>Deploy Terraform Code</h3>
          <form id="deploy-form">
            <textarea id="tf-code" name="tf_code" rows="20" cols="100"
              placeholder="Paste your Terraform code here..."></textarea><br><br>
            <button type="submit">🚀 Deploy</button>
          </form>

          <div id="deploy-status" style="margin-top:12px;font-family:system-ui,Arial,sans-serif;"></div>
        </div>

        <!-- Frontend logic to POST to /trigger-deploy -->
        <script src="/static/deploy.js"></script>
    </body>
    </html>
    '''

@app.route('/trigger-deploy', methods=['POST'])
def trigger_deploy():
    if not AGENT_KEY:
        return jsonify({"status": "error", "message": "AGENT_KEY is not set"}), 500

    tf_code = request.form.get('tf_code', '').strip()
    if not tf_code:
        return jsonify({"status": "error", "message": "Terraform code is empty"}), 400

    headers = {
        "Authorization": f"Bearer {AGENT_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"terraform_code": tf_code}

    try:
        # Call same app’s /deploy or another service via BACKEND_BASE_URL
        deploy_base = os.environ.get("BACKEND_BASE_URL", request.host_url.rstrip('/'))
        resp = requests.post(f"{deploy_base}/deploy", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        is_json = resp.headers.get('content-type', '').lower().startswith('application/json')
        return jsonify({
            "status": "ok",
            "message": "Deployment triggered",
            "response": resp.json() if is_json else resp.text
        }), 200
    except requests.RequestException as e:
        body = ""
        if getattr(e, "response", None) is not None:
            try:
                body = e.response.text
            except Exception:
                body = str(e)
        else:
            body = str(e)
        return jsonify({"status": "error", "message": body}), 502

@app.route('/deploy', methods=['POST'])
def deploy():
    # 1. Validate Authorization Header
    if not AGENT_KEY:
        return jsonify({"error": "Server misconfigured: AGENT_KEY not set"}), 500
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {AGENT_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    # 2. Validate Request Body
    data = request.get_json(silent=True) or {}
    if "terraform_code" not in data or not str(data["terraform_code"]).strip():
        return jsonify({"error": "Missing 'terraform_code' in request"}), 400

    if not DO_TOKEN:
        return jsonify({"error": "Server misconfigured: DO_TOKEN not set"}), 500

    tf_code = data["terraform_code"]

    # 3. Create Unique Working Directory
    deploy_id = str(uuid.uuid4())
    deploy_dir = os.path.join("/tmp", deploy_id)
    os.makedirs(deploy_dir, exist_ok=True)

    try:
        os.chdir(deploy_dir)

        # 4. Write Terraform Code
        with open("main.tf", "w") as f:
            f.write(tf_code)

        # 5. Inject token via tfvars
        with open("terraform.tfvars", "w") as f:
            f.write(f'do_token = "{DO_TOKEN}"\n')

        # 6. Inject provider block if not present (basic check)
        if "provider" not in tf_code:
            with open("provider.tf", "w") as f:
                f.write(
                    'variable "do_token" {}\n\n'
                    'provider "digitalocean" {\n'
                    '  token = var.do_token\n'
                    '}\n'
                )

        # 7. Run Terraform
        subprocess.run(["terraform", "init", "-no-color"], check=True)
        subprocess.run([
            "terraform", "apply",
            "-var-file=terraform.tfvars",
            "-auto-approve",
            "-no-color"
        ], check=True)

        return jsonify({"message": "✅ Terraform applied successfully!"}), 200

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Terraform failed", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500
    finally:
        try:
            os.chdir("/app")
            shutil.rmtree(deploy_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
