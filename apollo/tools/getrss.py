import requests
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin

# Sembunyikan warning kotor
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

class ApolloRSSDetector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        }
        self.common_paths = ['/rss', '/feed', '/rss.xml', '/market/rss']

    def is_rss(self, url):
        """Cek apakah URL yang dimasukkan sebenarnya sudah RSS."""
        try:
            r = requests.head(url, headers=self.headers, timeout=10)
            ctype = r.headers.get('Content-Type', '').lower()
            return 'xml' in ctype or 'rss' in url
        except:
            return False

    def scan(self, target_url):
        print(f"\n[Apollo] Scanning: {target_url}")
        
        if self.is_rss(target_url):
            return [{'title': 'Direct RSS Input', 'url': target_url}]

        rss_links = []
        try:
            with requests.Session() as s:
                r = s.get(target_url, headers=self.headers, timeout=15)
                # Gunakan lxml sebagai parser utama
                soup = BeautifulSoup(r.text, 'lxml')
                
                # Cari meta tags
                tags = soup.find_all('link', type=['application/rss+xml', 'application/atom+xml', 'text/xml'])
                for tag in tags:
                    href = tag.get('href')
                    if href:
                        rss_links.append({
                            'title': tag.get('title', 'Detected Feed'),
                            'url': urljoin(target_url, href)
                        })

                # Fallback brute force jika kosong
                if not rss_links:
                    for path in self.common_paths:
                        test_url = urljoin(target_url, path)
                        if s.head(test_url, timeout=5).status_code == 200:
                            rss_links.append({'title': f'Guessed {path}', 'url': test_url})

        except Exception as e:
            print(f"[Apollo Error] {e}")
            
        return rss_links

if __name__ == "__main__":
    detector = ApolloRSSDetector()
    url = input("Masukkan URL: ").strip()
    if not url.startswith('http'): url = 'https://' + url
    
    found = detector.scan(url)
    if found:
        print(f"\n[Success] Ditemukan {len(found)} link:")
        for f in found:
            print(f" >> {f['title']}: {f['url']}")
    else:
        print("\n[Fail] Tidak ada RSS ditemukan.")
