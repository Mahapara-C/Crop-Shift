"""
Minimal test: confirm the model can correctly choose to call a tool
(function) instead of just replying with text — the core mechanic the
orchestrator loop depends on.
"""

import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.getenv("HF_TOKEN"),
)

# A deliberately simple fake tool, just to test the mechanic
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_district_elevation",
            "description": "Get the elevation in meters for a Bangladesh district.",
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "The district name, e.g. Cumilla"
                    }
                },
                "required": ["district"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="meta-llama/Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "What is the elevation of Cumilla?"}],
    tools=tools,
)

message = response.choices[0].message
print("Model's raw response message:")
print(message)

if message.tool_calls:
    print("\n--- Model chose to call a tool ---")
    for call in message.tool_calls:
        print(f"Function: {call.function.name}")
        print(f"Arguments: {call.function.arguments}")
else:
    print("\n--- Model did NOT call a tool, just replied with text ---")
    print(message.content)