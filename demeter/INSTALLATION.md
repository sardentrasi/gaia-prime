# Demeter Installation Guide

Demeter is the AI Agronomist and IoT Garden Guardian. This guide explains how to set up the vision system and sensor API.

---

## 📋 Prerequisites

- **Python 3.10+**
- **FFmpeg** (Required for capturing snapshots from RTSP streams)

---

## ⚙️ Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Peripheral Configuration (`.env`)

Create `demeter/.env`:

```bash
RTSP_URL=rtsp://user:pass@your_camera_ip:port/stream
MOISTURE_SAFETY_LIMIT=20
BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_id
LLM_API_KEY=your_key
```

### 3. Hardware Integration (ESP32)

Ensure your IoT hardware is programmed to send POST requests to:
`http://[YOUR_SERVER_IP]:5000/siram`
Data fields: `moisture`, `temp`.

---

## 🚀 Running Demeter

Run from the parent directory:

```bash
python -m demeter.demeter_main
```

---

## 🩺 Verification

- Monitor `demeter.log` for sensor heartbeats.
- Use `/cek` in Telegram to verify snapshot capture from the RTSP stream.
