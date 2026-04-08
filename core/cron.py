"""
Gaia Prime - Cron Scheduler
JSON-based scheduled task system. Jobs are created/managed by the LLM
via tool calling (not hardcoded). Heartbeat daemon checks and executes due jobs.
"""

import os
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import pytz

logger = logging.getLogger("GaiaCron")

env_timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    MY_TZ = pytz.timezone(env_timezone)
except pytz.UnknownTimeZoneError:
    MY_TZ = pytz.timezone("Asia/Jakarta")


class CronScheduler:
    """
    Manages scheduled tasks stored in gaia_cron.json.
    Jobs can be one-shot or recurring, created dynamically by the LLM.
    
    Schedule formats:
      - "once YYYY-MM-DDTHH:MM" → one-time execution
      - "daily HH:MM" → every day at HH:MM
      - "weekday HH:MM" → Mon-Fri at HH:MM
      - "weekend HH:MM" → Sat-Sun at HH:MM  
      - "every Xh" → every X hours from creation
      - "every Xm" → every X minutes from creation
    """

    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir or os.getcwd()
        self.cron_file = os.path.join(self.root_dir, "gaia_cron.json")
        self.jobs = self._load()

    def _load(self) -> list:
        """Load cron jobs from file."""
        if not os.path.exists(self.cron_file):
            return []
        try:
            with open(self.cron_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to load cron file: {e}")
            return []

    def _save(self):
        """Save cron jobs to file."""
        try:
            with open(self.cron_file, "w", encoding="utf-8") as f:
                json.dump(self.jobs, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cron file: {e}")

    def create_job(self, name: str, schedule: str, action: str,
                   platform: str = "telegram", target_id: str = None,
                   job_type: str = "task") -> dict:
        """
        Create a new cron job.
        
        Args:
            name: Human-readable job name
            schedule: Schedule expression (see class docstring)
            action: The prompt/instruction for LLM to execute, or direct message for reminders
            platform: "telegram"
            target_id: Chat/user ID to send result to
            job_type: "task" (process via LLM) or "reminder" (deliver action directly)
            
        Returns:
            The created job dict
        """
        job = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "schedule": schedule,
            "action": action,
            "platform": platform,
            "target_id": target_id or self._get_default_target(platform),
            "type": job_type,
            "enabled": True,
            "created_at": datetime.now(MY_TZ).isoformat(),
            "last_run": None,
            "run_count": 0
        }
        self.jobs.append(job)
        self._save()
        logger.info(f"📋 [CRON] Created job: {name} ({schedule}) [type={job_type}]")
        return job

    def delete_job(self, job_id: str) -> bool:
        """Delete a cron job by ID or name."""
        original_count = len(self.jobs)
        self.jobs = [j for j in self.jobs if j["id"] != job_id and j["name"] != job_id]
        
        if len(self.jobs) < original_count:
            self._save()
            logger.info(f"🗑️ [CRON] Deleted job: {job_id}")
            return True
        return False

    def list_pending(self) -> list:
        """Return pending one-shot jobs (enabled + schedule starts with 'once' + not yet run)."""
        return [
            j for j in self.jobs
            if j.get("enabled", True) and j["schedule"].startswith("once ") and not j.get("last_run")
        ]

    def postpone_job(self, job_id: str, new_time_iso: str) -> bool:
        """Postpone a pending job to a new time.
        
        Args:
            job_id: Job ID or name to postpone
            new_time_iso: New ISO-8601 time string
            
        Returns:
            True if job was found and updated
        """
        for job in self.jobs:
            if job["id"] == job_id or job["name"] == job_id:
                if not job.get("enabled", True):
                    return False  # Already executed
                job["schedule"] = f"once {new_time_iso}"
                self._save()
                logger.info(f"⏰ [CRON] Postponed job '{job['name']}' → {new_time_iso}")
                return True
        return False

    def _get_default_target(self, platform: str) -> str:
        """Get default target_id based on platform."""
        if platform == "telegram":
            return os.getenv("TELEGRAM_CHAT_ID", "")
        return ""

    def list_jobs(self) -> list:
        """Return all cron jobs."""
        return self.jobs

    def get_due_jobs(self) -> List[dict]:
        """Check which jobs are due for execution right now."""
        now = datetime.now(MY_TZ)
        due = []

        for job in self.jobs:
            if not job.get("enabled", True):
                continue

            schedule = job["schedule"]
            last_run = job.get("last_run")

            if self._is_due(schedule, now, last_run, job.get("created_at")):
                due.append(job)

        return due

    def mark_executed(self, job_id: str):
        """Mark a job as having been executed. One-shot jobs are removed immediately."""
        for job in self.jobs:
            if job["id"] == job_id:
                job["last_run"] = datetime.now(MY_TZ).isoformat()
                job["run_count"] = job.get("run_count", 0) + 1
                
                # Remove one-shot jobs after execution (keep file clean)
                if job["schedule"].startswith("once "):
                    self.jobs.remove(job)
                    logger.info(f"🧹 [CRON] One-shot job '{job['name']}' executed and removed")
                break
        self._save()

    def _is_due(self, schedule: str, now: datetime, 
                last_run: Optional[str], created_at: Optional[str]) -> bool:
        """Check if a schedule expression is due at the given time."""
        try:
            # Parse last_run
            if last_run:
                last_dt = datetime.fromisoformat(last_run)
            else:
                last_dt = None

            # "once YYYY-MM-DDTHH:MM"
            if schedule.startswith("once "):
                if last_run:  # Already ran
                    return False
                target_str = schedule[5:].strip()
                target = datetime.fromisoformat(target_str)
                if target.tzinfo is None:
                    target = MY_TZ.localize(target)
                return now >= target

            # "daily HH:MM"
            if schedule.startswith("daily "):
                time_str = schedule[6:].strip()
                hour, minute = map(int, time_str.split(":"))
                target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                if now >= target_today:
                    if last_dt and last_dt.date() == now.date():
                        return False  # Already ran today
                    return True
                return False

            # "weekday HH:MM"
            if schedule.startswith("weekday "):
                if now.weekday() >= 5:  # Sat=5, Sun=6
                    return False
                time_str = schedule[8:].strip()
                hour, minute = map(int, time_str.split(":"))
                target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if now >= target_today:
                    if last_dt and last_dt.date() == now.date():
                        return False
                    return True
                return False

            # "weekend HH:MM"
            if schedule.startswith("weekend "):
                if now.weekday() < 5:
                    return False
                time_str = schedule[8:].strip()
                hour, minute = map(int, time_str.split(":"))
                target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if now >= target_today:
                    if last_dt and last_dt.date() == now.date():
                        return False
                    return True
                return False

            # "every Xh" or "every Xm"
            if schedule.startswith("every "):
                interval_str = schedule[6:].strip()
                if interval_str.endswith("h"):
                    interval = timedelta(hours=int(interval_str[:-1]))
                elif interval_str.endswith("m"):
                    interval = timedelta(minutes=int(interval_str[:-1]))
                else:
                    return False

                reference = last_dt
                if not reference and created_at:
                    reference = datetime.fromisoformat(created_at)
                if not reference:
                    return True  # No reference, run now

                if reference.tzinfo is None:
                    reference = MY_TZ.localize(reference)
                return now >= reference + interval

        except Exception as e:
            logger.error(f"❌ Cron schedule parse error for '{schedule}': {e}")
            return False

        return False
