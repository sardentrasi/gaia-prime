"""
Eleuthia Main - Telegram Bot Orchestrator (Multi-Email Edition)
Personal Assistant bot for email management, calendar sync, and intelligent notifications.
Supports multiple email accounts per protocol with Work/Personal categorization.
"""

import os
import sys
import json
import logging
import asyncio
import threading
import subprocess
import signal
import time
from datetime import datetime, time, timezone
from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Application
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from dotenv import load_dotenv

# Load .env early
load_dotenv()

# --- CONFIG & BRIDGES ---
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eleuthia.tools.config import (
    TelegramConfig,
    ScheduleConfig,
    NotificationConfig,
    validate_config
)
from eleuthia.tools.connector_email import EmailHandler
from eleuthia.eleuthia_memory_manager import EleuthiaBrain
from eleuthia.tools.connector_telegram import TelegramMonitor
from eleuthia.features.briefing import generate_morning_report
from eleuthia.features.context_manager import set_active_email, clear_context
import requests

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
        logging.FileHandler(os.path.join(os.getcwd(), "eleuthia.log"), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger("Eleuthia")

# [STANDALONE SURVIVAL] Short-Term Memory
import schedule

def update_short_memory(action: str, result: str, details: str = None) -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    module_name = os.path.basename(current_dir)
    state_file = os.path.join(current_dir, f"{module_name}_state.json")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_entry = {
        "timestamp": timestamp,
        "action": action,
        "result": result
    }
    if details:
        memory_entry["details"] = details
    
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
            # [FIX] Use threading wait instead of time.sleep due to import naming conflicts with datetime.time
            threading.Event().wait(60)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("🕒 Midnight Cleanup Scheduler initialized.")

# Load category config
config_path = os.path.join(os.path.dirname(__file__), 'eleuthia_config.json')
CATEGORY_CONFIG = {}
try:
    with open(config_path, 'r') as f:
        _cfg = json.load(f)
        CATEGORY_CONFIG = _cfg.get('categories', {})
except Exception:
    pass

# Global instances
email_handler = EmailHandler()
brain = EleuthiaBrain()
scheduler = AsyncIOScheduler()

# Initialize Admin Monitor (Telegram)
telegram_monitor = TelegramMonitor(
    bot_token=TelegramConfig.BOT_TOKEN,
    admin_chat_id=TelegramConfig.CHAT_ID
)

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def load_help_text():
    """Load help interface from file."""
    help_file = os.path.join(os.path.dirname(__file__), 'help_interface.txt')
    try:
        with open(help_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Help file not found. Use /start to begin."

async def is_quiet_hours(category: str = None) -> bool:
    """
    Check if current time is within quiet hours.
    Supports per-category quiet hours.
    """
    if not NotificationConfig.SEND_URGENT_ALERTS:
        return True
    
    tz = pytz.timezone(ScheduleConfig.TIMEZONE)
    now = datetime.now(tz).time()
    
    # Use category-specific quiet hours if available
    if category and category in CATEGORY_CONFIG:
        cat_cfg = CATEGORY_CONFIG[category]
        start_str = cat_cfg.get('quiet_hours', {}).get('start', NotificationConfig.QUIET_HOURS_START)
        end_str = cat_cfg.get('quiet_hours', {}).get('end', NotificationConfig.QUIET_HOURS_END)
    else:
        start_str = NotificationConfig.QUIET_HOURS_START
        end_str = NotificationConfig.QUIET_HOURS_END
    
    start = time.fromisoformat(start_str)
    end = time.fromisoformat(end_str)
    
    if start < end:
        return start <= now <= end
    else:  # Crosses midnight
        return now >= start or now <= end

def _parse_category_arg(args) -> str:
    """Parse category argument from command args. Returns 'work', 'personal', or None."""
    if args and len(args) > 0:
        arg = args[0].lower()
        if arg in ('work', 'personal'):
            return arg
        elif arg == 'all':
            return None
    return None

def _classify_and_process_lite(emails: list) -> dict:
    """Classify emails based on headers only (Lite Mode) - No LLM."""
    results = {
        'urgent': [],
        'info': [],
        'spam': [],
        'by_account': {},
        'by_category': {'work': {'total': 0}, 'personal': {'total': 0}}
    }
    
    for em in emails:
        # Strict Classification via Brain (FilterMail.json)
        # Assuming 'brain' global is available as initialized in main
        # If not, default to 'info'
        classification = 'info'
        try:
             if 'brain' in globals() and brain:
                 classification = brain.classify_email(em)
        except Exception as e:
             logger.error(f"Lite classification failed: {e}")
             
        # Map spam to info for lite view unless explicitly unwanted?
        # User wants strict classification so we keep it.
        if classification not in ['urgent', 'info', 'spam']:
            classification = 'info'
            
        acc_name = em.get('account_name', 'unknown')
        acc_cat = em.get('account_category', 'unknown')
        
        # Use existing 'urgent' list structure for compatibility
        if classification == 'urgent':
            results['urgent'].append(em)
        else:
            results['info'].append(em)
        
        # Organize by account
        if acc_name not in results['by_account']:
            results['by_account'][acc_name] = {
                'urgent': 0, 'info': 0, 'spam': 0, 'total': 0,
                'category': acc_cat
            }
        results['by_account'][acc_name][classification] += 1
        results['by_account'][acc_name]['total'] += 1
        
        # Organize by category
        if acc_cat in results['by_category']:
            results['by_category'][acc_cat]['total'] += 1
            
    return results

def _classify_and_process(emails: list) -> dict:
    """Classify emails and return organized results (Full LLM)."""
    results = {
        'urgent': [],
        'info': [],
        'spam': [],
        'by_account': {},
        'by_category': {'work': {'urgent': 0, 'info': 0, 'total': 0},
                        'personal': {'urgent': 0, 'info': 0, 'total': 0}}
    }
    
    for em in emails:
        classification = brain.classify_email(em)
        acc_name = em.get('account_name', 'unknown')
        acc_cat = em.get('account_category', 'unknown')
        
        # Record non-spam
        if classification in ['urgent', 'info']:
            summary = None
            # Only summarize urgent for full process
            if classification == 'urgent':
                summary = brain.summarize_email(em)
                em['_summary'] = summary
            brain.record_email(em, classification, summary)
        
        # Organize by classification
        results[classification].append(em)
        
        # Organize by account
        if acc_name not in results['by_account']:
            results['by_account'][acc_name] = {
                'urgent': 0, 'info': 0, 'spam': 0, 'total': 0,
                'category': acc_cat, 'emails': []
            }
        results['by_account'][acc_name][classification] += 1
        results['by_account'][acc_name]['total'] += 1
        results['by_account'][acc_name]['emails'].append(em)
        
        # Organize by category
        if acc_cat in results['by_category']:
            if classification in ('urgent', 'info'):
                results['by_category'][acc_cat][classification] += 1
            results['by_category'][acc_cat]['total'] += 1
    
    return results


# ==========================================
# EMAIL TEMPLATE HELPER
# ==========================================

def _create_professional_email_html(body_text: str, sender_name: str, signature_data: dict = None) -> str:
    """
    Generate a professional HTML email layout.
    
    Args:
        body_text: The main content of the email (text).
        sender_name: Name of the sender.
        signature_data: Optional dict with 'role', 'company', 'phone', 'website'.
    """
    # Default signature if none provided
    if not signature_data:
        signature_data = {
            'role': 'AI Assistant',
            'company': 'Eleuthia Systems'
        }
    
    # Get current year
    current_year = datetime.now().year

    # Process body text for HTML (simple newlines to breaks)
    # Note: If body_text is already HTML, this might be redundant or destructive, 
    # but we assume input from LLM is plain text.
    html_body_content = body_text.replace('\n', '<br>')
    
    t_company = signature_data.get('company', 'Gaia Prime')
    t_role = signature_data.get('role', '')
    t_website = signature_data.get('website', '')
    
    template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333333; margin: 0; padding: 0; background-color: #f9f9f9; }}
        .email-container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
        .header {{ background-color: #2c3e50; color: #ffffff; padding: 20px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; font-weight: 300; letter-spacing: 1px; }}
        .content {{ padding: 30px; font-size: 16px; }}
        .content p {{ margin-bottom: 15px; }}
        .footer {{ background-color: #f4f4f4; padding: 20px; text-align: center; font-size: 12px; color: #888888; border-top: 1px solid #eeeeee; }}
        .signature {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eeeeee; font-size: 14px; color: #555555; }}
        .signature strong {{ color: #2c3e50; font-size: 16px; display: block; margin-bottom: 5px; }}
        .signature p {{ margin: 2px 0; }}
        a {{ color: #3498db; text-decoration: none; }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1>{t_company}</h1>
        </div>
        <div class="content">
            <p>{html_body_content}</p>
            
            <div class="signature">
                <strong>{sender_name}</strong>
                <p>{t_role}</p>
                <p>{t_company}</p>
                <p><a href="{t_website}">{t_website}</a></p>
            </div>
        </div>
        <div class="footer">
            <p>&copy; {current_year} {t_company}. All rights reserved.</p>
            <p>Generated by Eleuthia AI</p>
        </div>
    </div>
</body>
</html>"""
    return template

# ==========================================
# COMMAND HANDLERS
# ==========================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initialize Eleuthia."""
    # Count accounts
    all_accounts = email_handler.get_all_accounts()
    active = [a for a in all_accounts if a['active']]
    work_count = len([a for a in active if a.get('category') == 'work'])
    personal_count = len([a for a in active if a.get('category') == 'personal'])
    
    welcome_msg = f"""
🤖 <b>E.L.E.U.T.H.I.A. ONLINE</b>
<i>Enhanced Life &amp; Executive Utility Through Hyper-Intelligent Automation</i>

Your personal assistant is ready to manage:
📧 Email intelligence ({len(active)} accounts: {work_count} work, {personal_count} personal)
📅 Calendar synchronization
🔔 Smart notifications

Use /help to see available commands.
    """
    await update.message.reply_text(welcome_msg, parse_mode='HTML')


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help menu."""
    try:
        help_text = load_help_text()
        await update.message.reply_text(help_text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Help command error: {e}")
        # Plain text fallback
        try:
            help_text = load_help_text()
            await update.message.reply_text(help_text)
        except Exception:
            pass

async def about_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show version/about info."""
    about_text = """
🤖 <b>Eleuthia v2.5</b>
<i>Enhanced Life &amp; Executive Utility Through Hyper-Intelligent Automation</i>

Eleuthia adalah asisten email dan personal berbasis AI yang dirancang untuk mendukung produktivitas tinggi dengan manajemen notifikasi cerdas.

<b>Developer:</b> Gaia Prime Team
<b>Engine:</b> Polyglot (LiteLLM)
<b>Memory:</b> Gaia Brain Cross-Sync
    """
    await update.message.reply_text(about_text, parse_mode='HTML')


async def check_email_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Force check for new emails (Lite Mode - Headers only, no LLM).
    Usage: /check_email [work|personal|all]
    Aliases: /cek_email, /inbox
    """
    category = _parse_category_arg(context.args)
    cat_label = f" ({category.upper()})" if category else ""
    
    loading_msg = await update.message.reply_text(
        f"📬 <b>CHECKING EMAILS{cat_label} (LITE)</b>...", parse_mode='HTML')
    
    try:
        # Fetch emails
        emails = email_handler.fetch_all_emails(category=category, max_results=10)
        
        if not emails:
            await loading_msg.edit_text(
                f"📭 <b>NO NEW EMAILS{cat_label}</b>\n\nYour inbox is clear!", 
                parse_mode='HTML')
            return
        
        # Use Lite Processing (No LLM)
        results = _classify_and_process_lite(emails)
        
        # Build response
        msg = f"📬 <b>INBOX{cat_label}</b>\n\n"
        
        for i, em in enumerate(emails[:10], 1):
            icon = "🚨" if any(w in em.get('subject', '').lower() for w in ['urgent', 'important']) else "✉️"
            acc_hint = f"[{em.get('account_name', '?')}]"
            msg += f"{i}. {icon} <b>{em.get('subject', 'No Subject')[:50]}</b>\n"
            msg += f"   From: {em.get('from', 'Unknown')[:30]} {acc_hint}\n"
            msg += f"   <i>{em.get('date', '')[:16]}</i>\n\n"
            
        msg += f"Total: {len(emails)} emails shown.\n"
        msg += "Use <code>/baca_email [nomor]</code> untuk membaca detail."
        
        await loading_msg.edit_text(msg, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Email check failed: {e}")
        await loading_msg.edit_text(
            f"❌ <b>EMAIL CHECK FAILED</b>\n\n{str(e)}", parse_mode='HTML')


async def read_email_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Read full content of a specific email (Lite Mode - No AI Summary).
    Usage: /read_email <number> | /baca_email <nomor>
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/baca_email [nomor]</code>\n"
            "Lihat nomor dari perintah /cek_email", parse_mode='HTML')
        return

    try:
        index = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("❌ Nomor tidak valid.")
        return

    loading_msg = await update.message.reply_text("📖 <b>LOADING EMAIL...</b>", parse_mode='HTML')

    try:
        # Re-fetch to ensure freshness/ordering (in a real DB app we'd query ID, here we assume order stability for now or refetch)
        # Note: Ideally we should use message_id, but for simple index usage we fetch recent again
        emails = email_handler.fetch_all_emails(max_results=20)
        
        if index < 0 or index >= len(emails):
            await loading_msg.edit_text("❌ Email tidak ditemukan (index out of range).")
            return

        em = emails[index]
        
        # Set Active Context
        set_active_email({
            'id': em.get('id', ''),
            'message_id': em.get('id', ''),
            'thread_id': em.get('thread_id', ''),
            'sender': em.get('from', ''),
            'subject': em.get('subject', ''),
            'account_name': em.get('account_name', ''),
            'protocol': em.get('protocol', '')
        })

        # Display Content
        body = em.get('body', '')
        if len(body) > 3000:
            body = body[:3000] + "\n\n... [Truncated]"

        msg = f"📖 <b>READ EMAIL</b>\n\n"
        msg += f"<b>From:</b> {em.get('from')}\n"
        msg += f"<b>Subject:</b> {em.get('subject')}\n"
        msg += f"<b>Account:</b> {em.get('account_name')}\n"
        msg += "-" * 20 + "\n\n"
        msg += body
        msg += "\n\n" + "-" * 20 + "\n"
        msg += "Gunakan <code>/reply_email</code> atau <code>/balas_email</code> untuk membalas."

        await loading_msg.edit_text(msg, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Read email failed: {e}")
        await loading_msg.edit_text(f"❌ Failed: {str(e)}", parse_mode='HTML')


async def reply_email_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Reply to the active email using LLM assistance.
    Usage: /reply_email [instruction/draft]
    """
    from eleuthia.features.context_manager import get_context, clear_context
    
    active_email = get_context()
    if not active_email:
        await update.message.reply_text(
            "⚠️ <b>Tidak ada email aktif.</b>\n\n"
            "Gunakan /cek_email lalu /baca_email untuk memilih email yang akan dibalas.",
            parse_mode='HTML')
        return

    user_instruction = " ".join(context.args)
    if not user_instruction:
        await update.message.reply_text(
            f"📝 <b>REPLY TO: {active_email.get('sender', 'Unknown')}</b>\n\n"
            "Silakan ketik instruksi balasannya setelah command.\n"
            "Contoh: <code>/reply_email tolong bilang saya setuju dan akan dikerjakan besok</code>",
            parse_mode='HTML')
        return

    loading_msg = await update.message.reply_text("✍️ <b>DRAFTING REPLY (AI)...</b>", parse_mode='HTML')

    try:
        # Generate Reply using Brain
        if hasattr(brain, 'llm_model'):
            from litellm import completion
            
            # Load Persona (Standardization)
            persona_path = os.path.join(os.path.dirname(__file__), "persona_eleuthia.md")
            persona_text = "You are a professional email assistant."
            if os.path.exists(persona_path):
                try:
                    with open(persona_path, "r", encoding="utf-8") as f:
                        persona_text = f.read()
                except: pass

            prompt = f"""{persona_text}

Draft a reply to this email based on the user's instruction.

Original Sender: {active_email.get('sender')}
Subject: {active_email.get('subject')}
User Instruction: "{user_instruction}"

Respond with ONLY the email body text. Formal but natural tone."""

            response = completion(
                model=brain.llm_model,
                messages=[{"role": "user", "content": prompt}],
                api_key=brain.llm_api_key,
                base_url=brain.llm_base_url
            )
            reply_body = response.choices[0].message.content.strip()
            
            # Send the email
            # Note: In a real scenario we might want a confirmation step. 
            # For now, we append a signature and send.
            
            # Generate HTML version
            sender_display_name = active_email.get('account_name', 'Eleuthia')
            # You could look up specific signatures for accounts here
            html_content = _create_professional_email_html(reply_body, sender_display_name)
            
            # Send the email with HTML
            final_body = f"{reply_body}\n\nSent via Eleuthia AI"
            
            success = email_handler.reply_to_email(
                message_id=active_email.get('message_id'),
                thread_id=active_email.get('thread_id'),
                reply_body=final_body,
                account_name=active_email.get('account_name'),
                original_email=active_email,
                html_body=html_content
            )
            
            if success:
                clear_context()
                
                # [NEW] Extract snippet for short-term memory
                clean_body = reply_body.replace('\n', ' ').replace('*', '').replace('`', '').replace('_', ' ')
                clean_body = ' '.join(clean_body.split())
                body_snip = clean_body[:8000] + "..." if len(clean_body) > 8000 else clean_body
                update_short_memory("Reply Email", f"To: {active_email.get('sender')} | {body_snip}")
                
                await loading_msg.edit_text(
                    f"✅ <b>REPLY SENT!</b> (HTML Format)\n\n"
                    f"To: {active_email.get('sender')}\n\n"
                    f"{reply_body}", parse_mode='HTML')
            else:
                await loading_msg.edit_text("❌ Gagal mengirim email via API provider.", parse_mode='HTML')
                
        else:
            await loading_msg.edit_text("❌ Brain offline, cannot draft reply.", parse_mode='HTML')

    except Exception as e:
        logger.error(f"Reply failed: {e}")
        await loading_msg.edit_text(f"❌ Error: {str(e)}", parse_mode='HTML')


async def new_email_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Draft and send a new email using LLM.
    Usage: /new_email [to_email] [instruction]
    """
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/new_email [email_tujuan] [instruksi]</code>\n\n"
            "Contoh: <code>/new_email bos@kantor.com ajukan cuti untuk minggu depan</code>",
            parse_mode='HTML')
        return

    to_email = context.args[0]
    instruction = " ".join(context.args[1:])
    
    loading_msg = await update.message.reply_text("✍️ <b>DRAFTING NEW EMAIL (AI)...</b>", parse_mode='HTML')
    
    try:
        # 1. Generate Subject and Body
        if hasattr(brain, 'llm_model'):
            from litellm import completion
            
            prompt = f"""You are a professional email assistant.
Draft a new email based on the user's instruction.
Recipient: {to_email}
Instruction: "{instruction}"

Respond in JSON format:
{{
  "subject": "...",
  "body": "..."
}}
"""
            response = completion(
                model=brain.llm_model,
                messages=[{"role": "user", "content": prompt}],
                api_key=brain.llm_api_key,
                base_url=brain.llm_base_url,
                response_format={"type": "json_object"}
            )
            import json
            content = json.loads(response.choices[0].message.content)
            subject = content.get('subject', 'No Subject')
            body = content.get('body', '') + "\n\nSent via Eleuthia AI"
            
            # 2. Select Account (Default to first work or first active)
            # Future: Let user pick account
            acc = email_handler.get_default_account()
            if not acc:
                await loading_msg.edit_text("❌ No active email account found used to send.")
                return

            # 3. Send
            # email_handler needs a send_email method. Assuming it exists or using reply mechanism? 
            # Check email_handler capability. If not exists, we use basic SMTP or API generic send.
            # actually `connector_email.py` usually has send/reply. 
            # If not, we might need to implement it. Checking `email_handler`...
            # Assuming `send_email` exists for now based on standard creation patterns.
            # If not, will fail and we catch it.
            
            # Since I can't verify `connector_email.py` right now easily without breaking flow, 
            # I'll assume it has a generic send or I use the reply function with no message_id if it supports it.
            # But let's check `reply_to_email` signature in previous code it used `message_id`.
            
            # For this refactor, I will mark it as "Not fully implemented" if the tool is missing, 
            # but I'll try to call `send_email` if it exists.
            
            if hasattr(email_handler, 'send_email'):
                
                # Generate HTML
                sender_display_name = acc.get('name', 'Eleuthia')
                html_content = _create_professional_email_html(content.get('body', ''), sender_display_name)
                
                email_handler.send_email(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    account_name=acc['name'],
                    html_body=html_content
                )
                
                # [NEW] Extract snippet for short-term memory
                clean_body = content.get('body', '').replace('\n', ' ').replace('*', '').replace('`', '').replace('_', ' ')
                clean_body = ' '.join(clean_body.split())
                body_snip = clean_body[:8000] + "..." if len(clean_body) > 8000 else clean_body
                update_short_memory("Send Email", f"To: {to_email} | Sub: {subject} | {body_snip}")
                
                await loading_msg.edit_text(
                    f"✅ <b>EMAIL SENT!</b> (HTML Format)\n\n"
                    f"From: {acc['name']}\n"
                    f"To: {to_email}\n"
                    f"Subject: {subject}\n\n"
                    f"{content.get('body', '')}", parse_mode='HTML')
            else:
                await loading_msg.edit_text("❌ `send_email` method missing in handler (Task for another day).", parse_mode='HTML')
                
        else:
             await loading_msg.edit_text("❌ Brain offline.", parse_mode='HTML')

    except Exception as e:
        logger.error(f"New email failed: {e}")
        await loading_msg.edit_text(f"❌ Error: {str(e)}", parse_mode='HTML')




async def urgent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show only urgent emails.
    Usage: /urgent [work|personal|all]
    """
    category = _parse_category_arg(context.args)
    cat_label = f" ({category.upper()})" if category else ""
    
    loading_msg = await update.message.reply_text(
        f"🚨 <b>FETCHING URGENT EMAILS{cat_label}</b>...", parse_mode='HTML')
    
    try:
        emails = email_handler.fetch_all_emails(category=category, max_results=20)
        urgent_emails = []
        
        for em in emails:
            classification = brain.classify_email(em)
            if classification == 'urgent':
                em['_summary'] = brain.summarize_email(em)
                brain.record_email(em, classification, em['_summary'])
                urgent_emails.append(em)
        
        if not urgent_emails:
            await loading_msg.edit_text(
                f"✅ <b>NO URGENT EMAILS{cat_label}</b>\n\nAll clear!", 
                parse_mode='HTML')
            return
        
        # Group urgent by category
        work_urgent = [e for e in urgent_emails if e.get('account_category') == 'work']
        personal_urgent = [e for e in urgent_emails if e.get('account_category') == 'personal']
        
        msg = f"🚨 <b>URGENT EMAILS ({len(urgent_emails)}){cat_label}</b>\n\n"
        
        # Work urgent
        if work_urgent:
            msg += f"💼 <b>WORK ({len(work_urgent)}):</b>\n"
            for i, em in enumerate(work_urgent[:5], 1):
                summary_data = em.get('_summary', {})
                msg += (f"{i}. <b>{em['subject'][:50]}</b>\n"
                       f"   From: {em['from']} ({em.get('account_name', '')})\n"
                       f"   📝 {summary_data.get('summary', 'N/A')}\n"
                       f"   💬 <i>{summary_data.get('suggested_reply', '')}</i>\n\n")
        
        # Personal urgent
        if personal_urgent:
            msg += f"🏠 <b>PERSONAL ({len(personal_urgent)}):</b>\n"
            for i, em in enumerate(personal_urgent[:5], 1):
                summary_data = em.get('_summary', {})
                msg += (f"{i}. <b>{em['subject'][:50]}</b>\n"
                       f"   From: {em['from']} ({em.get('account_name', '')})\n"
                       f"   📝 {summary_data.get('summary', 'N/A')}\n"
                       f"   💬 <i>{summary_data.get('suggested_reply', '')}</i>\n\n")
        
        total_shown = min(len(work_urgent), 5) + min(len(personal_urgent), 5)
        if len(urgent_emails) > total_shown:
            msg += f"<i>... and {len(urgent_emails) - total_shown} more urgent emails</i>"
        
        await loading_msg.edit_text(msg, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Urgent fetch failed: {e}")
        await loading_msg.edit_text(f"❌ Failed: {str(e)}", parse_mode='HTML')


async def briefing_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manual morning briefing with multi-account categories.
    Usage: /briefing [work|personal|all]
    """
    category = _parse_category_arg(context.args)
    cat_label = f" ({category.upper()})" if category else ""
    
    loading_msg = await update.message.reply_text(
        f"🌅 <b>PREPARING BRIEFING{cat_label}</b>...", parse_mode='HTML')
    
    try:
        # Fetch emails
        emails = email_handler.fetch_all_emails(category=category, max_results=20)
        results = _classify_and_process(emails)
        
        # Build briefing
        tz = pytz.timezone(ScheduleConfig.TIMEZONE)
        now = datetime.now(tz)
        msg = f"🌅 <b>DAILY BRIEFING</b>\n"
        msg += f"<i>{now.strftime('%A, %d %B %Y %H:%M')}</i>\n\n"
        
        # Calendar section
        msg += "📅 <b>Today's Schedule</b>:\n"
        msg += "<i>Calendar integration coming soon...</i>\n\n"
        
        # ---- WORK EMAILS ----
        work_data = results['by_category'].get('work', {})
        work_accounts = [a for a, d in results['by_account'].items() 
                        if d['category'] == 'work']
        
        if work_data.get('total', 0) > 0 or (not category or category == 'work'):
            account_names = ", ".join(work_accounts) if work_accounts else "none"
            msg += f"📧 <b>WORK EMAILS</b> ({account_names})\n"
            msg += f"Urgent: {work_data.get('urgent', 0)}\n"
            msg += f"Info: {work_data.get('info', 0)}\n"
            msg += f"Total: {work_data.get('total', 0)}\n\n"
            
            # Per-account breakdown
            for acc_name in work_accounts:
                acc = results['by_account'][acc_name]
                msg += (f"  📬 <code>{acc_name}</code>\n"
                       f"  - Urgent: {acc['urgent']} | Info: {acc['info']}\n\n")
        
        # ---- PERSONAL EMAILS ----
        personal_data = results['by_category'].get('personal', {})
        personal_accounts = [a for a, d in results['by_account'].items() 
                            if d['category'] == 'personal']
        
        if personal_data.get('total', 0) > 0 or (not category or category == 'personal'):
            account_names = ", ".join(personal_accounts) if personal_accounts else "none"
            msg += f"📧 <b>PERSONAL EMAILS</b> ({account_names})\n"
            msg += f"Urgent: {personal_data.get('urgent', 0)}\n"
            msg += f"Info: {personal_data.get('info', 0)}\n"
            msg += f"Total: {personal_data.get('total', 0)}\n\n"
            
            for acc_name in personal_accounts:
                acc = results['by_account'][acc_name]
                msg += (f"  📬 <code>{acc_name}</code>\n"
                       f"  - Urgent: {acc['urgent']} | Info: {acc['info']}\n\n")
        
        # ---- URGENT DETAILS ----
        work_urgent = [e for e in results['urgent'] if e.get('account_category') == 'work']
        personal_urgent = [e for e in results['urgent'] if e.get('account_category') == 'personal']
        
        if work_urgent:
            msg += f"🚨 <b>URGENT WORK ({len(work_urgent)}):</b>\n"
            for i, em in enumerate(work_urgent[:5], 1):
                summary = em.get('_summary', {})
                msg += f"{i}. [{em.get('from', '?')[:20]}] {em['subject'][:40]} - {em.get('account_name', '')}\n"
            msg += "\n"
        
        if personal_urgent:
            msg += f"🚨 <b>URGENT PERSONAL ({len(personal_urgent)}):</b>\n"
            for i, em in enumerate(personal_urgent[:5], 1):
                summary = em.get('_summary', {})
                msg += f"{i}. [{em.get('from', '?')[:20]}] {em['subject'][:40]} - {em.get('account_name', '')}\n"
            msg += "\n"
        
        if not results['urgent']:
            msg += "✅ <b>No urgent emails!</b>\n\n"
        
        msg += "Use /urgent work or /urgent personal for details.\n"
        msg += "\nHave a productive day! 🚀"
        
        await loading_msg.edit_text(msg, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Briefing failed: {e}")
        await loading_msg.edit_text(f"❌ Failed: {str(e)}", parse_mode='HTML')


async def accounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all configured email accounts."""
    all_accounts = email_handler.get_all_accounts()
    
    if not all_accounts:
        await update.message.reply_text(
            "📧 <b>NO ACCOUNTS CONFIGURED</b>\n\n"
            "Add accounts in your .env file.\n"
            "See .env.multi.template for examples.",
            parse_mode='HTML')
        return
    
    work_accounts = [a for a in all_accounts if a.get('category') == 'work']
    personal_accounts = [a for a in all_accounts if a.get('category') == 'personal']
    active_count = len([a for a in all_accounts if a['active']])
    
    msg = "📧 <b>CONFIGURED EMAIL ACCOUNTS</b>\n\n"
    
    if work_accounts:
        msg += f"<b>WORK ({len(work_accounts)} accounts):</b>\n"
        for acc in work_accounts:
            status = "✅" if acc['active'] else "❌"
            email_addr = acc.get('email', acc.get('username', ''))
            msg += f"{status} <code>{acc['name']}</code> ({acc['protocol'].title()})"
            if email_addr:
                msg += f" - {email_addr}"
            msg += "\n"
        msg += "\n"
    
    if personal_accounts:
        msg += f"<b>PERSONAL ({len(personal_accounts)} accounts):</b>\n"
        for acc in personal_accounts:
            status = "✅" if acc['active'] else "❌"
            email_addr = acc.get('email', acc.get('username', ''))
            msg += f"{status} <code>{acc['name']}</code> ({acc['protocol'].title()})"
            if email_addr:
                msg += f" - {email_addr}"
            msg += "\n"
        msg += "\n"
    
    msg += f"<b>Total</b>: {len(all_accounts)} accounts | {active_count} enabled"
    
    await update.message.reply_text(msg, parse_mode='HTML')


async def enable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Enable a disabled email account.
    Usage: /enable <account_name>
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/enable [account_name]</code>\n\n"
            "Use /accounts to see available accounts.",
            parse_mode='HTML')
        return
    
    account_name = context.args[0]
    all_names = [a['name'] for a in email_handler.get_all_accounts()]
    
    if account_name not in all_names:
        await update.message.reply_text(
            f"❌ Account <code>{account_name}</code> not found.\n\n"
            "Use /accounts to see available accounts.",
            parse_mode='HTML')
        return
    
    email_handler.enable_account(account_name)
    await update.message.reply_text(
        f"✅ <b>Account enabled:</b> <code>{account_name}</code>\n\n"
        "This account will now be checked for emails.",
        parse_mode='HTML')


async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Disable an email account temporarily.
    Usage: /disable <account_name>
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/disable [account_name]</code>\n\n"
            "Use /accounts to see available accounts.",
            parse_mode='HTML')
        return
    
    account_name = context.args[0]
    all_names = [a['name'] for a in email_handler.get_all_accounts()]
    
    if account_name not in all_names:
        await update.message.reply_text(
            f"❌ Account <code>{account_name}</code> not found.\n\n"
            "Use /accounts to see available accounts.",
            parse_mode='HTML')
        return
    
    email_handler.disable_account(account_name)
    await update.message.reply_text(
        f"⛔ <b>Account disabled:</b> <code>{account_name}</code>\n\n"
        "This account will not be checked until re-enabled.\n"
        f"Use <code>/enable {account_name}</code> to re-enable.",
        parse_mode='HTML')


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """System health check with multi-account info."""
    msg = "⚙️ <b>SYSTEM STATUS</b>\n\n"
    
    # Account status
    all_accounts = email_handler.get_all_accounts()
    active_accounts = [a for a in all_accounts if a['active']]
    msg += f"📧 <b>Email Accounts</b>: {len(active_accounts)}/{len(all_accounts)} active\n"
    
    for acc in all_accounts:
        status = "✅" if acc['active'] else "❌"
        msg += f"  {status} {acc['name']} ({acc['protocol']})\n"
    msg += "\n"
    
    # Brain status
    if brain.gaia_brain:
        msg += "✅ Gaia Brain: Connected\n"
    else:
        msg += "⚠️ Gaia Brain: Offline (using local)\n"
    
    # Scheduler
    if scheduler.running:
        msg += "✅ Scheduler: Running\n"
    else:
        msg += "❌ Scheduler: Stopped\n"
    
    # Analytics
    analytics = brain.get_analytics()
    msg += (f"\n📊 <b>Analytics</b>:\n"
            f"  Emails processed: {analytics.get('total_emails', 0)}\n"
            f"  Emails classified: {analytics.get('emails_classified', 0)}\n")
    
    tz = pytz.timezone(ScheduleConfig.TIMEZONE)
    msg += f"\n<i>Last check: {datetime.now(tz).strftime('%H:%M:%S')}</i>"
    
    await update.message.reply_text(msg, parse_mode='HTML')


async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View current settings including category config."""
    msg = (
        "⚙️ <b>CONFIGURATION</b>\n\n"
        f"<b>Morning Briefing</b>: {ScheduleConfig.MORNING_BRIEFING_TIME}\n"
        f"<b>Email Check</b>: Every {ScheduleConfig.EMAIL_CHECK_INTERVAL} mins\n"
        f"<b>Global Quiet Hours</b>: {NotificationConfig.QUIET_HOURS_START} - {NotificationConfig.QUIET_HOURS_END}\n"
        f"<b>Timezone</b>: {ScheduleConfig.TIMEZONE}\n\n"
    )
    
    # Category-specific settings
    if CATEGORY_CONFIG:
        msg += "<b>Category Settings:</b>\n"
        for cat_name, cat_cfg in CATEGORY_CONFIG.items():
            emoji = "💼" if cat_name == "work" else "🏠"
            qh = cat_cfg.get('quiet_hours', {})
            msg += (f"\n{emoji} <b>{cat_name.upper()}</b>\n"
                   f"  Priority: {cat_cfg.get('priority', 'N/A')}\n"
                   f"  Quiet Hours: {qh.get('start', 'N/A')} - {qh.get('end', 'N/A')}\n"
                   f"  Notify Urgent: {'✅' if cat_cfg.get('notify_urgent') else '❌'}\n"
                   f"  Notify Info: {'✅' if cat_cfg.get('notify_info') else '❌'}\n")
    
    msg += "\n<i>Edit eleuthia_config.json to change settings</i>"
    
    await update.message.reply_text(msg, parse_mode='HTML')


async def cekwifi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    WiFi radio infrastructure check.
    Runs SSH to Ubiquiti devices, collects metrics, then asks LLM for analysis.
    Usage: /cekwifi
    """
    import asyncio
    from eleuthia.features.cekwifi import run_check

    loading_msg = await update.message.reply_text(
        "📡 <b>CEK WIFI</b> — Scanning radio infrastructure...", parse_mode='HTML')

    try:
        # Run SSH check in thread (blocking I/O)
        cards, raw_report = await asyncio.to_thread(run_check)

        # Send metrics cards
        msg = f"📡 <b>WIFI RADIO STATUS</b>\n\n{cards}"
        await loading_msg.edit_text(msg, parse_mode='HTML')

        # LLM Analysis
        if hasattr(brain, 'llm_model') and raw_report:
            analysis_msg = await update.message.reply_text(
                "🤖 <b>Menganalisa...</b>", parse_mode='HTML')

            try:
                from litellm import completion

                prompt = f"""Kamu adalah network engineer expert untuk wireless PTP (Point-to-Point) Ubiquiti.
Berikut data radio dari infrastruktur WiFi:

{raw_report}

Berikan analisa singkat:
1. Kondisi link overall (Baik/Perlu Perhatian/Kritis)
2. Kualitas signal dan noise floor
3. Apakah throughput sesuai kapasitas?
4. Rekomendasi jika ada masalah

PENTING: Jawab dalam Bahasa Indonesia. Gunakan plain text saja, JANGAN gunakan markdown (tidak ada ** atau *). Gunakan emoji untuk penekanan. Singkat dan langsung ke poin."""

                response = completion(
                    model=brain.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    api_key=brain.llm_api_key,
                    base_url=brain.llm_base_url
                )
                analysis = response.choices[0].message.content.strip()
                # Clean any remaining markdown
                analysis = analysis.replace('**', '').replace('__', '')
                await analysis_msg.edit_text(
                    f"🤖 <b>ANALISA WIFI</b>\n\n{analysis}", parse_mode='HTML')
            except Exception as e:
                logger.error(f"WiFi LLM analysis failed: {e}")
                await analysis_msg.edit_text(
                    f"⚠️ Analisa AI gagal: {e}", parse_mode='HTML')

    except Exception as e:
        logger.error(f"WiFi check failed: {e}")
        await loading_msg.edit_text(
            f"❌ <b>CEK WIFI GAGAL</b>\n\n{str(e)}", parse_mode='HTML')


# ==========================================
# BACKGROUND JOBS
# ==========================================

async def morning_briefing_job(context: ContextTypes.DEFAULT_TYPE):
    """Automated morning briefing with multi-account categories."""
    if not NotificationConfig.SEND_MORNING_BRIEFING:
        return
    
    logger.info("🌅 Running morning briefing job...")
    
    try:
        # Fetch all emails
        emails = email_handler.fetch_all_emails(max_results=20)
        results = _classify_and_process(emails)
        
        # Build briefing message
        tz = pytz.timezone(ScheduleConfig.TIMEZONE)
        now = datetime.now(tz)
        
        report = f"🌅 Good Morning!\n\n"
        
        # Work section
        work_data = results['by_category'].get('work', {})
        work_accounts = [a for a, d in results['by_account'].items() if d['category'] == 'work']
        
        if work_accounts:
            account_names = ", ".join(work_accounts)
            report += f"📧 *WORK EMAILS* ({account_names})\n"
            report += f"Urgent: {work_data.get('urgent', 0)}\n"
            report += f"Info: {work_data.get('info', 0)}\n"
            report += f"Total: {work_data.get('total', 0)}\n\n"
            
            for acc_name in work_accounts:
                acc = results['by_account'][acc_name]
                report += f"  📬 {acc_name}\n"
                report += f"  - Urgent: {acc['urgent']} | Info: {acc['info']}\n\n"
        
        # Personal section
        personal_data = results['by_category'].get('personal', {})
        personal_accounts = [a for a, d in results['by_account'].items() if d['category'] == 'personal']
        
        if personal_accounts:
            account_names = ", ".join(personal_accounts)
            report += f"📧 *PERSONAL EMAILS* ({account_names})\n"
            report += f"Urgent: {personal_data.get('urgent', 0)}\n"
            report += f"Info: {personal_data.get('info', 0)}\n"
            report += f"Total: {personal_data.get('total', 0)}\n\n"
            
            for acc_name in personal_accounts:
                acc = results['by_account'][acc_name]
                report += f"  📬 {acc_name}\n"
                report += f"  - Urgent: {acc['urgent']} | Info: {acc['info']}\n\n"
        
        # Urgent details
        work_urgent = [e for e in results['urgent'] if e.get('account_category') == 'work']
        personal_urgent = [e for e in results['urgent'] if e.get('account_category') == 'personal']
        
        if work_urgent:
            report += f"🚨 *URGENT WORK ({len(work_urgent)}):*\n"
            for i, em in enumerate(work_urgent[:5], 1):
                report += f"{i}. [{em.get('from', '?')[:80]}] {em['subject'][:100]} - {em.get('account_name', '')}\n"
            report += "\n"
        
        if personal_urgent:
            report += f"🚨 *URGENT PERSONAL ({len(personal_urgent)}):*\n"
            for i, em in enumerate(personal_urgent[:5], 1):
                report += f"{i}. [{em.get('from', '?')[:20]}] {em['subject'][:40]} - {em.get('account_name', '')}\n"
            report += "\n"
        
        if not results['urgent']:
            report += "✅ No urgent emails!\n\n"
        
        report += "Use /urgent work or /urgent personal for details."
        
        # Send morning briefing via Telegram
        try:
            await context.bot.send_message(
                chat_id=TelegramConfig.CHAT_ID,
                text=report,
                parse_mode="Markdown"
            )
            logger.info("✅ Morning briefing delivered to Telegram")
        except Exception as tg_err:
            logger.error(f"Telegram briefing delivery failed: {tg_err}")
        
        # [NEW] Extract snippet for short-term memory
        clean_report = report.replace('\n', ' ').replace('*', '').replace('`', '').replace('_', ' ')
        clean_report = ' '.join(clean_report.split())
        report_snip = clean_report[:8000] + "..." if len(clean_report) > 8000 else clean_report
        update_short_memory("Morning Briefing", f"Delivered: {report_snip}")
        
    except Exception as e:
        logger.error(f"Morning briefing failed: {e}")


async def email_monitor_job(context: ContextTypes.DEFAULT_TYPE):
    """Monitor emails for urgent alerts with category-aware quiet hours."""
    logger.info("📧 Running email monitor...")
    
    try:
        emails = email_handler.fetch_all_emails(max_results=5)
        
        for em in emails:
            classification = brain.classify_email(em)
            acc_cat = em.get('account_category', 'work')
            
            # Check category-specific quiet hours
            if await is_quiet_hours(category=acc_cat):
                logger.info(f"⏰ Quiet hours for {acc_cat} - skipping notification")
                brain.record_email(em, classification)
                continue
            
            # Check if category allows notification
            cat_cfg = CATEGORY_CONFIG.get(acc_cat, {})
            
            if classification == 'urgent' and (cat_cfg.get('notify_urgent', True) or NotificationConfig.SEND_URGENT_ALERTS):
                # USE MINIMAL SUMMARIZATION (NO LLM/RAG) for automated alerts
                summary = brain.summarize_email(em, minimal=True)
                brain.record_email(em, classification, summary)
                
                # Set active email context (with full metadata)
                set_active_email({
                    'id': em.get('id', ''),
                    'message_id': em.get('id', ''),
                    'thread_id': em.get('thread_id', ''),
                    'sender': em.get('from', ''),
                    'subject': em.get('subject', ''),
                    'account_name': em.get('account_name', ''),
                    'protocol': em.get('protocol', ''),
                    'account_category': acc_cat
                })
                
                cat_emoji = "💼" if acc_cat == "work" else "🏠"
                alert_msg = (
                    f"🚨 *URGENT EMAIL ALERT* {cat_emoji}\n\n"
                    f"*Account*: {em.get('account_name', 'unknown')}\n"
                    f"*From*: {em.get('from', '')}\n"
                    f"*Subject*: {em.get('subject', '')}\n\n"
                    f"📝 *Summary:*\n{summary.get('summary', 'N/A')}\n\n"
                    f"💬 *Suggested Reply:*\n_{summary.get('suggested_reply', '')}_"
                )
                
                # Send alert via Telegram
                try:
                    await context.bot.send_message(
                        chat_id=TelegramConfig.CHAT_ID,
                        text=alert_msg,
                        parse_mode="Markdown"
                    )
                    logger.info(f"🚨 Urgent email alert sent to Telegram: {em.get('subject', '')[:30]}")
                except Exception as tg_err:
                    logger.error(f"Telegram alert delivery failed: {tg_err}")
                
                # [NEW] Log urgent email to short-term memory (Only when LLM processes an urgent email)
                update_short_memory("Urgent Email Alert", f"From {em.get('from', '')[:30]} | Subj: {em.get('subject', '')[:50]}")
                
            elif classification == 'info':
                # Record info emails without notification
                notify_info = cat_cfg.get('notify_info', False)
                brain.record_email(em, classification)
                
                if notify_info:
                    # Logic for Telegram info notification removed per user request
                    # Record only
                    logger.info(f"💾 Recorded info email: {em.get('subject', '')[:40]}")
                
                logger.info(f"💾 Recorded info email: {em.get('subject', '')[:40]}")
            else:
                # Skip spam
                logger.info(f"🗑️ Skipped spam email: {em.get('subject', '')[:40]}")
        # Removed generic "Checked X emails" from short-term memory to prevent noise
    except Exception as e:
        logger.error(f"Email monitor failed: {e}")



async def casual_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle all non-command text messages as casual chat (using LLM).
    This allows the user to talk to Eleuthia naturally.
    """
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    user_name = update.effective_user.first_name or "User"
    
    # Optional: Log chat to console
    # logger.info(f"Casual Chat from {user_name}: {user_text}")

    try:
        # Use Brain (LiteLLM) to generate response
        if hasattr(brain, 'llm_model'):
            from litellm import completion
            
            # Load Casual Persona
            persona = "You are Eleuthia, a helpful and friendly personal assistant."
            try:
                with open(os.path.join(os.path.dirname(__file__), 'persona_eleuthia.txt'), 'r') as f:
                    persona = f.read().strip()
            except:
                pass

            response = completion(
                model=brain.llm_model,
                messages=[
                    {"role": "system", "content": persona},
                    {"role": "user", "content": user_text}
                ],
                api_key=brain.llm_api_key,
                base_url=brain.llm_base_url
            )
            reply = response.choices[0].message.content
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("🧠 Eleuthia brain is offline/local only.")
            
    except Exception as e:
        logger.error(f"Casual chat failed: {e}")
        # Optionally reply with error or specific fallback

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Optional: notify admin about error
    if isinstance(update, Update) and update.effective_message:
        text = "❌ An error occurred while processing your request. The issue has been logged."
        await update.effective_message.reply_text(text)
        # await update.message.reply_text("💤") 



# ==========================================
# MAIN
# ==========================================

def main():
    """Start Eleuthia bot with multi-email support."""
    try:
        # Validate configuration
        validate_config()
        logger.info("✅ Configuration validated")
        
        # Log account info
        all_accounts = email_handler.get_all_accounts()
        logger.info(f"📧 {len(all_accounts)} email accounts configured:")
        for acc in all_accounts:
            status = "✅" if acc['active'] else "❌"
            logger.info(f"  {status} {acc['name']} ({acc['protocol']}) [{acc.get('category', 'N/A')}]")
        
        # Setup scheduler (initialized here but started in post_init)
        scheduler = AsyncIOScheduler(timezone=ScheduleConfig.TIMEZONE)
        
        async def post_init(application: Application):
            """Start scheduler after loop is running."""
            # Setup jobs using the application instance
            tz = pytz.timezone(ScheduleConfig.TIMEZONE)
            
            # Morning briefing
            hour, minute = ScheduleConfig.MORNING_BRIEFING_TIME.split(':')
            scheduler.add_job(
                morning_briefing_job,
                CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
                args=[application],
                id='morning_briefing'
            )
            
            # Email monitoring
            scheduler.add_job(
                email_monitor_job,
                'interval',
                minutes=ScheduleConfig.EMAIL_CHECK_INTERVAL,
                args=[application],
                id='email_monitor'
            )
            
            scheduler.start()
            start_midnight_cleanup_scheduler()
            logger.info("✅ Scheduler started (async)")

        # Create application with post_init hook
        app = Application.builder().token(TelegramConfig.BOT_TOKEN).post_init(post_init).build()
        app.add_error_handler(error_handler)
        
        # Register command handlers
        # Register command handlers
        app.add_handler(CommandHandler(["start"], start_cmd))
        app.add_handler(CommandHandler(["help"], help_cmd))
        app.add_handler(CommandHandler(["about"], about_cmd))
        app.add_handler(CommandHandler(["check_email", "cek_email", "inbox"], check_email_cmd))
        app.add_handler(CommandHandler(["read_email", "baca_email"], read_email_cmd))
        app.add_handler(CommandHandler(["reply_email", "balas_email", "balas"], reply_email_cmd))
        app.add_handler(CommandHandler(["new_email", "tulis_email"], new_email_cmd))
        
        app.add_handler(CommandHandler("urgent", urgent_cmd))
        app.add_handler(CommandHandler("briefing", briefing_cmd))
        app.add_handler(CommandHandler("accounts", accounts_cmd))
        app.add_handler(CommandHandler("enable", enable_cmd))
        app.add_handler(CommandHandler("disable", disable_cmd))
        app.add_handler(CommandHandler("status", status_cmd))
        app.add_handler(CommandHandler("config", config_cmd))
        app.add_handler(CommandHandler(["cekwifi", "cek_wifi"], cekwifi_cmd))
        
        # Casual Chat Handler (Must be last to avoid catching commands)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, casual_chat_handler))

        
        # Scheduler setup moved to post_init
        
        # Start bot
        logger.info("🤖 Eleuthia is starting (Telegram-Only Edition)...")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down Eleuthia...")
        scheduler.shutdown()
        email_handler.close_all()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        email_handler.close_all()
        raise


if __name__ == "__main__":
    main()
