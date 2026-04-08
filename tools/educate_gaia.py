import os
import sys
import logging
import hashlib
from datetime import datetime

# Adjust path to import brain from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# [REFACTOR] Renamed from brain.py
from gaia_memory_manager import GaiaBrain

logger = logging.getLogger("CodeIngester")

class CodeIngester:
    def __init__(self):
        self.brain = GaiaBrain()
        self.root_dir = "." # Default to current directory
        # [FIX] Exclude harvested_data to prevent polluting memory with raw JSON logs
        self.ignore_dirs = {
            # Meta & Config
            '.git', 'venv', '__pycache__', '.env', 'logs', 
            # Databases & Memory
            'memory_core', '.gemini', '.chroma', 
            # Deep Data & Auth
            'harvested_data', 'node_modules', 'auth_info_baileys', 'credentials', 
            'wa-bridge-gaia', 'auth-info-gaia', 'auth_info_gaia',
            # Temporary & Build
            'dist', 'build', 'coverage', 'tmp', 'downloads',
            # Backups & Logs
            'backups', 'backupmain', 'data_logs',
            # Media
            'vision_capture', 'captured_media', 'static'
        }
        self.ignore_files = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', '.DS_Store', '.xlsx'}
        self.include_exts = {'.py', '.txt', '.md', '.json'}
        
        # [CHUNKING CONFIG] Prevent embedding API limit errors & Improve Granularity
        self.max_chunk_chars = 4000  # Reduced to ~1000 tokens for better semantic precision
        self.min_file_size = 10  # Skip files smaller than 10 bytes
        
    def ingest_file(self, filepath):
        """
        Reads a file and saves it to Gaia's memory.
        """
        if not os.path.exists(filepath):
            logger.warning(f"⚠️ File not found: {filepath}")
            return False
        
        # [FIX] Check file size before reading to skip empty files
        try:
            file_size = os.path.getsize(filepath)
            if file_size < self.min_file_size:
                # logger.info(f"⏩ Skipping tiny/empty file: {filepath} ({file_size} bytes)")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to check file size {filepath}: {e}")
            return False
            
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # [FIX] Double-check content after reading (whitespace-only files)
            if not content.strip():
                # logger.info(f"⏩ Skipping whitespace-only file: {filepath}")
                return False
                
            # Create a unique ID for this version of the file
            file_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Use relative path for tags to identify the file cleanly
            rel_path = os.path.relpath(filepath, self.root_dir).replace("\\", "/")
            
            # [SYSTEM AWARENESS] Add specific tag for architecture files
            extra_tags = ""
            if "system_architecture" in rel_path or "registry.json" in rel_path or "intent_config.json" in rel_path:
                extra_tags = "system_architecture, core_knowledge"
            
            # [FIX] Chunk large files to prevent embedding API limit errors
            if len(content) > self.max_chunk_chars:
                return self._ingest_chunked(content, rel_path, file_hash, extra_tags)
            else:
                # Small file - embed as-is
                tags = f"source_code, {rel_path}, {file_hash}"
                
                # [SYSTEM AWARENESS] Add specific tag for architecture files
                if "system_architecture" in rel_path or "registry.json" in rel_path or "intent_config.json" in rel_path:
                    tags += ", system_architecture, core_knowledge"
                
                virtual_user = f"system_{rel_path}"
                
                if self.brain.record(content, user_name=virtual_user, tags=tags, source="source_code"):
                    return True
                else:
                    return False

        except Exception as e:
            logger.error(f"❌ Failed to ingest {filepath}: {e}")
            return False
    
    def _ingest_chunked(self, content, rel_path, file_hash, extra_tags=""):
        """
        Splits large file content into chunks and ingests each separately.
        """
        chunks = self._chunk_content(content)
        logger.info(f"📄 Chunking large file: {rel_path} ({len(chunks)} chunks)")
        
        success_count = 0
        for i, chunk in enumerate(chunks):
            # Create unique tags for each chunk
            chunk_tags = f"source_code, {rel_path}, {file_hash}, chunk_{i+1}_of_{len(chunks)}"
            if extra_tags:
                chunk_tags += f", {extra_tags}"

            virtual_user = f"system_{rel_path}_chunk_{i+1}"
            
            if self.brain.record(chunk, user_name=virtual_user, tags=chunk_tags, source="source_code"):
                success_count += 1
        
        return success_count == len(chunks)
    
    def _chunk_content(self, content):
        """
        Splits content into chunks, preserving line boundaries.
        """
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for line in lines:
            line_size = len(line) + 1  # +1 for newline
            
            if current_size + line_size > self.max_chunk_chars and current_chunk:
                # Save current chunk
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_size = line_size
            else:
                current_chunk.append(line)
                current_size += line_size
        
        # Add remaining chunk
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return chunks

    def ingest_all(self):
        """
        Ingests all target files using RECURSIVE SCAN (Omniscient Mode).
        """
        return self.scan_directory(self.root_dir)

    def scan_directory(self, root_dir):
        """
        Recursively scans the directory and ingests valid files.
        """
        logger.info(f"📚 Starting recursive code scan from: {root_dir}")
        count = 0
        scanned_dirs = 0
        
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Filtering directories
            dirnames[:] = [d for d in dirnames if d not in self.ignore_dirs]
            scanned_dirs += 1
            
            for filename in filenames:
                if filename in self.ignore_files:
                    continue
                    
                _, ext = os.path.splitext(filename)
                if ext in self.include_exts:
                    filepath = os.path.join(dirpath, filename)
                    if self.ingest_file(filepath):
                        count += 1
                        # Optional: Print progress every 10 files
                        if count % 10 == 0:
                            logger.info(f"   ...learned {count} files so far...")
                            
        logger.info(f"✅ OMNISCIENT SCAN COMPLETE.\nScanned {scanned_dirs} directories.\nIngested {count} source files.")
        return count
