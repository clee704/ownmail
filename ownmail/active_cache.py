"""Disposable Active messages, stored separately from the owned archive."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from ownmail.database import ArchiveDatabase
from ownmail.parser import EmailParser

_LOG = logging.getLogger(__name__)
_ID = re.compile(r"active-[0-9a-f]{64}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


class ActiveCache:
    """Keep rebuildable search data and authoritative cache files outside an archive."""

    def __init__(self, archive_dir: Path, cache_dir: Path | None = None):
        self.archive_dir = Path(archive_dir).resolve()
        chosen = (
            Path(cache_dir) if cache_dir is not None else self.archive_dir.with_name(f".{self.archive_dir.name}-active")
        )
        self.cache_dir = chosen.resolve()
        if (
            self.cache_dir == self.archive_dir
            or self.cache_dir in self.archive_dir.parents
            or self.archive_dir in self.cache_dir.parents
        ):
            raise ValueError("Active cache and archive directories must be separate")
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._check_root()
        marker = self.cache_dir / "active-cache.json"
        self._check_file(marker)
        if marker.exists():
            data = json.loads(self._read_file(marker))
            if data != {"version": 1, "archive": str(self.archive_dir)}:
                raise ValueError("Active cache belongs to a different archive or version")
        else:
            if any(self.cache_dir.iterdir()):
                raise ValueError("Active cache directory must be empty or an existing ownmail Active cache")
            self._atomic_write(marker, json.dumps({"version": 1, "archive": str(self.archive_dir)}).encode())
        for name in ("entries", "messages", "sources"):
            path = self.cache_dir / name
            if path.is_symlink():
                raise ValueError("Active cache directories cannot be symbolic links")
            path.mkdir(exist_ok=True, mode=0o700)
            self._check_directory(path)
        self._db = None
        self.rebuild_index()

    def _check_root(self) -> None:
        if self.cache_dir.is_symlink() or self.cache_dir.resolve() != self.cache_dir or not self.cache_dir.is_dir():
            raise ValueError("Active cache directory has changed or is unsafe")
        archive = self.archive_dir.resolve()
        if archive == self.cache_dir or archive in self.cache_dir.parents or self.cache_dir in archive.parents:
            raise ValueError("Active cache and archive directories must be separate")

    def _check_directory(self, path: Path) -> None:
        self._check_root()
        if path != self.cache_dir and path.parent != self.cache_dir:
            raise ValueError("Unexpected Active cache directory")
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Active cache directory is unsafe")

    def _check_file(self, path: Path) -> None:
        self._check_directory(path.parent)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Active cache files must be regular files without links")

    def _read_file(self, path: Path) -> bytes:
        self._check_file(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Active cache file changed while reading")
            return stream.read()

    @staticmethod
    def _sync_directory(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _atomic_write(self, path: Path, data: bytes) -> None:
        self._check_file(path)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_file(path)
            os.replace(temporary, path)
            self._sync_directory(path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _entry_path(self, active_id: str) -> Path:
        if not isinstance(active_id, str) or not _ID.fullmatch(active_id):
            raise ValueError("Invalid Active message ID")
        return self.cache_dir / "entries" / f"{active_id}.json"

    def _payload_path(self, entry: dict) -> Path:
        active_id = entry["id"]
        content_hash = entry["content_hash"]
        if not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash):
            raise ValueError("Invalid Active content hash")
        expected = f"messages/{active_id}-{content_hash}.eml"
        if entry["filename"] != expected:
            raise ValueError("Invalid Active message filename")
        path = self.cache_dir / expected
        self._check_file(path)
        return path

    def get(self, active_id: str) -> dict | None:
        """Read metadata for one Active message; reject unsafe or inconsistent entries."""
        path = self._entry_path(active_id)
        try:
            entry = json.loads(self._read_file(path))
        except FileNotFoundError:
            return None
        if not isinstance(entry, dict):
            raise ValueError("Invalid Active message metadata")
        required = ("source_name", "account", "provider_id", "identity", "state", "checked_at", "content_at")
        if any(not isinstance(entry.get(key), str) for key in required):
            raise ValueError("Invalid Active message metadata")
        if entry.get("id") != active_id or active_id != "active-" + _digest(
            entry["source_name"], entry["account"], entry["identity"]
        ):
            raise ValueError("Active message identity does not match its entry")
        if entry["state"] not in ("active", "unknown"):
            raise ValueError("Invalid Active message state")
        revision = entry.get("content_revision")
        if revision is not None and (not isinstance(revision, str) or not revision):
            raise ValueError("Invalid Active content revision")
        for key in ("labels", "roles"):
            if not isinstance(entry.get(key), list) or any(not isinstance(value, str) for value in entry[key]):
                raise ValueError("Invalid Active message labels or roles")
        if "active_scope" in entry and (
            not isinstance(entry["active_scope"], list)
            or any(not isinstance(value, str) for value in entry["active_scope"])
        ):
            raise ValueError("Invalid Active tracking scope")
        if "filename" not in entry or "content_hash" not in entry:
            raise ValueError("Incomplete Active message metadata")
        self._payload_path(entry)
        return entry

    def list_entries(self, source_name: str | None = None, account: str | None = None) -> list[dict]:
        """List valid cache entries, optionally limited to a source and account."""
        directory = self.cache_dir / "entries"
        self._check_directory(directory)
        entries = []
        for path in sorted(directory.glob("*.json")):
            try:
                entry = self.get(path.stem)
                if (
                    entry is None
                    or (source_name is not None and entry["source_name"] != source_name)
                    or (account is not None and entry["account"] != account)
                ):
                    continue
                self.read(entry["id"])
                entries.append(entry)
            except (OSError, ValueError):
                _LOG.warning("Skipping unreadable Active cache entry: %s", path.name)
        return entries

    def path(self, active_id: str) -> Path:
        """Return a validated cache payload path, after checking its content hash."""
        entry = self.get(active_id)
        if entry is None:
            raise FileNotFoundError("Active message is no longer cached")
        path = self._payload_path(entry)
        if hashlib.sha256(self._read_file(path)).hexdigest() != entry["content_hash"]:
            raise ValueError("Active message content hash does not match")
        return path

    def read(self, active_id: str) -> bytes:
        """Read verified cached message contents."""
        entry = self.get(active_id)
        if entry is None:
            raise FileNotFoundError("Active message is no longer cached")
        raw = self._read_file(self._payload_path(entry))
        if hashlib.sha256(raw).hexdigest() != entry["content_hash"]:
            raise ValueError("Active message content hash does not match")
        return raw

    def put(
        self,
        *,
        source_name: str,
        account: str,
        provider_id: str,
        identity: str,
        roles: list[str],
        labels: list[str],
        raw: bytes,
        checked_at: str | None = None,
        state: str = "active",
        content_revision: str | None = None,
        active_scope: list[str] | None = None,
    ) -> dict:
        """Commit payload and metadata before updating the disposable search index."""
        if state not in ("active", "unknown"):
            raise ValueError("Invalid Active message state")
        if content_revision is not None and (not isinstance(content_revision, str) or not content_revision):
            raise ValueError("Invalid Active content revision")
        if not all(isinstance(value, str) for value in (source_name, account, provider_id, identity)):
            raise ValueError("Active message identity fields must be strings")
        if not all(
            isinstance(values, list) and all(isinstance(value, str) for value in values) for values in (roles, labels)
        ):
            raise ValueError("Active message labels and roles must be string lists")
        if active_scope is not None and (
            not isinstance(active_scope, list) or any(not isinstance(value, str) for value in active_scope)
        ):
            raise ValueError("Active tracking scope must be a string list")
        active_id = "active-" + _digest(source_name, account, identity)
        old = self.get(active_id)
        content_hash = hashlib.sha256(raw).hexdigest()
        now = checked_at or _now()
        entry = {
            "id": active_id,
            "source_name": source_name,
            "account": account,
            "provider_id": provider_id,
            "identity": identity,
            "roles": list(dict.fromkeys(roles)),
            "labels": list(dict.fromkeys(labels)),
            "state": state,
            "content_hash": content_hash,
            "checked_at": now,
            "content_at": old["content_at"] if old and old["content_hash"] == content_hash else now,
            "filename": f"messages/{active_id}-{content_hash}.eml",
            "content_revision": content_revision,
        }
        if active_scope is not None:
            entry["active_scope"] = list(dict.fromkeys(active_scope))
        payload = self._payload_path(entry)
        # Versioned payloads keep the previous metadata readable across a failed save.
        # A matching metadata hash alone cannot establish that the payload is intact.
        try:
            unchanged = old is not None and old["content_hash"] == content_hash and self.read(active_id) == raw
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            self._atomic_write(payload, raw)
        self._atomic_write(self._entry_path(active_id), json.dumps(entry, ensure_ascii=True).encode())
        self._index_entry(entry, raw)
        if old and old["filename"] != entry["filename"]:
            self._unlink(self._payload_path(old))
        return entry

    def _unlink(self, path: Path) -> None:
        self._check_file(path)
        path.unlink(missing_ok=True)
        self._sync_directory(path.parent)

    def update_scope(self, active_id: str, active_scope: list[str]) -> None:
        """Record a confirmed exclusion without refreshing cached content or its age."""
        if not isinstance(active_scope, list) or any(not isinstance(value, str) for value in active_scope):
            raise ValueError("Active tracking scope must be a string list")
        entry = self.get(active_id)
        if entry is not None:
            entry["active_scope"] = list(dict.fromkeys(active_scope))
            self._atomic_write(self._entry_path(active_id), json.dumps(entry, ensure_ascii=True).encode())

    def remove(self, active_id: str) -> bool:
        """Remove only this cache's metadata, index entry, and validated payload."""
        entry = self.get(active_id)
        if entry is None:
            return False
        payload = self._payload_path(entry)
        self._unlink(self._entry_path(active_id))
        with closing(sqlite3.connect(self.db.db_path)) as conn, conn:
            self._delete_index_entry(conn, active_id)
        self._unlink(payload)
        return True

    def set_source_status(
        self,
        source_name: str,
        account: str,
        *,
        complete: bool,
        error: str | None = None,
        checked_at: str | None = None,
        active_scope_signature: str | None = None,
        capture_scope_signature: str | None = None,
        capture_state: str | None = None,
    ) -> None:
        """Persist the latest attempt, retaining the last complete refresh time."""
        previous = self.source_status(source_name, account)
        now = checked_at or _now()
        data = {
            "source_name": source_name,
            "account": account,
            "complete": complete,
            "error": error,
            "checked_at": now,
            "completed_at": now if complete else (previous or {}).get("completed_at"),
        }
        if active_scope_signature is not None:
            data["active_scope_signature"] = active_scope_signature
            data["capture_scope_signature"] = capture_scope_signature
            data["capture_state"] = capture_state
        self._atomic_write(
            self.cache_dir / "sources" / f"{_digest(source_name, account)}.json", json.dumps(data).encode()
        )

    def source_status(self, source_name: str, account: str) -> dict | None:
        """Return persisted freshness and completeness for one source."""
        path = self.cache_dir / "sources" / f"{_digest(source_name, account)}.json"
        try:
            data = json.loads(self._read_file(path))
        except FileNotFoundError:
            return None
        if (
            not isinstance(data, dict)
            or data.get("source_name") != source_name
            or data.get("account") != account
            or type(data.get("complete")) is not bool
        ):
            raise ValueError("Invalid Active source status")
        return data

    @property
    def db(self) -> ArchiveDatabase:
        """Return the cache search index after checking its filesystem boundary."""
        self._check_database_paths()
        return self._db

    def _check_database_paths(self) -> None:
        for suffix in ("", "-journal", "-wal", "-shm"):
            self._check_file(self.cache_dir / f"ownmail.db{suffix}")

    @staticmethod
    def _delete_index_entry(conn: sqlite3.Connection, active_id: str) -> None:
        conn.execute(
            "DELETE FROM emails_fts WHERE rowid IN (SELECT rowid FROM emails WHERE email_id = ?)", (active_id,)
        )
        conn.execute("DELETE FROM emails WHERE email_id = ?", (active_id,))

    def _index_entry(self, entry: dict, raw: bytes, conn: sqlite3.Connection | None = None) -> None:
        parsed = EmailParser.parse_file(content=raw)
        try:
            date = parsedate_to_datetime(parsed["date_str"])
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            email_date = date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError, OverflowError):
            # Drafts commonly have no Date header and must remain searchable.
            email_date = entry["content_at"][:19]
        if conn is None:
            with closing(sqlite3.connect(self.db.db_path)) as connection, connection:
                self._write_index_entry(connection, entry, parsed, email_date)
        else:
            self._write_index_entry(conn, entry, parsed, email_date)

    def _write_index_entry(self, conn: sqlite3.Connection, entry: dict, parsed: dict, email_date: str) -> None:
        self._delete_index_entry(conn, entry["id"])
        self._db.mark_downloaded(
            email_id=entry["id"],
            provider_id=entry["id"],
            filename=entry["filename"],
            content_hash=entry["content_hash"],
            account=entry["account"],
            conn=conn,
            email_date=email_date,
        )
        self._db.index_email(email_id=entry["id"], **parsed, conn=conn, labels=entry["labels"], email_date=email_date)
        conn.execute(
            "UPDATE emails SET downloaded_at = ?, indexed_hash = ? WHERE email_id = ?",
            (entry["content_at"], entry["content_hash"], entry["id"]),
        )

    def rebuild_index(self) -> None:
        """Rebuild cache search data entirely from verified message files and JSON."""
        self._check_database_paths()
        try:
            self._db = ArchiveDatabase(self.cache_dir)
        except sqlite3.DatabaseError:
            for suffix in ("", "-journal", "-wal", "-shm"):
                self._unlink(self.cache_dir / f"ownmail.db{suffix}")
            self._db = ArchiveDatabase(self.cache_dir)
        with closing(sqlite3.connect(self.db.db_path)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DROP TABLE emails_fts")
            conn.execute(
                "CREATE VIRTUAL TABLE emails_fts USING fts5(subject, sender, recipients, body, attachments, tokenize='porter unicode61')"
            )
            conn.execute("DELETE FROM emails")
            for entry in self.list_entries():
                self._index_entry(entry, self.read(entry["id"]), conn)
