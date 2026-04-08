"""
Gaia Prime - Context Layer (Memory + Skills)
Encapsulates intent detection, RAG retrieval, prompt assembly, and situational awareness.
Extracted from GaiaSystem._neural_core_process() context logic and gather_situational_awareness().
"""

import os
import re
import json
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional

logger = logging.getLogger("GaiaContext")


@dataclass
class IntentResult:
    """Result of intent detection on a user query."""
    is_small_talk: bool = False
    is_technical: bool = False
    is_news: bool = False
    is_architecture: bool = False
    found_entities: List[str] = field(default_factory=list)
    
    @property
    def has_entities(self) -> bool:
        return bool(self.found_entities)


class ContextManager:
    """
    Context Layer for Gaia Prime.
    Handles:
      - Intent detection using config-driven keywords
      - RAG memory retrieval with semantic boosts
      - Prompt assembly (persona + context + history + network awareness)
      - Situational awareness from decentralized module states
    """

    def __init__(self, brain, intent_config: dict = None, root_dir: str = None):
        """
        Args:
            brain: GaiaBrain instance for memory access
            intent_config: Loaded intent_config.json dict (or brain.config)
            root_dir: Root directory for Gaia Prime (for reading state files)
        """
        self.brain = brain
        self.config = intent_config or getattr(brain, 'config', {})
        self.root_dir = root_dir or os.path.dirname(os.path.abspath(__file__))
        # Walk up one level from core/ to project root
        if self.root_dir.endswith('core'):
            self.root_dir = os.path.dirname(self.root_dir)

    def detect_intent(self, query: str) -> IntentResult:
        """
        Detect intent from user query using keyword matching and entity filters.
        Extracted from _neural_core_process lines 1122-1172.
        
        Args:
            query: The user's message text
            
        Returns:
            IntentResult with detected intents and entities
        """
        result = IntentResult()
        q_lower = query.lower()

        # --- Small Talk Detection ---
        small_talk_patterns = [
            r"^(hi|halo|hello|hey|hai|pagi|siang|sore|malam)(.*?)(gaia)?$",
            r"^(apa kabar|gimana kabar|tes|ping|test|cek)(.*?)$",
            r"^(.{0,10})(makasih|terima kasih|thanks|thank you|ok|oke|sip|mantap)(.{0,10})$"
        ]
        
        if len(query) < 50:
            for pattern in small_talk_patterns:
                if re.match(pattern, query, re.IGNORECASE):
                    result.is_small_talk = True
                    logger.info(f"🗣️ [SMALL TALK] Detected casual conversation")
                    return result

        # --- Keyword-Based Intent ---
        technical_keywords = self.config.get("technical_keywords", [
            "code", "kode", "script", "file", "fungsi", "function", "class", "def ", "import ", "main.py"
        ])
        news_keywords = self.config.get("news_keywords", [
            "berita", "news", "headline", "ihsg", "saham", "market", "cuaca", "laporan"
        ])
        architecture_keywords = self.config.get("architecture_keywords", [
            "architecture", "arsitektur", "flow", "alur", "topology"
        ])

        result.is_technical = any(k in q_lower for k in technical_keywords)
        result.is_news = any(k in q_lower for k in news_keywords)
        result.is_architecture = any(k in q_lower for k in architecture_keywords)

        # Priority rules
        if result.is_news:
            result.is_technical = False
        if result.is_architecture:
            result.is_technical = True

        # --- Entity Detection (Regex-based) ---
        entity_filters = self.config.get("entity_filters", {})
        for entity, keywords in entity_filters.items():
            match_found = False
            if re.search(rf"\b{entity}\b", query, re.IGNORECASE):
                match_found = True
            else:
                for k in keywords:
                    if re.search(rf"\b{re.escape(k)}\b", query, re.IGNORECASE):
                        match_found = True
                        break
            if match_found:
                result.found_entities.append(entity)

        return result

    def retrieve(self, query: str, intent: IntentResult, 
                 session_id: str = None, user_id: str = None) -> str:
        """
        Retrieve relevant context from memory based on detected intent.
        Extracted from _neural_core_process lines 1198-1245.
        
        Args:
            query: User query
            intent: Detected intent result
            session_id: Active session ID
            user_id: User identifier
            
        Returns:
            String of retrieved memory hits
        """
        q_lower = query.lower()
        active_filter = []
        domain_keywords = ""
        hits = ""
        
        if intent.found_entities:
            active_filter = list(intent.found_entities)
            semantic_boosts = self.config.get("semantic_boosts", {})

            # Lean Retrieval: only use semantic boosts for keywords
            for entity in intent.found_entities:
                if entity in semantic_boosts:
                    domain_keywords += " " + semantic_boosts[entity]

            if intent.is_technical:
                domain_keywords = self.config.get(
                    "technical_domain_keywords",
                    "source code python script function class architecture logic main.py"
                )
                for entity in intent.found_entities:
                    domain_keywords += f" {entity}_main.py {entity}_core.py"

            # Recency boost
            recency_keywords = self.config.get("recency_keywords", [
                "semalam", "tadi malam", "last night", "kemarin", "yesterday",
                "recent", "latest", "terakhir", "terbaru"
            ])
            recency_boost_text = self.config.get("memory_retrieval", {}).get(
                "recency_boost_keywords", "recent latest today yesterday night analysis report"
            )
            if any(keyword in q_lower for keyword in recency_keywords):
                historical_indicators = [
                    "bulan lalu", "tahun lalu", "dulu", "history", "sejarah",
                    "masa lalu", "past", "last month", "last year"
                ]
                if any(h in q_lower for h in historical_indicators):
                    domain_keywords += " history past historical long-term archive"
                else:
                    domain_keywords += f" {recency_boost_text}"

            # Construct Final Query
            boosted_query = f"{query} {domain_keywords}".strip()

            # ─── FIX: Include book/knowledge data in positive filters ───
            active_filter.extend(["user_interaction", "gaia_noted", "book", "technical_knowledge", "-learned_content"])

            # Prevent Source Code Leak in General Queries
            if not intent.is_technical:
                active_filter.append("-source_code")

            filter_str = ", ".join(active_filter)
            entity_limit = self.config.get("memory_retrieval", {}).get("entity_query_limit", 25)

            # ─── DUAL-QUERY STRATEGY: Parallel retrieval for book + chat data ───
            knowledge_entities = {"minerva", "technical_knowledge"}
            has_knowledge = bool(set(intent.found_entities) & knowledge_entities)

            if has_knowledge:
                logger.info(f"📚 [DUAL-QUERY] Running parallel book + chat retrieval")
                # Query 1: Normal entity query (chat data)
                chat_hits = self.brain.remember(
                    boosted_query, n_results=entity_limit,
                    filter_type=filter_str, session_id=session_id, user_id=user_id
                )
                # Query 2: Book-specific query (knowledge data)
                book_boost = self.config.get("semantic_boosts", {}).get("technical_knowledge", "")
                book_query = f"{query} {book_boost}".strip()
                book_filter = "book, technical_knowledge, -learned_content, -source_code"
                book_limit = self.config.get("memory_retrieval", {}).get("book_query_limit", 10)
                book_hits = self.brain.remember(
                    book_query, n_results=book_limit,
                    filter_type=book_filter, session_id=None, user_id=None,
                    use_cache=False
                )
                # Merge results (book data first for priority)
                parts = []
                if book_hits:
                    parts.append(f"[📚 KNOWLEDGE DATA]\n{book_hits}")
                if chat_hits:
                    parts.append(f"[💬 INTERACTION DATA]\n{chat_hits}")
                hits = "\n\n".join(parts)
            else:
                hits = self.brain.remember(
                    boosted_query, n_results=entity_limit,
                    filter_type=filter_str, session_id=session_id, user_id=user_id
                )

        elif intent.is_technical:
            filter_str = "source_code, user_interaction, -learned_content"
            technical_limit = self.config.get("memory_retrieval", {}).get("technical_query_limit", 5)
            hits = self.brain.remember(
                query, n_results=technical_limit, 
                filter_type=filter_str, session_id=session_id, user_id=user_id
            )
        else:
            filter_str = "user_interaction, gaia_noted, -learned_content"
            general_limit = self.config.get("memory_retrieval", {}).get("general_query_limit", 5)
            hits = self.brain.remember(
                query, n_results=general_limit,
                filter_type=filter_str, session_id=session_id, user_id=user_id
            )

        # ─── POST-RETRIEVAL: Keyword Relevance Filter ───
        # Extract key terms from query (uppercase words = likely tickers/entity names)
        # Filter hit lines to only keep those containing relevant terms
        if hits and intent.found_entities:
            hits = self._filter_hits_by_relevance(query, hits)

        return hits or ""

    def _filter_hits_by_relevance(self, query: str, hits: str) -> str:
        """
        Post-retrieval filter: keep only hit lines that contain
        key terms from the user's query (tickers, entity names, etc).
        Prevents LLM from seeing irrelevant data and hallucinating.
        """
        # Extract likely entity names: uppercase words 2+ chars, or quoted terms
        import re as _re
        # Match uppercase words (stock tickers like BULL, DEWA, GTSI)
        upper_tokens = set(_re.findall(r'\b[A-Z]{2,}\b', query))
        # Also match capitalized multi-word names (like "Darma Henwa")
        capitalized = set(_re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query))
        
        # Combine all key terms (lowercase for matching)
        key_terms = set()
        for t in upper_tokens:
            if t not in ('CEK', 'TBK', 'PT', 'DAN', 'DARI', 'YANG', 'UNTUK', 'DENGAN', 'YA'):
                key_terms.add(t.lower())
        for t in capitalized:
            if len(t) > 3:  # Skip short words
                key_terms.add(t.lower())
        
        if not key_terms:
            return hits  # No key terms to filter by
        
        logger.info(f"🔎 [RELEVANCE FILTER] Key terms: {key_terms}")
        
        # Split hits into sections and lines, keep relevant ones
        lines = hits.split('\n')
        filtered_lines = []
        section_header = ""
        
        for line in lines:
            line_lower = line.lower()
            # Always keep section headers
            if line.startswith('[📚') or line.startswith('[💬'):
                section_header = line
                filtered_lines.append(line)
                continue
            # Check if line contains any key term
            if any(term in line_lower for term in key_terms):
                filtered_lines.append(line)
        
        if filtered_lines:
            result = '\n'.join(filtered_lines)
            logger.info(f"🔎 [RELEVANCE FILTER] {len(lines)} → {len(filtered_lines)} lines (kept relevant)")
            return result
        
        # If nothing matched, return original (don't lose all data)
        logger.warning(f"⚠️ [RELEVANCE FILTER] No lines matched key terms, returning original hits")
        return hits

    def build_prompt(self, query: str, context_hits: str, session_history: list,
                     network_awareness: str, intent: IntentResult,
                     user_name: str = "User") -> str:
        """
        Assemble the full system prompt from persona + context + history + awareness.
        Extracted from _neural_core_process lines 1253-1297.
        
        Args:
            query: User query
            context_hits: RAG retrieval results
            session_history: Recent conversation history
            network_awareness: Situational awareness from module states
            intent: Detected intent result
            user_name: User display name
            
        Returns:
            Complete system prompt string
        """
        now = datetime.now()
        days_id = {
            0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
            4: "Jumat", 5: "Sabtu", 6: "Minggu"
        }
        day_name = days_id.get(now.weekday(), now.strftime("%A"))
        current_time = f"{day_name}, {now.strftime('%d %B %Y %H:%M')}"
        
        try:
            persona_path = os.path.join(self.root_dir, "persona.md")
            with open(persona_path, "r", encoding="utf-8") as f:
                persona_template = f.read()
            
            system_prompt = persona_template.format(
                time_now=current_time,
                history="\n".join(session_history) if session_history else "No recent history.",
                context=context_hits if context_hits else "No relevant sector data found."
            )

            # Situational Awareness injection
            if network_awareness:
                system_prompt += f"\n\n[SITUATIONAL AWARENESS]\n{network_awareness}\n"

            # Multi-domain synergy
            if len(intent.found_entities) > 1:
                domains_str = ", ".join([e.upper() for e in intent.found_entities])
                synergy_prompt = (
                    f"\n\n[INFO: KORELASI DATA] Saya mendeteksi adanya keterkaitan antara data dari sektor {domains_str}. "
                    "Sampaikan temuan ini secara natural dalam satu narasi yang terpadu. "
                    "Jelaskan bagaimana data-data tersebut saling berhubungan (misal: pengaruh cuaca terhadap kondisi tanaman) "
                    "tanpa menggunakan daftar poin yang kaku atau bahasa yang terlalu teknis/puitis."
                )
                system_prompt += synergy_prompt

            # Technical self-reflection mode
            if intent.is_technical:
                system_prompt += "\n[MODE: SELF-REFLECTION] You are reviewing your own source code. Explain logic clearly."

            # Architecture awareness
            if intent.is_architecture:
                try:
                    arch_path = os.path.join(self.root_dir, "system_architecture.md")
                    registry_path = os.path.join(self.root_dir, "registry.json")
                    
                    with open(arch_path, "r", encoding="utf-8") as f:
                        arch_doc = f.read()
                    with open(registry_path, "r", encoding="utf-8") as f:
                        registry_doc = f.read()
                    
                    system_prompt += (
                        f"\n\n[SYSTEM ARCHITECTURE CONTEXT]\n{arch_doc}\n\n"
                        f"[CURRENT MODULE REGISTRY]\n{registry_doc}\n"
                        "\n[INSTRUCTION] Use the provided System Architecture and Registry data "
                        "to answer questions about Gaia's internal structure, data flow, and module status."
                    )
                except Exception as e:
                    logger.error(f"Failed to load architecture docs: {e}")

        except Exception as e:
            system_prompt = f"You are Gaia Prime. Time: {current_time}.\nAnswer accurately."
            logger.error(f"Prompt assembly fallback: {e}")

        return system_prompt

    def gather_situational_awareness(self) -> str:
        """
        Aggregate real-time status from decentralized module states.
        Extracted from GaiaSystem.gather_situational_awareness().
        
        Returns:
            Narrative string of module statuses
        """
        identity_file = os.path.join(self.root_dir, "module_identity.json")
        narrative_parts = []

        try:
            if not os.path.exists(identity_file):
                logger.warning("⚠️ Module Identity file missing. Assuming no decentralized awareness.")
                return "Situational Awareness: [OFFLINE] Module identities mapping not found."

            with open(identity_file, "r", encoding="utf-8") as f:
                identities = json.load(f)

            for module_name, info in identities.items():
                if not info.get("active", False):
                    continue

                state_file = os.path.join(self.root_dir, module_name, f"{module_name}_state.json")
                if os.path.exists(state_file):
                    try:
                        with open(state_file, "r", encoding="utf-8") as sf:
                            state_data = json.load(sf)

                        memories = state_data.get("short_term_memory", [])
                        if memories:
                            latest = memories[-1]
                            action_str = str(latest.get('action', ''))
                            result_str = str(latest.get('result', ''))
                            result_snip = (result_str[:50000] + "...(truncated)" 
                                          if len(result_str) > 50000 else result_str)

                            narrative_parts.append(
                                f"- {module_name.capitalize()} ({info.get('role', 'Subsystem')}) "
                                f"reported at {latest.get('timestamp')}:\n"
                                f"  Action: '{action_str}' -> Result: '{result_snip}'"
                            )
                    except Exception as e:
                        logger.error(f"❌ Failed to decode state payload for {module_name}: {e}")

            if not narrative_parts:
                return "System Action: All modules operating nominally. No recent events in short-term memory."

            final_report = (
                "Real-Time Gaia Prime Ecosystem Status (Last Known Actions):\n" 
                + "\n".join(narrative_parts)
            )
            logger.info(f"🌐 [SITUATIONAL AWARENESS] Gathered real-time status from {len(narrative_parts)} active modules.")
            return final_report

        except Exception as e:
            logger.error(f"❌ Critical Failure gathering situational awareness: {e}", exc_info=True)
            return "System Status: Error establishing network sync with localized memory states."
