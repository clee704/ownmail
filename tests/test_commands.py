"""Tests for maintenance commands."""

import sqlite3
from pathlib import Path

import pytest

from ownmail.archive import EmailArchive
from ownmail.commands import (
    _print_file_list,
    cmd_db_check,
    cmd_rehash,
    cmd_reindex,
    cmd_verify,
)


class TestPrintFileList:
    """Tests for _print_file_list helper."""

    def test_prints_nothing_for_empty_list(self, capsys):
        """Test that nothing is printed for empty list."""
        _print_file_list([], "Test Label", verbose=False)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_prints_truncated_list(self, capsys):
        """Test that list is truncated when not verbose."""
        files = [f"file{i}.eml" for i in range(10)]
        _print_file_list(files, "Test Files", verbose=False, max_show=3)
        captured = capsys.readouterr()
        assert "Test Files: 10" in captured.out
        assert "file0.eml" in captured.out
        assert "file2.eml" in captured.out
        assert "... and 7 more" in captured.out

    def test_prints_full_list_when_verbose(self, capsys):
        """Test that full list is printed when verbose."""
        files = [f"file{i}.eml" for i in range(10)]
        _print_file_list(files, "Test Files", verbose=True)
        captured = capsys.readouterr()
        assert "Test Files: 10" in captured.out
        assert "file9.eml" in captured.out
        assert "... and" not in captured.out


class TestCmdReindex:
    """Tests for reindex command."""

    def test_reindex_empty_database(self, temp_dir, capsys):
        """Test reindex on empty database."""
        archive = EmailArchive(temp_dir, {})
        cmd_reindex(archive)
        captured = capsys.readouterr()
        assert "already indexed" in captured.out or "Reindex" in captured.out

    def test_reindex_single_file(self, temp_dir, sample_eml_simple, capsys):
        """Test reindexing a single file."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Mark as downloaded
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path)

        # Reindex single file
        cmd_reindex(archive, file_path=email_path)
        captured = capsys.readouterr()
        assert "Indexed successfully" in captured.out or "Indexing" in captured.out

    def test_reindex_nonexistent_file(self, temp_dir, capsys):
        """Test reindex with nonexistent file."""
        archive = EmailArchive(temp_dir, {})
        cmd_reindex(archive, file_path=Path("/nonexistent/file.eml"))
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_reindex_force_mode(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with force flag."""
        archive = EmailArchive(temp_dir, {})

        # Create and index an email
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash="abc123")

        # Set indexed_hash so it looks already indexed
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET indexed_hash = 'abc123' WHERE message_id = 'test123'")
            conn.commit()

        # Without force, should skip
        cmd_reindex(archive)
        captured = capsys.readouterr()
        assert "already indexed" in captured.out

        # With force, should reindex
        cmd_reindex(archive, force=True)
        captured = capsys.readouterr()
        assert "Force mode" in captured.out

    def test_reindex_with_pattern(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with pattern filter."""
        archive = EmailArchive(temp_dir, {})

        # Create multiple emails
        for year in ["2023", "2024"]:
            emails_dir = temp_dir / "emails" / year / "01"
            emails_dir.mkdir(parents=True)
            email_path = emails_dir / "test.eml"
            email_path.write_bytes(sample_eml_simple)

            rel_path = str(email_path.relative_to(temp_dir))
            archive.db.mark_downloaded(f"msg_{year}", rel_path, content_hash=None)

        # Reindex only 2024
        cmd_reindex(archive, pattern="2024/*")
        captured = capsys.readouterr()
        assert "Pattern '2024/*'" in captured.out

    def test_reindex_single_file_not_in_db(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex single file that's not in database."""
        archive = EmailArchive(temp_dir, {})

        # Create file but don't add to DB
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "standalone.eml"
        email_path.write_bytes(sample_eml_simple)

        # Index single file - should use filename as message_id
        cmd_reindex(archive, file_path=email_path)
        captured = capsys.readouterr()
        assert "Indexing:" in captured.out


class TestCmdVerify:
    """Tests for verify command."""

    def test_verify_empty_database(self, temp_dir, capsys):
        """Test verify on empty database."""
        archive = EmailArchive(temp_dir, {})
        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "No emails to verify" in captured.out

    def test_verify_finds_missing_file(self, temp_dir, capsys):
        """Test verify detects missing files."""
        archive = EmailArchive(temp_dir, {})

        # Add email record but don't create the file
        archive.db.mark_downloaded("test123", "emails/2024/01/missing.eml", content_hash="abc123")

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "missing from disk" in captured.out or "Missing" in captured.out.lower()

    def test_verify_detects_corruption(self, temp_dir, capsys):
        """Test verify detects corrupted files."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(b"Original content")

        # Store with different hash
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash="wrong_hash_value")

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "CORRUPTED" in captured.out or "mismatch" in captured.out.lower()

    def test_verify_all_ok(self, temp_dir, sample_eml_simple, capsys):
        """Test verify when all files are OK."""
        import hashlib

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Store with correct hash
        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash=content_hash)

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "OK: 1" in captured.out

    def test_verify_finds_orphaned_files(self, temp_dir, sample_eml_simple, capsys):
        """Test verify detects orphaned files on disk."""
        import hashlib
        archive = EmailArchive(temp_dir, {})

        # Create one indexed email so verify has something to do
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        indexed_path = emails_dir / "indexed.eml"
        indexed_path.write_bytes(sample_eml_simple)
        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        archive.db.mark_downloaded("indexed123", str(indexed_path.relative_to(temp_dir)), content_hash=content_hash)

        # Create orphaned email file not in database
        (emails_dir / "orphaned.eml").write_bytes(b"Orphaned email")

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "not in index" in captured.out or "orphan" in captured.out.lower()


class TestCmdRehash:
    """Tests for rehash command."""

    def test_rehash_empty_database(self, temp_dir, capsys):
        """Test rehash on empty database."""
        archive = EmailArchive(temp_dir, {})
        cmd_rehash(archive)
        captured = capsys.readouterr()
        assert "already have hashes" in captured.out

    def test_rehash_computes_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test rehash computes hashes for emails without them."""
        import hashlib

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Store without hash
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash=None)

        cmd_rehash(archive)
        captured = capsys.readouterr()
        assert "Hashed: 1" in captured.out

        # Verify hash was stored
        with sqlite3.connect(archive.db.db_path) as conn:
            result = conn.execute(
                "SELECT content_hash FROM emails WHERE message_id = 'test123'"
            ).fetchone()

        expected_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        assert result[0] == expected_hash

    def test_rehash_skips_missing_files(self, temp_dir, capsys):
        """Test rehash handles missing files gracefully."""
        archive = EmailArchive(temp_dir, {})

        # Add record without creating file
        archive.db.mark_downloaded("test123", "emails/missing.eml", content_hash=None)

        cmd_rehash(archive)
        captured = capsys.readouterr()
        assert "Errors" in captured.out or "missing" in captured.out.lower()


class TestCmdDbCheck:
    """Tests for db-check command."""

    def test_db_check_clean_database(self, temp_dir, capsys):
        """Test db-check on clean database."""
        archive = EmailArchive(temp_dir, {})
        cmd_db_check(archive)
        captured = capsys.readouterr()
        assert "No issues found" in captured.out or "Database Check" in captured.out

    def test_db_check_finds_duplicate_fts(self, temp_dir, capsys):
        """Test db-check finds duplicate FTS entries."""
        archive = EmailArchive(temp_dir, {})

        # Add email and index it twice
        archive.db.mark_downloaded("test123", "test.eml")
        archive.db.index_email(
            "test123", "Subject", "sender@test.com", "recipient@test.com",
            "2024-01-01", "Body text", ""
        )
        # Add duplicate FTS entry
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments)
                VALUES ('test123', 'Subject 2', 'sender@test.com', 'recipient@test.com', '2024-01-01', 'Body', '')
            """)
            conn.commit()

        cmd_db_check(archive, verbose=True)
        captured = capsys.readouterr()
        assert "duplicate" in captured.out.lower()

    def test_db_check_fixes_duplicates(self, temp_dir, capsys):
        """Test db-check --fix removes duplicates."""
        archive = EmailArchive(temp_dir, {})

        archive.db.mark_downloaded("test123", "test.eml")
        # Add two FTS entries for same message
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments)
                VALUES ('test123', 'Subject 1', 'a@test.com', 'b@test.com', '2024-01-01', 'Body 1', '')
            """)
            conn.execute("""
                INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments)
                VALUES ('test123', 'Subject 2', 'a@test.com', 'b@test.com', '2024-01-01', 'Body 2', '')
            """)
            conn.commit()

        cmd_db_check(archive, fix=True)
        captured = capsys.readouterr()
        assert "Fixed" in captured.out

        # Verify only one entry remains
        with sqlite3.connect(archive.db.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM emails_fts WHERE message_id = 'test123'"
            ).fetchone()[0]
        assert count == 1

    def test_db_check_finds_orphaned_fts(self, temp_dir, capsys):
        """Test db-check finds orphaned FTS entries."""
        archive = EmailArchive(temp_dir, {})

        # Add FTS entry without corresponding email record
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments)
                VALUES ('orphan123', 'Orphan', 'a@test.com', 'b@test.com', '2024-01-01', 'Body', '')
            """)
            conn.commit()

        cmd_db_check(archive)
        captured = capsys.readouterr()
        assert "orphaned" in captured.out.lower() or "no matching" in captured.out.lower()

    def test_db_check_finds_missing_fts(self, temp_dir, capsys):
        """Test db-check finds emails missing from FTS."""
        archive = EmailArchive(temp_dir, {})

        # Add email without FTS entry
        archive.db.mark_downloaded("test123", "test.eml")

        cmd_db_check(archive)
        captured = capsys.readouterr()
        assert "not in search index" in captured.out or "missing" in captured.out.lower()

    def test_db_check_fixes_orphaned_fts(self, temp_dir, capsys):
        """Test db-check --fix removes orphaned FTS entries."""
        archive = EmailArchive(temp_dir, {})

        # Add FTS entry without corresponding email record
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails_fts (message_id, subject, sender, recipients, date_str, body, attachments)
                VALUES ('orphan123', 'Orphan', 'a@test.com', 'b@test.com', '2024-01-01', 'Body', '')
            """)
            conn.commit()

        cmd_db_check(archive, fix=True)
        captured = capsys.readouterr()

        # Verify entry was removed
        with sqlite3.connect(archive.db.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM emails_fts WHERE message_id = 'orphan123'"
            ).fetchone()[0]
        assert count == 0

    def test_db_check_hash_mismatches(self, temp_dir, sample_eml_simple, capsys):
        """Test db-check detects hash mismatches."""
        import hashlib
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Store with correct content_hash but different indexed_hash
        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        rel_path = str(email_path.relative_to(temp_dir))

        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails (message_id, filename, content_hash, indexed_hash)
                VALUES (?, ?, ?, 'different_hash')
            """, ("test123", rel_path, content_hash))
            conn.commit()

        cmd_db_check(archive)
        captured = capsys.readouterr()
        assert "out of date" in captured.out or "mismatch" in captured.out.lower()

    def test_db_check_missing_content_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test db-check detects missing content hashes."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        rel_path = str(email_path.relative_to(temp_dir))

        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails (message_id, filename, content_hash)
                VALUES (?, ?, NULL)
            """, ("test456", rel_path))
            conn.commit()

        cmd_db_check(archive)
        captured = capsys.readouterr()
        assert "missing" in captured.out.lower() or "hash" in captured.out.lower()
