"""Run and schedule CLI downloads for the web interface."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROGRESS_PHASES = {"starting", "authenticating", "checking", "scanning", "downloading", "refreshing", "finished"}
_MAX_PROGRESS_BYTES = 65536


class DownloadManager:
    """Keep at most one download subprocess running for a web server."""

    def __init__(self, archive_root: Path, config_path: str | None, interval_minutes: int = 0):
        self._archive_root = archive_root.resolve()
        self._config_path = Path(config_path).resolve() if config_path else None
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._stopped = False
        self._state = "idle"
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._next_run: datetime | None = None
        self._progress_dir: tempfile.TemporaryDirectory | None = None
        self._progress_path: Path | None = None
        self._progress = self._empty_progress()
        self._interval = 0
        self.set_interval(interval_minutes)

    def start_scheduler(self) -> None:
        """Start watching downloads and running the configured schedule."""
        with self._condition:
            if not self._stopped:
                self._ensure_thread()

    def start_download(self) -> bool:
        """Start a download without waiting, unless one is already running."""
        with self._condition:
            self._reap()
            if self._stopped or not self._config_path or self._process is not None:
                return False
            started = self._launch()
            self._ensure_thread()
            self._condition.notify_all()
            return started

    def set_interval(self, minutes: int) -> None:
        """Change the interval; zero disables future scheduled downloads."""
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0:
            raise ValueError("Download interval must be a nonnegative integer.")
        with self._condition:
            self._interval = minutes
            self._schedule(datetime.now(timezone.utc))
            self._condition.notify_all()

    def snapshot(self) -> dict:
        """Return current status without including command output."""
        with self._condition:
            self._reap()
            self._read_progress()
            return {
                "available": self._config_path is not None,
                "running": self._process is not None,
                "state": self._state,
                "interval_minutes": self._interval,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "finished_at": self._finished_at.isoformat() if self._finished_at else None,
                "next_run": self._next_run.isoformat() if self._next_run else None,
                **self._progress,
            }

    def stop(self) -> None:
        """Stop scheduling and give an active download time to save progress."""
        with self._condition:
            self._stopped = True
            self._next_run = None
            self._condition.notify_all()
            thread = self._thread
            process = self._process
        if thread:
            thread.join(timeout=1)
        if process is not None and process.poll() is None:
            actions = (
                (lambda: process.send_signal(signal.SIGINT), 5),
                (process.terminate, 2),
                (process.kill, 2),
            )
            for action, timeout in actions:
                try:
                    action()
                except (OSError, ValueError):
                    continue
                try:
                    process.wait(timeout=timeout)
                    break
                except subprocess.TimeoutExpired:
                    continue
        with self._condition:
            self._reap()

    def _ensure_thread(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="ownmail-downloads", daemon=True)
            self._thread.start()

    def _schedule(self, now: datetime) -> None:
        self._next_run = (
            now + timedelta(minutes=self._interval)
            if self._config_path and self._interval and not self._stopped and self._process is None
            else None
        )

    def _launch(self) -> bool:
        self._started_at = datetime.now(timezone.utc)
        self._finished_at = None
        self._next_run = None
        self._progress = self._empty_progress()
        self._progress["phase"] = "starting"
        try:
            self._progress_dir = tempfile.TemporaryDirectory(prefix="ownmail-download-", ignore_cleanup_errors=True)
            self._progress_path = Path(self._progress_dir.name) / "progress.json"
            # A subprocess preserves the downloader's main-thread SIGINT handling.
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "ownmail",
                    "--config",
                    str(self._config_path),
                    "--archive-root",
                    str(self._archive_root),
                    "download",
                    "--progress-file",
                    str(self._progress_path),
                ],
                stdin=subprocess.DEVNULL,
                # The server sends SIGINT on shutdown; avoid receiving it twice.
                start_new_session=os.name != "nt",
            )
        except OSError:
            self._state = "failed"
            self._finished_at = datetime.now(timezone.utc)
            self._progress["phase"] = "finished"
            self._progress["failure_reason"] = "Could not start the downloader. Restart ownmail serve and try again."
            self._cleanup_progress()
            self._schedule(self._finished_at)
            return False
        self._state = "running"
        return True

    def _reap(self) -> None:
        if self._process is None:
            return
        returncode = self._process.poll()
        if returncode is None:
            return
        self._read_progress()
        self._process = None
        self._state = {0: "succeeded", 75: "busy"}.get(returncode, "failed")
        self._finished_at = datetime.now(timezone.utc)
        self._progress["phase"] = "finished"
        if returncode and not self._progress["failure_reason"]:
            self._progress["failure_reason"] = (
                "Another download is already running. Try again after it finishes."
                if returncode == 75
                else "The downloader stopped before it finished. Check the server console and try again."
            )
        self._cleanup_progress()
        self._schedule(self._finished_at)

    @staticmethod
    def _empty_progress() -> dict:
        return {
            "phase": None,
            "source": None,
            "downloaded": 0,
            "skipped": 0,
            "errors": 0,
            "failure_reason": None,
            "has_progress": False,
            "active_refreshed": 0,
            "active_complete": None,
            "scan_checked": 0,
        }

    def _read_progress(self) -> None:
        if self._progress_path is None:
            return
        try:
            with self._progress_path.open("rb") as stream:
                data = stream.read(_MAX_PROGRESS_BYTES + 1)
            if len(data) > _MAX_PROGRESS_BYTES:
                return
            report = json.loads(data)
        except (OSError, ValueError, RecursionError):
            return
        if not isinstance(report, dict):
            return
        phase = report.get("phase")
        counters = ("downloaded", "skipped", "errors")
        if not isinstance(phase, str) or phase not in _PROGRESS_PHASES:
            return
        if any(type(report.get(key)) is not int or report[key] < 0 for key in counters):
            return
        if report.get("source") is not None and not isinstance(report["source"], str):
            return
        if report.get("failure_reason") is not None and not isinstance(report["failure_reason"], str):
            return
        if type(report.get("active_refreshed", 0)) is not int or report.get("active_refreshed", 0) < 0:
            return
        if type(report.get("scan_checked", 0)) is not int or report.get("scan_checked", 0) < 0:
            return
        if report.get("active_complete") is not None and type(report["active_complete"]) is not bool:
            return
        self._progress = {key: report.get(key) for key in self._progress if key != "has_progress"}
        self._progress["active_refreshed"] = report.get("active_refreshed", 0)
        self._progress["scan_checked"] = report.get("scan_checked", 0)
        self._progress["has_progress"] = True

    def _cleanup_progress(self) -> None:
        if self._progress_dir is not None:
            self._progress_dir.cleanup()
            self._progress_dir = None
            self._progress_path = None

    def _run(self) -> None:
        with self._condition:
            while not self._stopped:
                self._reap()
                now = datetime.now(timezone.utc)
                if self._next_run is not None and now >= self._next_run:
                    self._launch()
                if self._process is not None:
                    timeout = 0.25
                elif self._next_run is not None:
                    timeout = max(0, (self._next_run - datetime.now(timezone.utc)).total_seconds())
                else:
                    timeout = None
                self._condition.wait(timeout=timeout)
