import chromadb
import os

db_path = os.path.join(os.getcwd(), "memory_core")
client = chromadb.PersistentClient(path=db_path)
collection = client.get_or_create_collection(name="knowledge_base")

# Fetch all docs with source='apollo' (or just fetch first 20 to see)
results = collection.get(limit=20) 

print(f"Found {len(results['ids'])} documents.")
for i, meta in enumerate(results['metadatas']):
    if "apollo" in str(meta).lower() or "news" in str(meta).lower():
        print(f"--- Doc {i} ---")
        print(f"Content: {results['documents'][i]}")
        print(f"Metadata: {meta}")
