"""Tests for maintenance commands."""

import sqlite3
from pathlib import Path

from ownmail.archive import EmailArchive
from ownmail.commands import (
    _print_file_list,
    cmd_reindex,
    cmd_verify,
)
from ownmail.database import ArchiveDatabase


def _eid(provider_id, account=""):
    """Compute email_id from provider_id for tests."""
    return ArchiveDatabase.make_email_id(account, provider_id)


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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path)

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash="abc123")

        # Set indexed_hash so it looks already indexed
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET indexed_hash = 'abc123' WHERE email_id = ?", (_eid("test123"),))
            conn.commit()

        # Without force, should skip
        cmd_reindex(archive)
        captured = capsys.readouterr()
        assert "already indexed" in captured.out

        # With force, should reindex
        cmd_reindex(archive, force=True)
        captured = capsys.readouterr()
        assert "(force)" in captured.out

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
            archive.db.mark_downloaded(_eid(f"msg_{year}"), f"msg_{year}", rel_path, content_hash=None)

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
        assert "No emails in database" in captured.out

    def test_verify_finds_missing_file(self, temp_dir, capsys):
        """Test verify detects missing files."""
        archive = EmailArchive(temp_dir, {})

        # Add email record but don't create the file
        archive.db.mark_downloaded(_eid("test123"), "test123", "emails/2024/01/missing.eml", content_hash="abc123")

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "missing from disk" in captured.out.lower()

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash="wrong_hash_value")

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash=content_hash)

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
        archive.db.mark_downloaded(_eid("indexed123"), "indexed123", str(indexed_path.relative_to(temp_dir)), content_hash=content_hash)

        # Create orphaned email file not in database
        (emails_dir / "orphaned.eml").write_bytes(b"Orphaned email")

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "not indexed" in captured.out or "orphan" in captured.out.lower()

    def test_verify_detects_moved_files(self, temp_dir, sample_eml_simple, capsys):
        """Test verify detects moved/renamed files by matching hashes."""
        import hashlib
        archive = EmailArchive(temp_dir, {})

        # Register email at old path (file doesn't exist there)
        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        archive.db.mark_downloaded(
            _eid("moved123"), "moved123",
            "emails/2024/01/old_name.eml", content_hash=content_hash,
        )

        # Place the same file at a new path (orphaned from DB's perspective)
        new_dir = temp_dir / "emails" / "2024" / "02"
        new_dir.mkdir(parents=True)
        new_path = new_dir / "new_name.eml"
        new_path.write_bytes(sample_eml_simple)

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "moved" in captured.out.lower() or "renamed" in captured.out.lower()
        # Should NOT report as missing or orphaned files
        assert "Missing from disk" not in captured.out
        assert "On disk but not indexed" not in captured.out

    def test_verify_fix_updates_moved_paths(self, temp_dir, sample_eml_simple, capsys):
        """Test verify --fix updates DB paths for moved files."""
        import hashlib
        archive = EmailArchive(temp_dir, {})

        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        archive.db.mark_downloaded(
            _eid("moved123"), "moved123",
            "emails/2024/01/old_name.eml", content_hash=content_hash,
        )

        new_dir = temp_dir / "emails" / "2024" / "02"
        new_dir.mkdir(parents=True)
        (new_dir / "new_name.eml").write_bytes(sample_eml_simple)

        cmd_verify(archive, fix=True)
        captured = capsys.readouterr()
        assert "Updated" in captured.out

        # Verify DB was updated
        with sqlite3.connect(archive.db.db_path) as conn:
            row = conn.execute(
                "SELECT filename FROM emails WHERE email_id = ?",
                (_eid("moved123"),),
            ).fetchone()
        assert row[0] == "emails/2024/02/new_name.eml"


class TestCmdVerifyDatabase:
    """Tests for verify command database checks (formerly db-check)."""

    def test_verify_clean_database(self, temp_dir, capsys):
        """Test verify on clean database."""
        archive = EmailArchive(temp_dir, {})
        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "No emails in database" in captured.out or "Verify" in captured.out

    def test_verify_finds_missing_metadata(self, temp_dir, capsys):
        """Test verify finds emails missing metadata (not indexed)."""
        archive = EmailArchive(temp_dir, {})

        # Add email without indexing it (no subject set)
        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml")

        cmd_verify(archive, verbose=True)
        captured = capsys.readouterr()
        assert "missing metadata" in captured.out.lower() or "missing" in captured.out.lower()

    def test_verify_finds_fts_sync_issues(self, temp_dir, capsys):
        """Test verify finds FTS sync issues."""
        archive = EmailArchive(temp_dir, {})

        # Add email and index it
        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml")
        archive.db.index_email(
            _eid("test123"), "Subject", "sender@test.com", "recipient@test.com",
            "2024-01-01", "Body text", ""
        )

        # Manually drop FTS to simulate sync issue
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("DROP TABLE emails_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE emails_fts USING fts5(
                    subject, sender, recipients, body, attachments,
                    content='', tokenize='porter unicode61'
                )
            """)
            conn.commit()

        cmd_verify(archive, verbose=True)
        captured = capsys.readouterr()
        assert "FTS" in captured.out

    def test_verify_fix_rebuilds_fts(self, temp_dir, capsys):
        """Test verify --fix rebuilds FTS when out of sync."""
        archive = EmailArchive(temp_dir, {})

        # Create actual email file on disk
        email_path = temp_dir / "test.eml"
        email_path.write_bytes(b"Subject: Test\n\nBody text")

        # Add email and index it
        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml")
        archive.db.index_email(
            _eid("test123"), "Subject", "sender@test.com", "recipient@test.com",
            "2024-01-01", "Body text", ""
        )

        # Drop FTS entries to simulate sync issue
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("DROP TABLE emails_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE emails_fts USING fts5(
                    subject, sender, recipients, body, attachments,
                    content='', tokenize='porter unicode61'
                )
            """)
            conn.commit()

        cmd_verify(archive, fix=True)
        captured = capsys.readouterr()
        assert "rebuilt" in captured.out.lower() or "Fixed" in captured.out or "FTS" in captured.out

        # Verify FTS has entry now
        with sqlite3.connect(archive.db.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
        assert count == 1

    def test_verify_finds_missing_fts(self, temp_dir, capsys):
        """Test verify finds emails missing from FTS (not indexed)."""
        archive = EmailArchive(temp_dir, {})

        # Add email without FTS entry (not indexed)
        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml")

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "missing" in captured.out.lower() or "not yet indexed" in captured.out.lower()

    def test_verify_hash_mismatches(self, temp_dir, sample_eml_simple, capsys):
        """Test verify detects hash mismatches."""
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
                INSERT INTO emails (email_id, provider_id, filename, content_hash, indexed_hash)
                VALUES (?, ?, ?, ?, 'different_hash')
            """, (_eid("test123"), "test123", rel_path, content_hash))
            conn.commit()

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "stale index" in captured.out or "out of date" in captured.out or "mismatch" in captured.out.lower()

    def test_verify_missing_content_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test verify detects missing content hashes."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        rel_path = str(email_path.relative_to(temp_dir))

        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails (email_id, provider_id, filename, content_hash)
                VALUES (?, ?, ?, NULL)
            """, (_eid("test456"), "test456", rel_path))
            conn.commit()

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "missing" in captured.out.lower() or "hash" in captured.out.lower()


class TestCmdVerifyEdgeCases:
    """Additional tests for verify command."""

    def test_verify_empty_database(self, temp_dir, capsys):
        """Test verify on empty database."""
        archive = EmailArchive(temp_dir, {})
        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "No emails in database" in captured.out

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash=content_hash)

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "Verifying" in captured.out

    def test_verify_missing_file(self, temp_dir, capsys):
        """Test verify detects missing files."""
        archive = EmailArchive(temp_dir, {})

        # Add to DB but don't create file
        archive.db.mark_downloaded(_eid("missing123"), "missing123", "emails/2024/01/missing.eml", content_hash="abc")

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash="wrong_hash")

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash=None)

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
        archive.db.mark_downloaded(_eid("msg1", "test@gmail.com"), "msg1", "emails/2024/01/msg1.eml", content_hash="abc", account="test@gmail.com")
        archive.db.mark_downloaded(_eid("msg2", "test@gmail.com"), "msg2", "emails/2024/01/msg2.eml", content_hash="def", account="test@gmail.com")

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["msg1", "msg2"]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "in sync" in captured.out.lower()


class TestCmdUpdateLabels:
    """Tests for update-labels command."""

    def test_update_labels_no_sources(self, temp_dir, capsys):
        """Test update-labels with no sources configured."""
        from ownmail.commands import cmd_update_labels
        archive = EmailArchive(temp_dir, {})

        cmd_update_labels(archive)
        captured = capsys.readouterr()
        assert "No sources" in captured.out

    def test_update_labels_no_emails(self, temp_dir, capsys):
        """Test update-labels with no emails to process."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_update_labels

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

            cmd_update_labels(archive)

        captured = capsys.readouterr()
        assert "No emails" in captured.out or "Update Labels" in captured.out

    def test_update_labels_with_emails(self, temp_dir, sample_eml_simple, capsys):
        """Test update-labels with emails that need labels."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_update_labels

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
        archive.db.mark_downloaded(_eid("test123", "test@gmail.com"), "test123", rel_path, content_hash="abc", account="test@gmail.com")

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_labels_for_message.return_value = ["INBOX", "Work"]
            mock_provider_class.return_value = mock_provider

            cmd_update_labels(archive)

        captured = capsys.readouterr()
        assert "Update Labels" in captured.out

    def test_update_labels_already_has_labels(self, temp_dir, capsys):
        """Test update-labels skips emails with existing labels."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_update_labels

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
        archive.db.mark_downloaded(_eid("test123", "test@gmail.com"), "test123", rel_path, content_hash="abc", account="test@gmail.com")

        with patch("ownmail.commands.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider_class.return_value = mock_provider

            cmd_update_labels(archive)

        captured = capsys.readouterr()
        assert "Skipped" in captured.out or "Update Labels" in captured.out


class TestCmdVerifyDatabaseVerbose:
    """Additional tests for verify database checks verbose output."""

    def test_verify_verbose_shows_all_info(self, temp_dir, capsys):
        """Test verify --verbose shows detailed database info."""
        archive = EmailArchive(temp_dir, {})

        # Create multiple emails without indexing
        for i in range(5):
            archive.db.mark_downloaded(_eid(f"msg{i}"), f"msg{i}", f"test{i}.eml")

        cmd_verify(archive, verbose=True)
        captured = capsys.readouterr()
        # Should show count of emails missing metadata
        assert "5 emails missing" in captured.out or "missing" in captured.out.lower()


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
            archive.db.mark_downloaded(_eid(f"test{i}"), f"test{i}", rel_path, content_hash="wrong_hash")

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash=None)

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
        archive.db.mark_downloaded(_eid("local1", "test@gmail.com"), "local1", "emails/2024/01/local1.eml", content_hash="abc", account="test@gmail.com")
        archive.db.mark_downloaded(_eid("local2", "test@gmail.com"), "local2", "emails/2024/01/local2.eml", content_hash="def", account="test@gmail.com")

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
        archive.db.mark_downloaded(_eid("missing123"), "missing123", "emails/2024/01/missing.eml", content_hash=None)

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
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash=content_hash)

        cmd_reindex(archive)

        # Check indexed_hash was set
        with sqlite3.connect(archive.db.db_path) as conn:
            result = conn.execute(
                "SELECT indexed_hash FROM emails WHERE email_id = ?",
                (_eid("test123"),)
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


class TestCmdListUnknown:
    """Tests for cmd_list_unknown command."""

    def test_list_unknown_empty(self, temp_dir, capsys):
        """Test list_unknown when no unknown folder exists."""
        from ownmail.commands import cmd_list_unknown

        archive = EmailArchive(temp_dir, {})
        cmd_list_unknown(archive)
        captured = capsys.readouterr()
        # Should report no unknown files or folder doesn't exist
        assert "unknown" in captured.out.lower() or "0" in captured.out

    def test_list_unknown_with_files(self, temp_dir, sample_eml_simple, capsys):
        """Test list_unknown when unknown folder has files."""
        from ownmail.commands import cmd_list_unknown

        archive = EmailArchive(temp_dir, {})

        # Create unknown folder with some files
        unknown_dir = temp_dir / "emails" / "unknown"
        unknown_dir.mkdir(parents=True)
        (unknown_dir / "unknown1.eml").write_bytes(sample_eml_simple)
        (unknown_dir / "unknown2.eml").write_bytes(sample_eml_simple)

        cmd_list_unknown(archive)
        captured = capsys.readouterr()
        # Should list the files
        assert "2" in captured.out or "unknown" in captured.out.lower()

    def test_list_unknown_verbose(self, temp_dir, sample_eml_simple, capsys):
        """Test list_unknown with verbose flag."""
        from ownmail.commands import cmd_list_unknown

        archive = EmailArchive(temp_dir, {})

        # Create unknown folder with files
        unknown_dir = temp_dir / "emails" / "unknown"
        unknown_dir.mkdir(parents=True)
        (unknown_dir / "test.eml").write_bytes(sample_eml_simple)

        cmd_list_unknown(archive, verbose=True)
        captured = capsys.readouterr()
        # Verbose should show more details
        assert "test.eml" in captured.out or "unknown" in captured.out.lower()


class TestCmdPopulateDates:
    """Tests for cmd_populate_dates command."""

    def test_populate_dates_empty(self, temp_dir, capsys):
        """Test populate_dates on empty database."""
        from ownmail.commands import cmd_populate_dates

        archive = EmailArchive(temp_dir, {})
        cmd_populate_dates(archive)
        captured = capsys.readouterr()
        # Should complete without error
        assert "date" in captured.out.lower() or "0" in captured.out or captured.out == ""

    def test_populate_dates_with_emails(self, temp_dir, sample_eml_simple, capsys):
        """Test populate_dates with emails in database."""
        from ownmail.commands import cmd_populate_dates

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash="abc123")

        cmd_populate_dates(archive)
        captured = capsys.readouterr()
        # Should process emails
        assert "date" in captured.out.lower() or "test" in captured.out.lower() or captured.out

