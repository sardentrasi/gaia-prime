import sys
import os
import hashlib
import json
import time
import tempfile
import feedparser
import logging
from dateutil import parser
from datetime import datetime, timezone, timedelta

# LOGGING SETUP
logger = logging.getLogger("NewsHarvester")

# Use FileHandler + StreamHandler so logs go to both file and screen
handlers = [
    logging.FileHandler("apollo.log"),
    logging.StreamHandler(sys.stdout)
]
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=handlers
)

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir) # apollo/
root_dir = os.path.dirname(parent_dir)    # root/

sys.path.append(parent_dir)
sys.path.append(root_dir)

try:
    from apollo_memory_manager import GaiaBrain
    print("[NEWS] Apollo Local Memory Manager connected (Local-First Sync).")
except ImportError:
    try:
        from gaia_memory_manager import GaiaBrain
        print("⚠️ [NEWS] Apollo Manager missing. Using Central Brain directly.")
    except ImportError as e:
        print(f"❌ CRITICAL: Memory Manager missing! {e}")
        sys.exit(1)

class NewsHarvester:
    def __init__(self):
        self.current_script_dir = os.path.dirname(os.path.abspath(__file__))
        self.sources_file = os.path.join(self.current_script_dir, "../sources.txt")
        self.feeds = self._load_sources()
        self.brain = GaiaBrain()
        
        # [DEDUPLICATION] Persistent Tracking
        self.tracking_file = os.path.join(self.current_script_dir, "harvested_news_ids.json")
        self.harvested_ids = self._load_ids()

    def _load_ids(self):
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r') as f:
                    # Keep max 5000 IDs to manage file size
                    data = json.load(f)
                    return set(data[-5000:])
            except (json.JSONDecodeError, ValueError):
                return set()
        return set()

    def _save_ids(self):
        try:
            # [ATOMIC WRITE] Prevent corruption on interrupt
            tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(self.tracking_file), suffix=".tmp")
            with os.fdopen(tmp_fd, 'w') as f:
                # Store up to 5000 latest IDs
                json.dump(list(self.harvested_ids)[-5000:], f)
            os.replace(tmp_path, self.tracking_file)
        except Exception as e:
            logger.error(f"❌ Error saving news tracking IDs: {e}")
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _load_sources(self):
        """Loads RSS feeds from sources.txt"""
        defaults = [
            "https://www.cnbcindonesia.com/market/rss",
            "https://www.cnnindonesia.com/ekonomi/rss",
            "https://www.antaranews.com/rss/ekonomi"
        ]
        
        if not os.path.exists(self.sources_file):
            logger.warning(f"⚠️ sources.txt not found at {self.sources_file}. Using defaults.")
            return defaults
            
        try:
            with open(self.sources_file, "r") as f:
                lines = [line.strip() for line in f.readlines()]
                
            # Filter: Ignore comments (#), empty lines, and duplicates
            feeds = [l for l in lines if l and not l.startswith("#")]
            
            if not feeds:
                logger.warning("⚠️ sources.txt is empty. Using defaults.")
                return defaults
                
            logger.info(f"📋 Loaded {len(feeds)} feeds from sources.txt")
            return feeds
            
        except Exception as e:
            logger.error(f"❌ Error reading sources.txt: {e}")
            return defaults

    def harvest(self):
        logger.info(f"📡 Starting harvest at {datetime.now().strftime('%H:%M:%S')}...")
        total_saved = 0
        
        # 24 Hour Logic
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        
        # GLOBAL ACCUMULATORS (Panen Raya)
        global_batch_texts = []
        global_batch_metadatas = []
        global_batch_ids = []
        
        # [NEW] Track top headlines for short-term memory
        top_headlines = []

        for i, url in enumerate(self.feeds):
            # [RATE LIMIT] Delay between feed requests (skip first)
            if i > 0:
                time.sleep(1)
            
            domain = url.split("//")[-1].split("/")[0]
            logger.info(f"🔎 Checking {url}...")
            
            try:
                feed = feedparser.parse(url)
                count = 0
                
                for entry in feed.entries:
                    try:
                        # 1. Check Date
                        published = entry.get("published", entry.get("pubDate"))
                        if not published: continue
                        
                        pub_date = parser.parse(published)
                        if pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                        
                        if pub_date < cutoff:
                            continue # Too old
                            
                        # 2. Extract Data & Create Stable ID
                        title = entry.get("title", "No Title")
                        link = entry.get("link", "")
                        article_hash = hashlib.md5(f"{title}_{link}".encode()).hexdigest()
                        full_id = f"news_{article_hash}"

                        # [DEDUPLICATION] Persistent check
                        if full_id in self.harvested_ids:
                            continue
                        
                        summary = entry.get("summary", entry.get("description", ""))
                        
                        # 3. Print Verbose
                        logger.info(f"[NEWS] Panen: {title[:50]}... | Sumber: {domain}")
                        
                        # 4. Prepare for Global Batch
                        date_str = pub_date.strftime("%Y-%m-%d %H:%M")
                        content_text = f"[{date_str}] BERITA {domain}: {title}.\nLink: {link}\nRingkasan: {summary}"
                        
                        # [NEW] Track ALL headlines with their links for short-term memory
                        top_headlines.append(f"[{domain}] {title} ( {link} )")
                            
                        # [DYNAMIC TAGGING] Extract category from URL
                        url_parts = url.lower().replace(".xml", "").replace(".html", "").replace(".php", "").split('/')
                        junk = ["rss", "feed", "feeds", "index", "sindikasi", "www", "com", "id", "http:", "https:", ""]
                        path_tokens = [p for p in url_parts if p not in junk and not p.isdigit()]
                        
                        if path_tokens:
                            category = ", ".join(path_tokens[-2:]) if len(path_tokens) >= 2 else path_tokens[0]
                        else:
                            category = "general"

                        if "politik" in url.lower() and "politik" not in category:
                            category += ", politik"
                        if ("ekonomi" in url.lower() or "market" in url.lower() or "bisnis" in url.lower()) and "economy" not in category:
                            category += ", finance, economy"
                        if "kriminal" in url.lower() and "kriminal" not in category:
                            category += ", kriminal"
                        if "cuaca" in url.lower() and "cuaca" not in category:
                            category += ", cuaca"
                        if "olahraga" in url.lower() and "olahraga" not in category:
                            category += ", olahraga"
                        if "teknologi" in url.lower() and "teknologi" not in category:
                            category += ", teknologi"
                        if "lifestyle" in url.lower() and "lifestyle" not in category:
                            category += ", lifestyle"
                        if "hiburan" in url.lower() and "hiburan" not in category:
                            category += ", hiburan"
                            
                        # [CONTENT-BASED TAGGING] Check Title & Summary for better precision
                        content_scan = f"{title} {summary}".lower()
                        scan_map = {
                            "politik": ["politik", "presiden", "menteri", "dpr", "pemilu", "pilkada"],
                            "kriminal": ["kriminal", "polisi", "kejadian", "pembunuhan", "perampokan", "tangkap", "tewas"],
                            "cuaca": ["cuaca", "hujan", "banjir", "gempa", "bmkg", "panas", "angin"],
                            "olahraga": ["sepak bola", "timnas", "bola", "sport", "pertandingan", "skor"],
                            "teknologi": ["gadget", "aplikasi", "startup", "internet", "inovasi", "tech"],
                            "ekonomi": ["saham", "investasi", "ihsg", "bisnis", "ekonomi", "keuangan", "finance"]
                        }
                        
                        extra_cats = []
                        for cat_key, keywords in scan_map.items():
                            if any(k in content_scan for k in keywords):
                                if cat_key not in category:
                                    extra_cats.append(cat_key)
                                    
                        if extra_cats:
                            category += ", " + ", ".join(extra_cats)

                        tags = f"apollo, news, {category}, {domain}"
                        timestamp = datetime.now().isoformat()
                        
                        global_batch_texts.append(content_text)
                        global_batch_metadatas.append({
                            "source": "news_harvest",
                            "author": domain,
                            "tags": tags,
                            "timestamp": timestamp
                        })
                        global_batch_ids.append(full_id)
                        self.harvested_ids.add(full_id)
                        count += 1
                            
                    except Exception as inner_e:
                        logger.warning(f"Skipping entry: {inner_e}")
                        continue
                
                logger.info(f"   -> Found {count} UNIQUE articles from {domain}")
                
            except Exception as e:
                logger.error(f"❌ Feed Error ({domain}): {e}")

        if global_batch_texts:
            total_items = len(global_batch_texts)
            logger.info(f"💾 Sending {total_items} TOTAL UNIQUE articles to Memory Core...")
            
            if hasattr(self.brain, 'record_batch'):
                success = self.brain.record_batch(global_batch_texts, global_batch_metadatas, ids=global_batch_ids)
                if success:
                    total_saved = total_items
                    logger.info("✅ Global Batch Success!")
                    self._save_ids()
                    # [REMOVED] Redundant state update, handled by apollo_main
            else:
                for i, txt in enumerate(global_batch_texts):
                    meta = global_batch_metadatas[i]
                    self.brain.record(txt, meta['author'], meta['tags'], meta['source'])
                total_saved = total_items
                self._save_ids()
                # [REMOVED] Redundant state update, handled by apollo_main

        logger.info(f"✅ Finished. Total: {total_saved} unique articles processed.")
        return total_saved, top_headlines


if __name__ == "__main__":
    bot = NewsHarvester()
    bot.harvest()
