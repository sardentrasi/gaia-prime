import os
import logging
import re
import json
import shutil
import time
from datetime import datetime, timedelta
from litellm import completion
from gaia_memory_manager import GaiaBrain

logger = logging.getLogger("Lazarus")

class LazarusGuardian:
    def __init__(self, brain: GaiaBrain, model_name: str, api_key: str):
        self.brain = brain
        self.model = model_name
        self.api_key = api_key

    def _get_surgical_context(self, source_file, error_log, window=50):
        """
        Extracts only necessary context: 
        1. Last 20 lines of log (the error)
        2. Surgical window of source code (100 lines around error if known, else first 200 lines)
        """
        code_snippet = ""
        try:
            # 1. Parse Line Number
            match = re.search(r'line (\d+)', error_log)
            target_line = int(match.group(1)) if match else 1
            
            if os.path.exists(source_file):
                with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                
                # Surgical Window: 50 lines before, 50 lines after
                start = max(0, target_line - window - 1)
                end = min(len(lines), target_line + window)
                
                snippet_lines = []
                for i in range(start, end):
                    snippet_lines.append(f"{i+1}: {lines[i].rstrip()}")
                code_snippet = "\n".join(snippet_lines)
            else:
                code_snippet = "# [ERROR] Source file not found on disk."
        except Exception as e:
            code_snippet = f"# [ERROR] Context extraction failed: {e}"

        return code_snippet

    def diagnose_and_heal(self, module_name, module_path, error_snippet, modules_config):
        """
        Refactored Lazarus Protocol (Token Optimized):
        1. Strike Check
        2. Surgical Context (Disk only)
        3. LLM Fix
        4. Application & Execution
        """
        logger.info(f"🚑 [LAZARUS] Initiating Modular Healing for: {module_name}")
        
        # A. Resolve Source Path
        source_file = os.path.join(module_path, f"{module_name}_main.py")
        if not os.path.exists(source_file):
            source_file = os.path.join(module_path, "main.py")
        
        if not os.path.exists(source_file):
            return False, "Source file missing"

        # B. Central Backup Setup
        gaia_root = os.getcwd()
        backup_dir = os.path.join(gaia_root, "backups", module_name)
        os.makedirs(backup_dir, exist_ok=True)
        
        # 3-Strike Check (Simplified)
        now = datetime.now()
        ten_mins_ago = now - timedelta(minutes=10)
        recent_backups = [f for f in os.listdir(backup_dir) 
                         if datetime.fromtimestamp(os.path.getmtime(os.path.join(backup_dir, f))) > ten_mins_ago]
        
        if len(recent_backups) >= 3:
            return False, "3-Strike Limit Hit. Manual intervention required."

        # C. Create Metadata-Rich Backup
        ts = now.strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"{module_name}.bk_{ts}.py")
        shutil.copy2(source_file, backup_path)

        # D. Surgical Context (NO GLOBAL LEARN)
        code_context = self._get_surgical_context(source_file, error_snippet)
        
        # E. AI Consult (Load from MD Brain)
        brain_path = os.path.join(os.getcwd(), "brain_lazarus.md")
        default_prompt = "You are Lazarus. Fix this error: {error_snippet}\nCode: {code_context}\nReturn ONLY JSON."
        
        if os.path.exists(brain_path):
            with open(brain_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        else:
            prompt_template = default_prompt

        prompt = prompt_template.format(
            module_name=module_name,
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
            error_snippet=error_snippet,
            code_context=code_context
        )

        try:
            # We use a combined single prompt for simplicity when loading from file
            msgs = [{"role": "user", "content": prompt}]
            response = completion(model=self.model, messages=msgs, api_key=self.api_key, response_format={"type": "json_object"})
            data = json.loads(response.choices[0].message.content)
            
            fixed_code = data.get('fixed_code')
            shell_cmd = data.get('shell_command')
            explanation = data.get('explanation', 'Healed by AI.')

            if not fixed_code: raise Exception("AI failed to generate fix.")

            # Apply Shell Fix (if any)
            if shell_cmd:
                logger.info(f"🐚 [LAZARUS] SHELL CMD: {shell_cmd}")
                pane = modules_config.get(module_name, {}).get('pane')
                if pane:
                    pane.send_keys(shell_cmd, enter=True)
                    time.sleep(5)

            # Apply Code Fix
            with open(source_file, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            # Record Solution
            self.brain.record(f"Fixed {module_name} error: {explanation}", source="lazarus", tags="fix,auto")
            
            return True, explanation

        except Exception as e:
            logger.error(f"❌ Lazarus LLM Error: {e}")
            return False, str(e)
