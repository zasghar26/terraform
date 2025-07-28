from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import openai
import os

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise Exception("OPENAI_API_KEY is missing.")

client = openai.OpenAI(api_key=api_key)
app = FastAPI()

class RequestModel(BaseModel):
    text: str

# Load prompt examples
try:
    with open("prompt_examples.txt", "r") as f:
        FEW_SHOT_PROMPT = f.read()
except FileNotFoundError:
    raise Exception("prompt_examples.txt not found.")

@app.post("/generate")
def generate_code(data: RequestModel):
    try:
        prompt = f"{FEW_SHOT_PROMPT}\nInput: {data.text}\nOutput:"
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a Terraform generator for DigitalOcean."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        terraform_code = response.choices[0].message.content.strip()
        return {"terraform_code": terraform_code}
    except Exception as e:
        print("🔥 Error:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
