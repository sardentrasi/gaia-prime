import chromadb
import os
from langchain_chroma import Chroma
from gaia_memory_manager import GaiaBrain

def check_memories():
    brain = GaiaBrain()
    print(f"Connected to DB at: {brain.db_path}")
    
    # Query for all (or a large enough subset) and filter in Python
    results = brain.collection.get()
    
    demeter_items = []
    for i in range(len(results['ids'])):
        tags = results['metadatas'][i].get('tags', '').lower()
        if 'demeter' in tags:
            demeter_items.append({
                "id": results['ids'][i],
                "metadata": results['metadatas'][i],
                "document": results['documents'][i]
            })
    
    print(f"Found {len(demeter_items)} items containing 'demeter' in tags")
    for i in range(min(10, len(demeter_items))):
        item = demeter_items[i]
        print(f"ID: {item['id']}")
        print(f"Metadata: {item['metadata']}")
        print(f"Document: {item['document'][:100]}...")
        print("-" * 20)

if __name__ == "__main__":
    check_memories()
