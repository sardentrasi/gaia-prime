# Eleuthia Installation Guide

Eleuthia is the personal steward for email and briefing management. This guide covers API setup and configuration.

---

## 📋 Prerequisites

- **Python 3.10+**

---

## ⚙️ Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Email API Credentials

- **Gmail:** Place `gmail_credentials.json` in `eleuthia/credentials/`.
- **Outlook:** Configure `AZURE_CLIENT_ID` and `AZURE_TENANT_ID` in `.env`.

---

## 🚀 Running Eleuthia

Run from the parent directory:

```bash
python -m eleuthia.eleuthia_main
```

---

## 🩺 Verification

- Check `eleuthia.log` for email sync completion.
- Verify Telegram bot is responding to commands.
