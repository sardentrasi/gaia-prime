import os
import sys
import logging
import json
import cv2
import time
import requests
import glob
import threading
import asyncio
import pytz
import gc
import traceback
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import NetworkError, TimedOut
from litellm import completion
from dotenv import load_dotenv
from PIL import Image

# Load .env before accessing os.getenv
load_dotenv()
import traceback
import config # Import config to use hardcoded RTSP_URL
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
current_folder_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
log_filename = f"{current_folder_name}.log"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), log_filename), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("Demeter")

# [STANDALONE SURVIVAL] Short-Term Memory
import schedule
import threading

def update_short_memory(action: str, result: str) -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    module_name = os.path.basename(current_dir)
    state_file = os.path.join(current_dir, f"{module_name}_state.json")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_entry = {
        "timestamp": timestamp,
        "action": action,
        "result": result
    }
    
    try:
        state_data = {}
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                try:
                    state_data = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ [{module_name.upper()}] State file corrupted. Rebuilding memory structure.")
        
        if "short_term_memory" not in state_data:
            state_data["short_term_memory"] = []
            
        state_data["short_term_memory"].append(memory_entry)
        state_data["short_term_memory"] = state_data["short_term_memory"][-10:]
        
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=4)
            
        logger.info(f"💾 [{module_name.upper()}] Local Short-Term Memory Updated: '{action}'")
        
    except Exception as e:
        logger.error(f"❌ [{module_name.upper()}] Failed to write local short-term memory: {e}", exc_info=True)

def clear_local_short_memory() -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    module_name = os.path.basename(current_dir)
    state_file = os.path.join(current_dir, f"{module_name}_state.json")
    
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            
            if "short_term_memory" in state_data:
                state_data["short_term_memory"] = []
                
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=4)
                
            logger.info(f"🧹 [{module_name.upper()}] Midnight Protocol Initiated: Short-Term Memory purged.")
    except Exception as e:
        logger.error(f"❌ [{module_name.upper()}] Failed to clear short-term memory at midnight: {e}", exc_info=True)

def start_midnight_cleanup_scheduler() -> None:
    schedule.every().day.at("00:00").do(clear_local_short_memory)

    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(60)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("🕒 Midnight Cleanup Scheduler initialized.")

# [STANDARDIZATION] Local Brain with Central Sync
try:
    from demeter_memory_manager import GaiaBrain
    logger.info("🧠 Demeter Memory Manager (Local + Central Sync) connected.")
except ImportError as e:
    logger.error(f"⚠️ [SURVIVAL MODE] Local Memory Manager error: {e}")
    # Final Safety Net (Mock Class to prevent crash)
    class GaiaBrain:
        def __init__(self): pass
        def record(self, *args, **kwargs): return False
        def remember(self, *args, **kwargs): return ""

# Opsional: Redirect print() biasa agar masuk ke sistem logging juga
# Ini berguna jika kode lama Anda banyak menggunakan print() daripada logging.info()
class StreamToLogger(object):
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())
    def flush(self):
        pass

# Aktifkan redirect stdout dan stderr ke logging
sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO)
sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR)

logging.info(f"--- SYSTEM STARTUP: {current_folder_name.upper()} ---")

# --- END LOGGING SETUP ---

# LOAD ENV (FORCE TOP)
load_dotenv()

# ==========================================
# --- SYSTEM CONFIGURATION ---
# ==========================================

LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    print("CRITICAL: LLM_API_KEY missing in .env")
# raise ValueError("LLM_API_KEY missing") 

# [HYDRA PROTOCOL] MULTI-KEY SUPPORT
# Split by comma to support rotation
API_KEY_LIST = [k.strip() for k in LLM_API_KEY.split(',') if k.strip()] if LLM_API_KEY else [] 

# LLM Model Config (STRICT)
LLM_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
print(f"[POLYGLOT] Model: {LLM_MODEL} | Key Present: {bool(LLM_API_KEY)}")

# 2. Telegram Bot Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
users_str = os.getenv("USERS_ALLOWED", "")
ALLOWED_USERS = [int(x) for x in users_str.split(',') if x.strip().isdigit()]
# Add owner to allowed list
if TELEGRAM_CHAT_ID and int(TELEGRAM_CHAT_ID) not in ALLOWED_USERS:
    ALLOWED_USERS.append(int(TELEGRAM_CHAT_ID))
print(f"[SECURITY] Whitelisted Users: {ALLOWED_USERS}")

# 3. Kamera CCTV (RTSP URL)
# Menggunakan config.py agar konsisten dengan edit user
RTSP_URL = config.RTSP_URL
print(f"[SYSTEM] RTSP URL Loaded: {RTSP_URL}")

# 4. Pengaturan File & Folder
DB_FILE = os.getenv("DB_FILE", "data_logs/garden_history.csv")
CAPTURE_DIR = os.getenv("CAPTURE_DIR", "vision_capture")

# 5. Pengaturan Sistem
MOISTURE_SAFETY_LIMIT = int(os.getenv("MOISTURE_SAFETY_LIMIT", 70))

# ==========================================
# --- SYSTEM CORE ---
# ==========================================

# GLOBAL VARIABLES (Safety & State)
LATEST_DATA = {
    "moisture": 0, "temp": 0, "last_seen": datetime.min,
    "action": "WAITING", "status": "BOOT"
}
LAST_LOG_TIME = datetime.min
# VARIABLE COOLDOWN & NIGHT MODE
NEXT_ANALYSIS_TIME = datetime.now() 
HARD_COOLDOWN_HOURS = 3
SOFT_COOLDOWN_HOURS = 2
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6

# [OPTIMIZATION] Custom Lock with Timeout to prevent deadlocks
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
            pass # Already released

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError("Lock acquisition timed out")
        return True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

COMMAND_QUEUE = None
AI_PROCESSING_LOCK = TimeoutLock(timeout=60.0) # Smart Lock

# TELEGRAM UX STATE
LAST_TELEGRAM_MSG_ID = None
LAST_CHAT_ID = None

# AI PERSONA PROMPT
# TELEGRAM UX STATE
# (Reverted to standard flow)

# Compatibility for older references (will be updated via LATEST_DATA)
SYSTEM_CACHE = {
    "last_moisture": None,
    "last_temp": None, 
    "last_update": None,
    "status": "WAITING_DATA"
}

app = Flask(__name__)

# Menggunakan Polyglot Config
# client = genai.Client(api_key=API_KEY) # DEPRECATED - REMOVED PERMANENTLY

# --- MODUL UTILITIES ---
def get_previous_image(current_img_path):
    """Mencari gambar satu langkah sebelum gambar saat ini"""
    try:
        if not os.path.exists(CAPTURE_DIR):
             os.makedirs(CAPTURE_DIR)

        list_files = sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.jpg")))
        
        if len(list_files) < 2:
            return None
            
        try:
            current_index = list_files.index(current_img_path)
            if current_index > 0:
                prev_img = list_files[current_index - 1]
                return prev_img
        except ValueError:
            return list_files[-2]
            
        return None
    except Exception as e:
        print(f"[ERROR] Gagal cari gambar lama: {e}")
        return None

# --- MODUL 1: TELEGRAM NOTIFICATION (OUTBOUND) ---
# Fungsi ini digunakan oleh Flask Thread untuk mengirim notifikasi proaktif
def kirim_telegram_sync(pesan, file_gambar=None):
    print(f"[TELEGRAM] Mengirim notifikasi...")
    try:
        url_text = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        
        if file_gambar and os.path.exists(file_gambar):
            with open(file_gambar, "rb") as f:
                payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": pesan, "parse_mode": "Markdown"}
                files = {"photo": f}
                requests.post(url_photo, data=payload, files=files, timeout=20)
        else:
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan, "parse_mode": "Markdown"}
            requests.post(url_text, data=payload, timeout=20)
    except Exception as e:
        print(f"[ERROR] Telegram fail: {e}")

# --- HELPER: SECURITY CHECK ---
def _check_auth(update: Update) -> bool:
    if not update.effective_user: return False
    user_id = update.effective_user.id
    if user_id in ALLOWED_USERS:
        return True
    return False

# --- MODUL 1.5: ERROR HANDLER ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log error yang disebabkan oleh Update."""
    import logging
    
    # Filter error umum biar log gak penuh sampah
    if isinstance(context.error, (NetworkError, TimedOut)):
        logging.warning(f"⚠️ [NETWORK] Gangguan koneksi ke Telegram: {context.error}. Retrying...")
    else:
        # Log error serius lainnya
        logging.error("Exception while handling an update:", exc_info=context.error)

# --- MODUL 2: TELEGRAM BOT LISTENER (INBOUND via Asyncio) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    await update.message.reply_text('🌱 Demeter Core Online. Ketik /status untuk cek kondisi.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    try:
        with open("help_interface.txt", "r", encoding="utf-8") as f:
            help_text = f.read()
    except Exception as e:
        help_text = "⚠️ Help file missing."
        print(f"[ERROR] Missing help_interface.txt: {e}")
        
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    start_time = time.time()
    msg = await update.message.reply_text("🏓 Pinging...")
    end_time = time.time()
    latency_ms = (end_time - start_time) * 1000
    await msg.edit_text(f"🏓 *Pong!*\nLatency: `{latency_ms:.2f}ms`", parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    global COMMAND_QUEUE
    
    # 1. Kirim Pesan Loading
    await update.message.reply_text("⏳ **Permintaan Diterima.**\nMenunggu laporan ESP32 & Analisa AI...", parse_mode='Markdown')
    
    # 2. Masukkan perintah ke antrian beserta CHAT ID pengirim
    COMMAND_QUEUE = {
        "action": "ANALYZE", 
        "duration": 0, 
        "chat_id": update.message.chat_id 
    }

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Discuss with Demeter (Reasoning Engine)."""
    if not _check_auth(update): return

    if not context.args:
        await update.message.reply_text("ℹ️ **Penggunaan:** `/chat [pesan]`", parse_mode="Markdown")
        return
        
    user_name = update.effective_user.first_name if update.effective_user else "User"
    user_msg = " ".join(context.args)
    
    try:
        # 1. Initialize Memory Manager
        brain = GaiaBrain()

        # [ACTIVE MEMORY] 📝 Record user interaction
        if len(user_msg) > 5:
            brain.record(text=user_msg, user_name=user_name, source="user_chat", tags=f"demeter, user_chat_{update.effective_user.id}")

        # 2. Prepare System Persona
        persona_path = "persona_demeter.md"
        system_persona = "You are Demeter, the Garden AI."
        
        if os.path.exists(persona_path):
            with open(persona_path, "r", encoding="utf-8") as f:
                system_persona = f.read()
        
        # Inject dynamic sender name if present in template
        system_persona = system_persona.replace("{sender}", user_name)

        # Notify user
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # 3. Generate Response (LangChain)
        # Demeter specific filter
        reply = await brain.chat_with_langchain(
            query=user_msg,
            system_persona=system_persona,
            user_name=user_name,
            filter_type="demeter"
        )
        
        await update.message.reply_text(reply)

        # [ACTIVE MEMORY] 📝 Record Demeter's Reply
        if len(reply) > 20:
             brain.record(text=f"DEMETER to {user_name}: {reply}", user_name="Demeter", source="demeter_chat", tags=f"ai_response_{update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"Demeter Chat Error: {e}")
        await update.message.reply_text("⚠️ **Terjadi Kesalahan Komunikasi**")

def run_telegram_bot():
    # [GENESIS] Initialize Memory Manager at startup
    try:
        global_brain = GaiaBrain()
        logger.info(f"🧠 Demeter Memory Core initialized (Mode: {getattr(global_brain, 'mode', 'N/A')})")
    except Exception as e:
        logger.error(f"⚠️ Failed to initialize Memory Core at startup: {e}")

    print("[SYSTEM] Starting Telegram Bot Listener...")

    # Konfigurasi Request dengan Timeout LEBIH PANJANG (Badak Mode)
    request_config = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0
    )

    application = Application.builder().token(TELEGRAM_TOKEN).request(request_config).build()

    # Pasang Error Handler
    application.add_error_handler(error_handler)
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("chat", chat_command))
    
    # Run polling
    application.run_polling()

# --- MODUL 3: VISION ---
# --- MODUL 3: VISION ---
def cleanup_vision_folder(max_days=3, max_files=1000):
    """
    Menghapus foto lama agar disk tidak penuh.
    - Hapus file > max_days
    - Jika total file > max_files, hapus yang terlama.
    """
    try:
        if not os.path.exists(CAPTURE_DIR): return

        # 1. Age-based Cleanup
        now = time.time()
        cutoff = now - (max_days * 86400)
        
        files = glob.glob(os.path.join(CAPTURE_DIR, "*.jpg"))
        deleted = 0
        
        for f in files:
            if os.path.getmtime(f) < cutoff:
                try:
                    os.remove(f)
                    deleted += 1
                except: pass
        
        if deleted > 0:
            print(f"[CLEANUP] Deleted {deleted} old images (> {max_days} days).")

        # 2. Count-based Cleanup (Safety Net)
        files = sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.jpg")), key=os.path.getmtime)
        if len(files) > max_files:
            excess = len(files) - max_files
            for i in range(excess):
                try:
                    os.remove(files[i])
                except: pass
            print(f"[CLEANUP] Deleted {excess} excess images (Limit: {max_files}).")
            
    except Exception as e:
        print(f"[ERROR] Cleanup failed: {e}")

# Set Global Opencv Option once
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

def capture_visual():
    # [OPTIMIZATION] Removed aggressive GC. Python handles this well enough.
    print("[VISION] Capture sequence started...")
    
    cap = None
    filepath = None
    
    try:
        if not os.path.exists(CAPTURE_DIR):
            os.makedirs(CAPTURE_DIR)
            
        # Run cleanup probability (10% chance) to avoid overhead every call
        if __import__("random").random() < 0.1:
            cleanup_vision_folder()

        cap = cv2.VideoCapture(RTSP_URL)
        # [MEMORY FIX] Set Buffer Size to 1 to prevent FFmpeg RAM accumulation
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            print("[ERROR] RTSP Fail.")
            return None
        
        # Warmup (Shortened to minimal)
        cap.read() 
        ret, frame = cap.read()
        
        if ret and frame is not None:
            timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{timestamp_str}.jpg"
            filepath = os.path.join(CAPTURE_DIR, filename)
            # [OPTIMIZATION] Compress quality to 80 to save disk
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return filepath
        return None
        
    except Exception as e:
        print(f"[ERROR] Vision Crash: {e}")
        return None
        
    finally:
        if cap:
            try:
                cap.release()
            except: pass

# --- MODUL 4: LOGGING ---
def log_data(moisture, temp, action, img_path="None"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{timestamp},{moisture},{temp},{action},{img_path}\n"
    try:
        # Pindahkan logika create dir jika belum ada
        log_dir = os.path.dirname(DB_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        if not os.path.exists(DB_FILE):
            with open(DB_FILE, "w") as f:
                f.write("timestamp,moisture,temp,action,image_path\n")
        with open(DB_FILE, "a") as f:
            f.write(entry)
    except Exception as e:
        print(f"[ERROR] Logging failed: {e}")

# --- MODUL 5: OTAK GEMINI (COMPARATIVE MODE) ---
def consult_demeter(moisture, temp, current_img, prev_img):
    print(f"[DEMETER] Analisa Komparatif dimulai...")
    
    # 1. Load Persona dari File Eksternal (Markdown Preferred)
    persona_text = ""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    persona_md_path = os.path.join(current_dir, "persona_demeter.md")
    legacy_persona_path = os.path.join(current_dir, "prompt_persona.txt")

    try:
        if os.path.exists(persona_md_path):
            with open(persona_md_path, "r", encoding="utf-8") as f:
                persona_text = f.read()
        elif os.path.exists(legacy_persona_path):
             with open(legacy_persona_path, "r", encoding="utf-8") as f:
                persona_text = f.read()
    except Exception as e:
        print(f"[SYSTEM WARN] Gagal baca persona: {e}. Menggunakan default.")
        persona_text = "Bertindaklah sebagai asisten kebun. Analisa apakah tanaman butuh air berdasarkan foto dan sensor."

    # Validasi input
    if not current_img:
        print("[AI] Foto tidak ditemukan.")
        return {"action": "DIAM", "duration_sec": 0, "reason": "No Image"}

    # 2. Gabungkan Persona (Dinamis) + Instruksi Teknis (Hardcoded)
    prompt = f"""
    {persona_text}
    
    =========================================
    📊 DATA AKTUAL KEBUN:
    - Moisture Sensor: {moisture}%
    - Suhu Udara: {temp}°C
    =========================================
    
    ⚠️ INSTRUKSI SISTEM (JANGAN DIUBAH):
    Jawab HANYA dengan JSON valid. Tanpa markdown ```json.
    Format Wajib:
    {{
        "action": "SIRAM" atau "DIAM",
        "duration_sec": 5,
        "reason": "Paragraf analisa lengkap (3-4 kalimat) berdasarkan panduan visual di atas. Sertakan observasi daun dan tanah."
    }}
    """
    
    inputs = [prompt]
    
    # Load Gambar 1 (Lama)
    if prev_img and os.path.exists(prev_img):
        try:
            img1 = Image.open(prev_img)
            inputs.append(img1)
        except: pass

    # Load Gambar 2 (Baru)
    if current_img and os.path.exists(current_img):
        try:
            img2 = Image.open(current_img)
            inputs.append(img2)
        except: pass

    
    # [POLYGLOT FORCE UPDATE]
    try:
        # Gunakan API_KEY_LIST untuk Rotasi / Failover
        keys_to_try = API_KEY_LIST if API_KEY_LIST else [LLM_API_KEY]
        
        # Helper to encode (defined once)
        def encode_image(image_path):
            import base64
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        last_error = None
        
        for attempt, api_key_val in enumerate(keys_to_try):
            try:
                # 2. Panggil LiteLLM
                # Construct Messages RE-FRESH per attempt if needed? 
                # No, messages input is static, just the key changes.
                
                messages = [
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt}
                    ]}
                ]
                
                # Add Images if available
                if prev_img and os.path.exists(prev_img):
                    try:
                        b64 = encode_image(prev_img)
                        messages[0]["content"].append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                        })
                    except: pass
        
                if current_img and os.path.exists(current_img):
                    try:
                        b64 = encode_image(current_img)
                        messages[0]["content"].append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                        })
                    except: pass
        
                response = completion(
                    model=LLM_MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    api_key=api_key_val # <--- ROTATING KEY
                )
                
                # 3. Ambil teks jawaban
                # 3. Ambil teks jawaban
                raw_response = response.choices[0].message.content
                ai_json = json.loads(raw_response)
                
                # [MEMORY RECORDING - ALL LLM USAGE]
                try:
                    brain = GaiaBrain()
                    # Capture reasoning specifically
                    reasoning_text = ai_json.get("reason", "No reasoning provided.")
                    # Format: ACTION | Reason
                    # [SEMANTIC BOOST] Add explicit context for retrieval
                    mem_text = f"DEMETER STATUS REPORT: Action={ai_json.get('action')} | Condition: {reasoning_text}"
                    # [TAG FIX] Add 'demeter' for entity filtering
                    brain.record(text=mem_text, user_name="DemeterAI", source="demeter_ai_brain", tags="demeter, ai_consultation, decision")
                    print("[MEMORY] AI Reasoning saved to Core.")
                except Exception as mem_err:
                    print(f"[ERROR] AI Memory Save Failed: {mem_err}")

                return ai_json
                
            except Exception as e:
                print(f"⚠️ Attempt {attempt+1} failed: {e}")
                last_error = e
                import time; time.sleep(1)
        
        # If all keys failed
        raise last_error if last_error else Exception("All keys exhausted.")

    except Exception as e:
        print(f"⚠️ System Error: {str(e)}")
        # Return fallback json to prevent crash
        return {"action": "DIAM", "duration_sec": 0, "reason": f"AI Failure: {str(e)}"}

# --- FLASK SERVER (THREAD 1) ---
@app.route('/lapor', methods=['POST'])
def handle_report():
    global LATEST_DATA, LAST_LOG_TIME, NEXT_ANALYSIS_TIME, COMMAND_QUEUE
    
    try:
        # 1. Parsing Data
        data = request.json
        moist = int(data.get('moisture', 0))
        temp = float(data.get('temp', 0))
        
        current_time = datetime.now()
        
        # --- 2. INISIALISASI VARIABEL DEFAULT (PENTING!) ---
        # Ini mencegah error "UnboundLocalError" jika logic masuk ke jalur skip/busy
        action = "DIAM"
        duration = 0
        save_to_disk = False
        status_msg = "Ready"
        img_path = None
        
        # --- FITUR LIVE MONITOR (REQUEST USER) ---
        wait_msg = "READY"
        if current_time < NEXT_ANALYSIS_TIME:
            remaining = int((NEXT_ANALYSIS_TIME - current_time).total_seconds() / 60)
            wait_msg = f"WAIT {remaining}m"
        
        print(f"📡 [LIVE] Tanah: {moist}% | Suhu: {temp}C | {wait_msg}")

        # --- LOGIC PRIORITAS UTAMA: MANUAL COMMAND ---
        # Cek ini PALING AWAL sebelum Night Mode/Cooldown
        if COMMAND_QUEUE:
            cmd_action = COMMAND_QUEUE['action']
            
            # AMBIL TARGET CHAT ID (Untuk Balasan Manual)
            target_chat_id = COMMAND_QUEUE.get('chat_id', TELEGRAM_CHAT_ID)
            
            # Skenario A: Manual Siram (User ketik /siram 5)
            if cmd_action == "SIRAM":
                action = "SIRAM"
                duration = COMMAND_QUEUE['duration']
                NEXT_ANALYSIS_TIME = current_time + timedelta(hours=3) # Reset jadwal
                status_msg = "Manual Override: Watering"
                save_to_disk = True
                COMMAND_QUEUE = None # Clear
                print(f"[MANUAL] Memaksa siram {duration} detik.")

            # Skenario B: Manual Analisa (User ketik /status)

            elif cmd_action == "ANALYZE":
                print("[MANUAL] User meminta analisa saat ini...")
                COMMAND_QUEUE = None # Clear dulu biar gak loop
                
                try:
                    with AI_PROCESSING_LOCK:
                        # Lakukan Analisa Lengkap (Persis seperti Auto)
                        img_path = capture_visual()
                        
                        ai_result = consult_demeter(moist, temp, img_path, None)
                        
                        action = ai_result.get('action', 'DIAM')
                        duration = ai_result.get('duration_sec', 0)
                        
                        # Update Jadwal Masa Depan
                        if action == "SIRAM":
                            NEXT_ANALYSIS_TIME = current_time + timedelta(hours=HARD_COOLDOWN_HOURS)
                            status_msg = f"Manual Check: Watering (+{HARD_COOLDOWN_HOURS}h)"
                        else:
                            NEXT_ANALYSIS_TIME = current_time + timedelta(hours=SOFT_COOLDOWN_HOURS)
                            status_msg = f"Manual Check: OK/Skipped (+{SOFT_COOLDOWN_HOURS}h)"
                        
                        save_to_disk = True
                        
                        # Kirim Notif Telegram Hasilnya disini
                        # --- MENYUSUN LAPORAN LENGKAP ---
                        
                        # 1. Tentukan Pesan Keputusan
                        status_info = ""
                        if action == "SIRAM":
                            status_info = f"💦 MENYIRAM ({duration}s)"
                        else:
                            status_info = "🛑 DIAM (Visual Basah/Cukup)"
                        
                        # Ambil alasan dari AI
                        reason = ai_result.get('reason', 'Tidak ada analisa visual.')
                        
                        # 2. Hitung Jadwal Berikutnya
                        next_schedule = NEXT_ANALYSIS_TIME.strftime("%H:%M")
                        
                        # 3. Buat Caption Cantik
                        caption = (
                            f"🕵️‍♂️ **DEMETER MANUAL CHECK**\n"
                            f"Status: {status_info}\n\n"
                            f"🧠 **Analisa Agronomis:**\n{reason}\n\n"
                            f"🌱 Tanah: {moist}% | 🌡️ Suhu: {temp}°C\n"
                            f"⏳ Next: {next_schedule}"
                        )
                        
                        # 4. KIRIM KE TELEGRAM (Foto + Caption)
                        try:
                            print(f"[MANUAL] Mengirim laporan ke ID {target_chat_id}...")
                            url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                            url_msg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                            
                            # --- CEK APAKAH FOTO ADA? ---
                            if img_path:
                                # SKENARIO NORMAL: KIRIM FOTO
                                with open(img_path, 'rb') as photo_file:
                                    payload = {
                                        'chat_id': target_chat_id, 
                                        'caption': caption, 
                                        'parse_mode': 'Markdown'
                                    }
                                    files = {'photo': photo_file}
                                    requests.post(url_photo, data=payload, files=files)
                                print("[MANUAL] Foto laporan terkirim.")
                            
                            else:
                                # SKENARIO ERROR KAMERA: KIRIM TEKS SAJA
                                # Tambahkan warning di caption
                                caption += "\n\n⚠️ **WARNING:** Gagal mengambil bukti visual (Kamera Error/Offline)."
                                
                                payload = {
                                    'chat_id': target_chat_id, 
                                    'text': caption, 
                                    'parse_mode': 'Markdown'
                                }
                                requests.post(url_msg, data=payload)
                                print("[MANUAL] Laporan teks (tanpa foto) terkirim.")
                            
                            # [MEMORY RECORDING - SHORT TERM ONLY]
                            # RAG (Long-term) is already handled inside consult_demeter()
                            try:
                                # [NEW] Extract AI reason for short-term memory
                                clean_reason = reason.replace('\n', ' ').replace('*', '').replace('`', '').replace('_', ' ')
                                clean_reason = ' '.join(clean_reason.split())
                                reason_snippet = clean_reason[:8000] + '...' if len(clean_reason) > 8000 else clean_reason
                                update_short_memory("Manual Diagnosis (Visual)", f"Status: {status_info} | AI: {reason_snippet}")
                            except Exception as mem_err:
                                print(f"[ERROR] Memory Save Failed: {mem_err}")
                            
                        except Exception as e:
                            print(f"[TELEGRAM ERROR] Gagal kirim manual: {e}")
                            
                except TimeoutError:
                    print("[MANUAL SKIP] Server sedang sibuk (Lock Timeout).")
                    status_msg = "Server Busy (Timeout)"
                    
                except Exception as e:
                    print(f"[MANUAL ERROR] {e}")
                    status_msg = "Manual Check Failed"
                    print(traceback.format_exc())

            # Kembalikan JSON Action ke ESP32

            # Kembalikan JSON Action ke ESP32
            # Update RAM
            LATEST_DATA = {
                "moisture": moist, "temp": temp, "last_seen": current_time, 
                "action": action, "status": status_msg
            }
            # Log disk jika perlu
            if save_to_disk:
                 log_data(moist, temp, action, img_path)

            return jsonify({"action": action, "duration_sec": duration})

        # --- 1. CEK NIGHT MODE (Hemat Token & Sehat Buat Tanaman) ---
        current_hour = current_time.hour
        # Malam: 22:00 - 06:00
        is_night = current_hour >= NIGHT_START_HOUR or current_hour < NIGHT_END_HOUR
        
        if is_night:
             status_msg = "Night Mode (Sleep)"
             if current_time.minute == 0: 
                pass

             # Update RAM tetap jalan biar status terlihat
             LATEST_DATA = {
                "moisture": moist, "temp": temp, "last_seen": current_time,
                "action": "DIAM", "status": status_msg
             }
             return jsonify({"action": "DIAM", "duration_sec": 0})

        # --- 2. CEK COOLDOWN TIMER ---
        if current_time < NEXT_ANALYSIS_TIME:
            time_left = NEXT_ANALYSIS_TIME - current_time
            minutes_left = int(time_left.total_seconds() / 60)
            status_msg = f"Cooldown (Wait {minutes_left}m)"
            
            LATEST_DATA = {
                "moisture": moist, "temp": temp, "last_seen": current_time,
                "action": "DIAM", "status": status_msg
            }
            return jsonify({"action": "DIAM", "duration_sec": 0})

        # --- DETERMINASI TUGAS ---
        task_type = None
        # COMMAND QUEUE SUDAH DIHANDLE DIATAS
        
        if moist < MOISTURE_SAFETY_LIMIT:
             # Lolos Night & Cooldown -> Cek Moisture
            task_type = 'AUTO'
        elif (current_time - LAST_LOG_TIME).total_seconds() > 3600:
            task_type = 'HEARTBEAT'

        # --- EKSEKUSI DENGAN GLOBAL LOCK ---
        if task_type:
            # [OPTIMIZATION] Use Context Manager for safety
            try:
                with AI_PROCESSING_LOCK:
                    # [CRITICAL] OPTIMISTIC TIMER UPDATE
                    if task_type == 'HEARTBEAT':
                        print("[HEARTBEAT] Memulai log rutin...")
                        LAST_LOG_TIME = current_time
                        status_msg = "Hourly Log"
                    
                    elif task_type == 'AUTO':
                        print(f"[AUTO] Sensor ({moist}%) -> Memulai Analisa...")
                        status_msg = "AI Analyzing..."

                    # HEAVY PROCESSING
                    img_path = capture_visual()
                    
                    save_to_disk = False

                    # LOGIC PER TIPE TUGAS
                    if task_type == 'AUTO':
                        # Tanya Gemini
                        ai_result = consult_demeter(moist, temp, img_path, None)
                        action = ai_result.get('action', 'DIAM')
                        duration = ai_result.get('duration_sec', 0)
                        
                        print(f"[AI DECISION] Gemini: {action}")
                        
                        # --- PENENTUAN JADWAL BERIKUTNYA ---
                        if action == "SIRAM":
                            # HARD COOLDOWN: 3 JAM
                            NEXT_ANALYSIS_TIME = current_time + timedelta(hours=HARD_COOLDOWN_HOURS)
                            status_msg = f"AI: Watering (Next: +{HARD_COOLDOWN_HOURS}h)"
                            save_to_disk = True
                        else:
                            # SOFT COOLDOWN: 2 JAM (Veto AI / Error)
                            NEXT_ANALYSIS_TIME = current_time + timedelta(hours=SOFT_COOLDOWN_HOURS)
                            status_msg = f"AI: Skipped (Next: +{SOFT_COOLDOWN_HOURS}h)"
                            save_to_disk = True
                    
                    elif task_type == 'HEARTBEAT':
                        save_to_disk = True
                        # Action default DIAM

                    # PENYIMPANAN & NOTIFIKASI
                    if save_to_disk:
                        log_data(moist, temp, action, img_path)
                        
                        # [NEW] Extract AI reason for short-term memory
                        if task_type == 'AUTO':
                            reason = ai_result.get('reason', 'Routine check')
                            clean_reason = reason.replace('\n', ' ').replace('*', '').replace('`', '').replace('_', ' ')
                            clean_reason = ' '.join(clean_reason.split())
                            reason_snip = clean_reason[:4000] + '...' if len(clean_reason) > 4000 else clean_reason
                            update_short_memory(f"Autonomous Action ({task_type})", f"Dec: {action} (M:{moist}%, T:{temp}C) | AI: {reason_snip}")
                        
                        if action == "SIRAM":
                            pesan = f"💦 **DEMETER ACTIVE** ({status_msg})\n🌱 Tanah: {moist}%\n🌡️ Suhu: {temp}°C"
                            try:
                                kirim_telegram_sync(pesan, img_path)
                            except Exception as tg_err:
                                print(f"[ERROR] Telegram fail: {tg_err}")

            except TimeoutError:
                 # Jika server sibuk / Lock Timeout
                print(f"[BUSY] Server sibuk memproses {task_type}. Skip.")
                status_msg = "Server Busy (Timeout)"
                action = "DIAM"

            except Exception as e:
                print(f"[PROCESS ERROR] {e}")
                # ERROR PENALTY (2 Jam)
                if task_type == 'AUTO':
                    print("[SAFETY] Force Cooldown due to Error.")
                    NEXT_ANALYSIS_TIME = current_time + timedelta(hours=SOFT_COOLDOWN_HOURS)
                    action = "DIAM"
                    status_msg = "Error -> Soft Cooldown"

        # Update Memory
        LATEST_DATA = {
            "moisture": moist, "temp": temp, "last_seen": current_time,
            "action": action, "status": status_msg
        }

        return jsonify({"action": action, "duration_sec": duration})

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
        print(traceback.format_exc())
        return jsonify({"action": "DIAM", "duration_sec": 0}), 500

def run_flask():
    print("[SYSTEM] Starting Flask Server (Daemon)...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# --- MAIN EXECUTION (THREAD MANAGER) ---
if __name__ == '__main__':
    print("--- DEMETER V6.1 (ENV INTEGRATED) ONLINE ---")
    
    # 1. Jalankan Flask di Thread Terpisah (Daemon)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 2. Jalankan Telegram Bot di Main Thread (Asyncio Loop)
    try:
        start_midnight_cleanup_scheduler()
        run_telegram_bot()
    except KeyboardInterrupt:
        print("[SYSTEM] Shutting down...")
