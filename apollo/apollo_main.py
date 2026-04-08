import logging
import sys
import signal
import time
import os
import re
import asyncio
import httpx
import datetime
import tempfile
import json
from telegram import Update
from dotenv import load_dotenv
import pytz

# Load .env before accessing os.getenv
load_dotenv()
# Fix Path for 'apollo' module import
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from tools.file_ops import append_to_file, read_file  # Import after path fix

from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from apollo.harvesters.news import NewsHarvester
from apollo.harvesters.sbfeed import StockbitHarvester
# Timezone Setup
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")

# Logging Setup (Gaia Standard)
def custom_time(*args):
    utc_dt = datetime.datetime.now(datetime.timezone.utc)
    converted = utc_dt.astimezone(MY_TZ)
    return converted.timetuple()

logging.Formatter.converter = custom_time
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), "apollo.log"), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("Apollo")

# [STANDALONE SURVIVAL] Short-Term Memory
import schedule
import threading

def update_short_memory(action: str, result: str) -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    module_name = os.path.basename(current_dir)
    state_file = os.path.join(current_dir, f"{module_name}_state.json")
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        
        if not isinstance(state_data, dict):
            state_data = {}
            
        if "short_term_memory" not in state_data:
            state_data["short_term_memory"] = []
            
        state_data["short_term_memory"].append(memory_entry)
        state_data["short_term_memory"] = state_data["short_term_memory"][-10:]
        
        # [REFINEMENT] Ensure only short_term_memory is preserved
        clean_state = {"short_term_memory": state_data["short_term_memory"]}
        
        # [ATOMIC WRITE] Prevent corruption on interrupt
        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(state_file), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(clean_state, f, indent=4)
            os.replace(tmp_path, state_file)
        except:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
            
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
                
            # [ATOMIC WRITE] Prevent corruption on interrupt
            tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(state_file), suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(state_data, f, indent=4)
                os.replace(tmp_path, state_file)
            except:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
                
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
    from apollo_memory_manager import GaiaBrain
    logger.info("🧠 Apollo Memory Manager (Local + Central Sync) connected.")
except ImportError as e:
    logger.error(f"⚠️ [SURVIVAL MODE] Local Memory Manager error: {e}")
    # Final Safety Net (Mock Class to prevent crash)
    class GaiaBrain:
        def __init__(self): pass
        def record(self, *args, **kwargs): return False
        def remember(self, *args, **kwargs): return ""


# Security Configuration
def get_allowed_users():
    """
    Retrieves and validates allowed user IDs from environment variables.
    Returns:
        List[int]: A list of valid user IDs.
    """
    users = os.getenv("USERS_ALLOWED", "")
    valid_users = []
    for u in users.split(","):
        u = u.strip()
        if u.isdigit():
            valid_users.append(int(u))
        elif u:
            logger.warning(f"⚠️ Invalid User ID in .env: '{u}' (Must be integer)")
    return valid_users

ALLOWED_USERS = get_allowed_users()

async def restricted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Middleware to check if the user is authorized.
    """
    user = update.effective_user
    if not user or user.id not in ALLOWED_USERS:
        logger.warning(f"⛔ Unauthorized access attempt from {user.first_name} ({user.id})")
        return False
    return True

running = True
def signal_handler(sig, frame):
    global running
    logger.info("Shutdown signal received (Signal ID: %s)..." % sig)
    running = False
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /start command.
    Greets the user and explains the bot's purpose.
    """
    user_name = update.effective_user.first_name if update.effective_user else "Pengguna"
    
    if not await restricted(update, context):
        return

    logger.info(f"Received /start command from user: {user_name} ({update.effective_user.id})")
    await update.message.reply_text(
        f"Halo, {user_name}! Saya adalah Apollo, subsistem pengumpul data Gaia Prime.\n"
        "Saya bertugas mengumpulkan berita dan data intelijen."
    )

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles unknown commands.
    Informs the user that the command is not recognized.
    """
    user_name = update.effective_user.first_name if update.effective_user else "Pengguna"
    logger.warning(f"Received unknown command: {update.message.text} from user: {user_name} ({update.effective_user.id})")
    await update.message.reply_text(
        "❓ Perintah tidak dikenali. Gunakan /start untuk bantuan."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help menu."""
    if not await restricted(update, context):
        return

    help_text = read_file("help_interface.txt")
    if not help_text:
        help_text = "⚠️ Help file not found."
        
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def force_harvest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Manually triggers the news harvest asynchronously.
    """
    if not await restricted(update, context):
        return

    msg = await update.message.reply_text("📡 **Starting Manual Harvest...**\n- News RSS\n- Stockbit Feed", parse_mode="Markdown")
    try:
        loop = asyncio.get_running_loop()
        
        # 1. News Harvest
        news_harvester = NewsHarvester()
        news_count, news_headlines = await loop.run_in_executor(None, news_harvester.harvest)
        
        # 2. Stockbit Harvest
        sb_harvester = StockbitHarvester()
        sb_count, sb_headlines = await loop.run_in_executor(None, sb_harvester.harvest)
        
        total_saved = news_count + sb_count
        
        # Create Unified Rich Report
        report_parts = [f"Ingested {total_saved} items (News: {news_count}, SB: {sb_count})"]
        
        # Put Stockbit first (usually more high-density contexts)
        if sb_headlines:
            report_parts.append("\n--- STOCKBIT FEED ---")
            report_parts.extend(sb_headlines)
            
        if news_headlines:
            report_parts.append("\n--- BERITA UTAMA (NEWS) ---")
            report_parts.extend(news_headlines)

        full_report = "\n".join(report_parts)
        # Removed truncation to satisfy user request for 'seluruh' data
        update_short_memory("Unified Harvest Report", full_report)
        
        await context.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text=f"✅ **Harvest Complete.**\n- News: {news_count} articles\n- Stockbit: {sb_count} posts",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Manual Harvest Failed: {e}")
        await context.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text=f"❌ **Harvest Error:** {e}",
            parse_mode="Markdown"
        )

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Discuss with Apollo (RAG Enabled via Central Brain)."""
    if not await restricted(update, context):
        return

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
            # [TAG FIX] Add 'apollo' for entity filtering
            user_id = update.effective_user.id
            brain.record(text=user_msg, user_name=user_name, source="user_chat", tags=f"apollo, user_chat_{user_id}", user_id=user_id)

        # [INTENT ROUTING] Use config from brain (which now handles local fallbacks)
        config = getattr(brain, 'config', {})
        
        tech_k = config.get("technical_keywords", ["code", "script"])
        news_k = config.get("news_keywords", ["news", "berita"])
        entity_filters = config.get("entity_filters", {
            "demeter": ["demeter", "kebun", "tanaman", "siram", "air"],
            "minerva": ["minerva", "saham", "market", "trading", "investasi"],
            "apollo": ["apollo", "berita", "news", "artikel", "harvest"]
        })

        # 1. Entity Filter (Demeter/Minerva/Apollo check)
        filter_type = None
        q_lower = user_msg.lower()
        
        detected_categories = []
        for entity, keywords in entity_filters.items():
            if any(k in q_lower for k in keywords):
                if entity == "apollo":
                    # For Apollo, try to be more specific with categories from config
                    categories = config.get("news_subcategories", ["politik", "ekonomi", "market", "bisnis", "sosial", "kriminal", "olahraga", "teknologi", "cuaca"])
                    for cat in categories:
                        if cat in q_lower:
                            detected_categories.append(cat)
                
                filter_type = entity
                break

        if filter_type == "apollo" and detected_categories:
            # Append specific categories to boost similarity
            filter_type = f"apollo, {', '.join(detected_categories)}"
            
        # 2. Technical Code Filter
        is_technical = any(k in q_lower for k in tech_k)
        if is_technical: filter_type = "source_code"
            
        # 3. News Context
        is_news = any(k in q_lower for k in news_k)
        if is_news and not filter_type: filter_type = "apollo"
            
        logger.info(f"🔍 [INTENT] Filter Decision: {filter_type} (Msg: '{user_msg}')")

        # 2. Prepare System Persona
        # [PERSONA] Modern Persona (Markdown)
        current_dir = os.path.dirname(__file__)
        persona_path = os.path.join(current_dir, "persona_apollo.md")
        system_persona = "You are Apollo, the intelligence subsystem of Gaia Prime."
        if os.path.exists(persona_path):
            with open(persona_path, "r", encoding="utf-8") as f:
                system_persona = f.read()
        
        # Inject standard placeholders
        system_persona = system_persona.replace("{time_now}", datetime.datetime.now(MY_TZ).strftime("%Y-%m-%d %H:%M:%S"))

        # Notify user
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # 3. Generate Response (LangChain)
        reply = await brain.chat_with_langchain(
            query=user_msg,
            system_persona=system_persona,
            user_name=user_name,
            filter_type=filter_type,
            user_id=update.effective_user.id
        )
        
        await update.message.reply_text(reply)

        # [ACTIVE MEMORY] 📝 Record Apollo's Reply
        if len(reply) > 20:
             logger.info("💾 [MEMORY] Recording Apollo Response...")
             user_id = update.effective_user.id
             brain.record(text=f"APOLLO to {user_name}: {reply}", user_name="Apollo", source="apollo_chat", tags=f"ai_response_{user_id}", user_id=user_id)
        
        # [NEW] Extract concise reply for situational awareness
        clean_reply = re.sub(r'[*_#`\n]', ' ', reply)
        clean_reply = re.sub(r'\s+', ' ', clean_reply).strip()
        reply_snippet = clean_reply[:100] + "..." if len(clean_reply) > 100 else clean_reply
        update_short_memory(f"Chat with {user_name}", f"Q: '{user_msg[:30]}...' -> A: {reply_snippet}")

        
    except Exception as e:
        logger.error(f"Apollo Chat Error: {e}")
        await update.message.reply_text("⚠️ **Terjadi Kesalahan Komunikasi**")

async def auto_harvest_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Background Job for Harvesting.
    Runs every 6 hours.
    """
    logger.info("🤖 Auto-Harvest Triggered...")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    try:
        msg = None
        if chat_id:
            msg = await context.bot.send_message(chat_id=chat_id, text="🤖 *Apollo Auto-Harvest Started...*", parse_mode="Markdown")
            
        loop = asyncio.get_running_loop()
        
        # 1. News
        news_harvester = NewsHarvester()
        news_count, news_headlines = await loop.run_in_executor(None, news_harvester.harvest)
        
        # 2. Stockbit
        sb_harvester = StockbitHarvester()
        sb_count, sb_headlines = await loop.run_in_executor(None, sb_harvester.harvest)
        
        total_saved = news_count + sb_count
        
        # Create Unified Rich Report
        report_parts = [f"Ingested {total_saved} items (News: {news_count}, SB: {sb_count})"]
        
        if sb_headlines:
            report_parts.append("\n--- STOCKBIT FEED ---")
            report_parts.extend(sb_headlines)
            
        if news_headlines:
            report_parts.append("\n--- BERITA UTAMA (NEWS) ---")
            report_parts.extend(news_headlines)

        full_report = "\n".join(report_parts)
        update_short_memory("Unified Auto-Harvest Report", full_report)
        
        if msg:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg.message_id,
                text=f"✅ *Apollo Auto-Harvest Complete.*\n- News: {news_count} News\n- Stockbit: {sb_count} Feeds",
                parse_mode="Markdown"
            )
            
    except httpx.NetworkError as ne:
        logger.error(f"Auto-Harvest Network Error: {ne}")
        if chat_id: await context.bot.send_message(chat_id=chat_id, text=f"⚠️ *Harvest Network Error:* {ne}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Auto-Harvest Critical Fail: {e}")
        if chat_id:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ *Harvest Critical Fail:* {e}", parse_mode="Markdown")

async def add_source_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Adds a new RSS source to sources.txt.
    Usage: /add_source [url]
    """
    if not await restricted(update, context):
        return

    if not context.args:
        await update.message.reply_text("ℹ️ **Penggunaan:** `/add_source [url]`", parse_mode="Markdown")
        return

    url = context.args[0]
    target_file = "sources.txt" 

    try:
        append_to_file(target_file, url)
        await update.message.reply_text(f"✅ Sumber baru ditambahkan ke Apollo: `{url}`", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to add source: {e}")
        await update.message.reply_text(f"❌ Gagal menambahkan sumber: {e}")

def main() -> None:
    """
    Main function to run the Apollo Telegram Bot.
    Initializes the bot, sets up handlers, and starts polling.
    """
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        sys.exit(1)

    logger.info("Initializing Apollo bot...")
    
    # Reload Allowed Users logic here just in case, or rely on global
    logger.info(f"🔒 Security Active. Allowed User IDs: {ALLOWED_USERS}")

    application = ApplicationBuilder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # [GENESIS] Initialize Memory Manager at startup to ensure local folder creation
    try:
        global_brain = GaiaBrain()
        logger.info(f"🧠 Apollo Memory Core initialized (Mode: {getattr(global_brain, 'mode', 'N/A')})")
    except Exception as e:
        logger.error(f"⚠️ Failed to initialize Memory Core at startup: {e}")

    application.add_handler(CommandHandler("chat", chat_command))
    application.add_handler(CommandHandler("force_harvest", force_harvest_command))
    application.add_handler(CommandHandler("add_source", add_source_command))

    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    import pytz
    tz_name = os.getenv("TIMEZONE", "Asia/Jakarta")
    local_tz = pytz.timezone(tz_name)

    # Schedule Auto-Harvest (Daily at 05:00 and 17:00)
    if application.job_queue:
        application.job_queue.run_daily(auto_harvest_job, time=datetime.time(hour=5, minute=0, tzinfo=local_tz))
        application.job_queue.run_daily(auto_harvest_job, time=datetime.time(hour=17, minute=0, tzinfo=local_tz))
        logger.info(f"🕒 Auto-Harvest scheduled (Daily @ 05:00 & 17:00 {tz_name}). No immediate run.")

    try:
        start_midnight_cleanup_scheduler()
        logger.info("Apollo bot started polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"An unhandled error occurred during polling: {e}", exc_info=True)
    finally:
        logger.info("Apollo bot application stopped.")

if __name__ == "__main__":
    main()
