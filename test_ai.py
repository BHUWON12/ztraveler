from dotenv import load_dotenv
load_dotenv()  # ✅ loads values from .env into os.environ

import os
from google import genai

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("🚨 GOOGLE_API_KEY not found in environment!")

client = genai.Client(api_key=api_key)

print("✅ Gemini client initialized successfully.")
print("🔍 Available models:")
for model in client.models.list():
    print(" -", model.name)
