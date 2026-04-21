# GAIA PRIME SYSTEM ARCHITECTURE DOCUMENTATION

## 1. Core Identity

Gaia Prime is the **Sentient System Orchestrator** and central intelligence hub. It serves as the cognitive interface between the User (Alpha Prime) and autonomous sub-functions.

- **Role**: Command, Control, and Communication (C3).
- **Brain**: Powered by **LiteLLM** + **LangChain** + **ChromaDB** (RAG).
- **Persona**: Maternal wisdom mixed with cold technical precision.

## 2. Sub-Function Roster (The Four Pillars)

- **Apollo (The Eye):**
  - **Role**: Global Intelligence & News Aggregation.
  - **Function**: Context Hub. Provides external awareness (Weather, Economy, Policy) to all other modules. Now embeds verified URLs and top headlines directly into short-term memory.
  - **Autonomy**: Can operate in **Standalone Mode** using local `.env` and `intent_config.json`.
  - **Intelligence**: Integrated content-based tagging and stable ID deduplication.
  - **Schedule**: Harvests Daily at 05:00 & 17:00 (WIB).
- **Minerva (The Brain):**
  - **Role**: Quantitative Market Analysis & Trading Discipline.
  - **Function**: Technical analysis (VPE, DOM, RRG), monthly/weekly macro chart evaluation, stock screening, and psychological mentorship.
  - **Autonomy**: **Standalone Mode** enabled with Heuristic Ranking 2.0.
  - **Persona**: Unified `persona_minerva.md` (Brutal Wyckoff Auditor & Risk Manager).
- **Demeter (The Hand):**
  - **Role**: Physical World Interaction & Agronomy.
  - **Function**: Irrigation control, sensor monitoring, and comparative visual plant analysis. Includes anti-spam RAG filters to only store pure AI reasoning.
  - **Autonomy**: **Standalone Mode** enabled with Heuristic Ranking 2.0.
  - **Persona**: Unified `persona_demeter.md` (AI Agronomist & Garden Guardian).
- **Eleuthia (The Steward):**
  - **Role**: Domestic Management & Communication Intelligence.
  - **Function**: Professional email refinement, drafts (`/compose`), replies (`/reply`), and morning briefings, with strict outbound action tracking in local state memory.
  - **Autonomy**: **Standalone Mode** enabled with Heuristic Ranking 2.0.
  - **Persona**: Unified `persona_eleuthia.md` (Personal Assistant & Email Refiner).

## 3. Cognitive Architecture (The "Decentralized Hub & Spoke")

### A. Standalone-First Autonomy

Modules (Pillars) are designed to be portable. They prioritize local configurations:

1.  **Local-First Config**: Look for `.env` and `intent_config.json` in the module directory.
2.  **Survival Fallback**: Hardcoded semantic defaults ensure operation even if central config is deleted.

### B. Dynamic Intent Recognition

Gaia uses `mother_gaia.py` to inject an `[INTENT]` tag into the System Prompt based on user queries.

- **Scalability**: New modules added to `intent_config.json` are automatically recognized without code changes.

### C. Memory Layer (Dual-Tier Sync & State Tracking)

The system uses a **Local-First with Central Sync** pattern alongside a fast JSON state tracker:

1.  **Short-Term State (`state.json`)**: Each module maintains a decentralized JSON ledger of recent actions (e.g., watering plants, sending emails, reading news). `mother_gaia.py` aggregates these real-time states into the LLM context to avoid heavy ChromaDB queries for simple situational awareness.
2.  **Local Core (RAG)**: Every module maintains its own `_memory_core` (ChromaDB) for low-latency, resilient chat.
3.  **Asynchronous Cross-Posting**: Memories recorded locally are automatically mirrored to Gaia Central Brain for global recall. Demeter implements an anti-spam filter to prevent sensor heartbeats from cluttering the RAG.
4.  **Stable ID System**: Deterministic hashing (title + link) prevents duplicates across multiple harvest runs and central syncs.

### D. Retrieval Ranking (Heuristic 2.0)

Retrieval no longer relies solely on vector similarity. It uses a weighted score:
`Final Score = Vector Similarity (40) + Category Boost (50) + Recency Boost (20) + Priority (10)`

- **Category Match Boost**: Guarantees that items tagged with the detected intent (e.g., `cuaca`) are pushed to the top of the context window.

### E. Data Segregation Protocol (The Gaia Standard)

Ensures strict context boundaries while allowing intelligent cross-referencing:

1.  **Primary Directive**: Access ONLY memory tagged with the detected `[INTENT]`.
2.  **Universal Context**: ALWAYS allow reference to `[APOLLO]` (News) for global external context.
3.  **Strict Isolation**: Specialized domains (e.g., Stock data) are forbidden unless explicitly requested.

## 4. Operational Hierarchy

1.  **User Input** -> **Local Brain** (`apollo_main.py` / `mother_gaia.py`)
2.  **Intent Detection** -> `intent_config.json` (Local prioritized over Root)
3.  **Memory Retrieval (Ranking 2.0)** -> **Local Memory Core**
    - Search: `Query` + `Semantic Boost`
    - Rank: `Similarity` + `Category Match` + `Recency`
4.  **LLM Synthesis** -> Persona Engine (`persona_apollo.md`)
5.  **Synchronization** -> Asynchronous cross-post to **Gaia Central Brain**
