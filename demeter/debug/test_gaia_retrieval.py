
import sys
import os
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GaiaTest")

# Add path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from gaia_memory_manager import GaiaBrain

def main():
    print("--- [TEST] Initializing GaiaBrain ---")
    brain = GaiaBrain()
    print("✅ GaiaBrain Online.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            print("-" * 50)
            query = input("📝 Enter Query: ").strip()
            if query.lower() in ["exit", "quit"]:
                print("👋 Exiting...")
                break
            
            if not query:
                continue

            filters = input("🔍 Enter Filter Type (optional, e.g., 'demeter', 'user_interaction'): ").strip()
            
            print(f"\n🚀 Retrieving for: '{query}' | Filter: '{filters}'")
            
            # Retrieve
            try:
                results = brain.remember(query, n_results=5, filter_type=filters if filters else None)
                
                print("\n--- [RESULTS] ---")
                if results:
                    # Check if results is a list (standard) or string
                    if isinstance(results, list):
                        for i, res in enumerate(results):
                            print(f"\nResult #{i+1}:\n{res.strip()}")
                    else:
                        print(results)
                else:
                    print("⚠️ No results found.")
            except Exception as e:
                print(f"❌ Error during retrieval: {e}")

        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except Exception as e:
            print(f"❌ Unexpected Error: {e}")

if __name__ == "__main__":
    main()
