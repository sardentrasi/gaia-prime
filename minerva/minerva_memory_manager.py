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
    from gaia_memory_manager import GaiaBrain as CentralGaiaBrain
    GAIA_BRAIN_AVAILABLE = True
except ImportError:
    GAIA_BRAIN_AVAILABLE = False
    logging.warning("⚠️ Gaia Brain not available. Using standalone mode.")

# Load Root .env explicitly
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(root_env_path)

# Timezone Setup
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")

# Logging Setup (Gaia Standard)
def custom_time(*args):
    utc_dt = datetime.datetime.now(datetime.timezone.utc)
    converted = utc_dt.astimezone(MY_TZ)
    return converted.timetuple()

logging.Formatter.converter = custom_time
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), "minerva.log"), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("Minerva")

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
        local_memory_path = os.path.join(current_dir, "minerva_memory_core")
        
        # [SURVIVAL MODE]
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

        # Session management
        self.active_sessions = {}
        self.user_active_sessions = {}
        self._load_sessions()

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

        # Load configuration (Prioritizing local intent_config.json if available)
        self.config = self._load_config()
        self.default_max_tokens = self.config.get("context_windows", {}).get("default_max_tokens", 4000)
        self.default_max_chars = self.config.get("context_windows", {}).get("default_max_chars", 15000)

        # --- [FINAL MODE AUDIT] ---
        if self.gaia_brain:
            self.mode = "INTEGRATED (Hybrid)"
        else:
            self.mode = "STANDALONE (Survival)"

        try:
            # Force Disable Telemetry via Env Var
            os.environ["ANONYMIZED_TELEMETRY"] = "False"
            
            # 1. Initialize Embeddings (OpenRouter/LiteLLM)
            self.embedding_function = self.get_embedding_function()
            
            # 2. Initialize Chroma Client Explicitly
            self.client = chromadb.PersistentClient(path=self.db_path)
            
            # 3. Initialize Chroma via LangChain
            from langchain_chroma import Chroma
            
            self.vectorstore = Chroma(
                client=self.client,
                embedding_function=self.embedding_function,
                collection_name="minerva_knowledge"
            )
            
            self.collection = self.vectorstore._collection
            logger.info(f"🧠 Neural Link Established [{self.mode}]. Connected to: {self.db_path}")
            
        except Exception as e:
            logger.error(f"❌ Brain Damage (DB Init Failed): {e}")
            self.vectorstore = None

    def create_session(self, user_id=None, user_name=None):
        """Create a new memory session for isolated context."""
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        self.active_sessions[session_id] = {
            "user_id": user_id,
            "user_name": user_name,
            "created_at": datetime.datetime.now().isoformat(),
            "last_accessed": datetime.datetime.now().isoformat()
        }
        logger.info(f"📝 Created session: {session_id}")
        self._save_sessions()
        return session_id
    
    def cleanup_session(self, session_id):
        """Remove session."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            logger.info(f"🗑️ Cleaned up session: {session_id}")
            self._save_sessions()
            return True
        return False
    
    def get_active_session(self, user_id):
        """Get the currently active session for a user."""
        return self.user_active_sessions.get(str(user_id))
    
    def set_active_session(self, user_id, session_id):
        """Set the active session for a user."""
        if session_id and session_id not in self.active_sessions:
            logger.warning(f"⚠️ Session {session_id} does not exist")
            return False
        
        if session_id:
            self.user_active_sessions[str(user_id)] = session_id
            logger.info(f"✅ Set active session for user {user_id}: {session_id}")
        else:
            if str(user_id) in self.user_active_sessions:
                del self.user_active_sessions[str(user_id)]
                logger.info(f"🔄 Cleared active session for user {user_id}")
        
        self._save_sessions()
        return True

    def _save_sessions(self):
        """Persist active sessions to disk."""
        try:
            session_data = {
                "active_sessions": self.active_sessions,
                "user_active_sessions": self.user_active_sessions
            }
            session_file = os.path.join(self.db_path, "sessions.json")
            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=4)
        except Exception as e:
            logger.error(f"⚠️ Failed to save sessions: {e}")

    def _load_sessions(self):
        """Load active sessions from disk."""
        try:
            session_file = os.path.join(self.db_path, "sessions.json")
            if os.path.exists(session_file):
                with open(session_file, "r") as f:
                    session_data = json.load(f)
                    self.active_sessions = session_data.get("active_sessions", {})
                    self.user_active_sessions = session_data.get("user_active_sessions", {})
                    logger.info(f"💾 Loaded {len(self.active_sessions)} sessions from disk")
        except Exception as e:
            logger.error(f"⚠️ Failed to load sessions: {e}")

    def get_recent_session_history(self, session_id, n=5):
        """
        Retrieves the last n turns for a specific session.
        """
        if not self.vectorstore or not session_id: return []
        
        try:
            results = self.collection.get(
                where={"session_id": session_id},
                include=["documents", "metadatas"]
            )
            
            if not results or not results['ids']: return []
            
            history_items = []
            for i in range(len(results['ids'])):
                metadata = results['metadatas'][i]
                doc_text = results['documents'][i]
                tags = str(metadata.get('tags', ''))
                
                role = "User"
                if "minerva_reply" in tags or "ai_response" in tags or metadata.get('user_name') == 'Minerva':
                    role = "Minerva"
                
                history_items.append({
                    "role": role,
                    "text": doc_text,
                    "timestamp": metadata.get('timestamp', '')
                })
            
            history_items.sort(key=lambda x: x['timestamp'])
            
            recent_items = history_items[-n:]
            formatted_history = [f"{item['role']}: {item['text']}" for item in recent_items]
            return formatted_history
            
        except Exception as e:
            logger.error(f"⚠️ Failed to fetch session history: {e}")
            return []

    def _load_config(self):
        """Load configuration from root intent_config.json."""
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "intent_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Failed to load intent_config.json: {e}")
        return {}

    def _estimate_tokens(self, text):
        return len(text) // 4

    def _fit_to_window(self, text, max_tokens=None, max_chars=None):
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + "\n... [CONTEXT TRUNCATED]"
        if max_tokens:
            estimated_tokens = self._estimate_tokens(text)
            if estimated_tokens > max_tokens:
                target_chars = max_tokens * 4
                text = text[:target_chars] + "\n... [CONTEXT TRUNCATED]"
        return text

    def _get_cache_key(self, query, filter_type, n_results, session_id=None, user_id=None):
        key_str = f"{query}|{filter_type}|{n_results}|{session_id}|{user_id}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cached(self, cache_key):
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
        self.memory_cache[cache_key] = (result, time.time())
        if len(self.memory_cache) > self.cache_max_size:
            self.memory_cache.popitem(last=False)

    def remember(self, query, n_results=5, filter_type=None, session_id=None, user_id=None, use_cache=True):
        """
        Retrieves relevant context using LangChain Similarity Search.
        Enhanced with Gaia Standard Semantic Memory.
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Skipping retrieval.")
            return ""

        start_time = time.time()

        if use_cache:
            cache_key = self._get_cache_key(query, filter_type, n_results, session_id, user_id)
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        try:
            logger.info(f"🔍 Recall triggered: '{query}' (Filter: {filter_type}, Session: {session_id}, User: {user_id})")
            
            boosted_query = query
            if filter_type:
                semantic_boosts = self.config.get("semantic_boosts", {})
                primary_entity = filter_type.split(",")[0].strip()
                if primary_entity in semantic_boosts:
                    boost_keywords = semantic_boosts[primary_entity]
                    boosted_query = f"{query} {boost_keywords}"

            k_fetch = n_results * 5 if filter_type else n_results
            docs = self.vectorstore.similarity_search(boosted_query, k=k_fetch)
            
            if not docs:
                self.analytics.queries_processed += 1
                return ""
            
            final_docs = []
            for doc in docs:
                metadata = doc.metadata
                
                # Session & User Filter (Manual)
                metadata_session = metadata.get('session_id')
                metadata_user = metadata.get('user_id')
                
                if session_id or user_id:
                    # [OPTIMIZATION] Cross-session memory for the same user
                    is_user_match = user_id and str(metadata_user) == str(user_id)
                    is_session_match = session_id and str(metadata_session) == str(session_id)
                    
                    # If it's a general knowledge (no session/user), always allow
                    is_general = not metadata_session and not metadata_user
                    
                    if not (is_session_match or is_user_match or is_general):
                        continue

                if filter_type:
                    tags = str(metadata.get('tags', '')).lower()
                    source = str(metadata.get('source', '')).lower()
                    keys = filter_type.lower().split(",")
                    has_positive_match, has_negative_match = False, False
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

                # --- [HEURISTIC RANKING 2.0] ---
                # 1. Similarity (implicitly from k_fetch selection)
                # 2. Category Match Boost
                category_boost = 0
                if filter_type:
                    categories = filter_type.lower().split(",")
                    tags_low = str(metadata.get('tags', '')).lower()
                    for cat in categories:
                        cat = cat.strip()
                        if cat and (cat in tags_low or cat in source.lower()):
                            category_boost += 50 # High Boost for direct match
                
                # 3. Recency Boost
                priority = metadata.get('priority', 5)
                recency_score = 0
                ts = metadata.get('timestamp', '')
                if ts:
                    try:
                        mem_time = datetime.datetime.fromisoformat(ts)
                        age_h = (datetime.datetime.now() - mem_time).total_seconds() / 3600
                        recency_score = max(0, 10 - (age_h / 72)) # Award up to 10 points for freshness (decay over 3 days)
                    except: pass
                
                # [TIMELESS MEMORY] Boost Score for Books/Knowledge
                is_timeless = False
                timeless_tags = ['book', 'technical_knowledge', 'manual', 'teori', 'theory']
                tags_str = str(metadata.get('tags', ''))
                for t_tag in timeless_tags:
                    if t_tag in tags_str:
                        is_timeless = True
                        break
                
                if is_timeless:
                    recency_score = 10  # Treat as "Just Happened"
                    priority += 5       # Technical Knowledge gets higher priority
                
                combined_score = priority + recency_score + category_boost
                final_docs.append({
                    "content": f"[{ts[:16] if ts else '?'}] {doc.page_content}",
                    "score": combined_score
                })
                if len(final_docs) >= n_results: break

            final_docs.sort(key=lambda x: x['score'], reverse=True)
            knowledge_text = "\n".join([f"- {d['content']}" for d in final_docs])
            knowledge_text = self._fit_to_window(knowledge_text)
            
            elapsed = time.time() - start_time
            self.analytics.queries_processed += 1
            self.analytics.total_retrieval_time += elapsed
            if use_cache:
                self._cache_result(cache_key, knowledge_text)
            
            return knowledge_text
        except Exception as e:
            logger.error(f"⚠️ Amnesia (Recall Failed): {e}")
            return ""

    def record(self, text, user_name="System", tags="general", source="user_interaction", session_id=None, user_id=None):
        """
        Saves a memory locally AND cross-posts to Gaia Brain central.
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Cannot record.")
            return False

        try:
            if "minerva" not in tags.lower():
                tags = f"minerva, {tags}" if tags else "minerva"

            metadata = {
                "source": str(source),
                "author": str(user_name),
                "tags": str(tags),
                "priority": 5,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            if session_id:
                metadata["session_id"] = str(session_id)
            if user_id:
                metadata["user_id"] = str(user_id)
            
            unique_string = f"{source}_{text}"
            doc_id = hashlib.md5(unique_string.encode("utf-8")).hexdigest()

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
                logger.info(f"💾 Local Memory Recorded (Pre-computed) [{source}]: {tags}")
                
                if self.gaia_brain:
                    try:
                        self.gaia_brain.record(
                            text=text, 
                            user_name=user_name, 
                            tags=tags, 
                            source=f"minerva_{source}", 
                            user_id=user_id,
                            embeddings=embedding # Pass pre-computed vector
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

    def record_batch(self, texts, metadatas=None):
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
                tags = md.get("tags", "general")
                if "minerva" not in tags.lower():
                    tags = f"minerva, {tags}"
                
                md.update({
                    "source": md.get("source", "batch_import"),
                    "author": md.get("author", "System"),
                    "tags": tags,
                    "priority": md.get("priority", 5),
                    "timestamp": md.get("timestamp", timestamp)
                })
                final_metadatas.append(md)

            raw_ids = []
            unique_batch_map = {} 
            for i, txt in enumerate(texts):
                unique_string = f"{final_metadatas[i]['source']}_{txt}"
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

                if self.gaia_brain:
                    try:
                        # Find indices in the original texts list that were recorded
                        # This ensures metadatas and embeddings align
                        self.gaia_brain.record_batch(
                            texts=new_texts, 
                            metadatas=new_metadatas,
                            embeddings=batch_embeddings # Pass pre-computed vectors
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

        # [OPTIMIZED CHUNKING] for technical/stock analysis books
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=250,  # Increased overlap for technical continuity
            length_function=len,
            separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""]
        )
        splits = text_splitter.split_documents(docs)
        
        # Process Splits with Minerva Metadata
        texts_to_record = []
        metadatas_to_record = []
        
        for split in splits:
            source_file = os.path.basename(split.metadata.get("source", "unknown_book"))
            texts_to_record.append(split.page_content)
            metadatas_to_record.append({
                "source": f"book_{source_file}",
                "author": "Minerva_Library",
                "tags": "minerva, technical_knowledge, book",
                "priority": 8  # Higher priority for technical knowledge
            })

        # Save to Disk (Sub-directory for RAG to keep separate from main memory)
        rag_db_path = os.path.join(self.db_path, "rag_store")
        
        try:
            # 1. Update Legacy Local RAG Store for backward compatibility
            Chroma.from_documents(
                documents=splits, 
                embedding=self.get_embedding_function(), 
                persist_directory=rag_db_path
            )
            
            # 2. Sync with Standard Memory (Local + Central)
            self.record_batch(texts=texts_to_record, metadatas=metadatas_to_record)
            
            return f"✅ Ingested {len(splits)} chunks. Synchronized with Gaia Brain Central."
        except Exception as e:
            logger.error(f"❌ Ingestion Error: {e}")
            return f"❌ Ingestion Failed: {e}"

    def get_rag_context(self, query_text):
        """Retrieves relevant book excerpts from both local RAG store and unified memory."""
        context_parts = []
        
        # 1. Try Main Unified Memory (Synchronized Knowledge)
        try:
            # Query for technical_knowledge chunks
            technical_context = self.remember(query_text, n_results=3, filter_type="technical_knowledge, book")
            if technical_context:
                context_parts.append(f"[TECHNICAL KNOWLEDGE]:\n{technical_context}")
        except Exception as e:
            logger.warning(f"⚠️ Unified Memory RAG lookup failed: {e}")

        # 2. Try Legacy Local RAG Store (Backward Compatibility)
        rag_db_path = os.path.join(self.db_path, "rag_store")
        if os.path.exists(rag_db_path):
            from langchain_chroma import Chroma
            try:
                vectorstore = Chroma(persist_directory=rag_db_path, embedding_function=self.get_embedding_function())
                retriever = vectorstore.as_retriever(search_kwargs={"k": 2}) # Fetch top 2
                docs = retriever.invoke(query_text)
                local_context = "\n\n".join([f"[BOOK EXCERPT]: {d.page_content}" for d in docs])
                if local_context:
                    context_parts.append(local_context)
            except Exception as e:
                logger.error(f"⚠️ Legacy RAG Retrieval Failed: {e}")
        
        if not context_parts:
            return "[NO BOOK DATA] Relying on internal System Persona (brain.md)."
            
        return "\n\n".join(context_parts)

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
            # [FIX] Force Generic Theory Search (Ignore Ticker Name)
            context_str = self.get_rag_context("Wyckoff VSA accumulation distribution analysis theory supply test")
            
            if context_str:
                logger.info("✅ RAG Context Found (Theory Loaded).")
            else:
                # [FIX] Fallback to System Persona if RAG empty
                context_str = "[NO BOOK DATA] Relying on internal System Persona (brain.md)."
                logger.info("⚠️ RAG Context Empty. Using System Persona only.")
        
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

    async def chat_with_langchain(self, query, system_persona, user_name, history=[], filter_type=None, context_override=None, image_paths=None):
        """
        [NEW] Gaia Chat Engine powered by LangChain.
        Unifies logic with /analyze and supports multimodal inputs.
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_community.chat_models import ChatLiteLLM
        import base64
        
        # 1. RAG Retrieval (Use context_override if provided, else fetch from memory)
        context_str = context_override if context_override else self.remember(query, n_results=5, filter_type=filter_type)
        
        # 2. Setup LLM
        try:
            llm = ChatLiteLLM(
                model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
                api_key=os.getenv("LLM_API_KEY")
            )
            
            # 3. Construct Multimodal Prompt
            final_system_prompt = f"{system_persona}\n\n[MEMORY CONTEXT]:\n{context_str}\n\n[USER]: {user_name}"
            
            message_content = [{"type": "text", "text": query}]
            
            if image_paths:
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

            messages = [
                SystemMessage(content=final_system_prompt),
                HumanMessage(content=message_content)
            ]
            
            # 4. Invoke
            response = await llm.ainvoke(messages)
            return response.content
            
        except Exception as e:
            logger.error(f"❌ LangChain Chat Error: {e}")
            return f"⚠️ Brain Stutter: {e}"
    def ask(self, query, plugin_persona, user_name="Trader", context_override=None, filter_type=None, session_id=None, user_id=None, image_paths=None):
        """
        Synchronous RAG chat using LangChain (LiteLLM wrapper).
        Use this for Flask webhooks or sync handlers.
        Supports Multimodal (Images).
        """
        from langchain_community.chat_models import ChatLiteLLM
        from langchain_core.messages import HumanMessage, SystemMessage
        import base64
        import asyncio

        try:
            # 1. RAG Retrieval
            context = context_override if context_override else self.remember(query, n_results=5, filter_type=filter_type, session_id=session_id, user_id=user_id)
            
            # [NEW] Session History Injection
            history_str = ""
            if session_id:
                history_list = self.get_recent_session_history(session_id, n=3)
                if history_list:
                    history_str = "\n[RECENT CONVERSATION]:\n" + "\n".join(history_list)

            # 2. Setup LLM (Sync)
            llm = ChatLiteLLM(
                model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
                api_key=os.getenv("LLM_API_KEY")
            )
            
            # 3. Build Messages
            final_system = f"{plugin_persona}\n\n[RELEVANT CONTEXT]:\n{context}{history_str}"
            
            # Message Content (Text + Optional Images)
            message_content = [{"type": "text", "text": query}]
            
            if image_paths:
                for img_path in image_paths:
                    try:
                        # Handle URL vs Local Path
                        if img_path.startswith("http"):
                             message_content.append({
                                "type": "image_url",
                                "image_url": {"url": img_path}
                            })
                        else:
                            with open(img_path, "rb") as image_file:
                                image_data = base64.b64encode(image_file.read()).decode("utf-8")
                                message_content.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                                })
                    except Exception as e:
                        logger.error(f"❌ Failed to attach image {img_path}: {e}")

            messages = [
                SystemMessage(content=final_system),
                HumanMessage(content=message_content)
            ]
            
            # 4. Generate Response (Sync Invoke)
            logger.info(f"🧠 [Minerva LLM] Invoking LangChain for: {user_name} (Session: {session_id})")
            response = llm.invoke(messages)
            reply = response.content
            
            # 5. Record Interaction
            self.record(query, user_name=user_name, tags="minerva, chat, wa_query, rag", source="minerva_wa_ask", session_id=session_id, user_id=user_id)
            self.record(reply, user_name="Minerva", tags="minerva, chat, wa_reply, rag", source="minerva_wa_ask", session_id=session_id, user_id=user_id)
            
            return reply
            
        except Exception as e:
            logger.error(f"❌ Minerva Brain Ask Error: {e}")
            return "⚠️ Maaf, sistem visual saya sedang gangguan."
            return f"⚠️ Brain offline: {e}"
