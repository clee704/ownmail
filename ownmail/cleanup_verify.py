"""Read-only local evidence required before removing a server copy."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from ownmail.database import ArchiveDatabase
from ownmail.live_sync import capture_provenance
from ownmail.sidecar import sidecar_path

_BATCH_SIZE = 100


class CleanupHold(ValueError):
    """Local evidence cannot authorize cleanup of this server copy."""


@dataclass(frozen=True)
class VerifiedCopy:
    """A freshly verified owned copy; server state still requires verification."""

    email_id: str
    filename: str
    source_name: str
    account: str
    provider_id: str
    identity: str
    content_hash: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class _ArchivePaths:
    archive_dir: Path

    def get_emails_dir(self, source_name: str) -> Path:
        return self.archive_dir / "sources" / source_name


def _source(source: dict) -> tuple[str, str]:
    name, account = source.get("name"), source.get("account")
    if not isinstance(name, str) or not name or name in {".", ".."} or Path(name).name != name:
        raise CleanupHold("Source name is not a safe archive directory")
    if not isinstance(account, str) or not account:
        raise CleanupHold("Source account is unavailable")
    return name, account


def _regular(path: Path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise CleanupHold("Cleanup requires regular files without links")
    return info


def _read_regular(path: Path) -> bytes:
    before = _regular(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if opened != before:
            raise CleanupHold("Owned file changed while opening it")
        data = stream.read()
        after = os.fstat(stream.fileno())
    current = _regular(path)
    # Reads may update access time; ownership checks depend on contents and identity.
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(
        getattr(before, field) != getattr(after, field) or getattr(after, field) != getattr(current, field)
        for field in fields
    ):
        raise CleanupHold("Owned file changed while reading it")
    return data


def _index_path(archive_root: Path, db_path: Path | None) -> Path:
    configured = Path(db_path) if db_path is not None else archive_root / "ownmail.db"
    path = Path(os.path.abspath(configured))
    _regular(path)
    if path.parent.resolve(strict=True) != path.parent:
        raise CleanupHold("Archive index directory must not use symbolic links")
    return path


def iter_candidate_ids(archive_root: Path, source: dict, *, db_path: Path | None = None):
    """Traverse an account's index in bounded batches without holding a snapshot."""
    _, account = _source(source)
    try:
        root = Path(archive_root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CleanupHold("Archive root is unavailable for cleanup") from error
    last = ""
    while True:
        try:
            path = _index_path(root, db_path)
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
                rows = conn.execute(
                    "SELECT email_id FROM emails WHERE account = ? AND email_id > ? ORDER BY email_id LIMIT ?",
                    (account, last, _BATCH_SIZE),
                ).fetchall()
        except (OSError, sqlite3.Error, ValueError, RuntimeError) as error:
            raise CleanupHold("Archive index is unavailable for cleanup") from error
        if not rows:
            return
        for (email_id,) in rows:
            if not isinstance(email_id, str) or not email_id:
                raise CleanupHold("Archive index contains an invalid message identity")
            yield email_id
        last = rows[-1][0]


def _owned_path(root: Path, source_name: str, filename: str) -> Path:
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".eml":
        raise CleanupHold("Owned message path is unsafe")
    expected = ("sources", source_name)
    if relative.parts[:2] != expected:
        raise CleanupHold("Owned message is outside the selected source")
    path = root
    for part in relative.parts[:-1]:
        path = path / part
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise CleanupHold("Owned message directory is unavailable or linked")
    return root / relative


def verify_local(archive_root: Path, source: dict, email_id: str, *, db_path: Path | None = None) -> VerifiedCopy:
    """Re-read indexed identity, owned contents, and durable capture metadata."""
    source_name, account = _source(source)
    if not isinstance(email_id, str) or not email_id or email_id.startswith("active-"):
        raise CleanupHold("An Active cache is not an owned archive copy")
    try:
        root = Path(archive_root).resolve(strict=True)
        index = _index_path(root, db_path)
        with closing(sqlite3.connect(index.as_uri() + "?mode=ro", uri=True)) as conn:
            row = conn.execute(
                "SELECT filename, provider_id, content_hash, account, trashed_at, original_filename "
                "FROM emails WHERE email_id = ?",
                (email_id,),
            ).fetchone()
        if row is None:
            raise CleanupHold("Owned message is no longer indexed")
        filename, indexed_id, content_hash, indexed_account, trashed_at, original_filename = row
        if indexed_account != account:
            raise CleanupHold("Owned message belongs to another account")
        if trashed_at is not None or original_filename is not None:
            raise CleanupHold("Local Trash cannot authorize server cleanup")
        if not isinstance(filename, str) or not filename:
            raise CleanupHold("Owned message path is unavailable")
        path = _owned_path(root, source_name, filename)
        raw = _read_regular(path)
        if hashlib.sha256(raw).hexdigest() != content_hash:
            raise CleanupHold("Owned message hash does not match its index")
        metadata = json.loads(_read_regular(sidecar_path(path)))
        if not isinstance(metadata, dict):
            raise CleanupHold("Capture metadata is malformed")
        provenance = capture_provenance(_ArchivePaths(root), path, raw, metadata)
        if provenance is None:
            raise CleanupHold("Legacy capture completeness is unverified")
        if any(not label.strip() for label in metadata["labels"]):
            raise CleanupHold("Capture labels are malformed")
        capture = metadata["capture"]
        if capture["source_name"] != source_name or capture["account"] != account:
            raise CleanupHold("Capture metadata belongs to another source or account")
        expected_id, captured_account, _ = provenance
        if (
            indexed_id != expected_id
            or indexed_account != captured_account
            or email_id != ArchiveDatabase.make_email_id(account, expected_id)
        ):
            raise CleanupHold("Capture identity does not match its index")
        return VerifiedCopy(
            email_id=email_id,
            filename=filename,
            source_name=source_name,
            account=account,
            provider_id=capture["provider_id"],
            identity=capture["identity"],
            content_hash=content_hash,
            labels=tuple(metadata["labels"]),
        )
    except CleanupHold:
        raise
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, RuntimeError) as error:
        raise CleanupHold("Owned contents or complete capture metadata could not be verified") from error
