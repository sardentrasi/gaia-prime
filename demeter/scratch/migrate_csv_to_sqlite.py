import sys
import os
import csv
import sqlite3

# Add current dir to path to import core
sys.path.append(os.getcwd())

from core.state import DB_FILE, DB_PATH
from core.database import init_db, get_db_connection

def migrate():
    print(f"🚀 Starting migration from {DB_FILE} to {DB_PATH}...")
    
    if not os.path.exists(DB_FILE):
        print(f"⚠️ CSV file {DB_FILE} not found. Nothing to migrate.")
        return

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    with open(DB_FILE, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
            print(f"📊 CSV Header detected: {header}")
        except StopIteration:
            print("⚠️ CSV is empty.")
            return
        
        count = 0
        for row in reader:
            if not row or len(row) < 2: continue
            
            try:
                # Flexible parsing
                timestamp = row[0]
                moisture = float(row[1]) if len(row) > 1 and row[1] else 0
                temp = float(row[2]) if len(row) > 2 and row[2] else 0
                
                # Action is usually at index 3
                action = row[3] if len(row) > 3 else "UNKNOWN"
                
                # img_path is at index 4
                img_path = row[4] if len(row) > 4 else ""
                
                # humidity is at index 5 (if exists)
                humidity = float(row[5]) if len(row) > 5 and row[5] else 0
                
                cursor.execute('''
                    INSERT INTO sensor_logs (timestamp, moisture, temp, humidity, action, img_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (timestamp, moisture, temp, humidity, action, img_path))
                count += 1
            except Exception as e:
                print(f"❌ Failed to parse row {row}: {e}")
            
    conn.commit()
    conn.close()
    print(f"✅ Migration finished! {count} records inserted into SQLite.")

if __name__ == "__main__":
    migrate()
