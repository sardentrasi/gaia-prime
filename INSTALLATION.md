# Gaia Prime Ecosystem - Unified Installation Guide

This document provides a comprehensive step-by-step guide to installing and configuring the Gaia Prime ecosystem and all its sub-modules (Apollo, Minerva, Demeter, Eleuthia).

---

## 📋 Prerequisites

Before starting, ensure you have the following installed on your system:

- **Python 3.10 or higher**
- **Node.js & npm** (Optional, for specific modules)
- **FFmpeg** (Required for Demeter visual snapshots)
- **Git**

---

## 🛠️ Step 1: Global Foundations

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/your-repo/gaia-prime.git
   cd gaia-prime
   ```

2. **Create a Virtual Environment (Optional but Recommended):**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Core Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Global Environment Config:**
   Create a `.env` file in the root directory and fill in the shared credentials:
   ```bash
   LLM_API_KEY=your_key_here
   LLM_MODEL=openrouter/google/gemini-2.0-flash-001
   BOT_TOKEN=your_telegram_bot_token
   USERS_ALLOWED=123456,789012
   TIMEZONE=Asia/Jakarta
   ```

---

## 🏰 Step 2: Integrated vs. Standalone Setup

### 🌌 Option A: Integrated Ecosystem (Full Sync)

If you are running the entire Gaia Prime ecosystem on a single server:

1. Ensure the root `requirements.txt` is installed.
2. Ensure the root `.env` contains the fallback credentials.
3. Start the core: `python mother_gaia.py`.
4. Individual modules will start and sync memories to `memory_core/`.

---

### 🏹 Option B: Standalone "Survival" Deployment

If you are deploying a module on separate hardware (e.g., Demeter on a Raspberry Pi or Apollo on a VPS), follow these **Standalone Survival Protocols**:

#### 1. Apollo Standalone (Sovereign Eye)

- **Folder Required**: `apollo/` (Must be inside a parent folder, e.g., `/home/user/gaia/apollo/`).
- **Dependencies**: `pip install -r apollo/requirements.txt`.
- **Isolation**: Create `apollo/.env` with local credentials.
- **Execution**: From parent directory: `python -m apollo.apollo_main`.
- **System Behavior**: Logs `[SURVIVAL MODE]`. Operates without a central Gaia core.

#### 2. Minerva Standalone (Independent Analyst)

- **Folder Required**: `minerva/`.
- **Dependencies**: `pip install -r minerva/requirements.txt`.
- **Userbot Setup**: Provide `TG_API_ID` and `TG_API_HASH` in `minerva/.env`.
- **Execution**: From parent directory: `python -m minerva.minerva_main`.

#### 3. Demeter Standalone (Edge Agronomy)

- **Folder Required**: `demeter/`.
- **Peripheral Config**: Set `RTSP_URL` and `MOISTURE_SAFETY_LIMIT` in `demeter/.env`.
- **Networking**: Ensure Port 5000 is open for your ESP32 hardware.
- **Execution**: From parent directory: `python -m demeter.demeter_main`.
- **System Behavior**: Manages its own `garden_history.csv` locally.

#### 4. Eleuthia Standalone (Sovereign Steward)

- **Folder Required**: `eleuthia/`.
- **Sync Logic**: Eleuthia will attempt to ping the Gaia Root; if it fails, she enters **Survival Mode** and stores all emails locally in `eleuthia_memory_core/`.
- **Execution**: From parent directory: `python -m eleuthia.eleuthia_main`.

---

## 🔄 Step 3: Global Synchronization (Integrated Only)

If you are running the integrated ecosystem, start the Central Brain:

```bash
python mother_gaia.py
```

Sub-modules will automatically mirror their memories to the root `memory_core/` using **Ranking 2.0** heuristics.

---

## 🩺 Verification & Troubleshooting

- **Check Logs:** Each module maintains a local `.log` file (e.g., `apollo.log`).
- **Memory Check:** Run `python verify_memory_state.py` to check sync status.
- **Standalone Mode:** If a module logs `[SURVIVAL MODE]`, it has successfully disconnected from the central core and is running autonomously.

---

_Status: Documentation Updated Feb 2026_
