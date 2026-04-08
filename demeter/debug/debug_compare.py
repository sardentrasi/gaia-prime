
import os
import json
import chromadb

def debug_comparison():
    # 1. Central Brain
    central_path = os.path.join(os.getcwd(), "memory_core")
    print(f"--- [CENTRAL BRAIN] {central_path} ---")
    if os.path.exists(central_path):
        client = chromadb.PersistentClient(path=central_path)
        try:
            collection = client.get_collection("knowledge_base")
            res = collection.get(where={"source": "news_harvest"}, limit=5)
            print(f"News items found: {len(res['ids'])}")
        except Exception as e:
            print(f"Error accessing central collection: {e}")
    else:
        print("Central path does not exist.")

    # 2. Local Apollo Brain
    local_path = os.path.join(os.getcwd(), "apollo", "apollo_memory_core")
    print(f"\n--- [LOCAL APOLLO BRAIN] {local_path} ---")
    if os.path.exists(local_path):
        client = chromadb.PersistentClient(path=local_path)
        try:
            # Note: Apollo uses 'apollo_knowledge' collection name
            collection = client.get_collection("apollo_knowledge")
            res = collection.get(where={"source": "news_harvest"}, limit=5)
            print(f"News items found: {len(res['ids'])}")
            
            # Check all sources if no news found
            if len(res['ids']) == 0:
                all_res = collection.get(limit=5)
                print(f"Available sources in local core: {set(m.get('source') for m in all_res['metadatas'])}")
        except Exception as e:
            print(f"Error accessing local collection: {e}")
    else:
        print("Local Apollo path does not exist.")

if __name__ == "__main__":
    debug_comparison()
