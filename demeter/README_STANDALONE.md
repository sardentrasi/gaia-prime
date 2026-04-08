# Demeter Standalone Deployment Guide

Demeter is architected for "Edge Agronomy." This guide details how to deploy her as an independent physical world controller.

## 🌿 Sovereignty Principles

1. **Local Decision Making**: Validates sensor data against visual input without central cloud reliance.
2. **Deterministic Fallback**: Moves to safety states (Stop Irrigation) if LLM or network fails.
3. **Resilient Logging**: Maintains CSV and image archives locally for manual audit.

## 🛠️ Deployment Steps

### 1. Hardware Localization

Copy the `demeter/` folder to the local machine (e.g., Raspberry Pi or local server) physically near the garden hardware.

### 2. Environment Setup (`.env`)

Ensure `RTSP_URL` is accessible locally. If the Gaia Central sync is unavailable, Demeter automatically engages:
`🧠 Demeter Memory Core Established [STANDALONE (Survival)]`

### 3. Network Configuration

Ensure Port 5000 is open for local ESP32/IoT communication.

### 4. Start Protocol

Run from the parent directory:

```bash
python -m demeter.demeter_main
```

## 🩺 System Check

- Check `demeter.log` for logs: `[GENESIS] ✨ Created Memory Core`.
- Verify Flask: `[SYSTEM] Starting Flask Server (Daemon)...`.
- Verify RTSP: Capture a test image using `/cek`.

---

_Standalone garden safety enabled._
