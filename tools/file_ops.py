import os

def append_to_file(filepath, content):
    """
    Appends content to a file.
    Ensures content ends with a newline if missing.
    Raises Exception if failed.
    """
    try:
        # Check if file exists (optional, but good for append logic validation?)
        # The prompt says "Return True if successful, raise Exception if failed."
        # Standard open('a') creates the file if it doesn't exist. 
        # But if we want to ensure we are appending to an *existing* config, checking existence is safer.
        if not os.path.exists(filepath):
             # If strictly appending to existing source lists, maybe we want to fail if missing?
             # But usually appending creates. Let's assume standard behavior but ensure directory exists.
             if not os.path.exists(os.path.dirname(filepath)):
                 os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Read to check newline if file exists
        prefix = ""
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = f.read()
                if existing and not existing.endswith('\n'):
                    prefix = "\n"
        
        with open(filepath, 'a', encoding='utf-8') as f:
             f.write(f"{prefix}{content}\n")
             
        return True
        
    except Exception as e:
        raise Exception(f"Failed to append to file: {e}")

def read_file(filepath):
    """
    Returns file content as string.
    """
    try:
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise Exception(f"Failed to read file: {e}")
