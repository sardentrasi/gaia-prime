import sys
import os
import chromadb
# [REFACTOR] Renamed from brain.py
from gaia_memory_manager import GaiaBrain

def test_brain_state():
    print("--- BRAIN DIAGNOSTIC ---")
    
    # 1. Init Brain
    try:
        brain = GaiaBrain()
        print(f"DB Path: {brain.db_path}")
        print(f"Collection: {brain.collection.name}")
        print(f"Count: {brain.collection.count()}")
    except Exception as e:
        print(f"❌ Error initializing GaiaBrain: {e}")
        return
    
    # 2. Peek Data
    print("\n--- RECENT MEMORIES (Top 5) ---")
    try:
        peek = brain.collection.peek(limit=5)
        if peek['ids']:
            for i in range(len(peek['ids'])):
                meta = peek['metadatas'][i]
                doc = peek['documents'][i]
                print(f"[{i}] Source: {meta.get('source')} | Tags: {meta.get('tags')}")
                print(f"    Text: {doc[:100]}...")
        else:
            print("   (Memory is empty)")
    except Exception as e:
        print(f"   Error peeking data: {e}")

    # 3. Dynamic Search (User Input)
    print("\n--- CUSTOM SEARCH ---")
    
    # Meminta input dari user
    search_query = input("Masukkan keyword tag/source (tekan Enter untuk default 'learned_content'): ").strip()
    
    # Default value jika user langsung tekan enter
    if not search_query:
        search_query = "learned_content"
    
    print(f"\n🔎 Scanning memory for: '{search_query}' ...")

    # Ambil semua data
    all_data = brain.collection.get()
    found = 0
    
    if not all_data['ids']:
        print("❌ Database kosong.")
        return

    # Loop pencarian
    for i, meta in enumerate(all_data['metadatas']):
        if meta is None: continue

        tags = str(meta.get('tags', '')).lower()
        src = str(meta.get('source', '')).lower()
        target = search_query.lower()

        # Logika pencarian dinamis
        if target in tags or target in src:
            doc_content = all_data['documents'][i]
            preview = doc_content[:100].replace('\n', ' ') if doc_content else "No Content"
            
            print(f"✅ FOUND [{i}]: {preview}...")
            print(f"   -> Tags: {tags} | Source: {src}")
            print("-" * 40)
            
            found += 1
            # Batasi output agar terminal tidak banjir jika hasil ribuan
            if found >= 20: 
                print(f"... Limit tampilan tercapai (masih ada data lain).")
                break
            
    if found == 0:
        print(f"❌ NO DATA FOUND containing '{search_query}'.")
    else:
        print(f"📊 Total item ditemukan: {found}")

if __name__ == "__main__":
    test_brain_state()
