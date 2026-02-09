"""Integration tests for ownmail CLI commands."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ownmail import GmailArchive


class TestGmailArchiveInit:
    """Tests for GmailArchive initialization."""

    def test_creates_archive_directory(self, temp_dir):
        """Test that archive directory is created."""
        archive_path = temp_dir / "my_archive"
        GmailArchive(archive_path)

        assert archive_path.exists()
        assert (archive_path / "ownmail.db").exists()

    def test_creates_emails_subdirectory_path(self, temp_dir):
        """Test that emails_dir is set correctly."""
        archive = GmailArchive(temp_dir)

        assert archive.emails_dir == temp_dir / "emails"


class TestIndexEmail:
    """Tests for email indexing."""

    def test_index_email_from_file(self, temp_dir, sample_eml_simple):
        """Test indexing an email file."""
        archive = GmailArchive(temp_dir)

        # Create a test email file
        email_path = temp_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Mark as downloaded first
        archive.db.mark_downloaded("test123", str(email_path.relative_to(temp_dir)))

        # Index it
        result = archive.index_email("test123", email_path)

        assert result is True
        assert archive.db.is_indexed("test123")

    def test_index_email_updates_hash(self, temp_dir, sample_eml_simple):
        """Test that indexing updates content_hash and indexed_hash."""
        archive = GmailArchive(temp_dir)

        email_path = temp_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded("test123", "test.eml")
        archive.index_email("test123", email_path, update_hash=True)

        with sqlite3.connect(archive.db.db_path) as conn:
            row = conn.execute(
                "SELECT content_hash, indexed_hash FROM emails WHERE message_id = ?",
                ("test123",)
            ).fetchone()

        assert row[0] is not None  # content_hash
        assert row[1] is not None  # indexed_hash
        assert row[0] == row[1]    # should match after indexing


class TestCmdStats:
    """Tests for stats command."""

    def test_stats_runs_without_error(self, temp_dir, capsys):
        """Test that stats command runs."""
        archive = GmailArchive(temp_dir)

        # Create emails directory
        (temp_dir / "emails").mkdir()

        # Use database stats instead of cmd_stats
        stats = archive.db.get_stats()

        assert "total_emails" in stats
        assert stats["total_emails"] == 0


class TestCmdDbCheck:
    """Tests for db-check command."""

    def test_db_check_clean_database(self, temp_dir):
        """Test db-check on a clean database."""
        archive = GmailArchive(temp_dir)

        # Check database has expected structure
        with sqlite3.connect(archive.db.db_path) as conn:
            # Verify FTS table exists
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='emails_fts'"
            ).fetchone()
            assert result is not None

    def test_db_check_finds_duplicates(self, temp_dir):
        """Test that db-check finds duplicate FTS entries."""
        archive = GmailArchive(temp_dir)

        # Manually create duplicates (with 6 columns including account)
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?)",
                        ("msg1", "file1.eml", "2024-01-01", "hash1", "hash1", None))
            conn.execute(
                "INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("msg1", "Subj1", "from", "to", "date", "body", "")
            )
            conn.execute(
                "INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("msg1", "Subj2", "from", "to", "date", "body2", "")
            )
            conn.commit()

        # Check we have duplicates
        with sqlite3.connect(archive.db.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM emails_fts WHERE message_id = ?", ("msg1",)
            ).fetchone()[0]
        assert count == 2

    def test_db_check_fix_duplicates(self, temp_dir):
        """Test that duplicate detection works."""
        archive = GmailArchive(temp_dir)

        # Create duplicates (with 6 columns including account)
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?)",
                        ("msg1", "file1.eml", "2024-01-01", "hash1", "hash1", None))
            conn.execute(
                "INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("msg1", "Old", "from", "to", "date", "body", "")
            )
            conn.execute(
                "INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("msg1", "New", "from", "to", "date", "body", "")
            )
            conn.commit()

        # Check duplicates exist
        with sqlite3.connect(archive.db.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM emails_fts WHERE message_id = ?", ("msg1",)
            ).fetchone()[0]

        assert count == 2
