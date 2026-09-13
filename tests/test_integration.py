"""Integration tests for ownmail CLI commands."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ownmail import GmailArchive, sidecar
from ownmail.database import ArchiveDatabase


def _eid(provider_id, account=""):
    return ArchiveDatabase.make_email_id(account, provider_id)


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
        archive.db.mark_downloaded(_eid("test123"), "test123", str(email_path.relative_to(temp_dir)))

        # Index it
        result = archive.index_email(_eid("test123"), email_path)

        assert result is True
        assert archive.db.is_indexed(_eid("test123"))

    def test_index_email_updates_hash(self, temp_dir, sample_eml_simple):
        """Test that indexing updates content_hash and indexed_hash."""
        archive = GmailArchive(temp_dir)

        email_path = temp_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml")
        archive.index_email(_eid("test123"), email_path, update_hash=True)

        with sqlite3.connect(archive.db.db_path) as conn:
            row = conn.execute(
                "SELECT content_hash, indexed_hash FROM emails WHERE email_id = ?", (_eid("test123"),)
            ).fetchone()

        assert row[0] is not None  # content_hash
        assert row[1] is not None  # indexed_hash
        assert row[0] == row[1]  # should match after indexing


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


class TestDatabaseIntegrity:
    """Tests for database integrity (covered by verify command)."""

    def test_clean_database_has_fts(self, temp_dir):
        """Test a clean database has expected FTS structure."""
        archive = GmailArchive(temp_dir)

        # Check database has expected structure
        with sqlite3.connect(archive.db.db_path) as conn:
            # Verify FTS table exists
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='emails_fts'").fetchone()
            assert result is not None

    def test_missing_metadata_detected(self, temp_dir):
        """Test that emails without metadata are detectable."""
        archive = GmailArchive(temp_dir)

        # Add email without metadata (not indexed)
        archive.db.mark_downloaded(_eid("msg1"), "msg1", "file1.eml")

        # Check email exists but has no subject
        with sqlite3.connect(archive.db.db_path) as conn:
            result = conn.execute("SELECT subject FROM emails WHERE email_id = ?", (_eid("msg1"),)).fetchone()
        assert result[0] is None

    def test_fts_sync(self, temp_dir):
        """Test that FTS stays in sync with emails table."""
        archive = GmailArchive(temp_dir)

        # Add email and index it
        archive.db.mark_downloaded(_eid("msg1"), "msg1", "file1.eml")
        archive.db.index_email(_eid("msg1"), "Subject", "from@test.com", "to@test.com", "2024-01-01", "Body text", "")

        # Check FTS has entry
        with sqlite3.connect(archive.db.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
        assert count == 1


class TestGmailArchiveIndexEmail:
    """Tests for the deprecated GmailArchive.index_email compatibility shim."""

    EML = b"From: a@example.com\r\nSubject: Indexed subject\r\nDate: Mon, 1 Jan 2024 10:00:00 +0000\r\n\r\nbody\r\n"

    def _archive_with_email(self, temp_dir):
        from ownmail.database import ArchiveDatabase

        archive = GmailArchive(temp_dir)
        filepath = temp_dir / "mail.eml"
        filepath.write_bytes(self.EML)
        email_id = ArchiveDatabase.make_email_id("", "msg1")
        # email_date must be set: search filters out undated rows by default.
        archive.db.mark_downloaded(email_id, "msg1", "mail.eml", email_date="2024-01-01T10:00:00+00:00")
        return archive, email_id, filepath

    def _hashes(self, archive, email_id):
        import sqlite3

        with sqlite3.connect(archive.db.db_path) as conn:
            return conn.execute(
                "SELECT content_hash, indexed_hash FROM emails WHERE email_id = ?", (email_id,)
            ).fetchone()

    def test_indexes_and_updates_hashes(self, temp_dir):
        """Indexing should populate FTS and record the content hash."""
        import hashlib

        archive, email_id, filepath = self._archive_with_email(temp_dir)

        assert archive.index_email(email_id, filepath) is True

        expected = hashlib.sha256(self.EML).hexdigest()
        assert self._hashes(archive, email_id) == (expected, expected)
        assert archive.db.search("Indexed") != []

    def test_indexes_labels_from_sidecar(self, temp_dir):
        archive, email_id, filepath = self._archive_with_email(temp_dir)
        labels = ["Receipts, 2026", " Work "]
        sidecar.write_labels(filepath, labels)

        assert archive.index_email(email_id, filepath) is True

        assert sorted(archive.db.get_labels_for_email(email_id)) == sorted(labels)

    def test_update_hash_false_leaves_hashes_alone(self, temp_dir):
        """With update_hash off, the stored hashes should not change."""
        archive, email_id, filepath = self._archive_with_email(temp_dir)

        assert archive.index_email(email_id, filepath, update_hash=False) is True

        assert self._hashes(archive, email_id) == (None, None)

    def test_uses_batch_connection_when_present(self, temp_dir):
        """A batch connection should be reused rather than opening a new one."""
        import sqlite3

        archive, email_id, filepath = self._archive_with_email(temp_dir)
        conn = sqlite3.connect(archive.db.db_path)
        archive._batch_conn = conn
        try:
            assert archive.index_email(email_id, filepath) is True
            conn.commit()
        finally:
            conn.close()
            archive._batch_conn = None

        assert self._hashes(archive, email_id)[0] is not None

    def test_debug_prints_timing_breakdown(self, temp_dir, capsys):
        """Debug mode should print the per-stage timing line."""
        archive, email_id, filepath = self._archive_with_email(temp_dir)

        archive.index_email(email_id, filepath, debug=True)

        out = capsys.readouterr().out
        assert "DEBUG: read=" in out
        assert "TOTAL=" in out

    def test_missing_file_reports_error(self, temp_dir, capsys):
        """A missing file should be reported and return False."""
        archive = GmailArchive(temp_dir)

        assert archive.index_email("id1", temp_dir / "gone.eml") is False
        assert "Error indexing" in capsys.readouterr().out
