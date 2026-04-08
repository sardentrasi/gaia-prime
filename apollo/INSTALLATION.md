# Apollo Installation Guide

Apollo is the global intelligence and news aggregation module of the Gaia Prime ecosystem. This guide provides instructions for both integrated and standalone setup.

---

## 📋 Prerequisites

- **Python 3.10+**
- **Virtual Environment** (Recommended)

---

## ⚙️ Setup Instructions

### 1. Install Dependencies

Navigate to the `apollo` directory and install the required packages:

```bash
pip install -r requirements.txt
```

### 2. Configuration (`.env`)

Create a `.env` file in the `apollo/` directory:

```bash
BOT_TOKEN=your_telegram_bot_token
USERS_ALLOWED=123456,789012
TIMEZONE=Asia/Jakarta
LLM_API_KEY=your_key_here
LLM_MODEL=openrouter/google/gemini-2.0-flash-001
```

### 3. Source Management

Add your preferred RSS or news feed URLs to `sources.txt` (one URL per line).

---

## 🚀 Running Apollo

### As part of Gaia Prime:

Ensure the central core is running (`mother_gaia.py`). Apollo will automatically sync memories.

### As a Standalone Module:

Run from the parent directory to maintain package context:

```bash
python -m apollo.apollo_main
```

---

## 🩺 Verification

- Check `apollo.log` for initialization logs.
- Use the `/status` command in Telegram to verify connectivity.
