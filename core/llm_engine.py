"""
Gaia Prime - LLM Engine Layer (Polyglot Engine)
Consolidates all LLM interaction: direct completion + LangChain chat.
Extracted from GaiaSystem._ask_polyglot() and GaiaBrain.chat_with_langchain()
"""

import os
import logging
import time
import base64
from litellm import completion, token_counter

logger = logging.getLogger("PolyglotEngine")


class PolyglotEngine:
    """
    Unified LLM interface for Gaia Prime.
    Supports:
      - Direct completion (ask) with key rotation (Hydra Protocol)
      - LangChain conversational chat with multimodal support
    """

    def __init__(self, model: str = None, api_keys: list = None, ollama_url: str = None):
        self.model = model or os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")
        self.ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        # [HYDRA PROTOCOL] Multi-Key Support
        if api_keys:
            self.api_keys = api_keys
        else:
            keys_str = os.getenv("LLM_API_KEYS", "") or os.getenv("LLM_API_KEY", "")
            self.api_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
        
        self.current_key_index = 0
        
        if not self.api_keys:
            logger.error("CRITICAL: No LLM API keys available")
        else:
            logger.info(f"✅ PolyglotEngine initialized | Model: {self.model} | Keys: {len(self.api_keys)}")

    @property
    def primary_key(self) -> str:
        """Returns the currently active API key."""
        return self.api_keys[self.current_key_index] if self.api_keys else None

    def ask(self, prompt: str, json_mode: bool = False, model_override: str = None) -> str:
        """
        Direct LLM completion with key rotation.
        Extracted from GaiaSystem._ask_polyglot().
        
        Args:
            prompt: The prompt text
            json_mode: If True, request JSON output format
            model_override: Override the default model
            
        Returns:
            Raw string response from LLM
        """
        target_model = model_override or self.model
        api_base = self.ollama_url if ("ollama" in target_model or "local" in target_model) else None

        # Token Logging (Safety Check)
        msgs = [{"role": "user", "content": prompt}]
        try:
            count = token_counter(model=target_model, messages=msgs)
            logger.info(f"🧠 Asking {target_model} | Load: {count} tokens")
        except Exception:
            pass

        # Execute with Retry & Key Rotation
        resp_format = {"type": "json_object"} if json_mode else None
        keys_to_try = self.api_keys if self.api_keys else [None]

        for attempt in range(len(keys_to_try) * 2):
            current_key = keys_to_try[attempt % len(keys_to_try)]
            try:
                response = completion(
                    model=target_model,
                    messages=msgs,
                    api_base=api_base,
                    response_format=resp_format,
                    api_key=current_key
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt+1} failed on {target_model}: {e}")
                time.sleep(1)

        raise Exception(f"Polyglot Brain Failed on {target_model} after exhaustion.")

    async def chat(self, system_prompt: str, user_query: str, 
                   history: list = None, image_paths: list = None,
                   context_str: str = None, user_name: str = "User") -> str:
        """
        LangChain-based conversational chat with multimodal support.
        Extracted from GaiaBrain.chat_with_langchain().
        
        Args:
            system_prompt: Full system prompt including persona + context
            user_query: The user's query
            history: List of recent conversation history strings
            image_paths: List of image file paths for multimodal input
            context_str: Pre-fetched RAG context (optional, for injection)
            user_name: User display name
            
        Returns:
            String response from LLM
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        try:
            from langchain_litellm import ChatLiteLLM
        except ImportError:
            from langchain_community.chat_models import ChatLiteLLM

        history = history or []
        image_paths = image_paths or []

        try:
            llm = ChatLiteLLM(
                model=self.model,
                api_key=self.primary_key,
                verbose=True
            )

            # Build the final system prompt with history/context deduplication
            history_str = "\n".join(history) if history else "No history."
            final_system_prompt = system_prompt

            # [DEDUPLICATION] Recognizes both English and Indonesian labels
            has_history_block = any(marker in system_prompt for marker in [
                "[CONVERSATION HISTORY]",
                "[HISTORI PERCAKAPAN SINGKAT]",
                "**Short-term Memory:**",
                "{history}"
            ])
            has_context_block = any(marker in system_prompt for marker in [
                "[MEMORY CONTEXT]",
                "[ALIRAN MEMORI / DATA SEKTOR]",
                "**Sector Data / Memory Hits:**",
                "{context}"
            ])

            if not has_history_block:
                if not has_context_block and context_str:
                    final_system_prompt = (
                        f"{system_prompt}\n\n[CONVERSATION HISTORY]:\n{history_str}\n\n"
                        f"[MEMORY CONTEXT]:\n{context_str}\n\n[USER]: {user_name}"
                    )
                else:
                    final_system_prompt = (
                        f"{system_prompt}\n\n[CONVERSATION HISTORY]:\n{history_str}\n\n[USER]: {user_name}"
                    )

            # Debug logging
            ctx_len = len(context_str) if context_str else 0
            logger.info(f"🧠 [BRAIN] Injecting {ctx_len} chars of context and {len(history_str)} chars of history.")
            if context_str:
                logger.info(f"🔍 [DEBUG] Context Preview: {context_str[:100]}...")

            messages = [SystemMessage(content=final_system_prompt)]

            if image_paths:
                # Multimodal User Message
                content_parts = [{"type": "text", "text": user_query}]
                for img_path in image_paths:
                    try:
                        with open(img_path, "rb") as image_file:
                            image_data = base64.b64encode(image_file.read()).decode("utf-8")
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                            })
                    except Exception as e:
                        logger.error(f"❌ Failed to attach image {img_path}: {e}")
                messages.append(HumanMessage(content=content_parts))
            else:
                messages.append(HumanMessage(content=user_query))

            # Invoke LLM
            logger.info(f"🧠 [LLM] Gaia Brain Ignition using {self.model}...")
            start_time = time.time()
            response = await llm.ainvoke(messages)
            duration = time.time() - start_time
            logger.info(f"💡 [LLM] Response generated in {duration:.2f}s")
            return response.content

        except Exception as e:
            logger.error(f"❌ LangChain Chat Error: {e}")
            return f"⚠️ Brain Stutter: {e}"

    def chat_with_tools(self, messages: list, tools: list = None) -> dict:
        """
        LLM completion with native function calling support.
        Uses litellm.completion() directly (not LangChain) for tool_calls support.
        
        Args:
            messages: List of message dicts (OpenAI format: role + content)
            tools: List of tool schemas (OpenAI function calling format)
            
        Returns:
            Raw response message dict with potential tool_calls
        """
        from litellm import completion

        kwargs = {
            "model": self.model,
            "messages": messages,
            "api_key": self.primary_key,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Cap output tokens to prevent context overflow on large inputs
        kwargs["max_tokens"] = 4096

        # Ollama routing
        if "ollama" in self.model or "local" in self.model:
            kwargs["api_base"] = self.ollama_url

        keys_to_try = self.api_keys if self.api_keys else [None]

        for attempt in range(len(keys_to_try) * 2):
            current_key = keys_to_try[attempt % len(keys_to_try)]
            kwargs["api_key"] = current_key
            try:
                logger.info(f"🧠 [LLM+TOOLS] Calling {self.model} (attempt {attempt+1})...")
                response = completion(**kwargs, timeout=90)
                return response.choices[0].message
            except Exception as e:
                logger.warning(f"⚠️ chat_with_tools attempt {attempt+1} failed: {e}")
                import time
                time.sleep(1)

        # Fallback: return a message with no tool calls
        logger.error(f"❌ chat_with_tools exhausted all retries on {self.model}")
        class FallbackMessage:
            content = "⚠️ Maaf, terjadi gangguan pada sistem AI. Silakan coba lagi."
            tool_calls = None
            role = "assistant"
        return FallbackMessage()

