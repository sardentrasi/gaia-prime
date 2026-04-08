"""
Gaia Prime - Heartbeat Daemon
Background thread that checks cron jobs and pending reminders every 60 seconds.
When a job is due, executes the action via AgentLoop and delivers the response.
"""

import os
import json
import logging
import asyncio
import threading
import time as time_module
from datetime import datetime

import pytz

logger = logging.getLogger("GaiaHeartbeat")

env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")


class HeartbeatDaemon:
    """
    Background daemon that:
    1. Checks cron jobs every 60 seconds
    2. Executes due jobs via AgentLoop (LLM + tools)
    3. Delivers responses to Telegram
    """

    HEARTBEAT_INTERVAL = 60  # seconds

    def __init__(self, cron, agent_loop, tool_registry=None, send_telegram_fn=None,
                 event_loop=None):
        """
        Args:
            cron: CronScheduler instance
            agent_loop: AgentLoop instance for executing actions
            tool_registry: ToolRegistry instance (for pending commands)
            send_telegram_fn: async fn(chat_id, text) to send Telegram messages
            event_loop: asyncio event loop for scheduling coroutines
        """
        self.cron = cron
        self.agent = agent_loop
        self.tools = tool_registry
        self.send_telegram = send_telegram_fn
        self.loop = event_loop
        self._running = False
        self._thread = None

    def start(self):
        """Start the heartbeat daemon in a background thread."""
        if self._running:
            logger.warning("⚠️ Heartbeat already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="GaiaHeartbeat")
        self._thread.start()
        logger.info("💓 [HEARTBEAT] Daemon started (interval: 60s)")

    def stop(self):
        """Stop the heartbeat daemon."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("💤 [HEARTBEAT] Daemon stopped")

    def _run(self):
        """Main heartbeat loop."""
        while self._running:
            try:
                self._check_and_execute()
                self._check_pending_commands()
            except Exception as e:
                logger.error(f"❌ [HEARTBEAT] Error in heartbeat cycle: {e}", exc_info=True)

            time_module.sleep(self.HEARTBEAT_INTERVAL)

    def _check_and_execute(self):
        """Check cron jobs and execute any that are due."""
        # Reload jobs (in case they were modified externally)
        self.cron.jobs = self.cron._load()

        due_jobs = self.cron.get_due_jobs()
        if not due_jobs:
            return

        logger.info(f"💓 [HEARTBEAT] {len(due_jobs)} job(s) due for execution")

        for job in due_jobs:
            try:
                self._execute_job(job)
            except Exception as e:
                logger.error(f"❌ [HEARTBEAT] Failed to execute job '{job['name']}': {e}")

    def _execute_job(self, job: dict):
        """Execute a single cron job. Reminders deliver directly, tasks go through LLM."""
        from core.message import GaiaMessage

        job_name = job["name"]
        action = job["action"]
        platform = job.get("platform", "telegram")
        target_id = job.get("target_id", "")
        job_type = job.get("type", "task")

        logger.info(f"⏰ [HEARTBEAT] Executing cron job: '{job_name}' [type={job_type}] → {action[:50]}...")

        if self.loop and self.loop.is_running():
            if job_type == "reminder":
                # Direct delivery — skip LLM, send action text as-is
                future = asyncio.run_coroutine_threadsafe(
                    self._deliver_direct(job),
                    self.loop
                )
            else:
                # Task — process through full AgentLoop (LLM + tools)
                message = GaiaMessage(
                    user_id=target_id,
                    user_name="Gaia Cron",
                    text=action,
                    platform=platform,
                    target_id=target_id
                )
                future = asyncio.run_coroutine_threadsafe(
                    self._process_and_deliver(message, job),
                    self.loop
                )
            # Wait for result with timeout
            try:
                future.result(timeout=120)
            except Exception as e:
                logger.error(f"❌ [HEARTBEAT] Job '{job_name}' execution timeout or error: {e}")
        else:
            logger.warning(f"⚠️ [HEARTBEAT] Event loop not available, skipping job '{job_name}'")

    async def _deliver_direct(self, job: dict):
        """Deliver a reminder directly without LLM processing."""
        try:
            platform = job.get("platform", "telegram")
            target_id = job.get("target_id", "")
            job_name = job["name"]
            action = job["action"]

            header = f"⏰ *{job_name}*\n\n"
            full_message = header + action

            if platform == "telegram" and self.send_telegram:
                await self.send_telegram(target_id, full_message)
                logger.info(f"✅ [HEARTBEAT] Reminder delivered to Telegram: {target_id}")
            else:
                logger.warning(f"⚠️ [HEARTBEAT] No delivery method for platform '{platform}'")

            # Mark job as executed
            self.cron.mark_executed(job["id"])

        except Exception as e:
            logger.error(f"❌ [HEARTBEAT] Direct delivery failed for '{job['name']}': {e}")

    async def _process_and_deliver(self, message, job: dict):
        """Process the message through AgentLoop and deliver the response."""
        try:
            response = await self.agent.process(message)

            if response and response != "...":
                platform = job.get("platform", "telegram")
                target_id = job.get("target_id", "")
                job_name = job["name"]

                header = f"📋 *{job_name}*\n\n"
                full_response = header + response

                if platform == "telegram" and self.send_telegram:
                    await self.send_telegram(target_id, full_response)
                    logger.info(f"✅ [HEARTBEAT] Delivered to Telegram: {target_id}")
                else:
                    logger.warning(f"⚠️ [HEARTBEAT] No delivery method for platform '{platform}'")

            # Mark job as executed
            self.cron.mark_executed(job["id"])

        except Exception as e:
            logger.error(f"❌ [HEARTBEAT] Process & deliver failed for '{job['name']}': {e}")

    def set_telegram_sender(self, send_fn):
        """Set the Telegram message sender function (called after bot is ready)."""
        self.send_telegram = send_fn
        logger.info("💓 [HEARTBEAT] Telegram sender connected")

    def set_event_loop(self, loop):
        """Set the event loop (called when the main loop is available)."""
        self.loop = loop
        logger.info("💓 [HEARTBEAT] Event loop connected")

    # ─── PENDING COMMAND MONITORING ───

    def _check_pending_commands(self):
        """Check if any async shell commands have finished and auto-report results."""
        if not self.tools or not self.tools.pending_commands:
            return

        pane = self.tools._get_cmd_pane()
        if not pane:
            return

        try:
            # Capture last lines of the pane
            output_lines = pane.capture_pane(start=-60)
            if isinstance(output_lines, list):
                output_text = "\n".join(output_lines)
            else:
                output_text = str(output_lines)

            # Detect if command is done: last non-empty line ends with $ or #
            stripped_lines = [l for l in output_lines if l.strip()] if isinstance(output_lines, list) else []
            if not stripped_lines:
                return

            last_line = stripped_lines[-1].strip()
            command_finished = last_line.endswith("$") or last_line.endswith("#") or last_line.endswith("%")

            if not command_finished:
                return  # Still running

            # Report all unreported pending commands
            unreported = [c for c in self.tools.pending_commands if not c.get("reported")]
            if not unreported:
                return

            for cmd_info in unreported:
                cmd_info["reported"] = True
                cmd_name = cmd_info["command"][:60]

                report = (
                    f"🖥️ *Command Selesai*\n\n"
                    f"`{cmd_info['command']}`\n\n"
                    f"*Output:*\n```\n{output_text.strip()[-2000:]}\n```"
                )

                logger.info(f"✅ [HEARTBEAT] Command finished: {cmd_name}")
                self._deliver_message(
                    report,
                    platform=cmd_info.get("platform", "telegram"),
                    target_id=cmd_info.get("target_id", "")
                )

            # Clean up reported commands
            self.tools.pending_commands = [
                c for c in self.tools.pending_commands if not c.get("reported")
            ]

        except Exception as e:
            logger.error(f"❌ [HEARTBEAT] Pending command check failed: {e}")

    def _deliver_message(self, text: str, platform: str = "telegram", target_id: str = ""):
        """Send a proactive message via Telegram."""
        if not target_id:
            target_id = os.getenv("TELEGRAM_CHAT_ID", "")

        if self.send_telegram and self.loop and self.loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.send_telegram(target_id, text),
                    self.loop
                )
                future.result(timeout=15)
                logger.info(f"✅ [HEARTBEAT] Proactive message sent via Telegram → {target_id}")
            except Exception as e:
                logger.error(f"❌ [HEARTBEAT] Telegram delivery failed: {e}")
        else:
            logger.warning(f"⚠️ [HEARTBEAT] No delivery method available")
