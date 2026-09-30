"""Process locks: one download per archive, one sanitizer dependency install at a time."""

import errno
import sys
from pathlib import Path


class LockHeld(Exception):
    """Another process holds the lock."""


class DownloadInProgress(LockHeld):
    """Another process is downloading into this archive."""


class ProcessLock:
    """Hold a nonblocking process lock on a file until the context exits."""

    held_error = LockHeld
    held_message = "Another process holds this lock."

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException as exc:
            self._file.close()
            if isinstance(exc, OSError) and exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise self.held_error(self.held_message) from exc
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Closing releases the OS lock; retaining the inode avoids races with waiters.
        self._file.close()


class DownloadLock(ProcessLock):
    """Hold a nonblocking lock on an archive's downloads until the context exits."""

    held_error = DownloadInProgress
    held_message = "A download is already running for this archive."

    def __init__(self, archive_root: Path):
        self.archive_root = archive_root.resolve()
        super().__init__(self.archive_root / ".download.lock")
