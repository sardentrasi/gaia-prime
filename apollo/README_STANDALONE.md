# Apollo Standalone Deployment Guide

Apollo is architected for total autonomy. She can be deployed as a "Sovereign Eye" on a separate instance to harvest world events independently.

## 🏹 Survival Principles

1. **Local Priority**: Prioritizes local `.env` and `intent_config.json`.
2. **Offline Resilience**: Operates without `gaia_memory_manager.py` (Central Core).
3. **Independent Scheduling**: Manages its own harvest cycles (Default: 05:00 & 17:00).

## 🛠️ Deployment Steps

### 1. Module Extraction

Copy the `apollo/` folder to your target server. Keep the structure intact.

### 2. Environment Setup

Fill `apollo/.env` with local credentials. If Apollo detects that the central Gaia sync is unavailable, it will automatically switch to:
`🧠 Apollo Memory Core Established [STANDALONE (Survival)]`

### 3. Execution Protocol

Always execute from the parent directory to maintain package context:

```bash
python -m apollo.apollo_main
```

## 🩺 Health Check

- Monitor `apollo.log` for logs: `[GENESIS] ✨ Created Memory Core`.
- Verify harvest success: `✅ Harvest Complete: X items processed`.

---

_Optimized for decentralized awareness._
