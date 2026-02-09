"""SQLite database for tracking emails and full-text search."""

import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ownmail.query import parse_query


class ArchiveDatabase:
    """SQLite database for tracking emails and full-text search.

    Schema:
    - emails: Track downloaded emails with email_id, provider_id, filename, hash, account
    - sync_state: Key-value store for per-account sync state
    - emails_fts: FTS5 virtual table for full-text search
    """

    def __init__(self, archive_dir: Path, db_dir: Path = None):
        """Initialize the archive database.

        Args:
            archive_dir: Directory containing the email archive
            db_dir: Optional separate directory for the database.
                    If not provided, the database is stored in archive_dir.
        """
        self.archive_dir = archive_dir
        effective_db_dir = db_dir or archive_dir
        self.db_path = effective_db_dir / "ownmail.db"
        archive_dir.mkdir(parents=True, exist_ok=True)
        if db_dir:
            db_dir.mkdir(parents=True, exist_ok=True)

        is_new_db = not self.db_path.exists()
        if is_new_db:
            print(f"Creating new database: {self.db_path}")

        self._init_db()

    @staticmethod
    def make_email_id(account: str, provider_id: str) -> str:
        """Generate a stable email_id from account and provider_id.

        Uses 24 hex chars (96 bits) of SHA-256, giving collision resistance
        up to ~79 billion emails (birthday bound at 2^48).

        Args:
            account: Email address (e.g., "user@gmail.com")
            provider_id: Provider-specific message ID (e.g., Gmail API hex ID)

        Returns:
            24-character hex string
        """
        return hashlib.sha256(f"{account}/{provider_id}".encode()).hexdigest()[:24]

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Migrate from old message_id schema if needed
            self._migrate_message_id_to_email_id(conn)

            # Main emails table - stores all metadata for fast indexed queries
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    email_id TEXT PRIMARY KEY,
                    provider_id TEXT,
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

            # Add has_attachments flag for fast attachment filtering
            # (FTS is contentless so we can't query attachment column directly)
            try:
                conn.execute("ALTER TABLE emails ADD COLUMN has_attachments INTEGER DEFAULT 0")
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

            # Normalized recipients table for fast recipient lookups
            # LIKE '%,email,%' on recipient_emails column requires full table scan
            # This table allows indexed exact-match lookups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_recipients (
                    email_rowid INTEGER,
                    recipient_email TEXT,
                    PRIMARY KEY (email_rowid, recipient_email)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email_recipients_email ON email_recipients(recipient_email)")

            # Normalized labels table for fast label lookups
            # LIKE '%INBOX%' on labels column requires full table scan
            # This table allows indexed exact-match lookups
            # Includes email_date for sorting without touching emails table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_labels (
                    email_rowid INTEGER,
                    label TEXT,
                    email_date TEXT,
                    PRIMARY KEY (email_rowid, label)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email_labels_label ON email_labels(label)")
            # Covering index for (label, email_date DESC) to speed up sorted label queries
            # This allows ORDER BY email_date DESC without touching emails table
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_email_labels_label_date
                ON email_labels(label, email_date DESC, email_rowid)
            """)

            # Indexes for fast queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_account ON emails(account)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_indexed_hash ON emails(indexed_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_filename ON emails(filename)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(email_date)")
            # Composite index for from:user@example.com sorted by date (very common query)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_sender_date ON emails(sender_email, email_date DESC)")
            # Composite index for has:attachment sorted by date
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_attachments_date ON emails(has_attachments, email_date DESC)")
            # Unique index for fast provider_id lookups and duplicate prevention
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_emails_provider ON emails(account, provider_id)")

            # Drop legacy single-column indexes replaced by composites or normalized tables
            conn.execute("DROP INDEX IF EXISTS idx_emails_labels")  # replaced by email_labels table
            conn.execute("DROP INDEX IF EXISTS idx_emails_recipient_emails")  # replaced by email_recipients table
            conn.execute("DROP INDEX IF EXISTS idx_emails_sender_email")  # replaced by idx_emails_sender_date

            # Cascade delete triggers - clean up junction tables when emails are deleted
            # Note: FTS cleanup is NOT handled here because contentless FTS5 requires
            # the exact original content (including body) for delete operations.
            # After deleting emails, run `reindex --force` to rebuild the FTS index.
            conn.execute("""CREATE TRIGGER IF NOT EXISTS trg_emails_delete
                AFTER DELETE ON emails
                BEGIN
                    DELETE FROM email_recipients WHERE email_rowid = OLD.rowid;
                    DELETE FROM email_labels WHERE email_rowid = OLD.rowid;
                END
            """)

            conn.commit()

    def _migrate_message_id_to_email_id(self, conn: sqlite3.Connection) -> None:
        """Migrate from old message_id PK schema to email_id PK schema.

        Preserves rowids so that FTS5 and junction tables remain valid.
        """
        # Check if migration is needed
        cols = {row[1] for row in conn.execute("PRAGMA table_info(emails)")}
        if not cols:
            return  # Table doesn't exist yet (fresh install)
        if 'provider_id' in cols:
            return  # Already migrated
        if 'message_id' not in cols:
            return  # Unexpected schema

        print("Migrating database schema (message_id → email_id)...", end="", flush=True)

        # Read all existing data with rowids
        rows = conn.execute(
            """SELECT rowid, message_id, filename, downloaded_at, content_hash,
               indexed_hash, account, labels, email_date, subject, sender,
               recipients, date_str, snippet,
               sender_email, recipient_emails,
               COALESCE(has_attachments, 0)
               FROM emails"""
        ).fetchall()

        # Compute email_id for each row
        migrated = []
        for row in rows:
            rowid, message_id = row[0], row[1]
            account = row[6] or ""
            email_id = self.make_email_id(account, message_id)
            # (rowid, email_id, provider_id=message_id, filename, ...)
            migrated.append((rowid, email_id, message_id) + row[2:])

        # Drop trigger before dropping table
        conn.execute("DROP TRIGGER IF EXISTS trg_emails_delete")
        conn.execute("DROP TABLE emails")

        # Create new table with email_id PK
        conn.execute("""
            CREATE TABLE emails (
                email_id TEXT PRIMARY KEY,
                provider_id TEXT,
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
                snippet TEXT,
                sender_email TEXT,
                recipient_emails TEXT,
                has_attachments INTEGER DEFAULT 0
            )
        """)

        # Insert with preserved rowids (keeps FTS5 and junction tables valid)
        if migrated:
            conn.executemany(
                """INSERT INTO emails
                   (rowid, email_id, provider_id, filename, downloaded_at,
                    content_hash, indexed_hash, account, labels, email_date,
                    subject, sender, recipients, date_str, snippet,
                    sender_email, recipient_emails, has_attachments)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                migrated
            )

        conn.commit()
        print(f" migrated {len(migrated)} rows", flush=True)

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

    def delete_account_sync_state(self, account: str) -> None:
        """Delete all sync state for an account.

        This forces a full re-sync on the next backup.

        Args:
            account: Email address
        """
        prefix = f"{account}/"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sync_state WHERE key LIKE ?", (prefix + "%",))
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

    def is_downloaded(self, provider_id: str, account: str = None) -> bool:
        """Check if a message has already been downloaded.

        Args:
            provider_id: Provider-specific message ID (e.g., Gmail API hex ID)
            account: Email address for scoped lookup
        """
        with sqlite3.connect(self.db_path) as conn:
            if account:
                result = conn.execute(
                    "SELECT 1 FROM emails WHERE provider_id = ? AND account = ?",
                    (provider_id, account)
                ).fetchone()
            else:
                result = conn.execute(
                    "SELECT 1 FROM emails WHERE provider_id = ?",
                    (provider_id,)
                ).fetchone()
            return result is not None

    def get_downloaded_ids(self, account: str = None) -> set:
        """Get all downloaded provider IDs.

        Returns:
            Set of provider_id values (for comparison with provider's ID list)
        """
        with sqlite3.connect(self.db_path) as conn:
            if account:
                results = conn.execute(
                    "SELECT provider_id FROM emails WHERE account = ?",
                    (account,)
                ).fetchall()
            else:
                results = conn.execute(
                    "SELECT provider_id FROM emails"
                ).fetchall()
            return {row[0] for row in results}

    def get_email_by_id(self, email_id: str) -> Optional[tuple]:
        """Get email info by email_id.

        Args:
            email_id: 24-char hex hash

        Returns:
            Tuple of (email_id, filename, downloaded_at, content_hash, account)
            or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT email_id, filename, downloaded_at, content_hash, account FROM emails WHERE email_id = ?",
                (email_id,)
            ).fetchone()
            return result

    def mark_downloaded(
        self,
        email_id: str,
        provider_id: str,
        filename: str,
        content_hash: str = None,
        account: str = None,
        conn: sqlite3.Connection = None,
        email_date: str = None,
    ) -> None:
        """Mark a message as downloaded.

        Args:
            email_id: 24-char hex hash (PK)
            provider_id: Provider-specific message ID
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
                (email_id, provider_id, filename, downloaded_at, content_hash, account, email_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (email_id, provider_id, filename, datetime.now().isoformat(), content_hash, account, email_date)
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
        email_id: str,
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
            email_id: 24-char hex hash
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
                "SELECT rowid, subject, email_date FROM emails WHERE email_id = ?",
                (email_id,)
            ).fetchone()
            if not row:
                # Message not in database yet - can't index
                if should_close:
                    conn.close()
                return

            rowid = row[0]
            was_indexed = row[1] is not None  # Had subject before
            email_date = row[2]  # For email_labels table

            # Extract email addresses for indexed lookups
            sender_email = self._extract_email(sender)
            recipient_emails = self._normalize_recipients(recipients)

            # Check if email has attachments (non-empty attachments string)
            has_attachments = 1 if attachments and attachments.strip() else 0

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
                    recipient_emails = ?,
                    has_attachments = ?
                WHERE email_id = ?
                """,
                (subject, sender, recipients, date_str, labels, snippet, sender_email, recipient_emails, has_attachments, email_id)
            )

            # Update normalized recipients table for fast lookups
            # First delete any existing entries for this email
            conn.execute("DELETE FROM email_recipients WHERE email_rowid = ?", (rowid,))
            # Then insert individual recipient emails
            if recipient_emails:
                # recipient_emails is in format ",a@b.com,c@d.com,"
                for email in recipient_emails.strip(',').split(','):
                    email = email.strip()
                    if email:
                        conn.execute(
                            "INSERT OR IGNORE INTO email_recipients (email_rowid, recipient_email) VALUES (?, ?)",
                            (rowid, email)
                        )

            # Update normalized labels table for fast lookups
            conn.execute("DELETE FROM email_labels WHERE email_rowid = ?", (rowid,))
            if labels:
                # labels is comma-separated: "INBOX,IMPORTANT,CATEGORY_PERSONAL"
                for label in labels.split(','):
                    label = label.strip()
                    if label:
                        conn.execute(
                            "INSERT OR IGNORE INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                            (rowid, label, email_date)
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

    def is_indexed(self, email_id: str) -> bool:
        """Check if a message is in the search index (has metadata populated)."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM emails WHERE email_id = ? AND subject IS NOT NULL",
                (email_id,)
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
        import time
        _t0 = time.time()
        with sqlite3.connect(self.db_path) as conn:
            _t1 = time.time()
            # Parse query using the new query parser
            parsed = parse_query(query)
            print(f"[db.search] connect: {_t1-_t0:.3f}s, parse_query: {time.time()-_t1:.3f}s", flush=True)
            print(f"[db.search] fts_query={repr(parsed.fts_query)}, where={parsed.where_clauses}, error={parsed.error}", flush=True)

            # If there's a parse error, return empty results
            # The caller (web.py or cli) should display parsed.error to the user
            if parsed.has_error():
                print(f"[db.search] Parse error: {parsed.error}", flush=True)
                return []

            # Build WHERE clause for emails table
            where_clauses = []
            params = []

            # Exclude emails without parsed dates unless explicitly requested
            if not include_unknown:
                where_clauses.append("e.email_date IS NOT NULL")

            if account:
                where_clauses.append("e.account = ?")
                params.append(account)

            # Add WHERE clauses from parsed query
            # Handle special markers that need custom handling
            recipient_email_filter = None
            not_recipient_email_filter = None
            label_filter = None
            not_label_filter = None
            param_idx = 0

            for clause in parsed.where_clauses:
                if clause == "__RECIPIENT_EMAIL__":
                    # This is a recipient email filter - needs JOIN
                    recipient_email_filter = parsed.params[param_idx]
                    param_idx += 1
                elif clause == "__NOT_RECIPIENT_EMAIL__":
                    # This is a negated recipient email filter - needs NOT EXISTS
                    not_recipient_email_filter = parsed.params[param_idx]
                    param_idx += 1
                elif clause == "__LABEL__":
                    # This is a label filter - needs JOIN with email_labels
                    label_filter = parsed.params[param_idx]
                    param_idx += 1
                elif clause == "__NOT_LABEL__":
                    # This is a negated label filter - needs NOT EXISTS
                    not_label_filter = parsed.params[param_idx]
                    param_idx += 1
                else:
                    where_clauses.append(clause)
                    # Only consume a param if the clause uses one (has ?)
                    if '?' in clause:
                        params.append(parsed.params[param_idx])
                        param_idx += 1

            # Add negated recipient email filter as a WHERE clause
            if not_recipient_email_filter:
                where_clauses.append("""
                    NOT EXISTS (
                        SELECT 1 FROM email_recipients er2
                        WHERE er2.email_rowid = e.rowid
                          AND er2.recipient_email = ?
                    )
                """)
                params.append(not_recipient_email_filter)

            # Add negated label filter as a WHERE clause
            if not_label_filter:
                where_clauses.append("""
                    NOT EXISTS (
                        SELECT 1 FROM email_labels el2
                        WHERE el2.email_rowid = e.rowid
                          AND el2.label = ? COLLATE NOCASE
                    )
                """)
                params.append(not_label_filter)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Get FTS query
            fts_query = parsed.fts_query

            # Determine sort order
            if sort == "date_desc":
                order_by = "e.email_date DESC"
            elif sort == "date_asc":
                order_by = "e.email_date ASC"
            else:
                order_by = "e.email_date DESC"  # Default for non-FTS queries

            # If there's a text search query, use FTS
            if fts_query.strip():
                print("[db.search] Using FTS path", flush=True)
                if sort == "relevance":
                    order_by = "rank"

                # Build additional JOINs for label/recipient filters
                extra_joins = []
                extra_where = []
                extra_params = []

                if label_filter:
                    extra_joins.append("JOIN email_labels el ON el.email_rowid = e.rowid")
                    extra_where.append("el.label = ? COLLATE NOCASE")
                    extra_params.append(label_filter)
                    # Use el.email_date for sorting to leverage covering index
                    if order_by == "e.email_date DESC":
                        order_by = "el.email_date DESC"
                    elif order_by == "e.email_date ASC":
                        order_by = "el.email_date ASC"

                if recipient_email_filter:
                    extra_joins.append("JOIN email_recipients er ON er.email_rowid = e.rowid")
                    extra_where.append("er.recipient_email = ?")
                    extra_params.append(recipient_email_filter)

                join_sql = " ".join(extra_joins)
                if extra_where:
                    where_sql = " AND ".join([where_sql] + extra_where) if where_sql != "1=1" else " AND ".join(extra_where)

                # Determine if we need DISTINCT
                # Single-join cases never produce duplicates due to PKs on junction tables
                # Multi-join (label + recipient) also safe: each email has at most one
                # matching row per filter
                distinct = ""

                # JOIN with FTS using rowid
                fts_params = [fts_query] + extra_params + params + [limit, offset]
                _t2 = time.time()
                try:
                    results = conn.execute(
                        f"""
                        SELECT {distinct}
                            e.email_id,
                            e.filename,
                            e.subject,
                            e.sender,
                            e.date_str,
                            e.snippet
                        FROM emails e
                        JOIN emails_fts f ON f.rowid = e.rowid
                        {join_sql}
                        WHERE f.emails_fts MATCH ?
                          AND {where_sql}
                        ORDER BY {order_by}
                        LIMIT ? OFFSET ?
                        """,
                        fts_params
                    ).fetchall()
                except sqlite3.OperationalError as e:
                    error_str = str(e).lower()
                    if "fts5" in error_str or "match" in error_str or "syntax" in error_str:
                        print(f"[db.search] FTS5 error: {e}", flush=True)
                        # Return empty results - caller should check for FTS errors
                        return []
                    raise
                print(f"[db.search] FTS query took {time.time()-_t2:.3f}s, {len(results)} results", flush=True)
            else:
                print("[db.search] Using table-only path", flush=True)
                # No text search - query emails table only (fast with indexes)
                _t2 = time.time()

                # Build query - use JOIN if filtering by recipient email or label
                joins = []
                filter_params = []

                if recipient_email_filter:
                    joins.append("JOIN email_recipients er ON er.email_rowid = e.rowid")
                    where_clauses.insert(0, "er.recipient_email = ?")
                    filter_params.append(recipient_email_filter)

                if label_filter:
                    joins.append("JOIN email_labels el ON el.email_rowid = e.rowid")
                    where_clauses.insert(0, "el.label = ? COLLATE NOCASE")
                    filter_params.append(label_filter)
                    # Use el.email_date for sorting to leverage covering index
                    if "email_date DESC" in order_by:
                        order_by = "el.email_date DESC"
                    elif "email_date ASC" in order_by:
                        order_by = "el.email_date ASC"

                join_sql = " ".join(joins)
                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

                # Determine if we need DISTINCT
                # Single-join cases never produce duplicates due to PKs on junction tables
                # Multi-join (label + recipient) also safe: each email has at most one
                # matching row per filter
                distinct = ""

                sql = f"""
                    SELECT {distinct}
                        e.email_id,
                        e.filename,
                        e.subject,
                        e.sender,
                        e.date_str,
                        e.snippet
                    FROM emails e
                    {join_sql}
                    WHERE {where_sql}
                    ORDER BY {order_by}
                    LIMIT ? OFFSET ?
                    """
                query_params = filter_params + params + [limit, offset]

                print(f"[db.search] SQL: {sql}", flush=True)
                print(f"[db.search] params: {query_params}", flush=True)
                results = conn.execute(sql, query_params).fetchall()
                print(f"[db.search] Table query took {time.time()-_t2:.3f}s, {len(results)} results", flush=True)

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
