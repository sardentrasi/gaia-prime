"""
Eleuthia Memory Manager (Advanced)
Sophisticated LLM-powered email intelligence with ChromaDB vector store.
Matches gaia_memory_manager.py capabilities with email-specific enhancements.
"""

import os
import sys
import logging
import hashlib
import datetime
import uuid
import json
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

# ChromaDB (LangChain is imported locally for robustness)
import chromadb
# from langchain_chroma import Chroma  <-- Removed top-level import

# LiteLLM for embeddings and LLM calls
from litellm import completion, embedding

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [STANDARDIZATION] Try to import Gaia Brain for integration
try:
    from gaia_memory_manager import GaiaBrain
    GAIA_BRAIN_AVAILABLE = True
except ImportError:
    GAIA_BRAIN_AVAILABLE = False
    logging.warning("⚠️ Gaia Brain not available. Using standalone mode.")

from eleuthia.tools.config import LLMConfig, ClassificationConfig
from eleuthia.tools.email_filter import EmailFilter

logger = logging.getLogger("EleuthiaBrain")

class EleuthiaBrain:
    """
    Advanced email intelligence system with Gaia-standard memory core.
    
    Features:
    - ChromaDB vector store with Gaia standards
    - Semantic search with priority/recency ranking
    - Token-aware context window management
    - RAG Library ingestion and retrieval
    - LLM-powered chat and email intelligence
    """
    
    class MemoryAnalytics:
        """Tracks memory usage statistics and performance metrics."""
        def __init__(self):
            self.total_memories = 0
            self.emails_processed = 0
            self.emails_summarized = 0
            self.queries_processed = 0
            self.total_retrieval_time = 0.0
            self.cache_hits = 0
            self.cache_misses = 0
            self.classification_breakdown = {'urgent': 0, 'info': 0, 'spam': 0}
            self.start_time = datetime.datetime.now()
        
        def to_dict(self):
            uptime = (datetime.datetime.now() - self.start_time).total_seconds()
            return {
                'total_memories': self.total_memories,
                'emails_processed': self.emails_processed,
                'emails_summarized': self.emails_summarized,
                'queries_processed': self.queries_processed,
                'avg_retrieval_time_ms': (self.total_retrieval_time * 1000) / max(1, self.queries_processed),
                'cache_hit_ratio': self.cache_hits / max(1, self.cache_hits + self.cache_misses),
                'classification_stats': self.classification_breakdown,
                'uptime_hours': round(uptime / 3600, 2)
            }
    
    def __init__(self):
        """Initialize Eleuthia Brain with vector store and analytics."""
        
        # --- [MEMORY CORE SETUP] ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(current_dir, "eleuthia_memory_core")
        
        # Create memory directory
        if not os.path.exists(self.db_path):
            try:
                os.makedirs(self.db_path, exist_ok=True)
                logger.info(f"[GENESIS] ✨ Created Eleuthia Memory Core at: {self.db_path}")
            except Exception as e:
                logger.critical(f"[CRITICAL] ❌ Failed to create memory directory: {e}")
                self.vectorstore = None
                return
        
        # --- [ANALYTICS & CACHING] ---
        self.analytics = self.MemoryAnalytics()
        
        # LRU cache
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

        # --- [FINAL MODE AUDIT] ---
        if self.gaia_brain:
            self.mode = "INTEGRATED (Hybrid)"
        else:
            self.mode = "STANDALONE (Survival)"
        
        # --- [EMAIL FILTER SETUP] ---
        filter_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools', 'filtermail.json')
        self.email_filter = EmailFilter(filter_path)
        
        # --- [LLM CONFIG] ---
        self.llm_model = LLMConfig.MODEL
        self.llm_api_key = LLMConfig.API_KEY
        self.llm_base_url = LLMConfig.BASE_URL
        
        # Context window settings (Matching Gaia)
        self.default_max_tokens = int(os.getenv("DEFAULT_MAX_TOKENS", 4000))
        self.default_max_chars = int(os.getenv("DEFAULT_MAX_CHARS", 15000))

        # Classification keywords
        self.urgent_keywords = ClassificationConfig.URGENT_KEYWORDS
        self.spam_keywords = ClassificationConfig.SPAM_KEYWORDS
        self.info_keywords = ClassificationConfig.INFO_KEYWORDS
        
        # --- [VECTOR STORE INITIALIZATION] ---
        try:
            # Disable telemetry
            os.environ["ANONYMIZED_TELEMETRY"] = "False"
            
            # Initialize embeddings
            self.embedding_function = self._get_embedding_function()
            
            # Initialize Chroma client
            self.client = chromadb.PersistentClient(path=self.db_path)
            
            # [ROBUSTNESS] Local import for Chroma
            try:
                from langchain_chroma import Chroma
                self.vectorstore = Chroma(
                    client=self.client,
                    embedding_function=self.embedding_function,
                    collection_name="eleuthia_emails"
                )
                self.collection = self.vectorstore._collection
                
                # Count existing memories
                try:
                    existing_count = self.collection.count()
                    self.analytics.total_memories = existing_count
                    logger.info(f"📊 Loaded {existing_count} existing email memories")
                except:
                    pass
                
                logger.info(f"🧠 Eleuthia Neural Link Established. Connected to: {self.db_path}")
            except ImportError:
                logger.warning("⚠️ langchain_chroma not found. Memory features will be limited.")
                self.vectorstore = None
                self.collection = None # We might need to handle this manually with self.client
            
        except Exception as e:
            logger.error(f"❌ Vector Store Init Failed: {e}")
            self.vectorstore = None

    # --- [TOKEN & CONTEXT MANAGEMENT] --- (Gaia Standard)
    def _estimate_tokens(self, text):
        """Rough token estimation (4 chars ≈ 1 token for English/Indonesian)."""
        return len(text) // 4

    def _fit_to_window(self, text, max_tokens=None, max_chars=None):
        """Truncate text to fit within context window limits."""
        limit_tokens = max_tokens or self.default_max_tokens
        limit_chars = max_chars or self.default_max_chars
        
        # Char-based truncation (First line of defense)
        if len(text) > limit_chars:
            text = text[:limit_chars] + "\n...[Content Truncated due to Length]..."
            
        # Token-based truncation (More precise)
        while self._estimate_tokens(text) > limit_tokens and len(text) > 100:
            text = text[:-100]
            
        return text

    # --- [EMBEDDING SYSTEM] --- (Gaia Standard)
    def _get_embedding_function(self):
        """Returns custom LiteLLM embedding wrapper for LangChain (Avoids Import Errors)."""
        from langchain_core.embeddings import Embeddings
        import litellm
        
        class EleuthiaLiteLLMEmbeddings(Embeddings):
            def __init__(self, model_name, api_key=None):
                self.model_name = model_name
                self.api_key = api_key
                self.api_base = os.getenv("EMBEDDING_API_BASE")
                # Local Cache to save tokens/cost
                self._embedding_cache = OrderedDict()
                self._cache_max = 500

            def _get_cache_key(self, text):
                return hashlib.md5(text.encode('utf-8')).hexdigest()

            def embed_documents(self, texts):
                if not texts: return []
                
                results = [None] * len(texts)
                to_embed_indices = []
                to_embed_texts = []
                
                # 1. Check Cache
                for i, text in enumerate(texts):
                    key = self._get_cache_key(text)
                    if key in self._embedding_cache:
                        results[i] = self._embedding_cache[key]
                        self._embedding_cache.move_to_end(key)
                    else:
                        to_embed_indices.append(i)
                        to_embed_texts.append(text)
                
                if not to_embed_texts:
                    return results

                # 2. Embed missing
                batch_size = 2048
                encoding_fmt = os.getenv("EMBEDDING_ENCODING_FORMAT")
                
                for i in range(0, len(to_embed_texts), batch_size):
                    batch = to_embed_texts[i:i + batch_size]
                    indices_batch = to_embed_indices[i:i + batch_size]
                    
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
                    
                    for j, r in enumerate(response['data']):
                        idx = indices_batch[j]
                        vec = r['embedding']
                        results[idx] = vec
                        # Update cache
                        key = self._get_cache_key(batch[j])
                        self._embedding_cache[key] = vec
                        if len(self._embedding_cache) > self._cache_max:
                            self._embedding_cache.popitem(last=False)
                
                return results
                
            def embed_query(self, text):
                if not text: return []
                
                # Check Cache
                key = self._get_cache_key(text)
                if key in self._embedding_cache:
                    logger.info(f"⚡ [CACHE] Reusing embedding for query: {text[:30]}...")
                    self._embedding_cache.move_to_end(key)
                    return self._embedding_cache[key]

                logger.info(f"🔍 [EMBEDDING] Embedding query using {self.model_name}")
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
                vec = response['data'][0]['embedding']
                
                # Update Cache
                self._embedding_cache[key] = vec
                if len(self._embedding_cache) > self._cache_max:
                    self._embedding_cache.popitem(last=False)
                
                return vec

        # Enforced Environment Variables
        # [FIX] Simplified API Key Priority (No fallback as requested)
        embedding_model = os.getenv("LLM_EMBEDDING_MODEL", "openrouter/openai/text-embedding-3-small")
        api_key_val = os.getenv("EMBEDDING_API_KEY")
        
        return EleuthiaLiteLLMEmbeddings(model_name=embedding_model, api_key=api_key_val)
    
    def _get_cache_key(self, query, filter_type, n_results):
        """Generate cache key for query."""
        key_string = f"{query}_{filter_type}_{n_results}"
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    def _get_cached(self, cache_key):
        """Retrieve cached result if valid."""
        if cache_key in self.memory_cache:
            cached_data, timestamp = self.memory_cache[cache_key]
            if (time.time() - timestamp) < self.cache_ttl_seconds:
                self.memory_cache.move_to_end(cache_key)
                self.analytics.cache_hits += 1
                logger.info(f"⚡ Cache hit for key: {cache_key[:8]}...")
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

    # --- [MEMORY RETRIEVAL] --- (Gaia Standard Upgrade)
    def remember(self, query, n_results=5, filter_type=None, max_tokens=None, max_chars=None, use_cache=True, return_vector=False):
        """
        Retrieves relevant context using LangChain Similarity Search.
        Enhanced with: Caching, Semantic Boosting, Priority Ranking, and Recency Scoring.
        """
        if not self.vectorstore:
            logger.warning("⚠️ Memory Core not initialized. Skipping retrieval.")
            return ("", None) if return_vector else ""
        
        start_time = time.time()
        
        # 0. Pre-compute or fetch embedding for query (to be reused)
        query_vec = self.embedding_function.embed_query(query)

        # 1. Cache Check
        cache_key = self._get_cache_key(query, filter_type, n_results)
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached: 
                return (cached, query_vec) if return_vector else cached

        try:
            logger.info(f"🔍 Recall triggered: '{query}' (Filter: {filter_type})")
            
            # 2. Search kwargs for filtering
            search_kwargs = {}
            k_fetch = n_results * 5 if filter_type else n_results
            
            # Perform Semantic Search
            # Use similarity_search_by_vector to reuse our pre-computed query_vec
            docs = self.vectorstore.similarity_search_by_vector(query_vec, k=k_fetch, **search_kwargs)
            
            if not docs:
                self.analytics.queries_processed += 1
                return ("", query_vec) if return_vector else ""
            
            # 3. Priority-based ranking, Recency scoring, and SEMANTIC BOOST
            final_docs = []
            
            # Text-based boosting (naive)
            boost_terms = []
            if getattr(self, 'semantic_boost_terms', None):
                 boost_terms.extend(self.semantic_boost_terms)
            
            # Dynamic boost from query analysis (simple)
            if "urgent" in query.lower(): boost_terms.append("urgent")
            if "password" in query.lower(): boost_terms.append("security")
            
            for doc in docs:
                metadata = doc.metadata
                content = doc.page_content.lower()
                
                # Apply Type Filter Manually
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
                                has_negative_match = True
                                break
                        else:
                            if k in tags or k in source:
                                has_positive_match = True
                    
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
                ts_str = metadata.get('timestamp', '')
                if ts_str:
                    try:
                        mem_time = datetime.datetime.fromisoformat(ts_str)
                        age_h = (datetime.datetime.now() - mem_time).total_seconds() / 3600
                        recency_score = max(0, 10 - (age_h / 72))  # Award up to 10 points for freshness (decay over 3 days)
                    except: pass
                
                # [TIMELESS MEMORY] Boost Score for Books/Knowledge
                is_timeless = False
                timeless_tags = ['email', 'inbox', 'sender', 'message', 'communication', 'guide', 'manual']
                tags_str = str(metadata.get('tags', ''))
                for t_tag in timeless_tags:
                    if t_tag in tags_str:
                        is_timeless = True
                        break
                
                if is_timeless:
                    recency_score = 10  # Treat as "Just Happened"
                    priority += 5       # Knowledge base gets higher priority
                
                combined_score = priority + recency_score + category_boost
                
                final_docs.append({
                    "content": f"[{ts_str[:16]}] [P:{priority}] {doc.page_content}",
                    "score": combined_score
                })
                if len(final_docs) >= n_results: break
            
            # Sort by combined score
            final_docs.sort(key=lambda x: x['score'], reverse=True)
            knowledge_text = "\n".join([f"- {d['content']}" for d in final_docs])
            
            # 4. Fit to window
            knowledge_text = self._fit_to_window(knowledge_text, max_tokens, max_chars)
            
            # 5. Finalize
            self.analytics.queries_processed += 1
            self.analytics.total_retrieval_time += (time.time() - start_time)
            if use_cache: self._cache_result(cache_key, knowledge_text)
            
            return (knowledge_text, query_vec) if return_vector else knowledge_text
        except Exception as e:
            logger.error(f"⚠️ Recall Failed: {e}")
            return ""
    
    # --- [MEMORY STORAGE] --- (Gaia Standard)
    def record(self, text, user_name="System", tags="general", source="user_interaction", embeddings=None):
        """Saves a memory to the database using LangChain."""
        if not self.vectorstore: return False
        try:
            # Ensure 'eleuthia' tag exists so Gaia and other modules can identify the source
            final_tags = tags
            if "eleuthia" not in tags.lower():
                final_tags = f"{tags},eleuthia"
                
            metadata = {
                "source": str(source),
                "author": str(user_name),
                "tags": str(final_tags),
                "timestamp": datetime.datetime.now().isoformat(),
                "priority": 5
            }
            unique_string = f"{source}_{text}"
            doc_id = hashlib.md5(unique_string.encode("utf-8")).hexdigest()

            existing = self.collection.get(ids=[doc_id])
            if not (existing and existing['ids']):
                # Compute embedding once for both local and central (or reuse if provided)
                if embeddings:
                    embedding_vec = embeddings
                    logger.info(f"♻️ [MEMORY] Reusing provided vector for record [{source}]")
                else:
                    logger.debug(f"✨ [EMBEDDING] Encoding new memory for record [{source}]")
                    embedding_vec = self.embedding_function.embed_query(text)
                
                # Local storage using pre-computed embedding
                # Ensure embedding_vec is a list of lists for collection.add
                vector = [embedding_vec] if not isinstance(embedding_vec[0], list) else embedding_vec
                
                self.collection.add(
                    ids=[doc_id],
                    embeddings=vector,
                    documents=[text],
                    metadatas=[metadata]
                )
                self.analytics.total_memories += 1
                logger.info(f"💾 Local Memory Recorded (Pre-computed) [{source}]: {final_tags}")
                
                # Cross-post to Gaia central memory (Optimized)
                if self.gaia_brain:
                    try: 
                        self.gaia_brain.record(
                            text, 
                            user_name=user_name, 
                            tags=final_tags, 
                            source=source,
                            embeddings=embedding_vec # Pass pre-computed vector
                        )
                        logger.info(f"🌐 [CENTRAL] Cross-posted memory to Gaia Brain (Optimized).")
                    except Exception as ge:
                        logger.warning(f"⚠️ Gaia cross-post failed: {ge}")
            else:
                logger.debug(f"♻️ Duplicate ignored: {source}")

            return True
        except Exception as e:
            logger.error(f"❌ Record failed: {e}"); return False

    def record_batch(self, texts, metadatas=None):
        """Saves multiple memories in a single batch (Gaia Standard)."""
        if not self.vectorstore or not texts: return False
        try:
            timestamp = datetime.datetime.now().isoformat()
            final_metadatas = metadatas or [{
                "source": "batch_import", "author": "System", "tags": "general",
                "timestamp": timestamp, "priority": 5
            } for _ in texts]

            raw_ids, unique_batch_map = [], {}
            for i, txt in enumerate(texts):
                doc_id = hashlib.md5(f"{final_metadatas[i].get('source')}_{txt}".encode()).hexdigest()
                if doc_id not in unique_batch_map:
                    unique_batch_map[doc_id] = {"text": txt, "metadata": final_metadatas[i]}
                    raw_ids.append(doc_id)

            existing_ids = set(self.collection.get(ids=raw_ids)['ids'])
            new_texts = [unique_batch_map[rid]['text'] for rid in raw_ids if rid not in existing_ids]
            new_metas = [unique_batch_map[rid]['metadata'] for rid in raw_ids if rid not in existing_ids]
            new_ids = [rid for rid in raw_ids if rid not in existing_ids]
            
            if new_texts:
                # Compute embeddings once for batch
                batch_embeddings = self.embedding_function.embed_documents(new_texts)
                
                self.collection.add(
                    ids=new_ids,
                    embeddings=batch_embeddings,
                    documents=new_texts,
                    metadatas=new_metas
                )
                self.analytics.total_memories += len(new_texts)
                logger.info(f"💾 Local Batch Memory Recorded (Pre-computed): {len(new_texts)} items.")

                if self.gaia_brain:
                    try:
                        self.gaia_brain.record_batch(
                            texts=new_texts, 
                            metadatas=new_metas,
                            embeddings=batch_embeddings # Pass pre-computed vectors
                        )
                        logger.info(f"✨ [MEMORY] Cross-posted {len(new_texts)} items to Gaia Brain central (Optimized).")
                    except Exception as ex:
                        logger.warning(f"⚠️ Failed to cross-post batch to central: {ex}")
            return True
        except Exception as e:
            logger.error(f"❌ Batch Record failed: {e}"); return False

    # --- [EMAIL SPECIFIC INTELLIGENCE] ---
    def classify_email(self, email: Dict) -> str:
        """
        Classify email using STRICT rule-based filtering (filtermail.json).
        Delegates to EmailFilter tool.
        """
        return self.email_filter.classify(email)

    def record_email(self, email: Dict, classification: str, summary: Optional[Dict] = None, embeddings = None):
        """Record email with enriched metadata and cross-post to Gaia."""
        try:
            text = f"From: {email.get('from')}\nSubject: {email.get('subject')}\nClassification: {classification}\nBody: {email.get('body', '')[:500]}"
            if summary:
                text += f"\nSummary: {summary.get('summary')}\nSuggested Reply: {summary.get('suggested_reply')}"

            metadata = {
                'source': 'eleuthia_email',
                'sender': email.get('from', ''),
                'subject': email.get('subject', ''),
                'classification': classification,
                'timestamp': email.get('timestamp', datetime.datetime.now().isoformat()),
                'priority': 9 if classification == 'urgent' else 5,
                'account_name': email.get('account_name', 'unknown'),
                'author': 'Eleuthia',
                'tags': f"email,{classification},{email.get('from', '')},eleuthia"
            }
            
            # Local Store ID
            unique_str = f"email_{email.get('id')}_{metadata['timestamp']}"
            doc_id = hashlib.md5(unique_str.encode()).hexdigest()
            
            # Save to Local Store if unique
            existing = self.collection.get(ids=[doc_id])
            if not (existing and existing['ids']):
                # Compute embedding once (or reuse)
                if embeddings:
                    embedding_vec = embeddings
                    logger.info(f"♻️ [MEMORY] Reusing provided embedding for email [{email.get('subject', '')[:30]}]")
                else:
                    embedding_vec = self.embedding_function.embed_query(text)
                
                # Local storage
                vector = [embedding_vec] if not isinstance(embedding_vec[0], list) else embedding_vec
                self.collection.add(
                    ids=[doc_id],
                    embeddings=vector,
                    documents=[text],
                    metadatas=[metadata]
                )
                self.analytics.total_memories += 1
                self.analytics.emails_processed += 1
                
                # Cross-post to Gaia central memory (Optimized)
                if self.gaia_brain:
                    try: 
                        self.gaia_brain.record(
                            text, 
                            user_name="Eleuthia", 
                            tags=metadata['tags'], 
                            source="eleuthia_email",
                            embeddings=embedding_vec # Pass pre-computed vector
                        )
                        logger.info(f"🌐 [CENTRAL] Email cross-posted to Gaia Brain (Optimized).")
                    except: pass
            else:
                logger.debug(f"♻️ Email duplicate ignored: {email.get('subject', '')[:30]}")
            
            logger.info(f"💾 Email recorded: {email.get('subject', '')[:30]}")
            return True
        except Exception as e:
            logger.error(f"❌ record_email failed: {e}"); return False

    def search_emails(self, query: str, n_results: int = 5, classification_filter: Optional[str] = None):
        """Standard wrapper for remember() to maintain backward compatibility."""
        context = self.remember(query, n_results=n_results, filter_type=classification_filter)
        # Parse into simplified dict format for legacy compatibility
        lines = context.split("- [")[1:] if "- [" in context else []
        results = []
        for line in lines:
            results.append({'content': line.strip(), 'classification': classification_filter or "info"})
        return results
    
    def summarize_email(self, email: Dict, minimal: bool = False) -> Dict[str, str]:
        """Generate summary (STRICT MODE: No LLM, Extractive Only)."""
        body = email.get('body', '')[:2000]
        # STRICT MODE: Force minimal summary (No LLM)
        # User requested to strictly limit LLM usage to only Casual Chat and Reply.
        clean_body = body.replace('\n', ' ').strip()
        summary = f"{clean_body[:250]}..." if len(clean_body) > 250 else clean_body
        self.analytics.emails_summarized += 1
        return {'summary': summary or "(No content)", 'suggested_reply': "Balas manual."}

    def extract_meeting_request(self, email: Dict) -> Optional[Dict]:
        """Extract meeting details if email contains scheduling requests."""
        subject = email.get('subject', '')
        body = email.get('body', '')[:2000]
        
        keywords = ['meeting', 'schedule', 'appointment', 'call', 'zoom', 'teams', 'rapat', 'jadwal', 'pertemuan']
        if not any(kw in subject.lower() or kw in body.lower() for kw in keywords):
            return None
        
        return None
        # STRICT MODE: Disabled LLM extraction
        # try:
        #     prompt = f"Analyze if this email is a meeting request..."
        #     ...
        # except Exception as e:
        #     logger.error(f"Meeting extraction failed: {e}"); return None

    # --- [RAG LIBRARY & CHAT] --- (Gaia/Minerva Standard)
    def ingest_library(self, library_dir="library"):
        """Ingest PDFs from a directory into a specialized RAG store."""
        if not os.path.exists(library_dir): return "Library folder not found."
        
        from langchain_community.document_loaders import PyPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        
        tracking_file = os.path.join(library_dir, ".ingested_pdfs.json")
        ingested = self._load_tracking(tracking_file)
        
        pdf_files = [f for f in os.listdir(library_dir) if f.endswith(".pdf")]
        new_pdfs = [f for f in pdf_files if self._get_file_hash(os.path.join(library_dir, f)) not in ingested]
        
        if not new_pdfs: return "✅ All PDFs already ingested."
        
        docs = []
        for f in new_pdfs:
            try:
                path = os.path.join(library_dir, f)
                loader = PyPDFLoader(path)
                loaded = loader.load()
                for d in loaded: d.metadata['source'] = f
                docs.extend(loaded)
            except: logger.error(f"Failed to load {f}")
            
        if not docs: return "❌ No valid documents loaded."
        
        splits = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=400).split_documents(docs)
        rag_db_path = os.path.join(self.db_path, "rag_store")
        
        try:
            vectorstore = Chroma.from_documents(
                documents=splits, 
                embedding=self.embedding_function, 
                persist_directory=rag_db_path
            )
            # Update tracking
            for f in new_pdfs:
                ingested[self._get_file_hash(os.path.join(library_dir, f))] = f
            self._save_tracking(tracking_file, ingested)
            return f"✅ Ingested {len(splits)} chunks from {len(new_pdfs)} PDFs."
        except Exception as e:
            return f"❌ Ingestion Failed: {e}"

    def get_rag_context(self, query):
        """Retrieves technical context from book/PDF library."""
        rag_db_path = os.path.join(self.db_path, "rag_store")
        if not os.path.exists(rag_db_path): return ""
        try:
            vectorstore = Chroma(persist_directory=rag_db_path, embedding_function=self.embedding_function)
            results = vectorstore.similarity_search(query, k=3)
            return "\n\n".join([f"[BOOK EXCERPT]: {r.page_content}" for r in results])
        except Exception as e:
            logger.error(f"⚠️ RAG Retrieval Failed: {e}"); return ""

    async def chat_with_langchain(self, query, system_persona, user_name, context_override=None, image_paths=[]):
        """
        Gaia-standard multimodal chat engine.
        Unifies memory recall with LLM interaction.
        """
        from langchain_litellm import ChatLiteLLM
        from langchain_core.messages import HumanMessage, SystemMessage
        import base64
        
        # 1. RAG Recall
        if context_override:
            context = context_override
            query_vec = self.embedding_function.embed_query(query) # Still need vector for record
            logger.info("⚡ [OPTIMIZATION] Using pre-fetched context. Skipping redundant recall.")
        else:
            context, query_vec = self.remember(query, n_results=5, return_vector=True)
        
        # 2. Setup LLM
        try:
            llm = ChatLiteLLM(model=self.llm_model, api_key=self.llm_api_key, verbose=False)
            
            # 3. Construct Prompt
            final_system = f"{system_persona}\n\n[CONTEXT]:\n{context}\n\n[USER]: {user_name}"
            messages = [SystemMessage(content=final_system)]
            
            if image_paths:
                content_parts = [{"type": "text", "text": query}]
                for img_path in image_paths:
                    try:
                        with open(img_path, "rb") as f:
                            encoded = base64.b64encode(f.read()).decode("utf-8")
                            content_parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
                    except: pass
                messages.append(HumanMessage(content=content_parts))
            else:
                messages.append(HumanMessage(content=query))
            
            # 4. Invoke
            response = await llm.ainvoke(messages)
            
            # Record Interaction (Implicitly recorded here for unified RAG usage)
            # REUSE query_vec for the user prompt
            self.record(query, user_name=user_name, tags="chat,rag", source="langchain_chat", embeddings=query_vec)
            self.record(response.content, user_name="Eleuthia", tags="chat,bot_response", source="langchain_chat")
            
            return response.content
            
        except Exception as e:
            logger.error(f"❌ LangChain Chat Error: {e}")
            return f"⚠️ Brain Stutter: {e}"

    def ask(self, query, system_persona, user_name="User", context_override=None, temperature=0.3):
        """
        Synchronous RAG chat using LangChain (LiteLLM wrapper).
        Use this for Flask webhooks or sync handlers.
        """
        from langchain_litellm import ChatLiteLLM
        from langchain_core.messages import HumanMessage, SystemMessage
        
        try:
            # 1. RAG Recall (The 'R' in RAG)
            if context_override:
                context = context_override
                # Get vector for record using cache (to avoid API call if already embedded)
                query_vec = self.embedding_function.embed_query(query)
                logger.info("⚡ [OPTIMIZATION] Using pre-fetched context. Skipping redundant recall.")
            else:
                context, query_vec = self.remember(query, n_results=5, return_vector=True)
            
            # 2. Initialize LangChain LLM
            llm = ChatLiteLLM(
                model=self.llm_model, 
                api_key=self.llm_api_key, 
                base_url=self.llm_base_url,
                temperature=temperature
            )
            
            # 3. Build Messages
            final_system = f"{system_persona}\n\n[RELEVANT CONTEXT]:\n{context}"
            messages = [
                SystemMessage(content=final_system),
                HumanMessage(content=query)
            ]
            
            # 4. Generate Response (LangChain Invoke)
            logger.info(f"🧠 [LLM] Invoking LangChain RAG for: {user_name}")
            response = llm.invoke(messages)
            reply = response.content
            
            # 5. Record Interaction (The 'Learning' part)
            # [OPTIMIZATION] Reuse the query vector computed during remember()
            self.record(query, user_name=user_name, tags="chat,user_query,rag", source="eleuthia_ask", embeddings=query_vec)
            self.record(reply, user_name="Eleuthia", tags="chat,bot_reply,rag", source="eleuthia_ask")
            
            return reply
            
        except Exception as e:
            logger.error(f"❌ Brain Ask Error: {e}")
            return f"⚠️ Brain offline: {e}"

    # --- [HOUSEKEEPING HELPERS] ---
    def _get_file_hash(self, filepath):
        """Generate MD5 hash for file deduplication."""
        try:
            with open(filepath, 'rb') as f: return hashlib.md5(f.read()).hexdigest()
        except: return None

    def _load_tracking(self, tracking_file):
        if os.path.exists(tracking_file):
            try:
                with open(tracking_file, 'r') as f: return json.load(f)
            except: return {}
        return {}

    def _save_tracking(self, tracking_file, data):
        try:
            with open(tracking_file, 'w') as f: json.dump(data, f, indent=2)
        except: pass

    def get_analytics(self) -> Dict:
        """Returns deep insights into Eleuthia's neural activity."""
        return self.analytics.to_dict()

if __name__ == "__main__":
    # Test Brain Upgrade
    logging.basicConfig(level=logging.INFO)
    brain = EleuthiaBrain()
    print(f"🧠 Eleuthia Neural Link: {brain.analytics.total_memories} memories active.")
    
    # Quick Test Search
    test_query = "deadline urgent project"
    result = brain.remember(test_query, n_results=1)
    print(f"🔍 Test Recall Result:\n{result}")
