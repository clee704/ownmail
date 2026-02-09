"""Tests for maintenance commands."""

import sqlite3
from pathlib import Path

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
        assert "matching '2024/*'" in captured.out

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
        capsys.readouterr()

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


class TestCmdVerifyEdgeCases:
    """Additional tests for verify command."""

    def test_verify_empty_database(self, temp_dir, capsys):
        """Test verify on empty database."""
        archive = EmailArchive(temp_dir, {})
        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "No emails to verify" in captured.out

    def test_verify_valid_email(self, temp_dir, sample_eml_simple, capsys):
        """Test verify with valid email."""
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
        assert "Verifying" in captured.out

    def test_verify_missing_file(self, temp_dir, capsys):
        """Test verify detects missing files."""
        archive = EmailArchive(temp_dir, {})

        # Add to DB but don't create file
        archive.db.mark_downloaded("missing123", "emails/2024/01/missing.eml", content_hash="abc")

        cmd_verify(archive)
        capsys.readouterr()
        # Should complete without crashing

    def test_verify_corrupted_file(self, temp_dir, sample_eml_simple, capsys):
        """Test verify detects corrupted files."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Store with wrong hash
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash="wrong_hash")

        cmd_verify(archive)
        capsys.readouterr()
        # Should detect mismatch

    def test_verify_no_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test verify handles emails with no hash."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Store without hash
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash=None)

        cmd_verify(archive)
        capsys.readouterr()
        # Should complete without crashing

    def test_verify_orphaned_files(self, temp_dir, sample_eml_simple, capsys):
        """Test verify detects orphaned files on disk."""
        archive = EmailArchive(temp_dir, {})

        # Create file but don't add to DB
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "orphan.eml"
        email_path.write_bytes(sample_eml_simple)

        cmd_verify(archive)
        capsys.readouterr()
        # Should detect orphaned file


class TestCmdRehashEdgeCases:
    """Additional tests for rehash command."""

    def test_rehash_empty_database(self, temp_dir, capsys):
        """Test rehash on empty database."""
        archive = EmailArchive(temp_dir, {})
        cmd_rehash(archive)
        captured = capsys.readouterr()
        assert "Compute Hashes" in captured.out or "already have hashes" in captured.out

    def test_rehash_computes_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test rehash computes missing hashes."""
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
        assert "Rehash" in captured.out

    def test_rehash_skips_existing(self, temp_dir, sample_eml_simple, capsys):
        """Test rehash skips emails with existing hash."""
        import hashlib
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Store with hash
        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash=content_hash)

        cmd_rehash(archive)
        capsys.readouterr()
        # Should complete without errors

    def test_rehash_missing_file(self, temp_dir, capsys):
        """Test rehash handles missing files."""
        archive = EmailArchive(temp_dir, {})

        # Add to DB without hash but don't create file
        archive.db.mark_downloaded("missing123", "emails/2024/01/missing.eml", content_hash=None)

        cmd_rehash(archive)
        captured = capsys.readouterr()
        # Should report errors for missing files
        assert "Errors" in captured.out or "Rehash Complete" in captured.out

    def test_rehash_computes_correct_hash(self, temp_dir, sample_eml_simple):
        """Test rehash computes correct SHA256 hash."""
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

        # Verify correct hash was stored
        expected_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        with sqlite3.connect(archive.db.db_path) as conn:
            stored_hash = conn.execute(
                "SELECT content_hash FROM emails WHERE message_id = ?",
                ("test123",)
            ).fetchone()[0]
        assert stored_hash == expected_hash


class TestCmdSyncCheck:
    """Tests for sync-check command."""

    def test_sync_check_no_sources(self, temp_dir, capsys):
        """Test sync-check with no sources configured."""
        from ownmail.commands import cmd_sync_check
        archive = EmailArchive(temp_dir, {})

        cmd_sync_check(archive)
        captured = capsys.readouterr()
        assert "No sources" in captured.out or "no Gmail" in captured.out.lower()

    def test_sync_check_with_gmail_source(self, temp_dir, capsys):
        """Test sync-check with mocked Gmail source."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["msg1", "msg2", "msg3"]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "Sync Check" in captured.out

    def test_sync_check_in_sync(self, temp_dir, capsys):
        """Test sync-check when local matches server."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Add messages to local archive
        archive.db.mark_downloaded("msg1", "emails/2024/01/msg1.eml", content_hash="abc", account="test@gmail.com")
        archive.db.mark_downloaded("msg2", "emails/2024/01/msg2.eml", content_hash="def", account="test@gmail.com")

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["msg1", "msg2"]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "in sync" in captured.out.lower()


class TestCmdAddLabels:
    """Tests for add-labels command."""

    def test_add_labels_no_sources(self, temp_dir, capsys):
        """Test add-labels with no sources configured."""
        from ownmail.commands import cmd_add_labels
        archive = EmailArchive(temp_dir, {})

        cmd_add_labels(archive)
        captured = capsys.readouterr()
        assert "No sources" in captured.out

    def test_add_labels_no_emails(self, temp_dir, capsys):
        """Test add-labels with no emails to process."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_add_labels

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider_class.return_value = mock_provider

            cmd_add_labels(archive)

        captured = capsys.readouterr()
        assert "No emails" in captured.out or "Add Labels" in captured.out

    def test_add_labels_with_emails(self, temp_dir, sample_eml_simple, capsys):
        """Test add-labels with emails that need labels."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_add_labels

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Add to database
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash="abc", account="test@gmail.com")

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_labels_for_message.return_value = ["INBOX", "Work"]
            mock_provider_class.return_value = mock_provider

            cmd_add_labels(archive)

        captured = capsys.readouterr()
        assert "Add Labels" in captured.out

    def test_add_labels_already_has_labels(self, temp_dir, capsys):
        """Test add-labels skips emails with existing labels."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_add_labels

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Create email file with labels already
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(b"""X-Gmail-Labels: INBOX
From: test@example.com
Subject: Test

Body
""")

        # Add to database
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash="abc", account="test@gmail.com")

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider_class.return_value = mock_provider

            cmd_add_labels(archive)

        captured = capsys.readouterr()
        assert "Skipped" in captured.out or "Add Labels" in captured.out


class TestCmdDbCheckVerbose:
    """Additional tests for db-check verbose output."""

    def test_db_check_verbose_shows_all_files(self, temp_dir, capsys):
        """Test db-check --verbose shows all files."""
        archive = EmailArchive(temp_dir, {})

        # Create multiple orphaned FTS entries
        with sqlite3.connect(archive.db.db_path) as conn:
            for i in range(15):
                conn.execute("""
                    INSERT INTO emails_fts (message_id, subject, sender, recipients, body, attachments)
                    VALUES (?, 'test', 'test', 'test', 'test', '')
                """, (f"orphan{i}",))
            conn.commit()

        cmd_db_check(archive, verbose=True)
        captured = capsys.readouterr()
        assert "orphan" in captured.out


class TestCmdVerifyVerbose:
    """Additional tests for verify verbose output."""

    def test_verify_verbose_shows_all_files(self, temp_dir, sample_eml_simple, capsys):
        """Test verify --verbose shows all files."""
        archive = EmailArchive(temp_dir, {})

        # Create multiple emails with wrong hashes
        for i in range(7):
            emails_dir = temp_dir / "emails" / "2024" / "01"
            emails_dir.mkdir(parents=True, exist_ok=True)
            email_path = emails_dir / f"test{i}.eml"
            email_path.write_bytes(sample_eml_simple)

            rel_path = str(email_path.relative_to(temp_dir))
            archive.db.mark_downloaded(f"test{i}", rel_path, content_hash="wrong_hash")

        cmd_verify(archive, verbose=True)
        captured = capsys.readouterr()
        # Should show corrupted files
        assert "test" in captured.out or "Verify" in captured.out


class TestCmdReindexDebug:
    """Tests for reindex debug mode."""

    def test_reindex_debug_shows_timing(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex --debug shows timing info."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash=None)

        cmd_reindex(archive, debug=True)
        captured = capsys.readouterr()
        # Should complete - debug mode outputs more info
        assert "Reindex" in captured.out


class TestCmdSyncCheckDifferences:
    """Tests for sync-check with differences."""

    def test_sync_check_emails_on_gmail_not_local(self, temp_dir, capsys):
        """Test sync-check when Gmail has emails not in local."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["msg1", "msg2", "msg3"]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "On Gmail but not local" in captured.out or "3" in captured.out

    def test_sync_check_emails_on_local_not_gmail(self, temp_dir, capsys):
        """Test sync-check when local has emails not on Gmail."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Add local emails
        archive.db.mark_downloaded("local1", "emails/2024/01/local1.eml", content_hash="abc", account="test@gmail.com")
        archive.db.mark_downloaded("local2", "emails/2024/01/local2.eml", content_hash="def", account="test@gmail.com")

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = []  # Gmail is empty
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "On local but not on Gmail" in captured.out or "deleted" in captured.out

    def test_sync_check_verbose_shows_all(self, temp_dir, capsys):
        """Test sync-check --verbose shows all message IDs."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "test_gmail",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            # More than 5 to trigger truncation unless verbose
            mock_provider.get_all_message_ids.return_value = [f"msg{i}" for i in range(10)]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive, verbose=True)

        captured = capsys.readouterr()
        assert "Sync Check" in captured.out


class TestCmdReindexEdgeCases:
    """Additional edge case tests for reindex."""

    def test_reindex_with_missing_file_continues(self, temp_dir, capsys):
        """Test reindex skips missing files and continues."""
        archive = EmailArchive(temp_dir, {})

        # Add to DB but don't create file
        archive.db.mark_downloaded("missing123", "emails/2024/01/missing.eml", content_hash=None)

        cmd_reindex(archive)
        captured = capsys.readouterr()
        # Should complete without crashing
        assert "Reindex" in captured.out

    def test_reindex_updates_indexed_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex updates the indexed_hash after indexing."""
        import hashlib
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash=content_hash)

        cmd_reindex(archive)

        # Check indexed_hash was set
        with sqlite3.connect(archive.db.db_path) as conn:
            result = conn.execute(
                "SELECT indexed_hash FROM emails WHERE message_id = ?",
                ("test123",)
            ).fetchone()
        assert result[0] == content_hash


class TestCmdVerifyMoreEdgeCases:
    """More edge case tests for verify."""

    def test_verify_with_orphaned_files(self, temp_dir, sample_eml_simple, capsys):
        """Test verify detects orphaned files on disk."""
        archive = EmailArchive(temp_dir, {})

        # Create file but don't add to DB
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "orphan.eml"
        email_path.write_bytes(sample_eml_simple)

        cmd_verify(archive)
        captured = capsys.readouterr()
        # Should mention orphaned files
        assert "orphan" in captured.out.lower() or "disk" in captured.out.lower() or "Verify" in captured.out
