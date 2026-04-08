# Minerva - Quantitative Market Analysis Module

**M.I.N.E.R.V.A.** - Market Intelligence & Neural Evaluation for Risk-adjusted Vector Analysis

Minerva is "The Brain" of the Gaia Prime ecosystem, specialized in high-precision technical analysis of the Indonesian stock market.

---

## 📊 Core Capabilities

### 📡 Satellite Data Harvesting

Minerva captures and interprets visual data from professional trading terminals, including:

- **VPE**: Volume Price Analysis (Validation).
- **PIV**: Structural Pivot Points.
- **VBP**: Volume By Price (Supply/Demand Zones).
- **Star Rotation**: RRG Momentum and Sector Analysis.
- **Speedometer**: Fear & Greed Sentiment.
- **DOM**: Bandarmology (Foreign vs Local flow).
- **Tren**: Automated Trendline recognition.

### 🧠 Advanced RAG (Ranking 2.0)

- **Technical Library**: Integrated RAG context for Wyckoff, VSA, and Dow Theory.
- **Heuristic Ranking 2.0**: Domain-specific boosting for market data and timeless trading knowledge.
- **Ledger System**: Maintains a historical record of all analyses for longitudinal performance tracking.

### 🛡️ Trading Discipline Persona

- **Unified Persona**: `persona_minerva.md` defines a Brutal Wyckoff Auditor, harsh evaluator, and cautious trading mentor.
- **Psychological Guardrails**: Enforces strict risk management (Stop Loss/Target Price) and ruthlessly roasts poor emotional entries based on monthly/weekly macro trends.

---

## 📁 Project Structure

```
/minerva/
├── minerva_main.py            # Main Orchestrator (Userbot + Bot API)
├── minerva_memory_manager.py  # Ranking 2.0 Memory Controller
├── persona_minerva.md         # Unified Markdown Persona
├── ledger.json                # Historical Analysis Record
├── minerva_config.json        # Behavioral Settings
├── library/                   # PDF/Technical manuals for RAG
└── harvested_data/            # Local Image & Cache Storage
```

---

## ⚙️ Installation & Setup

### 1. Requirements

- Python 3.10+
- Dependencies: `pip install -r requirements.txt`

### 2. Configuration (`.env`)

Create a `.env` file in the `minerva/` directory:

```bash
BOT_TOKEN=your_telegram_bot_token
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash
SOURCE_BOT_USERNAME=dlquant_bot
TIMEZONE=Asia/Jakarta
LLM_API_KEY=your_key
```

### 3. Execution

Run from the Gaia Prime root:

```bash
python -m minerva.minerva_main
```

---

## 🎮 Commands

| Command                        | Description                                          |
| ------------------------------ | ---------------------------------------------------- |
| **Stock Analysis**             |                                                      |
| `/analyze [ticker]`            | Perform manual analysis on a stock ticker.           |
| `/wanalyze [ticker]`           | Perform weekly timeframe analysis on a stock ticker. |
| **Automation Triggers**        |                                                      |
| `/morning`                     | Trigger manual Morning Call (08:30 WIB).             |
| `/night`                       | Trigger manual Night Analysis (19:00 WIB).           |
| `/weekly`                      | Generate Weekly Strategy Report.                     |
| `/monthly`                     | Generate Monthly Report.                             |
| **Brain Management (Persona)** |                                                      |
| `/viewbrain`                   | View current system prompt.                          |
| `/brainupdate [instruction]`   | Tweak the current brain.                             |
| `/brainreplace [concept]`      | Re-write the brain from scratch.                     |
| `/ingest`                      | Read & memorize library (PDFs) into RAG.             |
| **Info**                       |                                                      |
| `/help`                        | Show documentation.                                  |

---

## 💾 Decentralized Architecture

Minerva can operate in **STANDALONE (Survival)** mode, maintaining its own image cache and memory core without Gaia Central. See [README_STANDALONE.md](README_STANDALONE.md) for details.

---

_Status: 📈 Fully Operational_
