# TerraformGen (DigitalOcean)

Small Flask app with a web UI that accepts Terraform code and deploys it using the Terraform CLI inside the container.

## How it works

- Paste Terraform code and click **Deploy**.
- The server writes the code to a temp dir, injects a minimal `provider "digitalocean" {}` if missing, and runs `terraform init` + `terraform apply -auto-approve`.
- Deploys are non-blocking: `/trigger-deploy` returns `202 Accepted` with a `job_id`. The client polls `/jobs/<job_id>` until `done` or `error`.

## Endpoints
- `GET /` — HTML UI.
- `POST /trigger-deploy` — starts a job. Accepts either `application/x-www-form-urlencoded` with fields `tf_code`, `do_token` or JSON `{ "code": "...", "do_token": "..." }`.
- `GET /jobs/<job_id>` — returns job status JSON.

## Dev
```bash
pip install -r requirements.txt
export FLASK_APP=main.py
flask run -p 8080
