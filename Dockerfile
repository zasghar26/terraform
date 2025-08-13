# Use Debian bookworm so HashiCorp's apt repo exists
FROM python:3.11-bookworm

# Install system packages and Terraform from HashiCorp's apt repo
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg unzip ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    \
    # Add HashiCorp apt repo (bookworm)
    install -d -m 0755 /etc/apt/keyrings && \
    curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /etc/apt/keyrings/hashicorp.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com bookworm main" > /etc/apt/sources.list.d/hashicorp.list && \
    apt-get update && apt-get install -y --no-install-recommends terraform && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set up app
WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:8080"]
