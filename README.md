# Gaia Prime - System Orchestrator

Gaia Prime is the core intelligence hub and sentient orchestrator of the ecosystem. It serves as the primary interface between the User (Alpha Prime) and various autonomous sub-modules.

---

## 🏛️ System Pillars

Gaia Prime manages four dedicated sub-functions, each capable of standalone operation:

- **[Apollo](apollo/README.md)**: Global Intelligence & News Aggregator.
- **[Minerva](minerva/README.md)**: Quantitative Market Analysis & Trading Discipline.
- **[Demeter](demeter/README.md)**: Visual Agronomy & IoT Garden Guardian.
- **[Eleuthia](eleuthia/README.md)**: Personal Assistant & Email Intelligence.

---

## 🚀 Advanced Architecture

### 🧠 Decentralized Memory (Ranking 2.0)

Gaia uses a "Hub & Spoke" memory model:

1. **Local Core**: Sub-modules manage their own semantic memory for low-latency survival.
2. **Short-Term State (state.json)**: Real-time, decentralized JSON ledgers for immediate situational awareness without heavy RAG queries.
3. **Central Sync**: Memories are asynchronously mirrored to the Root Gaia Brain via specialized cross-postings.
4. **Heuristic Ranking 2.0**: Weighted retrieval logic (Similarity + Category + Recency + Priority).

### ⏳ Interactive Agent & Delayed RAG

- **Reminders**: Natural language task scheduling via Telegram.
- **Pre-Generated Answers**: When asked a complex question with a delayed schedule (e.g., "explain relativity but remind me at 5 PM"), Gaia triggers RAG immediately, composes a comprehensive response, and seamlessly defers delivery until the requested time without blocking the event loop.

### 🛡️ Security Protocol

- **Hierarchical Access**: Alpha/Omega key system using OTP (Alpha for general tasks, Omega for critical purges).
- **Authorized IDs**: Strict Telegram user verification.

### 🩹 Lazarus Protocol (Self-Healing)

- **Autonomic Monitoring**: Detects module crashes and tracebacks.
- **AI-Driven Repair**: Automatically attempts to "heal" crashed modules using LLM-based code correction.

---

## 🛠️ Installation & Setup

### 1. Unified Environment

Install dependencies for the entire ecosystem:

```bash
pip install -r requirements.txt
```

### 2. Global Configuration (`.env`)

Fill the global credentials. Sub-modules will look for these if their local `.env` is missing (Standalone Override).

### 3. Ignition

Start the central core:

```bash
python mother_gaia.py
```

---

## 🎮 Central Commands

| Command                              | Description                                                          |
| ------------------------------------ | -------------------------------------------------------------------- |
| **Monitoring**                       |                                                                      |
| `/status`                            | Check System & Module Health.                                        |
| `/audit [name]`                      | Inspect code quality & security.                                     |
| **Control**                          |                                                                      |
| `/start [module]`                    | Start specific module.                                               |
| `/stop [module]`                     | Stop specific module.                                                |
| `/rollback [mod] [lvl] [otp]`        | Manually revert to last backup.                                      |
| `/add_source [url]`                  | Add new RSS feed to Apollo.                                          |
| **Furnace (Creation & Update)**      |                                                                      |
| `/forge [name] [lvl] [otp] [desc]`   | Create new Sub Function AI.                                          |
| `/initialize [name] [lvl] [otp]`     | Deploy & Ignite new Sub Function AI.                                 |
| `/upgrade [mod] [lvl] [otp] [instr]` | Evolve module (Secure).                                              |
| **Security**                         |                                                                      |
| `/setup_security`                    | Generate Alpha/Omega keys.                                           |
| `/purge [mod] [lvl] [otp]`           | Delete module (Soft/Hard Delete).                                    |
| **Lazarus (Self-Healing)**           |                                                                      |
| `/learn`                             | Force Gaia to learn/index source code manually.                      |
| **Cortex (Active Memory & Agents)**  |                                                                      |
| `/chat [question]`                   | Chat with Gaia (Uses RAG & Self-Recording).                          |
| `/remind [text]`                     | Add a reminder using natural language (e.g. "remind me in 10 mins"). |
| `/memory_stats`                      | View memory analytics dashboard.                                     |
| `/cleanup_memory [days]`             | Remove memories older than N days.                                   |
| `/session_info`                      | View active memory sessions.                                         |
| `/new_session [name]`                | Start new isolated memory session.                                   |
| `/switch_session [id]`               | Switch to an existing session.                                       |
| `/end_session`                       | End current memory session.                                          |
| **Info**                             |                                                                      |
| `/help`                              | Detailed architecture and command menu.                              |

---

## 💾 Survival Protocol

Gaia Prime is designed for high availability. In the event of a central core failure, all sub-pillars can transition into **Survival Mode** independently. See [README_STANDALONE.md](docs/survival/README_STANDALONE.md) for global survival instructions.

---

_Status: 🌍 Gaia Mind Synchronized_
