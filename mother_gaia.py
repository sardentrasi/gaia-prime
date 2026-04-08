"""
╔══════════════════════════════════════════════════════════╗
║             GAIA PRIME — MOTHER CORTEX                   ║
║        Modular Architecture • Layered Design             ║
║                                                          ║
║   Chat Apps → Message → LLM ↔ Tools → Context            ║
║                                     → Response           ║
╚══════════════════════════════════════════════════════════╝

Thin orchestrator that wires together the modular layers:
  - core/llm_engine.py    → PolyglotEngine (LLM)
  - core/context.py       → ContextManager (Memory + Skills)
  - core/agent_loop.py    → AgentLoop (Message → LLM ↔ Tools → Response)
  - core/module_manager.py → ModuleManager (tmux, forge, upgrade)
  - connectors/telegram_bot.py → TelegramBot + build_telegram_app()
  - gaia_memory_manager.py → GaiaBrain (ChromaDB RAG)
"""

import os
import sys
import json
import asyncio
import logging
import signal

import pytz
from datetime import datetime, timezone
from dotenv import load_dotenv

# ─── ENVIRONMENT ───
load_dotenv()

# ─── TIMEZONE ───
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")

# ─── LOGGING ───
def custom_time(*args):
    utc_dt = datetime.now(timezone.utc)
    return utc_dt.astimezone(MY_TZ).timetuple()

logging.Formatter.converter = custom_time
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), "gaia_prime.log"), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("MotherGAIA")

# ─── CORE IMPORTS ───
from gaia_memory_manager import GaiaBrain
from tools.lazarus import LazarusGuardian
from tools.educate_gaia import CodeIngester

from core.llm_engine import PolyglotEngine
from core.context import ContextManager
from core.agent_loop import AgentLoop
from core.module_manager import ModuleManager
from core.tools import ToolRegistry
from core.cron import CronScheduler
from core.heartbeat import HeartbeatDaemon

from connectors.telegram_bot import build_telegram_app


def main():
    """
    Main entry point for Gaia Prime.
    Initializes all layers and starts the Telegram polling loop.
    """
    logger.info("=" * 60)
    logger.info("🌍 GAIA PRIME v4.0 — Modular Architecture Boot Sequence")
    logger.info("=" * 60)

    # ─── 1. MEMORY LAYER ───
    brain = GaiaBrain()
    logger.info("🧠 [CORTEX] Brain Implant Online")

    # ─── 2. LLM ENGINE ───
    llm_api_key = os.getenv("LLM_API_KEY", "")
    api_keys = [k.strip() for k in llm_api_key.split(',') if k.strip()]
    engine = PolyglotEngine(
        model=os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash"),
        api_keys=api_keys,
        ollama_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    logger.info("🧬 [POLYGLOT] Neural Engine Online")

    # ─── 3. CONTEXT LAYER ───
    intent_config = {}
    intent_config_path = os.path.join(os.getcwd(), "intent_config.json")
    if os.path.exists(intent_config_path):
        try:
            with open(intent_config_path, "r", encoding="utf-8") as f:
                intent_config = json.load(f)
            logger.info("🎯 [INTENT] Config loaded")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load intent_config.json: {e}")
    
    context = ContextManager(brain=brain, intent_config=intent_config, root_dir=os.getcwd())
    logger.info("📚 [CONTEXT] Memory Layer Online")

    # ─── 3b. CRON SCHEDULER ───
    cron = CronScheduler(root_dir=os.getcwd())
    logger.info(f"⏰ [CRON] Scheduler Online ({len(cron.jobs)} jobs loaded)")

    # ─── 3c. TOOL REGISTRY ───
    tool_registry = ToolRegistry(brain=brain, context=context, root_dir=os.getcwd(), cron=cron)
    logger.info("🔧 [TOOLS] Tool Registry Online (9 tools available)")

    # ─── 4. AGENT LOOP ───
    agent = AgentLoop(engine=engine, context=context, brain=brain, tool_registry=tool_registry)
    logger.info("🔄 [AGENT] Core Processing Loop Online (Iterative Tool Loop Enabled)")

    # ─── 4b. HEARTBEAT DAEMON ───
    heartbeat = HeartbeatDaemon(cron=cron, agent_loop=agent, tool_registry=tool_registry)
    logger.info("💓 [HEARTBEAT] Daemon initialized (waiting for event loop)")

    # ─── 5. MODULE MANAGER (Tools Layer) ───
    lazarus = LazarusGuardian(brain, engine.model, engine.primary_key)
    ingester = CodeIngester()
    modules = ModuleManager(
        llm_engine=engine,
        brain=brain,
        lazarus=lazarus,
        ingester=ingester
    )
    logger.info("🔧 [MODULES] Module Manager Online")

    # ─── 6. TELEGRAM APP ───
    app = build_telegram_app(
        agent_loop=agent,
        module_manager=modules
    )

    # ─── 7. SIGNAL HANDLING ───
    def signal_handler(sig, frame):
        logger.info("🛑 Shutting down Gaia Prime...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # ─── 8. LAUNCH ───
    logger.info("=" * 60)
    logger.info("🌍 GAIA PRIME v4.0 — ALL SYSTEMS ONLINE")
    logger.info("=" * 60)

    # Start Heartbeat with the event loop from polling
    heartbeat.set_event_loop(asyncio.get_event_loop())

    # Connect Telegram sender to Heartbeat
    async def telegram_sender(chat_id, text):
        try:
            await app.bot.send_message(chat_id=int(chat_id), text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ Heartbeat Telegram send failed: {e}")
    heartbeat.set_telegram_sender(telegram_sender)

    heartbeat.start()

    try:
        app.run_polling()
    finally:
        heartbeat.stop()


if __name__ == "__main__":
    main()
