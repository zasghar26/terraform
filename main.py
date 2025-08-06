from flask import Flask, request, jsonify
import os
import subprocess
import uuid
import shutil

app = Flask(__name__)

AGENT_KEY = os.environ.get("AGENT_KEY")
DO_TOKEN = os.environ.get("DO_TOKEN")

@app.route('/deploy', methods=['POST'])
def deploy():
    # Authorization header check
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {AGENT_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    # Get and validate JSON
    data = request.get_json()
    tf_code = data.get("terraform_code")

    if not tf_code:
        return jsonify({"error": "No Terraform code provided"}), 400

    # Create temporary isolated directory
    deploy_id = str(uuid.uuid4())
    os.makedirs(deploy_id)
    os.chdir(deploy_id)

    # Write main.tf
    with open("main.tf", "w") as f:
        f.write(tf_code)

    # Write tfvars with DO token
    with open("terraform.tfvars", "w") as f:
        f.write(f'do_token = "{DO_TOKEN}"\n')

    # Inject provider block if not present
    if "provider" not in tf_code:
        with open("provider.tf", "w") as f:
            f.write("""
variable "do_token" {}

provider "digitalocean" {
    token = var.do_token
}
""")

    # Run Terraform
    try:
        subprocess.run(["terraform", "init"], check=True)
        subprocess.run(["terraform", "apply", "-var-file=terraform.tfvars", "-auto-approve"], check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Terraform failed", "details": str(e)}), 500
    finally:
        # Clean up after run
        os.chdir("..")
        shutil.rmtree(deploy_id, ignore_errors=True)

    return jsonify({"message": "Terraform applied successfully!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
