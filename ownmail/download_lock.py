"""Prevent concurrent downloads into the same archive."""

import errno
import sys
from pathlib import Path


class DownloadInProgress(Exception):
    """Another process is downloading into this archive."""


class DownloadLock:
    """Hold a nonblocking process lock until the context exits."""

    def __init__(self, archive_root: Path):
        self.archive_root = archive_root.resolve()

    def __enter__(self):
        self.archive_root.mkdir(parents=True, exist_ok=True)
        self._file = (self.archive_root / ".download.lock").open("a+b")
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
                raise DownloadInProgress("A download is already running for this archive.") from exc
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Closing releases the OS lock; retaining the inode avoids races with waiters.
        self._file.close()
