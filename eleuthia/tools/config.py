"""
Eleuthia Configuration Module
Loads environment variables and provides configuration access.
"""

import os
import json
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict, Optional

# Load .env from eleuthia directory (parent of tools)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Load JSON config
config_json_path = Path(__file__).parent.parent / 'eleuthia_config.json'
try:
    with open(config_json_path, 'r', encoding='utf-8') as f:
        JSON_CONFIG = json.load(f)
except FileNotFoundError:
    print(f"⚠️ Warning: {config_json_path} not found. Using defaults.")
    JSON_CONFIG = {
        "scheduling": {
            "morning_briefing_time": "07:00",
            "email_check_interval_minutes": 5,
            "calendar_sync_interval_minutes": 60,
            "timezone": "Asia/Jakarta"
        },
        "classification": {
            "urgent_keywords": ["urgent", "asap", "deadline"],
            "spam_keywords": ["unsubscribe", "promotional"],
            "info_keywords": ["newsletter", "update"]
        },
        "notification_settings": {
            "send_morning_briefing": True,
            "send_urgent_alerts": True
        }
    }

# Email Account Configuration (Multi-Account Support)
class EmailAccountConfig:
    """Configuration for multiple email accounts per protocol."""
    
    @staticmethod
    @staticmethod
    def _get_config(key: str, env_var: str, default: List[Dict] = None) -> List[Dict]:
        """Get config from JSON_CONFIG first, then environment variable."""
        # 1. Try eleuthia_config.json
        if key in JSON_CONFIG:
            return JSON_CONFIG[key]
        
        # 2. Try environment variable
        value = os.getenv(env_var)
        if not value:
            return default or []
        
        try:
            # Handle both JSON string and Python dict format
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError as e:
            print(f"⚠️ Warning: Failed to parse {env_var}: {e}")
            return default or []
    
    @staticmethod
    def get_gmail_accounts() -> List[Dict]:
        """Get all configured Gmail accounts."""
        accounts = EmailAccountConfig._get_config('gmail_accounts', 'GMAIL_ACCOUNTS')
        
        # Fallback to legacy single account
        if not accounts:
            legacy_path = os.getenv('GMAIL_CREDENTIALS_PATH')
            if legacy_path:
                accounts = [{
                    'name': 'default_gmail',
                    'category': 'work',
                    'credentials_path': legacy_path,
                    'token_path': os.getenv('GMAIL_TOKEN_PATH', './eleuthia/credentials/gmail_token.json'),
                    'enabled': True
                }]
        
        return accounts
    
    @staticmethod
    def get_outlook_accounts() -> List[Dict]:
        """Get all configured Outlook accounts."""
        accounts = EmailAccountConfig._get_config('outlook_accounts', 'OUTLOOK_ACCOUNTS')
        
        # Fallback to legacy single account
        if not accounts:
            client_id = os.getenv('OUTLOOK_CLIENT_ID')
            if client_id:
                accounts = [{
                    'name': 'default_outlook',
                    'category': 'work',
                    'client_id': client_id,
                    'client_secret': os.getenv('OUTLOOK_CLIENT_SECRET'),
                    'tenant_id': os.getenv('OUTLOOK_TENANT_ID', 'common'),
                    'enabled': True
                }]
        
        return accounts
    
    @staticmethod
    def get_imap_accounts() -> List[Dict]:
        """Get all configured IMAP accounts."""
        accounts = EmailAccountConfig._get_config('imap_accounts', 'IMAP_ACCOUNTS')
        
        # Fallback to legacy single account
        if not accounts:
            username = os.getenv('IMAP_USERNAME')
            if username:
                accounts = [{
                    'name': 'default_imap',
                    'category': 'work',
                    'host': os.getenv('IMAP_HOST', 'imap.gmail.com'),
                    'port': int(os.getenv('IMAP_PORT', '993')),
                    'username': username,
                    'password': os.getenv('IMAP_PASSWORD'),
                    'enabled': True
                }]
        
        return accounts

# Legacy Email Configuration (Backward Compatibility)
class EmailConfig:
    # Gmail
    GMAIL_CREDENTIALS_PATH = os.getenv('GMAIL_CREDENTIALS_PATH', './eleuthia/credentials/gmail_credentials.json')
    GMAIL_TOKEN_PATH = os.getenv('GMAIL_TOKEN_PATH', './eleuthia/credentials/gmail_token.json')
    
    # Outlook
    OUTLOOK_CLIENT_ID = os.getenv('OUTLOOK_CLIENT_ID')
    OUTLOOK_CLIENT_SECRET = os.getenv('OUTLOOK_CLIENT_SECRET')
    OUTLOOK_TENANT_ID = os.getenv('OUTLOOK_TENANT_ID', 'common')
    
    # IMAP Fallback
    IMAP_HOST = os.getenv('IMAP_HOST', 'imap.gmail.com')
    IMAP_PORT = int(os.getenv('IMAP_PORT', '993'))
    IMAP_USERNAME = os.getenv('IMAP_USERNAME')
    IMAP_PASSWORD = os.getenv('IMAP_PASSWORD')

# Calendar Configuration
class CalendarConfig:
    GOOGLE_CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
    OUTLOOK_CALENDAR_ID = os.getenv('OUTLOOK_CALENDAR_ID', 'primary')

# Telegram Configuration
class TelegramConfig:
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# LLM Configuration
class LLMConfig:
    API_KEY = os.getenv('LLM_API_KEY')
    MODEL = os.getenv('LLM_MODEL', 'openrouter/arcee-ai/trinity-large-preview:free')
    BASE_URL = os.getenv('OLLAMA_BASE_URL', 'https://openrouter.ai/api/v1')

# Scheduling Configuration (from JSON)
class ScheduleConfig:
    MORNING_BRIEFING_TIME = JSON_CONFIG.get('scheduling', {}).get('morning_briefing_time', '07:00')
    EMAIL_CHECK_INTERVAL = JSON_CONFIG.get('scheduling', {}).get('email_check_interval_minutes', 5)
    CALENDAR_SYNC_INTERVAL = JSON_CONFIG.get('scheduling', {}).get('calendar_sync_interval_minutes', 60)
    TIMEZONE = JSON_CONFIG.get('scheduling', {}).get('timezone', os.getenv('TIMEZONE', 'Asia/Jakarta'))

# Classification Configuration (from JSON)
class ClassificationConfig:
    URGENT_KEYWORDS = JSON_CONFIG.get('classification', {}).get('urgent_keywords', [])
    SPAM_KEYWORDS = JSON_CONFIG.get('classification', {}).get('spam_keywords', [])
    INFO_KEYWORDS = JSON_CONFIG.get('classification', {}).get('info_keywords', [])

# Notification Settings (from JSON)
class NotificationConfig:
    SEND_MORNING_BRIEFING = JSON_CONFIG.get('notification_settings', {}).get('send_morning_briefing', True)
    SEND_URGENT_ALERTS = JSON_CONFIG.get('notification_settings', {}).get('send_urgent_alerts', True)
    SEND_CALENDAR_REMINDERS = JSON_CONFIG.get('notification_settings', {}).get('send_calendar_reminders', True)
    QUIET_HOURS_START = JSON_CONFIG.get('notification_settings', {}).get('quiet_hours_start', '22:00')
    QUIET_HOURS_END = JSON_CONFIG.get('notification_settings', {}).get('quiet_hours_end', '06:00')

# Validation
def validate_config():
    """Validate critical configuration values."""
    errors = []
    
    if not TelegramConfig.BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is required")
    
    if not TelegramConfig.CHAT_ID:
        errors.append("TELEGRAM_CHAT_ID is required")
    
    if not LLMConfig.API_KEY:
        errors.append("LLM_API_KEY is required")
    
    # At least one email source must be configured
    has_email_source = any([
        len(EmailAccountConfig.get_gmail_accounts()) > 0,
        len(EmailAccountConfig.get_outlook_accounts()) > 0,
        len(EmailAccountConfig.get_imap_accounts()) > 0
    ])
    
    if not has_email_source:
        errors.append("At least one email source must be configured (Gmail/Outlook/IMAP)")
    
    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True

if __name__ == "__main__":
    # Test configuration
    try:
        validate_config()
        print("✅ Configuration valid!")
        print(f"Telegram Bot: {TelegramConfig.BOT_TOKEN[:10]}...")
        print(f"LLM Model: {LLMConfig.MODEL}")
        print(f"Morning Briefing: {ScheduleConfig.MORNING_BRIEFING_TIME}")
        print(f"Urgent Keywords: {ClassificationConfig.URGENT_KEYWORDS}")
    except ValueError as e:
        print(f"❌ {e}")
