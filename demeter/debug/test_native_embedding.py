import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(".env")
load_dotenv("minerva/.env", override=True) # Check minerva config

api_key = os.getenv("EMBEDDING_API_KEY")
base_url = os.getenv("EMBEDDING_API_BASE")
# Clean the model name for OpenAI client (remove prefixes if present, or keep if OpenRouter needs them)
# OpenRouter usually wants "google/gemini-embedding-001"
model = os.getenv("LLM_EMBEDDING_MODEL").replace("openai/", "").replace("openrouter/", "")

print(f"--- NATIVE OPENAI CLIENT TEST ---")
print(f"API KEY: {api_key[:5]}...")
print(f"BASE URL: {base_url}")
print(f"MODEL: {model}")

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

try:
    response = client.embeddings.create(
        model=model,
        input="Hello native world"
    )
    print("✅ SUCCESS!")
    print(f"Embedding len: {len(response.data[0].embedding)}")
except Exception as e:
    print(f"❌ FAILED: {e}")
