import json
import os
import logging
import time

logger = logging.getLogger(__name__)

class EmailFilter:
    """
    Handles deterministic email filtering based on external JSON configuration.
    Supports hot-reloading to avoid restarting the bot for rule changes.
    """
    def __init__(self, filter_path: str):
        self.filter_path = filter_path
        self.filters = {}
        self.last_load_time = 0
        self.reload_interval = 60 # Check for updates every 60 seconds
        self._load_filters()

    def _load_filters(self):
        """Load rules from filtermail.json."""
        if not os.path.exists(self.filter_path):
            logger.warning(f"⚠️ Filter file not found: {self.filter_path}")
            # Create a basic template if missing
            self._create_template()
        
        try:
            with open(self.filter_path, 'r', encoding='utf-8') as f:
                self.filters = json.load(f)
                self.last_load_time = time.time()
                logger.info(f"✅ Loaded email filters from {os.path.basename(self.filter_path)}")
        except Exception as e:
            logger.error(f"❌ Failed to load filters: {e}")
            if not self.filters:
                self.filters = {"urgent": {"from": [], "subject": []}, "spam": {"from": [], "subject": []}, "info": {"from": [], "subject": []}}

    def _create_template(self):
        """Creates a default filtermail.json if it doesn't exist."""
        template = {
            "urgent": {
                "from": ["boss@company.com"],
                "subject": ["urgent", "asap", "deadline"]
            },
            "spam": {
                "from": ["newsletter", "promo"],
                "subject": ["unsubscribe", "diskon"]
            },
            "info": {
                "from": [],
                "subject": ["pemberitahuan", "update"]
            }
        }
        try:
            with open(self.filter_path, 'w', encoding='utf-8') as f:
                json.dump(template, f, indent=2)
            logger.info(f"✨ Created filter template at {self.filter_path}")
        except Exception as e:
            logger.error(f"Failed to create template: {e}")

    def _check_reload(self):
        """Reload filters if interval passed and file changed."""
        if time.time() - self.last_load_time > self.reload_interval:
            if os.path.exists(self.filter_path):
                # We could check mtime here for more efficiency, but reload_interval is fine
                self._load_filters()

    def classify(self, email_obj: dict) -> str:
        """
        Determine classification ('urgent', 'info', 'spam') based on filters.
        Returns 'info' if no match found.
        """
        self._check_reload()
        
        sender = email_obj.get('from', '').lower()
        subject = email_obj.get('subject', '').lower()
        
        # 1. Check Urgent (Highest Priority)
        urgent = self.filters.get('urgent', {})
        if self._matches(sender, urgent.get('from', [])) or self._matches(subject, urgent.get('subject', [])):
            return 'urgent'
            
        # 2. Check Spam
        spam = self.filters.get('spam', {})
        if self._matches(sender, spam.get('from', [])) or self._matches(subject, spam.get('subject', [])):
            return 'spam'
            
        # 3. Check Info
        info = self.filters.get('info', {})
        if self._matches(sender, info.get('from', [])) or self._matches(subject, info.get('subject', [])):
            return 'info'
            
        # Default fallback
        return 'info'

    def _matches(self, text: str, patterns: list) -> bool:
        """Helper to check if text contains any of the patterns (case-insensitive)."""
        if not text or not patterns:
            return False
        return any(p.lower() in text for p in patterns)
