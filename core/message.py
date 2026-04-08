"""
Gaia Prime - Unified Message Layer
Platform-agnostic message envelope used across all connectors.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class GaiaMessage:
    """
    Universal message envelope that flows through the entire Gaia pipeline.
    Created by the Telegram connector, consumed by the Agent Loop.
    """
    user_id: str                      # Canonical user ID (Telegram user ID)
    user_name: str                    # Display name
    text: str                         # Message content (query)
    platform: str                     # "telegram"
    target_id: Optional[str] = None   # Reply target (chat_id for routing response)
    raw: Optional[dict] = None        # Platform-specific raw data (images, forwarded msgs, etc.)
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Metadata populated during processing
    is_command: bool = False           # True if message starts with /
    command: Optional[str] = None      # The command name (without /)
    command_args: list = field(default_factory=list)  # Command arguments
    
    @property
    def is_short(self) -> bool:
        """Messages under 50 chars are candidates for small talk detection."""
        return len(self.text) < 50
    
    @property
    def has_substance(self) -> bool:
        """Messages over 10 chars and not commands are worth recording."""
        return len(self.text) > 10 and not self.is_command
    
    def __str__(self):
        return f"[{self.platform}] {self.user_name}: {self.text[:50]}..."
