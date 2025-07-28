from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import openai
import os

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Check API key is loaded
if not openai.api_key:
    raise Exception("OPENAI_API_KEY is missing. Check your .env file.")

# Load few-shot examples from file
try:
    with open("prompt_examples.txt", "r") as f:
        FEW_SHOT_PROMPT = f.read()
except FileNotFoundError:
    raise Exception("prompt_examples.txt not found in the project directory.")

# Initialize FastAPI
app = FastAPI()

# Define request schema
class RequestModel(BaseModel):
    text: str

# POST endpoint to generate Terraform code
@app.post("/generate")
def generate_code(data: RequestModel):
    try:
        full_prompt = f"{FEW_SHOT_PROMPT}\nInput: {data.text}\nOutput:"
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=full_prompt,
            max_tokens=500,
            temperature=0.3
        )
        terraform_code = response.choices[0].text.strip()
        return {"terraform_code": terraform_code}

    except Exception as e:
        print("🔥 Error:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
