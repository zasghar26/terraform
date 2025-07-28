from fastapi import FastAPI, Request
from pydantic import BaseModel
import openai
import os
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

class RequestModel(BaseModel):
    text: str

with open("prompt_examples.txt") as f:
    FEW_SHOT_PROMPT = f.read()

@app.post("/generate")
def generate_code(data: RequestModel):
    full_prompt = f"{FEW_SHOT_PROMPT}\nInput: {data.text}\nOutput:"
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=full_prompt,
        max_tokens=500,
        temperature=0.3
    )
    return {"terraform_code": response.choices[0].text.strip()}
