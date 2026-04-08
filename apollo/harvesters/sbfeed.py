import requests
import json
import os
import hashlib
import re
import tempfile
import time
from datetime import datetime

# [STANDARDIZATION] Apollo Local-First with Central Sync
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    import sys
    sys.path.append(parent_dir)
    from apollo_memory_manager import GaiaBrain
    BRAIN_CONNECTED = True
except ImportError:
    BRAIN_CONNECTED = False

class StockbitHarvester:
    def __init__(self):
        # [FIX] API URL dari .env agar mudah diubah tanpa edit code
        self.api_url = os.getenv("STOCKBIT_API_URL", "https://exodus.stockbit.com/stream/non-login/user/stockbit")
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Origin': 'https://stockbit.com',
            'Referer': 'https://stockbit.com/stockbit'
        }
        # Folder data sesuai struktur GAIA (Apollo Root)
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        self.apollo_root = os.path.dirname(current_script_dir)
        self.output_dir = self.apollo_root
        
        # Tracking file untuk deduplikasi
        self.tracking_file = os.path.join(current_script_dir, "harvested_ids.json")
        self.harvested_ids = self._load_ids()
        self.brain = GaiaBrain() if BRAIN_CONNECTED else None

    def _load_ids(self):
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r') as f:
                    # [FIX] Keep max 5000 IDs to manage memory
                    data = json.load(f)
                    return set(data[-5000:]) if isinstance(data, list) else set()
            except (json.JSONDecodeError, ValueError):
                return set()
        return set()

    def _save_ids(self):
        try:
            # [ATOMIC WRITE] Prevent corruption on interrupt
            tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(self.tracking_file), suffix=".tmp")
            with os.fdopen(tmp_fd, 'w') as f:
                # [FIX] Store up to 5000 latest IDs
                json.dump(list(self.harvested_ids)[-5000:], f)
            os.replace(tmp_path, self.tracking_file)
        except Exception as e:
            print(f"[Stockbit Error] Gagal simpan tracking IDs: {e}")
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def collect_posts(self, limit=50):
        print(f"[Stockbit] Memanen data dari: {self.api_url}")
        
        try:
            params = {'limit': limit}
            response = requests.get(self.api_url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                raw_data = response.json()
                post_list = raw_data.get('data', [])

                if not isinstance(post_list, list):
                    print("[Stockbit Error] Struktur data tidak sesuai (bukan list).")
                    return []

                extracted_data = []
                new_count = 0
                for p in post_list:
                    if not isinstance(p, dict): continue
                    
                    # Handle missing ID with a hash of content for deduplication safety
                    raw_id = p.get('id') or p.get('id_str') or p.get('post_id')
                    text_content = p.get('content', '').strip()
                    
                    if not raw_id:
                        post_id = f"gen_{hashlib.md5(text_content.encode()).hexdigest()[:12]}"
                    else:
                        post_id = str(raw_id)

                    if post_id in self.harvested_ids:
                        continue
                    
                    # Timestamp fallback - Check more potential keys
                    raw_ts = p.get('created_at') or p.get('time') or p.get('date') or p.get('updated_at')
                    
                    # Ekstraksi Media & Links
                    media_urls = []
                    
                    # 1. Structured Image URLs
                    img_keys = ['images', 'attachments', 'media', 'image_url', 'thumbnail']
                    for k in img_keys:
                        val = p.get(k)
                        if not val: continue
                        
                        if isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict) and item.get('url'): media_urls.append(item.get('url'))
                                elif isinstance(item, str) and (item.startswith('http')): media_urls.append(item)
                        elif isinstance(val, str) and val.startswith('http'):
                            media_urls.append(val)
                    
                    # 2. Structured Links
                    link_keys = ['links', 'entities', 'references']
                    for lk in link_keys:
                        val = p.get(lk)
                        if not val: continue
                        if isinstance(val, list):
                            for item in val:
                                if isinstance(item, str) and item.startswith('http'): media_urls.append(item)
                                elif isinstance(item, dict) and item.get('url'): media_urls.append(item.get('url'))

                    # 3. Regex Fallback: Extract from text_content
                    # Mencari link http/https yang tertulis di dalam teks
                    found_links = re.findall(r'(https?://[^\s)\]]+)', text_content)
                    for fl in found_links:
                        if fl not in media_urls:
                            media_urls.append(fl)

                    harvest_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Ekstraksi data mendalam untuk Minerva
                    post_obj = {
                        'post_id': post_id,
                        'timestamp': raw_ts or harvest_time, # Fallback jika Stockbit tidak sedia waktu
                        'harvested_at': harvest_time,
                        'author': p.get('username') or p.get('author_name') or "Stockbit",
                        'text_content': text_content,
                        'prediction': p.get('prediction'), # Bullish/Bearish/Neutral
                        'sentiment_tags': p.get('topics', []) or p.get('tickers', []),
                        'media_urls': list(set(media_urls)) # Deduplicate URLs
                    }
                    
                    if post_obj['text_content']:
                        extracted_data.append(post_obj)
                        self.harvested_ids.add(post_id)
                        new_count += 1

                print(f"[Stockbit] Berhasil mengekstrak {new_count} postingan baru.")
                if new_count > 0:
                    self._save_ids()
                return extracted_data
            else:
                print(f"[Stockbit Fail] HTTP Status: {response.status_code}")
        except Exception as e:
            print(f"[Stockbit Error] Terjadi kegagalan: {e}")
        
        return []

    def harvest(self):
        """Main method to integrate with Apollo Core scheduler/manual harvest."""
        print(f"📡 [Stockbit] Starting harvest at {datetime.now().strftime('%H:%M:%S')}...")
        new_posts = self.collect_posts(limit=50)
        
        if not new_posts:
            print("[Stockbit] Tidak ada data baru untuk diproses.")
            return 0, []

        # [REMOVED] Redundant state update, handled by apollo_main

        # 2. Record to RAG (Gaia Brain)
        texts = []
        metadatas = []
        ids = []
        headlines = []

        for p in new_posts:
            # Format text for RAG
            sentiment = f" | Sentiment: {p['prediction']}" if p['prediction'] else ""
            tags_str = ", ".join(p['sentiment_tags']) if p['sentiment_tags'] else "market"
            
            rag_text = f"[{p['timestamp']}] STOCKBIT ({p['author']}): {p['text_content']}{sentiment}"
            if p['media_urls']:
                rag_text += f"\nMedia: {', '.join(p['media_urls'])}"
            
            texts.append(rag_text)
            metadatas.append({
                "source": "stockbit_harvest",
                "author": p['author'],
                "tags": f"apollo, stockbit, {tags_str}",
                "timestamp": p['timestamp']
            })
            ids.append(f"sb_{p['post_id']}")
            
            # For short-term memory summary
            # For short-term memory summary (Rich Snippet)
            clean_text = p['text_content'].replace('\n', ' ').strip()
            snip = (clean_text[:100] + "..") if len(clean_text) > 100 else clean_text
            headlines.append(f"@{p['author']}: {snip}")

        if self.brain and texts:
            if hasattr(self.brain, 'record_batch'):
                self.brain.record_batch(texts, metadatas, ids=ids)
            else:
                for i in range(len(texts)):
                    self.brain.record(texts[i], metadatas[i]['author'], metadatas[i]['tags'], metadatas[i]['source'])
        
        return len(new_posts), headlines


if __name__ == "__main__":
    harvester = StockbitHarvester()
    harvester.harvest()