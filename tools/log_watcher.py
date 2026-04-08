import time
import os
import sys
import re
from datetime import datetime

# Add root to pass for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gaia_memory_manager import GaiaBrain

# CONFIGURATION
LOG_FILE = "gaia_prime.log"
POLL_INTERVAL = 0.5

# FILTER RULES
# Ignore if line contains ANY of these:
IGNORE_TOKENS = ["Checking", "Looping", "Wait", "Sleep", "Connecting", "polling", "Heartbeat"]

# Capture if line contains ANY of these:
CAPTURE_TOKENS = [
    "[ERROR]", 
    "[WARNING]", 
    "[CRITICAL]", 
    "[LAZARUS]", 
    "[TRACEBACK]",
    "Panen Selesai", 
    "Application started",
    "System Online"
]

def main():
    print(f"👁️ LogWatcher Active. Monitoring: {LOG_FILE}")
    
    # Initialize Brain
    try:
        brain = GaiaBrain()
        if not brain.collection:
            print("⚠️ Memory Core not ready. Waiting...")
    except Exception as e:
        print(f"❌ Brain Init Failed: {e}")
        return

    # Open the file
    target_path = os.path.abspath(os.path.join(os.getcwd(), LOG_FILE))
    
    # Wait for file to exist
    while not os.path.exists(target_path):
        print(f"⏳ Waiting for {LOG_FILE} to appear...")
        time.sleep(2)

    # Open and Tail
    with open(target_path, "r", encoding="utf-8") as f:
        # Move to end of file to start monitoring NEW events
        f.seek(0, os.SEEK_END)
        
        while True:
            line = f.readline()
            if not line:
                time.sleep(POLL_INTERVAL)
                continue
                
            line = line.strip()
            if not line:
                continue

            # 1. CHECK IGNORE LIST
            if any(token in line for token in IGNORE_TOKENS):
                continue
                
            # 2. CHECK CAPTURE LIST
            is_important = any(token in line for token in CAPTURE_TOKENS)
            
            if is_important:
                try:
                    # Clean Timestamp if possible (optional)
                    # Just record raw line for context
                    
                    # Record to Memory (DISABLED: To prevent memory core clutter)
                    # brain.record(
                    #     text=line,
                    #     user_name="SYSTEM_LOG",
                    #     tags="system_log, health_monitor"
                    # )
                    print(f"[LOG_WATCH] 👁️ Captured: {line[:50]}...")
                    
                except Exception as e:
                    print(f"❌ Failed to record log: {e}")

if __name__ == "__main__":
    main()
