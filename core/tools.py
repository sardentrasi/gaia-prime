"""
Gaia Prime - Tool Registry & Executors
Defines tools that the LLM can call autonomously via function calling.
Each tool has a schema (OpenAI format) and an executor function.
"""

import os
import re
import ast
import json
import logging
import subprocess
import time as time_module
from datetime import datetime
from typing import Dict, List, Any, Callable, Optional

import pytz

try:
    import libtmux
except ImportError:
    libtmux = None

logger = logging.getLogger("GaiaTools")

# Timezone
env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")


# ─── BLOCKED SHELL COMMANDS ───
BLOCKED_PATTERNS = [
    r"\brm\s+-rf\s+/",       # rm -rf /
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bhalt\b",
    r"\binit\s+0\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\{\s*:\|:&\s*\};:", # fork bomb
    r"\bformat\b.*\b[cCdD]:",
    r">\s*/dev/sd",
    r"\bchmod\s+-R\s+777\s+/\s*$",
    r"\bchown\s+-R\s+.*\s+/\s*$",
    # Prevent LLM from creating its own tmux/screen sessions
    r"\btmux\s+new-session\b",
    r"\btmux\s+new-window\b",
    r"\btmux\s+split-window\b",
    r"\btmux\s+split\b",
    r"\bscreen\s+-[dDmS]",
]

SHELL_TIMEOUT = 30  # seconds
SHELL_MAX_OUTPUT = 2000  # chars
GAIA_CMD_PANE = "gaia_cmd"  # tmux pane name for async commands

# Commands that are automatically routed to tmux pane (no timeout)
LONG_RUNNING_PATTERNS = [
    "apt ", "apt-get ", "dpkg ", "pip ", "pip3 ",
    "npm ", "yarn ", "cargo ", "go build", "make",
    "cmake", "docker ", "git clone", "git pull",
    "wget ", "curl -o", "curl -O", "scp ", "rsync ",
    "tar ", "unzip ", "zip ", "gzip ",
    "systemctl ", "service ",
    "python3 -m pip", "python -m pip",
]


class ToolRegistry:
    """
    Central registry for all tools available to the Gaia Agent Loop.
    Provides tool schemas for LLM function calling and executor dispatch.
    """

    def __init__(self, brain=None, context=None, root_dir: str = None, cron=None):
        """
        Args:
            brain: GaiaBrain instance for memory_search
            context: ContextManager instance for module status
            root_dir: Gaia Prime root directory
            cron: CronScheduler instance for scheduled tasks
        """
        self.brain = brain
        self.context = context
        self.root_dir = root_dir or os.getcwd()
        self.cron = cron

        # Tool executor map: name → callable
        self._executors: Dict[str, Callable] = {
            "memory_search": self._exec_memory_search,
            "record_memory": self._exec_record_memory,
            "get_module_status": self._exec_get_module_status,
            "get_current_time": self._exec_get_current_time,
            "calculate": self._exec_calculate,
            "execute_shell": self._exec_execute_shell,
            "check_command_output": self._exec_check_command_output,
            "create_cron": self._exec_create_cron,
            "list_cron": self._exec_list_cron,
            "delete_cron": self._exec_delete_cron,
            "list_pending": self._exec_list_pending,
            "postpone_cron": self._exec_postpone_cron,
        }

        # Tmux session reference (lazy init)
        self._tmux_pane = None

        # Pending async commands — heartbeat checks these
        self.pending_commands = []

    def get_tool_schemas(self) -> List[dict]:
        """Returns OpenAI-compatible tool schemas for LLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "memory_search",
                    "description": (
                        "Search Gaia's long-term memory (ChromaDB) for relevant information. "
                        "Use this when you need to recall past conversations, stored knowledge, "
                        "news articles, or data from subsystems like Apollo, Demeter, Minerva."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to find relevant memories"
                            },
                            "filter_type": {
                                "type": "string",
                                "description": (
                                    "Optional filter for memory source. Examples: "
                                    "'apollo' (news), 'demeter' (garden), 'minerva' (market), "
                                    "'user_interaction', 'source_code'. Can combine with comma."
                                )
                            },
                            "n_results": {
                                "type": "integer",
                                "description": "Number of results to return (default: 5, max: 15)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "record_memory",
                    "description": (
                        "Save important information to Gaia's long-term memory (ChromaDB). "
                        "WAJIB gunakan tool ini ketika user meminta untuk mencatat, mengingat, "
                        "atau menyimpan suatu fakta/informasi. Trigger words: 'catat', 'ingat', "
                        "'simpan', 'record', 'remember', 'note', 'save'. "
                        "Simpan informasi dalam format yang jelas dan terstruktur agar mudah "
                        "ditemukan kembali saat dibutuhkan."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": (
                                    "The information to save. Write it as a clear, factual statement. "
                                    "Example: 'Puasa Ramadhan 2026 dimulai tanggal 17 Februari 2026'"
                                )
                            },
                            "tags": {
                                "type": "string",
                                "description": (
                                    "Comma-separated tags for categorization. "
                                    "Examples: 'ramadhan,puasa,jadwal', 'personal,catatan', 'fakta,penting'"
                                )
                            }
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_module_status",
                    "description": (
                        "Get real-time status of Gaia Prime subsystem modules. "
                        "Returns the latest actions and state from module short-term memory. "
                        "Available modules: apollo (news), demeter (garden), minerva (market), eleuthia (telegram)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "module_name": {
                                "type": "string",
                                "description": (
                                    "Specific module to check. "
                                    "If omitted, returns status of ALL active modules."
                                )
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": (
                        "Get the current date and time with timezone information. "
                        "Use this when user asks about the time, date, day of week, "
                        "or when you need accurate timing for scheduling."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": (
                        "Evaluate a mathematical expression safely. "
                        "Use this for any numerical computation to avoid calculation errors. "
                        "Supports: +, -, *, /, **, %, parentheses."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Mathematical expression to evaluate, e.g. '(15/100) * 2500000' or '2**10'"
                            }
                        },
                        "required": ["expression"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_shell",
                    "description": (
                        "Execute a shell command on the Gaia Prime server (Linux). "
                        "Use this for ANY system command: disk usage (df -h), uptime, "
                        "package install (apt install), pip install, file operations, "
                        "network checks, process management, etc. "
                        "Quick commands run directly with output returned immediately. "
                        "Long commands (apt, pip, npm, docker, wget, git clone) "
                        "are automatically routed to a tmux pane with no timeout. "
                        "You can also set background=true to force tmux mode for any command. "
                        "Use check_command_output to see results of background/long commands. "
                        "IMPORTANT: Do NOT create your own tmux sessions, windows, or panes. "
                        "Do NOT use 'tmux new-session', 'screen', or 'nohup &'. "
                        "Long commands are handled automatically. "
                        "Destructive commands (rm -rf /, shutdown, reboot) are blocked."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to execute, e.g. 'df -h', 'apt install -y traceroute', 'pip install requests'"
                            },
                            "background": {
                                "type": "boolean",
                                "description": "Set to true to run in tmux pane (no timeout). Use for long-running commands. Default: auto-detect."
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_command_output",
                    "description": (
                        "Read the latest output from the gaia_cmd tmux pane. "
                        "Use this after execute_shell runs a long command (apt, pip, etc.) "
                        "to check if it has finished and see the results."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lines": {
                                "type": "integer",
                                "description": "Number of lines to read from the pane (default: 50, max: 200)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_cron",
                    "description": (
                        "Create a scheduled task (cron job) that Gaia will execute automatically. "
                        "Use this when the user wants recurring reports, morning briefings, "
                        "evening summaries, periodic checks, or any timed action. "
                        "Schedule formats: 'daily HH:MM', 'weekday HH:MM', 'weekend HH:MM', "
                        "'every Xh', 'every Xm', 'once YYYY-MM-DDTHH:MM'."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Human-readable name for the job, e.g. 'Morning Briefing', 'Disk Check'"
                            },
                            "schedule": {
                                "type": "string",
                                "description": (
                                    "Schedule expression. Examples: 'daily 06:00', 'weekday 08:00', "
                                    "'weekend 10:00', 'every 6h', 'every 30m', 'once 2026-03-05T14:00'"
                                )
                            },
                            "action": {
                                "type": "string",
                                "description": (
                                    "The instruction/prompt that Gaia will execute when the job triggers. "
                                    "This goes through the full Agent Loop (LLM + tools). "
                                    "Example: 'Berikan ringkasan berita pagi dan kondisi tanaman Demeter'"
                                )
                            },
                            "platform": {
                                "type": "string",
                                "description": "Delivery platform: 'telegram'. If not specified, auto-detects from the current chat platform."
                            }
                        },
                        "required": ["name", "schedule", "action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_cron",
                    "description": (
                        "List all scheduled cron jobs. Shows job name, schedule, action, "
                        "enabled status, and last run time."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_cron",
                    "description": (
                        "Delete a scheduled cron job by its ID or name. "
                        "Use list_cron first to see available jobs and their IDs."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_id": {
                                "type": "string",
                                "description": "The ID or name of the cron job to delete"
                            }
                        },
                        "required": ["job_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_pending",
                    "description": (
                        "List all pending reminders and scheduled one-shot tasks that haven't fired yet. "
                        "Use when user asks 'cek pengingat', 'ada reminder apa', 'jadwal apa saja', "
                        "'pending reminder', or any question about upcoming scheduled tasks."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "postpone_cron",
                    "description": (
                        "Postpone or reschedule a pending reminder or cron job to a new time. "
                        "Use when user says 'tunda', 'postpone', 'reschedule', 'geser jadwal', "
                        "'mundurkan'. Use list_pending first to find the job ID."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_id": {
                                "type": "string",
                                "description": "ID or name of the job to postpone (from list_pending or list_cron)"
                            },
                            "new_time": {
                                "type": "string",
                                "description": "New time in ISO-8601 format, e.g. '2026-03-05T18:00'"
                            }
                        },
                        "required": ["job_id", "new_time"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, arguments: dict) -> str:
        """
        Execute a tool by name with given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Dict of arguments from LLM function call
            
        Returns:
            String result to feed back to LLM
        """
        executor = self._executors.get(tool_name)
        if not executor:
            return f"Error: Unknown tool '{tool_name}'"

        try:
            logger.info(f"🔧 [TOOL] Executing: {tool_name}({json.dumps(arguments, ensure_ascii=False)[:100]})")
            result = executor(**arguments)
            logger.info(f"✅ [TOOL] {tool_name} completed ({len(str(result))} chars)")
            return result
        except Exception as e:
            error_msg = f"Tool execution error ({tool_name}): {e}"
            logger.error(f"❌ [TOOL] {error_msg}")
            return error_msg

    # ─── TOOL EXECUTORS ───

    def _exec_memory_search(self, query: str, filter_type: str = None, n_results: int = 5, **kwargs) -> str:
        """Search ChromaDB memory."""
        if not self.brain:
            return "Memory system not available."

        n_results = min(max(n_results, 1), 15)

        try:
            results = self.brain.remember(
                query=query,
                n_results=n_results,
                filter_type=filter_type
            )
            if not results:
                return f"No memories found for query: '{query}'"
            return results
        except Exception as e:
            return f"Memory search failed: {e}"

    def _exec_record_memory(self, text: str, tags: str = "catatan_penting", **kwargs) -> str:
        """Save a fact/note to ChromaDB with high priority for reliable retrieval."""
        if not self.brain:
            return "Memory system not available."

        try:
            success = self.brain.record(
                text=text,
                user_name="Gaia",
                tags=tags,
                source="gaia_noted",
                priority=9  # High priority for user-requested saves
            )
            if success:
                return f"✅ Berhasil dicatat ke memori jangka panjang.\nIsi: {text}\nTags: {tags}"
            else:
                return "❌ Gagal menyimpan ke memori."
        except Exception as e:
            return f"❌ Error saat menyimpan memori: {e}"

    def _exec_get_module_status(self, module_name: str = None, **kwargs) -> str:
        """Read module state files for real-time status."""
        identity_file = os.path.join(self.root_dir, "module_identity.json")

        if not os.path.exists(identity_file):
            return "Module identity file not found. No modules registered."

        try:
            with open(identity_file, "r", encoding="utf-8") as f:
                identities = json.load(f)
        except Exception as e:
            return f"Failed to read module identities: {e}"

        # Filter to specific module if requested
        if module_name:
            module_name = module_name.lower()
            if module_name not in identities:
                available = ", ".join(identities.keys())
                return f"Module '{module_name}' not found. Available: {available}"
            identities = {module_name: identities[module_name]}

        reports = []
        for name, info in identities.items():
            status = "🔴 Inactive" if not info.get("active", False) else "🟢 Active"
            role = info.get("role", "Unknown")

            state_file = os.path.join(self.root_dir, name, f"{name}_state.json")
            state_info = "No state data available."

            if os.path.exists(state_file):
                try:
                    with open(state_file, "r", encoding="utf-8") as sf:
                        state_data = json.load(sf)

                    memories = state_data.get("short_term_memory", [])
                    if memories:
                        latest = memories[-1]
                        state_info = (
                            f"Last action: '{latest.get('action', 'N/A')}' "
                            f"at {latest.get('timestamp', 'N/A')}\n"
                            f"Result: {str(latest.get('result', ''))[:500]}"
                        )
                    else:
                        state_info = "Short-term memory is empty."
                except Exception as e:
                    state_info = f"Failed to read state: {e}"

            reports.append(f"[{name.upper()}] {status} | {role}\n{state_info}")

        return "\n\n".join(reports) if reports else "No modules found."

    def _exec_get_current_time(self, **kwargs) -> str:
        """Return current time with timezone info."""
        now = datetime.now(MY_TZ)
        days_id = {
            0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
            4: "Jumat", 5: "Sabtu", 6: "Minggu"
        }
        day_name = days_id.get(now.weekday(), now.strftime("%A"))

        return (
            f"Waktu sekarang: {now.strftime('%H:%M:%S')} {now.tzname()}\n"
            f"Tanggal: {day_name}, {now.strftime('%d %B %Y')}\n"
            f"Timezone: {env_timezone}\n"
            f"ISO: {now.isoformat()}"
        )

    def _exec_calculate(self, expression: str, **kwargs) -> str:
        """Safely evaluate a mathematical expression."""
        # Sanitize: only allow safe chars
        clean = expression.strip()
        if not re.match(r'^[\d\s\+\-\*\/\%\.\(\)\,\^]+$', clean):
            return f"Invalid expression: contains unsafe characters. Only math operators allowed."

        # Replace ^ with ** for power
        clean = clean.replace('^', '**')

        try:
            # Use compile + eval with empty namespace for safety
            code = compile(clean, "<calc>", "eval")
            # Verify no names are accessed (only literals and operators)
            for name in code.co_names:
                return f"Invalid expression: function calls not allowed."

            result = eval(code, {"__builtins__": {}}, {})
            return f"Expression: {expression}\nResult: {result}"
        except (SyntaxError, TypeError, ZeroDivisionError) as e:
            return f"Calculation error: {e}"
        except Exception as e:
            return f"Unexpected error: {e}"

    def _exec_execute_shell(self, command: str, background: bool = False, **kwargs) -> str:
        """Execute a shell command — LLM chooses mode + auto-detect as safety net."""
        command = command.strip()

        # Security check: blocked commands
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"⛔ BLOCKED: Command matches a dangerous pattern. Refused to execute: '{command}'"

        # Determine mode: LLM explicit choice OR auto-detect
        use_tmux = background or any(
            command.lower().startswith(p) or f" {p}" in command.lower()
            for p in LONG_RUNNING_PATTERNS
        )

        if use_tmux:
            # Route to tmux pane (no timeout)
            return self._exec_via_tmux(command)
        else:
            # Quick command via subprocess
            return self._exec_via_subprocess(command)

    def _exec_via_subprocess(self, command: str) -> str:
        """Run a quick command via subprocess with timeout."""
        logger.info(f"🖥️ [SHELL] Executing (subprocess): {command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=SHELL_TIMEOUT,
                cwd=self.root_dir
            )

            output = result.stdout.strip()
            errors = result.stderr.strip()

            parts = [f"Command: {command}", f"Exit Code: {result.returncode}"]

            if output:
                if len(output) > SHELL_MAX_OUTPUT:
                    output = output[:SHELL_MAX_OUTPUT] + "\n... [OUTPUT TRUNCATED]"
                parts.append(f"Output:\n{output}")

            if errors:
                if len(errors) > SHELL_MAX_OUTPUT:
                    errors = errors[:SHELL_MAX_OUTPUT] + "\n... [STDERR TRUNCATED]"
                parts.append(f"Stderr:\n{errors}")

            if not output and not errors:
                parts.append("(No output)")

            return "\n".join(parts)

        except subprocess.TimeoutExpired:
            return f"⏰ Command timed out after {SHELL_TIMEOUT}s. Retrying via tmux pane...\n" + self._exec_via_tmux(command)
        except Exception as e:
            return f"Shell execution error: {e}"

    def _exec_via_tmux(self, command: str, _msg_meta: dict = None) -> str:
        """Run a command in gaia_cmd tmux pane (no timeout)."""
        pane = self._get_cmd_pane()
        if not pane:
            return "❌ Cannot access tmux pane 'gaia_cmd'. Is Gaia running inside tmux session 'gaia_net'?"

        try:
            logger.info(f"🖥️ [SHELL] Executing (tmux): {command[:80]}...")
            pane.send_keys(command, enter=True)

            # Register as pending — heartbeat will auto-report when done
            msg_ctx = getattr(self, '_current_msg', {})
            self.pending_commands.append({
                "command": command,
                "started_at": datetime.now(MY_TZ).isoformat(),
                "platform": msg_ctx.get("platform", "telegram"),
                "target_id": msg_ctx.get("target_id", os.getenv("TELEGRAM_CHAT_ID", "")),
                "reported": False
            })

            return (
                f"✅ Long-running command sent to gaia_cmd pane:\n"
                f"{command}\n\n"
                f"Saya akan otomatis mengirim hasilnya ketika selesai."
            )
        except Exception as e:
            return f"❌ Failed to send command to tmux pane: {e}"

    # ─── CRON TOOL EXECUTORS ───

    def _exec_create_cron(self, name: str, schedule: str, action: str,
                          platform: str = None, **kwargs) -> str:
        """Create a new cron job."""
        if not self.cron:
            return "Cron scheduler not available."

        # Auto-detect platform and target_id from current message context
        msg_ctx = getattr(self, '_current_msg', {})
        if not platform:
            platform = msg_ctx.get("platform", "telegram")
        target_id = msg_ctx.get("target_id", "") or None

        try:
            job = self.cron.create_job(
                name=name,
                schedule=schedule,
                action=action,
                platform=platform,
                target_id=target_id
            )
            return (
                f"✅ Cron job created successfully!\n"
                f"ID: {job['id']}\n"
                f"Name: {job['name']}\n"
                f"Schedule: {job['schedule']}\n"
                f"Action: {job['action']}\n"
                f"Platform: {job['platform']}\n"
                f"Target: {job['target_id']}"
            )
        except Exception as e:
            return f"Failed to create cron job: {e}"

    def _exec_list_cron(self, **kwargs) -> str:
        """List all cron jobs."""
        if not self.cron:
            return "Cron scheduler not available."

        jobs = self.cron.list_jobs()
        if not jobs:
            return "No cron jobs found. Use create_cron to create one."

        lines = []
        for j in jobs:
            status = "🟢 Enabled" if j.get("enabled", True) else "🔴 Disabled"
            last_run = j.get("last_run", "Never")
            lines.append(
                f"[{j['id']}] {j['name']} {status}\n"
                f"  Schedule: {j['schedule']}\n"
                f"  Action: {j['action'][:80]}{'...' if len(j['action']) > 80 else ''}\n"
                f"  Platform: {j.get('platform', 'telegram')} | Runs: {j.get('run_count', 0)} | Last: {last_run}"
            )
        return "\n\n".join(lines)

    def _exec_delete_cron(self, job_id: str, **kwargs) -> str:
        """Delete a cron job."""
        if not self.cron:
            return "Cron scheduler not available."

        if self.cron.delete_job(job_id):
            return f"✅ Cron job '{job_id}' deleted successfully."
        else:
            return f"❌ Cron job '{job_id}' not found. Use list_cron to see available jobs."

    def _exec_list_pending(self, **kwargs) -> str:
        """List pending one-shot reminders/tasks."""
        if not self.cron:
            return "Cron scheduler not available."

        pending = self.cron.list_pending()
        if not pending:
            return "Tidak ada pengingat yang pending."

        lines = []
        for j in pending:
            schedule_time = j["schedule"][5:]  # Strip "once "
            lines.append(
                f"[{j['id']}] {j['name']}\n"
                f"  Jadwal: {schedule_time}\n"
                f"  Action: {j['action'][:80]}{'...' if len(j['action']) > 80 else ''}\n"
                f"  Platform: {j.get('platform', 'telegram')}"
            )
        return f"📋 Pending Reminders ({len(pending)}):\n\n" + "\n\n".join(lines)

    def _exec_postpone_cron(self, job_id: str, new_time: str, **kwargs) -> str:
        """Postpone a pending job to a new time."""
        if not self.cron:
            return "Cron scheduler not available."

        if self.cron.postpone_job(job_id, new_time):
            return f"✅ Job '{job_id}' berhasil ditunda ke {new_time}"
        return f"❌ Job '{job_id}' tidak ditemukan atau sudah dieksekusi."

    # ─── TMUX PANE HELPERS ───

    def _get_cmd_pane(self):
        """Get or create the gaia_cmd tmux pane."""
        if self._tmux_pane:
            # Verify pane still exists
            try:
                self._tmux_pane.cmd('display-message', '-p', '#{pane_id}')
                return self._tmux_pane
            except Exception:
                self._tmux_pane = None

        if not libtmux:
            return None

        try:
            server = libtmux.Server()
            session = server.sessions.get(session_name="gaia_net")
            if not session:
                return None

            window = session.windows.get(window_name="command_center")
            if not window:
                return None

            # Look for existing gaia_cmd pane
            for pane in window.panes:
                try:
                    title = pane.cmd('display-message', '-p', '#{pane_title}').stdout[0]
                    if title == GAIA_CMD_PANE:
                        self._tmux_pane = pane
                        logger.info(f"🖥️ [TMUX] Found existing {GAIA_CMD_PANE} pane")
                        return pane
                except Exception:
                    continue

            # Create new pane
            pane = window.split(attach=False)
            window.select_layout("tiled")
            pane.cmd('select-pane', '-T', GAIA_CMD_PANE)
            self._tmux_pane = pane
            logger.info(f"🖥️ [TMUX] Created new {GAIA_CMD_PANE} pane")
            time_module.sleep(0.5)
            return pane

        except Exception as e:
            logger.error(f"❌ [TMUX] Failed to get/create cmd pane: {e}")
            return None

    # ─── TMUX TOOL EXECUTORS ───

    def _exec_check_command_output(self, lines: int = 50, **kwargs) -> str:
        """Read output from gaia_cmd tmux pane."""
        lines = min(max(lines, 5), 200)

        pane = self._get_cmd_pane()
        if not pane:
            return "❌ Cannot access tmux pane 'gaia_cmd'. No async commands have been run."

        try:
            output = pane.capture_pane(start=-lines)
            if isinstance(output, list):
                output = "\n".join(output)

            output = output.strip()
            if not output:
                return "(gaia_cmd pane is empty — command may still be running)"

            return f"gaia_cmd pane output (last {lines} lines):\n{output}"
        except Exception as e:
            return f"❌ Failed to read pane output: {e}"
