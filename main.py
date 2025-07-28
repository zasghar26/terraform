from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import requests
import os

# Load .env variables
load_dotenv()

DO_API_KEY = os.getenv("DO_API_KEY")
DO_AGENT_ID = os.getenv("DO_AGENT_ID")

if not DO_API_KEY or not DO_AGENT_ID:
    raise Exception("DO_API_KEY or DO_AGENT_ID is missing in .env")

# FastAPI app
app = FastAPI()

# Input schema
class RequestModel(BaseModel):
    text: str

# API route to talk to the DO agent
@app.post("/generate")
def generate_code(data: RequestModel):
    try:
        url = f"https://api.digitalocean.com/v2/agents/{DO_AGENT_ID}/chat"
        headers = {
            "Authorization": f"Bearer {DO_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": data.text
                }
            ]
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        result = response.json()
        message = result["choices"][0]["message"]["content"].strip()
        return {"terraform_code": message}

    except Exception as e:
        print("🔥 Error:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
