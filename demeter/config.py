import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- LLM CONFIG (STRICT) ---
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")

# --- TELEGRAM ---
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- CAMERA CONFIG (RTSP) ---
# RTSP URL (Verified in VLC)
RTSP_URL = os.getenv("RTSP_URL")


# --- FILE PATHS ---
CAPTURE_DIR = os.getenv("CAPTURE_DIR", "vision_capture")
DB_FILE = os.getenv("DB_FILE", "data_logs/garden_history.csv")

# --- SYSTEM SETTINGS ---
MOISTURE_SAFETY_LIMIT = int(os.getenv("MOISTURE_SAFETY_LIMIT", 60))
