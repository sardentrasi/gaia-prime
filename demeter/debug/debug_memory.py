import chromadb
import os

db_path = os.path.join(os.getcwd(), "memory_core")
client = chromadb.PersistentClient(path=db_path)
collection = client.get_or_create_collection(name="knowledge_base")

results = collection.get(where_document={"$contains": "Permintaan berita"})

if results and results['ids']:
    print(f"Found {len(results['ids'])} documents.")
    for i, doc in enumerate(results['documents']):
        print(f"--- Doc {i} ---")
        print(f"Content: {doc}")
        print(f"Metadata: {results['metadatas'][i]}")
else:
    print("No documents found containing 'Permintaan berita'.")

