from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import requests
import os

load_dotenv()

AGENT_URL = os.getenv("DO_AGENT_URL")
AGENT_TOKEN = os.getenv("DO_AGENT_TOKEN")  # Optional token

if not AGENT_URL:
    raise Exception("DO_AGENT_URL is missing in .env")

app = FastAPI()

class RequestModel(BaseModel):
    text: str

@app.post("/generate")
def generate_code(data: RequestModel):
    try:
        headers = {
            "Content-Type": "application/json"
        }

        if AGENT_TOKEN:
            headers["Authorization"] = f"Bearer {AGENT_TOKEN}"

        payload = {
            "messages": [
                {"role": "user", "content": data.text}
            ]
        }

        response = requests.post(AGENT_URL, headers=headers, json=payload)
        response.raise_for_status()

        result = response.json()
        message = result["choices"][0]["message"]["content"].strip()

        cleaned_code = message.replace("```hcl", "").replace("```", "").strip()
        return {"terraform_code": cleaned_code}


    except Exception as e:
        print("🔥 Error:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
