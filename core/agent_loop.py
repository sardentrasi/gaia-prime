"""
Gaia Prime - Agent Loop
The heart of the architecture: Message → LLM ↔ Tools → Response
Orchestrates intent detection, context retrieval, prompt assembly, 
LLM invocation, and response recording.
Extracted from GaiaSystem._neural_core_process().
"""

import os
import re
import json
import logging
from datetime import datetime

import pytz

from core.message import GaiaMessage
from core.llm_engine import PolyglotEngine
from core.context import ContextManager, IntentResult
from core.tools import ToolRegistry

logger = logging.getLogger("AgentLoop")

# Maximum iterations for LLM ↔ Tools loop
MAX_TOOL_ITERATIONS = 8


# Timezone Setup
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")


class AgentLoop:
    """
    Core Agent Loop for Gaia Prime.
    Implements the diagram flow: Message → LLM ↔ Tools → Response
    
    Steps:
      1. Session management
      2. Memory recording
      3. Small talk / intent detection
      4. Reminder interception
      5. Context retrieval (RAG + situational awareness)
      6. Prompt assembly
      7. LLM invocation
      8. Response recording
    """



    def __init__(self, engine: PolyglotEngine, context: ContextManager, brain,
                 tool_registry: ToolRegistry = None):
        """
        Args:
            engine: PolyglotEngine for LLM calls
            context: ContextManager for intent/retrieval/prompt
            brain: GaiaBrain instance for memory persistence
            tool_registry: ToolRegistry for LLM function calling
        """
        self.engine = engine
        self.context = context
        self.brain = brain
        self.tools = tool_registry

        # Load persona content for fallback/wait messages
        self.persona_text = ""
        persona_path = os.path.join(os.getcwd(), "persona.md")
        if os.path.exists(persona_path):
            try:
                with open(persona_path, "r", encoding="utf-8") as f:
                    self.persona_text = f.read()
            except Exception as e:
                logger.error(f"❌ [AGENT LOOP] Failed to load persona.md: {e}")

    async def process(self, message: GaiaMessage) -> str:
        """
        Main agent loop. Processes a platform-agnostic GaiaMessage 
        and returns a response string.
        
        Extracted from GaiaSystem._neural_core_process().
        
        Args:
            message: Unified GaiaMessage from any connector
            
        Returns:
            Response text to send back to the user
        """
        user_id = str(message.user_id)
        user_name = message.user_name
        user_query = message.text
        platform = message.platform
        target_id = message.target_id

        # ─── 1. SESSION MANAGEMENT ───
        active_session = self.brain.get_active_session(user_id)
        if not active_session:
            active_session = self.brain.create_session(user_id=user_id, user_name=user_name)
            self.brain.set_active_session(user_id, active_session)
            logger.info(f"✨ [AUTO-SESSION] Created session {active_session} for user {user_id}")

        # ─── 2. ACTIVE MEMORY RECORDING ───
        if message.has_substance:
            logger.info(f"[MEMORY] 📝 Menyimpan percakapan dari {user_name}...")
            self.brain.record(
                text=user_query,
                user_name=user_name,
                tags=f"user_chat_{user_id}",
                source="user_interaction",
                session_id=active_session,
                user_id=user_id
            )

        # ─── 3. INTENT DETECTION ───
        intent = self.context.detect_intent(user_query)

        # ─── 4. REMINDER INTERCEPTION ───
        # Skip interception if the query is about managing existing reminders
        # (let the LLM handle via list_pending, postpone_cron, delete_cron tools)
        management_keywords = [
            "list", "cek", "ada", "tampilkan", "lihat", "show", "pending",
            "hapus", "delete", "cancel", "batalkan",
            "tunda", "postpone", "reschedule", "geser", "mundurkan"
        ]
        is_management = any(k in user_query.lower() for k in management_keywords)
        if "reminder" in intent.found_entities and not is_management:
            return await self._handle_reminder(
                user_query, user_id, user_name, platform, target_id,
                active_session, intent
            )

        # ─── 5. CONTEXT RETRIEVAL ───
        # Skip RAG for management queries (list/cek/tunda reminder) — tools only read JSON
        hits = ""
        if not intent.is_small_talk and not is_management:
            hits = self.context.retrieve(
                user_query, intent, session_id=active_session, user_id=user_id
            )

        # Short-term memory (conversation history)
        session_history = (
            self.brain.get_recent_session_history(active_session, n=5) 
            if active_session else []
        )

        # Situational awareness from module states
        network_awareness = self.context.gather_situational_awareness()

        # ─── 6. PROMPT ASSEMBLY ───
        system_prompt = self.context.build_prompt(
            query=user_query,
            context_hits=hits,
            session_history=session_history,
            network_awareness=network_awareness,
            intent=intent,
            user_name=user_name
        )

        # ─── 7. LLM INVOCATION (Iterative Tool Loop) ───
        if self.tools:
            # Set message context so pending commands know where to reply
            self.tools._current_msg = {
                "platform": message.platform,
                "target_id": getattr(message, 'target_id', '') or user_id
            }
            response_text = await self._tool_loop(
                system_prompt=system_prompt,
                user_query=user_query,
                session_history=session_history,
                context_str=hits,
                user_name=user_name
            )
        else:
            # Fallback: single-pass LLM (backward compatible)
            response_text = await self.engine.chat(
                system_prompt=system_prompt,
                user_query=user_query,
                history=session_history,
                context_str=hits,
                user_name=user_name
            )

        # Clean up any raw tool_call bleed-out from free-tier models
        if response_text:
            response_text = re.sub(r'<tool_call>.*?</tool_call>', '', response_text, flags=re.DOTALL)
            response_text = response_text.strip()

        if not response_text:
            # If no final response after tool loop, generate a "processing" message via LLM
            logger.info("⏳ [AGENT LOOP] No response text, generating 'please wait' message via LLM...")
            try:
                # Build a persona-aware system prompt for the wait message
                system_instr = (
                    f"{self.persona_text}\n\n"
                    "Your previous actions are being processed in the background. "
                    "Briefly tell the user to wait in a friendly, helpful way consistent with your persona. "
                    "Be concise."
                )
                response_text = await self.engine.chat(
                    system_prompt=system_instr,
                    user_query=user_query,
                    history=session_history,
                    user_name=user_name
                )
            except Exception as e:
                logger.error(f"❌ [AGENT LOOP] Failed to generate wait message: {e}")
                response_text = "Mohon tunggu sebentar ya, sedang saya proses di latar belakang... ⏳"

        # ─── 8. RESPONSE RECORDING ───
        if len(response_text) > 20:
            self.brain.record(
                text=f"GAIA to {user_name}: {response_text}",
                user_name="Gaia",
                tags=f"ai_response_{user_id}",
                source="user_interaction",
                session_id=active_session,
                user_id=user_id
            )

        return response_text

    async def _tool_loop(self, system_prompt: str, user_query: str,
                         session_history: list = None, context_str: str = None,
                         user_name: str = "User") -> str:
        """
        Iterative LLM ↔ Tools loop.
        Sends messages to LLM with tool schemas. If LLM requests tool calls,
        executes them and feeds results back. Repeats until LLM returns
        a final text response or max iterations reached.
        
        Args:
            system_prompt: Full system prompt
            user_query: User's message
            session_history: Recent conversation history
            context_str: RAG context
            user_name: User display name
            
        Returns:
            Final response text from LLM
        """
        # Build initial messages in OpenAI format
        history_str = "\n".join(session_history) if session_history else "No history."
        
        # Inject context and history into system prompt if not already present
        final_system = system_prompt
        has_history = any(m in system_prompt for m in [
            "[CONVERSATION HISTORY]", "[HISTORI PERCAKAPAN SINGKAT]",
            "**Short-term Memory:**", "{history}"
        ])
        has_context = any(m in system_prompt for m in [
            "[MEMORY CONTEXT]", "[ALIRAN MEMORI / DATA SEKTOR]",
            "**Sector Data / Memory Hits:**", "{context}"
        ])
        
        if not has_history:
            if not has_context and context_str:
                final_system = (
                    f"{system_prompt}\n\n[CONVERSATION HISTORY]:\n{history_str}\n\n"
                    f"[MEMORY CONTEXT]:\n{context_str}\n\n[USER]: {user_name}"
                )
            else:
                final_system = (
                    f"{system_prompt}\n\n[CONVERSATION HISTORY]:\n{history_str}\n\n[USER]: {user_name}"
                )

        messages = [
            {"role": "system", "content": final_system},
            {"role": "user", "content": user_query}
        ]

        tool_schemas = self.tools.get_tool_schemas()

        for iteration in range(MAX_TOOL_ITERATIONS):
            logger.info(f"🔄 [AGENT LOOP] Iteration {iteration + 1}/{MAX_TOOL_ITERATIONS}")

            response_msg = self.engine.chat_with_tools(messages, tools=tool_schemas)

            # Check if LLM wants to call tools
            tool_calls = getattr(response_msg, 'tool_calls', None)

            if not tool_calls:
                # No tools requested — this is the final answer
                content = getattr(response_msg, 'content', None) or "..."
                logger.info(f"✅ [AGENT LOOP] Final response at iteration {iteration + 1}")
                return content

            # LLM requested tool calls — execute them
            logger.info(f"🔧 [AGENT LOOP] LLM requested {len(tool_calls)} tool call(s)")

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": getattr(response_msg, 'content', None),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            })

            # Execute each tool and append results
            for tc in tool_calls:
                func_name = tc.function.name
                try:
                    func_args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    func_args = {}

                result = self.tools.execute(func_name, func_args)

                messages.append({
                    "tool_call_id": tc.id,
                    "role": "tool",
                    "name": func_name,
                    "content": str(result)
                })

        # Max iterations reached — get final response without tools
        logger.warning(f"⚠️ [AGENT LOOP] Max iterations ({MAX_TOOL_ITERATIONS}) reached. Forcing final response.")
        response_msg = self.engine.chat_with_tools(messages, tools=None)
        return getattr(response_msg, 'content', None) or "..."



    async def _handle_reminder(self, user_query, user_id, user_name, 
                                platform, target_id, active_session, intent):
        """
        Handle reminder entity detected in intent.
        Creates a one-shot cron job for scheduled delivery.
        Supports both simple reminders and delayed RAG answers.
        """
        delivery_id = target_id if target_id else str(user_id)
        meta = self._extract_reminder_metadata(user_query)
        
        if not meta:
            return "Maaf, instruksi waktu/pengingat tidak dapat dipahami."

        time_str = self._format_reminder_time(meta["time"])

        if meta.get("is_question"):
            # Deep question — run full RAG, then schedule delivery
            from core.message import GaiaMessage
            question_msg = GaiaMessage(
                user_id=user_id,
                user_name=user_name,
                text=meta["task"],
                platform=platform,
                target_id=target_id
            )
            
            # Remove reminder from entities to avoid infinite loop
            question_intent = self.context.detect_intent(meta["task"])
            question_intent.found_entities = [
                e for e in question_intent.found_entities if e != "reminder"
            ]
            
            hits = self.context.retrieve(
                meta["task"], question_intent, 
                session_id=active_session, user_id=str(user_id)
            )
            session_history = self.brain.get_recent_session_history(active_session, n=5)
            network_awareness = self.context.gather_situational_awareness()
            
            system_prompt = self.context.build_prompt(
                query=meta["task"],
                context_hits=hits,
                session_history=session_history,
                network_awareness=network_awareness,
                intent=question_intent,
                user_name=user_name
            )
            
            response_text = await self.engine.chat(
                system_prompt=system_prompt,
                user_query=meta["task"],
                history=session_history,
                context_str=hits,
                user_name=user_name
            )
            
            # Save as one-shot cron job with pre-computed answer
            self.tools.cron.create_job(
                name=f"Reminder: {meta['task'][:40]}",
                schedule=f"once {meta['time']}",
                action=response_text,
                platform=platform,
                target_id=delivery_id,
                job_type="reminder"
            )
            
            # Record to RAG for long-term recall
            self.brain.record(
                text=f"[REMINDER] {user_name} membuat pengingat: '{meta['task']}' dijadwalkan {time_str} via {platform}. Jawaban telah disiapkan.",
                user_name=user_name,
                tags="reminder",
                source="reminder",
                session_id=active_session,
                user_id=str(user_id)
            )
            
            # Generate confirmation
            confirm_prompt = (
                system_prompt + 
                "\n\n[INSTRUCTION] Berikan konfirmasi yang hangat dan profesional sebagai Gaia "
                "bahwa data telah diproses dan akan dikirim otomatis sesuai jadwal. "
                "Jangan sertakan isi risetnya sekarang."
            )
            return await self.engine.chat(
                system_prompt=confirm_prompt,
                user_query=(
                    f"Konfirmasi secara natural bahwa riset komprehensif mengenai "
                    f"'{meta['task']}' sudah siap dan dijadwalkan untuk dikirim pada {time_str}."
                ),
                history=session_history,
                user_name=user_name
            )
        else:
            # Simple reminder → refine text with LLM + persona, then create one-shot cron job
            refined_action = self._refine_reminder_text(meta["task"], user_name)
            self.tools.cron.create_job(
                name=f"Reminder: {meta['task'][:40]}",
                schedule=f"once {meta['time']}",
                action=refined_action,
                platform=platform,
                target_id=delivery_id,
                job_type="reminder"
            )
            
            # Record to RAG for long-term recall
            self.brain.record(
                text=f"[REMINDER] {user_name} membuat pengingat: '{meta['task']}' dijadwalkan {time_str} via {platform}.",
                user_name=user_name,
                tags="reminder",
                source="reminder",
                session_id=active_session,
                user_id=str(user_id)
            )
            return f"✅ Pengingat aktif. Saya akan mengingatkan: '{meta['task']}' pada {time_str}."

    def _format_reminder_time(self, time_iso: str) -> str:
        """Format ISO time string for human display."""
        try:
            return datetime.fromisoformat(time_iso).strftime("%d %b %Y %H:%M")
        except Exception:
            return time_iso

    def _refine_reminder_text(self, task: str, user_name: str = "User") -> str:
        """Use LLM + Gaia persona to transform raw reminder text into a natural message."""
        persona_path = os.path.join(self.context.root_dir, "persona.md")
        persona_snippet = ""
        try:
            if os.path.exists(persona_path):
                with open(persona_path, "r", encoding="utf-8") as f:
                    persona_snippet = f.read()[:500]
        except Exception:
            pass

        prompt = (
            f"{persona_snippet}\n\n"
            f"[INSTRUKSI] Ubah pesan pengingat berikut menjadi pesan yang natural, hangat, dan sesuai persona Gaia. "
            f"Pesan ini akan dikirim langsung ke user bernama {user_name} saat waktunya tiba. "
            f"Buat singkat (1-2 kalimat), gunakan emoji yang relevan, dan langsung ke inti tanpa basa-basi.\n\n"
            f"Pesan asli: \"{task}\"\n\n"
            f"Tulis HANYA pesan pengingatnya, tanpa penjelasan tambahan."
        )
        try:
            refined = self.engine.ask(prompt)
            return refined.strip() if refined and refined.strip() else task
        except Exception as e:
            logger.warning(f"Failed to refine reminder text, using raw: {e}")
            return task

    def _extract_reminder_metadata(self, query: str) -> dict:
        """Extract reminder time and task from natural language query."""
        prompt = f"""
        Tugas: Ekstrak pengingat/reminder dari Teks Asli. 
        Tentukan apakah pesan ini memuat pertanyaan yang butuh DIJAWAB panjang oleh AI (seperti 'jelaskan', 'apa itu', 'berikan ide') ATAU hanya alarm sederhana (seperti 'minum air', 'matikan lampu', 'pergi meeting').
        
        Aturan Waktu:
        1. Parse waktu Indonesia seperti 'lewat' (misal: 18 lewat 10 = 18:10).
        2. Jika user menyebut waktu tanpa tanggal, asumsikan HARI INI berdasarkan Waktu Sekarang.
        3. Jika waktu sudah lewat di hari ini, asumsikan BESOK.
        
        Teks Asli: "{query}"
        Waktu Sekarang: {datetime.now(MY_TZ).isoformat()}
        
        Keluarkan MURNI JSON tanpa markdown:
        {{
            "time": "ISO-8601 string waktu yang spesifik dari Waktu Sekarang, misal 2026-02-20T16:00:00+07:00",
            "task": "Pesan inti (jika is_question true, ini berisi PERTANYAAN utamanya)",
            "is_question": true/false
        }}
        """
        try:
            response = self.engine.ask(prompt, json_mode=True)
            return json.loads(self._clean_json_text(response))
        except Exception as e:
            logger.error(f"Failed to extract reminder metadata: {e}")
            return None

    @staticmethod
    def _clean_json_text(text: str) -> str:
        """Removes markdown code blocks and extra characters for JSON parsing."""
        if not text:
            return "{}"
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            if len(lines) > 2:
                clean = "\n".join(lines[1:-1])
            else:
                clean = clean.replace("```json", "").replace("```python", "").replace("```", "")
        return clean.strip()
