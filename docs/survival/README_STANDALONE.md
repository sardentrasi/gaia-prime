# Gaia Global Survival Protocol

This document outlines the operational protocol for maintaining system integrity during a "Core Disconnection" event or when running Gaia as a standalone instance.

## 🧠 The Intelligence Kernel

When running without sub-modules, Gaia Prime operates as a **Core Intelligence Kernel**. In this mode, the system focuses on:

- **Systemic Orchestration**: Managing the central memory and security layers.
- **Interactive Agent & Delayed RAG**: Gaia processes natural language scheduling natively (e.g., "remind me to check the server at 5 PM"). For complex queries, Gaia can pre-generate comprehensive RAG answers and seamlessly defer their delivery until the exact requested time.
- **Autonomous Forging (`/forge`)**: Gaia is capable of creating new functional sub-modules from scratch using the `/forge` command, allowing for recursive system expansion.
- **Sentinel Monitoring**: Maintaining the health and self-healing (Lazarus) protocols for any attached cells.

## 🛠️ Standalone Checklist

### 1. Local Configuration Isolation

Each module must have its own `.env` file within its directory. This overrides the root `.env` and allows the module to run on specialized hardware (e.g., Demeter on a Raspberry Pi next to the garden).

### 2. Standalone Execution

Execute modules using the package-aware command from the project root:

```bash
python -m apollo.apollo_main
python -m minerva.minerva_main
python -m demeter.demeter_main
python -m eleuthia.eleuthia_main
```

### 3. Cross-Sync Failure Handling

If a module detects that the central Gaia sync is failing (`ConnectionError`), it will automatically switch to **STANDALONE (Survival)** mode. It will continue to record memories locally and catch up with central sync once connectivity is restored.

## 🩺 System Recovery (Lazarus Core)

If the Root core is reachable but modules are crashing, invoke the Lazarus Protocol:

1. Ensure `brain_lazarus.md` is updated.
2. The sentinel in `mother_gaia.py` will monitor and auto-heal.

---

_Survival verified. The Gaia Mind is eternal._
