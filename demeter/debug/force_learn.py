from tools.educate_gaia import CodeIngester
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

print("🚀 Starting Manual Code Ingestion...")
ingester = CodeIngester()
count = ingester.ingest_all()
print(f"✅ Ingestion Complete. Learned {count} files.")
