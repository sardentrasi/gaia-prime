
import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")

try:
    import litellm
    print("✅ import litellm success")
    print(f"litellm file: {litellm.__file__}")
    print(f"litellm version: {getattr(litellm, '__version__', 'unknown')}")
except Exception as e:
    print(f"❌ import litellm failed: {e}")

try:
    from litellm import embedding
    print("✅ from litellm import embedding success")
except Exception as e:
    print(f"❌ from litellm import embedding failed: {e}")

try:
    import litellm.types.rerank
    print("✅ import litellm.types.rerank success")
except Exception as e:
    print(f"❌ import litellm.types.rerank failed: {e}")
