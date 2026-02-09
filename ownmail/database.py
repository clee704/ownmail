"""SQLite database for tracking emails and full-text search."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


class ArchiveDatabase:
    """SQLite database for tracking emails and full-text search.

    Schema:
    - emails: Track downloaded emails with message_id, filename, hash, account
    - sync_state: Key-value store for per-account sync state
    - emails_fts: FTS5 virtual table for full-text search
    """

    def __init__(self, archive_dir: Path):
        """Initialize the archive database.

        Args:
            archive_dir: Directory containing the archive (database will be created here)
        """
        self.archive_dir = archive_dir
        self.db_path = archive_dir / "ownmail.db"
        archive_dir.mkdir(parents=True, exist_ok=True)

        is_new_db = not self.db_path.exists()
        if is_new_db:
            print(f"Creating new database: {self.db_path}")

        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Main emails table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    message_id TEXT PRIMARY KEY,
                    filename TEXT,
                    downloaded_at TEXT,
                    content_hash TEXT,
                    indexed_hash TEXT,
                    account TEXT
                )
            """)

            # Add account column if missing (migration from v0.1)
            try:
                conn.execute("ALTER TABLE emails ADD COLUMN account TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Sync state for incremental backup (per-account)
            # Key format: "<account>/<key>" e.g., "alice@gmail.com/history_id"
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Full-text search index using FTS5
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
                    message_id,
                    subject,
                    sender,
                    recipients,
                    date_str,
                    body,
                    attachments,
                    tokenize='porter unicode61'
                )
            """)

            # Index for per-account queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_account
                ON emails(account)
            """)

            # Index for indexed_hash queries (for stats)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_indexed_hash
                ON emails(indexed_hash)
            """)

            conn.commit()

    # -------------------------------------------------------------------------
    # Sync State (per-account)
    # -------------------------------------------------------------------------

    def get_sync_state(self, account: str, key: str) -> Optional[str]:
        """Get sync state value for an account.

        Args:
            account: Email address
            key: State key (e.g., 'history_id')

        Returns:
            State value, or None if not set
        """
        state_key = f"{account}/{key}"
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?",
                (state_key,)
            ).fetchone()
            return result[0] if result else None

    def set_sync_state(self, account: str, key: str, value: str) -> None:
        """Set sync state value for an account.

        Args:
            account: Email address
            key: State key
            value: State value
        """
        state_key = f"{account}/{key}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
                (state_key, value)
            )
            conn.commit()

    # Legacy methods for backward compatibility
    def get_history_id(self, account: str = None) -> Optional[str]:
        """Get Gmail history ID for an account."""
        if account:
            return self.get_sync_state(account, "history_id")
        # Legacy: check for non-account-scoped key
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT value FROM sync_state WHERE key = 'history_id'"
            ).fetchone()
            return result[0] if result else None

    def set_history_id(self, history_id: str, account: str = None) -> None:
        """Set Gmail history ID for an account."""
        if account:
            self.set_sync_state(account, "history_id", history_id)
        else:
            # Legacy: non-account-scoped
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('history_id', ?)",
                    (history_id,)
                )
                conn.commit()

    # -------------------------------------------------------------------------
    # Email Tracking
    # -------------------------------------------------------------------------

    def is_downloaded(self, message_id: str, account: str = None) -> bool:
        """Check if a message has already been downloaded."""
        with sqlite3.connect(self.db_path) as conn:
            if account:
                result = conn.execute(
                    "SELECT 1 FROM emails WHERE message_id = ? AND account = ?",
                    (message_id, account)
                ).fetchone()
            else:
                result = conn.execute(
                    "SELECT 1 FROM emails WHERE message_id = ?",
                    (message_id,)
                ).fetchone()
            return result is not None

    def get_downloaded_ids(self, account: str = None) -> set:
        """Get all downloaded message IDs."""
        with sqlite3.connect(self.db_path) as conn:
            if account:
                results = conn.execute(
                    "SELECT message_id FROM emails WHERE account = ?",
                    (account,)
                ).fetchall()
            else:
                results = conn.execute(
                    "SELECT message_id FROM emails"
                ).fetchall()
            return {row[0] for row in results}

    def mark_downloaded(
        self,
        message_id: str,
        filename: str,
        content_hash: str = None,
        account: str = None,
        conn: sqlite3.Connection = None
    ) -> None:
        """Mark a message as downloaded.

        Args:
            message_id: Provider-specific message ID
            filename: Relative path to .eml file
            content_hash: SHA256 hash of file content
            account: Email address
            conn: Optional existing connection (for batching)
        """
        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO emails
                (message_id, filename, downloaded_at, content_hash, account)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, filename, datetime.now().isoformat(), content_hash, account)
            )
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    # -------------------------------------------------------------------------
    # Full-Text Search
    # -------------------------------------------------------------------------

    def index_email(
        self,
        message_id: str,
        subject: str,
        sender: str,
        recipients: str,
        date_str: str,
        body: str,
        attachments: str,
        conn: sqlite3.Connection = None,
        skip_delete: bool = False,
    ) -> None:
        """Add email to full-text search index.

        Args:
            message_id: Message ID
            subject, sender, recipients, date_str, body, attachments: Parsed email fields
            conn: Optional existing connection (for batching)
            skip_delete: If True, skip DELETE (for new emails not yet in FTS)
        """
        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        try:
            if not skip_delete:
                conn.execute("DELETE FROM emails_fts WHERE message_id = ?", (message_id,))
            conn.execute(
                """
                INSERT INTO emails_fts
                (message_id, subject, sender, recipients, date_str, body, attachments)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, subject, sender, recipients, date_str, body, attachments)
            )
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def is_indexed(self, message_id: str) -> bool:
        """Check if a message is in the search index."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM emails_fts WHERE message_id = ?",
                (message_id,)
            ).fetchone()
            return result is not None

    def search(self, query: str, account: str = None, limit: int = 50) -> List[Tuple]:
        """Search emails using FTS5.

        Args:
            query: Search query (supports from:, subject:, etc.)
            account: Filter to specific account (optional)
            limit: Maximum results

        Returns:
            List of tuples: (message_id, filename, subject, sender, date_str, snippet)
        """
        with sqlite3.connect(self.db_path) as conn:
            fts_query = self._convert_query(query)

            if account:
                results = conn.execute(
                    """
                    SELECT
                        e.message_id,
                        e.filename,
                        f.subject,
                        f.sender,
                        f.date_str,
                        snippet(emails_fts, 5, '>>>', '<<<', '...', 32) as snippet
                    FROM emails_fts f
                    JOIN emails e ON e.message_id = f.message_id
                    WHERE emails_fts MATCH ? AND e.account = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, account, limit)
                ).fetchall()
            else:
                results = conn.execute(
                    """
                    SELECT
                        e.message_id,
                        e.filename,
                        f.subject,
                        f.sender,
                        f.date_str,
                        snippet(emails_fts, 5, '>>>', '<<<', '...', 32) as snippet
                    FROM emails_fts f
                    JOIN emails e ON e.message_id = f.message_id
                    WHERE emails_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit)
                ).fetchall()
            return results

    def _convert_query(self, query: str) -> str:
        """Convert user query to FTS5 syntax."""
        query = re.sub(r'\bfrom:', 'sender:', query)
        query = re.sub(r'\bto:', 'recipients:', query)
        query = re.sub(r'\battachment:', 'attachments:', query)
        return query

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_email_count(self, account: str = None) -> int:
        """Get quick email count for an account.

        This is faster than get_stats() for just displaying counts.

        Args:
            account: Filter to specific account (optional)

        Returns:
            Number of emails
        """
        with sqlite3.connect(self.db_path, timeout=5.0) as conn:
            if account:
                return conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE account = ?",
                    (account,)
                ).fetchone()[0]
            else:
                return conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]

    def get_stats(self, account: str = None) -> dict:
        """Get archive statistics.

        Args:
            account: Filter to specific account (optional)

        Returns:
            Dictionary with total_emails, indexed_emails, oldest_backup, newest_backup
        """
        with sqlite3.connect(self.db_path, timeout=5.0) as conn:
            if account:
                # Single query for all stats
                row = conn.execute(
                    """SELECT COUNT(*), MIN(downloaded_at), MAX(downloaded_at)
                       FROM emails WHERE account = ?""",
                    (account,)
                ).fetchone()
                email_count, oldest, newest = row
            else:
                row = conn.execute(
                    "SELECT COUNT(*), MIN(downloaded_at), MAX(downloaded_at) FROM emails"
                ).fetchone()
                email_count, oldest, newest = row

            # Count indexed emails (those with indexed_hash set)
            # This is faster than counting FTS5 rows
            indexed_count = conn.execute(
                "SELECT COUNT(*) FROM emails WHERE indexed_hash IS NOT NULL"
            ).fetchone()[0]

            return {
                "total_emails": email_count,
                "indexed_emails": indexed_count,
                "oldest_backup": oldest,
                "newest_backup": newest,
            }

    def clear_index(self) -> None:
        """Clear the full-text search index."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM emails_fts")
            conn.commit()

    # -------------------------------------------------------------------------
    # Account Management
    # -------------------------------------------------------------------------

    def get_accounts(self) -> List[str]:
        """Get list of unique accounts in the database."""
        with sqlite3.connect(self.db_path) as conn:
            results = conn.execute(
                "SELECT DISTINCT account FROM emails WHERE account IS NOT NULL"
            ).fetchall()
            return [row[0] for row in results]

    def get_email_count_by_account(self) -> dict:
        """Get email count per account.

        Returns:
            Dictionary mapping account to email count
        """
        with sqlite3.connect(self.db_path) as conn:
            results = conn.execute(
                """
                SELECT COALESCE(account, '(legacy)') as acct, COUNT(*)
                FROM emails
                GROUP BY account
                """
            ).fetchall()
            return {row[0]: row[1] for row in results}
