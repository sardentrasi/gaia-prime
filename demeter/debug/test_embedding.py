from dotenv import load_dotenv
import os
import litellm
import logging

# Load env
load_dotenv(".env")
load_dotenv("minerva/.env", override=True) # mimic minerva loading

logging.basicConfig(level=logging.INFO)
litellm.set_verbose=True

api_key = os.getenv("EMBEDDING_API_KEY")
model = os.getenv("LLM_EMBEDDING_MODEL")
api_base = os.getenv("EMBEDDING_API_BASE")

print(f"--- TESTING EMBEDDING ---")
print(f"API KEY: {api_key[:5]}...{api_key[-4:] if api_key else 'None'}")
print(f"MODEL: {model}")
print(f"API BASE: {api_base}")

try:
    response = litellm.embedding(
        model=model,
        input=["Hello world"],
        api_key=api_key,
        api_base=api_base
    )
    print("✅ SUCCESS!")
    print(f"Embedding length: {len(response['data'][0]['embedding'])}")
except Exception as e:
    print(f"❌ FAILED: {e}")

print("\n--- ATTEMPT 2: WITHOUT PREFIX (Raw 'google/gemini-embedding-001') ---")
try:
    raw_model = "google/gemini-embedding-001"
    print(f"Testing model: {raw_model}")
    response = litellm.embedding(
        model=raw_model,
        input=["Hello world"],
        api_key=api_key,
        api_base=api_base
    )
    print("✅ SUCCESS (Raw)!")
    print(f"Embedding length: {len(response['data'][0]['embedding'])}")
except Exception as e:
    print(f"❌ FAILED (Raw): {e}")

print("\n--- ATTEMPT 3: OPENROUTER PREFIX ('openrouter/google/gemini-embedding-001') ---")
try:
    or_model = "openrouter/google/gemini-embedding-001"
    print(f"Testing model: {or_model}")
    response = litellm.embedding(
        model=or_model,
        input=["Hello world"],
        api_key=api_key,
        api_base=api_base
    )
    print("✅ SUCCESS (OpenRouter Prefix)!")
    print(f"Embedding length: {len(response['data'][0]['embedding'])}")
except Exception as e:
    print(f"❌ FAILED (OpenRouter Prefix): {e}")

# Try custom provider setting
print("\n--- ATTEMPT 4: CUSTOM_LLM_PROVIDER='openai' ---")
try:
    raw_model = "google/gemini-embedding-001"
    print(f"Testing model: {raw_model} with custom_llm_provider='openai'")
    response = litellm.embedding(
        model=raw_model,
        input=["Hello world"],
        api_key=api_key,
        api_base=api_base,
        custom_llm_provider="openai"
    )
    print("✅ SUCCESS (Custom Provider)!")
    print(f"Embedding length: {len(response['data'][0]['embedding'])}")
except Exception as e:
    print(f"❌ FAILED (Custom Provider): {e}")
