# Eleuthia Standalone Deployment Guide (Survival Edition)

Eleuthia is designed for complete decentralization. This guide explains how to deploy her as an independent "Survival" module, minimizing reliance on the Gaia Prime central core.

## 🚀 Survival Mode Features

- **Local-First Config**: Prioritizes `eleuthia/.env` and local `intent_config.json`.
- **Ranking 2.0**: Full heuristic memory retrieval without needing Gaia central sync.

## Prerequisites

- Python 3.10+
- Dependencies: `pip install -r requirements.txt`

## 🛠️ Deployment Instructions

1. **Localize the Module** 📂
   - Keep the folder named `eleuthia/`.
   - Ensure `eleuthia_memory_core/` is present or will be auto-created for local context.

2. **Environment Isolation** ⚙️
   - Create `eleuthia/.env` with local API keys.
   - If `GAIA_BRAIN_AVAILABLE` is false (due to missing `gaia_memory_manager.py`), Eleuthia automatically enters **STANDALONE (Survival)** mode.

3. **Run the Independent Brain** 🚀
   - From the parent directory: `python -m eleuthia.eleuthia_main`
   - This ensures all relative imports within the `eleuthia` package work correctly.

## 🩺 System Check

- Check `eleuthia.log` for logs: `[GENESIS] ✨ Created Memory Core`.
- Verify mode in startup logs: `🧠 Eleuthia Brain Established [STANDALONE (Survival)]`.

---

_Standalone readiness verified as of Feb 2026 upgrade._
