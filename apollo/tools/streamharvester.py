import requests
import json
import os
from datetime import datetime

class ApolloHarvester:
    def __init__(self):
        # Menggunakan endpoint exodus non-login hasil temuan di Network Tab
        self.api_url = "https://exodus.stockbit.com/stream/non-login/user/stockbit"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Origin': 'https://stockbit.com',
            'Referer': 'https://stockbit.com/stockbit'
        }
        # Folder data sesuai struktur GAIA
        self.output_dir = "/home/gaia-prime/apollo/data/feeds/"
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def collect_posts(self, limit=50):
        print(f"[Apollo] Memanen data dari: {self.api_url}")
        
        try:
            params = {'limit': limit}
            response = requests.get(self.api_url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                raw_data = response.json()
                post_list = raw_data.get('data', [])

                if not isinstance(post_list, list):
                    print("[Apollo Error] Struktur data tidak sesuai (bukan list).")
                    return []

                extracted_data = []
                for p in post_list:
                    if not isinstance(p, dict): continue

                    # Ekstraksi data mendalam untuk Minerva
                    post_obj = {
                        'post_id': p.get('id'),
                        'timestamp': p.get('created_at'),
                        'author': p.get('username'),
                        'text_content': p.get('content', '').strip(),
                        'prediction': p.get('prediction'), # Bullish/Bearish tag jika ada
                        'sentiment_tags': p.get('topics', []),
                        'media': [
                            {'type': 'image', 'url': img.get('url')} 
                            for img in p.get('images', []) if isinstance(img, dict)
                        ]
                    }
                    
                    if post_obj['text_content']:
                        extracted_data.append(post_obj)

                print(f"[Apollo] Berhasil mengekstrak {len(extracted_data)} postingan.")
                return extracted_data
            else:
                print(f"[Apollo Fail] HTTP Status: {response.status_code}")
        except Exception as e:
            print(f"[Apollo Error] Terjadi kegagalan: {e}")
        
        return []

    def save_for_minerva(self, posts):
        if not posts:
            print("[Apollo] Tidak ada data untuk disimpan.")
            return None
        
        # Nama file unik berdasarkan waktu
        filename = f"stockbit_full_feed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                # Perbaikan parameter: ensure_ascii=False agar karakter unik/emoji tidak rusak
                json.dump(posts, f, ensure_ascii=False, indent=4)
            
            print(f"\n[Apollo Success] Data JSON siap diolah Minerva.")
            print(f"File Location: {filepath}")
            return filepath
        except Exception as e:
            print(f"[Apollo Error] Gagal menulis file JSON: {e}")
            return None

if __name__ == "__main__":
    harvester = ApolloHarvester()
    
    # Menarik 50 postingan terakhir
    all_posts = harvester.collect_posts(limit=50)
    
    if all_posts:
        # Tampilkan JSON mentah di terminal (opsional)
        # print(json.dumps(all_posts[:1], ensure_ascii=False, indent=2))
        
        harvester.save_for_minerva(all_posts)
