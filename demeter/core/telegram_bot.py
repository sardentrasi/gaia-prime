import os
import time
import requests
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import NetworkError, TimedOut

import core.state
from core.state import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ALLOWED_USERS, logger, global_brain

def kirim_telegram_sync(pesan, file_gambar=None):
    logger.info(f"[TELEGRAM] Mengirim notifikasi...")
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
        logger.error(f"[ERROR] Telegram fail: {e}")

def _check_auth(update: Update) -> bool:
    if not update.effective_user: return False
    user_id = update.effective_user.id
    if user_id in ALLOWED_USERS:
        return True
    return False

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning(f"⚠️ [NETWORK] Gangguan koneksi ke Telegram: {context.error}. Retrying...")
    else:
        logger.error("Exception while handling an update:", exc_info=context.error)

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
        logger.error(f"[ERROR] Missing help_interface.txt: {e}")
        
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
    
    await update.message.reply_text("⏳ **Permintaan Diterima.**\nMenunggu laporan ESP32 & Analisa AI...", parse_mode='Markdown')
    
    core.state.COMMAND_QUEUE = {
        "action": "ANALYZE", 
        "duration": 0, 
        "chat_id": update.message.chat_id 
    }

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_auth(update): return

    if not context.args:
        await update.message.reply_text("ℹ️ **Penggunaan:** `/chat [pesan]`", parse_mode="Markdown")
        return
        
    user_name = update.effective_user.first_name if update.effective_user else "User"
    user_msg = " ".join(context.args)
    
    try:
        if len(user_msg) > 5:
            global_brain.record(text=user_msg, user_name=user_name, source="user_chat", tags=f"demeter, user_chat_{update.effective_user.id}")

        persona_path = "persona_demeter.md"
        system_persona = "You are Demeter, the Garden AI."
        
        if os.path.exists(persona_path):
            with open(persona_path, "r", encoding="utf-8") as f:
                system_persona = f.read()
        
        system_persona = system_persona.replace("{sender}", user_name)

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        reply = await global_brain.chat_with_langchain(
            query=user_msg,
            system_persona=system_persona,
            user_name=user_name,
            filter_type="demeter"
        )
        
        await update.message.reply_text(reply)

        if len(reply) > 20:
             global_brain.record(text=f"DEMETER to {user_name}: {reply}", user_name="Demeter", source="demeter_chat", tags=f"ai_response_{update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"Demeter Chat Error: {e}")
        await update.message.reply_text("⚠️ **Terjadi Kesalahan Komunikasi**")

def run_telegram_bot():
    logger.info("[SYSTEM] Starting Telegram Bot Listener...")

    request_config = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0
    )

    application = Application.builder().token(TELEGRAM_TOKEN).request(request_config).build()

    application.add_error_handler(error_handler)
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("chat", chat_command))
    
    application.run_polling()
