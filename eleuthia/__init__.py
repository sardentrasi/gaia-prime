"""
E.L.E.U.T.H.I.A. - Enhanced Life & Executive Utility Through Hyper-Intelligent Automation

A personal assistant module for the GAIA PRIME ecosystem.
Handles email management, calendar integration, and intelligent notifications via Telegram.
"""

__version__ = "1.0.0"
__author__ = "GAIA PRIME"

from .tools.config import (
    EmailConfig,
    CalendarConfig,
    TelegramConfig,
    LLMConfig,
    ScheduleConfig,
    ClassificationConfig,
    NotificationConfig,
    validate_config
)

__all__ = [
    'EmailConfig',
    'CalendarConfig',
    'TelegramConfig',
    'LLMConfig',
    'ScheduleConfig',
    'ClassificationConfig',
    'NotificationConfig',
    'validate_config'
]
