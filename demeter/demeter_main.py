import os
import time
import asyncio
import threading
import glob
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from functools import wraps
from dotenv import load_dotenv

import core.state
from core.state import (
    logger, MOISTURE_SAFETY_LIMIT, HARD_COOLDOWN_HOURS, SOFT_COOLDOWN_HOURS, CAPTURE_DIR, DB_FILE,
    LLM_BASE_MODEL, DB_PATH
)
from core.utils import update_short_memory, start_midnight_cleanup_scheduler, log_data
from core.vision import capture_visual, get_previous_image
from core.ai_consultant import consult_demeter
from core.telegram_bot import run_telegram_bot, kirim_telegram_sync
from core.database import (
    init_db, get_latest_history, get_sensor_timeseries, get_sensor_stats,
    get_daily_reports, insert_notification, get_unread_notifications, mark_notifications_read,
    insert_growth_log, get_growth_logs, insert_chat_message, get_chat_history
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "demeter-secret-key-123")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- IOT ENDPOINT ---
@app.route('/lapor', methods=['POST'])
def handle_report():
    try:
        data = request.json
        moist = data.get("moisture", 0)
        temp = data.get("temp", 0)
        humidity = data.get("humidity", 0)
        co2 = data.get("co2", 0)
        
        current_time = datetime.now()
        
        logger.info(f"📥 [ESP32] Laporan: Moisture={moist}%, Temp={temp}°C, Hum={humidity}%, CO2={co2}ppm")
        
        # Priority 1: User Request
        if core.state.COMMAND_QUEUE:
            logger.info("⚡ [OVERRIDE] Telegram Command detected in queue!")
            cmd = core.state.COMMAND_QUEUE
            core.state.COMMAND_QUEUE = None
            
            try:
                with core.state.AI_PROCESSING_LOCK:
                    img_path = capture_visual()
                    prev_img = get_previous_image(img_path) if img_path else None
                    
                    ai_result = consult_demeter(moist, temp, img_path, prev_img)
                    action = ai_result.get('action', 'DIAM')
                    duration = ai_result.get('duration_sec', 0)
                    
                    if action == "SIRAM":
                        core.state.NEXT_ANALYSIS_TIME = current_time + timedelta(hours=HARD_COOLDOWN_HOURS)
                        status_msg = f"User Request: Watering (+{HARD_COOLDOWN_HOURS}h)"
                    else:
                        core.state.NEXT_ANALYSIS_TIME = current_time + timedelta(hours=SOFT_COOLDOWN_HOURS)
                        status_msg = f"User Request: Analyzed (+{SOFT_COOLDOWN_HOURS}h)"
                        
                    log_data(moist, temp, action, img_path, humidity, co2)
                    
                    core.state.LATEST_DATA = {
                        "moisture": moist, "temp": temp, "last_seen": current_time,
                        "action": action, "status": status_msg
                    }
                    
                    # --- AUTOMATED GROWTH LOGGING ---
                    health = ai_result.get('health_score', 'Good')
                    height = ai_result.get('estimated_height_cm', 0)
                    reasoning = ai_result.get("reason", "Manual Override Evaluated")
                    insert_growth_log(
                        plant_name=core.state.PLANT_NAME, 
                        height=height, 
                        health=health, 
                        notes=f"[AUTO-LOG via /status] {reasoning}",
                        img_path=img_path
                    )
                    
                    pesan = f"🟢 **Laporan Analisa Manual**\n💦 Tanah: {moist}%\n🌡️ Suhu: {temp}°C\n🤖 Keputusan AI: **{action}**\n\n*Catatan*: {reasoning}"
                    kirim_telegram_sync(pesan, img_path)
                    
                    return jsonify({"action": action, "duration_sec": duration})
                    
            except TimeoutError:
                logger.warning("[BUSY] Server memproses perintah. Mengabaikan perintah baru.")
                core.state.LATEST_DATA = {
                    "moisture": moist, "temp": temp, "last_seen": current_time,
                    "action": "DIAM", "status": "Server Busy"
                }
                kirim_telegram_sync("⚠️ Demeter sedang sibuk memproses analisa lain. Harap tunggu.")
                return jsonify({"action": "DIAM", "duration_sec": 0})
        
        # Priority 2: Cooldown check
        if current_time < core.state.NEXT_ANALYSIS_TIME:
            time_left = core.state.NEXT_ANALYSIS_TIME - current_time
            minutes_left = int(time_left.total_seconds() / 60)
            status_msg = f"Cooldown (Wait {minutes_left}m)"
            
            core.state.LATEST_DATA = {
                "moisture": moist, "temp": temp, "last_seen": current_time,
                "action": "DIAM", "status": status_msg
            }
            return jsonify({"action": "DIAM", "duration_sec": 0})

        # Priority 3: Determine task
        task_type = None
        
        if moist < MOISTURE_SAFETY_LIMIT:
            task_type = 'AUTO'
        elif (current_time - core.state.LAST_LOG_TIME).total_seconds() > 3600:
            task_type = 'HEARTBEAT'

        # Execute task
        if task_type:
            try:
                with core.state.AI_PROCESSING_LOCK:
                    if task_type == 'HEARTBEAT':
                        logger.info("[HEARTBEAT] Memulai log rutin...")
                        core.state.LAST_LOG_TIME = current_time
                        status_msg = "Hourly Log"
                    
                    elif task_type == 'AUTO':
                        logger.info(f"[AUTO] Sensor ({moist}%) -> Memulai Analisa...")
                        status_msg = "AI Analyzing..."

                    img_path = capture_visual()
                    save_to_disk = False
                    action = "DIAM"
                    duration = 0

                    if task_type == 'AUTO':
                        prev_img = get_previous_image(img_path) if img_path else None
                        ai_result = consult_demeter(moist, temp, img_path, prev_img)
                        action = ai_result.get('action', 'DIAM')
                        duration = ai_result.get('duration_sec', 0)
                        
                        logger.info(f"[AI DECISION] Gemini: {action}")
                        
                        if action == "SIRAM":
                            core.state.NEXT_ANALYSIS_TIME = current_time + timedelta(hours=HARD_COOLDOWN_HOURS)
                            status_msg = f"AI: Watering (Next: +{HARD_COOLDOWN_HOURS}h)"
                            save_to_disk = True
                        else:
                            core.state.NEXT_ANALYSIS_TIME = current_time + timedelta(hours=SOFT_COOLDOWN_HOURS)
                            status_msg = f"AI: Skipped (Next: +{SOFT_COOLDOWN_HOURS}h)"
                            save_to_disk = True
                    
                    elif task_type == 'HEARTBEAT':
                        save_to_disk = True

                    if save_to_disk:
                        log_data(moist, temp, action, img_path, humidity, co2)
                        
                        if task_type == 'AUTO':
                            reason = ai_result.get('reason', 'Routine check')
                            clean_reason = ' '.join(reason.replace('\n', ' ').replace('*', '').replace('`', '').replace('_', ' ').split())
                            reason_snip = clean_reason[:4000] + '...' if len(clean_reason) > 4000 else clean_reason
                            update_short_memory(f"Autonomous Action ({task_type})", f"Dec: {action} (M:{moist}%, T:{temp}C) | AI: {reason_snip}")

                            # --- AUTOMATED GROWTH LOGGING ---
                            health = ai_result.get('health_score', 'Good')
                            height = ai_result.get('estimated_height_cm', 0)
                            insert_growth_log(
                                plant_name=core.state.PLANT_NAME, 
                                height=height, 
                                health=health, 
                                notes=f"[AUTO-LOG via Analysis] {clean_reason}",
                                img_path=img_path
                            )
                        
                        if action == "SIRAM":
                            pesan = f"💦 **DEMETER ACTIVE** ({status_msg})\n🌱 Tanah: {moist}%\n🌡️ Suhu: {temp}°C"
                            insert_notification('irrigation', f'Irrigation activated. Soil: {moist}%, Temp: {temp}°C')
                            try:
                                kirim_telegram_sync(pesan, img_path)
                            except Exception as tg_err:
                                logger.error(f"[ERROR] Telegram fail: {tg_err}")

            except TimeoutError:
                logger.info(f"[BUSY] Server sibuk memproses {task_type}. Skip.")
                status_msg = "Server Busy (Timeout)"
                action = "DIAM"

            except Exception as e:
                logger.error(f"[PROCESS ERROR] {e}")
                core.state.NEXT_ANALYSIS_TIME = current_time + timedelta(hours=SOFT_COOLDOWN_HOURS)
                status_msg = "Error Cooldown"
                update_short_memory("System Error", str(e))

            core.state.LATEST_DATA = {
                "moisture": moist, "temp": temp, "humidity": humidity, "co2": co2, "last_seen": current_time,
                "action": action, "status": status_msg
            }

            return jsonify({"action": action, "duration_sec": duration})

        status_msg = "Sistem Sehat"
        core.state.LATEST_DATA = {
            "moisture": moist, "temp": temp, "humidity": humidity, "co2": co2, "last_seen": current_time,
            "action": "DIAM", "status": status_msg
        }

        return jsonify({"action": "DIAM", "duration_sec": 0})

    except Exception as e:
        logger.error(f"[CRITICAL ERROR] {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"action": "DIAM", "duration_sec": 0}), 500

# --- WEB DASHBOARD ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        correct_username = os.getenv('DASHBOARD_USERNAME', 'admin')
        correct_password = os.getenv('DASHBOARD_PASSWORD', 'admin123')
        if username == correct_username and password == correct_password:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = "Invalid username or password."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', active_page='dashboard')

@app.route('/api/status')
@login_required
def api_status():
    latest_img = None
    list_files = sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.jpg")))
    if list_files:
        latest_img = os.path.basename(list_files[-1])
    
    next_analysis = None
    if isinstance(core.state.NEXT_ANALYSIS_TIME, datetime):
        next_analysis = core.state.NEXT_ANALYSIS_TIME.isoformat()
        
    return jsonify({
        "moisture": core.state.LATEST_DATA.get("moisture", 0),
        "temp": core.state.LATEST_DATA.get("temp", 0),
        "humidity": core.state.LATEST_DATA.get("humidity", 0),
        "co2": core.state.LATEST_DATA.get("co2", 0),
        "last_seen": core.state.LATEST_DATA.get("last_seen").isoformat() if isinstance(core.state.LATEST_DATA.get("last_seen"), datetime) else None,
        "action": core.state.LATEST_DATA.get("action", "WAITING"),
        "status": core.state.LATEST_DATA.get("status", "BOOT"),
        "latest_image": latest_img,
        "command_queue": bool(core.state.COMMAND_QUEUE),
        "next_analysis": next_analysis
    })

@app.route('/api/history')
@login_required
def api_history():
    history = get_latest_history(limit=20)
    return jsonify(history)

@app.route('/vision_capture/<path:filename>')
@login_required
def serve_capture(filename):
    return send_from_directory(CAPTURE_DIR, filename)

# --- GROWTH LOGS ---
@app.route('/growth-log')
@login_required
def growth_log_page():
    return render_template('growth_log.html', active_page='growth_log')

@app.route('/api/growth-logs', methods=['GET'])
@login_required
def api_get_growth_logs():
    logs = get_growth_logs(limit=50)
    return jsonify(logs)

@app.route('/api/growth-logs', methods=['POST'])
@login_required
def api_post_growth_log():
    try:
        data = request.json
        plant_name = data.get('plant_name')
        height = data.get('height', 0)
        health = data.get('health', 'Good')
        notes = data.get('notes', '')
        
        if not plant_name:
            return jsonify({'success': False, 'message': 'Plant name is required'}), 400
            
        insert_growth_log(plant_name, height, health, notes)
        insert_notification('growth', f'New growth log for {plant_name}: {height}cm, {health}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/insights/latest', methods=['GET'])
@login_required
def api_latest_insight():
    logs = get_growth_logs(limit=1)
    if not logs:
        return jsonify({
            'title': 'No insight yet',
            'notes': 'Belum ada hasil analisa AI yang tersimpan. Jalankan scan untuk menghasilkan insight terbaru.',
            'timestamp': None,
            'plant_name': None,
            'health': None,
            'height': None,
            'image_url': None,
            'link': '/growth-log'
        })

    latest = logs[0]
    raw_notes = (latest.get('notes') or '').strip()
    clean_notes = raw_notes
    for prefix in ('[AUTO-LOG via Analysis] ', '[AUTO-LOG via /status] '):
        if clean_notes.startswith(prefix):
            clean_notes = clean_notes[len(prefix):]

    health = latest.get('health') or 'Unknown'
    plant_name = latest.get('plant_name') or 'Greenhouse System'
    timestamp = latest.get('timestamp')
    height = latest.get('height')
    title = f"{plant_name} - Health {health}"

    img_path = latest.get('img_path')
    image_url = None
    if img_path:
        image_name = os.path.basename(str(img_path))
        if image_name:
            image_url = url_for('serve_capture', filename=image_name)

    return jsonify({
        'title': title,
        'notes': clean_notes or 'Insight tersedia tetapi belum ada catatan detail.',
        'timestamp': timestamp,
        'plant_name': plant_name,
        'health': health,
        'height': height,
        'image_url': image_url,
        'link': '/growth-log'
    })


# --- CLIMATIC DATA ---
SENSOR_CONFIGS = {
    'temperature': {'title': 'Temperature', 'subtitle': 'Ambient Air Temperature Readings', 'unit': '°C', 'color': '#163300'},
    'humidity':    {'title': 'Air Humidity', 'subtitle': 'Relative Humidity Readings', 'unit': '%', 'color': '#054d28'},
    'moisture':    {'title': 'Soil Moisture', 'subtitle': 'Capacitive Sensor Readings', 'unit': '%', 'color': '#9fe870'},
    'co2':         {'title': 'CO₂ Level', 'subtitle': 'MQ-135 Gas Sensor Readings', 'unit': 'ppm', 'color': '#0e0f0c'},
}

@app.route('/climatic/<sensor_type>')
@login_required
def climatic_page(sensor_type):
    if sensor_type not in SENSOR_CONFIGS:
        return redirect(url_for('index'))
    return render_template('climatic.html',
        active_page=f'climatic_{sensor_type}',
        sensor_type=sensor_type,
        sensor_config=SENSOR_CONFIGS[sensor_type]
    )

@app.route('/api/climatic/<sensor_type>')
@login_required
def api_climatic(sensor_type):
    hours = request.args.get('hours', 24, type=int)
    timeseries = get_sensor_timeseries(sensor_type, hours)
    stats = get_sensor_stats(sensor_type, hours)
    return jsonify({'timeseries': timeseries, 'stats': stats})

# --- REPORTS ---
@app.route('/reports')
@login_required
def reports_page():
    return render_template('reports.html', active_page='reports')

@app.route('/api/reports')
@login_required
def api_reports():
    days = request.args.get('days', 30, type=int)
    reports = get_daily_reports(days)
    return jsonify(reports)

# --- CONTROLS ---
@app.route('/controls')
@login_required
def controls_page():
    return render_template('controls.html', active_page='controls')

@app.route('/api/controls/scan', methods=['POST'])
@login_required
def api_control_scan():
    if core.state.COMMAND_QUEUE:
        return jsonify({'success': False, 'message': 'A command is already queued. Wait for it to complete.'})
    core.state.COMMAND_QUEUE = {'action': 'ANALYZE', 'duration': 0, 'source': 'dashboard'}
    insert_notification('control', 'Manual scan triggered from dashboard')
    logger.info("[DASHBOARD] Force scan command queued.")
    return jsonify({'success': True, 'message': 'Scan command queued. Will execute on next ESP32 report.'})

@app.route('/api/controls/water', methods=['POST'])
@login_required
def api_control_water():
    if core.state.COMMAND_QUEUE:
        return jsonify({'success': False, 'message': 'A command is already queued. Wait for it to complete.'})
    core.state.COMMAND_QUEUE = {'action': 'ANALYZE', 'duration': 0, 'source': 'dashboard_water'}
    insert_notification('control', 'Manual irrigation triggered from dashboard')
    logger.info("[DASHBOARD] Force water command queued.")
    return jsonify({'success': True, 'message': 'Water command queued. Will execute on next ESP32 report.'})

@app.route('/api/controls/reset-cooldown', methods=['POST'])
@login_required
def api_control_reset_cooldown():
    core.state.NEXT_ANALYSIS_TIME = datetime.min
    insert_notification('control', 'Cooldown timer reset from dashboard')
    logger.info("[DASHBOARD] Cooldown timer reset.")
    return jsonify({'success': True, 'message': 'Cooldown timer reset. Next report will trigger analysis.'})

# --- SETTINGS ---
@app.route('/settings')
@login_required
def settings_page():
    return render_template('settings.html', active_page='settings')

@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def api_settings():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if 'moisture_safety_limit' in data:
                core.state.MOISTURE_SAFETY_LIMIT = float(data['moisture_safety_limit'])
            if 'hard_cooldown_hours' in data:
                core.state.HARD_COOLDOWN_HOURS = float(data['hard_cooldown_hours'])
            if 'soft_cooldown_hours' in data:
                core.state.SOFT_COOLDOWN_HOURS = float(data['soft_cooldown_hours'])
            if 'plant_name' in data:
                core.state.PLANT_NAME = str(data['plant_name'])
            
            logger.info(f"[SETTINGS] Updated: plant={core.state.PLANT_NAME}, moisture={core.state.MOISTURE_SAFETY_LIMIT}, hard_cd={core.state.HARD_COOLDOWN_HOURS}h")
            return jsonify({'success': True, 'message': 'Settings saved (runtime only).'})
        except Exception as e:
            logger.error(f"[SETTINGS ERROR] {e}")
            return jsonify({'success': False, 'message': str(e)}), 400
    
    return jsonify({
        'moisture_safety_limit': core.state.MOISTURE_SAFETY_LIMIT,
        'hard_cooldown_hours': core.state.HARD_COOLDOWN_HOURS,
        'soft_cooldown_hours': core.state.SOFT_COOLDOWN_HOURS,
        'plant_name': core.state.PLANT_NAME,
        'llm_model': core.state.LLM_BASE_MODEL,
        'db_path': core.state.DB_PATH,
        'capture_dir': core.state.CAPTURE_DIR
    })

# --- AI CHAT ---
@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """Chat with Demeter AI — same engine as Telegram /chat"""
    user_msg = request.json.get('message', '').strip()
    if not user_msg:
        return jsonify({'reply': 'Please enter a message.'})
    
    try:
        # Save user message to DB
        insert_chat_message('user', user_msg)
        
        # Load persona
        persona = "You are Demeter, the Garden AI."
        persona_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona_demeter.md")
        if os.path.exists(persona_path):
            with open(persona_path, "r", encoding="utf-8") as f:
                persona = f.read()
        persona = persona.replace("{sender}", "Dashboard Operator")
        
        # Record user message to memory
        if len(user_msg) > 5:
            core.state.global_brain.record(
                text=user_msg, user_name="Dashboard Operator",
                source="dashboard_chat", tags="demeter, dashboard_chat"
            )
        
        # Run async chat in sync context
        loop = asyncio.new_event_loop()
        reply = loop.run_until_complete(
            core.state.global_brain.chat_with_langchain(
                query=user_msg,
                system_persona=persona,
                user_name="Dashboard Operator",
                filter_type="demeter"
            )
        )
        loop.close()
        
        # Save AI reply to DB
        insert_chat_message('ai', reply)

        # Record AI reply to memory
        if len(reply) > 20:
            core.state.global_brain.record(
                text=f"DEMETER to Dashboard: {reply}",
                user_name="Demeter",
                source="demeter_chat",
                tags="ai_response_dashboard"
            )
        
        return jsonify({'reply': reply})
    except Exception as e:
        logger.error(f"[CHAT ERROR] {e}")
        return jsonify({'reply': f'⚠️ Communication error: {str(e)}'})

@app.route('/api/chat/history', methods=['GET'])
@login_required
def api_chat_history():
    history = get_chat_history(limit=50)
    return jsonify(history)

# --- NOTIFICATIONS ---
@app.route('/api/notifications')
@login_required
def api_notifications():
    notifs = get_unread_notifications()
    return jsonify(notifs)

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def api_mark_notifications_read():
    mark_notifications_read()
    return jsonify({'success': True})

def run_flask():
    logger.info("[SYSTEM] Starting Flask Server (Daemon)...")
    logger.info("💡 [PRODUCTION TIP] Untuk Ubuntu, jalankan: gunicorn -w 4 -b 0.0.0.0:5000 demeter_main:app")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    logger.info("--- DEMETER V6.2 (MODULAR) ONLINE ---")
    
    # Initialize Database
    init_db()
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    try:
        start_midnight_cleanup_scheduler()
        run_telegram_bot()
    except KeyboardInterrupt:
        logger.info("[SYSTEM] Shutting down...")
