import os
import sys
import logging
from datetime import datetime, timezone
import threading
import pytz
from dotenv import load_dotenv

load_dotenv()

# Timezone Setup
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")

# Logging Setup (Gaia Standard)
def custom_time(*args):
    utc_dt = datetime.now(timezone.utc)
    converted = utc_dt.astimezone(MY_TZ)
    return converted.timetuple()

logging.Formatter.converter = custom_time
current_folder_name = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_filename = f"{current_folder_name}.log"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), log_filename), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.__stdout__)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("Demeter")



logging.info(f"--- SYSTEM STARTUP: {current_folder_name.upper()} ---")

# ==========================================
# --- SYSTEM CONFIGURATION ---
# ==========================================
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    print("CRITICAL: LLM_API_KEY missing in .env")

API_KEY_LIST = [k.strip() for k in LLM_API_KEY.split(',') if k.strip()] if LLM_API_KEY else [] 
LLM_BASE_MODEL = os.getenv("LLM_BASE_MODEL", "gemini/gemini-2.0-flash")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
users_str = os.getenv("USERS_ALLOWED", "")
ALLOWED_USERS = [int(x) for x in users_str.split(',') if x.strip().isdigit()]
if TELEGRAM_CHAT_ID and int(TELEGRAM_CHAT_ID) not in ALLOWED_USERS:
    ALLOWED_USERS.append(int(TELEGRAM_CHAT_ID))

RTSP_URL = os.getenv("RTSP_URL")

DB_FILE = os.getenv("DB_FILE", "data_logs/garden_history.csv")
DB_PATH = os.getenv("DB_PATH", "data_logs/demeter.db")
CAPTURE_DIR = os.getenv("CAPTURE_DIR", "vision_capture")
MOISTURE_SAFETY_LIMIT = int(os.getenv("MOISTURE_SAFETY_LIMIT", 70))
PLANT_NAME = os.getenv("PLANT_NAME", "Monstera Deliciosa Variegata")

# GLOBAL VARIABLES
LATEST_DATA = {
    "moisture": 0, "temp": 0, "humidity": 0, "co2": 0, "last_seen": datetime.min,
    "action": "WAITING", "status": "BOOT"
}
LAST_LOG_TIME = datetime.min
NEXT_ANALYSIS_TIME = datetime.now() 
HARD_COOLDOWN_HOURS = 3
SOFT_COOLDOWN_HOURS = 2
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6

class TimeoutLock:
    def __init__(self, timeout=10.0):
        self._lock = threading.Lock()
        self.timeout = timeout

    def acquire(self, blocking=True):
        return self._lock.acquire(blocking=blocking, timeout=self.timeout)

    def release(self):
        try:
            self._lock.release()
        except RuntimeError:
            pass

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError("Lock acquisition timed out")
        return True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

COMMAND_QUEUE = None
AI_PROCESSING_LOCK = TimeoutLock(timeout=60.0)

LAST_TELEGRAM_MSG_ID = None
LAST_CHAT_ID = None

SYSTEM_CACHE = {
    "last_moisture": None,
    "last_temp": None, 
    "last_update": None,
    "status": "WAITING_DATA"
}

# Local Brain with Central Sync
try:
    from core.memory_manager import GaiaBrain
    global_brain = GaiaBrain()
    logger.info("🧠 Demeter Memory Manager (Local + Central Sync) connected.")
except ImportError as e:
    logger.error(f"⚠️ [SURVIVAL MODE] Local Memory Manager error: {e}")
    class GaiaBrain:
        def __init__(self): pass
        def record(self, *args, **kwargs): return False
        def remember(self, *args, **kwargs): return ""
    global_brain = GaiaBrain()
