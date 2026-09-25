"""
Minimal test: confirm we can call a free Hugging Face model and get a
response back, before building the full orchestrator loop.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # reads HF_TOKEN from your local .env file

client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.getenv("HF_TOKEN"),
)

response = client.chat.completions.create(
    model="meta-llama/Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)

print(response.choices[0].message.content)