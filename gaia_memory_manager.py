import chromadb
import os
import logging
import hashlib
import datetime
import uuid
import json
import time
import concurrent.futures
from collections import OrderedDict
from dotenv import load_dotenv

from collections import OrderedDict
from dotenv import load_dotenv

# Load Root .env explicitly
root_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(root_env_path)

# Logging setup (English standard)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GaiaBrain")
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

class GaiaBrain:
    class MemoryAnalytics:
        """Tracks memory usage statistics and performance metrics."""
        def __init__(self):
            self.total_memories = 0
            self.queries_processed = 0
            self.total_retrieval_time = 0.0
            self.cache_hits = 0
            self.cache_misses = 0
            self.memories_by_source = {}
            self.memories_by_tag = {}
            self.start_time = datetime.datetime.now()
        
        def to_dict(self):
            avg_time = self.total_retrieval_time / max(self.queries_processed, 1)
            total_cache_queries = self.cache_hits + self.cache_misses
            hit_ratio = self.cache_hits / max(total_cache_queries, 1) * 100
            
            return {
                "total_memories": self.total_memories,
                "queries_processed": self.queries_processed,
                "average_retrieval_time_ms": round(avg_time * 1000, 2),
                "cache_hit_ratio_percent": round(hit_ratio, 2),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "memories_by_source": self.memories_by_source,
                "memories_by_tag": self.memories_by_tag,
                "uptime_hours": round((datetime.datetime.now() - self.start_time).total_seconds() / 3600, 2)
            }
    
    def __init__(self):
        # --- [AUTO-GENESIS PROTOCOL] ---
        # 1. Determine Identity & Path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Paths to check
        # A. Central Memory (Relative to this file)
        central_memory_path = os.path.join(current_dir, "memory_core")
        
        # B. Local Fallback (Relative to Execution CWD - e.g. for submodules)
        local_memory_path = os.path.join(os.getcwd(), "memory_core")
        
        # Decision Logic
        
        # [FORCE CENTRALIZATION]
        # Always use the memory_core adjacent to this script (Root), regardless of CWD.
        # This prevents "Split Brain" where submodules (Apollo) create their own ./memory_core
        self.db_path = central_memory_path
        self.mode = "INTEGRATED (Root)"

        # Auto-Create
        if not os.path.exists(self.db_path):
            try:
                os.makedirs(self.db_path, exist_ok=True)
                logger.info(f"[GENESIS] ✨ Created Memory Core at: {self.db_path}")
            except Exception as e:
                logger.critical(f"[CRITICAL] ❌ Failed to create memory directory: {e}")
                self.vectorstore = None
                return
        
        # --- [MEMORY MANAGEMENT ENHANCEMENTS] ---
        # Initialize analytics tracking
        self.analytics = self.MemoryAnalytics()
        
        # Memory cache (LRU-like using OrderedDict)
        self.memory_cache = OrderedDict()
        self.cache_max_size = 100
        self.cache_ttl_seconds = 300  # 5 minutes
        
        # Session management
        self.sessions_file = os.path.join(self.db_path, "sessions.json")
        self.active_sessions = {}
        self.user_active_sessions = {}  # Maps user_id -> session_id
        self._load_sessions()
        
        # Load configuration
        self.config = self._load_config()
        
        # Context window settings
        self.default_max_tokens = self.config.get("context_windows", {}).get("default_max_tokens", 4000)
        self.default_max_chars = self.config.get("context_windows", {}).get("default_max_chars", 15000)
        
        # Auto-cleanup settings
        self.auto_cleanup_enabled = self.config.get("cleanup_config", {}).get("auto_cleanup_enabled", False)
        self.max_memory_age_days = self.config.get("cleanup_config", {}).get("max_memory_age_days", 90)

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
                collection_name="knowledge_base"
            )
            
            # Expose raw collection for low-level ops (like ID checks)
            self.collection = self.vectorstore._collection
            
            # Count existing memories for analytics
            try:
                existing_count = self.collection.count()
                self.analytics.total_memories = existing_count
                logger.info(f"📊 Loaded {existing_count} existing memories from database")
            except:
                pass
            
            logger.info(f"🧠 Neural Link Established [{self.mode}]. Connected to: {self.db_path}")
            
        except Exception as e:
            logger.error(f"❌ Brain Damage (DB Init Failed): {e}")
            self.vectorstore = None


    def _load_config(self):
        """Load configuration from intent_config.json."""
        try:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intent_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Failed to load intent_config.json: {e}")
        return {}
    
    def _estimate_tokens(self, text):
        """Rough token estimation (4 chars ≈ 1 token for English/Indonesian)."""
        return len(text) // 4
    
    def _fit_to_window(self, text, max_tokens=None, max_chars=None):
        """Truncate text to fit within context window limits."""
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + "\n... [CONTEXT TRUNCATED]"
        
        if max_tokens:
            estimated_tokens = self._estimate_tokens(text)
            if estimated_tokens > max_tokens:
                # Truncate to approximate token limit
                target_chars = max_tokens * 4
                text = text[:target_chars] + "\n... [CONTEXT TRUNCATED]"
        
        return text
    
    def _get_cache_key(self, query, filter_type, n_results, session_id=None, user_id=None):
        """Generate cache key for query with normalization."""
        q = query.strip().lower()
        f = str(filter_type).strip().lower() if filter_type else "none"
        s = str(session_id) if session_id else "global"
        u = str(user_id) if user_id else "any"
        
        # Create a stable key
        key_str = f"{q}|{f}|{n_results}|{s}|{u}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cached(self, cache_key):
        """Retrieve cached result if valid."""
        if cache_key in self.memory_cache:
            cached_data, timestamp = self.memory_cache[cache_key]
            
            # [OPTIMIZATION] Extended TTL for global queries
            ttl = 3600 if "global" in cache_key else self.cache_ttl_seconds
            
            # Check TTL
            if time.time() - timestamp < ttl:
                # Move to end (LRU)
                self.memory_cache.move_to_end(cache_key)
                self.analytics.cache_hits += 1
                logger.info(f"✅ [CACHE HIT] Using cached memory retrieval (Key: {cache_key})")
                return cached_data
            else:
                # Expired, remove
                del self.memory_cache[cache_key]
        
        self.analytics.cache_misses += 1
        return None
    
    def _cache_result(self, cache_key, result):
        """Store result in cache with LRU eviction."""
        self.memory_cache[cache_key] = (result, time.time())
        
        # LRU eviction if over limit
        if len(self.memory_cache) > self.cache_max_size:
            self.memory_cache.popitem(last=False)  # Remove oldest
    
    def create_session(self, user_id=None, user_name=None):
        """Create a new memory session for isolated context."""
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        self.active_sessions[session_id] = {
            "user_id": user_id,
            "user_name": user_name,  # [FIX] Store user name for display
            "created_at": datetime.datetime.now().isoformat(),
            "last_accessed": datetime.datetime.now().isoformat()
        }
        logger.info(f"📝 Created session: {session_id}")
        self._save_sessions()
        return session_id
    
    def cleanup_session(self, session_id):
        """Remove session and optionally its memories."""
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
            # Clear active session
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
            with open(self.sessions_file, "w") as f:
                json.dump(session_data, f, indent=4)
        except Exception as e:
            logger.error(f"⚠️ Failed to save sessions: {e}")

    def _load_sessions(self):
        """Load active sessions from disk."""
        try:
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, "r") as f:
                    session_data = json.load(f)
                    self.active_sessions = session_data.get("active_sessions", {})
                    self.user_active_sessions = session_data.get("user_active_sessions", {})
                    logger.info(f"💾 Loaded {len(self.active_sessions)} sessions from disk")
        except Exception as e:
            logger.error(f"⚠️ Failed to load sessions: {e}")

    def get_recent_session_history(self, session_id, n=5):
        """
        Retrieves the last n turns for a specific session.
        Focuses on 'user_interaction' source and labels turns for the LLM.
        """
        if not self.vectorstore or not session_id: return []
        
        try:
            # Query for documents with session_id
            results = self.collection.get(
                where={"session_id": session_id},
                include=["documents", "metadatas"]
            )
            
            if not results or not results['ids']: return []
            
            # Combine documents and metadatas, then sort by timestamp
            history_items = []
            for i in range(len(results['ids'])):
                metadata = results['metadatas'][i]
                doc_text = results['documents'][i]
                tags = str(metadata.get('tags', ''))
                
                # Identify sender
                role = "User"
                if "ai_response" in tags or metadata.get('user_name') == 'Gaia':
                    role = "Gaia"
                
                # Cleanup text: remove prefix if present
                clean_text = doc_text
                if f"GAIA to" in doc_text and ":" in doc_text:
                    clean_text = doc_text.split(":", 1)[1].strip()
                
                history_items.append({
                    "role": role,
                    "text": clean_text,
                    "timestamp": metadata.get('timestamp', '')
                })
            
            # Sort by timestamp (chronological)
            history_items.sort(key=lambda x: x['timestamp'])
            
            # Take the last N items and format as a dialogue string
            recent_items = history_items[-n:]
            formatted_history = [f"{item['role']}: {item['text']}" for item in recent_items]
            return formatted_history
            
        except Exception as e:
            logger.error(f"⚠️ Failed to fetch session history: {e}")
            return []

    def remember(self, query, n_results=5, filter_type=None, session_id=None, user_id=None, max_tokens=None, max_chars=None, use_cache=True):
        """
        Retrieves relevant context using LangChain Similarity Search.
        
        Enhanced with:
        - Caching for performance
        - Session-based filtering
        - User-based cross-session retrieval
        - Context window control
        - Semantic boosting
        - Priority-based ranking
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Skipping retrieval.")
            return ""
        
        start_time = time.time()
        
        # Check cache first
        if use_cache:
            cache_key = self._get_cache_key(query, filter_type, n_results, session_id, user_id)
            cached = self._get_cached(cache_key)
            if cached is not None:
                logger.info(f"✅ Cache HIT for key: {cache_key}")
                return cached
            else:
                logger.info(f"❌ Cache MISS for key: {cache_key}")

        try:
            logger.info(f"🔍 Recall triggered: '{query}' (Filter: {filter_type}, Session: {session_id}, User: {user_id})")
            
            # Apply semantic boosting if filter_type is specified
            boosted_query = query
            if filter_type:
                semantic_boosts = self.config.get("semantic_boosts", {})
                # Extract primary entity from filter_type (e.g., "demeter, apollo" -> "demeter")
                primary_entity = filter_type.split(",")[0].strip()
                
                if primary_entity in semantic_boosts:
                    boost_keywords = semantic_boosts[primary_entity]
                    boosted_query = f"{query} {boost_keywords}"
                    logger.info(f"🚀 [SEMANTIC BOOST] Enhanced query with: {boost_keywords[:50]}...")
            
            # Search kwargs for filtering if supported by Chroma/LangChain
            # Chroma supports 'filter' kwarg in similarity_search
            search_kwargs = {}
            
            # Session filtering (if session_id provided, add to filter)
            if session_id:
                # We'll need to filter manually since Chroma metadata filtering is limited
                pass
 
            # Perform Balanced Multi-Domain Search if multiple positive filters exist
            positive_filters = [k.strip() for k in filter_type.split(",") if k.strip() and not k.strip().startswith("-")] if filter_type else []
            
            if len(positive_filters) > 1:
                logger.info(f"🌐 [MULTI-DOMAIN] Parallel retrieval for: {positive_filters}")
                all_raw_docs = []
                # Fetch enough results per domain to ensure representation
                k_per_domain = max(5, n_results // len(positive_filters) + 2)
                
                def search_domain(domain):
                    """Search using raw collection API + Python-side tag filtering."""
                    t_start = time.time()
                    domain_boost = self.config.get("semantic_boosts", {}).get(domain, "")
                    d_query = f"{query} {domain_boost}" if domain_boost else query
                    try:
                        # Fetch a large batch from vectorstore, then filter by tag in Python
                        # This ensures domain-specific data isn't drowned by unrelated docs
                        fetch_k = k_per_domain * 10  # Over-fetch to compensate for filtering
                        
                        # Embed query first (raw collection has no embedding function)
                        query_embedding = self.embedding_function.embed_query(d_query)
                        raw_results = self.collection.query(
                            query_embeddings=[query_embedding],
                            n_results=min(fetch_k, 100),  # Cap at 100 to avoid excessive load
                            include=["documents", "metadatas"]
                        )
                        
                        from langchain_core.documents import Document
                        filtered_docs = []
                        if raw_results and raw_results['ids'] and raw_results['ids'][0]:
                            for i in range(len(raw_results['ids'][0])):
                                meta = raw_results['metadatas'][0][i]
                                tags = str(meta.get('tags', '')).lower()
                                source = str(meta.get('source', '')).lower()
                                # Check if this doc belongs to the current domain
                                if domain in tags or domain in source:
                                    filtered_docs.append(Document(
                                        page_content=raw_results['documents'][0][i],
                                        metadata=meta
                                    ))
                                    if len(filtered_docs) >= k_per_domain * 3:
                                        break
                        
                        logger.info(f"🔎 Domain '{domain}': {len(filtered_docs)} results ({round((time.time()-t_start)*1000, 2)}ms)")
                        return filtered_docs
                    except Exception as e:
                        logger.error(f"❌ Domain '{domain}' search failed: {e}")
                        return []

                # [OPTIMIZATION] Parallel execution to reduce latency
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    results = executor.map(search_domain, positive_filters)
                    for res in results:
                        all_raw_docs.extend(res)
                
                docs = all_raw_docs
            else:
                # Perform Standard Single-Query Search
                # We fetch a bit more to filter manually if needed
                k_fetch = n_results * 5 if filter_type else n_results
                t0 = time.time()
                docs = self.vectorstore.similarity_search(boosted_query, k=k_fetch, **search_kwargs)
                t1 = time.time()
                logger.info(f"⏱️ Vectorstore Search Time: {round((t1-t0)*1000, 2)}ms")
            
            if not docs:
                self.analytics.queries_processed += 1
                self.analytics.total_retrieval_time += time.time() - start_time
                return ""
            
            # Format output with priority-based ranking
            final_docs = []
            for doc in docs:
                # Check Filter Manually (Python side)
                metadata = doc.metadata
                
                # Session & User filter
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
                
                # Type filter
                if filter_type:
                    tags = str(metadata.get('tags', '')).lower()
                    source = str(metadata.get('source', '')).lower()
                    keys = filter_type.lower().split(",")
                    
                    # Logic: Must match at least one POSITIVE key, and NO NEGATIVE keys.
                    has_positive_match = False
                    has_negative_match = False
                    
                    for k in keys:
                        k = k.strip()
                        if not k: continue
                        
                        # Negative Filter (Exclude)
                        if k.startswith("-"):
                            clean_k = k[1:]
                            if clean_k and (clean_k in tags or clean_k in source):
                                has_negative_match = True
                                break
                        # Positive Filter (Include)
                        else:
                            if k in tags or k in source:
                                has_positive_match = True
                    
                    # If we found a negative match, skip doc
                    if has_negative_match: continue
                    
                    # If we have positive keys but found no match, skip doc
                    # (If filter_type only had negatives, we assume "Match All except negatives")
                    has_positive_keys = any(not k.strip().startswith("-") for k in keys if k.strip())
                    if has_positive_keys and not has_positive_match:
                        continue

                # Calculate relevance score (priority + recency)
                priority = metadata.get('priority', 5)  # Default priority: 5
                timestamp_str = metadata.get('timestamp', '')
                
                # Simple recency scoring (newer = higher score)
                recency_score = 0
                if timestamp_str:
                    try:
                        mem_time = datetime.datetime.fromisoformat(timestamp_str)
                        age_hours = (datetime.datetime.now() - mem_time).total_seconds() / 3600
                        # Decay over 3 days (72 hours) for chat recency
                        recency_score = max(0, 10 - (age_hours / 72))  # 0-10 scale
                    except:
                        pass
                
                # [TIMELESS MEMORY] Boost Score for Books/Knowledge
                # Force max recency for technical knowledge so it doesn't decay
                is_timeless = False
                timeless_tags = ['book', 'technical_knowledge', 'manual']
                for t_tag in timeless_tags:
                    if t_tag in str(metadata.get('tags', '')):
                        is_timeless = True
                        break
                
                if is_timeless:
                    recency_score = 10  # Treat as "Just Happened"
                    priority += 2       # Bonus Priority Boost
                
                # Combined relevance
                combined_score = priority + recency_score
                
                # Get clean source for label
                src_label = str(metadata.get('source', 'unknown')).upper()
                
                final_docs.append({
                    "content": f"[S:{src_label}] [P:{priority}] [T:{metadata.get('timestamp', '?')[:19]}] {doc.page_content}",
                    "score": combined_score
                })
                
                if len(final_docs) >= n_results:
                    break
            
            # Sort by combined score (descending)
            final_docs.sort(key=lambda x: x['score'], reverse=True)
            
            # Extract content
            knowledge_text = "\n".join([f"- {d['content']}" for d in final_docs])
            
            # Apply context window limits
            max_tokens = max_tokens or self.default_max_tokens
            max_chars = max_chars or self.default_max_chars
            knowledge_text = self._fit_to_window(knowledge_text, max_tokens, max_chars)
            
            # Update analytics
            elapsed = time.time() - start_time
            self.analytics.queries_processed += 1
            self.analytics.total_retrieval_time += elapsed
            
            # Cache result
            if use_cache:
                self._cache_result(cache_key, knowledge_text)
            
            return knowledge_text
            
        except Exception as e:
            logger.error(f"⚠️ Amnesia (Recall Failed): {e}")
            self.analytics.queries_processed += 1
            self.analytics.total_retrieval_time += time.time() - start_time
            return ""


    def record(self, text, user_name="System", tags="general", source="user_interaction", session_id=None, user_id=None, priority=None, embeddings=None, ids=None):
        """
        Saves a memory to the database (Active Memory) using LangChain.
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Cannot record.")
            return False

        try:
            # Determine Priority from config if not provided
            if priority is None:
                priorities = self.config.get("memory_priorities", {})
                priority = priorities.get(source, priorities.get("general", 5))

            # Metadata Construction
            metadata = {
                "source": str(source),
                "author": str(user_name),
                "tags": str(tags),
                "priority": int(priority),
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # [SESSION & USER SUPPORT] 
            if session_id:
                metadata["session_id"] = str(session_id)
            if user_id:
                metadata["user_id"] = str(user_id)
            
            # [STABLE ID SUPPORT] Use provided ID if available
            doc_id = ids if ids else hashlib.md5(f"{source}_{text}".encode("utf-8")).hexdigest()

            # [COST SAVER] Check existence first
            existing = self.collection.get(ids=[doc_id])
            if existing and existing['ids']:
                logger.debug(f"♻️ Duplicate ignored: {source} (ID: {doc_id})")
                return True

            if embeddings:
                # Direct collection add to reuse pre-computed embeddings
                # Ensure embeddings is a list of lists if passed as a single vector
                vector = embeddings if isinstance(embeddings[0], (list, float)) else [embeddings]
                if not isinstance(vector[0], list): vector = [vector]
                
                self.collection.add(
                    ids=[doc_id],
                    embeddings=vector,
                    documents=[text],
                    metadatas=[metadata]
                )
                logger.info(f"💾 Memory Recorded with Pre-computed Embedding [{source}] (ID: {doc_id})")
            else:
                self.vectorstore.add_texts(
                    texts=[text],
                    metadatas=[metadata],
                    ids=[doc_id]
                )
            
            # Update Analytics
            self.analytics.total_memories += 1
            source_key = str(source).split('_')[0] if '_' in str(source) else str(source)
            self.analytics.memories_by_source[source_key] = self.analytics.memories_by_source.get(source_key, 0) + 1
            
            for tag in str(tags).split(','):
                t = tag.strip().lower()
                if t:
                    self.analytics.memories_by_tag[t] = self.analytics.memories_by_tag.get(t, 0) + 1

            logger.info(f"💾 Memory Encoded [{source}] [P:{priority}]: {tags}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to record memory: {e}")
            return False

    def record_batch(self, texts, metadatas=None, embeddings=None, ids=None):
        """
        Saves multiple memories in a single batch (Optimized for Harvest).
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Cannot batch record.")
            return False
            
        if not texts: return False

        try:
            # Add default metadata if missing
            transformed_metadatas = []
            priorities = self.config.get("memory_priorities", {})
            timestamp = datetime.datetime.now().isoformat()

            for i, txt in enumerate(texts):
                md = metadatas[i] if metadatas else {}
                src = md.get("source", "batch_import")
                
                # Priority lookup
                if "priority" not in md:
                    md["priority"] = priorities.get(src, priorities.get("general", 5))
                
                md.update({
                    "source": str(src),
                    "author": str(md.get("author", "System")),
                    "tags": str(md.get("tags", "general")),
                    "timestamp": md.get("timestamp", timestamp)
                })
                transformed_metadatas.append(md)

            # Generate Deterministic IDs for Batch
            raw_ids = []
            unique_batch_map = {} 
            
            for i, txt in enumerate(texts):
                # [STABLE ID SUPPORT] Use provided ID or generate deterministic one
                if ids and len(ids) > i:
                    doc_id = ids[i]
                else:
                    src = transformed_metadatas[i].get("source", "batch")
                    unique_string = f"{src}_{txt}"
                    doc_id = hashlib.md5(unique_string.encode("utf-8")).hexdigest()
                
                if doc_id not in unique_batch_map:
                    unique_batch_map[doc_id] = {
                        "text": txt,
                        "metadata": transformed_metadatas[i],
                        "index": i
                    }
                    raw_ids.append(doc_id)

            # [COST SAVER] Filter out existing IDs
            existing = self.collection.get(ids=raw_ids)
            existing_ids = set(existing['ids']) if existing else set()
            
            new_texts, new_metadatas, new_ids, new_embeddings = [], [], [], []
            for doc_id in raw_ids:
                if doc_id not in existing_ids:
                    data = unique_batch_map[doc_id]
                    new_texts.append(data["text"])
                    new_metadatas.append(data["metadata"])
                    new_ids.append(doc_id)
                    if embeddings:
                        new_embeddings.append(embeddings[data["index"]])
            
            if not new_texts:
                logger.info(f"♻️ All {len(texts)} items were duplicates. Zero cost.")
                return True

            if embeddings and new_embeddings:
                self.collection.add(
                    ids=new_ids,
                    embeddings=new_embeddings,
                    documents=new_texts,
                    metadatas=new_metadatas
                )
                logger.info(f"💾 Local Batch Record (Pre-computed): {len(new_texts)} items.")
            else:
                self.vectorstore.add_texts(
                    texts=new_texts,
                    metadatas=new_metadatas,
                    ids=new_ids
                )
                logger.info(f"💾 Local Batch Memory Encoded: {len(new_texts)} items.")
            
            # Update Analytics
            self.analytics.total_memories += len(new_texts)
            for md in new_metadatas:
                src = md.get("source", "unknown")
                source_key = src.split('_')[0] if '_' in src else src
                self.analytics.memories_by_source[source_key] = self.analytics.memories_by_source.get(source_key, 0) + 1
                
                for tag in str(md.get("tags", "")).split(','):
                    t = tag.strip().lower()
                    if t:
                        self.analytics.memories_by_tag[t] = self.analytics.memories_by_tag.get(t, 0) + 1

            logger.info(f"💾 Batch Memory Encoded: {len(new_texts)} new items.")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to batch record memory: {e}")
            return False

    # --- RAG EXPANSION (Minerva 2.0) ---
    def get_embedding_function(self):
        """Returns Custom LiteLLM embedding wrapper for LangChain (Avoids Import Errors)."""
        from langchain_core.embeddings import Embeddings
        # [FIX] Import specific function to avoid top-level Init errors in broken versions
        try:
            from litellm import embedding as litellm_embedding
        except ImportError:
            import litellm
            litellm_embedding = litellm.embedding
        
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
                    response = litellm_embedding(**kwargs)
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
                response = litellm_embedding(**kwargs)
                return response['data'][0]['embedding']

        # [FIX] Simplified API Key Priority (No fallback as requested)
        embedding_model = os.getenv("LLM_EMBEDDING_MODEL", "openrouter/openai/text-embedding-3-small")
        api_key_val = os.getenv("EMBEDDING_API_KEY")
        
        return GaiaLiteLLMEmbeddings(model_name=embedding_model, api_key=api_key_val)

    def ingest_library(self, library_dir="library"):
        """Reads PDFs, chunks them, and stores in ChromaDB local."""
        if not os.path.exists(library_dir): 
            return "Library folder not found."
        
        from langchain_community.document_loaders import PyPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_chroma import Chroma
        
        # [FIX] Load tracking file for deduplication
        tracking_file = os.path.join(library_dir, ".ingested_pdfs.json")
        ingested_pdfs = self._load_tracking(tracking_file)
        
        pdf_files = [f for f in os.listdir(library_dir) if f.endswith(".pdf")]
        
        if not pdf_files: 
            return "⚠️ No PDF files found in library."
        
        # [FIX] Filter out already-ingested PDFs
        new_pdfs = []
        for f in pdf_files:
            filepath = os.path.join(library_dir, f)
            file_hash = self._get_file_hash(filepath)
            
            if file_hash not in ingested_pdfs:
                new_pdfs.append((f, file_hash))
            else:
                logger.info(f"⏩ Skipping already-ingested: {f}")
        
        if not new_pdfs:
            return "✅ All PDFs already ingested. Nothing to do."
        
        logger.info(f"📚 Found {len(new_pdfs)} new books. Starting ingestion...")
        
        docs = []
        for filename, file_hash in new_pdfs:
            try:
                loader = PyPDFLoader(os.path.join(library_dir, filename))
                loaded_docs = loader.load()
                
                # [FIX] Add source metadata for tracking
                for doc in loaded_docs:
                    doc.metadata['source_file'] = filename
                    doc.metadata['file_hash'] = file_hash
                
                docs.extend(loaded_docs)
                logger.info(f"📖 Loaded: {filename}")
            except Exception as e:
                logger.error(f"❌ Failed to load {filename}: {e}")
        
        if not docs: 
            return "❌ No valid documents loaded."

        # [FIX] Improved chunking - larger chunks for better context
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=4000,  # Increased from 1000 for better context
            chunk_overlap=400  # 10% overlap for continuity
        )
        splits = text_splitter.split_documents(docs)
        
        # [FIX] Filter empty chunks
        splits = [s for s in splits if s.page_content.strip()]
        
        # Save to Disk (Sub-directory for RAG to keep separate from main memory)
        rag_db_path = os.path.join(self.db_path, "rag_store")
        
        try:
            # [FIX] Use incremental add instead of replace
            if os.path.exists(rag_db_path):
                # Load existing store and add new docs
                vectorstore = Chroma(
                    persist_directory=rag_db_path,
                    embedding_function=self.get_embedding_function()
                )
                vectorstore.add_documents(splits)
                logger.info(f"📥 Added {len(splits)} chunks to existing RAG store")
            else:
                # Create new store
                vectorstore = Chroma.from_documents(
                    documents=splits,
                    embedding=self.get_embedding_function(),
                    persist_directory=rag_db_path
                )
                logger.info(f"🆕 Created new RAG store with {len(splits)} chunks")
            
            # [FIX] Update tracking file
            for filename, file_hash in new_pdfs:
                ingested_pdfs[file_hash] = {
                    "filename": filename,
                    "ingested_at": datetime.datetime.now().isoformat()
                }
            self._save_tracking(tracking_file, ingested_pdfs)
            
            return f"✅ Ingested {len(splits)} chunks from {len(new_pdfs)} new PDFs into ChromaDB (RAG Store)."
        except Exception as e:
            logger.error(f"❌ Ingestion Error: {e}")
            return f"❌ Ingestion Failed: {e}"
    
    def _get_file_hash(self, filepath):
        """Generate MD5 hash of file content for deduplication."""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"❌ Failed to hash file {filepath}: {e}")
            return None
    
    def _load_tracking(self, tracking_file):
        """Load tracking data from JSON file."""
        if os.path.exists(tracking_file):
            try:
                with open(tracking_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load tracking file: {e}")
                return {}
        return {}
    
    def _save_tracking(self, tracking_file, data):
        """Save tracking data to JSON file."""
        try:
            with open(tracking_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Failed to save tracking file: {e}")

    def get_rag_context(self, query_text):
        """Retrieves relevant book excerpts."""
        rag_db_path = os.path.join(self.db_path, "rag_store")
        if not os.path.exists(rag_db_path): return ""
        
        from langchain_chroma import Chroma
        
        try:
            vectorstore = Chroma(persist_directory=rag_db_path, embedding_function=self.get_embedding_function())
            retriever = vectorstore.as_retriever(search_kwargs={"k": 3}) # Top 3 chunks
            docs = retriever.invoke(query_text)
            
            context = "\n\n".join([f"[BOOK EXCERPT]: {d.page_content}" for d in docs])
            return context
        except Exception as e:
            logger.error(f"⚠️ RAG Retrieval Failed: {e}")
            return ""

    # --- [MEMORY OPTIMIZATION & CLEANUP] ---
    def cleanup_old_memories(self, max_age_days=None):
        """Remove memories older than specified days."""
        if not self.vectorstore:
            return 0
        
        max_age = max_age_days or self.max_memory_age_days
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=max_age)
        
        try:
            # Get all documents
            all_docs = self.collection.get(include=["metadatas"])
            
            if not all_docs or not all_docs['ids']:
                return 0
            
            # Find old IDs
            old_ids = []
            for i, doc_id in enumerate(all_docs['ids']):
                metadata = all_docs['metadatas'][i]
                timestamp_str = metadata.get('timestamp', '')
                
                if timestamp_str:
                    try:
                        mem_time = datetime.datetime.fromisoformat(timestamp_str)
                        if mem_time < cutoff_date:
                            old_ids.append(doc_id)
                    except:
                        pass
            
            # Delete old memories
            if old_ids:
                self.collection.delete(ids=old_ids)
                self.analytics.total_memories -= len(old_ids)
                self.memory_cache.clear()  # Clear cache
                logger.info(f"🗑️ Cleaned up {len(old_ids)} old memories (>{max_age} days)")
                return len(old_ids)
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return 0
    
    def cleanup_low_priority(self, threshold=3):
        """Remove memories below specified priority threshold."""
        if not self.vectorstore:
            return 0
        
        try:
            # Get all documents
            all_docs = self.collection.get(include=["metadatas"])
            
            if not all_docs or not all_docs['ids']:
                return 0
            
            # Find low-priority IDs
            low_priority_ids = []
            for i, doc_id in enumerate(all_docs['ids']):
                metadata = all_docs['metadatas'][i]
                priority = metadata.get('priority', 5)
                
                if priority < threshold:
                    low_priority_ids.append(doc_id)
            
            # Delete low-priority memories
            if low_priority_ids:
                self.collection.delete(ids=low_priority_ids)
                self.analytics.total_memories -= len(low_priority_ids)
                self.memory_cache.clear()  # Clear cache
                logger.info(f"🗑️ Cleaned up {len(low_priority_ids)} low-priority memories (P<{threshold})")
                return len(low_priority_ids)
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Priority cleanup failed: {e}")
            return 0
    
    def get_analytics(self, save_to_file=False):
        """
        Get memory analytics and optionally save to JSON.
        
        Returns dict with:
        - total_memories
        - queries_processed
        - average_retrieval_time_ms
        - cache_hit_ratio_percent
        - memories_by_source
        - memories_by_tag
        - uptime_hours
        """
        analytics_dict = self.analytics.to_dict()
        
        if save_to_file:
            try:
                analytics_path = os.path.join(self.db_path, "memory_analytics.json")
                with open(analytics_path, "w", encoding="utf-8") as f:
                    json.dump(analytics_dict, f, indent=2)
                logger.info(f"📊 Analytics saved to: {analytics_path}")
            except Exception as e:
                logger.error(f"❌ Failed to save analytics: {e}")
        
        return analytics_dict



    async def chat_with_langchain(self, query, system_persona, user_name, history=[], filter_type=None, context_override=None, image_paths=[]):
        """
        [NEW] Gaia Chat Engine powered by LangChain.
        Unifies logic with /analyze but optimized for conversation.
        Supports RAG filtering AND Multimodal Images.
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_core.prompts import ChatPromptTemplate
        import base64
        # [FIX] Deprecation Warning: Use langchain_litellm instead of community
        try:
            from langchain_litellm import ChatLiteLLM
        except ImportError:
            # Fallback for older envs
            from langchain_community.chat_models import ChatLiteLLM
        
        # 1. RAG Retrieval
        # If context is already provided (by MotherGaia), use it. Otherwise, recall.
        if context_override:
            context_str = context_override
            logger.info("⚡ [OPTIMIZATION] Using pre-fetched context. Skipping redundant recall.")
        else:
            context_str = self.remember(query, n_results=5, filter_type=filter_type)
        
        # 2. Setup LLM
        # Use LLM_MODEL from env (likely OpenRouter)
        try:
            llm = ChatLiteLLM(
                model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
                api_key=os.getenv("LLM_API_KEY"),
                verbose=True
            )
            
            # 3. Construct Prompt (Multimodal + History Support)
            # Fetch history if session_id is provided in context or metadata
            history_str = "\n".join(history) if history else "No history."
            
            final_system_prompt = system_persona
            
            # [DEDUPLICATION] Recognizes both English and Indonesian labels
            has_history_block = (
                "[CONVERSATION HISTORY]" in system_persona or 
                "[HISTORI PERCAKAPAN SINGKAT]" in system_persona or
                "**Short-term Memory:**" in system_persona or
                "{history}" in system_persona
            )
            has_context_block = (
                "[MEMORY CONTEXT]" in system_persona or 
                "[ALIRAN MEMORI / DATA SEKTOR]" in system_persona or
                "**Sector Data / Memory Hits:**" in system_persona or
                "{context}" in system_persona
            )

            if not has_history_block:
                 if not has_context_block:
                      final_system_prompt = f"{system_persona}\n\n[CONVERSATION HISTORY]:\n{history_str}\n\n[MEMORY CONTEXT]:\n{context_str}\n\n[USER]: {user_name}"
                 else:
                      final_system_prompt = f"{system_persona}\n\n[CONVERSATION HISTORY]:\n{history_str}\n\n[USER]: {user_name}"
            
            # [DEBUG] Log context injection
            logger.info(f"🧠 [BRAIN] Injecting {len(context_str)} chars of context and {len(history_str)} chars of history.")
            if context_str:
                 # Show first bit of context to verify it's not empty or raw template
                 logger.info(f"🔍 [DEBUG] Context Preview: {context_str[:100]}...")
            messages = [
                SystemMessage(content=final_system_prompt)
            ]
            
            if image_paths:
                # Multimodal User Message
                content_parts = [{"type": "text", "text": query}]
                
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
                # Text-Only User Message
                messages.append(HumanMessage(content=query))
            
            # 4. Invoke
            model_info = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
            logger.info(f"🧠 [LLM] Gaia Brain Ignition using {model_info}...")
            start_time = time.time()
            response = await llm.ainvoke(messages)
            duration = time.time() - start_time
            logger.info(f"💡 [LLM] Response generated in {duration:.2f}s")
            return response.content
            
        except Exception as e:
            logger.error(f"❌ LangChain Chat Error: {e}")
            return f"⚠️ Brain Stutter: {e}"
