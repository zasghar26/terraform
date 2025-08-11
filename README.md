TerraformGen App (DigitalOcean App Platform)
A tiny Flask app with a web UI that accepts Terraform code and runs it asynchronously inside the same app container on DigitalOcean App Platform. The UI shows progress and final status—no external deploy service needed.

Features
Paste Terraform code and click Deploy.

Non-blocking deploys (returns 202 Accepted with a job ID).

Status endpoint for polling job progress.

Temp workdirs under /tmp/<uuid>; auto-cleanup after each run.

No hard-coded URLs; works same-origin by default.

Architecture

Frontend (static/deploy.js)
      |
      |  POST /trigger-deploy   (returns 202 + job_id + status_url)
      v
Backend (Flask)
  -> Background thread runs:
     - write TF files
     - terraform init && terraform apply
     - store result in JOBS[job_id]
      ^
      |  GET /jobs/<job_id>     (poll until done/error)
Frontend (polls and updates UI)
Repo Layout

.
├─ main.py               # Flask app with async job runner
├─ static/
│   └─ deploy.js         # Frontend JS: submit + poll job status
├─ requirements.txt      # Flask + Gunicorn
├─ Dockerfile            # (optional) Python + Terraform runtime for DO App Platform
└─ README.md
Requirements
Python 3.10+ (local dev)

Terraform 1.4+ available in the runtime (Dockerfile below provides it)

DigitalOcean Personal Access Token with API access (DO_TOKEN)

Environment Variables
Name	Required	Purpose
DO_TOKEN	✅	DigitalOcean API token passed to Terraform as var.do_token.
APP_BASE_URL	❌	Base URL for the frontend to call (leave empty for same-origin).

Same-origin is recommended. If frontend and backend are on different origins, enable CORS yourself.

Quickstart (Local)
Create and activate a venv:


python3 -m venv .venv
source .venv/bin/activate
Install deps:


pip install -r requirements.txt
Install Terraform (locally).

macOS: brew tap hashicorp/tap && brew install hashicorp/tap/terraform

Linux: follow HashiCorp’s instructions, or use the Dockerfile method below.

Export env vars:


export DO_TOKEN=your_do_api_token
export PORT=5000
Run:


gunicorn -w 2 -b 0.0.0.0:$PORT main:app
Open http://localhost:5000, paste Terraform code, click Deploy.

⚠️ Terraform may create billable resources. Use test projects/quotas and remember to destroy resources when you’re done.

Deploy on DigitalOcean App Platform
Recommended: Deploy with a Dockerfile so Terraform is present at runtime.

Dockerfile (example)
dockerfile

# ---- Build runtime with Python + Terraform ----
FROM python:3.11-slim

# Install Terraform
ARG TF_VERSION=1.7.5
RUN apt-get update && apt-get install -y curl unzip ca-certificates \
 && curl -fsSL https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip -o /tmp/terraform.zip \
 && unzip /tmp/terraform.zip -d /usr/local/bin \
 && rm -rf /var/lib/apt/lists/* /tmp/terraform.zip

# Create app dir
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Expose and run
ENV PORT=8080
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "main:app"]
App Platform settings:

Environment variables: set DO_TOKEN, optionally APP_BASE_URL (can be blank).

HTTP port: 8080 (matches Dockerfile CMD).

Autodeploy: optional.

Usage
Web UI
Visit the app URL.

Paste Terraform configuration into the textarea.

Click Deploy.

The UI submits to /trigger-deploy, receives a job_id, and polls /jobs/<job_id>.

When done, it shows ✅ success or ❌ error with details.

API Endpoints (for testing)
POST /trigger-deploy
Form data: tf_code=<terraform text>
Returns 202:


{
  "status": "accepted",
  "job_id": "b2e6…",
  "status_url": "https://your-app/jobs/b2e6…"
}
GET /jobs/<job_id>
Returns:


{"status": "pending|running|done|error", "message": "...", "details": "...?"}
Sample Terraform (DigitalOcean Droplet)
Costs money. Use at your own risk; destroy afterward.


terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

variable "do_token" {}

provider "digitalocean" {
  token = var.do_token
}

resource "digitalocean_droplet" "example" {
  name   = "tfgen-example"
  region = "nyc1"
  size   = "s-1vcpu-1gb"
  image  = "ubuntu-22-04-x64"
}
The app will create terraform.tfvars with:


do_token = "<value from DO_TOKEN>"
Troubleshooting
HTTP 504 / timeouts

Fixed by async flow: /trigger-deploy returns quickly with 202. If you still see 504, check any upstream proxy/load balancer.

Terraform not found

Ensure your App Platform service uses the provided Dockerfile (or otherwise installs Terraform).

Check logs: terraform: not found indicates the binary isn’t there.

CORS errors

Use same-origin (default). If frontend and backend are on different origins, add flask-cors and enable it for /trigger-deploy and /jobs/*.

DigitalOcean auth fails

Verify DO_TOKEN is set in the environment and has sufficient permissions for the resources you create.

State & concurrency

Jobs are kept in memory (JOBS dict). For multiple instances or restarts, use a persistent store/queue (Redis, DB, etc.).

This example is single-instance friendly.

Security Notes
The app executes arbitrary Terraform provided by the user. Protect the app behind auth if exposed to the public.

Limit providers/regions/quotas in your TF or workspace policies if needed.

Never log secrets (DO_TOKEN).

Development Notes
Logs are your friend. Add print() statements in /trigger-deploy and the worker as needed.

Consider streaming logs to /jobs/<id> if you want live output (SSE or WebSocket).

License
MIT (or your choice). Add a LICENSE file if needed.

Acknowledgements
Flask + Gunicorn app scaffold.

Terraform CLI run inside app container with per-job temp dirs.