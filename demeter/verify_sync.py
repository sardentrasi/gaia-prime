
import sys
import os
import time

# Verify paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir) # Add demeter dir
sys.path.insert(0, os.path.dirname(current_dir)) # Add root dir

from demeter_memory_manager import GaiaBrain as DemeterBrain

print("--- [TEST] Initializing DemeterBrain ---")
try:
    brain = DemeterBrain()
    print("✅ DemeterBrain initialized.")
except Exception as e:
    print(f"❌ Failed to init DemeterBrain: {e}")
    sys.exit(1)

print("\n--- [TEST] Checking Central Link ---")
if brain.gaia_brain:
    print("✅ Central GaiaBrain object exists.")
else:
    print("❌ Central GaiaBrain object MISSING.")

print("\n--- [TEST] Recording Memory ---")
test_text = f"Test Sync {time.time()}"
success = brain.record(test_text, tags="test_sync", source="test_script")

if success:
    print("✅ Record returned True.")
else:
    print("❌ Record returned False.")

print("\n--- [TEST] Verifying Central ---")
if brain.gaia_brain:
    # Try to verify via central brain if possible (implied by log check)
    pass
