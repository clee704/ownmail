"""Tests for ArchiveDatabase class."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ownmail import ArchiveDatabase


def _eid(provider_id, account=""):
    """Compute email_id from provider_id for tests."""
    return ArchiveDatabase.make_email_id(account, provider_id)


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
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
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

        assert "email_id" in columns
        assert "provider_id" in columns
        assert "filename" in columns
        assert "downloaded_at" in columns
        assert "content_hash" in columns
        assert "indexed_hash" in columns


class TestArchiveDatabaseOperations:
    """Tests for database operations."""

    def test_mark_downloaded(self, temp_dir):
        """Test marking an email as downloaded."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg123"), "msg123", "emails/2024/01/test.eml", "abc123hash")

        assert db.is_downloaded("msg123")
        assert not db.is_downloaded("nonexistent")

    def test_get_downloaded_ids(self, temp_dir):
        """Test getting all downloaded message IDs."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1"), "msg1", "file1.eml")
        db.mark_downloaded(_eid("msg2"), "msg2", "file2.eml")
        db.mark_downloaded(_eid("msg3"), "msg3", "file3.eml")

        ids = db.get_downloaded_ids()

        assert ids == {"msg1", "msg2", "msg3"}

    def test_get_tracked_filenames(self, temp_dir):
        """Test getting all tracked filenames."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1"), "msg1", "file1.eml", account="alice@example.com")
        db.mark_downloaded(_eid("msg2"), "msg2", "file2.eml", account="bob@example.com")

        assert db.get_tracked_filenames() == {"file1.eml", "file2.eml"}
        assert db.get_tracked_filenames(account="alice@example.com") == {"file1.eml"}
        assert db.get_tracked_filenames(account="nobody@example.com") == set()

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
        db.mark_downloaded(_eid("msg1"), "msg1", "test.eml")

        db.index_email(
            email_id=_eid("msg1"),
            subject="Meeting Tomorrow",
            sender="boss@example.com",
            recipients="team@example.com",
            date_str="Mon, 1 Jan 2024 10:00:00",
            body="Please attend the meeting at 3pm.",
            attachments="agenda.pdf",
        )

        assert db.is_indexed(_eid("msg1"))

    def test_search_by_subject(self, temp_dir):
        """Test searching by subject."""
        db = ArchiveDatabase(temp_dir)
        db.mark_downloaded(_eid("msg1"), "msg1", "test.eml")

        db.index_email(
            email_id=_eid("msg1"),
            subject="Invoice from Amazon",
            sender="orders@amazon.com",
            recipients="me@example.com",
            date_str="Mon, 1 Jan 2024",
            body="Your order has shipped.",
            attachments="",
        )

        results = db.search("invoice", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == _eid("msg1")

    def test_search_by_sender(self, temp_dir):
        """Test searching by sender using from: prefix."""
        db = ArchiveDatabase(temp_dir)
        db.mark_downloaded(_eid("msg1"), "msg1", "test.eml")

        db.index_email(
            email_id=_eid("msg1"),
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
        db.mark_downloaded(_eid("msg1"), "msg1", "test1.eml")
        db.index_email(
            email_id=_eid("msg1"),
            subject="Report",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="See attached",
            attachments="report.pdf",
        )

        # Email without attachment
        db.mark_downloaded(_eid("msg2"), "msg2", "test2.eml")
        db.index_email(
            email_id=_eid("msg2"),
            subject="Hi",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="Just saying hi",
            attachments="",
        )

        results = db.search("has:attachment", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == _eid("msg1")

    def test_search_attachment_type(self, temp_dir):
        """Test attachment:type filter finds emails with specific attachment types."""
        db = ArchiveDatabase(temp_dir)

        # Email with PDF
        db.mark_downloaded(_eid("msg1"), "msg1", "test1.eml")
        db.index_email(
            email_id=_eid("msg1"),
            subject="Report",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="See attached PDF",
            attachments="report.pdf",
        )

        # Email with Excel
        db.mark_downloaded(_eid("msg2"), "msg2", "test2.eml")
        db.index_email(
            email_id=_eid("msg2"),
            subject="Spreadsheet",
            sender="alice@example.com",
            recipients="bob@example.com",
            date_str="Mon, 1 Jan 2024",
            body="See attached spreadsheet",
            attachments="data.xlsx",
        )

        results = db.search("attachment:pdf", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == _eid("msg1")

        results = db.search("attachment:xlsx", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == _eid("msg2")

    def test_clear_index(self, temp_dir):
        """Test clearing the search index."""
        db = ArchiveDatabase(temp_dir)
        db.mark_downloaded(_eid("msg1"), "msg1", "test.eml")

        db.index_email(
            email_id=_eid("msg1"),
            subject="Test",
            sender="test@test.com",
            recipients="",
            date_str="",
            body="Body",
            attachments="",
        )

        assert db.is_indexed(_eid("msg1"))

        db.clear_index()

        assert not db.is_indexed(_eid("msg1"))


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

        db.mark_downloaded(_eid("msg1"), "msg1", "f1.eml")
        db.mark_downloaded(_eid("msg2"), "msg2", "f2.eml")
        db.index_email(_eid("msg1"), "Subj", "From", "To", "Date", "Body", "")

        # Also set indexed_hash for msg1 (simulates actual index flow)
        with sqlite3.connect(db.db_path) as conn:
            conn.execute(f"UPDATE emails SET indexed_hash = 'hash1' WHERE email_id = '{_eid('msg1')}'")

        stats = db.get_stats()

        assert stats["total_emails"] == 2
        assert stats["indexed_emails"] == 1

    def test_get_stats_per_account(self, temp_dir):
        """Test stats filtered by account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1", "alice@gmail.com"), "msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg2", "alice@gmail.com"), "msg2", "f2.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg3", "bob@gmail.com"), "msg3", "f3.eml", account="bob@gmail.com")

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

    def test_delete_account_sync_state(self, temp_dir):
        """Test deleting all sync state for an account."""
        db = ArchiveDatabase(temp_dir)

        # Set multiple keys for two accounts
        db.set_sync_state("alice@gmail.com", "history_id", "alice_history")
        db.set_sync_state("alice@gmail.com", "sync_state", "alice_sync")
        db.set_sync_state("bob@gmail.com", "history_id", "bob_history")

        # Delete all sync state for alice
        db.delete_account_sync_state("alice@gmail.com")

        # Alice's state should be gone
        assert db.get_sync_state("alice@gmail.com", "history_id") is None
        assert db.get_sync_state("alice@gmail.com", "sync_state") is None
        # Bob's state should be untouched
        assert db.get_sync_state("bob@gmail.com", "history_id") == "bob_history"

    def test_get_downloaded_ids_per_account(self, temp_dir):
        """Test getting downloaded IDs filtered by account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1", "alice@gmail.com"), "msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg2", "alice@gmail.com"), "msg2", "f2.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg3", "bob@gmail.com"), "msg3", "f3.eml", account="bob@gmail.com")

        alice_ids = db.get_downloaded_ids(account="alice@gmail.com")
        bob_ids = db.get_downloaded_ids(account="bob@gmail.com")
        all_ids = db.get_downloaded_ids()

        assert alice_ids == {"msg1", "msg2"}
        assert bob_ids == {"msg3"}
        assert all_ids == {"msg1", "msg2", "msg3"}

    def test_is_downloaded_per_account(self, temp_dir):
        """Test is_downloaded with account filter."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1", "alice@gmail.com"), "msg1", "f1.eml", account="alice@gmail.com")

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
        db.mark_downloaded(
            _eid("msg1"), "msg1", "emails/2024/01/20240101_120000_abc.eml", email_date="2024-01-01T12:00:00"
        )
        db.mark_downloaded(
            _eid("msg2"), "msg2", "emails/2024/02/20240201_120000_def.eml", email_date="2024-02-01T12:00:00"
        )
        db.index_email(_eid("msg1"), "Test", "from", "to", "date", "body", "")
        db.index_email(_eid("msg2"), "Test", "from", "to", "date", "body", "")

        results = db.search("test", sort="date_desc", include_unknown=True)

        assert len(results) == 2
        # Newest first
        assert results[0][0] == _eid("msg2")
        assert results[1][0] == _eid("msg1")

    def test_search_sort_date_asc(self, temp_dir):
        """Test search with date ascending sort."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(
            _eid("msg1"), "msg1", "emails/2024/01/20240101_120000_abc.eml", email_date="2024-01-01T12:00:00"
        )
        db.mark_downloaded(
            _eid("msg2"), "msg2", "emails/2024/02/20240201_120000_def.eml", email_date="2024-02-01T12:00:00"
        )
        db.index_email(_eid("msg1"), "Test", "from", "to", "date", "body", "")
        db.index_email(_eid("msg2"), "Test", "from", "to", "date", "body", "")

        results = db.search("test", sort="date_asc", include_unknown=True)

        assert len(results) == 2
        # Oldest first
        assert results[0][0] == _eid("msg1")
        assert results[1][0] == _eid("msg2")


class TestSearchDateFilters:
    """Tests for before: and after: date filters."""

    def test_search_after_filter(self, temp_dir):
        """Test search with after: date filter."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(
            _eid("msg1"), "msg1", "emails/2024/01/20240115_120000_abc.eml", email_date="2024-01-15T12:00:00"
        )
        db.mark_downloaded(
            _eid("msg2"), "msg2", "emails/2024/02/20240215_120000_def.eml", email_date="2024-02-15T12:00:00"
        )
        db.index_email(_eid("msg1"), "Test", "from", "to", "date", "body", "")
        db.index_email(_eid("msg2"), "Test", "from", "to", "date", "body", "")

        results = db.search("test after:2024-02-01", include_unknown=True)

        # Only msg2 is after 2024-02-01
        assert len(results) == 1
        assert results[0][0] == _eid("msg2")

    def test_search_before_filter(self, temp_dir):
        """Test search with before: date filter."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(
            _eid("msg1"), "msg1", "emails/2024/01/20240115_120000_abc.eml", email_date="2024-01-15T12:00:00"
        )
        db.mark_downloaded(
            _eid("msg2"), "msg2", "emails/2024/02/20240215_120000_def.eml", email_date="2024-02-15T12:00:00"
        )
        db.index_email(_eid("msg1"), "Test", "from", "to", "date", "body", "")
        db.index_email(_eid("msg2"), "Test", "from", "to", "date", "body", "")

        results = db.search("test before:2024-02-01", include_unknown=True)

        # Only msg1 is before 2024-02-01
        assert len(results) == 1
        assert results[0][0] == _eid("msg1")


class TestSearchLabelFilter:
    """Tests for label: filter using labels column."""

    def test_search_label_only(self, temp_dir):
        """Test search with label: only (no other terms)."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1"), "msg1", "emails/2024/01/20240115_120000_abc.eml")
        db.mark_downloaded(_eid("msg2"), "msg2", "emails/2024/02/20240215_120000_def.eml")
        db.index_email(_eid("msg1"), "Test1", "from", "to", "date", "body", "", labels="INBOX,IMPORTANT")
        db.index_email(_eid("msg2"), "Test2", "from", "to", "date", "body", "", labels="INBOX")

        results = db.search("label:IMPORTANT", include_unknown=True)

        assert len(results) == 1
        assert results[0][0] == _eid("msg1")

    def test_search_label_with_text(self, temp_dir):
        """Test search with label: and text query."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1"), "msg1", "emails/2024/01/20240115_120000_abc.eml")
        db.mark_downloaded(_eid("msg2"), "msg2", "emails/2024/02/20240215_120000_def.eml")
        db.index_email(_eid("msg1"), "Invoice", "from", "to", "date", "body", "", labels="IMPORTANT")
        db.index_email(_eid("msg2"), "Invoice", "from", "to", "date", "body", "", labels="INBOX")

        results = db.search("invoice label:IMPORTANT", include_unknown=True)

        assert len(results) == 1
        assert results[0][0] == _eid("msg1")


class TestAccountManagement:
    """Tests for account management methods."""

    def test_get_accounts(self, temp_dir):
        """Test getting list of accounts."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1", "alice@gmail.com"), "msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg2", "bob@gmail.com"), "msg2", "f2.eml", account="bob@gmail.com")
        db.mark_downloaded(_eid("msg3", "alice@gmail.com"), "msg3", "f3.eml", account="alice@gmail.com")

        accounts = db.get_accounts()

        assert set(accounts) == {"alice@gmail.com", "bob@gmail.com"}

    def test_get_email_count_by_account(self, temp_dir):
        """Test getting email count per account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1", "alice@gmail.com"), "msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg2", "alice@gmail.com"), "msg2", "f2.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg3", "bob@gmail.com"), "msg3", "f3.eml", account="bob@gmail.com")
        db.mark_downloaded(_eid("msg4"), "msg4", "f4.eml")  # Legacy, no account

        counts = db.get_email_count_by_account()

        assert counts.get("alice@gmail.com") == 2
        assert counts.get("bob@gmail.com") == 1
        assert counts.get("(legacy)") == 1  # Legacy entry


class TestSearchWithAccount:
    """Tests for search with account filtering."""

    def test_search_filters_by_account(self, temp_dir):
        """Test that search can filter by account."""
        db = ArchiveDatabase(temp_dir)

        db.mark_downloaded(_eid("msg1", "alice@gmail.com"), "msg1", "f1.eml", account="alice@gmail.com")
        db.mark_downloaded(_eid("msg2", "bob@gmail.com"), "msg2", "f2.eml", account="bob@gmail.com")

        db.index_email(_eid("msg1", "alice@gmail.com"), "Invoice Alice", "From", "To", "Date", "Body", "")
        db.index_email(_eid("msg2", "bob@gmail.com"), "Invoice Bob", "From", "To", "Date", "Body", "")

        results_alice = db.search("invoice", account="alice@gmail.com", include_unknown=True)
        results_bob = db.search("invoice", account="bob@gmail.com", include_unknown=True)
        results_all = db.search("invoice", include_unknown=True)

        assert len(results_alice) == 1
        assert results_alice[0][0] == _eid("msg1", "alice@gmail.com")
        assert len(results_bob) == 1
        assert results_bob[0][0] == _eid("msg2", "bob@gmail.com")
        assert len(results_all) == 2


class TestTrashOperations:
    """Tests for trash/restore/delete operations."""

    def test_trash_email(self, temp_dir):
        """Test trashing an email updates DB correctly."""
        db = ArchiveDatabase(temp_dir)
        eid = _eid("msg1")
        db.mark_downloaded(eid, "msg1", "sources/gmail/2024/01/test.eml")

        original = db.trash_email(eid, "trash/test.eml")
        assert original == "sources/gmail/2024/01/test.eml"

        info = db.get_email_by_id(eid)
        assert info[1] == "trash/test.eml"  # filename updated
        assert info[5] is not None  # trashed_at set

    def test_trash_email_not_found(self, temp_dir):
        """Test trashing a non-existent email returns None."""
        db = ArchiveDatabase(temp_dir)
        assert db.trash_email("nonexistent", "trash/x.eml") is None

    def test_trash_already_trashed(self, temp_dir):
        """Test trashing an already-trashed email returns None."""
        db = ArchiveDatabase(temp_dir)
        eid = _eid("msg1")
        db.mark_downloaded(eid, "msg1", "sources/gmail/2024/01/test.eml")
        db.trash_email(eid, "trash/test.eml")
        assert db.trash_email(eid, "trash/test2.eml") is None

    def test_restore_email(self, temp_dir):
        """Test restoring an email from trash."""
        db = ArchiveDatabase(temp_dir)
        eid = _eid("msg1")
        db.mark_downloaded(eid, "msg1", "sources/gmail/2024/01/test.eml")
        db.trash_email(eid, "trash/test.eml")

        result = db.restore_email(eid)
        assert result == ("trash/test.eml", "sources/gmail/2024/01/test.eml")

        info = db.get_email_by_id(eid)
        assert info[1] == "sources/gmail/2024/01/test.eml"
        assert info[5] is None  # trashed_at cleared

    def test_restore_not_trashed(self, temp_dir):
        """Test restoring a non-trashed email returns None."""
        db = ArchiveDatabase(temp_dir)
        eid = _eid("msg1")
        db.mark_downloaded(eid, "msg1", "test.eml")
        assert db.restore_email(eid) is None

    def test_permanently_delete(self, temp_dir):
        """Test permanently deleting emails."""
        db = ArchiveDatabase(temp_dir)
        eid1 = _eid("msg1")
        eid2 = _eid("msg2")
        db.mark_downloaded(eid1, "msg1", "f1.eml")
        db.mark_downloaded(eid2, "msg2", "f2.eml")

        count = db.permanently_delete_emails([eid1, eid2])
        assert count == 2
        assert db.get_email_by_id(eid1) is None
        assert db.get_email_by_id(eid2) is None

    def test_permanently_delete_empty(self, temp_dir):
        """Test permanently deleting empty list."""
        db = ArchiveDatabase(temp_dir)
        assert db.permanently_delete_emails([]) == 0

    def test_get_trashed_emails(self, temp_dir):
        """Test listing trashed emails."""
        db = ArchiveDatabase(temp_dir)
        eid = _eid("msg1")
        db.mark_downloaded(eid, "msg1", "test.eml")
        db.trash_email(eid, "trash/test.eml")

        rows = db.get_trashed_emails()
        assert len(rows) == 1
        assert rows[0][0] == eid

    def test_get_trash_count(self, temp_dir):
        """Test counting trashed emails."""
        db = ArchiveDatabase(temp_dir)
        assert db.get_trash_count() == 0

        eid = _eid("msg1")
        db.mark_downloaded(eid, "msg1", "test.eml")
        db.trash_email(eid, "trash/test.eml")
        assert db.get_trash_count() == 1

    def test_search_excludes_trashed(self, temp_dir):
        """Test that search excludes trashed emails."""
        db = ArchiveDatabase(temp_dir)
        eid1 = _eid("msg1")
        eid2 = _eid("msg2")
        db.mark_downloaded(eid1, "msg1", "f1.eml")
        db.mark_downloaded(eid2, "msg2", "f2.eml")
        db.index_email(eid1, "Hello World", "sender", "rcpt", "2024-01-01", "body", "")
        db.index_email(eid2, "Hello Again", "sender", "rcpt", "2024-01-02", "body", "")

        # Both should appear before trash
        results = db.search("Hello", include_unknown=True)
        assert len(results) == 2

        # Trash one
        db.trash_email(eid1, "trash/f1.eml")

        # Only one should appear
        results = db.search("Hello", include_unknown=True)
        assert len(results) == 1
        assert results[0][0] == eid2

    def test_get_stats_excludes_trashed(self, temp_dir):
        """Test that stats exclude trashed emails."""
        db = ArchiveDatabase(temp_dir)
        eid1 = _eid("msg1")
        eid2 = _eid("msg2")
        db.mark_downloaded(eid1, "msg1", "f1.eml")
        db.mark_downloaded(eid2, "msg2", "f2.eml")

        stats = db.get_stats()
        assert stats["total_emails"] == 2
        assert stats["trash_count"] == 0

        db.trash_email(eid1, "trash/f1.eml")
        stats = db.get_stats()
        assert stats["total_emails"] == 1
        assert stats["trash_count"] == 1

    def test_schema_has_trash_columns(self, temp_dir):
        """Test that trash columns exist in schema."""
        db = ArchiveDatabase(temp_dir)
        with sqlite3.connect(db.db_path) as conn:
            info = conn.execute("PRAGMA table_info(emails)").fetchall()
            columns = {row[1] for row in info}
        assert "trashed_at" in columns
        assert "original_filename" in columns


LEGACY_SCHEMA = """
    CREATE TABLE emails (
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
        snippet TEXT,
        sender_email TEXT,
        recipient_emails TEXT,
        has_attachments INTEGER DEFAULT 0
    )
"""


class TestMessageIdMigration:
    """Tests for the message_id -> email_id schema migration."""

    def _legacy_db(self, temp_dir, rows=()):
        """Write a pre-migration database file and return its path."""
        db_path = temp_dir / "ownmail.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(LEGACY_SCHEMA)
            for rowid, message_id, account in rows:
                conn.execute(
                    "INSERT INTO emails (rowid, message_id, filename, account, subject) VALUES (?, ?, ?, ?, ?)",
                    (rowid, message_id, f"{message_id}.eml", account, f"Subject {message_id}"),
                )
            conn.commit()
        return db_path

    def _columns(self, db_path):
        with sqlite3.connect(db_path) as conn:
            return {row[1] for row in conn.execute("PRAGMA table_info(emails)")}

    def test_migrates_legacy_schema(self, temp_dir, capsys):
        """A legacy database should gain email_id/provider_id columns."""
        db_path = self._legacy_db(temp_dir, [(1, "msg1", "a@example.com")])

        ArchiveDatabase(temp_dir)

        cols = self._columns(db_path)
        assert "email_id" in cols
        assert "provider_id" in cols
        assert "message_id" not in cols
        assert "migrated 1 rows" in capsys.readouterr().out

    def test_email_id_derived_from_account_and_message_id(self, temp_dir):
        """Each migrated row's email_id should match make_email_id."""
        db_path = self._legacy_db(temp_dir, [(1, "msg1", "a@example.com")])

        ArchiveDatabase(temp_dir)

        with sqlite3.connect(db_path) as conn:
            email_id, provider_id = conn.execute("SELECT email_id, provider_id FROM emails").fetchone()
        assert email_id == ArchiveDatabase.make_email_id("a@example.com", "msg1")
        assert provider_id == "msg1"

    def test_null_account_migrates_as_empty_string(self, temp_dir):
        """A row with no account should hash against an empty account."""
        db_path = self._legacy_db(temp_dir, [(1, "msg1", None)])

        ArchiveDatabase(temp_dir)

        with sqlite3.connect(db_path) as conn:
            (email_id,) = conn.execute("SELECT email_id FROM emails").fetchone()
        assert email_id == ArchiveDatabase.make_email_id("", "msg1")

    def test_rowids_are_preserved(self, temp_dir):
        """rowids must survive so FTS5 and junction tables stay valid."""
        db_path = self._legacy_db(temp_dir, [(5, "msg5", "a@example.com"), (9, "msg9", "a@example.com")])

        ArchiveDatabase(temp_dir)

        with sqlite3.connect(db_path) as conn:
            rows = dict(conn.execute("SELECT rowid, provider_id FROM emails").fetchall())
        assert rows == {5: "msg5", 9: "msg9"}

    def test_other_columns_survive(self, temp_dir):
        """Non-key columns should carry across the migration."""
        db_path = self._legacy_db(temp_dir, [(1, "msg1", "a@example.com")])

        ArchiveDatabase(temp_dir)

        with sqlite3.connect(db_path) as conn:
            filename, subject = conn.execute("SELECT filename, subject FROM emails").fetchone()
        assert filename == "msg1.eml"
        assert subject == "Subject msg1"

    def test_empty_legacy_table_migrates(self, temp_dir, capsys):
        """A legacy database with no rows should still be migrated."""
        db_path = self._legacy_db(temp_dir)

        ArchiveDatabase(temp_dir)

        assert "email_id" in self._columns(db_path)
        assert "migrated 0 rows" in capsys.readouterr().out

    def test_fresh_database_is_not_migrated(self, temp_dir, capsys):
        """A brand new database should skip the migration entirely."""
        ArchiveDatabase(temp_dir)
        assert "Migrating database schema" not in capsys.readouterr().out

    def test_already_migrated_database_is_untouched(self, temp_dir, capsys):
        """Reopening a migrated database must not re-run the migration."""
        self._legacy_db(temp_dir, [(1, "msg1", "a@example.com")])
        ArchiveDatabase(temp_dir)
        capsys.readouterr()

        ArchiveDatabase(temp_dir)

        assert "Migrating database schema" not in capsys.readouterr().out

    def test_unexpected_schema_is_left_alone(self, temp_dir, capsys):
        """A table with neither key column should be skipped, not rewritten.

        Driven through the migration directly: such a table cannot support
        the rest of _init_db, so the guard is what matters here.
        """
        db = ArchiveDatabase(temp_dir)
        foreign = temp_dir / "foreign.db"
        with sqlite3.connect(foreign) as conn:
            conn.execute("CREATE TABLE emails (something_else TEXT)")
            conn.commit()
            capsys.readouterr()

            db._migrate_message_id_to_email_id(conn)

            assert "Migrating database schema" not in capsys.readouterr().out
            cols = {row[1] for row in conn.execute("PRAGMA table_info(emails)")}
        assert cols == {"something_else"}


class TestSearchNegatedFilters:
    """Tests for negated label and recipient filters in search."""

    def _db_with_email(self, temp_dir, *, labels=(), recipients=()):
        db = ArchiveDatabase(temp_dir)
        email_id = _eid("msg1")
        db.mark_downloaded(email_id, "msg1", "msg1.eml", email_date="2024-01-15T00:00:00+00:00")
        db.index_email(
            email_id=email_id,
            subject="Quarterly invoice",
            sender="billing@example.com",
            recipients=", ".join(recipients) or "user@example.com",
            date_str="2024-01-15",
            body="invoice body",
            attachments="",
        )
        if labels:
            with sqlite3.connect(db.db_path) as conn:
                (rowid,) = conn.execute("SELECT rowid FROM emails WHERE email_id = ?", (email_id,)).fetchone()
                for label in labels:
                    conn.execute(
                        "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                        (rowid, label, "2024-01-15T00:00:00+00:00"),
                    )
                conn.commit()
        return db

    def test_negated_label_excludes_match(self, temp_dir):
        """-label: should drop emails carrying that label."""
        db = self._db_with_email(temp_dir, labels=["Work"])
        assert db.search("invoice") != []
        assert db.search("invoice -label:Work") == []

    def test_negated_label_keeps_non_match(self, temp_dir):
        """-label: should keep emails without that label."""
        db = self._db_with_email(temp_dir, labels=["Work"])
        assert db.search("invoice -label:Personal") != []

    def test_negated_recipient_excludes_match(self, temp_dir):
        """-to: with an address should drop emails sent to it."""
        db = self._db_with_email(temp_dir, recipients=["bob@example.com"])
        assert db.search("invoice") != []
        assert db.search("invoice -to:bob@example.com") == []

    def test_negated_recipient_keeps_non_match(self, temp_dir):
        """-to: should keep emails sent to a different address."""
        db = self._db_with_email(temp_dir, recipients=["bob@example.com"])
        assert db.search("invoice -to:carol@example.com") != []

    def test_parse_error_returns_no_results(self, temp_dir, capsys):
        """A malformed query should return nothing and report the error."""
        db = ArchiveDatabase(temp_dir)
        assert db.search('"unclosed') == []
        assert "Parse error" in capsys.readouterr().out
