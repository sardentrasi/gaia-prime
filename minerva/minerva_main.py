import os
import sys
import logging
import re
import json
import shutil
import asyncio
import glob
import subprocess
import pytz
import requests
import threading
from flask import Flask, request, jsonify
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient, events
from litellm import completion
# from google import genai
# from google.genai import types
from PIL import Image
import mimetypes

# Load .env early
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
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), "minerva.log"), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("Minerva")

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
    from minerva_memory_manager import GaiaBrain
    logger.info("🧠 Minerva Memory Manager (Local + Central Sync) connected.")
except ImportError as e:
    logger.error(f"⚠️ [SURVIVAL MODE] Local Memory Manager error: {e}")
    # Final Safety Net (Mock Class to prevent crash)
    class GaiaBrain:
        def __init__(self): pass
        def record(self, *args, **kwargs): return False
        def remember(self, *args, **kwargs): return ""

# --- END LOGGING SETUP ---

# GLOBAL LOCK to prevent simultaneous reads/writes
LEDGER_LOCK = asyncio.Lock()

load_dotenv()
TIMEZONE_NAME = os.getenv('TIMEZONE', 'Asia/Jakarta')
LOCAL_TZ = pytz.timezone(TIMEZONE_NAME)

def log_system(message, type="INFO"):
    """Wrapper: Routes legacy log_system calls to standard logger."""
    if type == "ERROR":
        logger.error(f"❌ {message}")
    elif type == "WARN":
        logger.warning(f"⚠️ {message}")
    elif type == "SUCCESS":
        logger.info(f"✅ {message}")
    elif type == "NETWORK":
        logger.info(f"📡 {message}")
    elif type == "AI":
        logger.info(f"🧠 {message}")
    else:
        logger.info(f"ℹ️ {message}")

# Client A: Userbot (Spy)
API_ID = os.getenv('TG_API_ID')
API_HASH = os.getenv('TG_API_HASH')
SOURCE_BOT = os.getenv('SOURCE_BOT_USERNAME', 'dlquant_bot')

# Client B: Bot API (Commander)
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_USER_ID')
if not ADMIN_ID:
    ADMIN_ID = os.getenv('TELEGRAM_CHAT_ID')
    # Filter quotes if present
    if ADMIN_ID: ADMIN_ID = ADMIN_ID.replace('"', '').replace("'", "")

# [MULTI-USER ACCESS]
users_str = os.getenv("USERS_ALLOWED", "")
ALLOWED_USERS = [int(x) for x in users_str.split(',') if x.strip().isdigit()]
# Ensure Owner is always Admin
if ADMIN_ID and int(ADMIN_ID) not in ALLOWED_USERS:
    ALLOWED_USERS.append(int(ADMIN_ID))
print(f"[SECURITY] Whitelisted Users: {ALLOWED_USERS}")

# --- GLOBAL STATE ---
main_loop = None



async def push_telegram_notification(text, image_path=None):
    """
    Sends message to Telegram.
    """
    try:
        if ADMIN_ID:
            if image_path and os.path.exists(image_path):
                await bot_client.send_file(int(ADMIN_ID), image_path, caption=text)
            else:
                await bot_client.send_message(int(ADMIN_ID), text)
            log_system("Telegram notification delivered.", "SUCCESS")
    except Exception as e:
        log_system(f"Telegram Delivery failed: {e}", "ERROR")

def check_auth(event):
    """Checks if sender is authorized."""
    try:
        if not event.sender_id: return False
        return int(event.sender_id) in ALLOWED_USERS
    except: return False

# AI Credentials (POLYGLOT MODE)
# LOAD KEYS AS A LIST
# LiteLLM automatically handles API keys if set in environment (LLM_API_KEY)
# We just need to load the model name.

# [STANDARDIZATION] LLM_MODEL
LLM_MODEL = os.getenv('LLM_MODEL', 'gemini/gemini-2.5-flash')
print(f"🧬 Polyglot Engine Active. Model: {LLM_MODEL}")

# [STANDARDIZATION] LLM_API_KEY
# [STANDARDIZATION] LLM_API_KEY (STRICT)
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    print("CRITICAL: LLM_API_KEY missing. AI features will fail.")

# [RESTORATION] API_KEY_LIST for Rotation
# Support comma-separated keys for load balancing/rotation
API_KEY_LIST = [k.strip() for k in LLM_API_KEY.split(',') if k.strip()] if LLM_API_KEY else []

# Load Library Config
# Default to False if not set, to prevent quota errors
USE_LIBRARY_JOBS = os.getenv("USE_LIBRARY_JOBS", "false").strip().lower() == "true"

if USE_LIBRARY_JOBS:
    print(f"📚 Library Feature is ON for Scheduled Jobs (Model: {LLM_MODEL})")
else:
    print(f"🚫 Library Feature is OFF for Scheduled Jobs (Chart-Only Mode).")

user_client = TelegramClient('session_user', int(API_ID), API_HASH)
bot_client = TelegramClient('session_bot', int(API_ID), API_HASH)

print(f"🛡️ Minerva Hybrid: On-Demand & Scheduled Analysis Active (Model: {LLM_MODEL})...")

# [GLOBAL PATHS]
HARVEST_DIR = os.getenv("HARVEST_DIR", "harvested_data")
BRAIN_FILE = "brain.md"
CURRENT_KEY_INDEX = 0

# --- Define Protocol (Hardcoded) ---
# Removed hardcoded JSON_PROTOCOL_SUFFIX. Now natively handled by brain.md template.

# ================= CORE LOGIC (REUSABLE) =================
# ================= CORE LOGIC (REUSABLE) =================
def get_brain():
    """Safely load the main brain file (Markdown)."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    content = load_brain_file(os.path.join(current_dir, BRAIN_FILE))
    return content if content else "Role: Stock Analyst. Task: Analyze this ticker."

def load_brain_file(filename):
    """Safely load a specific brain file (e.g., brainm.md, brainw.md)."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f: return f.read()
        except Exception as e:
            log_system(f"⚠️ Failed to read {filename}: {e}", "WARN")
            return None
    return None

# --- Helper: Ledger Manager ---
async def load_ledger_safe():
    """Thread-safe and error-tolerant ledger loader."""
    LEDGER_FILE = os.path.join(os.getcwd(), "ledger.json")
    async with LEDGER_LOCK:
        if not os.path.exists(LEDGER_FILE):
            return []
        
        try:
            with open(LEDGER_FILE, "r") as f:
                data = f.read().strip()
                if not data: return [] # Handle empty file
                return json.loads(data)
        except json.JSONDecodeError:
            log_system("⚠️ JSON Decode Error encountered. Returning empty list (No Reset yet).", "WARN")
            return []
        except Exception as e:
            log_system(f"❌ Read Error: {e}", "ERROR")
            return []

async def save_ledger_safe(data):
    """Atomic Write: Writes to temp file first, then renames. Prevents corruption."""
    if not isinstance(data, list):
        log_system("❌ Attempted to save invalid data format (not list). Aborted.", "ERROR")
        return

    LEDGER_FILE = os.path.join(os.getcwd(), "ledger.json")
    async with LEDGER_LOCK:
        try:
            # 1. Write to temp file
            temp_file = f"{LEDGER_FILE}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # 2. Atomic Move (Instant replacement)
            shutil.move(temp_file, LEDGER_FILE)
            # log_system("Ledger saved atomically.", "INFO") # Optional verbose
            return True
        except Exception as e:
            log_system(f"❌ Save Error: {e}", "ERROR")
            return False

# --- Helper: Ledger Manager (Legacy Wrapper / Refactored) ---
async def save_to_ledger(ticker, raw_json_str, local_folder_path=None):
    try:
        # 1. Parse Data
        data = json.loads(raw_json_str)
        
        # Add Metadata
        data['created_at'] = datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
        data['ticker'] = ticker.upper()
        
        # ─── SAFETY NET: 5% MINIMUM UPSIDE FOR BUY ───
        # Override BUY → WAIT if upside is below 5%
        if data.get('signal', '').upper() == 'BUY':
            try:
                last_price = float(data.get('last_price', 0))
                target_price = float(data.get('target_price', 0))
                
                if last_price > 0 and target_price > 0:
                    upside_pct = ((target_price - last_price) / last_price) * 100
                    data['upside_pct'] = round(upside_pct, 2)
                    
                    if upside_pct < 5.0:
                        data['signal'] = 'WAIT'
                        data['signal_override'] = f'BUY→WAIT (upside {upside_pct:.1f}% < 5% minimum)'
                        log_system(f"⚠️ [{ticker}] BUY overridden to WAIT — upside only {upside_pct:.1f}% (min 5%)", "WARN")
                    else:
                        log_system(f"✅ [{ticker}] BUY validated — upside {upside_pct:.1f}%", "INFO")
            except (ValueError, TypeError) as e:
                log_system(f"⚠️ [{ticker}] Could not validate upside: {e}", "WARN")
        # ─── END SAFETY NET: 5% MINIMUM UPSIDE FOR BUY ───


        # 2. SAVE TO CENTRAL LEDGER (Root)
        ledger = await load_ledger_safe()
        ledger.append(data)
        await save_ledger_safe(ledger)

        # 3. SAVE TO LOCAL ARCHIVE (Inside Stock Folder)
        if local_folder_path and os.path.exists(local_folder_path):
            local_file = os.path.join(local_folder_path, "analysis_result.json")
            with open(local_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        return True
    except Exception as e:
        log_system(f"⚠️ Ledger Save Error: {e}", "ERROR")
        return False

# --- Helper: History Reader ---
async def get_ticker_history(ticker):
    ledger = await load_ledger_safe()
    if not ledger: return None
    
    try:
        # Filter for this ticker
        # Assuming ledger is a list of dicts. We want the latest one.
        relevant = [entry for entry in ledger if entry.get('ticker') == ticker]
        
        if not relevant: return None
        
        # Get the very last entry (assuming append order is chronological)
        last_entry = relevant[-1]
        return last_entry
    except Exception as e:
        log_system(f"⚠️ History Read Error: {e}", "ERROR")
        return None

async def get_img(conv, command, output_path):
    log_system(f"Requesting: {command}", "NETWORK")
    
    try:
        # 1. Send Command
        await conv.send_message(command)
        
        # 2. Wait for Response
        # Timeout increased to 30s for slower chart bots
        response = await conv.get_response(timeout=240) 
        
        # 3. UNIVERSAL VALIDATION LOGIC
        
        # PRIORITY 1: Check for Photo (Success Case)
        # Even if it has a caption (text), as long as it has media, we take it.
        if response.media and hasattr(response.media, 'photo'):
            # SUCCESS: It is a photo
            # FIX: Use the response's own download method (Correct Client Context)
            await response.download_media(file=output_path)
            log_system(f"Saved: {output_path}", "SUCCESS")
            return output_path
            
        # PRIORITY 2: Check for Text Only (Failure Case)
        # If we are here, it means NO PHOTO was found.
        elif response.text:
            # We don't care what the text says. No photo = No chart.
            # Log the first 50 chars just for debug info.
            reason = response.text.replace('\n', ' ')[:50]
            log_system(f"⚠️ Harvest Failed ({command}). Bot replied text: '{reason}...' ", "WARN")
            return None
            
        else:
            # PRIORITY 3: Empty/Weird Response
            log_system(f"⚠️ Unknown response type for {command}. Skipping.", "WARN")
            return None

    except asyncio.TimeoutError:
        log_system(f"Timeout waiting for {command}", "WARN")
        return None
        
    except asyncio.TimeoutError:
        log_system(f"Timeout waiting for {command}", "WARN")
        return None
        
    except (asyncio.InvalidStateError, asyncio.CancelledError) as e:
        log_system(f"Race condition (InvalidState/Cancelled) for {command}: {e}. Ignoring.", "WARN")
        return None
        
    except Exception as e:
        log_system(f"Harvest Error ({command}): {e}", "ERROR")
        return None

# --- Helper: Gemini Caching ---
ACTIVE_CACHE_NAME = None

def setup_library_cache():
    # [POLYGLOT MODE]

    print("ℹ️ Library Cache disabled in Polyglot Mode.")
    return None

async def perform_analysis(ticker, destination_id, source_type="manual", use_library=False, timeframe="daily"):
    """
    Main logic: Harvests data for a single ticker and sends report to destination_id.
    source_type: 'manual' or 'scheduled' for folder organization
    timeframe: 'daily' or 'weekly'
    """
    log_system(f"--- Analysis Start: {ticker} ({source_type}) ---", "INFO")
    ticker = ticker.upper()
    progress_msg = None
    
    # Setup Folder
    today = datetime.now(LOCAL_TZ).strftime('%Y-%m-%d')
    folder_type = "manual" if source_type == "manual" else source_type
    stock_path = os.path.join(HARVEST_DIR, today, folder_type, ticker)
    os.makedirs(stock_path, exist_ok=True)

    # Logic Check for Library Usage
    final_use_library = use_library
    
    # Safety: If using a model known to have 0 cache limit (like 2.5-flash free), force False
    if "2.5" in LLM_MODEL and "flash" in LLM_MODEL:
        if final_use_library:
            log_system("⚠️ Model 2.5 detected. Forcing Library OFF to prevent Crash.", "WARN")
            final_use_library = False

    if final_use_library:
        pass # Will check cache later
    else:
        log_system("⏩ Skipping Library Upload (Config=False). Analyzing Chart Only.", "INFO")

    if timeframe == "weekly":
        commands = [
            ("/vpew", "vpew.jpg"),     # Weekly Price & Volume
            ("/piv", "piv.jpg"),       # Pivot Points (Daily Fallback)
            ("/vbpw", "vbpw.jpg"),     # Weekly Supply/Demand
            ("/wstar", "wstar.jpg"),   # Weekly Rotation/Momentum
            ("/wspeedo", "wspeedo.jpg"),# Weekly Fear/Greed
            ("/dom", "dom.jpg"),       # Bandarmology (Daily Fallback)
            ("/tren", "tren.jpg")      # Auto-Trendlines (Daily Fallback)
        ]
        img_order_str = "VPEW, VBPW, WSTAR, WSPEEDO, PIV, DOM, Tren"
    else:
        commands = [
            ("/vpe", "vpe.jpg"),       # Price & Volume
            ("/piv", "piv.jpg"),       # Pivot Points
            ("/vbp", "vbp.jpg"),       # Supply/Demand
            ("/star", "star.jpg"),     # Rotation/Momentum
            ("/speedo", "speedo.jpg"), # Fear/Greed
            ("/dom", "dom.jpg"),       # NEW: Bandarmology (Foreign vs Local)
            ("/tren", "tren.jpg")      # NEW: Auto-Trendlines
        ]
        img_order_str = "VPE, PIV, VBP, Star, Speedo, DOM, Tren"
    
    required = [fname for _, fname in commands]
    missing = [f for f in required if not (os.path.exists(os.path.join(stock_path, f)) and os.path.getsize(os.path.join(stock_path, f)) > 0)]
    
    # UI: Initial Message
    initial_text = f"🔍 **Menganalisa {ticker}...**\n" + (f"(Using cached data 📂)" if not missing else f"⏳ Sedang mengambil data satelit ({SOURCE_BOT})...")
    
    if destination_id:
        try:
            progress_msg = await bot_client.send_message(destination_id, initial_text)
        except Exception as e:
            log_system(f"Telegram Initial Msg Failed: {e}", "ERROR")
    
    log_system(f"Harvesting images for {ticker}...", "NETWORK")
    photos = []
    
    # Harvest Images (Using Userbot)
    async with user_client.conversation(SOURCE_BOT) as conv:
        for cmd, fname in commands:
            fpath = os.path.join(stock_path, fname)
            
            # Skip if already exists
            if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                log_system(f"Cached: {fname}", "INFO")
                photos.append(Image.open(fpath))
                continue

            res = await get_img(conv, f"{cmd} {ticker}", fpath)
            if res: 
                photos.append(Image.open(res))
            else:
                log_system(f"Failed to get {cmd} for {ticker}", "WARN")
            await asyncio.sleep(1.5)
    
    # READ HISTORY (Memory Injection)
    history_data = await get_ticker_history(ticker)
    history_context = ""
    if history_data:
        history_context = f"""\n[HISTORICAL CONTEXT]\nPrevious analysis on {history_data.get('created_at', 'Unknown')}.\nSignal: {history_data.get('signal', 'N/A')}, Price: {history_data.get('last_price', 0)}."""

    # --- MARKET CONTEXT INJECTION (NEW) ---
    market_ctx = ""
    active_ctx_path = os.path.join(HARVEST_DIR, "market_context", "active")
    
    # Read Weekly (Major Trend)
    try:
        with open(os.path.join(active_ctx_path, "context_weekly.json"), 'r') as f:
            w_data = json.load(f)
            market_ctx += f"\n[MARKET CONTEXT - WEEKLY (Major Trend)]\n{w_data.get('summary', '-')}\n"
    except: pass
    
    # Read Daily (Current Mood)
    try:
        with open(os.path.join(active_ctx_path, "context_daily.json"), 'r') as f:
            d_data = json.load(f)
            market_ctx += f"\n[MARKET CONTEXT - DAILY (Today's Sentiment)]\n{d_data.get('summary', '-')}\n"
    except: pass

    # Analyze & Report (NEW SDK LOGIC)
    log_system(f"Sending {len(photos)} images + prompts to Gemini...", "AI")
    
    # Prepare Prompt & Instructions
    market_ctx_inject = market_ctx if market_ctx else ""
    system_instruction = get_brain()
    
    if len(photos) > 0:
        final_prompt = f"{market_ctx_inject}\n{history_context}\n\nTask: Analyze {ticker} ({timeframe} timeframe) based on the {len(photos)} images provided (Order: {img_order_str})."
    else:
        log_system(f"⚠️ Proceeding with TEXT-ONLY analysis for {ticker} (No charts fetched).", "WARN")
        final_prompt = f"{market_ctx_inject}\n{history_context}\n\nTask: Analyze {ticker} ({timeframe} timeframe) based ONLY on available market context and history since chart images failed to load from the source bot. Provide the best estimation possible."



    global CURRENT_KEY_INDEX

    res = None
    # Gunakan API_KEY_LIST yang sudah dipulihkan
    key_count = len(API_KEY_LIST) if API_KEY_LIST else 1
    
    # Collect valid image paths for LangChain (Empty list is fine)
    valid_image_paths = []
    for cmd, fname in commands:
        fpath = os.path.join(stock_path, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            valid_image_paths.append(fpath)

    try:
        # [LANGCHAIN UPGRADE]
        brain = GaiaBrain()
        
        # UI Update
        if progress_msg:
            if len(photos) > 0:
                await progress_msg.edit(f"🧠 **Menganalisa {ticker}...**\n⏳ Gemini sedang berpikir (LangChain + RAG)...")
            else:
                await progress_msg.edit(f"⚠️ **Image Fetch Timeout!**\n🧠 Tetap Menganalisa {ticker} (Text-Only Fallback)...")
        
        # 1. RAG Retrieve (Manual Book Search)
        rag_context = "[LIBRARY OFF] Reference System Persona only."
        if final_use_library:
            log_system("📚 Searching library for: Wyckoff VSA Theory (Accumulation/Distribution)...", "AI")
            # [FIX] Force Generic Theory Search (Ignore Ticker Name)
            # The books contain theory, not specific stock data.
            rag_context = brain.get_rag_context("Wyckoff VSA accumulation distribution analysis theory supply test")
            
            if rag_context: 
                log_system("✅ RAG Context Found (Theory Loaded).", "AI")
            else:
                # [FIX] If no book found, DO NOT fallback to random memory.
                # Just use the System Brain (brain.md) which is already loaded as system_persona.
                rag_context = "[NO BOOK DATA] Relying on internal System Persona (brain.md)."
                log_system("⚠️ RAG Empty. Using System Persona only.", "WARN")
        
        # 2. Call Unified Chat Engine
        full_response = await brain.chat_with_langchain(
            query=final_prompt,
            system_persona=system_instruction,
            user_name=f"Minerva_Analyst_{ticker}",
            filter_type="technical_knowledge", # [FIX] Restrict Fallback Memory to Technical Data
            context_override=rag_context, # Pass Book Context here
            image_paths=valid_image_paths
        )
        
        log_system("LangChain response received!", "SUCCESS")
        
    except Exception as e:
        error_str = str(e)
        log_system(f"❌ AI Error: {e}", "ERROR")
        if progress_msg:
            await progress_msg.edit(f"❌ **Error {ticker}:**\n{e}")
        return # Stop analysis on error

    # Process Response if Success (Legacy Wrapper Logic)
    if full_response:
        try:
            # full_response = res.choices[0].message.content (REMOVED, we have string now)
            
            # Extract & Save
            json_match = re.search(r'```json_data\n(.*?)\n```', full_response, re.DOTALL)
            ledger_saved = False
            
            if json_match:
                json_str = json_match.group(1)
                ledger_saved = await save_to_ledger(ticker, json_str, stock_path)
                
                # ─── 5% UPSIDE DISPLAY OVERRIDE ───
                # If BUY was overridden to WAIT in ledger, patch the display too
                try:
                    signal_data = json.loads(json_str)
                    last_p = float(signal_data.get('last_price', 0))
                    target_p = float(signal_data.get('target_price', 0))
                    
                    if (signal_data.get('signal', '').upper() == 'BUY' 
                        and last_p > 0 and target_p > 0):
                        upside = ((target_p - last_p) / last_p) * 100
                        if upside < 5.0:
                            # Patch the visible report
                            full_response = full_response.replace(
                                'Action: BUY', f'Action: WAIT ⚠️'
                            ).replace(
                                '"signal": "BUY"', '"signal": "WAIT"'
                            )
                            full_response += (
                                f"\n\n⚠️ **OVERRIDE**: Sinyal diubah BUY → WAIT\n"
                                f"📐 Kalkulasi: ({int(target_p)} - {int(last_p)}) / {int(last_p)} × 100 = **{upside:.2f}%**\n"
                                f"⛔ Minimum upside untuk BUY: 5.00%"
                            )
                            log_system(f"⚠️ [{ticker}] Report patched: BUY→WAIT (upside {upside:.2f}%)", "WARN")
                except Exception:
                    pass
            
            if ledger_saved:
                full_response += "\n\n📝 _Recorded to Ledger & Archive_"

            report = f"📊 **Analisa {ticker}:**\n{full_response}\n\n💾 _Data: {stock_path}_"

            # [MEMORY RECORDING] Standardized
            try:
                brain = GaiaBrain()
                # Simpan Analisa ke Memory Core
                brain.record(
                    text=report, 
                    user_name="Minerva", 
                    source="minerva_analysis", 
                    tags=f"minerva, market, stock_analysis, {ticker}, {source_type}"
                )
                log_system(f"💾 Analysis for {ticker} saved to Memory Core.", "SUCCESS")
            except Exception as mem_err:
                log_system(f"❌ Memory Save Error: {mem_err}", "ERROR")
            
            # Helper to split long messages (Use EDIT for first part)
            if progress_msg:
                if len(report) > 4000:
                    await progress_msg.edit(report[:4000])
                    for x in range(4000, len(report), 4000):
                        await bot_client.send_message(destination_id, report[x:x+4000])
                else:
                    await progress_msg.edit(report)
            elif source_type != "scheduled" and destination_id:
                # If not scheduled and no progress_msg (meaning it was triggered without a previous msg object), send new msg
                await bot_client.send_message(destination_id, report)

            log_system(f"Analysis for {ticker} complete. Sending to user.", "SUCCESS")
        
        except Exception as e:
            log_system(f"Post-Process Error: {e}", "ERROR")
            if progress_msg:
                await progress_msg.edit(f"❌ **Error {ticker}:**\nProcessing: {e}")
    
    
    for p in photos: p.close()

# ================= FEATURE 1: MARKET ANALYSIS & MANUAL COMMAND =================


async def analyze_market(timeframe="daily"):
    print(f"🌍 Running Market Analysis ({timeframe.upper()})...")

    # 1. Setup Paths
    today_str = datetime.now(LOCAL_TZ).strftime('%Y-%m-%d')
    
    # A. Archive Path (History)
    archive_path = os.path.join(HARVEST_DIR, "market_context", "archive", today_str)
    os.makedirs(archive_path, exist_ok=True)
    
    # B. Active Path (System Reference - Fixed Path)
    active_path = os.path.join(HARVEST_DIR, "market_context", "active")
    os.makedirs(active_path, exist_ok=True)
    
    # C. Configure Command & Filenames
    if timeframe == "weekly":
        commands = [
            ("/vpew", "chart_weekly_vpew.jpg"),
            ("/wspeedo", "chart_weekly_wspeedo.jpg")
        ]
        json_name = "context_weekly.json"
        prompt_context = "Timeframe: WEEKLY (Major Trend). Analyze the Composite index based on the 2 weekly charts provided (Price & Volume, Momentum Speedometer). Determine Major Support/Resistance & Structural Trend."
    elif timeframe == "monthly":
        commands = [
            ("/vpem", "chart_monthly_vpem.jpg"),
        ]
        json_name = "context_monthly.json"
        prompt_context = "Timeframe: MONTHLY (Macro Trend). Analyze the Composite index based on the monthly Wyckoff VPA chart provided. Determine the primary Macro Trend, phases of accumulation/distribution, and long-term Support/Resistance."
    else:
        commands = [
            ("/vpe", "chart_daily.jpg")
        ]
        json_name = "context_daily.json"
        prompt_context = "Timeframe: DAILY (Short-term Sentiment). Focus on today's candle, volume, and momentum."

    # 2. Harvest Images (Save to Archive First)
    has_image = False
    valid_active_paths = []
    
    async with user_client.conversation(SOURCE_BOT) as conv:
        for cmd, img_name in commands:
            archive_img_path = os.path.join(archive_path, img_name)
            
            # Request image from bot with increased latency tolerance
            res = await get_img(conv, f"{cmd} composite", archive_img_path)
            
            if res:
                # COPY Image to Active Folder (Overwrite)
                import shutil
                active_img_path = os.path.join(active_path, img_name)
                shutil.copy2(archive_img_path, active_img_path)
                valid_active_paths.append(active_img_path)
                has_image = True
                print(f"✅ Harvested market chart: {cmd} ({timeframe})")
            else:
                print(f"⚠️ Failed to harvest market chart: {cmd} ({timeframe})")
                
            # Crucial: Sleep 5 seconds to give dlquantbot time & avoid API limits
            await asyncio.sleep(5)

    if not has_image:
        print(f"⚠️ Proceeding TEXT-ONLY. All chart downloads failed for {timeframe}.")
        
    # 3. Analyze with Polyglot
    try:
        system_instruction = get_brain()
        
        if has_image:
            import base64
            def encode_image_path(path):
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode('utf-8')

            final_p = f"{prompt_context}\n\nTask: Analyze composite chart for {timeframe} trend. Role: {system_instruction}"
            
            content_list = [{"type": "text", "text": final_p}]
            
            # Attach all successfully downloaded images
            for path in valid_active_paths:
                b64_img = encode_image_path(path)
                content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}})
                
            messages = [{"role": "user", "content": content_list}]
        else:
            final_p = f"{prompt_context}\n\nTask: Analyze {timeframe} composite market outlook using ONLY your internal general knowledge since the chart fetch timed out. Provide the best estimation possible. Role: {system_instruction}"
            messages = [{"role": "user", "content": final_p}]
            
        # [POLYGLOT FORCE INJECT]
        api_key_val = LLM_API_KEY
        
        res_ai = completion(
            model=LLM_MODEL,
            messages=messages,
            api_key=api_key_val # <--- FORCE INJECT
        )
        # Img closed auto
        
        # 4. Save JSON to BOTH locations
        summary = res_ai.choices[0].message.content
        json_data = {
            "updated_at": str(datetime.now(LOCAL_TZ)), 
            "timeframe": timeframe,
            "summary": summary
        }
        
        # Save to Archive
        with open(os.path.join(archive_path, json_name), 'w') as f:
            json.dump(json_data, f, indent=2)
            
        # Save to Active (Overwrite)
        with open(os.path.join(active_path, json_name), 'w') as f:
            json.dump(json_data, f, indent=2)
        
        print(f"✅ Market Context Saved: {timeframe}")
        
        # [MEMORY RECORDING] Standardized
        try:
            brain = GaiaBrain()
            record_text = f"🌍 **IHSG MARKET OUTLOOK ({timeframe.upper()})**\n{summary}"
            brain.record(
                text=record_text, 
                user_name="Minerva", 
                source="market_analysis", 
                tags=f"minerva, market_outlook, composite, ihsg, {timeframe}"
            )
            print(f"💾 {timeframe.capitalize()} Market Context saved to Memory.")
            update_short_memory(f"Market Context ({timeframe.upper()})", f"Saved {timeframe} market outlook")
        except Exception as mem_err:
            print(f"❌ Market Memory Error: {mem_err}")

    except Exception as e:
        print(f"❌ Market AI Error: {e}")


@bot_client.on(events.NewMessage(pattern=r'/ingest'))
async def ingest_handler(event):
    if not check_auth(event): return
    # Use reply to get a message object we can edit later
    msg = await event.reply("📚 **Sedang membaca & menghafal buku (ChromaDB)...**\nMohon tunggu...")
    
    try:
        brain = GaiaBrain()
        # Library is in the SAME folder as minerva_main.py (minerva/library)
        lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library")
        
        # Run synchronous ingestion in a separate thread to prevent blocking the bot
        import asyncio
        res = await asyncio.to_thread(brain.ingest_library, lib_path)
        
        # EDIT the previous message instead of sending a new one
        await msg.edit(res)
    except Exception as e:
        await msg.edit(f"❌ Error: {e}")

@bot_client.on(events.NewMessage(pattern=r'/analyze (\S+)'))
async def manual_analyze_handler(event):
    sender = await event.get_sender()
    sender_name = getattr(sender, 'username', 'Unknown')
    ticker = event.pattern_match.group(1).upper()
    
    log_system(f"Command received from @{sender_name}: /analyze {ticker}", "INFO")
    
    if not check_auth(event): return

    # [VALIDATION] Indonesian stocks must be 4 letters (e.g. BBCA, TLKM)
    if len(ticker) != 4:
        log_system(f"Validation failed for {sender_name}: {ticker}", "WARN")
        await event.reply("⚠️ _Kode ticker saham Indonesia harus **4 huruf** (contoh: BBCA, TLKM)._")
        return

    log_system(f"Starting Manual Analysis for: {ticker}", "INFO")
    await perform_analysis(ticker, event.chat_id, source_type="manual", use_library=USE_LIBRARY_JOBS, timeframe="daily")

@bot_client.on(events.NewMessage(pattern=r'/wanalyze (\S+)'))
async def manual_wanalyze_handler(event):
    sender = await event.get_sender()
    sender_name = getattr(sender, 'username', 'Unknown')
    ticker = event.pattern_match.group(1).upper()
    
    log_system(f"Command received from @{sender_name}: /wanalyze {ticker}", "INFO")
    
    if not check_auth(event): return

    # [VALIDATION] Indonesian stocks must be 4 letters (e.g. BBCA, TLKM)
    if len(ticker) != 4:
        log_system(f"Validation failed for {sender_name}: {ticker}", "WARN")
        await event.reply("⚠️ _Kode ticker saham Indonesia harus **4 huruf** (contoh: BBCA, TLKM)._")
        return

    log_system(f"Starting Manual Weekly Analysis for: {ticker}", "INFO")
    await perform_analysis(ticker, event.chat_id, source_type="manual", use_library=USE_LIBRARY_JOBS, timeframe="weekly")

# ================= FEATURE 2: NIGHT SCHEDULER =================

def manage_tickers(ticker, action="save"):
    # USE ABSOLUTE PATH to prevent "wrong folder" issues
    TICKER_FILE = os.path.join(os.getcwd(), "daily_tickers.txt")
    
    current = set()
    
    # LOAD LOGIC with Robust Debugging
    if os.path.exists(TICKER_FILE):
        try:
            with open(TICKER_FILE, "r", encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Clean up invisible characters (BOM, whitespace)
                    clean_line = line.strip().upper().replace('\ufeff', '')
                    if clean_line and len(clean_line) == 4: # Valid tickers are usually 4 chars
                        current.add(clean_line)
        except Exception as e:
            log_system(f"❌ Error reading ticker file: {e}", "ERROR")
    else:
        log_system(f"⚠️ Ticker file not found at: {TICKER_FILE}", "WARN")

    if action == "save":
        if ticker:
            ticker = ticker.strip().upper()
            if ticker not in current:
                with open(TICKER_FILE, "a", encoding='utf-8') as f: 
                    f.write(f"{ticker}\n")
                return True
    
    elif action == "load": 
        # Convert set back to list for processing
        final_list = list(current)
        log_system(f"📂 Loaded {len(final_list)} tickers: {final_list}", "INFO")
        return final_list
        
    elif action == "clear": 
        if os.path.exists(TICKER_FILE): 
            open(TICKER_FILE, 'w').close()
            
    return False

async def night_analysis_job():
    log_system("🌙 Night Owl: Starting Scheduled Analysis...", "INFO")
    
    # FIX: Only setup cache if the feature is explicitly ENABLED
    if USE_LIBRARY_JOBS:
        log_system("📚 Library Mode Active: Initializing Cache...", "INFO")
        setup_library_cache()
    else:
        log_system("⏩ Library Mode OFF: Skipping Cache Upload (Safe Mode).", "INFO")
    
    try:
        # Load Tickers
        tickers = manage_tickers(None, "load")
        
        if not tickers: 
            log_system("⚠️ Night Job stopped: Ticker list is empty (manage_tickers returned []).", "WARN")
            if ADMIN_ID: 
                msg = "ℹ️ **Night Owl Report:**\nTidak ada sinyal 'ALERT/BUY' yang tertangkap hari ini.\nJadwal analisa dilewatkan (Safe Skip)."
                await push_telegram_notification(msg)
            return

        log_system(f"🚀 Processing {len(tickers)} tickers: {tickers}", "INFO")
        if ADMIN_ID: await push_telegram_notification(f"🚀 **Night Job:** Menganalisa {len(tickers)} saham...")
        
    except Exception as e:
        log_system(f"Error in night_analysis_job setup: {e}", "ERROR")
        if ADMIN_ID: await push_telegram_notification(f"❌ Night Owl Report Error: {e}")
        return

    log_system(f"Starting loop for {len(tickers)} tickers...", "INFO")

    for i, stock in enumerate(tickers):
        if ADMIN_ID:
            log_system(f"[{i+1}/{len(tickers)}] Processing {stock}...", "INFO")
            # If USE_LIBRARY_JOBS is False, perform_analysis will skip PDF uploading
            await perform_analysis(stock, int(ADMIN_ID), source_type="scheduled", use_library=USE_LIBRARY_JOBS)
        log_system("Cooldown 5s...", "INFO")
        await asyncio.sleep(5)
    
    manage_tickers(None, "clear")
    log_system("🌙 Night Analysis Finished.", "SUCCESS")
    if ADMIN_ID: await push_telegram_notification("✅ Nightly Job Complete.")

# --- INTERNAL TRIGGER SERVER (For Cross-Process) ---
trigger_app = Flask("MinervaTrigger")

@trigger_app.route('/trigger', methods=['POST'])
def trigger_analyze():
    try:
        data = request.get_json()
        ticker = data.get("ticker", "").upper()
        user_id = data.get("user_id", "")
        sender = data.get("sender", "")
        platform = data.get("platform", "telegram")
        timeframe = data.get("timeframe", "daily") # Added timeframe support
        
        if not ticker: return jsonify({"error": "No ticker"}), 400
        
        log_system(f"📡 [TRIGGER] Received request for {ticker} from {platform} ({timeframe})", "INFO")
        
        if main_loop:
            # Schedule the analysis in the main event loop
            asyncio.run_coroutine_threadsafe(
                perform_analysis(ticker, int(ADMIN_ID) if ADMIN_ID else None, source_type=platform, use_library=USE_LIBRARY_JOBS, timeframe=timeframe),
                main_loop
            )
            return jsonify({"status": "triggered", "ticker": ticker, "timeframe": timeframe}), 200
        else:
            return jsonify({"error": "Main event loop not ready"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_trigger_server():
    try:
        # Use a high port for internal trigger
        trigger_app.run(port=3015, host='127.0.0.1', debug=False)
    except Exception as e:
        log_system(f"❌ Trigger Server Error: {e}", "ERROR")

# --- Helper: Generate Report ---
# --- Helper: Generate Report --- 

# --- Helper: Generate Monthly Report (AI Powered) ---
async def generate_monthly_report():
    ledger = await load_ledger_safe()
    if not ledger: return "⚠️ Ledger belum ada data."

    try:
        # 1. Filter Current Month
        now = datetime.now(LOCAL_TZ)
        current_month_str = now.strftime('%Y-%m') 
        monthly_data = [d for d in ledger if d.get('created_at', '').startswith(current_month_str)]
        
        if not monthly_data: return f"ℹ️ Belum ada sinyal di bulan {now.strftime('%B %Y')}."

        # 2. Load brainm.md
        current_dir = os.path.dirname(os.path.abspath(__file__))
        brain_instruction = load_brain_file(os.path.join(current_dir, "brainm.md"))
        if not brain_instruction:
             brain_instruction = "Role: Auditor. Task: Audit this trading month strictly."

        # 3. Read Monthly Market Context
        market_ctx = ""
        active_ctx_path = os.path.join(HARVEST_DIR, "market_context", "active")
        try:
            with open(os.path.join(active_ctx_path, "context_monthly.json"), 'r') as f:
                m_data = json.load(f)
                market_ctx += f"\n[MARKET CONTEXT - MONTHLY (Macro Trend)]\n{m_data.get('summary', '-')}\n"
        except:
            pass

        # 4. Ask Gemini
        prompt = f"""
        {brain_instruction}
        
        [CURRENT MONTH]: {now.strftime('%B %Y')}
        {market_ctx}
        [MONTHLY LEDGER DATA]:
        {json.dumps(monthly_data, indent=2)}
        """

        log_system("Generating Monthly Audit via AI...", "AI")
        # [POLYGLOT FORCE INJECT]
        api_key_val = LLM_API_KEY
        res = completion(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], api_key=api_key_val)
        report_content = res.choices[0].message.content

        # [MEMORY RECORDING] Standardized
        try:
             brain = GaiaBrain() # [FIX] Ensure brain is initialized
             brain.record(text=report_content, user_name="Minerva", source="monthly_report", tags="minerva, monthly_audit, report")
             log_system("💾 Monthly Report saved to Memory.", "SUCCESS")
        except Exception as mem_err:
             log_system(f"Memory Save Error: {mem_err}", "ERROR")

        return report_content

    except Exception as e:
        log_system(f"Monthly Gen Error: {e}", "ERROR")
        return f"❌ Gagal generate report: {e}"

# --- Updated: Generate Weekly Strategy (AI Powered) ---
async def generate_weekly_report():
    ledger = await load_ledger_safe()
    if not ledger: return "⚠️ Ledger belum ada data."

    try:
        # 1. Filter Last 7 Days
        now = datetime.now(LOCAL_TZ)
        one_week_ago = now - timedelta(days=7)
        weekly_data = []
        for d in ledger:
            try:
                entry_date = datetime.strptime(d.get('created_at', ''), '%Y-%m-%d %H:%M:%S')
                entry_date = LOCAL_TZ.localize(entry_date)
                if entry_date >= one_week_ago: weekly_data.append(d)
            except: pass
            
        if not weekly_data: return "ℹ️ Tidak ada aktivitas trading minggu ini. Istirahat yang tenang."

        # 2. Get Market Context (From the JSON saved by analyze_market)
        market_summary = "Data Market Tidak Tersedia (Belum ada analisa mingguan)."
        try:
            ctx_path = os.path.join(HARVEST_DIR, "market_context", "active", "context_weekly.json")
            if os.path.exists(ctx_path):
                with open(ctx_path, "r") as f:
                    market_summary = json.load(f).get("summary", "-")
        except: pass

        # 3. Load brainw.md
        current_dir = os.path.dirname(os.path.abspath(__file__))
        brain_instruction = load_brain_file(os.path.join(current_dir, "brainw.md"))
        if not brain_instruction: 
            brain_instruction = "Role: Strategist. Task: Summarize these trades and market outlook professionally."

        # 4. Ask Gemini
        prompt = f"""
        {brain_instruction}
        
        [MARKET OUTLOOK (IHSG)]:
        {market_summary}
        
        [WEEKLY LEDGER ACTIVITY]:
        {json.dumps(weekly_data, indent=2)}
        """
        
        log_system("Generating Weekly Report via AI...", "AI")
        # [POLYGLOT FORCE INJECT]
        api_key_val = LLM_API_KEY
        res = completion(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], api_key=api_key_val)
        report_content = res.choices[0].message.content

        # [MEMORY RECORDING] Standardized
        try:
             brain = GaiaBrain()
             brain.record(text=report_content, user_name="Minerva", source="weekly_report", tags="minerva, weekly_strategy, report")
             log_system("💾 Weekly Report saved to Memory.", "SUCCESS")
        except Exception as mem_err:
             log_system(f"Memory Save Error: {mem_err}", "ERROR")

        return report_content

    except Exception as e:
        log_system(f"Weekly Gen Error: {e}", "ERROR")
        return f"❌ Gagal generate weekly report: {e}"

# --- Helper: Split & Send Long Message ---
async def send_long_message(event, text):
    """Memecah pesan panjang menjadi beberapa bagian agar muat di Telegram."""
    if len(text) <= 4000:
        await event.reply(text)
    else:
        # Jika lebih dari 4000 karakter, potong per 4000
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await event.reply(part)
            await asyncio.sleep(1) # Jeda dikit biar urutan ga berantakan

# --- Command: /weekly ---
# --- Command: /weekly ---
@bot_client.on(events.NewMessage(pattern=r'/weekly'))
async def manual_weekly(event):
    if str(event.sender_id) != str(ADMIN_ID): return
    log_system("Manual Weekly Report triggered", "WARN")
    await event.reply("⏳ **Weekly Ritual:** Sedang menganalisa Market & Ledger...")
    
    try:
        # Step A: Refresh Market Context (Heavy Task)
        # This ensures the report has the latest IHSG outlook
        await analyze_market("weekly")
        
        # Step B: Generate Text Report
        report_text = await generate_weekly_report()
        
        # GUNAKAN HELPER BARU
        header = "📢 **WEEKLY STRATEGY (Manual)**\n\n"
        await send_long_message(event, header + report_text)
        
        log_system("Weekly report sent.", "SUCCESS")
        
    except Exception as e:
        log_system(f"Weekly Error: {e}", "ERROR")
        await event.reply(f"❌ Gagal membuat report weekly: {e}")

# --- Command: /monthly ---
@bot_client.on(events.NewMessage(pattern=r'/monthly'))
async def manual_monthly(event):
    if str(event.sender_id) != str(ADMIN_ID): return
    log_system("Manual Monthly Report triggered", "WARN")
    await event.reply("⏳ **Monthly Audit:** Sedang menghitung statistik performa...")
    
    try:
        # Fetch monthly market context first
        await analyze_market("monthly")
        
        # Generate the stats from ledger.json
        report_text = await generate_monthly_report()
        
        # GUNAKAN HELPER BARU
        header = "📢 **LAPORAN BULANAN (Manual)**\n\n"
        await send_long_message(event, header + report_text)
        
        log_system("Monthly report sent.", "SUCCESS")
        
    except Exception as e:
        log_system(f"Monthly Error: {e}", "ERROR")
        await event.reply(f"❌ Gagal membuat report bulanan: {e}")

# --- Command: /night (Manual Force Trigger) ---
@bot_client.on(events.NewMessage(pattern=r'/night'))
async def manual_night(event):
    if str(event.sender_id) != str(ADMIN_ID): return
    
    log_system("Manual Night Analysis triggered by User", "WARN")
    msg = await event.reply("🌙 **Force Trigger:** Memulai Rangkaian Analisa Malam...")
    
    try:
        # LANGKAH 1: Cek "Kesegaran" Data IHSG
        # Path file context harian
        ctx_path = os.path.join(HARVEST_DIR, "market_context", "active", "context_daily.json")
        need_market_update = True

        if os.path.exists(ctx_path):
            # Cek tanggal modifikasi file
            file_mod_time = datetime.fromtimestamp(os.path.getmtime(ctx_path), tz=LOCAL_TZ)
            now = datetime.now(LOCAL_TZ)
            
            # Jika file tersebut dimodifikasi HARI INI, berarti datanya masih segar.
            if file_mod_time.date() == now.date():
                need_market_update = False
                log_system("Market Context is fresh. Skipping update.", "INFO")
                await msg.edit("✅ Data IHSG hari ini sudah tersedia (Cached). Lanjut...")

        # LANGKAH 2: Update Market (Hanya Jika Perlu)
        if need_market_update:
            await msg.edit("1️⃣ Data IHSG usang/hilang. Mengambil data baru...")
            await analyze_market("daily") # Fungsi ini mengambil dari dlquanbot
            await msg.edit("✅ Data IHSG berhasil di-update.")
        
        # C. DISPLAY RESULT (The User Request)
        # Always show the outlook, even if tickers are empty.
        ihsg_summary = "⚠️ Gagal mengambil data IHSG."
        if os.path.exists(ctx_path):
            with open(ctx_path, 'r') as f:
                d = json.load(f)
                ihsg_summary = d.get('summary', 'No Data')
        
        await event.reply(f"🌍 **IHSG MARKET OUTLOOK:**\n{ihsg_summary}")

        # --- PHASE 2: STOCK ANALYSIS DIAGNOSIS ---
        await msg.edit("2️⃣ Mengecek antrian saham...")
        
        # DEBUG: Read tickers directly to show user using the robust function
        loaded_tickers = manage_tickers(None, "load")
        
        if not loaded_tickers:
            await event.reply("⚠️ **DIAGNOSA:** File `daily_tickers.txt` terbaca KOSONG oleh sistem.\nAnalisa saham dilewatkan.")
            await msg.edit("✅ Rangkaian Selesai (Hanya Market).")
        else:
            ticker_list_str = ", ".join(loaded_tickers)
            await event.reply(f"📋 **Ditemukan {len(loaded_tickers)} Saham:**\n`{ticker_list_str}`\n\n_Memulai analisa..._")
            
            # Run the job
            await night_analysis_job()
            await msg.edit("✅ **Rangkaian Malam Selesai.**")
        
    except Exception as e:
        log_system(f"Night Trigger Error: {e}", "ERROR")
        await event.reply(f"❌ Error saat manual night: {e}")

# --- Helper: Morning Briefing ---
async def morning_briefing_job():
    log_system("Starting Morning Briefing Job logic...", "INFO")
    
    try:
        ledger = await load_ledger_safe()
        if not ledger:
            log_system("Ledger empty or not found. Morning Job skipping.", "WARN")
            return
        
        log_system(f"Ledger loaded. Entries: {len(ledger)}", "INFO")

        # 3. Filter Data
        now = datetime.now(LOCAL_TZ)
        yesterday = now - timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y-%m-%d')
        
        log_system(f"Looking for signals dated: {yesterday_str}", "INFO")
        
        buy_candidates = []
        for entry in ledger:
            # Ambil tanggal YYYY-MM-DD
            entry_date = entry.get('created_at', '').split(' ')[0]
            if entry_date == yesterday_str and entry.get('signal') == 'BUY':
                buy_candidates.append(entry)
        
        log_system(f"Found {len(buy_candidates)} BUY candidates.", "INFO")

        # 4. Susun Pesan
        msg = f"☀️ **MORNING CALL ({now.strftime('%d/%m')})**\n"
        
        if not buy_candidates:
            log_system("Mode: Zero Signal Notification", "INFO")
            msg += f"_(Data: {yesterday_str})_\n\n"
            msg += "📉 **Tidak ada Sinyal BUY** dari analisa semalam.\n"
            msg += "_Market mungkin sedang bearish/sideways. Wait & See._ ☕"
        else:
            log_system("Mode: Active Signals", "SUCCESS")
            msg += f"_(Data: {yesterday_str})_\n"
            msg += f"Plan Entry Area:\n\n"
            for item in buy_candidates:
                ticker = item.get('ticker', '???')
                area = item.get('entry_area', 'Market')
                msg += f"🟢 **{ticker}** | Area: {area}\n"
            msg += "\n_Good luck!_ 🚀"

        # 5. Kirim
        if ADMIN_ID:
            log_system(f"Sending message to Admin ({ADMIN_ID})...", "NETWORK")
            await push_telegram_notification(msg)
            log_system("Morning Call sent successfully.", "SUCCESS")
            
            # [MEMORY RECORDING] Standardized
            try:
                brain = GaiaBrain()
                brain.record(text=msg, user_name="Minerva", source="morning_briefing", tags="minerva, morning_call, daily_recap")
                log_system("💾 Morning Call saved to Memory.", "SUCCESS")
            except Exception as mem_err:
                 log_system(f"Memory Save Error: {mem_err}", "ERROR")
        else:
            log_system("Admin ID missing. Message skipped.", "WARN")

    except Exception as e:
        import traceback
        log_system(f"CRASH in Morning Job: {e}", "ERROR")
        print(traceback.format_exc()) # Print full trace for deep debug

# --- Command: /morning ---
@bot_client.on(events.NewMessage(pattern=r'/morning'))
async def manual_morning(event):
    if not check_auth(event): return
    log_system("Manual Morning Call triggered", "WARN")
    await event.reply("☀️ **Force Trigger:** Menjalankan Morning Call manual...")
    await morning_briefing_job()

async def scheduler():
    log_system("⏰ Scheduler Loop Started", "INFO")
    processed_morning = False
    processed_night = False
    processed_weekly = False
    processed_daily_market = False # Flag for Daily Composite Analysis
    processed_month_end = False
    
    print("⏰ Scheduler Started...")

    while True:
        now = datetime.now(LOCAL_TZ)
        
        # 1. MORNING CALL (08:30 Mon-Fri)
        if now.weekday() <= 4 and now.hour == 8 and now.minute == 30 and not processed_morning:
            log_system("Triggering Scheduled Job: Morning Call", "INFO")
            if ADMIN_ID: await morning_briefing_job()
            processed_morning = True

        # 2. THE SUNDAY RITUAL (Sunday 16:00) -> Weekly Analysis + Report
        if now.weekday() == 6 and now.hour == 16 and not processed_weekly:
            log_system("Triggering Scheduled Job: Weekly Ritual", "INFO")
            if ADMIN_ID:
                await push_telegram_notification("⏳ **Memulai Ritual Mingguan...**")
                await analyze_market("weekly") # Step 1: Macro
                report = await generate_weekly_report() # Step 2: Report
                await push_telegram_notification(f"📢 **WEEKLY STRATEGY**\n\n{report}")
            processed_weekly = True

        # 3. DAILY MARKET CONTEXT (Mon-Fri 18:50) -> Daily Analysis
        # EXPLICITLY ADDED: Runs 10 mins before the Stock Analysis.
        if now.weekday() <= 4 and now.hour == 18 and now.minute == 50 and not processed_daily_market:
            log_system("Triggering Scheduled Job: Daily Market Context", "INFO")
            await analyze_market("daily") 
            processed_daily_market = True

        # 4. NIGHT STOCK ANALYSIS (Mon-Fri 19:00) -> Stock Analysis
        if now.weekday() <= 4 and now.hour == 19 and not processed_night:
            log_system("Triggering Scheduled Job: Night Stock Analysis", "INFO")
            await night_analysis_job()
            processed_night = True
        
        # 5. MONTHLY REPORT (Last Day 20:00)
        tomorrow = now + timedelta(days=1)
        is_last_day = (tomorrow.day == 1)
        if is_last_day and now.hour == 20 and not processed_month_end:
            log_system("Triggering Scheduled Job: Monthly Report", "INFO")
            if ADMIN_ID:
                await push_telegram_notification("⏳ **Memulai Audit Bulanan...**")
                await analyze_market("monthly")
                report = await generate_monthly_report()
                await push_telegram_notification(f"📢 **LAPORAN BULANAN**\n\n{report}")
            processed_month_end = True
            
        # RESET FLAGS (Midnight)
        if now.hour == 0: 
            processed_morning = False
            processed_night = False
            processed_weekly = False
            processed_daily_market = False # Reset Daily Market Flag
            processed_month_end = False
            
        await asyncio.sleep(30)



# ================= UTILS & LISTENER =================

@bot_client.on(events.NewMessage(pattern=r'/help'))
async def help_command(event):
    # Security Check
    if str(event.sender_id) != str(ADMIN_ID): return

    try:
        if os.path.exists("help_interface.txt"):
            with open("help_interface.txt", 'r', encoding='utf-8') as f:
                help_text = f.read()
        else:
            help_text = "⚠️ Help file (`help_interface.txt`) not found."
    except Exception as e:
        help_text = f"❌ Error reading help file: {e}"
        
    await event.reply(help_text)

@bot_client.on(events.NewMessage(pattern=r'/viewbrain'))
async def view_brain(event):
    if not check_auth(event): return
    try:
        if os.path.exists(BRAIN_FILE):
            with open(BRAIN_FILE, 'r') as f: content = f.read()
            # Limit output length if too long for Telegram
            if len(content) > 3000:
                content = content[:3000] + "... (truncated)"
            await event.reply(f"🧠 **Current Brain Persona:**\n\n```\n{content}\n```")
        else:
            await event.reply(f"⚠️ Brain file (`{BRAIN_FILE}`) not found.")
    except Exception as e:
        await event.reply(f"❌ Error reading brain: {e}")

# ---------------------------------------------------------
# FITUR 1: UPDATE (Revisi Kecil)
# ---------------------------------------------------------
@bot_client.on(events.NewMessage(pattern=r'/brainupdate (.+)'))
async def brain_update_handler(event):
    if not check_auth(event): return
    
    instruction = event.pattern_match.group(1)
    await event.reply(f"🧠 **Memproses Revisi Otak...**\nInstruction: _{instruction}_")

    # 1. Read Current
    current_brain = ""
    if os.path.exists(BRAIN_FILE):
        with open(BRAIN_FILE, 'r') as f: current_brain = f.read()
    else:
        await event.reply("⚠️ Brain file kosong. Gunakan /brainreplace dulu.")
        return

    # 2. Backup
    shutil.copy(BRAIN_FILE, f"{BRAIN_FILE}.bak")

    # 3. Gemini Refinement Task
    meta_prompt = f"""
    [TASK]: You are a System Prompt Engineer.
    [CURRENT PROMPT]:
    {current_brain}
    [USER REVISION REQUEST]:
    {instruction}
    [ACTION]:
    Rewrite the CURRENT PROMPT to incorporate the REVISION REQUEST.
    - Preserve the strict output format rules.
    - Preserve the indicator definitions (VPA, VBP, Star, Speedo).
    - ONLY change the tone/strategy as requested.
    - Output raw text only (no markdown blocks).
    """

    try:
        # [POLYGLOT] Use completion instead of ai_client
        res = completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": meta_prompt}],
            api_key=LLM_API_KEY
        )
        new_content = res.choices[0].message.content.replace("```", "").strip()
        
        with open(BRAIN_FILE, 'w') as f: f.write(new_content)
        await event.reply(f"✅ **Brain Updated!**\n(Backup: `{BRAIN_FILE}.bak`)\nCek dengan `/viewbrain`.")
        
        # [MEMORY RECORDING]
        try:
                brain = GaiaBrain()
                brain.record(
                    text=f"System Prompt Updated via /brainupdate: {instruction}", 
                    user_name="Minerva", 
                    source="system_update", 
                    tags="minerva, system, prompt_config, brain_update"
                )
        except: pass
    except Exception as e:
        await event.reply(f"❌ Error: {e}")

# ---------------------------------------------------------
# FITUR 2: REPLACE (Ganti Total tapi Cerdas)
# ---------------------------------------------------------
@bot_client.on(events.NewMessage(pattern=r'/brainreplace (.+)'))
async def brain_replace_handler(event):
    if not check_auth(event): return
    
    core_idea = event.pattern_match.group(1)
    await event.reply(f"🧠 **Membuat Otak Baru...**\nCore Concept: _{core_idea}_")

    # 1. Backup (Just in case)
    if os.path.exists(BRAIN_FILE):
        shutil.copy(BRAIN_FILE, f"{BRAIN_FILE}.bak")

    # 2. Gemini Creation Task
    meta_prompt = f"""
    [TASK]: You are an Expert Algo-Trading Architect.
    [GOAL]: Create a highly detailed SYSTEM PROMPT for a stock analysis bot based on the user's Core Concept.
    [USER CORE CONCEPT]:
    "{core_idea}"
    
    [REQUIREMENTS FOR THE NEW SYSTEM PROMPT]:
    1. Define the Persona clearly based on the Core Concept.
    2. Define how to read these specific inputs:
       - VPA (Volume Price Analysis): Trend & Validation.
       - VBP (Volume By Price): Support/Resistance zones.
       - Star Rotation (RRG): Sector rotation & momentum.
       - Speedometer: Sentiment (Fear/Greed).
    3. Enforce a STRICT Output Format (No yapping, just data):
       - "📊 ANALISA [TICKER]"
       - Bullet points for indicators.
       - "🚀 TRADING PLAN" (Entry, TP, SL).
    4. Output raw text only (no markdown blocks).
    """

    try:
        # [POLYGLOT] Use completion instead of ai_client
        res = completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": meta_prompt}],
            api_key=LLM_API_KEY
        )
        new_content = res.choices[0].message.content.replace("```", "").strip()
        
        with open(BRAIN_FILE, 'w') as f: f.write(new_content)
        await event.reply(f"✅ **New Brain Installed!**\n(Backup: `{BRAIN_FILE}.bak`)\nCek dengan `/viewbrain`.")

        # [MEMORY RECORDING]
        try:
                brain = GaiaBrain()
                brain.record(
                    text=f"System Prompt REPLACED via /brainreplace: {core_idea}", 
                    user_name="Minerva", 
                    source="system_update", 
                    tags="minerva, system, prompt_config, brain_replace"
                )
        except: pass
    except Exception as e:
        await event.reply(f"❌ Error: {e}")



@user_client.on(events.NewMessage(from_users=SOURCE_BOT))
async def spy_listen(event):
    # --- FILTER: IGNORE MANUAL INTERACTIONS ---
    if event.is_reply:
        return 

    msg = event.raw_text.upper()
    
    # Check for signal keywords (Alert, Signal, etc.)
    if any(x in msg for x in ["ALERT", "BUY", "SIGNAL", "BREAKOUT", "STRONG"]):
        # Extract Ticker (4 Uppercase Letters)
        m = re.search(r'\b[A-Z]{4}\b', msg)
        if m:
            ticker = m.group(0)
            
            # Add to Daily Ticker List (Schedule)
            if manage_tickers(ticker, "save"): 
                print(f"📝 Spy Captured Signal: {ticker}")

# ================= START =================
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    print(f"🚀 Minerva Started with {LLM_MODEL}.")
    
    # [GENESIS] Initialize Memory Manager at startup
    try:
        global_brain = GaiaBrain()
        logger.info(f"🧠 Minerva Memory Core initialized (Mode: {getattr(global_brain, 'mode', 'N/A')})")
    except Exception as e:
        logger.error(f"⚠️ Failed to initialize Memory Core at startup: {e}")

    # Start Clients Sequentially
    print("... Starting User Spy ...")
    await user_client.start()
    
    print("... Starting Commander Bot ...")
    await bot_client.start(bot_token=BOT_TOKEN)
    
    # Start Scheduler
    asyncio.create_task(scheduler())

    # Start Internal Trigger Server (Threaded)
    print("... Starting Internal Trigger Server (Port 3015) ...")
    threading.Thread(target=run_trigger_server, daemon=True).start()

    # Run Forever
    print("✅ All Systems Operational. Press Ctrl+C to stop.")
    start_midnight_cleanup_scheduler()
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )

if __name__ == '__main__':
    # Fix for 'DeprecationWarning: There is no current event loop'
    # and properly run the main coroutine
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Shutdown.")
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
