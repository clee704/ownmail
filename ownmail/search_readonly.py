"""Existing-data search views: no initialization, migration or cache repair.

SQLite mode=ro sees committed WAL data and may update normal WAL/SHM coordination
files. Each index is held in a read transaction for this command. Temporary query
tables stay in memory; source database contents cannot be written through these
handles. Active files must agree with their existing index, or search is unavailable.
"""

import json
import os
import sqlite3
from contextlib import ExitStack, closing, contextmanager, nullcontext
from pathlib import Path

from ownmail.active_cache import ActiveCache
from ownmail.archive import EmailArchive
from ownmail.config import get_db_dir, gmail_accounts
from ownmail.database import ArchiveDatabase


class SearchUnavailable(Exception):
    """A required existing search index or cache cannot be read without repair."""


class _SearchDatabase(ArchiveDatabase):
    def __init__(self, db_path, accounts, stack):
        self.db_path = db_path
        self.gmail_accounts = accounts
        self._reader = stack.enter_context(closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)))
        self._reader.execute("PRAGMA temp_store=MEMORY")
        self._reader.execute("BEGIN")
        # Pin the read snapshot and reject missing/old schemas without migrating.
        self._reader.execute(
            "SELECT email_id, provider_id, filename, downloaded_at, content_hash, indexed_hash, account, "
            "trashed_at, original_filename, email_date, subject, sender, sender_email, recipients, "
            "date_str, snippet, has_attachments FROM emails LIMIT 0"
        )
        self._reader.execute("SELECT email_rowid, label, email_date FROM email_labels LIMIT 0")
        self._reader.execute("SELECT email_rowid, recipient_email FROM email_recipients LIMIT 0")
        self._reader.execute("SELECT subject, sender, recipients, body, attachments FROM emails_fts LIMIT 0")

    def _connect(self):
        # A sqlite connection context manager commits on exit; retain our snapshot.
        return nullcontext(self._reader)

    def search(self, query, **options):
        return super().search(query, _raise_fts_errors=True, **options)


class _SearchCache(ActiveCache):
    def __init__(self, archive_dir, cache_dir, accounts, stack):
        self.archive_dir = archive_dir.resolve()
        self.cache_dir = cache_dir.resolve()
        self.gmail_accounts = accounts
        self._check_root()
        marker = json.loads(self._read_file(self.cache_dir / "active-cache.json"))
        if marker != {"version": 1, "archive": str(self.archive_dir)}:
            raise ValueError("Active cache belongs to a different archive or version")
        for name in ("entries", "messages", "sources"):
            self._check_directory(self.cache_dir / name)
        self._check_database_paths()
        self._db = _SearchDatabase(self.cache_dir / "ownmail.db", accounts, stack)
        self._verified_payloads = {}
        self._entries = super().list_entries()
        sources = {(entry["source_name"], entry["account"]) for entry in self._entries}
        self._statuses = {key: super(_SearchCache, self).source_status(*key) for key in sources}
        rows = self._db._reader.execute(
            "SELECT email_id, filename, content_hash, indexed_hash, account, downloaded_at FROM emails"
        ).fetchall()
        expected = {
            (
                entry["id"],
                entry["filename"],
                entry["content_hash"],
                entry["content_hash"],
                entry["account"],
                entry["content_at"],
            )
            for entry in self._entries
        }
        labels = set(
            self._db._reader.execute(
                "SELECT e.email_id, el.label FROM emails e JOIN email_labels el ON e.rowid=el.email_rowid"
            )
        )
        expected_labels = {(entry["id"], label) for entry in self._entries for label in entry["labels"]}
        if set(rows) != expected or labels != expected_labels:
            raise SearchUnavailable("Active search index needs repair; JSON search does not rebuild it")

    def list_entries(self, source_name=None, account=None):
        return [
            entry
            for entry in self._entries
            if (
                (source_name is None or entry["source_name"] == source_name)
                and (account is None or entry["account"] == account)
            )
        ]

    def source_status(self, source_name, account):
        return self._statuses.get((source_name, account))

    def check_unchanged(self):
        if super().list_entries() != self._entries or any(
            super(_SearchCache, self).source_status(*key) != status for key, status in self._statuses.items()
        ):
            raise SearchUnavailable("Active cache changed during search; retry the command")


class _SearchArchive(EmailArchive):
    def __init__(self, archive_dir, config, stack):
        if not archive_dir.is_dir():
            raise SearchUnavailable("Archive directory is unavailable")
        self.archive_dir = archive_dir
        self.config = config
        accounts = gmail_accounts(config)
        self.db = _SearchDatabase((get_db_dir(config) or archive_dir) / "ownmail.db", accounts, stack)
        root = archive_dir.resolve()
        cache_dir = (
            Path(config["active_cache_dir"])
            if config.get("active_cache_dir")
            else root.with_name(f".{root.name}-active")
        )
        self._active_cache = _SearchCache(root, cache_dir, accounts, stack) if os.path.lexists(cache_dir) else None

    def active_cache(self, *, create=False):
        if create:
            raise SearchUnavailable("JSON search cannot create an Active cache")
        return self._active_cache


@contextmanager
def open_search_archive(archive_dir: Path, config: dict):
    """Yield the existing consolidated view, closing every pinned read handle."""
    with ExitStack() as stack:
        try:
            archive = _SearchArchive(archive_dir, config, stack)
        except (OSError, ValueError, sqlite3.Error) as error:
            raise SearchUnavailable(f"Existing search data is unavailable: {error}") from error
        yield archive
        cache = archive.active_cache()
        if cache is not None:
            try:
                cache.check_unchanged()
            except (OSError, ValueError) as error:
                raise SearchUnavailable(f"Active cache is unavailable: {error}") from error
