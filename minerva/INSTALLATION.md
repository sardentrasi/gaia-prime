# Minerva Installation Guide

Minerva is the quantitative market analysis module. This guide covers the setup for its core logic.

---

## 📋 Prerequisites

- **Python 3.10+**

---

## ⚙️ Setup Instructions

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Telegram Userbot Setup

Minerva requires a Telegram Userbot to "spy" on market signal bots.

1. Obtain `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org).
2. Create `minerva/.env` and add:
   ```bash
   TG_API_ID=your_api_id
   TG_API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   LLM_API_KEY=your_key
   ```

---

## 🚀 Running Minerva

Run from the parent directory:

```bash
python -m minerva.minerva_main
```

---

## 🩺 Verification

- Check `minerva.log` for `[GENESIS]` logs.
- Verify the Userbot is capturing signals by checking the console output.
