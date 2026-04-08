"""
Telegram Monitor Connector
Handles admin notifications and system monitoring via Telegram.
Used for system alerts and status updates.
"""

import os
import logging
import requests
import io
from typing import Optional

logger = logging.getLogger(__name__)

class TelegramMonitor:
    """
    Telegram connector for admin monitoring and notifications.
    Sends system alerts, QR codes, and status updates to admin chat.
    """
    
    def __init__(self, bot_token: str, admin_chat_id: str):
        """
        Initialize Telegram monitor.
        
        Args:
            bot_token: Telegram bot token
            admin_chat_id: Admin's Telegram chat ID
        """
        self.bot_token = bot_token
        self.admin_chat_id = admin_chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        
        # Validate connection
        if not self._test_connection():
            logger.error("❌ Failed to connect to Telegram API")
        else:
            logger.info("✅ Telegram Monitor initialized")
    
    def _test_connection(self) -> bool:
        """Test Telegram API connection."""
        try:
            response = requests.get(f"{self.api_base}/getMe", timeout=5)
            if response.status_code == 200:
                bot_info = response.json()
                logger.info(f"🤖 Connected to bot: {bot_info['result']['username']}")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Send plain text message to admin chat.
        
        Args:
            text: Message text
            parse_mode: Formatting mode (Markdown/HTML)
        
        Returns:
            True if sent successfully
        """
        try:
            payload = {
                'chat_id': self.admin_chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            response = requests.post(
                f"{self.api_base}/sendMessage",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"📤 Message sent to Telegram: {text[:50]}...")
                return True
            else:
                logger.error(f"Failed to send message: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    def send_image(self, image_data: bytes, caption: str = "", parse_mode: str = "Markdown") -> bool:
        """
        Send image to admin chat.
        
        Args:
            image_data: Raw image bytes (PNG/JPEG)
            caption: Image caption
            parse_mode: Caption formatting mode
        
        Returns:
            True if sent successfully
        """
        try:
            files = {
                'photo': ('qr_code.png', io.BytesIO(image_data), 'image/png')
            }
            
            data = {
                'chat_id': self.admin_chat_id,
                'caption': caption,
                'parse_mode': parse_mode
            }
            
            response = requests.post(
                f"{self.api_base}/sendPhoto",
                files=files,
                data=data,
                timeout=15
            )
            
            if response.status_code == 200:
                logger.info(f"📸 Image sent to Telegram with caption: {caption[:50]}...")
                return True
            else:
                logger.error(f"Failed to send image: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending image: {e}")
            return False
    
    def send_startup_signal(self) -> bool:
        """
        Send system startup notification.
        
        Returns:
            True if sent successfully
        """
        startup_msg = """
🚀 **ELEUTHIA SYSTEM ONLINE**

**Status**: Initializing...
**Timestamp**: {timestamp}

Checking peripherals:
⏳ Email connectors...
⏳ Memory core...

Standby for status update.
        """.format(timestamp=self._get_timestamp())
        
        return self.send_message(startup_msg)
    
    def send_error_alert(self, error_msg: str, component: str = "System") -> bool:
        """
        Send error alert to admin.
        
        Args:
            error_msg: Error message
            component: Component name
        
        Returns:
            True if sent successfully
        """
        alert = f"""
❌ **ERROR ALERT**

**Component**: {component}
**Error**: {error_msg}
**Timestamp**: {self._get_timestamp()}

Action may be required.
        """
        return self.send_message(alert)
    
    def send_status_update(self, status_dict: dict) -> bool:
        """
        Send system status update.
        
        Args:
            status_dict: Dictionary with component statuses
        
        Returns:
            True if sent successfully
        """
        msg = "📊 **SYSTEM STATUS**\n\n"
        
        for component, status in status_dict.items():
            emoji = "✅" if status.get('ok', False) else "❌"
            msg += f"{emoji} **{component}**: {status.get('message', 'Unknown')}\n"
        
        msg += f"\n*Last check: {self._get_timestamp()}*"
        
        return self.send_message(msg)
    
    def _get_timestamp(self) -> str:
        """Get formatted timestamp."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    # Test monitor
    logging.basicConfig(level=logging.INFO)
    
    # Load from env
    from dotenv import load_dotenv
    load_dotenv()
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    admin_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not admin_id:
        print("❌ Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
        exit(1)
    
    monitor = TelegramMonitor(bot_token, admin_id)
    
    # Test message
    monitor.send_message("🧪 Test message from TelegramMonitor")
    
    # Test startup signal
    monitor.send_startup_signal()
    
    # Test status update
    monitor.send_status_update({
        'Email': {'ok': True, 'message': 'Connected'},
        'Memory': {'ok': True, 'message': 'Operational'}
    })
