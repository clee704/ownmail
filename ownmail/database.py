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
                    account TEXT,
                    labels TEXT,
                    email_date TEXT
                )
            """)

            # Add account column if missing (migration from v0.1)
            try:
                conn.execute("ALTER TABLE emails ADD COLUMN account TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Add labels column if missing (migration for label search optimization)
            try:
                conn.execute("ALTER TABLE emails ADD COLUMN labels TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Add email_date column if missing (migration for proper date filtering)
            try:
                conn.execute("ALTER TABLE emails ADD COLUMN email_date TEXT")
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

            # Index for date-based sorting (filename starts with YYYYMMDD_HHMMSS)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_filename
                ON emails(filename)
            """)

            # Index for label queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_labels
                ON emails(labels)
            """)

            # Index for email_date (for date sorting and filtering)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_date
                ON emails(email_date)
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

    def delete_sync_state(self, account: str, key: str) -> None:
        """Delete sync state value for an account.

        Args:
            account: Email address
            key: State key
        """
        state_key = f"{account}/{key}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sync_state WHERE key = ?", (state_key,))
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

    def get_email_by_id(self, message_id: str) -> Optional[tuple]:
        """Get email info by message ID.

        Args:
            message_id: Message ID

        Returns:
            Tuple of (message_id, filename, downloaded_at, content_hash, account)
            or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT message_id, filename, downloaded_at, content_hash, account FROM emails WHERE message_id = ?",
                (message_id,)
            ).fetchone()
            return result

    def mark_downloaded(
        self,
        message_id: str,
        filename: str,
        content_hash: str = None,
        account: str = None,
        conn: sqlite3.Connection = None,
        email_date: str = None,
    ) -> None:
        """Mark a message as downloaded.

        Args:
            message_id: Provider-specific message ID
            filename: Relative path to .eml file
            content_hash: SHA256 hash of file content
            account: Email address
            conn: Optional existing connection (for batching)
            email_date: Parsed email date in ISO format (YYYY-MM-DDTHH:MM:SS)
        """
        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO emails
                (message_id, filename, downloaded_at, content_hash, account, email_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, filename, datetime.now().isoformat(), content_hash, account, email_date)
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
        labels: str = "",
        skip_delete: bool = False,
    ) -> None:
        """Add email to full-text search index.

        Args:
            message_id: Message ID
            subject, sender, recipients, date_str, body, attachments: Parsed email fields
            labels: Gmail labels (stored in emails table for fast filtering)
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
            # Update labels in main emails table for fast label filtering
            if labels:
                conn.execute(
                    "UPDATE emails SET labels = ? WHERE message_id = ?",
                    (labels, message_id)
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

    def search(
        self,
        query: str,
        account: str = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "relevance",
        include_unknown: bool = False,
    ) -> List[Tuple]:
        """Search emails using FTS5.

        Args:
            query: Search query (supports from:, subject:, before:, after:, label:, etc.)
            account: Filter to specific account (optional)
            limit: Maximum results
            offset: Number of results to skip (for pagination)
            sort: Sort order - 'relevance', 'date_desc', or 'date_asc'
            include_unknown: Include emails in unknown/ folder (default: False)

        Returns:
            List of tuples: (message_id, filename, subject, sender, date_str, snippet)
        """
        with sqlite3.connect(self.db_path) as conn:
            # Extract special filters from query
            fts_query, filters = self._parse_query(query)

            # Determine ORDER BY clause - use email_date for proper date sorting
            if sort == "date_desc":
                order_by = "e.email_date DESC"
            elif sort == "date_asc":
                order_by = "e.email_date ASC"
            else:
                order_by = "rank"  # FTS5 relevance

            # Build WHERE clause for special filters
            where_clauses = []
            params = []

            # Exclude emails in unknown/ folder unless explicitly requested
            if not include_unknown:
                where_clauses.append("e.email_date IS NOT NULL")

            if fts_query.strip():
                where_clauses.append("emails_fts MATCH ?")
                params.append(fts_query)

            if account:
                where_clauses.append("e.account = ?")
                params.append(account)

            # Date filters - normalize path to /emails/YYYY/MM/YYYYMMDD for comparison
            # Works with both old (emails/...) and new (accounts/.../emails/...) paths
            # CASE: if contains /emails/, extract from there; else prepend / to old format
            date_path_expr = (
                "CASE WHEN instr(e.filename, '/emails/') > 0 "
                "THEN substr(e.filename, instr(e.filename, '/emails/')) "
                "ELSE '/' || e.filename END"
            )
            if filters.get("after"):
                where_clauses.append(f"({date_path_expr}) >= ?")
                params.append(filters["after"])
            if filters.get("before"):
                where_clauses.append(f"({date_path_expr}) < ?")
                params.append(filters["before"])

            # Label filter uses indexed labels column on emails table
            has_label_filter = filters.get("label")

            params.extend([limit, offset])

            # If no FTS query and no label filter, we can skip FTS entirely
            if not fts_query.strip() and not has_label_filter:
                # No text search, just date/account filter - use emails table only
                # For non-FTS queries, "relevance" doesn't make sense, default to date desc
                no_fts_order = order_by if sort != "relevance" else "e.filename DESC"

                email_clauses = []
                email_params = []
                # Exclude emails without parsed dates unless explicitly requested
                if not include_unknown:
                    email_clauses.append("email_date IS NOT NULL")
                if account:
                    email_clauses.append("account = ?")
                    email_params.append(account)
                # Date path normalization: old format emails/... -> /emails/...
                date_path_expr = (
                    "CASE WHEN instr(filename, '/emails/') > 0 "
                    "THEN substr(filename, instr(filename, '/emails/')) "
                    "ELSE '/' || filename END"
                )
                if filters.get("after"):
                    email_clauses.append(f"({date_path_expr}) >= ?")
                    email_params.append(filters["after"])
                if filters.get("before"):
                    email_clauses.append(f"({date_path_expr}) < ?")
                    email_params.append(filters["before"])

                email_where = " AND ".join(email_clauses) if email_clauses else "1=1"
                email_params.extend([limit, offset])

                # Just get from emails table - skip FTS entirely for speed
                # Web UI will get subject/sender from the email file itself
                results = conn.execute(
                    f"""
                    SELECT
                        message_id,
                        filename,
                        '' as subject,
                        '' as sender,
                        '' as date_str,
                        '' as snippet
                    FROM emails
                    WHERE {email_where}
                    ORDER BY email_date {"DESC" if "DESC" in no_fts_order else "ASC"}
                    LIMIT ? OFFSET ?
                    """,
                    email_params
                ).fetchall()
            elif not fts_query.strip():
                # Label filter only (no FTS search terms) - query emails table directly
                # Use indexed labels column for fast filtering, skip FTS join entirely
                no_fts_order = order_by if sort != "relevance" else "e.filename DESC"

                email_clauses = []
                email_params = []
                # Exclude emails without parsed dates unless explicitly requested
                if not include_unknown:
                    email_clauses.append("email_date IS NOT NULL")
                if account:
                    email_clauses.append("account = ?")
                    email_params.append(account)
                # Date path normalization: old format emails/... -> /emails/...
                date_path_expr = (
                    "CASE WHEN instr(filename, '/emails/') > 0 "
                    "THEN substr(filename, instr(filename, '/emails/')) "
                    "ELSE '/' || filename END"
                )
                if filters.get("after"):
                    email_clauses.append(f"({date_path_expr}) >= ?")
                    email_params.append(filters["after"])
                if filters.get("before"):
                    email_clauses.append(f"({date_path_expr}) < ?")
                    email_params.append(filters["before"])
                if filters.get("label"):
                    email_clauses.append("labels LIKE ?")
                    email_params.append(f"%{filters['label']}%")

                email_where = " AND ".join(email_clauses) if email_clauses else "1=1"
                email_params.extend([limit, offset])

                # Query emails table only - web layer fills in subject/sender from file
                order_col = "email_date DESC" if "DESC" in no_fts_order else "email_date ASC"
                results = conn.execute(
                    f"""
                    SELECT
                        message_id,
                        filename,
                        '' as subject,
                        '' as sender,
                        '' as date_str,
                        '' as snippet
                    FROM emails
                    WHERE {email_where}
                    ORDER BY {order_col}
                    LIMIT ? OFFSET ?
                    """,
                    email_params
                ).fetchall()
            elif sort in ("date_desc", "date_asc"):
                # For date-sorted FTS queries: first get FTS matches, then sort by date
                # This is faster than EXISTS because FTS search is done once upfront

                # Build emails table WHERE clause
                email_clauses = []
                email_params: list = []
                # Exclude emails without parsed dates unless explicitly requested
                if not include_unknown:
                    email_clauses.append("e.email_date IS NOT NULL")
                if account:
                    email_clauses.append("e.account = ?")
                    email_params.append(account)
                # Date path normalization: old format emails/... -> /emails/...
                date_path_expr = (
                    "CASE WHEN instr(e.filename, '/emails/') > 0 "
                    "THEN substr(e.filename, instr(e.filename, '/emails/')) "
                    "ELSE '/' || e.filename END"
                )
                if filters.get("after"):
                    email_clauses.append(f"({date_path_expr}) >= ?")
                    email_params.append(filters["after"])
                if filters.get("before"):
                    email_clauses.append(f"({date_path_expr}) < ?")
                    email_params.append(filters["before"])
                # Use indexed labels column instead of FTS body LIKE
                if filters.get("label"):
                    email_clauses.append("e.labels LIKE ?")
                    email_params.append(f"%{filters['label']}%")
                email_where = " AND ".join(email_clauses) if email_clauses else "1=1"

                # Use JOIN instead of EXISTS - SQLite can optimize this better
                # FTS query + params come first, then email params, then limit/offset
                all_params = [fts_query] + email_params + [limit, offset]

                # JOIN FTS matches with emails table, sort by filename
                results = conn.execute(
                    f"""
                    SELECT
                        e.message_id,
                        e.filename,
                        '' as subject,
                        '' as sender,
                        '' as date_str,
                        '' as snippet
                    FROM emails_fts f
                    JOIN emails e ON e.message_id = f.message_id
                    WHERE f.emails_fts MATCH ?
                      AND {email_where}
                    ORDER BY e.email_date {"DESC" if sort == "date_desc" else "ASC"}
                    LIMIT ? OFFSET ?
                    """,
                    all_params
                ).fetchall()
            else:
                # Relevance sort - let FTS5 drive
                where_sql = " AND ".join(where_clauses)
                # Add label filter using indexed column
                label_filter = ""
                if has_label_filter:
                    label_filter = "AND e.labels LIKE ?"
                    # Insert before limit/offset
                    params.insert(-2, f"%{filters['label']}%")
                results = conn.execute(
                    f"""
                    SELECT
                        e.message_id,
                        e.filename,
                        f.subject,
                        f.sender,
                        f.date_str,
                        snippet(emails_fts, 5, '>>>', '<<<', '...', 32) as snippet
                    FROM emails_fts f
                    JOIN emails e ON e.message_id = f.message_id
                    WHERE {where_sql} {label_filter}
                    ORDER BY {order_by}
                    LIMIT ? OFFSET ?
                    """,
                    params
                ).fetchall()
            return results

    def _parse_query(self, query: str) -> tuple:
        """Parse query and extract special filters.

        Returns:
            Tuple of (fts_query, filters_dict)
        """
        filters = {}

        # Extract before:YYYY-MM-DD or before:YYYYMMDD
        before_match = re.search(r'\bbefore:(\d{4}-?\d{2}-?\d{2})\b', query)
        if before_match:
            date_str = before_match.group(1).replace("-", "")
            # Convert to path format that works with substr extraction: /emails/YYYY/MM/YYYYMMDD
            year, month = date_str[:4], date_str[4:6]
            filters["before"] = f"/emails/{year}/{month}/{date_str}"
            query = query[:before_match.start()] + query[before_match.end():]

        # Extract after:YYYY-MM-DD or after:YYYYMMDD
        after_match = re.search(r'\bafter:(\d{4}-?\d{2}-?\d{2})\b', query)
        if after_match:
            date_str = after_match.group(1).replace("-", "")
            # Convert to path format that works with substr extraction: /emails/YYYY/MM/YYYYMMDD
            year, month = date_str[:4], date_str[4:6]
            filters["after"] = f"/emails/{year}/{month}/{date_str}"
            query = query[:after_match.start()] + query[after_match.end():]

        # Extract label:xxx or tag:xxx
        label_match = re.search(r'\b(?:label|tag):(\S+)\b', query)
        if label_match:
            filters["label"] = label_match.group(1)
            query = query[:label_match.start()] + query[label_match.end():]

        # Clean up the remaining query
        query = query.strip()

        # Remove orphaned AND operators (AND is implicit in FTS5 anyway)
        # e.g., "after:2025-01 AND before:2025-02" -> "AND" after extraction -> ""
        # e.g., "after:2025-01 AND invoice" -> "AND invoice" -> "invoice"
        # NOTE: We intentionally do NOT strip OR/NOT - if user writes "after:X OR text",
        # they expect OR semantics which we don't support, so let it error clearly.
        query = re.sub(r'^\s*AND\s+', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+AND\s*$', '', query, flags=re.IGNORECASE)
        if query.upper() == 'AND':
            query = ''

        # Convert remaining query to FTS5 syntax
        fts_query = self._convert_query(query.strip())

        return fts_query, filters

    def _convert_query(self, query: str) -> str:
        """Convert user query to FTS5 syntax."""
        # Convert field prefixes
        query = re.sub(r'\bfrom:', 'sender:', query)
        query = re.sub(r'\bto:', 'recipients:', query)
        query = re.sub(r'\battachment:', 'attachments:', query)

        # Quote values after field: prefixes that contain special characters
        # FTS5 special chars: . @ - + * " ( ) : ^
        def quote_field_value(match):
            field = match.group(1)
            value = match.group(2)
            # If value contains special chars, quote it
            if re.search(r'[.@\-+*"():^]', value):
                # Escape any existing quotes and wrap in quotes
                value = '"' + value.replace('"', '""') + '"'
            return field + ':' + value

        query = re.sub(r'\b(sender|recipients|subject|attachments):(\S+)', quote_field_value, query)

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
                # For filtered count, we need actual COUNT
                return conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE account = ?",
                    (account,)
                ).fetchone()[0]
            else:
                # Use MAX(rowid) as fast approximation for total count
                # This is ~100x faster than COUNT(*) on slow drives
                result = conn.execute("SELECT MAX(rowid) FROM emails").fetchone()[0]
                return result or 0

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
