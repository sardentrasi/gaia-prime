# Apollo - Global Intelligence Module

**A.P.O.L.L.O.** - Autonomous Processing & Omniscience Liaison for Local Operations

Apollo is "The Eye" of the Gaia Prime ecosystem. A sophisticated news aggregator and intelligence engine designed to provide external world awareness to the entire system.

---

## 🚀 Key Features

### 📡 News Harvesting

- **Multi-Source Ingestion**: Pulls data from RSS feeds, web scrapers, and external APIs.
- **Intelligent Deduplication**: Uses deterministic ID hashing to prevent redundant entries.
- **Categorization**: Automatic tagging (News, Policy, Tech, Economy) for targeted retrieval.

### 🧠 Intelligence Engine (Dual-Tier)

- **Decentralized Short-Term State**: Uses `apollo_state.json` to embed the headlines and verified URLs directly into the runtime context, giving Gaia immediate awareness without RAG overhead.
- **Heuristic Ranking 2.0**: Advanced memory retrieval using Similarity + Recency + Category Boosts for deep ChromaDB recall.
- **Local-First Architecture**: Maintains an independent `apollo_memory_core` for standalone resilience.
- **Central Sync**: Asynchronously mirrors deep intelligence to the Gaia Central Brain.

### 🤖 Adaptive Interaction

- **Dynamic Persona**: Guided by `persona_apollo.md` for a sophisticated, observational tone.
- **Intent Recognition**: Responds to complex queries using structured `intent_config.json`.

---

## 📁 Project Structure

```
/apollo/
├── apollo_main.py             # Bot Orchestrator & Scheduler
├── apollo_memory_manager.py   # Memory Manager (Ranking 2.0)
├── persona_apollo.md          # Unified Markdown Persona
├── sources.txt                # RSS/News sources list
├── intent_config.json         # Intent mapping for modularity
├── harvesters/                # Specialized scraping scripts
└── apollo_memory_core/        # Local ChromaDB (auto-created)
```

---

## ⚙️ Installation & Setup

### 1. Requirements

Ensure you have the following installed:

- Python 3.10+
- Dependencies: `pip install -r requirements.txt`

### 2. Configuration

Create an `.env` file in the `apollo/` directory:

```bash
BOT_TOKEN=your_telegram_bot_token
USERS_ALLOWED=123456,789101
TIMEZONE=Asia/Jakarta
LLM_API_KEY=your_key
LLM_MODEL=openrouter/google/gemini-2.0-flash-001
```

### 3. Source Management

Add your preferred news URLs to `sources.txt`.

### 4. Running Apollo

To run as a package (recommended for correct imports):

```bash
# From the gaia-prime root directory
python -m apollo.apollo_main
```

---

## 📱 Telegram Commands

| Command             | Description                                    |
| ------------------- | ---------------------------------------------- |
| **Monitoring**      |                                                |
| `/start`            | Activate Apollo Bot.                           |
| `/help`             | Show this menu.                                |
| **Operations**      |                                                |
| `/force_harvest`    | Trigger manual news collection immediately.    |
| `/add_source [url]` | Add new RSS feed to the database.              |
| **Cortex**          |                                                |
| `/chat [question]`  | Consult Apollo's specific memory (Intel Data). |

---

## 💾 Decentralized Architecture

Apollo can operate in **STANDALONE (Survival)** mode if the central Gaia Brain is offline. For detailed deployment instructions, see [README_STANDALONE.md](README_STANDALONE.md).

---

_Status: ✅ Active Deployment_
