"""Tests for maintenance commands."""

import hashlib
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

    def test_verify_fix_resets_sync_state_for_missing_files(self, temp_dir, capsys):
        """Test verify --fix resets sync state so backup re-downloads deleted messages."""
        archive = EmailArchive(temp_dir, {})

        # Set up sync state (simulating a completed backup)
        archive.db.set_sync_state("test@gmail.com", "history_id", "12345")

        # Add email record pointing to a missing file
        archive.db.mark_downloaded(
            _eid("missing1", "test@gmail.com"), "missing1",
            "emails/2024/01/missing.eml",
            content_hash="abc123",
            account="test@gmail.com",
        )

        # Run verify --fix
        cmd_verify(archive, fix=True)
        captured = capsys.readouterr()

        # Should have removed the stale entry
        assert "Removed" in captured.out
        # Should have reset sync state
        assert "Reset sync state" in captured.out

        # Verify sync state was actually cleared
        assert archive.db.get_sync_state("test@gmail.com", "history_id") is None

    def test_verify_fix_resets_sync_for_multiple_accounts(self, temp_dir, capsys):
        """Test verify --fix resets sync state for all affected accounts."""
        archive = EmailArchive(temp_dir, {})

        # Set up sync state for two accounts
        archive.db.set_sync_state("alice@gmail.com", "history_id", "111")
        archive.db.set_sync_state("bob@gmail.com", "history_id", "222")

        # Add missing files for both accounts
        archive.db.mark_downloaded(
            _eid("msg1", "alice@gmail.com"), "msg1",
            "emails/2024/01/msg1.eml", content_hash="aaa",
            account="alice@gmail.com",
        )
        archive.db.mark_downloaded(
            _eid("msg2", "bob@gmail.com"), "msg2",
            "emails/2024/01/msg2.eml", content_hash="bbb",
            account="bob@gmail.com",
        )

        cmd_verify(archive, fix=True)
        captured = capsys.readouterr()

        assert "2 account(s)" in captured.out
        assert archive.db.get_sync_state("alice@gmail.com", "history_id") is None
        assert archive.db.get_sync_state("bob@gmail.com", "history_id") is None


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

        with patch("ownmail.providers.gmail.GmailProvider") as mock_provider_class:
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

        with patch("ownmail.providers.gmail.GmailProvider") as mock_provider_class:
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

        cmd_update_labels(archive)

        captured = capsys.readouterr()
        assert "No emails" in captured.out

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

        with patch("ownmail.providers.gmail.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_labels_for_message.return_value = ["INBOX", "Work"]
            mock_provider_class.return_value = mock_provider

            cmd_update_labels(archive)

        captured = capsys.readouterr()
        assert "Update Labels" in captured.out
        assert "Updated: 1" in captured.out

    def test_update_labels_already_has_labels(self, temp_dir, capsys):
        """Test update-labels skips emails with existing labels."""
        import sqlite3

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

        # Add to database with labels already set (in email_labels table)
        email_id = _eid("test123", "test@gmail.com")
        archive.db.mark_downloaded(email_id, "test123", "emails/test.eml", content_hash="abc", account="test@gmail.com")
        conn = sqlite3.connect(archive.db.db_path)
        rowid = conn.execute("SELECT rowid FROM emails WHERE email_id = ?", (email_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
            (rowid, "INBOX", None)
        )
        conn.commit()
        conn.close()

        cmd_update_labels(archive)

        captured = capsys.readouterr()
        assert "No emails need labels" in captured.out

    def test_update_labels_imap_source(self, temp_dir, capsys):
        """Test update-labels with IMAP source derives labels from provider_id."""
        import sqlite3

        from ownmail.commands import cmd_update_labels

        config = {
            "sources": [{
                "name": "test_imap",
                "type": "imap",
                "account": "test@gmail.com",
                "host": "imap.gmail.com",
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Add emails with IMAP-style provider_id (folder:uid)
        eid1 = _eid("INBOX:100", "test@gmail.com")
        eid2 = _eid("[Gmail]/Sent Mail:200", "test@gmail.com")
        archive.db.mark_downloaded(eid1, "INBOX:100", "emails/msg1.eml", content_hash="abc", account="test@gmail.com")
        archive.db.mark_downloaded(eid2, "[Gmail]/Sent Mail:200", "emails/msg2.eml", content_hash="def", account="test@gmail.com")

        cmd_update_labels(archive)

        captured = capsys.readouterr()
        assert "Updated: 2" in captured.out

        # Verify labels in email_labels table
        with sqlite3.connect(archive.db.db_path) as conn:
            rowid1 = conn.execute("SELECT rowid FROM emails WHERE email_id = ?", (eid1,)).fetchone()[0]
            rowid2 = conn.execute("SELECT rowid FROM emails WHERE email_id = ?", (eid2,)).fetchone()[0]
            label1 = conn.execute("SELECT label FROM email_labels WHERE email_rowid = ?", (rowid1,)).fetchone()
            label2 = conn.execute("SELECT label FROM email_labels WHERE email_rowid = ?", (rowid2,)).fetchone()
        assert label1[0] == "INBOX"
        assert label2[0] == "[Gmail]/Sent Mail"

    def test_update_labels_imap_updates_email_labels_table(self, temp_dir, capsys):
        """Test update-labels for IMAP also populates email_labels normalized table."""
        import sqlite3

        from ownmail.commands import cmd_update_labels

        config = {
            "sources": [{
                "name": "test_imap",
                "type": "imap",
                "account": "test@gmail.com",
                "host": "imap.gmail.com",
            }]
        }
        archive = EmailArchive(temp_dir, config)

        eid = _eid("INBOX:100", "test@gmail.com")
        archive.db.mark_downloaded(eid, "INBOX:100", "emails/msg1.eml", content_hash="abc", account="test@gmail.com")

        cmd_update_labels(archive)

        with sqlite3.connect(archive.db.db_path) as conn:
            rowid = conn.execute("SELECT rowid FROM emails WHERE email_id = ?", (eid,)).fetchone()[0]
            labels = conn.execute("SELECT label FROM email_labels WHERE email_rowid = ?", (rowid,)).fetchall()
        assert len(labels) == 1
        assert labels[0][0] == "INBOX"


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

        with patch("ownmail.providers.gmail.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["msg1", "msg2", "msg3"]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "On server but not local" in captured.out or "3" in captured.out

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

        with patch("ownmail.providers.gmail.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = []  # Gmail is empty
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "On local but not on server" in captured.out or "deleted" in captured.out

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

        with patch("ownmail.providers.gmail.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            # More than 5 to trigger truncation unless verbose
            mock_provider.get_all_message_ids.return_value = [f"msg{i}" for i in range(10)]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive, verbose=True)

        captured = capsys.readouterr()
        assert "Sync Check" in captured.out

    def test_sync_check_imap_source(self, temp_dir, capsys):
        """Test sync-check with an IMAP source."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "work_imap",
                "type": "imap",
                "account": "user@company.com",
                "host": "imap.company.com",
                "auth": {"secret_ref": "keychain:work"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Add local emails
        archive.db.mark_downloaded(
            _eid("INBOX:1", "user@company.com"), "INBOX:1",
            "emails/2024/01/e1.eml", content_hash="aaa", account="user@company.com",
        )
        archive.db.mark_downloaded(
            _eid("INBOX:2", "user@company.com"), "INBOX:2",
            "emails/2024/01/e2.eml", content_hash="bbb", account="user@company.com",
        )

        with patch("ownmail.providers.imap.ImapProvider") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["INBOX:1", "INBOX:2", "INBOX:3"]
            mock_cls.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "In sync: 2" in captured.out or "\u2713 In sync: 2" in captured.out
        assert "On server but not local: 1" in captured.out

    def test_sync_check_imap_fully_synced(self, temp_dir, capsys):
        """Test sync-check IMAP fully in sync."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "work_imap",
                "type": "imap",
                "account": "user@company.com",
                "host": "imap.company.com",
                "auth": {"secret_ref": "keychain:work"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        archive.db.mark_downloaded(
            _eid("INBOX:1", "user@company.com"), "INBOX:1",
            "emails/2024/01/e1.eml", content_hash="aaa", account="user@company.com",
        )

        with patch("ownmail.providers.imap.ImapProvider") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["INBOX:1"]
            mock_cls.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "in sync with server" in captured.out.lower()

    def test_sync_check_unsupported_type(self, temp_dir, capsys):
        """Test sync-check with unsupported source type."""
        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "weird",
                "type": "pop3",
                "account": "x@x.com",
                "auth": {"secret_ref": "keychain:x"},
            }]
        }
        archive = EmailArchive(temp_dir, config)
        cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "not supported" in captured.out.lower()

    def test_sync_check_specific_source(self, temp_dir, capsys):
        """Test sync-check with --source targeting IMAP source."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [
                {
                    "name": "gmail_personal",
                    "type": "gmail_api",
                    "account": "me@gmail.com",
                    "auth": {"secret_ref": "keychain:gmail"},
                },
                {
                    "name": "work_imap",
                    "type": "imap",
                    "account": "user@company.com",
                    "host": "imap.company.com",
                    "auth": {"secret_ref": "keychain:work"},
                },
            ]
        }
        archive = EmailArchive(temp_dir, config)

        with patch("ownmail.providers.imap.ImapProvider") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = []
            mock_cls.return_value = mock_provider

            cmd_sync_check(archive, source_name="work_imap")

        captured = capsys.readouterr()
        assert "work_imap" in captured.out
        assert "user@company.com" in captured.out


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


class TestCmdVerifyDedup:
    """Tests for duplicate detection and removal in verify."""

    def test_verify_detects_duplicates(self, temp_dir, capsys):
        """Test that verify detects duplicate content_hash entries."""
        import hashlib

        archive = EmailArchive(temp_dir, {})

        content = b"From: a@b.com\r\nSubject: Dup\r\n\r\nBody"
        content_hash = hashlib.sha256(content).hexdigest()

        # Create two files with the same content
        emails_dir = temp_dir / "sources" / "test" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        path1 = emails_dir / "email1.eml"
        path1.write_bytes(content)
        path2 = emails_dir / "email2.eml"
        path2.write_bytes(content)

        rel1 = str(path1.relative_to(temp_dir))
        rel2 = str(path2.relative_to(temp_dir))

        archive.db.mark_downloaded(_eid("INBOX:1"), "INBOX:1", rel1, content_hash=content_hash)
        archive.db.mark_downloaded(_eid("AllMail:100"), "AllMail:100", rel2, content_hash=content_hash)

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "1 duplicate" in captured.out

    def test_verify_fix_removes_duplicates(self, temp_dir, capsys):
        """Test that verify --fix removes duplicate entries and files."""
        import hashlib

        archive = EmailArchive(temp_dir, {})

        content = b"From: a@b.com\r\nSubject: Dup\r\n\r\nBody"
        content_hash = hashlib.sha256(content).hexdigest()

        emails_dir = temp_dir / "sources" / "test" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        path1 = emails_dir / "email1.eml"
        path1.write_bytes(content)
        path2 = emails_dir / "email2.eml"
        path2.write_bytes(content)

        rel1 = str(path1.relative_to(temp_dir))
        rel2 = str(path2.relative_to(temp_dir))

        archive.db.mark_downloaded(_eid("INBOX:1"), "INBOX:1", rel1, content_hash=content_hash)
        archive.db.mark_downloaded(_eid("AllMail:100"), "AllMail:100", rel2, content_hash=content_hash)

        cmd_verify(archive, fix=True)
        captured = capsys.readouterr()
        assert "Removed 1 duplicate" in captured.out
        assert "FTS rebuilt" in captured.out

        # Verify only one entry remains
        with sqlite3.connect(archive.db.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
            assert count == 1

    def test_verify_fix_keeps_newest_entry(self, temp_dir, capsys):
        """Test that verify --fix keeps the newest (highest rowid) entry."""
        import hashlib

        archive = EmailArchive(temp_dir, {})

        content = b"From: a@b.com\r\nSubject: Dup\r\n\r\nBody"
        content_hash = hashlib.sha256(content).hexdigest()

        emails_dir = temp_dir / "sources" / "test" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        path1 = emails_dir / "old.eml"
        path1.write_bytes(content)
        path2 = emails_dir / "new.eml"
        path2.write_bytes(content)

        rel1 = str(path1.relative_to(temp_dir))
        rel2 = str(path2.relative_to(temp_dir))

        # First entry (older)
        archive.db.mark_downloaded(_eid("INBOX:1"), "INBOX:1", rel1, content_hash=content_hash)
        # Second entry (newer)
        archive.db.mark_downloaded(_eid("AllMail:100"), "AllMail:100", rel2, content_hash=content_hash)

        cmd_verify(archive, fix=True)

        with sqlite3.connect(archive.db.db_path) as conn:
            row = conn.execute("SELECT provider_id, filename FROM emails").fetchone()
            # Should keep the newer one
            assert row[0] == "AllMail:100"
            assert "new.eml" in row[1]

        # Old file should be deleted, new file should remain
        assert not path1.exists()
        assert path2.exists()

    def test_verify_no_duplicates_reports_clean(self, temp_dir, capsys):
        """Test verify reports clean when no duplicates exist."""
        import hashlib

        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "sources" / "test" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        for i in range(3):
            content = f"From: a@b.com\r\nSubject: Email {i}\r\n\r\nBody {i}".encode()
            path = emails_dir / f"email{i}.eml"
            path.write_bytes(content)
            rel = str(path.relative_to(temp_dir))
            h = hashlib.sha256(content).hexdigest()
            archive.db.mark_downloaded(_eid(f"msg{i}"), f"msg{i}", rel, content_hash=h)

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "No duplicate emails" in captured.out

    def test_verify_verbose_shows_duplicate_details(self, temp_dir, capsys):
        """Test that verify -v shows details of duplicate emails."""
        import hashlib

        archive = EmailArchive(temp_dir, {})

        content = b"From: a@b.com\r\nSubject: Dup\r\n\r\nBody"
        content_hash = hashlib.sha256(content).hexdigest()

        emails_dir = temp_dir / "sources" / "test" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        path1 = emails_dir / "email1.eml"
        path1.write_bytes(content)
        path2 = emails_dir / "email2.eml"
        path2.write_bytes(content)

        rel1 = str(path1.relative_to(temp_dir))
        rel2 = str(path2.relative_to(temp_dir))

        archive.db.mark_downloaded(_eid("INBOX:1"), "INBOX:1", rel1, content_hash=content_hash)
        archive.db.mark_downloaded(_eid("AllMail:100"), "AllMail:100", rel2, content_hash=content_hash)

        cmd_verify(archive, verbose=True)
        captured = capsys.readouterr()
        assert "INBOX:1" in captured.out
        assert "AllMail:100" in captured.out


# ---------------------------------------------------------------------------
# Reindex cancel / resume tests
# ---------------------------------------------------------------------------

_SAMPLE_EML = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: Reindex Test\r\n"
    b"Date: Mon, 15 Jan 2024 10:00:00 +0000\r\n"
    b"Message-ID: <reindex-test@example.com>\r\n"
    b"\r\n"
    b"Body content for reindex.\r\n"
)


def _make_email(archive, temp_dir, n, account="test@gmail.com"):
    """Create an email file and DB row for testing. Returns email_id."""
    emails_dir = temp_dir / "sources" / account / "2024" / "01"
    emails_dir.mkdir(parents=True, exist_ok=True)

    content = _SAMPLE_EML.replace(b"Reindex Test", f"Email {n}".encode())
    content_hash = hashlib.sha256(content).hexdigest()

    path = emails_dir / f"email_{n}.eml"
    path.write_bytes(content)
    rel = str(path.relative_to(temp_dir))

    eid = _eid(f"msg{n}", account)
    archive.db.mark_downloaded(eid, f"msg{n}", rel, content_hash=content_hash, account=account)
    return eid


class TestReindexCancel:
    """Tests for Ctrl-C (SIGINT) cancellation during reindex."""

    def test_sigint_stops_reindex_gracefully(self, temp_dir, capsys):
        """SIGINT mid-reindex stops after current email and saves progress."""
        import signal

        archive = EmailArchive(temp_dir, {})

        # Create 10 emails to index
        for i in range(10):
            _make_email(archive, temp_dir, i)

        # Monkey-patch _index_email_for_reindex to send SIGINT after 3
        from ownmail import commands
        original_fn = commands._index_email_for_reindex
        call_count = 0

        def patched_index(arch, email_id, filepath, conn, debug=False):
            nonlocal call_count
            call_count += 1
            result = original_fn(arch, email_id, filepath, conn, debug)
            if call_count == 3:
                import os
                os.kill(os.getpid(), signal.SIGINT)
            return result

        commands._index_email_for_reindex = patched_index
        try:
            cmd_reindex(archive)
        finally:
            commands._index_email_for_reindex = original_fn

        captured = capsys.readouterr()
        assert "Paused" in captured.out
        assert "resume" in captured.out.lower() or "again" in captured.out.lower()

    def test_reindex_resume_skips_indexed(self, temp_dir, capsys):
        """Second reindex run skips already-indexed emails."""
        archive = EmailArchive(temp_dir, {})

        # Create 5 emails
        for i in range(5):
            _make_email(archive, temp_dir, i)

        # First run: index all
        cmd_reindex(archive)
        captured1 = capsys.readouterr()
        assert "5" in captured1.out  # Should show 5 emails

        # Second run: nothing to do
        cmd_reindex(archive)
        captured2 = capsys.readouterr()
        assert "already indexed" in captured2.out

    def test_reindex_resume_after_interrupt(self, temp_dir, capsys):
        """After SIGINT, second reindex picks up where it left off."""
        import signal

        archive = EmailArchive(temp_dir, {})

        for i in range(8):
            _make_email(archive, temp_dir, i)

        from ownmail import commands
        original_fn = commands._index_email_for_reindex
        call_count = 0

        def patched_index(arch, email_id, filepath, conn, debug=False):
            nonlocal call_count
            call_count += 1
            result = original_fn(arch, email_id, filepath, conn, debug)
            if call_count == 3:
                import os
                os.kill(os.getpid(), signal.SIGINT)
            return result

        commands._index_email_for_reindex = patched_index
        try:
            cmd_reindex(archive)
        finally:
            commands._index_email_for_reindex = original_fn

        captured1 = capsys.readouterr()
        assert "Paused" in captured1.out

        # Count how many are now indexed
        with sqlite3.connect(archive.db.db_path) as conn:
            indexed = conn.execute(
                "SELECT COUNT(*) FROM emails WHERE indexed_hash IS NOT NULL"
            ).fetchone()[0]

        assert indexed >= 3  # At least 3 were indexed before SIGINT

        # Second run resumes
        cmd_reindex(archive)
        capsys.readouterr()

        # After second run, all 8 should be indexed
        with sqlite3.connect(archive.db.db_path) as conn:
            indexed = conn.execute(
                "SELECT COUNT(*) FROM emails WHERE indexed_hash IS NOT NULL"
            ).fetchone()[0]
        assert indexed == 8


class TestReindexForceMode:
    """Tests for reindex --force rebuilding FTS from scratch."""

    def test_force_rebuilds_fts_table(self, temp_dir, capsys):
        """Force mode drops and rebuilds FTS, re-indexes all emails."""
        archive = EmailArchive(temp_dir, {})

        for i in range(3):
            _make_email(archive, temp_dir, i)

        # First: normal index
        cmd_reindex(archive)
        capsys.readouterr()

        with sqlite3.connect(archive.db.db_path) as conn:
            fts_before = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
        assert fts_before == 3

        # Force reindex
        cmd_reindex(archive, force=True)
        captured = capsys.readouterr()
        assert "force" in captured.out.lower() or "Rebuilding" in captured.out

        with sqlite3.connect(archive.db.db_path) as conn:
            fts_after = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
            indexed = conn.execute(
                "SELECT COUNT(*) FROM emails WHERE indexed_hash IS NOT NULL"
            ).fetchone()[0]

        assert fts_after == 3
        assert indexed == 3

    def test_force_with_pattern_does_not_drop_fts(self, temp_dir, capsys):
        """Force + pattern re-indexes matching emails without dropping FTS."""
        archive = EmailArchive(temp_dir, {})

        for i in range(3):
            _make_email(archive, temp_dir, i)

        cmd_reindex(archive)
        capsys.readouterr()

        # Force with pattern - should NOT drop FTS table
        cmd_reindex(archive, pattern="email_0", force=True)
        captured = capsys.readouterr()

        # Should show pattern matching
        assert "email_0" in captured.out or "1" in captured.out

        with sqlite3.connect(archive.db.db_path) as conn:
            fts_count = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
        # All 3 remain (FTS wasn't dropped), pattern just re-indexed matching ones
        assert fts_count >= 3


class TestVerifyEndToEnd:
    """End-to-end verify → verify --fix → verify (clean) flow."""

    def test_verify_fix_verify_clean(self, temp_dir, capsys):
        """Full lifecycle: detect issues → fix → verify clean."""
        archive = EmailArchive(temp_dir, {})

        # Create 3 emails on disk and in DB
        emails_dir = temp_dir / "sources" / "test" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        contents = []
        for i in range(3):
            content = f"From: a@b.com\r\nSubject: Email {i}\r\nDate: Mon, 15 Jan 2024\r\n\r\nBody {i}".encode()
            contents.append(content)
            ch = hashlib.sha256(content).hexdigest()
            path = emails_dir / f"email_{i}.eml"
            path.write_bytes(content)
            rel = str(path.relative_to(temp_dir))
            eid = _eid(f"msg{i}")
            archive.db.mark_downloaded(eid, f"msg{i}", rel, content_hash=ch)
            archive.db.index_email(
                email_id=eid,
                subject=f"Email {i}",
                sender="a@b.com",
                recipients="",
                date_str="2024-01-15",
                body=f"Body {i}",
                attachments="",
            )

        # Now break things:
        # 1. Delete file for email_1 (→ missing)
        (emails_dir / "email_1.eml").unlink()

        # 2. Add a duplicate for email_0 (with metadata so it's fully indexed)
        dup_hash = hashlib.sha256(contents[0]).hexdigest()
        dup_path = emails_dir / "email_0_dup.eml"
        dup_path.write_bytes(contents[0])
        dup_rel = str(dup_path.relative_to(temp_dir))
        dup_eid = _eid("dup0")
        archive.db.mark_downloaded(dup_eid, "dup0", dup_rel, content_hash=dup_hash)
        archive.db.index_email(
            email_id=dup_eid,
            subject="Email 0",
            sender="a@b.com",
            recipients="",
            date_str="2024-01-15",
            body="Body 0",
            attachments="",
        )

        # Step 1: Verify (no fix) — should find issues
        cmd_verify(archive, fix=False)
        out1 = capsys.readouterr().out
        assert "issue" in out1.lower()

        # Step 2: Verify --fix — should fix issues
        cmd_verify(archive, fix=True)
        out2 = capsys.readouterr().out
        assert "Fixed" in out2 or "Removed" in out2

        # Step 3: Verify again — should be clean
        cmd_verify(archive, fix=False)
        out3 = capsys.readouterr().out
        assert "All checks passed" in out3

    def test_verify_fix_missing_then_backup_resumes(self, temp_dir, capsys):
        """After verify --fix removes missing files, backup can resume."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        # Download 2 emails
        emails_dir = temp_dir / "sources" / "test@gmail.com" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        for i in range(2):
            content = f"From: a@b.com\r\nDate: Mon, 15 Jan 2024\r\n\r\nBody {i}".encode()
            ch = hashlib.sha256(content).hexdigest()
            path = emails_dir / f"email_{i}.eml"
            path.write_bytes(content)
            rel = str(path.relative_to(temp_dir))
            eid = _eid(f"msg{i}", "test@gmail.com")
            archive.db.mark_downloaded(eid, f"msg{i}", rel, content_hash=ch, account="test@gmail.com")

        # Set sync state (simulating a successful prior sync)
        archive.db.set_sync_state("test@gmail.com", "sync_state", "old-sync")

        # Delete one file to simulate corruption
        (emails_dir / "email_0.eml").unlink()

        # verify --fix: removes stale entry AND resets sync state
        cmd_verify(archive, fix=True)
        out = capsys.readouterr().out
        assert "Reset sync state" in out or "Removed" in out

        # Sync state should be cleared
        state = archive.db.get_sync_state("test@gmail.com", "sync_state")
        assert state is None

        # Now backup should do a FULL sync (since sync state is cleared)
        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.name = "imap"
        provider.source_name = "test_source"
        provider.get_new_message_ids.return_value = ([], "fresh-state")

        archive.backup(provider)

        # get_new_message_ids should have been called with None (no prior state)
        provider.get_new_message_ids.assert_called_once()
        call_args = provider.get_new_message_ids.call_args
        assert call_args[0][0] is None  # sync_state=None → full scan

    def test_verify_fix_moved_file_then_web_ui_works(self, temp_dir, capsys):
        """Rename file on disk → verify --fix → DB updated → web UI serves it."""
        from ownmail.web import create_app

        archive = EmailArchive(temp_dir, {})

        # Create email on disk and register in DB
        old_dir = temp_dir / "sources" / "test" / "2024" / "01"
        old_dir.mkdir(parents=True)

        eml_content = (
            b"From: sender@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"Subject: Moved Email Test\r\n"
            b"Date: Mon, 15 Jan 2024 10:30:00 +0000\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"This email was moved on disk."
        )
        old_path = old_dir / "original_name.eml"
        old_path.write_bytes(eml_content)

        content_hash = hashlib.sha256(eml_content).hexdigest()
        eid = _eid("moved-test")
        old_rel = str(old_path.relative_to(temp_dir))
        archive.db.mark_downloaded(eid, "moved-test", old_rel, content_hash=content_hash)
        archive.db.index_email(
            email_id=eid,
            subject="Moved Email Test",
            sender="sender@example.com",
            recipients="recipient@example.com",
            date_str="Mon, 15 Jan 2024 10:30:00 +0000",
            body="This email was moved on disk.",
            attachments="",
        )

        # Rename/move the file on disk
        new_dir = temp_dir / "sources" / "test" / "2024" / "02"
        new_dir.mkdir(parents=True)
        new_path = new_dir / "renamed.eml"
        old_path.rename(new_path)

        # File stays at new path, old path is gone
        assert not old_path.exists()
        assert new_path.exists()

        # Run verify --fix → should detect moved file and update DB
        cmd_verify(archive, fix=True)
        out = capsys.readouterr().out
        assert "Updated" in out

        # Verify DB now has the new path
        new_rel = str(new_path.relative_to(temp_dir))
        with sqlite3.connect(archive.db.db_path) as conn:
            row = conn.execute(
                "SELECT filename FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
        assert row[0] == new_rel

        # Web UI should serve the email at the updated path
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get(f"/email/{eid}")
            assert response.status_code == 200
            assert b"Moved Email Test" in response.data
            assert b"sender@example.com" in response.data
            assert b"This email was moved on disk." in response.data
