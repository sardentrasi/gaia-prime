"""
Gaia Prime - Module Manager (Tools Layer)
Handles tmux-based module lifecycle: start/stop/forge/upgrade/rollback/purge.
Extracted from GaiaSystem module management methods.
"""

import os
import sys
import json
import shutil
import logging
import subprocess
import time
from datetime import datetime

import libtmux
import pyotp
from dotenv import set_key, find_dotenv

logger = logging.getLogger("ModuleManager")

# Telegram Error Whitelist (Network Issues - Don't Trigger Lazarus)
TELEGRAM_SAFE_ERRORS = [
    "Conflict: terminated by other getUpdates",
    "Error while getting Updates: Conflict",
    "TimedOut", "TimeoutError", "NetworkError",
    "Connection aborted", "Read timed out",
    "httpx.ReadTimeout", "httpx.ConnectTimeout",
    "telegram.error.TimedOut", "telegram.error.NetworkError",
    "telegram.error.Conflict"
]


class ModuleManager:
    """
    Module lifecycle manager for Gaia Prime.
    Controls tmux panes, registry, security, and module operations.
    """

    def __init__(self, llm_engine=None, brain=None, lazarus=None, ingester=None):
        """
        Args:
            llm_engine: PolyglotEngine instance for AI-powered operations
            brain: GaiaBrain instance for memory
            lazarus: LazarusGuardian instance for self-healing
            ingester: CodeIngester instance for codebase learning
        """
        self.engine = llm_engine
        self.brain = brain
        self.lazarus = lazarus
        self.ingester = ingester
        
        # Tmux connection
        self.server = libtmux.Server()
        self.session = self.find_session("gaia_net")
        if not self.session:
            logger.error("Tmux session 'gaia_net' not found! Please run start_prime.sh first.")
            # Don't exit here — allow graceful degradation
        
        self.window = None
        if self.session:
            self.window = self.session.windows.get(window_name="command_center")
            if not self.window:
                logger.error("Window 'command_center' not found!")
        
        # Dynamic Module Registry
        self.registry_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                           "..", "registry.json")
        # Normalize path
        self.registry_file = os.path.abspath(self.registry_file)
        self.modules = self.load_registry()
        
        # Log Cursor Memory
        self.log_cursors = {}
        
        # [SENTINEL] Retry Counters (3-Strike Rule)
        self.retry_counts = {}
        
        # Security
        self.alpha_key = os.getenv("GAIA_SECRET_ALPHA")
        self.omega_key = os.getenv("GAIA_SECRET_OMEGA")
        self.security_active = bool(self.alpha_key and self.omega_key)
        
        if not self.security_active:
            logger.warning("⚠️ Security Inactive. Run /setup_security to generate keys.")
        
        # Multi-user access
        users_str = os.getenv("USERS_ALLOWED", "")
        _telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        _raw_chat_id = _telegram_chat_id if _telegram_chat_id is not None else os.getenv("MY_USER_ID", "0")
        try:
            telegram_chat_id = int(_raw_chat_id)
        except (ValueError, TypeError):
            telegram_chat_id = 0
        self.allowed_users = [int(x) for x in users_str.split(',') if x.strip().isdigit()]
        if telegram_chat_id != 0 and telegram_chat_id not in self.allowed_users:
            self.allowed_users.append(telegram_chat_id)
        
        # Initial Sync
        self.sync_panes()
        logger.info(f"✅ ModuleManager initialized | Modules: {list(self.modules.keys())}")

    # ─── TMUX OPERATIONS ───

    def find_session(self, session_name):
        try:
            return self.server.sessions.get(session_name=session_name)
        except Exception as e:
            logger.error(f"Error connecting to Tmux: {e}")
            return None

    def sync_panes(self):
        """Match Tmux panes with modules based on pane title (metadata)."""
        self.modules = self.load_registry()
        if not self.window:
            return
        try:
            all_panes = self.window.panes
            for name, config in self.modules.items():
                target_pane = None
                for pane in all_panes:
                    try:
                        title = pane.cmd('display-message', '-p', '#T').stdout[0].strip()
                        if title == name:
                            target_pane = pane
                            break
                    except Exception:
                        continue
                
                if target_pane:
                    config['pane'] = target_pane
                    logger.info(f"🏷️ IDENTITY LOCK: '{name}' linked to Pane {target_pane.pane_id}")
                    log_file = config.get('log') or os.path.join(config.get('path', name), f"{name}.log")
                    if log_file and os.path.exists(log_file) and self.log_cursors.get(name, 0) == 0:
                        self.log_cursors[name] = os.path.getsize(log_file)
                else:
                    config['pane'] = None
        except Exception as e:
            logger.error(f"Sync Error: {e}")

    def get_pane(self, module_name):
        if module_name not in self.modules:
            return None
        return self.modules[module_name].get("pane")

    def is_running(self, module_name):
        pane = self.get_pane(module_name)
        if not pane:
            self.sync_panes()
            pane = self.get_pane(module_name)
        if not pane:
            return False
        try:
            tty_device = pane.pane_tty
            if not tty_device:
                return False
            tty_name = tty_device.replace("/dev/", "")
            result = subprocess.run(
                ["pgrep", "-t", tty_name, "-f", "python"],
                capture_output=True, text=True
            )
            return bool(result.stdout.strip())
        except Exception as e:
            logger.error(f"Error checking status for {module_name}: {e}")
            return False

    def start_module(self, module_name):
        if self.is_running(module_name):
            return False, "Already running"
        pane = self.get_pane(module_name)
        if not pane:
            self.sync_panes()
            pane = self.get_pane(module_name)
        if not pane:
            return False, "Pane not found (Module might need /initialize if new)"
        
        logger.info(f"Igniting {module_name}...")
        pane.send_keys("C-c", enter=False)
        
        try:
            config = self.modules[module_name]
            log_path = os.path.join(config["path"], f"{module_name}.log")
            self.log_cursors[module_name] = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        except Exception:
            pass
        
        script = f"{module_name}_main.py"
        full_path = os.path.abspath(self.modules[module_name]['path'])
        cmd = f"cd {full_path} && ./venv/bin/python3 -u {script}"
        pane.send_keys(cmd, enter=True)
        return True, "Ignition sequence started"

    def stop_module(self, module_name):
        if not self.is_running(module_name):
            return False, "Not running"
        pane = self.get_pane(module_name)
        if not pane:
            return False, "Pane not found"
        logger.info(f"Stopping {module_name}...")
        pane.send_keys("C-c", enter=False)
        return True, "Stop signal sent"

    def ignite_all_systems(self):
        logger.info("IGNITION SEQUENCE STARTED.")
        for module in self.modules:
            if self.modules[module].get("active", False):
                if not self.is_running(module):
                    self.start_module(module)

    # ─── SENTINEL (LOG MONITORING) ───

    def check_logs(self, module_name):
        try:
            config = self.modules[module_name]
            log_path = os.path.join(config["path"], f"{module_name}.log")
            if not os.path.exists(log_path):
                return None
            current_size = os.path.getsize(log_path)
            last_pos = self.log_cursors.get(module_name, 0)
            if current_size < last_pos:
                last_pos = 0
            if current_size == last_pos:
                return None
            
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(last_pos)
                new_logs = f.read()
            self.log_cursors[module_name] = current_size
            
            if "Traceback" in new_logs:
                if "KeyboardInterrupt" in new_logs:
                    return None
                for safe_error in TELEGRAM_SAFE_ERRORS:
                    if safe_error in new_logs:
                        logger.warning(f"⚠️ Telegram network error in {module_name}, ignoring: {safe_error}")
                        return None
                return "\n".join(new_logs.strip().splitlines()[-15:])
            return None
        except Exception as e:
            logger.error(f"Sentinel Error ({module_name}): {e}")
            return None

    def heal_module(self, module_name, error_snippet):
        """Delegate healing to Lazarus Protocol."""
        if not self.lazarus:
            return False, "Lazarus not initialized"
        module_path = os.path.abspath(self.modules[module_name]["path"])
        return self.lazarus.diagnose_and_heal(module_name, module_path, error_snippet, self.modules)

    # ─── REGISTRY ───

    def load_registry(self):
        try:
            with open(self.registry_file, "r") as f:
                data = json.load(f)
                reserved_keys = []
                return {k: v for k, v in data.items() if k not in reserved_keys}
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("Registry file not found or empty. Starting fresh.")
            return {}

    def save_registry(self):
        to_save = {}
        for name, data in self.modules.items():
            to_save[name] = {k: v for k, v in data.items() if k != 'pane'}
        if hasattr(self, 'extra_registry_config'):
            to_save.update(self.extra_registry_config)
        with open(self.registry_file, "w") as f:
            json.dump(to_save, f, indent=2)

    # ─── FORGE / INITIALIZE / UPGRADE / ROLLBACK / PURGE ───

    def _load_brain_file(self, filename):
        root = os.path.dirname(self.registry_file)
        candidate_paths = [
            os.path.join(root, "prompts", "brains", filename),
            os.path.join(root, filename),
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read()
        return ""

    def _load_furnace_brain(self, name, desc):
        default_template = (
            "Create a python telegram bot named {name}. "
            "Description: {desc}. "
            "Use python-telegram-bot v20+. Return ONLY code."
        )
        template = self._load_brain_file("brain_furnace.md") or default_template
        return template.format(name=name, desc=desc)

    def _clean_json_text(self, text):
        if not text:
            return "{}"
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            if len(lines) > 2:
                clean = "\n".join(lines[1:-1])
            else:
                clean = clean.replace("```json", "").replace("```python", "").replace("```", "")
        return clean.strip()

    def _get_main_script_path(self, name, module_path):
        """Return the primary main script path for a module ({name}_main.py with fallback to main.py)."""
        path = os.path.join(module_path, f"{name}_main.py")
        if not os.path.exists(path):
            path = os.path.join(module_path, "main.py")
        return path

    def _get_rag_context(self, name, module_path):
        """Read requirements.txt and source code for AI operations."""
        reqs = ""
        code = ""
        try:
            req_path = os.path.join(module_path, "requirements.txt")
            if os.path.exists(req_path):
                with open(req_path, "r") as f:
                    reqs = f.read()
            source_file = self._get_main_script_path(name, module_path)
            if os.path.exists(source_file):
                with open(source_file, "r", encoding="utf-8") as f:
                    code = f.read()
        except Exception as e:
            logger.error(f"Error reading RAG context for {name}: {e}")
        return reqs, code

    async def forge_bot(self, name, description):
        if not self.engine:
            return False, "LLM Engine not available."
        root = os.path.dirname(self.registry_file)
        base_path = os.path.join(root, name)
        if os.path.exists(base_path):
            return False, f"Module '{name}' already exists."

        logger.info(f"🔨 FURNACE: Forging code for {name} using Gaia DNA...")
        try:
            prompt = self._load_furnace_brain(name, description)
            try:
                response = self.engine.ask(prompt)
                initial_code = response.replace("```python", "").replace("```", "").strip()
            except Exception as e:
                return False, f"AI Generation Failed: {e}"
            
            os.makedirs(base_path, exist_ok=True)
            with open(os.path.join(base_path, f"{name}_main.py"), "w") as f:
                f.write(initial_code)
            with open(os.path.join(base_path, "requirements.txt"), "w") as f:
                f.write("python-telegram-bot==20.0\npython-dotenv\ngoogle-genai\n")
            with open(os.path.join(base_path, ".env"), "w") as f:
                f.write(f"TELEGRAM_TOKEN=\n")
                f.write(f"LLM_API_KEY={self.engine.primary_key}\n")
                f.write(f"LLM_MODEL={self.engine.model}\n")
            os.makedirs(os.path.join(base_path, "backups"), exist_ok=True)
            
            logger.info(f"📦 Creating venv for {name}...")
            subprocess.run([sys.executable, "-m", "venv", "venv"], cwd=base_path, check=True)
            venv_pip = os.path.join(base_path, "venv", "bin", "pip")
            subprocess.run([venv_pip, "install", "-r", "requirements.txt"], cwd=base_path, check=True)
            
            # Update module_identity.json
            identity_file = os.path.join(root, "module_identity.json")
            identities = {}
            if os.path.exists(identity_file):
                try:
                    with open(identity_file, "r", encoding="utf-8") as idf:
                        identities = json.load(idf)
                except Exception:
                    pass
            identities[name] = {
                "role": description[:60] + "..." if len(description) > 60 else description,
                "active": False
            }
            with open(identity_file, "w", encoding="utf-8") as idf:
                json.dump(identities, idf, indent=4)
            
            return True, f"Unit {name} forged successfully with Gaia Architecture."
        except Exception as e:
            logger.error(f"Furnace Error: {e}")
            os.makedirs(base_path, exist_ok=True)
            with open(os.path.join(base_path, f"{name}_main.py"), "w") as f:
                f.write(f"# Error generating code: {e}\n# Please edit manually.")
            return True, f"Unit {name} forged (Structure Only). AI Generation Failed."

    def initialize_bot(self, name):
        if name in self.modules:
            return False, "Module already initialized."
        root = os.path.dirname(self.registry_file)
        path = os.path.join(root, name)
        if not os.path.exists(path):
            return False, f"Directory '{name}' not found. Forge it first?"
        
        self.modules[name] = {"path": name, "active": True}
        self.save_registry()
        
        # Update module_identity.json
        identity_file = os.path.join(root, "module_identity.json")
        identities = {}
        if os.path.exists(identity_file):
            try:
                with open(identity_file, "r", encoding="utf-8") as idf:
                    identities = json.load(idf)
            except Exception:
                pass
        if name in identities:
            identities[name]["active"] = True
        else:
            identities[name] = {"role": "Newly Initialized Subsystem", "active": True}
        with open(identity_file, "w", encoding="utf-8") as idf:
            json.dump(identities, idf, indent=4)
        
        self.modules = self.load_registry()
        
        if not self.window:
            return False, "Tmux window not available"
        try:
            pane = self.window.split(attach=False)
            self.window.select_layout("tiled")
            try:
                pane.cmd('select-pane', '-T', name)
            except:
                pass
            full_path = os.path.abspath(name)
            cmd = f"cd {full_path} && ./venv/bin/python3 -u {name}_main.py"
            pane.send_keys("clear", enter=True)
            pane.send_keys(cmd, enter=True)
            self.sync_panes()
            return True, f"Module '{name}' initialized and ignited."
        except Exception as e:
            return False, f"Tmux deployment failed: {e}"

    async def upgrade_module(self, name, instruction):
        if name not in self.modules:
            return False, "Module not found"
        self.stop_module(name)
        
        root = os.path.dirname(self.registry_file)
        backup_dir = os.path.join(root, "backups", name)
        os.makedirs(backup_dir, exist_ok=True)
        
        module_path = os.path.abspath(self.modules[name]["path"])
        source_file = self._get_main_script_path(name, module_path)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(source_file, os.path.join(backup_dir, f"main_PRE_UPGRADE_{ts}.py"))
        
        reqs, code = self._get_rag_context(name, module_path)
        brain = self._load_brain_file("brain_evolution.md")
        if not brain:
            return False, "brain_evolution.md missing"
        
        prompt = brain.format(module_name=name, instruction=instruction, requirements=reqs, code=code)
        
        try:
            response = self.engine.ask(prompt, json_mode=True)
            clean_json = self._clean_json_text(response)
            data = json.loads(clean_json)
            
            with open(source_file, "w", encoding="utf-8") as f:
                f.write(data["main.py"])
            if "requirements.txt" in data:
                with open(os.path.join(module_path, "requirements.txt"), "w") as f:
                    f.write(data["requirements.txt"])
            if "changelog_entry" in data:
                with open(os.path.join(module_path, "changelog.txt"), "a") as f:
                    f.write(f"\n[{ts}] {data['changelog_entry']}")
            
            venv_pip = os.path.join(module_path, "venv", "bin", "pip")
            subprocess.run([venv_pip, "install", "-r", "requirements.txt"], cwd=module_path, check=False)
            self.start_module(name)
            
            report = f"✅ **UPGRADE COMPLETE**\n\n📜 Changelog:\n{data.get('changelog_entry')}"
            if data.get("env_warnings"):
                report += f"\n\n⚠️ **ENV WARNING**: {data['env_warnings']}"
            return True, report
        except Exception as e:
            logger.error(f"Upgrade Failed: {e}")
            self.start_module(name)
            return False, f"Upgrade Failed: {e}"

    def rollback_module(self, name):
        if name not in self.modules:
            return False, "Module not found"
        root = os.path.dirname(self.registry_file)
        backup_dir = os.path.join(root, "backups", name)
        if not os.path.exists(backup_dir):
            return False, "No backup history found."
        backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir)], key=os.path.getmtime)
        if not backups:
            return False, "Backup folder empty."
        target_backup = backups[-1]
        module_path = os.path.abspath(self.modules[name]["path"])
        dest_file = self._get_main_script_path(name, module_path)
        shutil.copy2(target_backup, dest_file)
        self.stop_module(name)
        time.sleep(1)
        self.start_module(name)
        return True, f"Rolled back to {os.path.basename(target_backup)}"

    def purge_module(self, name, level, otp):
        if not self.verify_access(level, otp):
            return False, "⛔ Access Denied. Authorization Invalid."
        if name not in self.modules:
            return False, "Module not found."
        try:
            self.stop_module(name)
            pane = self.get_pane(name)
            if pane:
                try:
                    pane.send_keys("exit", enter=True)
                except:
                    pass
            config = self.modules.pop(name)
            self.save_registry()
            if self.window:
                self.window.select_layout("tiled")
            
            root = os.path.dirname(self.registry_file)
            identity_file = os.path.join(root, "module_identity.json")
            if os.path.exists(identity_file):
                try:
                    with open(identity_file, "r", encoding="utf-8") as idf:
                        identities = json.load(idf)
                    if name in identities:
                        del identities[name]
                        with open(identity_file, "w", encoding="utf-8") as idf:
                            json.dump(identities, idf, indent=4)
                except Exception as e:
                    logger.warning(f"⚠️ Could not purge module_identity.json: {e}")
            
            msg = f"Module '{name}' has been decommissioned (Soft Delete)."
            if level == 'omega':
                module_path = os.path.abspath(config['path'])
                shutil.rmtree(module_path)
                msg = f"Module '{name}' has been INCINERATED (Hard Delete)."
            return True, msg
        except Exception as e:
            return False, f"Purge failed: {e}"

    async def audit_module(self, name):
        if name not in self.modules:
            return False, "Module not found"
        module_path = os.path.abspath(self.modules[name]["path"])
        reqs, code = self._get_rag_context(name, module_path)
        brain = self._load_brain_file("brain_auditor.md")
        if not brain:
            return False, "brain_auditor.md missing"
        prompt = brain.format(module_name=name, code=code)
        try:
            response = self.engine.ask(prompt)
            return True, response
        except Exception as e:
            return False, f"Audit Error: {e}"

    # ─── SECURITY ───

    def check_auth(self, user_id: int) -> bool:
        return user_id in self.allowed_users

    def verify_security(self, level, input_otp):
        level = level.lower()
        key = None
        if level == 'alpha':
            key = self.alpha_key
        elif level == 'omega':
            key = self.omega_key
        else:
            return False
        if not key:
            return False
        totp = pyotp.TOTP(key)
        return totp.verify(input_otp)

    def verify_access(self, level, otp):
        if not self.security_active:
            return False
        try:
            totp_alpha = pyotp.TOTP(self.alpha_key)
            totp_omega = pyotp.TOTP(self.omega_key)
            is_alpha = totp_alpha.verify(otp)
            is_omega = totp_omega.verify(otp)
            if level == 'omega':
                return is_omega
            elif level == 'alpha':
                return is_alpha or is_omega
            return False
        except Exception:
            return False

    def generate_keys(self):
        env_file = find_dotenv()
        if not env_file:
            with open(".env", "w") as f:
                pass
            env_file = ".env"
        current_alpha = os.getenv("GAIA_SECRET_ALPHA")
        if current_alpha:
            return False, None, None
        alpha_key = pyotp.random_base32()
        omega_key = pyotp.random_base32()
        set_key(env_file, "GAIA_SECRET_ALPHA", alpha_key)
        set_key(env_file, "GAIA_SECRET_OMEGA", omega_key)
        self.alpha_key = alpha_key
        self.omega_key = omega_key
        self.security_active = True
        return True, alpha_key, omega_key

    # ─── HELP ───

    def get_help_text(self):
        root = os.path.dirname(self.registry_file)
        file_path = os.path.join(root, "help_interface.txt")
        default_text = (
            "💠 **GAIA PRIME ORCHESTRATOR**\n"
            "System Online.\n\n"
            "Commands:\n"
            "/status - Check Status\n"
            "/forge - Create Bot\n"
            "/purge - Delete Bot\n"
            "/help - Show Help"
        )
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return default_text
        return default_text
