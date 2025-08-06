from flask import Flask, request, jsonify
import os
import subprocess
import uuid
import shutil

app = Flask(__name__)

# Load environment variables
AGENT_KEY = os.environ.get("AGENT_KEY")
DO_TOKEN = os.environ.get("DO_TOKEN")

@app.route('/deploy', methods=['POST'])
def deploy():
    # 1. Validate Authorization Header
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {AGENT_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    # 2. Validate Request Body
    data = request.get_json()
    if not data or "terraform_code" not in data:
        return jsonify({"error": "Missing 'terraform_code' in request"}), 400

    tf_code = data["terraform_code"]

    # 3. Create Unique Working Directory
    deploy_id = str(uuid.uuid4())
    deploy_dir = os.path.join("/tmp", deploy_id)
    os.makedirs(deploy_dir)

    try:
        os.chdir(deploy_dir)

        # 4. Write Terraform Code
        with open("main.tf", "w") as f:
            f.write(tf_code)

        # 5. Inject token via tfvars
        with open("terraform.tfvars", "w") as f:
            f.write(f'do_token = "{DO_TOKEN}"\n')

        # 6. Inject provider block if not present
        if "provider" not in tf_code:
            with open("provider.tf", "w") as f:
                f.write("""
variable "do_token" {}

provider "digitalocean" {
  token = var.do_token
}
""")

        # 7. Run Terraform
        subprocess.run(["terraform", "init", "-no-color"], check=True)
        subprocess.run([
            "terraform", "apply",
            "-var-file=terraform.tfvars",
            "-auto-approve",
            "-no-color"
        ], check=True)

        return jsonify({
            "message": "✅ Terraform applied successfully!"
        }), 200

    except subprocess.CalledProcessError as e:
        return jsonify({
            "error": "Terraform failed",
            "details": str(e)
        }), 500

    except Exception as e:
        return jsonify({
            "error": "Server error",
            "details": str(e)
        }), 500

    finally:
        # 8. Clean up
        try:
            os.chdir("/app")
            shutil.rmtree(deploy_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
