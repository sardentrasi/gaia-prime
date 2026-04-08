# Demeter - AI Agronomist Module

**D.E.M.E.T.E.R.** - Digitally Enhanced Mobile Environment & Terminal for Ecological Resources

Demeter is "The Hand" of the Gaia Prime ecosystem, providing intelligent agronomy and physical intervention for garden management.

---

## 🌱 Core Features

### 📸 Visual Agronomy

- **Computer Vision Analysis**: Uses LLM-Vision to analyze plant health, soil condition, and leaf status from camera snapshots.
- **Comparative Context**: Leverages historical captures to detect growth trends or pest infestations over time.

### 🔌 IoT Sensor Integration

- **Flask API**: High-frequency telemetry ingestion (Port 5000) for moisture and temperature sensors (e.g., ESP32).
- **Moisture Safety Limits**: Intelligent thresholding to prevent sensor-fault flooding or over-watering.
- **Automated Irrigation**: Self-healing protocol that triggers watering based on combined sensor + visual validation.

### 🧠 Advanced Memory (Dual-Tier)

- **Decentralized Short-Term State**: Uses `demeter_state.json` to log autonomous watering actions and manual checks for real-time situational awareness.
- **Anti-Spam RAG Filter**: Hourly telemetry heartbeats are aggressively filtered out of the ChromaDB semantic core to preserve pure AI analytical reasoning.
- **Heuristic Ranking 2.0**: Specialized boosts for garden data (`garden`, `tanaman`, `moisture`).
- **Data Logging**: Persistent CSV records of all sensor heartbeats.

---

## 📁 Project Structure

```
/demeter/
├── demeter_main.py            # Bot & Flask Orchestrator
├── demeter_memory_manager.py  # Ranking 2.0 Memory Controller
├── persona_demeter.md         # Unified Markdown Persona
├── garden_history.csv         # Sensor & Action Logs
├── data_logs/                 # Archive for long-term telemetry
└── vision_capture/            # Historical plant snapshots
```

---

## ⚙️ Installation & Setup

### 1. Requirements

- Python 3.10+
- FFmpeg (for RTSP snapshot capture)
- Dependencies: `pip install -r requirements.txt`

### 2. Configuration (`.env`)

Create an `.env` file in the `demeter/` directory:

```bash
BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_id
LLM_API_KEY=your_key
RTSP_URL=rtsp://user:pass@ip:port/stream
MOISTURE_SAFETY_LIMIT=20
```

### 3. ESP32 Integration

Point your hardware to `http://[INSTANCE_IP]:5000/siram` to report telemetry and receive irrigation instructions.

### 4. Running Demeter

Run from the Gaia Prime root:

```bash
python -m demeter.demeter_main
```

---

## 📱 Telegram Commands

| Command                  | Description                             |
| ------------------------ | --------------------------------------- |
| **Monitoring Dashboard** |                                         |
| `/status`                | View latest sensor telemetry & AI state |
| `/ping`                  | Check Demeter server latency            |
| **System Controls**      |                                         |
| `/start`                 | Register user for system notifications  |
| `/help`                  | Show the command center menu            |
| `/chat [query]`          | Natural language garden consultation    |

---

## 💾 Standalone Operation

Demeter is fully decentralized. She can operate as a "Garden Guardian" in **STANDALONE (Survival)** mode, managing irrigation and visual logs without external connectivity. See [README_STANDALONE.md](README_STANDALONE.md).

---

_Status: 🌿 System Healthy_
