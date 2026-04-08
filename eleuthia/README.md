# Eleuthia - Personal Assistant Module

**E.L.E.U.T.H.I.A.** - Enhanced Life & Executive Utility Through Hyper-Intelligent Automation

A sophisticated personal assistant module for the GAIA PRIME ecosystem, providing intelligent email management, calendar integration, and smart notifications via Telegram.

---

## 🚀 Features

### 📧 Email Intelligence

- **Multi-source support**: Gmail API, Outlook Graph API, IMAP fallback
- **LLM-powered classification**: Automatic categorization (urgent/info/spam)
- **Smart summarization**: 1-sentence summaries with reply suggestions
- **Outbound Execution**: Native `/compose` and `/reply` capabilities with conversational AI drafting
- **Meeting extraction**: Automatic detection of meeting requests
- **Memory-efficient**: Only stores important emails (urgent/info), ignores spam

### 🧠 Advanced Memory System (Heuristic Ranking 2.0)

- **Decentralized Short-Term State**: Uses `eleuthia_state.json` to log outbound actions (sent drafts, replies) for real-time Gaia awareness without ChromaDB overhead.
- **ChromaDB vector store**: Decentralized, persistent semantic memory
- **Heuristic Ranking 2.0**: Advanced scoring (Similarity + Category Boost + Recency + Timeless Knowledge)
- **Gaia Brain Sync**: Dual-tier architecture (Local Survival + Central Mirroring)
- **LRU caching**: Fast retrieval with 5-minute TTL
- **Analytics tracking**: Real-time performance metrics

### 🤖 Telegram Bot

- **Command-based interface**: 7 core commands
- **Morning briefing**: Automated daily summary (7 AM)
- **Real-time monitoring**: Email checks every 5 minutes
- **Quiet hours**: Auto-disable notifications (22:00-06:00)
- **Smart notifications**: Only urgent emails trigger alerts

---

## 📁 Project Structure

```
/eleuthia/
├── __init__.py                    # Module exports
├── .env                           # Configuration (gitignored)
├── .env.template                  # Configuration template
├── config.py                      # Config loader
├── eleuthia_config.json           # Behavior settings
├── connector_email.py             # Email fetching (Gmail/Outlook/IMAP)
├── eleuthia_memory_manager.py     # LLM intelligence + Ranking 2.0 logic
├── eleuthia_main.py               # Telegram bot orchestrator
├── persona_eleuthia.md            # [NEW] Unified Markdown Persona
├── help_interface.txt             # Help menu
├── requirements.txt               # Dependencies
└── eleuthia_memory_core/          # ChromaDB storage (auto-created)
```

---

## ⚙️ Setup

### 1. Install Dependencies

```bash
cd eleuthia
pip install -r requirements.txt
```

### 2. Configure Environment

Copy template and fill credentials:

```bash
cp .env.template .env
```

Edit `.env`:

- Add Gmail/Outlook/IMAP credentials
- Telegram bot token (pre-filled from parent)
- LLM API key (pre-filled from parent)

### 3. Setup Gmail API (Recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail API
3. Create OAuth 2.0 credentials
4. Download `credentials.json` → `eleuthia/credentials/gmail_credentials.json`

### 4. Customize Settings

Edit `eleuthia_config.json`:

- Briefing time
- Keywords (urgent/spam/info)
- Quiet hours
- Notification preferences

### 5. Run Eleuthia

```bash
python eleuthia_main.py
```

---

## 📱 Telegram Commands

| Command              | Description                        |
| -------------------- | ---------------------------------- |
| **Email Management** |                                    |
| `/check_email`       | Force email check and summary      |
| `/urgent`            | Show urgent emails only            |
| `/briefing`          | Manual morning briefing            |
| **Account Control**  |                                    |
| `/accounts`          | List connected accounts            |
| `/enable [name]`     | Enable an account                  |
| `/disable [name]`    | Disable an account temporarily     |
| **System Settings**  |                                    |
| `/config`            | View current settings              |
| `/status`            | System health and memory check     |
| `/about`             | About Eleuthia                     |
| **Chat & Outbound**  |                                    |
| `/chat`              | Casual chat with Eleuthia          |
| `/compose`           | Draft and send an email            |
| `/reply`             | Reply to a specific email          |
| **Help**             |                                    |
| `/help`              | Show command menu                  |

---

## 🧪 Testing

### Test Configuration

```bash
python config.py
```

### Test Email Connector

```bash
python connector_email.py
```

### Test Memory Manager

```bash
python eleuthia_memory_manager.py
```

### Test Bot

```bash
python eleuthia_main.py
```

Then in Telegram: `/start` → `/help` → `/status`

---

## 🔧 Configuration Files

### `.env` - Credentials

- Email API credentials
- Telegram bot token
- LLM API keys
- Embedding settings

### `eleuthia_config.json` - Behavior

- Scheduling (briefing time, intervals)
- Classification keywords
- Notification settings
- Quiet hours

---

## 💾 Memory Architecture

```
┌─────────────────────────────────────┐
│         ELEUTHIA MEMORY 2.0         │
├─────────────────────────────────────┤
│                                     │
│  ┌──────────────┐  ┌─────────────┐  │
│  │ Gaia Brain   │  │ Local Core  │  │
│  │ (Central)    │  │ (Survival)  │  │
│  └──────────────┘  └─────────────┘  │
│         │                 │         │
│         └────────┬────────┘         │
│                  │                  │
│         ┌────────▼────────┐         │
│         │  Ranking 2.0    │         │
│         │  (Heuristics)   │         │
│         └─────────────────┘         │
└─────────────────────────────────────┘
```

**Storage Policy:**

- ✅ **Urgent**: Vector store + Gaia + Summary
- ✅ **Info**: Vector store + Gaia
- 🗑️ **Spam**: Ignored (not stored)

---

## 📊 Analytics

Track performance with `brain.get_analytics()`:

- Total emails processed
- Classification breakdown
- Cache hit rate
- Average retrieval time
- Uptime hours

---

## 🔐 Security

- OAuth2 tokens stored locally (gitignored)
- IMAP passwords via environment variables
- Email content encrypted in vector store
- No sensitive data in logs

---

## 🚧 Roadmap

### Phase 1: Core Features ✅

- [x] Email connector (Gmail/Outlook/IMAP)
- [x] LLM classification & summarization
- [x] Telegram bot with commands
- [x] Background jobs (briefing, monitoring)
- [x] Vector store memory system

### Phase 2: Calendar Integration 🔄

- [ ] Google Calendar API
- [ ] Outlook Calendar API
- [ ] Meeting conflict detection
- [ ] Calendar in briefing

### Phase 3: Advanced Features 📋

- [ ] `/reply_N` command for quick replies
- [ ] Email search by sender/keyword
- [ ] Custom filters per user
- [ ] Multi-language support

---

## 🐛 Troubleshooting

### Gmail API Error

```
Error: credentials not found
```

**Solution:** Download OAuth credentials from Google Cloud Console

### LLM Classification Failed

```
LLM classification failed: API key invalid
```

**Solution:** Check `LLM_API_KEY` in `.env`

### Telegram Bot Not Responding

```
Telegram error: Unauthorized
```

**Solution:** Verify `TELEGRAM_BOT_TOKEN` in `.env`

---

## 📄 License

Part of GAIA PRIME ecosystem

---

## 🤝 Contributing

This is a personal assistant module. For issues or suggestions, contact the GAIA PRIME team.

---

**Status**: ✅ Production Ready  
**Version**: 1.1.0 (Rank 2.0 Upgrade)  
**Last Updated**: 2026-02-18
