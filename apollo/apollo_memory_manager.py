import chromadb
import os
import sys
import logging
import hashlib
import datetime
import uuid
import time
import json
from collections import OrderedDict
from dotenv import load_dotenv
import pytz

# Add parent directory to path to reach gaia_memory_manager.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [STANDARDIZATION] Try to import Gaia Brain for integration
try:
    from gaia_memory_manager import GaiaBrain
    GAIA_BRAIN_AVAILABLE = True
except ImportError:
    GAIA_BRAIN_AVAILABLE = False
    logging.warning("⚠️ Gaia Brain not available. Using standalone mode.")

# Logging Setup (Gaia Standard)
def custom_time(*args):
    utc_dt = datetime.datetime.now(datetime.timezone.utc)
    converted = utc_dt.astimezone(pytz.timezone(os.getenv("TIMEZONE", "Asia/Jakarta")))
    return converted.timetuple()

logging.Formatter.converter = custom_time
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), "apollo.log"), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("Apollo")

# Load .env (Prioritize Local Apollo .env)
local_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

if os.path.exists(local_env):
    load_dotenv(local_env)
    logger.info(f"📁 Loaded Local environment: {local_env}")
elif os.path.exists(root_env):
    load_dotenv(root_env)
    logger.info(f"📁 Loaded Root environment: {root_env}")

# Timezone Setup
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")

class GaiaBrain:
    class MemoryAnalytics:
        """Tracks memory usage statistics and performance metrics."""
        def __init__(self):
            self.total_memories = 0
            self.queries_processed = 0
            self.total_retrieval_time = 0.0
            self.cache_hits = 0
            self.cache_misses = 0
            self.start_time = datetime.datetime.now()
        
        def to_dict(self):
            uptime = (datetime.datetime.now() - self.start_time).total_seconds()
            return {
                'total_memories': self.total_memories,
                'queries_processed': self.queries_processed,
                'avg_retrieval_time_ms': (self.total_retrieval_time * 1000) / max(1, self.queries_processed),
                'cache_hit_ratio': self.cache_hits / max(1, self.cache_hits + self.cache_misses),
                'uptime_hours': round(uptime / 3600, 2)
            }
    def __init__(self):
        # --- [AUTO-GENESIS PROTOCOL] ---
        # 1. Determine Identity & Path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Paths to check
        local_memory_path = os.path.join(current_dir, "apollo_memory_core")
        
        # [SURVIVAL MODE]
        # This manager is ONLY used if Central Brain is missing.
        # Therefore, we MUST use Local Memory to function independently.
        self.db_path = local_memory_path
        self.mode = "STANDALONE (Survival)"

        # Auto-Create
        if not os.path.exists(self.db_path):
            try:
                os.makedirs(self.db_path, exist_ok=True)
                logger.info(f"[GENESIS] ✨ Created Memory Core at: {self.db_path}")
            except Exception as e:
                logger.critical(f"[CRITICAL] ❌ Failed to create memory directory: {e}")
                self.vectorstore = None
                return

        # --- [ANALYTICS & CACHING] ---
        self.analytics = self.MemoryAnalytics()
        self.memory_cache = OrderedDict()
        self.cache_max_size = 100
        self.cache_ttl_seconds = 300  # 5 minutes

        # --- [GAIA BRAIN INTEGRATION] ---
        self.gaia_brain = None
        if GAIA_BRAIN_AVAILABLE:
            try:
                # Add parent dir to path to reach gaia_memory_manager.py
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from gaia_memory_manager import GaiaBrain as CentralGaiaBrain
                self.gaia_brain = CentralGaiaBrain()
                logger.info("✅ Connected to Gaia Brain (Central Memory)")
            except Exception as e:
                logger.error(f"Failed to connect to Gaia Brain: {e}")

        # Load configuration
        self.config = self._load_config()
        self.default_max_tokens = self.config.get("context_windows", {}).get("default_max_tokens", 4000)
        self.default_max_chars = self.config.get("context_windows", {}).get("default_max_chars", 15000)

        # --- [NEURAL CONNECTION via LangChain] ---
        try:
            # Force Disable Telemetry via Env Var
            os.environ["ANONYMIZED_TELEMETRY"] = "False"
            
            # 1. Initialize Embeddings (OpenRouter/LiteLLM)
            self.embedding_function = self.get_embedding_function()
            
            # 2. Initialize Chroma Client Explicitly (More Robust vs Race Conditions)
            self.client = chromadb.PersistentClient(path=self.db_path)
            
            # 3. Initialize Chroma via LangChain (using shared client)
            from langchain_chroma import Chroma
            
            self.vectorstore = Chroma(
                client=self.client,
                embedding_function=self.embedding_function,
                collection_name="apollo_knowledge"
            )
            
            # Expose raw collection for low-level ops (like ID checks)
            self.collection = self.vectorstore._collection
            
            logger.info(f"🧠 Neural Link Established [{self.mode}]. Connected to: {self.db_path}")
            
        except Exception as e:
            logger.error(f"❌ Brain Damage (DB Init Failed): {e}")
            self.vectorstore = None

    def _load_config(self):
        """
        Load configuration from intent_config.json.
        Prioritizes local 'apollo/' directory for standalone mode.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        
        paths = [
            os.path.join(current_dir, "intent_config.json"), # Local
            os.path.join(parent_dir, "intent_config.json")   # Root
        ]
        
        for config_path in paths:
            try:
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        logger.info(f"⚙️ Config loaded from: {config_path}")
                        return config
            except Exception as e:
                logger.warning(f"⚠️ Failed to load config from {config_path}: {e}")
        
        logger.warning("⚠️ No intent_config.json found. Using empty defaults.")
        return {}

    def _estimate_tokens(self, text):
        """Rough token estimation (4 chars ≈ 1 token)."""
        return len(text) // 4

    def _fit_to_window(self, text, max_tokens=None, max_chars=None):
        """Truncate text to fit within context window limits."""
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + "\n... [CONTEXT TRUNCATED]"
        if max_tokens:
            estimated_tokens = self._estimate_tokens(text)
            if estimated_tokens > max_tokens:
                target_chars = max_tokens * 4
                text = text[:target_chars] + "\n... [CONTEXT TRUNCATED]"
        return text

    def _get_cache_key(self, query, filter_type, n_results, user_id=None):
        """Generate cache key for query."""
        key_str = f"{query}|{filter_type}|{n_results}|{user_id}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cached(self, cache_key):
        """Retrieve cached result if valid."""
        if cache_key in self.memory_cache:
            cached_data, timestamp = self.memory_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl_seconds:
                self.memory_cache.move_to_end(cache_key)
                self.analytics.cache_hits += 1
                return cached_data
            else:
                del self.memory_cache[cache_key]
        self.analytics.cache_misses += 1
        return None

    def _cache_result(self, cache_key, result):
        """Store result in cache with LRU eviction."""
        self.memory_cache[cache_key] = (result, time.time())
        if len(self.memory_cache) > self.cache_max_size:
            self.memory_cache.popitem(last=False)

    def remember(self, query, n_results=5, filter_type=None, user_id=None, use_cache=True):
        """
        Retrieves relevant context using LangChain Similarity Search.
        Enhanced with Gaia Standard Semantic Memory:
        - Caching & Context Window Control
        - Semantic Boosting
        - Priority & Recency Weighted Ranking
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Skipping retrieval.")
            return ""

        start_time = time.time()

        # 1. Check Cache
        if use_cache:
            cache_key = self._get_cache_key(query, filter_type, n_results, user_id)
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        try:
            logger.info(f"🔍 Recall triggered: '{query}' (Filter: {filter_type}, User: {user_id})")
            
            # 2. Semantic Boosting (Gaia Pattern)
            boosted_query = query
            if filter_type:
                semantic_boosts = self.config.get("semantic_boosts", {})
                primary_entity = filter_type.split(",")[0].strip()
                if primary_entity in semantic_boosts:
                    boost_keywords = semantic_boosts[primary_entity]
                    boosted_query = f"{query} {boost_keywords}"
                    logger.info(f"🚀 [SEMANTIC BOOST] Enhanced with: {boost_keywords[:50]}...")

            # 3. Perform Search
            # Fetch MORE to allow for ranking/filtering (Widen the net)
            k_fetch = n_results * 20 if filter_type else n_results * 5
            
            # Use similarity_search_with_score to get vector relevance
            scored_docs = self.vectorstore.similarity_search_with_score(boosted_query, k=k_fetch)
            
            if not scored_docs:
                self.analytics.queries_processed += 1
                return ""
            
            # 4. Filter & Rank (Similarity + Category + Priority + Recency)
            final_docs = []
            
            # [RELEVANCE BOOST] Categories to check for matches
            target_categories = []
            if filter_type:
                target_categories = [c.strip().lower() for c in filter_type.split(",")]
            
            # [RECENCY BOOST] Check for time-sensitive keywords
            time_sensitive = any(w in query.lower() for w in ["pagi", "hari ini", "latest", "terbaru", "recent", "now", "skrg"])
            
            for doc, score in scored_docs:
                metadata = doc.metadata
                
                # User Filter (Manual)
                metadata_user = metadata.get('user_id')
                if user_id:
                    # [OPTIMIZATION] Cross-session memory for the same user
                    is_user_match = str(metadata_user) == str(user_id)
                    
                    # If it's a general knowledge (no user_id), always allow
                    is_general = not metadata_user
                    
                    if not (is_user_match or is_general):
                        continue
                # Tag/Source Filter
                if filter_type:
                    tags = str(metadata.get('tags', '')).lower()
                    source = str(metadata.get('source', '')).lower()
                    keys = filter_type.lower().split(",")
                    
                    has_positive_match = False
                    has_negative_match = False
                    
                    for k in keys:
                        k = k.strip()
                        if not k: continue
                        if k.startswith("-"):
                            clean_k = k[1:]
                            if clean_k and (clean_k in tags or clean_k in source):
                                has_negative_match = True; break
                        else:
                            if k in tags or k in source: has_positive_match = True
                    
                    if has_negative_match: continue
                    has_positive_keys = any(not k.strip().startswith("-") for k in keys if k.strip())
                    if has_positive_keys and not has_positive_match: continue

                # Calculate Score (Gaia weighted ranking)
                
                # A. VECTOR SIMILARITY (0 to 40 pts)
                # Chroma distance: 0 is perfect, ~1.2+ is irrelevant.
                # Score = (2 - distance) * 20
                sim_score = max(0, (2 - score) * 20)
                
                # B. CATEGORY MATCH BOOST (+50 pts)
                # If the item tags match ANY of the detected categories
                cat_boost = 0
                item_tags = str(metadata.get('tags', '')).lower()
                for cat in target_categories:
                    if cat != "apollo" and cat in item_tags:
                        cat_boost = 50
                        break
                
                # C. PRIORITY (1 to 10 pts)
                priority = metadata.get('priority', 5)
                
                # D. RECENCY BOOST (0 to 20 pts)
                recency_score = 0
                ts = metadata.get('timestamp', '')
                if ts:
                    try:
                        mem_time = datetime.datetime.fromisoformat(ts)
                        age_h = (datetime.datetime.now() - mem_time).total_seconds() / 3600
                        # [TUNING] Dynamic Recency Curve
                        if age_h < 24:
                            # Super boost for < 24h items (Max 20 pts)
                            recency_score = 20 - (age_h * 0.5) 
                        else:
                            # Standard decay (Max 10 pts)
                            recency_score = max(0, 10 - (age_h / 72)) 
                            
                        # Double recency if query is time sensitive
                        if time_sensitive:
                            recency_score *= 2.0
                            
                    except: pass
                
                combined_score = sim_score + cat_boost + priority + recency_score
                
                # Log top candidates for debugging (if logger level is low)
                if cat_boost > 0 or sim_score > 30:
                    logger.debug(f"[RANK] Match: {doc.page_content[:40]}... | Score: {combined_score:.1f} (Sim: {sim_score:.1f}, Cat: {cat_boost})")

                final_docs.append({
                    "content": f"[{metadata.get('timestamp', '?')[:16]}] {doc.page_content}",
                    "score": combined_score
                })

            # 5. Sort by score and take TOP n_results
            final_docs.sort(key=lambda x: x['score'], reverse=True)
            top_docs = final_docs[:n_results]
            
            knowledge_text = "\n".join([f"- {d['content']}" for d in top_docs])
            
            # Apply Windowing
            knowledge_text = self._fit_to_window(knowledge_text)
            
            # Update Analytics & Cache
            elapsed = time.time() - start_time
            self.analytics.queries_processed += 1
            self.analytics.total_retrieval_time += elapsed
            if use_cache:
                self._cache_result(cache_key, knowledge_text)
            
            return knowledge_text
            
        except Exception as e:
            logger.error(f"⚠️ Amnesia (Recall Failed): {e}")
            return ""

    def record(self, text, user_name="System", tags="general", source="user_interaction", user_id=None, ids=None):
        """
        Saves a memory locally AND cross-posts to Gaia Brain central.
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Cannot record.")
            return False

        try:
            # 1. Standardized Tagging (Always add 'apollo')
            if "apollo" not in tags.lower():
                tags = f"apollo, {tags}" if tags else "apollo"

            metadata = {
                "source": str(source),
                "author": str(user_name),
                "tags": str(tags),
                "priority": 5,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            if user_id:
                metadata["user_id"] = str(user_id)
            
            # [STABLE ID SUPPORT] Use provided ID if available
            doc_id = ids if ids else hashlib.md5(f"{source}_{text}".encode("utf-8")).hexdigest()

            # Local Record
            existing = self.collection.get(ids=[doc_id])
            if not (existing and existing['ids']):
                # Compute embedding once for both local and central
                embedding = self.embedding_function.embed_query(text)
                
                # Local storage using pre-computed embedding
                self.collection.add(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[text],
                    metadatas=[metadata]
                )
                logger.info(f"💾 Local Memory Recorded (Pre-computed) [{source}] (ID: {doc_id})")
                
                # 2. CROSS-POST TO GAIA BRAIN (CENTRAL)
                if self.gaia_brain:
                    try:
                        self.gaia_brain.record(
                            text=text,
                            user_name=user_name,
                            tags=tags,
                            source=f"apollo_{source}",
                            user_id=user_id,
                            embeddings=embedding, # Pass pre-computed vector
                            ids=doc_id # Pass stable ID
                        )
                        logger.info("✨ [MEMORY] Cross-posted to Gaia Brain central (Optimized).")
                    except Exception as ex:
                        logger.warning(f"⚠️ Failed to cross-post to central: {ex}")
            else:
                logger.info(f"♻️ Duplicate ignored locally: {doc_id}")

            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to record memory: {e}")
            return False

    def record_batch(self, texts, metadatas=None, user_id=None, ids=None):
        """
        Saves multiple memories locally AND cross-posts to Gaia Brain central.
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Cannot batch record.")
            return False
            
        if not texts: return False

        try:
            timestamp = datetime.datetime.now().isoformat()
            final_metadatas = []
            
            for i, txt in enumerate(texts):
                md = metadatas[i] if metadatas else {}
                
                # Standardized Tagging
                tags = md.get("tags", "general")
                if "apollo" not in tags.lower():
                    tags = f"apollo, {tags}"
                
                md.update({
                    "source": md.get("source", "batch_import"),
                    "author": md.get("author", "System"),
                    "tags": tags,
                    "priority": md.get("priority", 5),
                    "timestamp": md.get("timestamp", timestamp)
                })
                if user_id:
                    md["user_id"] = str(user_id)
                final_metadatas.append(md)

            # Local Batch Record
            raw_ids = []
            unique_batch_map = {} 
            for i, txt in enumerate(texts):
                # [STABLE ID SUPPORT] Use provided ID or generate deterministic one
                if ids and len(ids) > i:
                    doc_id = ids[i]
                else:
                    src = final_metadatas[i].get("source", "batch")
                    unique_string = f"{src}_{txt}"
                    doc_id = hashlib.md5(unique_string.encode("utf-8")).hexdigest()
                
                if doc_id not in unique_batch_map:
                    unique_batch_map[doc_id] = {"text": txt, "metadata": final_metadatas[i]}
                    raw_ids.append(doc_id)

            existing = self.collection.get(ids=raw_ids)
            existing_ids = set(existing['ids']) if existing else set()
            
            new_texts, new_metadatas, new_ids = [], [], []
            for doc_id in raw_ids:
                if doc_id not in existing_ids:
                    new_texts.append(unique_batch_map[doc_id]["text"])
                    new_metadatas.append(unique_batch_map[doc_id]["metadata"])
                    new_ids.append(doc_id)
            
            if new_texts:
                # Compute embeddings once for batch
                batch_embeddings = self.embedding_function.embed_documents(new_texts)
                
                self.collection.add(
                    ids=new_ids,
                    embeddings=batch_embeddings,
                    documents=new_texts,
                    metadatas=new_metadatas
                )
                logger.info(f"💾 Local Batch Memory Recorded (Pre-computed): {len(new_texts)} items.")

                # 2. CROSS-POST BATCH TO GAIA BRAIN (CENTRAL)
                if self.gaia_brain:
                    try:
                        self.gaia_brain.record_batch(
                            texts=new_texts, 
                            metadatas=new_metadatas,
                            embeddings=batch_embeddings, # Pass pre-computed vectors
                            ids=new_ids # Pass stable IDs
                        )
                        logger.info(f"✨ [MEMORY] Cross-posted {len(new_texts)} items to Gaia Brain central (Optimized).")
                    except Exception as ex:
                        logger.warning(f"⚠️ Failed to cross-post batch to central: {ex}")

            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to batch record memory: {e}")
            return False

    # --- RAG EXPANSION (Minerva 2.0) ---
    def get_embedding_function(self):
        """Returns Custom LiteLLM embedding wrapper for LangChain (Avoids Import Errors)."""
        from langchain_core.embeddings import Embeddings
        import litellm
        
        class GaiaLiteLLMEmbeddings(Embeddings):
            def __init__(self, model_name, api_key=None):
                self.model_name = model_name
                self.api_key = api_key
                self.api_base = os.getenv("EMBEDDING_API_BASE")

            def embed_documents(self, texts):
                # Ensure texts is a list
                if not texts: return []
                
                # Batching Logic (Increased for Paid API)
                batch_size = 2048
                embeddings = []
                encoding_fmt = os.getenv("EMBEDDING_ENCODING_FORMAT")
                
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    # Prepare kwargs, only adding encoding_format if set
                    kwargs = {
                        "model": self.model_name,
                        "input": batch,
                        "api_key": self.api_key,
                        "api_base": self.api_base
                    }
                    if encoding_fmt:
                        kwargs["encoding_format"] = encoding_fmt

                    logger.info(f"✨ [LITELLM] Embedding {len(batch)} documents with {self.model_name}")
                    response = litellm.embedding(**kwargs)
                    embeddings.extend([r['embedding'] for r in response['data']])

                return embeddings
                
            def embed_query(self, text):
                if not text: return []
                encoding_fmt = os.getenv("EMBEDDING_ENCODING_FORMAT")
                
                kwargs = {
                    "model": self.model_name,
                    "input": [text],
                    "api_key": self.api_key,
                    "api_base": self.api_base
                }
                if encoding_fmt:
                    kwargs["encoding_format"] = encoding_fmt
                    
                logger.info(f"✨ [LITELLM] Embedding query with {self.model_name}")
                response = litellm.embedding(**kwargs)
                return response['data'][0]['embedding']

        # [FIX] Simplified API Key Priority (No fallback as requested)
        embedding_model = os.getenv("LLM_EMBEDDING_MODEL", "openrouter/openai/text-embedding-3-small")
        api_key_val = os.getenv("EMBEDDING_API_KEY")
        
        return GaiaLiteLLMEmbeddings(model_name=embedding_model, api_key=api_key_val)

    def ingest_library(self, library_dir="library"):
        """Reads PDFs, chunks them, and stores in ChromaDB local."""
        if not os.path.exists(library_dir): return "Library folder not found."
        
        from langchain_community.document_loaders import PyPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_chroma import Chroma
        
        docs = []
        pdf_files = [f for f in os.listdir(library_dir) if f.endswith(".pdf")]
        
        if not pdf_files: return "⚠️ No PDF files found in library."
        
        logger.info(f"📚 Found {len(pdf_files)} books. Starting ingestion...")
        
        for f in pdf_files:
            try:
                loader = PyPDFLoader(os.path.join(library_dir, f))
                docs.extend(loader.load())
                logger.info(f"📖 Loaded: {f}")
            except Exception as e:
                logger.error(f"❌ Failed to load {f}: {e}")
        
        if not docs: return "❌ No valid documents loaded."

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        
        # Save to Disk (Sub-directory for RAG to keep separate from main memory)
        rag_db_path = os.path.join(self.db_path, "rag_store")
        
        try:
            vectorstore = Chroma.from_documents(
                documents=splits, 
                embedding=self.get_embedding_function(), 
                persist_directory=rag_db_path
            )
            return f"✅ Ingested {len(splits)} chunks into ChromaDB (RAG Store)."
        except Exception as e:
            logger.error(f"❌ Ingestion Error: {e}")
            return f"❌ Ingestion Failed: {e}"

    def get_rag_context(self, query_text):
        """Retrieves relevant book excerpts."""
        rag_db_path = os.path.join(self.db_path, "rag_store")
        if not os.path.exists(rag_db_path): return ""
        
        from langchain_chroma import Chroma
        
        try:
            vectorstore = Chroma(persist_directory=rag_db_path, embedding_function=self.get_embedding_function())
            retriever = vectorstore.as_retriever(search_kwargs={"k": 3}) # Top 3 chunks
            docs = retriever.invoke(query_text)
            
            context = "\\n\\n".join([f"[BOOK EXCERPT]: {d.page_content}" for d in docs])
            return context
        except Exception as e:
            logger.error(f"⚠️ RAG Retrieval Failed: {e}")
            return ""

    async def analyze_stock_with_langchain(self, ticker, image_paths, system_instruction, user_prompt, use_rag=False):
        """
        Main analysis function using LangChain + LiteLLM.
        """
        from langchain_core.messages import HumanMessage
        from langchain_community.chat_models import ChatLiteLLM
        import base64

        context_str = ""
        
        # RAG: Fetch wisdom if enabled
        if use_rag:
            logger.info(f"📚 RAG Enabled. Searching library for: {ticker}...")
            # We query the DB using the system instruction keywords + ticker
            # Or just generic "Accumulation Distribution" concepts if ticker is not in books
            # Better to query concepts using the prompt context
            context_str = self.get_rag_context(f"Wyckoff VSA analysis for {ticker} accumulation distribution")
            if context_str:
                logger.info("✅ RAG Context Found.")
            else:
                logger.info("ℹ️ RAG Context Empty.")
        
        # Prepare Multimodal Message
        message_content = []
        
        # A. Text Prompt
        full_prompt = f"{system_instruction}\\n\\n[LIBRARY CONTEXT]:\\n{context_str}\\n\\n[USER PROMPT]:\\n{user_prompt}"
        message_content.append({"type": "text", "text": full_prompt})
        
        # B. Images
        for img_path in image_paths:
            try:
                with open(img_path, "rb") as image_file:
                    image_data = base64.b64encode(image_file.read()).decode("utf-8")
                    message_content.append({
                        "type": "image_url", 
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    })
            except Exception as e:
                logger.error(f"❌ Failed to attach image {img_path}: {e}")

        # Invoke LiteLLM via LangChain
        # Note: ChatLiteLLM automatically uses 'LLM_MODEL' and 'LLM_API_KEY' from env if not passed
        try:
            chat = ChatLiteLLM(
                model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
                api_key=os.getenv("LLM_API_KEY")
            )
            msg = HumanMessage(content=message_content)
            
            # Async invoke
            response = await chat.ainvoke([msg])
            return response.content
        except Exception as e:
            logger.error(f"❌ LangChain Analysis Error: {e}")
            return f"❌ Analysis Failed: {e}"

    async def chat_with_langchain(self, query, system_persona, user_name, history=[], filter_type=None, user_id=None):
        """
        [NEW] Gaia Chat Engine powered by LangChain.
        Unifies logic with /analyze but optimized for conversation.
        Supports RAG filtering.
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_community.chat_models import ChatLiteLLM
        
        # 1. RAG Retrieval
        context_str = self.remember(query, n_results=10, filter_type=filter_type, user_id=user_id)
        
        # 2. Setup LLM
        # Use LLM_MODEL from env (likely OpenRouter)
        try:
            llm = ChatLiteLLM(
                model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
                api_key=os.getenv("LLM_API_KEY"),
                verbose=True
            )
            
            # 3. Construct Prompt
            # System Persona + Context + History (Todo: History)
            final_system_prompt = f"{system_persona}\n\n[MEMORY CONTEXT]:\n{context_str}\n\n[USER]: {user_name}"
            
            messages = [
                SystemMessage(content=final_system_prompt),
                HumanMessage(content=query)
            ]
            
            # 4. Invoke
            response = await llm.ainvoke(messages)
            return response.content
            
        except Exception as e:
            logger.error(f"❌ LangChain Chat Error: {e}")
            return f"⚠️ Brain Stutter: {e}"
