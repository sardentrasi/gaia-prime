"""
Context Manager for Email Reply Tracking
Maintains state of the last email for reply routing.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Global context state
_context = {
    "last_email_id": None,
    "message_id": None,
    "thread_id": None,
    "sender": None,
    "subject": None,
    "account_name": None,
    "protocol": None,
    "timestamp": None
}

# Context expiry time (minutes)
CONTEXT_EXPIRY_MINUTES = 60

def set_active_email(email_data: Dict) -> None:
    """
    Set the active email context for reply routing.
    
    Args:
        email_data: Dict with keys: id, message_id, thread_id, sender, subject, account_name, protocol
    """
    global _context
    
    _context = {
        "last_email_id": email_data.get('id'),
        "message_id": email_data.get('message_id'),
        "thread_id": email_data.get('thread_id'),
        "from": email_data.get('sender', email_data.get('from')),
        "sender": email_data.get('sender', email_data.get('from')),
        "subject": email_data.get('subject'),
        "account_name": email_data.get('account_name'),
        "protocol": email_data.get('protocol'),
        "timestamp": datetime.now()
    }
    
    logger.info(f"📌 Context set: Email from {_context['sender']} (Account: {_context['account_name']})")
    logger.debug(f"   Subject: {_context['subject']}")
    logger.debug(f"   Protocol: {_context['protocol']}")

def get_context() -> Optional[Dict]:
    """
    Get the current email context if still valid.
    
    Returns:
        Context dict if valid, None if expired or not set
    """
    global _context
    
    if not _context.get('timestamp'):
        logger.warning("⚠️ No active email context")
        return None
    
    # Check expiry
    age = datetime.now() - _context['timestamp']
    if age > timedelta(minutes=CONTEXT_EXPIRY_MINUTES):
        logger.warning(f"⏰ Context expired (age: {age.total_seconds()/60:.1f} min)")
        clear_context()
        return None
    
    logger.info(f"✅ Context valid: {_context['sender']} (age: {age.total_seconds()/60:.1f} min)")
    return _context.copy()

def clear_context() -> None:
    """Clear the current email context."""
    global _context
    
    old_sender = _context.get('sender')
    
    _context = {
        "last_email_id": None,
        "message_id": None,
        "thread_id": None,
        "sender": None,
        "subject": None,
        "timestamp": None
    }
    
    if old_sender:
        logger.info(f"🗑️ Context cleared: {old_sender}")

def get_context_age_minutes() -> Optional[float]:
    """
    Get the age of the current context in minutes.
    
    Returns:
        Age in minutes, or None if no context
    """
    if not _context.get('timestamp'):
        return None
    
    age = datetime.now() - _context['timestamp']
    return age.total_seconds() / 60

def is_context_valid() -> bool:
    """
    Check if context is valid without retrieving it.
    
    Returns:
        True if context exists and is not expired
    """
    return get_context() is not None

if __name__ == "__main__":
    # Test context manager
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("CONTEXT MANAGER TEST")
    print("="*60 + "\n")
    
    # Test 1: Set context
    print("1. Setting context...")
    set_active_email({
        'id': 'email_123',
        'message_id': '<msg123@gmail.com>',
        'thread_id': 'thread_456',
        'sender': 'boss@company.com',
        'subject': 'Urgent: Project Update'
    })
    
    # Test 2: Get context
    print("\n2. Getting context...")
    ctx = get_context()
    if ctx:
        print(f"   Sender: {ctx['sender']}")
        print(f"   Subject: {ctx['subject']}")
        print(f"   Age: {get_context_age_minutes():.2f} min")
    
    # Test 3: Check validity
    print(f"\n3. Is valid: {is_context_valid()}")
    
    # Test 4: Clear context
    print("\n4. Clearing context...")
    clear_context()
    
    # Test 5: Get after clear
    print("\n5. Getting after clear...")
    ctx = get_context()
    print(f"   Result: {ctx}")
    
    print("\n" + "="*60)
