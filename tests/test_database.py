"""Tests for ArchiveDatabase class."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ownmail import ArchiveDatabase


class TestArchiveDatabaseInit:
    """Tests for database initialization."""

    def test_creates_database(self, temp_dir):
        """Test that database is created on initialization."""
        db = ArchiveDatabase(temp_dir)
        assert db.db_path.exists()
        assert db.db_path.name == "ownmail.db"

    def test_creates_tables(self, temp_dir):
        """Test that all required tables are created."""
        db = ArchiveDatabase(temp_dir)

        with sqlite3.connect(db.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]

        assert "emails" in table_names
        assert "sync_state" in table_names
        assert "emails_fts" in table_names

    def test_emails_table_schema(self, temp_dir):
        """Test that emails table has correct columns."""
        db = ArchiveDatabase(temp_dir)

        with sqlite3.connect(db.db_path) as conn:
            info = conn.execute("PRAGMA table_info(emails)").fetchall()
            columns = {row[1] for row in info}

        assert "message_id" in columns
        assert "filename" in columns
        assert "downloaded_at" in columns
        assert "content_hash" in columns
        assert "indexed_hash" in columns


class TestArchiveDatabaseOperations:
    """Tests for database operations."""

    def test_mark_downloaded(self, temp_dir):
        """Test marking an email as downloaded."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg123", "emails/2024/01/test.eml", "abc123hash")

        assert db.is_downloaded("msg123")
        assert not db.is_downloaded("nonexistent")

    def test_get_downloaded_ids(self, temp_dir):
        """Test getting all downloaded message IDs."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "file1.eml")
        db.mark_downloaded("msg2", "file2.eml")
        db.mark_downloaded("msg3", "file3.eml")

        ids = db.get_downloaded_ids()

        assert ids == {"msg1", "msg2", "msg3"}

    def test_history_id(self, temp_dir):
        """Test history ID get/set."""
        db = ArchiveDatabase(temp_dir)

        assert db.get_history_id() is None

        db.set_history_id("12345")
        assert db.get_history_id() == "12345"

        db.set_history_id("67890")
        assert db.get_history_id() == "67890"


class TestFullTextSearch:
    """Tests for FTS5 search functionality."""

    def test_index_email(self, temp_dir):
        """Test indexing an email."""
        db = ArchiveDatabase(temp_dir)
        db.mark_downloaded("msg1", "test.eml")

        db.index_email(
            message_id="msg1",
            subject="Meeting Tomorrow",
            sender="boss@example.com",
            recipients="team@example.com",
            date_str="Mon, 1 Jan 2024 10:00:00",
            body="Please attend the meeting at 3pm.",
            attachments="agenda.pdf",
        )

        assert db.is_indexed("msg1")

    def test_search_by_subject(self, temp_dir):
        """Test searching by subject."""
        db = ArchiveDatabase(temp_dir)
        db.mark_downloaded("msg1", "test.eml")

        db.index_email(
            message_id="msg1",
            subject="Invoice from Amazon",
            sender="orders@amazon.com",
            recipients="me@example.com",
            date_str="Mon, 1 Jan 2024",
            body="Your order has shipped.",
            attachments="",
        )

        results = db.search("invoice", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == "msg1"

    def test_search_by_sender(self, temp_dir):
        """Test searching by sender using from: prefix."""
        db = ArchiveDatabase(temp_dir)
        db.mark_downloaded("msg1", "test.eml")

        db.index_email(
            message_id="msg1",
            subject="Hello",
            sender="john@example.com",
            recipients="me@example.com",
            date_str="Mon, 1 Jan 2024",
            body="How are you?",
            attachments="",
        )

        # The search converts from: to sender:
        results = db.search("from:john", include_unknown=True)
        assert len(results) == 1

    def test_search_no_results(self, temp_dir):
        """Test search with no matches."""
        db = ArchiveDatabase(temp_dir)

        results = db.search("nonexistent query xyz123", include_unknown=True)
        assert results == []

    def test_search_has_attachment(self, temp_dir):
        """Test has:attachment filter finds emails with attachments."""
        db = ArchiveDatabase(temp_dir)

        # Email with attachment
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email(
            message_id="msg1",
            subject="Report",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="See attached",
            attachments="report.pdf",
        )

        # Email without attachment
        db.mark_downloaded("msg2", "test2.eml")
        db.index_email(
            message_id="msg2",
            subject="Hi",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="Just saying hi",
            attachments="",
        )

        results = db.search("has:attachment", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == "msg1"

    def test_search_attachment_type(self, temp_dir):
        """Test attachment:type filter finds emails with specific attachment types."""
        db = ArchiveDatabase(temp_dir)

        # Email with PDF
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email(
            message_id="msg1",
            subject="Report",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="See attached PDF",
            attachments="report.pdf",
        )

        # Email with Excel
        db.mark_downloaded("msg2", "test2.eml")
        db.index_email(
            message_id="msg2",
            subject="Spreadsheet",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="See attached spreadsheet",
            attachments="data.xlsx",
        )

        results = db.search("attachment:pdf", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == "msg1"

        results = db.search("attachment:xlsx", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == "msg2"

    def test_clear_index(self, temp_dir):
        """Test clearing the search index."""
        db = ArchiveDatabase(temp_dir)
        db.mark_downloaded("msg1", "test.eml")

        db.index_email(
            message_id="msg1",
            subject="Test",
            sender="test@test.com",
            recipients="",
            date_str="",
            body="Body",
            attachments="",
        )

        assert db.is_indexed("msg1")

        db.clear_index()

        assert not db.is_indexed("msg1")


class TestDatabaseStats:
    """Tests for database statistics."""

    def test_get_stats_empty(self, temp_dir):
        """Test stats on empty database."""
        db = ArchiveDatabase(temp_dir)
        stats = db.get_stats()

        assert stats["total_emails"] == 0
        assert stats["indexed_emails"] == 0

    def test_get_stats_with_data(self, temp_dir):
        """Test stats with some data."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "f1.eml")
        db.mark_downloaded("msg2", "f2.eml")
        db.index_email("msg1", "Subj", "From", "To", "Date", "Body", "")

        # Also set indexed_hash for msg1 (simulates actual index flow)
        with sqlite3.connect(db.db_path) as conn:
            conn.execute("UPDATE emails SET indexed_hash = 'hash1' WHERE message_id = 'msg1'")

        stats = db.get_stats()

        assert stats["total_emails"] == 2
        assert stats["indexed_emails"] == 1

    def test_get_stats_per_account(self, temp_dir):
        """Test stats filtered by account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded("msg2", "f2.eml", account="alice@gmail.com")
        db.mark_downloaded("msg3", "f3.eml", account="bob@gmail.com")

        stats_alice = db.get_stats(account="alice@gmail.com")
        stats_bob = db.get_stats(account="bob@gmail.com")

        assert stats_alice["total_emails"] == 2
        assert stats_bob["total_emails"] == 1


class TestPerAccountOperations:
    """Tests for per-account database operations."""

    def test_sync_state_per_account(self, temp_dir):
        """Test sync state is stored per account."""
        db = ArchiveDatabase(temp_dir)

        db.set_sync_state("alice@gmail.com", "history_id", "alice_history")
        db.set_sync_state("bob@gmail.com", "history_id", "bob_history")

        assert db.get_sync_state("alice@gmail.com", "history_id") == "alice_history"
        assert db.get_sync_state("bob@gmail.com", "history_id") == "bob_history"

    def test_get_downloaded_ids_per_account(self, temp_dir):
        """Test getting downloaded IDs filtered by account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded("msg2", "f2.eml", account="alice@gmail.com")
        db.mark_downloaded("msg3", "f3.eml", account="bob@gmail.com")

        alice_ids = db.get_downloaded_ids(account="alice@gmail.com")
        bob_ids = db.get_downloaded_ids(account="bob@gmail.com")
        all_ids = db.get_downloaded_ids()

        assert alice_ids == {"msg1", "msg2"}
        assert bob_ids == {"msg3"}
        assert all_ids == {"msg1", "msg2", "msg3"}

    def test_is_downloaded_per_account(self, temp_dir):
        """Test is_downloaded with account filter."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "f1.eml", account="alice@gmail.com")

        assert db.is_downloaded("msg1", account="alice@gmail.com") is True
        assert db.is_downloaded("msg1", account="bob@gmail.com") is False
        assert db.is_downloaded("msg1") is True

    def test_history_id_per_account(self, temp_dir):
        """Test history ID stored per account."""
        db = ArchiveDatabase(temp_dir)

        db.set_history_id("alice_history", account="alice@gmail.com")
        db.set_history_id("bob_history", account="bob@gmail.com")

        assert db.get_history_id(account="alice@gmail.com") == "alice_history"
        assert db.get_history_id(account="bob@gmail.com") == "bob_history"


class TestSearchSorting:
    """Tests for search with different sort options."""

    def test_search_sort_date_desc(self, temp_dir):
        """Test search with date descending sort."""
        db = ArchiveDatabase(temp_dir)

        # email_date determines sort order
        db.mark_downloaded("msg1", "emails/2024/01/20240101_120000_abc.eml", email_date="2024-01-01T12:00:00")
        db.mark_downloaded("msg2", "emails/2024/02/20240201_120000_def.eml", email_date="2024-02-01T12:00:00")
        db.index_email("msg1", "Test", "from", "to", "date", "body", "")
        db.index_email("msg2", "Test", "from", "to", "date", "body", "")

        results = db.search("test", sort="date_desc", include_unknown=True)

        assert len(results) == 2
        # Newest first
        assert results[0][0] == "msg2"
        assert results[1][0] == "msg1"

    def test_search_sort_date_asc(self, temp_dir):
        """Test search with date ascending sort."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "emails/2024/01/20240101_120000_abc.eml", email_date="2024-01-01T12:00:00")
        db.mark_downloaded("msg2", "emails/2024/02/20240201_120000_def.eml", email_date="2024-02-01T12:00:00")
        db.index_email("msg1", "Test", "from", "to", "date", "body", "")
        db.index_email("msg2", "Test", "from", "to", "date", "body", "")

        results = db.search("test", sort="date_asc", include_unknown=True)

        assert len(results) == 2
        # Oldest first
        assert results[0][0] == "msg1"
        assert results[1][0] == "msg2"


class TestSearchDateFilters:
    """Tests for before: and after: date filters."""

    def test_search_after_filter(self, temp_dir):
        """Test search with after: date filter."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "emails/2024/01/20240115_120000_abc.eml", email_date="2024-01-15T12:00:00")
        db.mark_downloaded("msg2", "emails/2024/02/20240215_120000_def.eml", email_date="2024-02-15T12:00:00")
        db.index_email("msg1", "Test", "from", "to", "date", "body", "")
        db.index_email("msg2", "Test", "from", "to", "date", "body", "")

        results = db.search("test after:2024-02-01", include_unknown=True)

        # Only msg2 is after 2024-02-01
        assert len(results) == 1
        assert results[0][0] == "msg2"

    def test_search_before_filter(self, temp_dir):
        """Test search with before: date filter."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "emails/2024/01/20240115_120000_abc.eml", email_date="2024-01-15T12:00:00")
        db.mark_downloaded("msg2", "emails/2024/02/20240215_120000_def.eml", email_date="2024-02-15T12:00:00")
        db.index_email("msg1", "Test", "from", "to", "date", "body", "")
        db.index_email("msg2", "Test", "from", "to", "date", "body", "")

        results = db.search("test before:2024-02-01", include_unknown=True)

        # Only msg1 is before 2024-02-01
        assert len(results) == 1
        assert results[0][0] == "msg1"


class TestSearchLabelFilter:
    """Tests for label: filter using labels column."""

    def test_search_label_only(self, temp_dir):
        """Test search with label: only (no other terms)."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "emails/2024/01/20240115_120000_abc.eml")
        db.mark_downloaded("msg2", "emails/2024/02/20240215_120000_def.eml")
        db.index_email("msg1", "Test1", "from", "to", "date", "body", "", labels="INBOX,IMPORTANT")
        db.index_email("msg2", "Test2", "from", "to", "date", "body", "", labels="INBOX")

        results = db.search("label:IMPORTANT", include_unknown=True)

        assert len(results) == 1
        assert results[0][0] == "msg1"

    def test_search_label_with_text(self, temp_dir):
        """Test search with label: and text query."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "emails/2024/01/20240115_120000_abc.eml")
        db.mark_downloaded("msg2", "emails/2024/02/20240215_120000_def.eml")
        db.index_email("msg1", "Invoice", "from", "to", "date", "body", "", labels="IMPORTANT")
        db.index_email("msg2", "Invoice", "from", "to", "date", "body", "", labels="INBOX")

        results = db.search("invoice label:IMPORTANT", include_unknown=True)

        assert len(results) == 1
        assert results[0][0] == "msg1"


class TestAccountManagement:
    """Tests for account management methods."""

    def test_get_accounts(self, temp_dir):
        """Test getting list of accounts."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded("msg2", "f2.eml", account="bob@gmail.com")
        db.mark_downloaded("msg3", "f3.eml", account="alice@gmail.com")

        accounts = db.get_accounts()

        assert set(accounts) == {"alice@gmail.com", "bob@gmail.com"}

    def test_get_email_count_by_account(self, temp_dir):
        """Test getting email count per account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded("msg2", "f2.eml", account="alice@gmail.com")
        db.mark_downloaded("msg3", "f3.eml", account="bob@gmail.com")
        db.mark_downloaded("msg4", "f4.eml")  # Legacy, no account

        counts = db.get_email_count_by_account()

        assert counts.get("alice@gmail.com") == 2
        assert counts.get("bob@gmail.com") == 1
        assert counts.get("(legacy)") == 1  # Legacy entry


class TestSearchWithAccount:
    """Tests for search with account filtering."""

    def test_search_filters_by_account(self, temp_dir):
        """Test that search can filter by account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded("msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded("msg2", "f2.eml", account="bob@gmail.com")

        db.index_email("msg1", "Invoice Alice", "From", "To", "Date", "Body", "")
        db.index_email("msg2", "Invoice Bob", "From", "To", "Date", "Body", "")

        results_alice = db.search("invoice", account="alice@gmail.com", include_unknown=True)
        results_bob = db.search("invoice", account="bob@gmail.com", include_unknown=True)
        results_all = db.search("invoice", include_unknown=True)

        assert len(results_alice) == 1
        assert results_alice[0][0] == "msg1"
        assert len(results_bob) == 1
        assert results_bob[0][0] == "msg2"
        assert len(results_all) == 2
