import os
import json
import schedule
import threading
import time
from datetime import datetime
from core.state import logger
from core.database import insert_sensor_data

def update_short_memory(action: str, result: str) -> None:
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    module_name = os.path.basename(current_dir)
    state_file = os.path.join(current_dir, f"{module_name}_state.json")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_entry = {
        "timestamp": timestamp,
        "action": action,
        "result": result
    }
    
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
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
            time.sleep(60)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("🕒 Midnight Cleanup Scheduler initialized.")

def log_data(moist, temp, action, img_path, humidity=0, co2=0):
    # Log to SQLite (Source of Truth)
    from core.database import insert_sensor_data
    insert_sensor_data(moist, temp, humidity, co2, action, img_path)
    
    from core.state import DB_FILE
    try:
        current_time = datetime.now()
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        file_exists = os.path.isfile(DB_FILE)
        
        with open(DB_FILE, 'a') as f:
            if not file_exists:
                f.write("timestamp,moisture,temp,action,img_path,humidity,co2\n")
            f.write(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')},{moist},{temp},{action},{img_path},{humidity},{co2}\n")
    except Exception as e:
        logger.error(f"❌ Failed to log data to CSV: {e}", exc_info=True)
