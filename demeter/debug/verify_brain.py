
import os
import sys
import shutil

# Ensure we can import brain
sys.path.append(os.getcwd())
# [REFACTOR] Renamed from brain.py
from gaia_memory_manager import GaiaBrain

def test_brain():
    print("🧠 Initializing GaiaBrain...")
    brain = GaiaBrain()
    
    # Test Data
    test_text = "Verification Test: Memory Core functionality check."
    user = "Tester"
    source = "verification_script"
    tags = "test,verification"
    
    # 1. Record
    print(f"📝 Recording: '{test_text}'")
    success = brain.record(text=test_text, user_name=user, source=source, tags=tags)
    
    if success:
        print("✅ Record Success.")
    else:
        print("❌ Record Failed.")
        return

    # 2. Retrieve
    print("🔍 Retrieving...")
    results = brain.remember("Verification Test", n_results=1)
    print(f"📄 Result: {results}")

    if "Verification Test" in results:
        print("✅ Retrieval Success.")
    else:
        print("❌ Retrieval Failed.")

if __name__ == "__main__":
    test_brain()
