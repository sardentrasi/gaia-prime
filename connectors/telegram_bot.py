import os
import sys
import io
import json
import asyncio
import logging
import signal

import pytz
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Defaults
from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest

from core.message import GaiaMessage
from tools.file_ops import append_to_file

logger = logging.getLogger("GaiaTelegram")

# Timezone
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")

_raw_chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("MY_USER_ID", "0")
try:
    TELEGRAM_CHAT_ID = int(_raw_chat_id)
except (ValueError, TypeError):
    TELEGRAM_CHAT_ID = 0


class TelegramBot:
    """
    Telegram connector for Gaia Prime.
    Converts Telegram Updates into GaiaMessages and routes to AgentLoop.
    """

    def __init__(self, agent_loop, module_manager):
        """
        Args:
            agent_loop: AgentLoop instance for chat processing
            module_manager: ModuleManager instance for system commands
        """
        self.agent = agent_loop
        self.modules = module_manager
        self.brain = agent_loop.brain

    # ─── AUTH ───

    async def _restricted(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return False
        return self.modules.check_auth(update.effective_user.id)

    # ─── UTILITY ───

    async def _send_safe_message(self, context, chat_id, text, parse_mode="Markdown"):
        """Anti-Flood: Safely splits and sends long messages."""
        MAX_LENGTH = 4000
        if len(text) <= MAX_LENGTH:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=text)
            return
        parts = []
        while text:
            if len(text) <= MAX_LENGTH:
                parts.append(text)
                break
            split_at = text.rfind('\n', 0, MAX_LENGTH)
            if split_at == -1:
                split_at = MAX_LENGTH
            parts.append(text[:split_at])
            text = text[split_at:]
        for i, part in enumerate(parts):
            msg = f"[{i+1}/{len(parts)}]\n{part}"
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=parse_mode)
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            await asyncio.sleep(0.5)

    # ─── CORE HANDLERS ───

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        if isinstance(context.error, (NetworkError, TimedOut)):
            logger.warning(f"📡 Network/Timeout issue: {context.error}. Continuing...")
        else:
            logger.error(f"❌ Application Error: {context.error}", exc_info=context.error)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if context.args:
            await self.turn_on(update, context)
            return
        await update.message.reply_text("👁️ Mother GAIA Sentinel Online. Monitoring logs & status.")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        self.modules.sync_panes()
        report = "📊 **System Status**\n\n"
        for module in self.modules.modules:
            is_active = self.modules.is_running(module)
            status_icon = "🟢 Online" if is_active else "🔴 Offline"
            report += f"• **{module.capitalize()}**: {status_icon}\n"
        await update.message.reply_text(report, parse_mode="Markdown")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        ui_text = self.modules.get_help_text()
        await update.message.reply_text(ui_text)

    async def turn_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if not context.args:
            await update.message.reply_text("Usage: /start [module_name]")
            return
        module_name = context.args[0].lower()
        status_msg = await update.message.reply_text(
            f"🔄 **IGNITION:** Starting sequence for `{module_name}`...", parse_mode='Markdown'
        )
        try:
            success, msg = self.modules.start_module(module_name)
            await asyncio.sleep(1.5)
            if success:
                await status_msg.edit_text(f"🟢 **{module_name.upper()} IS ONLINE**\n{msg}", parse_mode='Markdown')
            else:
                await status_msg.edit_text(f"❌ **IGNITION FAILED:** {msg}", parse_mode='Markdown')
        except Exception as e:
            await status_msg.edit_text(f"❌ **SYSTEM ERROR:** {e}", parse_mode='Markdown')

    async def turn_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if not context.args:
            await update.message.reply_text("Usage: /stop [module_name]")
            return
        module_name = context.args[0].lower()
        status_msg = await update.message.reply_text(
            f"🔻 **TERMINATING:** Sending kill signal to `{module_name}`...", parse_mode='Markdown'
        )
        try:
            success, msg = self.modules.stop_module(module_name)
            await asyncio.sleep(1)
            if success:
                await status_msg.edit_text(f"🛑 **{module_name.upper()} IS OFFLINE**\n{msg}", parse_mode='Markdown')
            else:
                await status_msg.edit_text(f"⚠️ **TERMINATION FAILED:** {msg}", parse_mode='Markdown')
        except Exception as e:
            await status_msg.edit_text(f"⚠️ **TERMINATION ERROR:** {e}", parse_mode='Markdown')

    # ─── FORGE / INITIALIZE / UPGRADE / ROLLBACK / PURGE ───

    async def forge(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if len(context.args) < 4:
            await update.message.reply_text("Usage: `/forge [name] [alpha/omega] [otp] [description...]`", parse_mode='Markdown')
            return
        name = context.args[0].lower()
        security_level = context.args[1].lower()
        input_otp = context.args[2]
        desc = " ".join(context.args[3:])
        if not self.modules.verify_security(security_level, input_otp):
            await update.message.reply_text(f"⛔ **ACCESS DENIED:** Invalid {security_level.upper()} OTP.")
            return
        await update.message.reply_text(
            f"🔨 Forging **{name}** ({security_level.upper()}AUTH)...\nDesc: {desc}\n_Please wait, parsing ether..._",
            parse_mode='Markdown'
        )
        success, msg = await self.modules.forge_bot(name, desc)
        if success:
            await update.message.reply_text(f"✅ {msg}\nRun `/initialize {name} {security_level} {input_otp}` to deploy.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ {msg}")

    async def initialize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if len(context.args) < 3:
            await update.message.reply_text("Usage: `/initialize [name] [alpha/omega] [otp]`", parse_mode='Markdown')
            return
        name = context.args[0].lower()
        security_level = context.args[1].lower()
        input_otp = context.args[2]
        if not self.modules.verify_security(security_level, input_otp):
            await update.message.reply_text(f"⛔ **ACCESS DENIED:** Invalid {security_level.upper()} OTP.")
            return
        await update.message.reply_text(f"⚙️ Initializing **{name}** ({security_level.upper()}AUTH)...", parse_mode='Markdown')
        success, msg = self.modules.initialize_bot(name)
        await update.message.reply_text(f"Result: {msg}")

    async def learn_codebase(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        await update.message.reply_text("⏳ **MEMINDAI KODE:** Gaia sedang mempelajari struktur dirinya sendiri...")
        count = self.modules.ingester.ingest_all() if self.modules.ingester else 0
        await update.message.reply_text(f"✅ **PROSES BELAJAR SELESAI.**\nSaya telah memperbarui ingatan saya tentang {count} file kode sumber.")

    async def add_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if not context.args:
            await update.message.reply_text("Usage: `/add_source [url]`", parse_mode='Markdown')
            return
        url = context.args[0]
        try:
            append_to_file("apollo/sources.txt", url)
            await update.message.reply_text(f"✅ Sumber intelijen baru ditambahkan ke Apollo:\n`{url}`\nAkan dipanen pada siklus berikutnya.", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal menulis ke konfigurasi: {e}")

    async def setup_security_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        success, alpha, omega = self.modules.generate_keys()
        if not success:
            await update.message.reply_text("⚠️ Security keys already exist in .env")
            return
        msg = (
            "🔐 **Gaia Security Matrix Generated**\n\n"
            f"🛡️ **Level 1: Alpha Authorize (Alpha)**\n`{alpha}`\n_(Hanya untuk Stop/Start/Soft Delete)_\n\n"
            f"☢️ **Level 2: Omega Authorize (Omega)**\n`{omega}`\n_(MASTER KEY: Izin pemusnahan data & akses penuh)_"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def purge_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if len(context.args) < 3:
            await update.message.reply_text("Usage needed:\n`/purge [name] alpha [OTP]`\n`/purge [name] omega [OTP]`", parse_mode="Markdown")
            return
        name = context.args[0].lower()
        level = context.args[1].lower()
        otp = context.args[2]
        if level not in ['alpha', 'omega']:
            await update.message.reply_text("Invalid Level. Use 'alpha' or 'omega'.")
            return
        await update.message.reply_text(f"⚠️ PROCESSING {level.upper()} PURGE FOR **{name}**...")
        success, msg = self.modules.purge_module(name, level, otp)
        await update.message.reply_text(f"{'✅' if success else '❌'} {msg}")

    async def audit_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if not context.args:
            await update.message.reply_text("Usage: /audit [name]")
            return
        name = context.args[0].lower()
        await update.message.reply_text(f"🕵️ **Auditing {name}**... Please wait.")
        success, report = await self.modules.audit_module(name)
        await self._send_safe_message(context, update.effective_chat.id, report)

    async def upgrade_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if len(context.args) < 4:
            await update.message.reply_text("⚠️ **SYNTAX ERROR:**\nUsage: `/upgrade [module] [alpha/omega] [otp] [instruction]`", parse_mode='Markdown')
            return
        name = context.args[0].lower()
        security_level = context.args[1].lower()
        input_otp = context.args[2]
        instr = " ".join(context.args[3:])
        if name not in self.modules.modules:
            await update.message.reply_text(f"❌ Module `{name}` not found.")
            return
        if not self.modules.verify_security(security_level, input_otp):
            await update.message.reply_text(f"⛔ **ACCESS DENIED:** Invalid {security_level.upper()} OTP.")
            return
        await self._send_safe_message(context, update.effective_chat.id,
            f"🧬 **EVOLUTION INITIATED ({security_level.upper()}AUTH):**\nTarget: `{name}`\nInstruction: _{instr}_",
            parse_mode='Markdown'
        )
        success, report = await self.modules.upgrade_module(name, instr)
        final_msg = f"{'✅ UPGRADE SUCCESS' if success else '❌ UPGRADE FAILED'}\n{report}"
        await self._send_safe_message(context, update.effective_chat.id, final_msg)

    async def rollback_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if len(context.args) < 3:
            await update.message.reply_text("Usage needed:\n`/rollback [module] [alpha/omega] [otp]`", parse_mode="Markdown")
            return
        name = context.args[0].lower().strip()
        security_level = context.args[1].lower().strip()
        input_otp = context.args[2].strip()
        if name not in self.modules.modules:
            await update.message.reply_text(f"❌ Module `{name}` not found.")
            return
        if not self.modules.verify_security(security_level, input_otp):
            await update.message.reply_text(f"⛔ **ACCESS DENIED:** Invalid {security_level.upper()} OTP.")
            return
        await update.message.reply_text(f"⏪ **ROLLBACK INITIATED ({security_level.upper()}AUTH):**\nTarget: `{name}`", parse_mode='Markdown')
        success, msg = self.modules.rollback_module(name)
        await update.message.reply_text(f"⏪ **ROLLBACK {name}**: {msg}")

    # ─── MEMORY MANAGEMENT ───

    async def memory_stats_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        loading_msg = await update.message.reply_text("📊 <b>RETRIEVING MEMORY ANALYTICS</b>...", parse_mode='HTML')
        try:
            stats = self.brain.get_analytics(save_to_file=True)
            msg = (
                "📊 <b>GAIA MEMORY ANALYTICS</b>\n\n"
                f"<b>Total Memories</b>: {stats['total_memories']}\n"
                f"<b>Queries Processed</b>: {stats['queries_processed']}\n"
                f"<b>Avg Retrieval Time</b>: {stats['average_retrieval_time_ms']}ms\n"
                f"<b>Cache Hit Ratio</b>: {stats['cache_hit_ratio_percent']}%\n"
                f"<b>Cache Hits</b>: {stats['cache_hits']} | Misses: {stats['cache_misses']}\n"
                f"<b>Uptime</b>: {stats['uptime_hours']}h\n\n"
                "<b>Memories by Source</b>:\n"
            )
            for source, count in sorted(stats['memories_by_source'].items(), key=lambda x: x[1], reverse=True)[:5]:
                msg += f"  • {source}: {count}\n"
            if stats['memories_by_tag']:
                msg += "\n<b>Top Tags</b>:\n"
                for tag, count in sorted(stats['memories_by_tag'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    msg += f"  • {tag}: {count}\n"
            msg += "\n<i>Analytics saved to memory_analytics.json</i>"
            await loading_msg.edit_text(msg, parse_mode='HTML')
        except Exception as e:
            await loading_msg.edit_text(f"❌ Failed to retrieve analytics: {e}")

    async def cleanup_memory_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if not context.args:
            await update.message.reply_text(
                "Usage:\n`/cleanup_memory [days]` - Remove memories older than N days\n"
                "`/cleanup_memory priority [threshold]` - Remove memories with priority < N",
                parse_mode='Markdown'
            )
            return
        try:
            if context.args[0].lower() == 'priority':
                threshold = int(context.args[1]) if len(context.args) > 1 else 3
                await update.message.reply_text(f"🗑️ **CLEANING UP LOW-PRIORITY MEMORIES** (P<{threshold})...", parse_mode='Markdown')
                count = self.brain.cleanup_low_priority(threshold=threshold)
                await update.message.reply_text(f"✅ Cleaned up **{count}** low-priority memories", parse_mode='Markdown')
            else:
                max_age_days = int(context.args[0])
                await update.message.reply_text(f"🗑️ **CLEANING UP OLD MEMORIES** (>{max_age_days} days)...", parse_mode='Markdown')
                count = self.brain.cleanup_old_memories(max_age_days=max_age_days)
                await update.message.reply_text(f"✅ Cleaned up **{count}** old memories", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Cleanup failed: {e}")

    async def session_info_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        try:
            sessions = self.brain.active_sessions
            user_id = update.effective_user.id
            active_session_id = self.brain.get_active_session(user_id)
            if not sessions:
                await update.message.reply_text("📝 <b>NO ACTIVE SESSIONS</b>\n\nNo memory sessions are currently active.", parse_mode='HTML')
                return
            msg = f"📝 <b>ACTIVE MEMORY SESSIONS</b> ({len(sessions)})\n\n"
            for session_id, session_data in sessions.items():
                created = session_data.get('created_at', 'Unknown')
                user_name = session_data.get('user_name', session_data.get('user_id', 'N/A'))
                active_marker = " ✅" if session_id == active_session_id else ""
                msg += f"<b>{session_id}</b>{active_marker}\n  User: {user_name}\n  Created: {created}\n\n"
            await update.message.reply_text(msg, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to retrieve session info: {e}")

    async def new_session_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        try:
            session_id = self.brain.create_session(user_id=user_id, user_name=user_name)
            self.brain.set_active_session(user_id, session_id)
            msg = (
                f"✅ <b>NEW SESSION CREATED</b>\n\n"
                f"<b>Session ID</b>: <code>{session_id}</code>\n"
                f"<b>User</b>: {user_name}\n\n"
                "<i>This session is now active. All /chat messages will be isolated to this session.</i>"
            )
            await update.message.reply_text(msg, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to create session: {e}")

    async def end_session_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        user_id = update.effective_user.id
        try:
            active_session = self.brain.get_active_session(user_id)
            if not active_session:
                await update.message.reply_text("ℹ️ <b>NO ACTIVE SESSION</b>\n\nYou don't have an active session.", parse_mode='HTML')
                return
            self.brain.set_active_session(user_id, None)
            self.brain.cleanup_session(active_session)
            msg = (
                f"✅ <b>SESSION ENDED</b>\n\n"
                f"<b>Session ID</b>: <code>{active_session}</code>\n\n"
                "<i>Session memories are preserved but no longer active.\nUse /new_session to start a new isolated context.</i>"
            )
            await update.message.reply_text(msg, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to end session: {e}")

    async def switch_session_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        user_id = update.effective_user.id
        try:
            if not context.args:
                sessions = self.brain.active_sessions
                if not sessions:
                    await update.message.reply_text("📝 <b>NO SESSIONS AVAILABLE</b>\n\nCreate a session first with /new_session", parse_mode='HTML')
                    return
                msg = "📝 <b>AVAILABLE SESSIONS</b>\n\nUse: <code>/switch_session [session_id]</code>\n\n"
                for sid in sessions.keys():
                    msg += f"• <code>{sid}</code>\n"
                await update.message.reply_text(msg, parse_mode='HTML')
                return
            target_session = context.args[0]
            if target_session not in self.brain.active_sessions:
                await update.message.reply_text(f"❌ <b>SESSION NOT FOUND</b>\n\nSession <code>{target_session}</code> does not exist.", parse_mode='HTML')
                return
            self.brain.set_active_session(user_id, target_session)
            session_data = self.brain.active_sessions[target_session]
            created = session_data.get('created_at', 'Unknown')
            msg = (
                f"✅ <b>SWITCHED TO SESSION</b>\n\n"
                f"<b>Session ID</b>: <code>{target_session}</code>\n"
                f"<b>Created</b>: {created}\n\n"
                "<i>All /chat messages will now use this session's context.</i>"
            )
            await update.message.reply_text(msg, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to switch session: {e}")

    # ─── CHAT (RAG) ───

    async def chat_rag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        if not context.args:
            await update.message.reply_text("Usage: `/chat [question]`", parse_mode="Markdown")
            return
        user_query = " ".join(context.args)
        user_name = update.effective_user.first_name if update.effective_user else "User"
        user_id = update.effective_user.id
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Create GaiaMessage and process via Agent Loop
        message = GaiaMessage(
            user_id=str(user_id),
            user_name=user_name,
            text=user_query,
            platform="telegram",
            target_id=str(update.effective_chat.id)
        )
        response_text = await self.agent.process(message)
        await self._send_safe_message(context, update.effective_chat.id, response_text)

    # ─── REMINDERS ───

    async def remind_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._restricted(update, context):
            return
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Usage: `/remind [pesan dan waktu]`", parse_mode="Markdown")
            return
        msg = await update.message.reply_text("⏳ Memproses pengingat...")
        meta = self.agent._extract_reminder_metadata(query)
        if meta:
            delivery_id = str(update.effective_chat.id)
            time_str = self.agent._format_reminder_time(meta["time"])
            if meta.get("is_question"):
                message = GaiaMessage(
                    user_id=str(update.effective_user.id),
                    user_name=update.effective_user.first_name,
                    text=meta["task"],
                    platform="telegram",
                    target_id=delivery_id
                )
                response_text = await self.agent.process(message)
                self.agent.tools.cron.create_job(
                    name=f"Reminder: {meta['task'][:40]}",
                    schedule=f"once {meta['time']}",
                    action=response_text,
                    platform="telegram",
                    target_id=delivery_id,
                    job_type="reminder"
                )
                response = f"✅ Jawaban komprehensif mengenai *'{meta['task']}'* telah disusun oleh memori Gaia dan akan dikirimkan pada {time_str}."
            else:
                user_name = update.effective_user.first_name if update.effective_user else "User"
                refined_action = self.agent._refine_reminder_text(meta["task"], user_name)
                self.agent.tools.cron.create_job(
                    name=f"Reminder: {meta['task'][:40]}",
                    schedule=f"once {meta['time']}",
                    action=refined_action,
                    platform="telegram",
                    target_id=delivery_id,
                    job_type="reminder"
                )
                response = f"✅ Pengingat aktif. Saya akan mengingatkan: '{meta['task']}' pada {time_str}."
        else:
            response = "Maaf, instruksi waktu/pengingat tidak dapat dipahami."
        await msg.edit_text(response)



    # ─── SENTINEL (Background) ───

    async def sentinel_monitoring(self, context: ContextTypes.DEFAULT_TYPE):
        for module in self.modules.modules:
            if self.modules.modules[module].get("active") and self.modules.is_running(module):
                error_snippet = self.modules.check_logs(module)
                if error_snippet:
                    trigger_line = error_snippet.split('\n')[0] if error_snippet else "Unknown"
                    logger.error(f"SENTINEL TRIGGERED BY: {trigger_line}")
                    logger.error(f"CRITICAL ERROR IN {module}!")
                    self.modules.stop_module(module)
                    try:
                        alert = f"⚠️ **CRASH DETECTED**: `{module}`\n🛑 Module STOPPED. Initiating Lazarus Protocol..."
                        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=alert, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Failed to send Lazarus Alert: {e}")
                    
                    fixed, report_msg = self.modules.heal_module(module, error_snippet)
                    if fixed:
                        msg = f"✅ LAZARUS SUCCESS:\nModul {module} berhasil diperbaiki.\nInfo: {report_msg}\n♻️ Restarting..."
                    else:
                        msg = f"⚠️ LAZARUS FAILED:\nModul {module} gagal diperbaiki.\n{report_msg}\n♻️ Restarting anyway..."
                    try:
                        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Failed to send Lazarus msg: {e}")
                    self.modules.start_module(module)


def build_telegram_app(agent_loop, module_manager):
    """
    Build and return the configured Telegram Application.
    This is the main entry point for setting up the Telegram bot.
    
    Args:
        agent_loop: AgentLoop instance
        module_manager: ModuleManager instance
        
    Returns:
        Application: The configured Telegram Application
    """
    TELEGRAM_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        logger.error("CRITICAL: TELEGRAM_TOKEN or BOT_TOKEN missing in .env")
        print("CRITICAL: TELEGRAM_TOKEN or BOT_TOKEN missing in .env")
        sys.exit(1)

    bot = TelegramBot(agent_loop, module_manager)
    defaults = Defaults(tzinfo=MY_TZ)
    request_config = HTTPXRequest(connect_timeout=60, read_timeout=60)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).defaults(defaults).request(request_config).build()

    # Register handlers
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("status", bot.status))
    app.add_handler(CommandHandler("stop", bot.turn_off))
    app.add_handler(CommandHandler("forge", bot.forge))
    app.add_handler(CommandHandler("initialize", bot.initialize))
    app.add_handler(CommandHandler("setup_security", bot.setup_security_cmd))
    app.add_handler(CommandHandler("purge", bot.purge_cmd))
    app.add_handler(CommandHandler("audit", bot.audit_cmd))
    app.add_handler(CommandHandler("upgrade", bot.upgrade_cmd))
    app.add_handler(CommandHandler("rollback", bot.rollback_cmd))
    app.add_handler(CommandHandler("learn", bot.learn_codebase))
    app.add_handler(CommandHandler("add_source", bot.add_source))
    
    # Memory management
    app.add_handler(CommandHandler("memory_stats", bot.memory_stats_cmd))
    app.add_handler(CommandHandler("cleanup_memory", bot.cleanup_memory_cmd))
    app.add_handler(CommandHandler("session_info", bot.session_info_cmd))
    app.add_handler(CommandHandler("new_session", bot.new_session_cmd))
    app.add_handler(CommandHandler("end_session", bot.end_session_cmd))
    app.add_handler(CommandHandler("switch_session", bot.switch_session_cmd))
    
    # Chat & Reminders
    app.add_handler(CommandHandler("chat", bot.chat_rag))
    app.add_handler(CommandHandler("remind", bot.remind_cmd))
    
    # Error handler
    app.add_error_handler(bot.error_handler)
    
    # Background jobs
    if app.job_queue:
        app.job_queue.run_repeating(bot.sentinel_monitoring, interval=5, first=10)

    return app
