"""Publish private download progress without exposing provider output."""

import errno
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from keyring.errors import KeyringError, KeyringLocked

FAILURE_REASONS = {
    "config": "Could not load a valid configuration. Check the config file.",
    "setup": "Mail source setup is incomplete. Run ownmail setup.",
    "busy": "Another download is already running for this archive.",
    "interrupted": "Download interrupted. Start again to resume.",
    "keychain_locked": "Keychain is locked or access was denied. Unlock it and try again.",
    "keychain": "Could not access saved credentials. Check the system keychain.",
    "authentication": "Could not sign in. Check your mail source setup.",
    "network": "Could not connect to the mail server. Check your connection.",
    "timeout": "Mail server request timed out. Try again.",
    "checking": "Could not check for new mail. Check the server console.",
    "download": "Some messages could not be downloaded. Check the server console.",
    "storage": "Could not write to the archive. Check permissions and free space.",
    "index": "Could not update the archive index. Check the server console.",
    "message_index": "Mail was saved but could not be indexed. Check the server console.",
    "failed": "Download failed. Check the server console.",
}


class DownloadProgress:
    """Write cumulative counts and bounded failure reasons as atomic JSON."""

    def __init__(self, path: Path):
        self.path = path
        self._state = {
            "phase": "starting",
            "source": None,
            "downloaded": 0,
            "skipped": 0,
            "errors": 0,
            "failure_reason": None,
        }
        self._last_write = float("-inf")
        self._last_exception = None
        self._write(force=True)

    @property
    def errors(self) -> int:
        return self._state["errors"]

    @property
    def failure_reason(self) -> str | None:
        return self._state["failure_reason"]

    def set_phase(self, phase: str, source: str | None = None) -> None:
        """Publish a phase change immediately, retaining the current source."""
        self._state["phase"] = phase
        if isinstance(source, str):
            self._state["source"] = source
        self._write(force=True)

    def advance(self, *, downloaded: int = 0, skipped: int = 0) -> None:
        """Count completed messages while limiting disk writes."""
        self._state["downloaded"] += downloaded
        self._state["skipped"] += skipped
        self._write()

    def fail(self, reason: str, *, errors: int = 0) -> None:
        """Publish a reason selected from the fixed message catalog."""
        self._state["failure_reason"] = FAILURE_REASONS[reason]
        self._state["errors"] += errors
        self._write(force=True)

    def fail_exception(self, error: BaseException, *, context: str | None = None, errors: int = 0) -> None:
        """Classify an exception without copying its message or arguments."""
        if error is self._last_exception and not errors:
            return
        self._last_exception = error
        context = context or self._state["phase"]
        if isinstance(error, KeyringLocked):
            reason = "keychain_locked"
        elif isinstance(error, KeyringError):
            reason = "keychain"
        elif context == "config":
            reason = "config"
        elif isinstance(error, sqlite3.Error):
            reason = "index"
        elif isinstance(error, PermissionError) or (
            isinstance(error, OSError) and (context == "archive" or error.errno in (errno.ENOSPC, errno.EROFS))
        ):
            reason = "storage"
        elif isinstance(error, TimeoutError):
            reason = "timeout"
        elif isinstance(error, (ConnectionError, OSError)):
            reason = "network"
        else:
            reason = {"authenticating": "authentication", "checking": "checking", "downloading": "download"}.get(
                context, "failed"
            )
        self.fail(reason, errors=errors)

    def flush(self) -> None:
        """Publish all counts collected since the last write."""
        self._write(force=True)

    def finish(self) -> None:
        """Flush the final counts even if the last update was throttled."""
        self.set_phase("finished")

    def _write(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_write < 0.25:
            return
        self._last_write = now
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".ownmail-progress-", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self._state, stream)
            os.replace(temporary, self.path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
