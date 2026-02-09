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
            # Main emails table - stores all metadata for fast indexed queries
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    message_id TEXT PRIMARY KEY,
                    filename TEXT,
                    downloaded_at TEXT,
                    content_hash TEXT,
                    indexed_hash TEXT,
                    account TEXT,
                    labels TEXT,
                    email_date TEXT,
                    subject TEXT,
                    sender TEXT,
                    recipients TEXT,
                    date_str TEXT,
                    snippet TEXT
                )
            """)

            # Add new metadata columns if missing (migration)
            for col in ['subject', 'sender', 'recipients', 'date_str', 'snippet']:
                try:
                    conn.execute(f"ALTER TABLE emails ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # Legacy migrations
            for col in ['account', 'labels', 'email_date']:
                try:
                    conn.execute(f"ALTER TABLE emails ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # Add sender_email and recipient_emails for fast indexed lookups
            for col in ['sender_email', 'recipient_emails']:
                try:
                    conn.execute(f"ALTER TABLE emails ADD COLUMN {col} TEXT")
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

            # Full-text search index using FTS5 - contentless mode
            # We don't store body in emails table (too large), so use contentless FTS
            # This means we manually manage inserts/deletes in index_email()
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
                    subject,
                    sender,
                    recipients,
                    body,
                    attachments,
                    content='',
                    tokenize='porter unicode61'
                )
            """)

            # Note: With contentless FTS (content=''), we manually manage FTS entries
            # in index_email() rather than using triggers. This is because:
            # 1. body/attachments are not stored in emails table (too large)
            # 2. Contentless FTS requires explicit insert/delete operations

            # Indexes for fast queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_account ON emails(account)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_indexed_hash ON emails(indexed_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_filename ON emails(filename)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_labels ON emails(labels)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(email_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_sender_email ON emails(sender_email)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_recipient_emails ON emails(recipient_emails)")

            conn.commit()

    # -------------------------------------------------------------------------
    # Email address parsing helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_email(sender_str: str) -> Optional[str]:
        """Extract email from 'Name <email>' or just 'email'."""
        if not sender_str:
            return None
        # Try to extract from angle brackets
        match = re.search(r'<([^>]+)>', sender_str)
        if match:
            return match.group(1).lower().strip()
        # If no brackets, check if it's just an email
        if '@' in sender_str:
            return sender_str.lower().strip()
        return None

    @staticmethod
    def _normalize_recipients(recipients_str: str) -> Optional[str]:
        """Convert 'a@b.com, Name <c@d.com>' to ',a@b.com,c@d.com,' for exact matching."""
        if not recipients_str:
            return None
        emails = []
        for part in recipients_str.split(','):
            part = part.strip()
            if not part:
                continue
            # Try to extract from angle brackets first
            match = re.search(r'<([^>]+)>', part)
            if match:
                email = match.group(1).lower().strip()
            elif '@' in part:
                email = part.lower().strip()
            else:
                continue
            if email:
                emails.append(email)
        if emails:
            return ',' + ','.join(emails) + ','
        return None

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
        """Add email to search index by updating emails table metadata and FTS.

        Args:
            message_id: Message ID
            subject, sender, recipients, date_str, body, attachments: Parsed email fields
            labels: Gmail labels
            conn: Optional existing connection (for batching)
            skip_delete: Ignored (kept for API compatibility)
        """
        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        # Create snippet from body (first 200 chars)
        snippet = body[:200] + "..." if len(body) > 200 else body

        try:
            # Check if already indexed BEFORE updating (for FTS delete logic)
            row = conn.execute(
                "SELECT rowid, subject FROM emails WHERE message_id = ?",
                (message_id,)
            ).fetchone()
            if not row:
                # Message not in database yet - can't index
                if should_close:
                    conn.close()
                return

            rowid = row[0]
            was_indexed = row[1] is not None  # Had subject before

            # Extract email addresses for indexed lookups
            sender_email = self._extract_email(sender)
            recipient_emails = self._normalize_recipients(recipients)

            # Update metadata in emails table
            conn.execute(
                """
                UPDATE emails SET
                    subject = ?,
                    sender = ?,
                    recipients = ?,
                    date_str = ?,
                    labels = ?,
                    snippet = ?,
                    sender_email = ?,
                    recipient_emails = ?
                WHERE message_id = ?
                """,
                (subject, sender, recipients, date_str, labels, snippet, sender_email, recipient_emails, message_id)
            )

            # Update FTS (contentless mode - we manage manually)
            if was_indexed:
                # Delete old FTS entry (contentless FTS requires exact content)
                # We don't have the old content, so we need a different approach
                # Option 1: Store old content - too expensive
                # Option 2: Just insert (may cause duplicates - not ideal for reindex)
                # Option 3: Use delete-all for this rowid and rebuild
                # For simplicity, we skip delete and just insert. Reindex handles cleanup.
                pass
            # Insert new FTS entry
            conn.execute(
                "INSERT INTO emails_fts(rowid, subject, sender, recipients, body, attachments) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (rowid, subject, sender, recipients, body, attachments)
            )

            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def is_indexed(self, message_id: str) -> bool:
        """Check if a message is in the search index (has metadata populated)."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM emails WHERE message_id = ? AND subject IS NOT NULL",
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
        """Search emails.

        Args:
            query: Search query (supports from:, subject:, before:, after:, label:, etc.)
            account: Filter to specific account (optional)
            limit: Maximum results
            offset: Number of results to skip (for pagination)
            sort: Sort order - 'relevance', 'date_desc', or 'date_asc'
            include_unknown: Include emails without parsed dates (default: False)

        Returns:
            List of tuples: (message_id, filename, subject, sender, date_str, snippet)
        """
        with sqlite3.connect(self.db_path) as conn:
            # Extract special filters from query
            fts_query, filters = self._parse_query(query)

            # Build WHERE clause for emails table
            where_clauses = []
            params = []

            # Exclude emails without parsed dates unless explicitly requested
            if not include_unknown:
                where_clauses.append("e.email_date IS NOT NULL")

            if account:
                where_clauses.append("e.account = ?")
                params.append(account)

            # Date filters - use indexed email_date column
            if filters.get("after"):
                where_clauses.append("e.email_date >= ?")
                params.append(filters["after"])
            if filters.get("before"):
                where_clauses.append("e.email_date < ?")
                params.append(filters["before"])

            # Label filter - use indexed labels column
            if filters.get("label"):
                where_clauses.append("e.labels LIKE ?")
                params.append(f"%{filters['label']}%")

            # Sender filter - use exact match on sender_email if it's an email address
            if filters.get("sender"):
                sender_val = filters["sender"]
                if '@' in sender_val:
                    # Email address - exact match on indexed sender_email column (fast)
                    where_clauses.append("e.sender_email = ?")
                    params.append(sender_val.lower())
                else:
                    # Name search - will be handled by FTS below
                    # Re-add to fts_query
                    filters["sender_fts"] = sender_val

            # Recipients filter - use exact match on recipient_emails if it's an email address
            if filters.get("recipients"):
                recipients_val = filters["recipients"]
                if '@' in recipients_val:
                    # Email address - search in normalized recipient_emails (fast with LIKE on indexed column)
                    # Format: ",a@b.com,c@d.com," so we search for ",email,"
                    where_clauses.append("e.recipient_emails LIKE ?")
                    params.append(f"%,{recipients_val.lower()},%")
                else:
                    # Name search - will be handled by FTS below
                    filters["recipients_fts"] = recipients_val

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Add name-based sender/recipients searches back to FTS query
            fts_parts = []
            if fts_query.strip():
                fts_parts.append(fts_query.strip())
            if filters.get("sender_fts"):
                # Name search on sender field via FTS
                fts_parts.append(f'sender:{filters["sender_fts"]}')
            if filters.get("recipients_fts"):
                # Name search on recipients field via FTS
                fts_parts.append(f'recipients:{filters["recipients_fts"]}')
            fts_query = ' '.join(fts_parts)

            # Determine sort order
            if sort == "date_desc":
                order_by = "e.email_date DESC"
            elif sort == "date_asc":
                order_by = "e.email_date ASC"
            else:
                order_by = "e.email_date DESC"  # Default for non-FTS queries

            # If there's a text search query, use FTS
            if fts_query.strip():
                if sort == "relevance":
                    order_by = "rank"

                # JOIN with FTS using rowid
                fts_params = [fts_query] + params + [limit, offset]
                results = conn.execute(
                    f"""
                    SELECT
                        e.message_id,
                        e.filename,
                        e.subject,
                        e.sender,
                        e.date_str,
                        e.snippet
                    FROM emails e
                    JOIN emails_fts f ON f.rowid = e.rowid
                    WHERE f.emails_fts MATCH ?
                      AND {where_sql}
                    ORDER BY {order_by}
                    LIMIT ? OFFSET ?
                    """,
                    fts_params
                ).fetchall()
            else:
                # No text search - query emails table only (fast with indexes)
                params.extend([limit, offset])
                results = conn.execute(
                    f"""
                    SELECT
                        message_id,
                        filename,
                        subject,
                        sender,
                        date_str,
                        snippet
                    FROM emails e
                    WHERE {where_sql}
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
            # Convert to ISO 8601 format for email_date column comparison
            year, month, day = date_str[:4], date_str[4:6], date_str[6:8]
            filters["before"] = f"{year}-{month}-{day}"
            query = query[:before_match.start()] + query[before_match.end():]

        # Extract after:YYYY-MM-DD or after:YYYYMMDD
        after_match = re.search(r'\bafter:(\d{4}-?\d{2}-?\d{2})\b', query)
        if after_match:
            date_str = after_match.group(1).replace("-", "")
            # Convert to ISO 8601 format for email_date column comparison
            year, month, day = date_str[:4], date_str[4:6], date_str[6:8]
            filters["after"] = f"{year}-{month}-{day}"
            query = query[:after_match.start()] + query[after_match.end():]

        # Extract label:xxx or tag:xxx
        label_match = re.search(r'\b(?:label|tag):(\S+)\b', query)
        if label_match:
            filters["label"] = label_match.group(1)
            query = query[:label_match.start()] + query[label_match.end():]

        # Extract from:xxx or sender:xxx - use LIKE filter instead of FTS for much faster date-sorted queries
        from_match = re.search(r'\b(?:from|sender):(\S+)\b', query)
        if from_match:
            filters["sender"] = from_match.group(1)
            query = query[:from_match.start()] + query[from_match.end():]

        # Extract to:xxx or recipients:xxx - use LIKE filter instead of FTS for much faster date-sorted queries
        to_match = re.search(r'\b(?:to|recipients):(\S+)\b', query)
        if to_match:
            filters["recipients"] = to_match.group(1)
            query = query[:to_match.start()] + query[to_match.end():]

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
        """Clear the full-text search index.

        For contentless FTS5, we drop and recreate the table.
        We also clear the indexed metadata in the emails table.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Drop and recreate FTS table (can't DELETE from contentless FTS)
            conn.execute("DROP TABLE IF EXISTS emails_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE emails_fts USING fts5(
                    subject,
                    sender,
                    recipients,
                    body,
                    attachments,
                    content='',
                    tokenize='porter unicode61'
                )
            """)
            # Clear indexed metadata in emails table
            conn.execute("UPDATE emails SET subject = NULL, sender = NULL, recipients = NULL, date_str = NULL, snippet = NULL, indexed_hash = NULL")
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
