# Minerva Standalone Deployment Guide

Minerva is designed to serve as a sovereign Technical Analyst. This guide details how to deploy her independently of the Gaia Prime core.

## 🧠 Sovereignty Features

1. **Satellite Autonomy**: Connects directly to `dlquant_bot` via Userbot account.
2. **Local Memory Core**: Maintains its own technical library and analysis ledger.

## 🛠️ Deployment Steps

### 1. Extraction

Copy the `minerva/` folder to your instance. Ensure `library/` (optional) is included for technical RAG enrichment.

### 2. Identity Config (`.env`)

Fill `minerva/.env` with:

- `TG_API_ID` & `TG_API_HASH`: To enable the Userbot spy.
- `BOT_TOKEN`: For command interaction.
- `LLM_API_KEY`: For technical synthesis.

### 3. Start Command

Run from the parent directory:

```bash
python -m minerva.minerva_main
```

## 🩺 System Check

- Check `minerva.log` for logs: `[GENESIS] ✨ Created Memory Core`.
- Verify userbot start: `... Starting User Spy ...`.

---

_Standalone market intelligence enabled._
