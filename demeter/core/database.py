import sqlite3
import os
from core.state import DB_PATH, logger

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create table for sensor logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                moisture REAL,
                temp REAL,
                humidity REAL,
                co2 REAL,
                action TEXT,
                img_path TEXT
            )
        ''')
        
        # Add CO2 column if it doesn't exist (for migration of existing SQLite DB)
        try:
            cursor.execute('ALTER TABLE sensor_logs ADD COLUMN co2 REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass # Column likely already exists

        # Create notifications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0
            )
        ''')

        # Create growth logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS growth_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                plant_name TEXT NOT NULL,
                height REAL,
                health TEXT,
                notes TEXT,
                img_path TEXT
            )
        ''')

        # Create chat history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL,
                message TEXT NOT NULL
            )
        ''')

        # Indexing for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_logs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(is_read)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_ts ON chat_history(timestamp)')
        
        conn.commit()
        conn.close()
        logger.info(f"🗄️ Database initialized at {DB_PATH}")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

def insert_sensor_data(moisture, temp, humidity, co2, action, img_path):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sensor_logs (moisture, temp, humidity, co2, action, img_path)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (moisture, temp, humidity, co2, action, img_path))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Failed to insert sensor data: {e}")

def get_latest_history(limit=20):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, moisture, temp, humidity, co2, action, img_path 
            FROM sensor_logs 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ Failed to fetch history: {e}")
        return []

# ============================================
# CLIMATIC DATA QUERIES
# ============================================

SENSOR_COLUMN_MAP = {
    'temperature': 'temp',
    'humidity': 'humidity',
    'moisture': 'moisture',
    'co2': 'co2'
}

def get_sensor_timeseries(sensor_type, hours=24):
    """Return time-series data for a specific sensor type."""
    col = SENSOR_COLUMN_MAP.get(sensor_type)
    if not col:
        return []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT timestamp, {col} as value
            FROM sensor_logs
            WHERE timestamp >= datetime('now', '-{int(hours)} hours')
            ORDER BY timestamp ASC
        ''')
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            ts = row['timestamp']
            # Format timestamp for chart labels
            if ts and ' ' in ts:
                time_part = ts.split(' ')[1][:5]
            else:
                time_part = ts or ''
            result.append({'time': time_part, 'value': round(row['value'] or 0, 1)})
        return result
    except Exception as e:
        logger.error(f"❌ Timeseries query error: {e}")
        return []

def get_sensor_stats(sensor_type, hours=24):
    """Return min, max, avg, current for a specific sensor type."""
    col = SENSOR_COLUMN_MAP.get(sensor_type)
    if not col:
        return {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT 
                MIN({col}) as min_val,
                MAX({col}) as max_val,
                ROUND(AVG({col}), 1) as avg_val
            FROM sensor_logs
            WHERE timestamp >= datetime('now', '-{int(hours)} hours')
        ''')
        stats = dict(cursor.fetchone())
        
        # Get current (latest) value
        cursor.execute(f'''
            SELECT {col} as current_val
            FROM sensor_logs
            ORDER BY timestamp DESC
            LIMIT 1
        ''')
        current_row = cursor.fetchone()
        conn.close()
        
        return {
            'min': round(stats['min_val'] or 0, 1),
            'max': round(stats['max_val'] or 0, 1),
            'avg': round(stats['avg_val'] or 0, 1),
            'current': round(current_row['current_val'] or 0, 1) if current_row else 0
        }
    except Exception as e:
        logger.error(f"❌ Sensor stats query error: {e}")
        return {'min': 0, 'max': 0, 'avg': 0, 'current': 0}

# ============================================
# REPORTS QUERIES
# ============================================

def get_daily_reports(days=30):
    """Aggregate sensor data by day for reports."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as total_readings,
                SUM(CASE WHEN action = 'SIRAM' THEN 1 ELSE 0 END) as irrigations,
                ROUND(AVG(moisture), 1) as avg_moisture,
                ROUND(AVG(temp), 1) as avg_temp,
                ROUND(AVG(humidity), 1) as avg_humidity,
                ROUND(AVG(co2), 0) as avg_co2
            FROM sensor_logs
            WHERE timestamp >= datetime('now', '-{int(days)} days')
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ Daily reports query error: {e}")
        return []

# ============================================
# NOTIFICATIONS
# ============================================

def insert_notification(notif_type, message):
    """Insert a new notification."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notifications (type, message)
            VALUES (?, ?)
        ''', (notif_type, message))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Failed to insert notification: {e}")

def get_unread_notifications(limit=20):
    """Get unread notifications."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, timestamp, type, message
            FROM notifications
            WHERE is_read = 0
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ Failed to fetch notifications: {e}")
        return []

def mark_notifications_read():
    """Mark all notifications as read."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE notifications SET is_read = 1 WHERE is_read = 0')
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Failed to mark notifications read: {e}")

# ============================================
# GROWTH LOGS
# ============================================

def insert_growth_log(plant_name, height, health, notes, img_path=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO growth_logs (plant_name, height, health, notes, img_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (plant_name, height, health, notes, img_path))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Failed to insert growth log: {e}")

def get_growth_logs(limit=50):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, timestamp, plant_name, height, health, notes, img_path
            FROM growth_logs
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ Failed to fetch growth logs: {e}")
        return []

# ============================================
# CHAT HISTORY
# ============================================

def insert_chat_message(role, message):
    """Insert a new chat message (user or ai)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chat_history (role, message)
            VALUES (?, ?)
        ''', (role, message))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Failed to insert chat message: {e}")

def get_chat_history(limit=50):
    """Get chat history sorted by time."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, message, timestamp
            FROM chat_history
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ Failed to fetch chat history: {e}")
        return []
