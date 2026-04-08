import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("LLM_API_KEY")

if not api_key:
    print("❌ API Key tidak ditemukan di .env")
    exit()

genai.configure(api_key=api_key)

print("\n🔍 MENCARI MODEL YANG TERSEDIA & SUPPORT 'generateContent'...\n")
print(f"{'NAMA MODEL (Copy ini ke .env)':<40} | {'METODE SUPPORTED'}")
print("-" * 80)

for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        # Kita cari model yang BUKAN version 'vision' saja, tapi general text
        print(f"✅ {m.name.replace('models/', ''):<40}")

print("-" * 80)
