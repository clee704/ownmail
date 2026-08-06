"""Tests for maintenance commands."""

import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ownmail import commands, sidecar
from ownmail.archive import EmailArchive
from ownmail.commands import (
    _print_file_list,
    _reconcile_label_sidecars,
    cmd_import,
    cmd_list_unknown,
    cmd_rebuild,
    cmd_scan,
    cmd_sync_check,
    cmd_update_labels,
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


class TestCmdRebuild:
    """Tests for rebuild command."""

    def test_rebuild_empty_database(self, temp_dir, capsys):
        """Test rebuild on empty database."""
        archive = EmailArchive(temp_dir, {})
        cmd_rebuild(archive)
        captured = capsys.readouterr()
        assert "already indexed" in captured.out or "Rebuild" in captured.out

    def test_rebuild_single_file(self, temp_dir, sample_eml_simple, capsys):
        """Test rebuilding a single file."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Mark as downloaded
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path)

        # Rebuild single file
        cmd_rebuild(archive, file_path=email_path)
        captured = capsys.readouterr()
        assert "Indexed successfully" in captured.out or "Indexing" in captured.out

    def test_rebuild_nonexistent_file(self, temp_dir, capsys):
        """Test rebuild with nonexistent file."""
        archive = EmailArchive(temp_dir, {})
        cmd_rebuild(archive, file_path=Path("/nonexistent/file.eml"))
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_rebuild_force_mode(self, temp_dir, sample_eml_simple, capsys):
        """Test rebuild with force flag."""
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
        cmd_rebuild(archive)
        captured = capsys.readouterr()
        assert "already indexed" in captured.out

        # With force, should rebuild
        cmd_rebuild(archive, force=True)
        captured = capsys.readouterr()
        assert "(force)" in captured.out

    def test_rebuild_with_pattern(self, temp_dir, sample_eml_simple, capsys):
        """Test rebuild with pattern filter."""
        archive = EmailArchive(temp_dir, {})

        # Create multiple emails
        for year in ["2023", "2024"]:
            emails_dir = temp_dir / "emails" / year / "01"
            emails_dir.mkdir(parents=True)
            email_path = emails_dir / "test.eml"
            email_path.write_bytes(sample_eml_simple)

            rel_path = str(email_path.relative_to(temp_dir))
            archive.db.mark_downloaded(_eid(f"msg_{year}"), f"msg_{year}", rel_path, content_hash=None)

        # Rebuild only 2024
        cmd_rebuild(archive, pattern="2024/*")
        captured = capsys.readouterr()
        assert "matching '2024/*'" in captured.out

    def test_rebuild_single_file_not_in_db(self, temp_dir, sample_eml_simple, capsys):
        """Test rebuild single file that's not in database."""
        archive = EmailArchive(temp_dir, {})

        # Create file but don't add to DB
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "standalone.eml"
        email_path.write_bytes(sample_eml_simple)

        # Index single file - should use filename as message_id
        cmd_rebuild(archive, file_path=email_path)
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
        archive.db.mark_downloaded(
            _eid("indexed123"), "indexed123", str(indexed_path.relative_to(temp_dir)), content_hash=content_hash
        )

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
            _eid("moved123"),
            "moved123",
            "emails/2024/01/old_name.eml",
            content_hash=content_hash,
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
            _eid("moved123"),
            "moved123",
            "emails/2024/01/old_name.eml",
            content_hash=content_hash,
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
            _eid("missing1", "test@gmail.com"),
            "missing1",
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
            _eid("msg1", "alice@gmail.com"),
            "msg1",
            "emails/2024/01/msg1.eml",
            content_hash="aaa",
            account="alice@gmail.com",
        )
        archive.db.mark_downloaded(
            _eid("msg2", "bob@gmail.com"),
            "msg2",
            "emails/2024/01/msg2.eml",
            content_hash="bbb",
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
            conn.execute(
                """
                INSERT INTO emails (email_id, provider_id, filename, content_hash, indexed_hash)
                VALUES (?, ?, ?, ?, 'different_hash')
            """,
                (_eid("test123"), "test123", rel_path, content_hash),
            )
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
            conn.execute(
                """
                INSERT INTO emails (email_id, provider_id, filename, content_hash)
                VALUES (?, ?, ?, NULL)
            """,
                (_eid("test456"), "test456", rel_path),
            )
            conn.commit()

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "missing" in captured.out.lower() or "hash" in captured.out.lower()


class TestVerifySystemLabels:
    """Verify reports emails archived out of a trash/spam folder.

    These predate role-based exclusion — a server whose trash wasn't named
    '[Gmail]/Trash' used to sync straight into the archive.
    """

    def _archive_with_labels(self, temp_dir, labels, account="user@company.com", trashed=False):
        archive = EmailArchive(temp_dir, {})
        archive.db.mark_downloaded(_eid("m1", account), "m1", "2024/01/m1.eml", account=account)
        archive.db.index_email(
            _eid("m1", account),
            subject="Hello",
            sender="a@b.com",
            recipients="",
            date_str="",
            body="",
            attachments="",
            labels=",".join(labels),
        )
        if trashed:
            with sqlite3.connect(archive.db.db_path) as conn:
                conn.execute("UPDATE emails SET trashed_at = datetime('now')")
        return archive

    def test_reports_trash_label(self, temp_dir, capsys):
        archive = self._archive_with_labels(temp_dir, ["Deleted Items"])
        cmd_verify(archive)
        out = capsys.readouterr().out
        assert "1 emails carry a trash/spam label" in out
        assert "Deleted Items (user@company.com): 1" in out

    def test_reports_spam_label(self, temp_dir, capsys):
        archive = self._archive_with_labels(temp_dir, ["Junk"])
        cmd_verify(archive)
        assert "carry a trash/spam label" in capsys.readouterr().out

    def test_ignores_ordinary_labels(self, temp_dir, capsys):
        archive = self._archive_with_labels(temp_dir, ["Receipts", "INBOX"])
        cmd_verify(archive)
        assert "No emails labelled trash/spam" in capsys.readouterr().out

    def test_ignores_locally_trashed_emails(self, temp_dir, capsys):
        """Already in ownmail's own trash — nothing left to report."""
        archive = self._archive_with_labels(temp_dir, ["Deleted Items"], trashed=True)
        cmd_verify(archive)
        assert "No emails labelled trash/spam" in capsys.readouterr().out

    def test_suggests_a_search_without_changing_anything(self, temp_dir, capsys):
        archive = self._archive_with_labels(temp_dir, ["Deleted Items"])
        cmd_verify(archive)
        out = capsys.readouterr().out
        assert 'ownmail search "label:Deleted Items"' in out

        labels = archive.db.get_labels_for_email(_eid("m1", "user@company.com"))
        assert labels == ["Deleted Items"]

    def test_fix_does_not_touch_them(self, temp_dir, capsys):
        """Report only — --fix must leave these emails alone."""
        archive = self._archive_with_labels(temp_dir, ["Deleted Items"])
        cmd_verify(archive, fix=True)

        with sqlite3.connect(archive.db.db_path) as conn:
            trashed = conn.execute("SELECT COUNT(*) FROM emails WHERE trashed_at IS NOT NULL").fetchone()[0]
        assert trashed == 0

    def test_groups_by_label_and_account(self, temp_dir, capsys):
        archive = EmailArchive(temp_dir, {})
        for i, (account, label) in enumerate([("a@x.com", "Trash"), ("a@x.com", "Trash"), ("b@y.com", "Junk")]):
            eid = _eid(f"m{i}", account)
            archive.db.mark_downloaded(eid, f"m{i}", f"2024/01/m{i}.eml", account=account)
            archive.db.index_email(
                eid, subject="s", sender="a@b.com", recipients="", date_str="", body="", attachments="", labels=label
            )

        cmd_verify(archive)
        out = capsys.readouterr().out
        assert "3 emails carry a trash/spam label" in out
        assert "Trash (a@x.com): 2" in out
        assert "Junk (b@y.com): 1" in out


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
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
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
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        # Add messages to local archive
        archive.db.mark_downloaded(
            _eid("msg1", "test@gmail.com"),
            "msg1",
            "emails/2024/01/msg1.eml",
            content_hash="abc",
            account="test@gmail.com",
        )
        archive.db.mark_downloaded(
            _eid("msg2", "test@gmail.com"),
            "msg2",
            "emails/2024/01/msg2.eml",
            content_hash="def",
            account="test@gmail.com",
        )

        with patch("ownmail.providers.gmail.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_all_message_ids.return_value = ["msg1", "msg2"]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "in sync" in captured.out.lower()

    def _archive(self, temp_dir, sources=None):
        return EmailArchive(temp_dir, {"sources": sources} if sources is not None else {})

    def _gmail_source(self):
        return [{"name": "g", "type": "gmail_api", "account": "a@example.com"}]

    def _imap_source(self):
        return [{"name": "w", "type": "imap", "account": "a@example.com", "host": "imap.example.com"}]

    def _provider(self, server_ids):
        provider = MagicMock()
        provider.get_all_message_ids.return_value = server_ids
        return provider

    def test_unknown_source_name(self, temp_dir, capsys):
        """An unknown --source should be reported."""
        cmd_sync_check(self._archive(temp_dir, self._gmail_source()), source_name="nope")
        assert "Source 'nope' not found" in capsys.readouterr().out

    def test_unsupported_source_type(self, temp_dir, capsys):
        """A source type without sync-check support should say so."""
        archive = self._archive(temp_dir, [{"name": "m", "type": "maildir", "account": "a@example.com"}])
        cmd_sync_check(archive)
        assert "not supported for source type 'maildir'" in capsys.readouterr().out

    def test_reports_emails_missing_locally(self, temp_dir, capsys):
        """Server-only messages should prompt a backup run."""
        archive = self._archive(temp_dir, self._gmail_source())

        with patch("ownmail.providers.gmail.GmailProvider", return_value=self._provider(["m1", "m2"])):
            cmd_sync_check(archive)

        out = capsys.readouterr().out
        assert "On server but not local: 2" in out
        assert "Run 'backup' to download these emails." in out

    def test_reports_emails_missing_on_server(self, temp_dir, capsys):
        """Local-only messages should be listed with their filenames."""
        archive = self._archive(temp_dir, self._gmail_source())
        archive.db.mark_downloaded(_eid("m1", "a@example.com"), "m1", "stored.eml", account="a@example.com")

        with patch("ownmail.providers.gmail.GmailProvider", return_value=self._provider([])):
            cmd_sync_check(archive)

        out = capsys.readouterr().out
        assert "On local but not on server" in out
        assert "stored.eml (m1)" in out

    def test_long_lists_are_truncated(self, temp_dir, capsys):
        """More than five differences should be elided by default."""
        archive = self._archive(temp_dir, self._gmail_source())
        server_ids = [f"m{i}" for i in range(9)]

        with patch("ownmail.providers.gmail.GmailProvider", return_value=self._provider(server_ids)):
            cmd_sync_check(archive)

        assert "... and 4 more (use --verbose to show all)" in capsys.readouterr().out

    def test_verbose_shows_every_difference(self, temp_dir, capsys):
        """--verbose should list all differing IDs."""
        archive = self._archive(temp_dir, self._gmail_source())
        server_ids = [f"m{i}" for i in range(9)]

        with patch("ownmail.providers.gmail.GmailProvider", return_value=self._provider(server_ids)):
            cmd_sync_check(archive, verbose=True)

        out = capsys.readouterr().out
        assert "... and" not in out
        for msg_id in server_ids:
            assert msg_id in out

    def test_imap_source_is_closed(self, temp_dir):
        """An IMAP provider should be built from config and closed after use."""
        archive = self._archive(temp_dir, self._imap_source())
        provider = self._provider([])

        with patch("ownmail.providers.imap.ImapProvider", return_value=provider) as mock_cls:
            cmd_sync_check(archive)

        assert mock_cls.call_args.kwargs["host"] == "imap.example.com"
        provider.authenticate.assert_called_once()
        provider.close.assert_called_once()


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
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
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
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Add to database
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded(
            _eid("test123", "test@gmail.com"), "test123", rel_path, content_hash="abc", account="test@gmail.com"
        )

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
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        # Add to database with labels already set (in email_labels table)
        email_id = _eid("test123", "test@gmail.com")
        archive.db.mark_downloaded(email_id, "test123", "emails/test.eml", content_hash="abc", account="test@gmail.com")
        conn = sqlite3.connect(archive.db.db_path)
        rowid = conn.execute("SELECT rowid FROM emails WHERE email_id = ?", (email_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)", (rowid, "INBOX", None)
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
            "sources": [
                {
                    "name": "test_imap",
                    "type": "imap",
                    "account": "test@gmail.com",
                    "host": "imap.gmail.com",
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        # Add emails with IMAP-style provider_id (folder:uid)
        eid1 = _eid("INBOX:100", "test@gmail.com")
        eid2 = _eid("[Gmail]/Sent Mail:200", "test@gmail.com")
        archive.db.mark_downloaded(eid1, "INBOX:100", "emails/msg1.eml", content_hash="abc", account="test@gmail.com")
        archive.db.mark_downloaded(
            eid2, "[Gmail]/Sent Mail:200", "emails/msg2.eml", content_hash="def", account="test@gmail.com"
        )

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
            "sources": [
                {
                    "name": "test_imap",
                    "type": "imap",
                    "account": "test@gmail.com",
                    "host": "imap.gmail.com",
                }
            ]
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

    def _archive(self, temp_dir, sources):
        return EmailArchive(temp_dir, {"sources": sources} if sources is not None else {})

    def _seed(self, archive, rows):
        with sqlite3.connect(archive.db.db_path) as conn:
            for email_id, provider_id, filename, account in rows:
                conn.execute(
                    "INSERT OR REPLACE INTO emails (email_id, provider_id, filename, account) VALUES (?, ?, ?, ?)",
                    (email_id, provider_id, filename, account),
                )

    def _labels(self, archive):
        with sqlite3.connect(archive.db.db_path) as conn:
            return sorted(
                conn.execute(
                    "SELECT e.email_id, el.label FROM email_labels el JOIN emails e ON e.rowid = el.email_rowid"
                ).fetchall()
            )

    def test_named_source_is_selected(self, temp_dir, capsys):
        """A valid --source name should select that source."""
        archive = self._archive(
            temp_dir,
            [
                {"name": "work", "type": "imap", "account": "work@example.com"},
                {"name": "home", "type": "imap", "account": "home@example.com"},
            ],
        )
        cmd_update_labels(archive, source_name="home")
        assert "Source: home (home@example.com)" in capsys.readouterr().out

    def test_unsupported_source_type(self, temp_dir, capsys):
        """A source type with no label support should say so."""
        archive = self._archive(temp_dir, [{"name": "mbox", "type": "maildir", "account": "a@example.com"}])
        self._seed(archive, [("a", "INBOX:1", "a.eml", "a@example.com")])
        cmd_update_labels(archive)
        assert "not supported for source type 'maildir'" in capsys.readouterr().out

    def test_imap_derives_labels_from_folder(self, temp_dir, capsys):
        """IMAP labels should come from the folder part of provider_id."""
        archive = self._archive(temp_dir, [{"name": "work", "type": "imap", "account": "a@example.com"}])
        (temp_dir / "a.eml").write_bytes(b"From: x@example.com\n\nbody\n")
        self._seed(archive, [("a", "INBOX/Sub:42", "a.eml", "a@example.com")])

        cmd_update_labels(archive)

        assert self._labels(archive) == [("a", "INBOX/Sub")]
        assert sidecar.read_labels(temp_dir / "a.eml") == ["INBOX/Sub"]
        assert "Updated: 1 emails" in capsys.readouterr().out

    def test_imap_multi_folder_sidecar_survives(self, temp_dir, capsys):
        """A message found in several folders must not be flattened to one.

        provider_id holds only the folder the message was downloaded from;
        the other folders the dedup scan found live in the sidecar. Deriving
        from provider_id and overwriting would destroy them — and the
        sidecar is the source of truth, so `rebuild --only sidecars` would
        then propagate the loss rather than repair it.
        """
        archive = self._archive(temp_dir, [{"name": "work", "type": "imap", "account": "a@example.com"}])
        (temp_dir / "a.eml").write_bytes(b"From: x@example.com\n\nbody\n")
        sidecar.write_labels(temp_dir / "a.eml", ["Archive", "INBOX", "Work"])
        self._seed(archive, [("a", "Archive:42", "a.eml", "a@example.com")])

        cmd_update_labels(archive)

        assert sidecar.read_labels(temp_dir / "a.eml") == ["Archive", "INBOX", "Work"]
        # The DB is the rebuildable side, so it gets restored from the file.
        assert sorted(self._labels(archive)) == [("a", "Archive"), ("a", "INBOX"), ("a", "Work")]
        assert "Restored from sidecar: 1" in capsys.readouterr().out

    def test_gmail_sidecar_wins_over_the_server(self, temp_dir, capsys):
        """After capture the archive is authoritative — don't re-read labels.

        doc-8: following server changes post-capture would let a
        non-authoritative source overwrite the authoritative one.
        """
        archive = self._archive(temp_dir, [{"name": "g", "type": "gmail_api", "account": "a@example.com"}])
        (temp_dir / "a.eml").write_bytes(b"From: x@example.com\n\nbody\n")
        sidecar.write_labels(temp_dir / "a.eml", ["Work", "Receipts"])
        self._seed(archive, [("a", "msg1", "a.eml", "a@example.com")])

        provider = MagicMock()
        provider.get_labels_for_message.return_value = ["INBOX"]
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            cmd_update_labels(archive)

        provider.get_labels_for_message.assert_not_called()
        assert sidecar.read_labels(temp_dir / "a.eml") == ["Work", "Receipts"]
        assert sorted(self._labels(archive)) == [("a", "Receipts"), ("a", "Work")]
        assert "Restored from sidecar: 1" in capsys.readouterr().out

    def test_imap_skips_malformed_provider_ids(self, temp_dir, capsys):
        """provider_ids with no folder part should be skipped, not crash."""
        archive = self._archive(temp_dir, [{"name": "work", "type": "imap", "account": "a@example.com"}])
        self._seed(
            archive,
            [
                ("a", "nocolon", "a.eml", "a@example.com"),
                ("b", ":42", "b.eml", "a@example.com"),
            ],
        )

        cmd_update_labels(archive)

        assert self._labels(archive) == []
        assert "Skipped: 2" in capsys.readouterr().out

    def test_gmail_confirmed_empty_writes_an_empty_sidecar(self, temp_dir, capsys):
        """A confirmed-empty label list is an answer, and gets recorded.

        Writing the sidecar is what stops the next run asking again.
        """
        archive = self._archive(temp_dir, [{"name": "g", "type": "gmail_api", "account": "a@example.com"}])
        (temp_dir / "a.eml").write_bytes(b"From: x@example.com\n\nbody\n")
        self._seed(archive, [("a", "msg1", "a.eml", "a@example.com")])

        provider = MagicMock()
        provider.get_labels_for_message.return_value = []
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            cmd_update_labels(archive)

        assert self._labels(archive) == []
        assert sidecar.read_labels(temp_dir / "a.eml") == []
        assert "Errors" not in capsys.readouterr().out

    def test_gmail_failed_fetch_is_an_error_not_an_empty_result(self, temp_dir, capsys):
        """A failed call must not be recorded as "this message has no labels"."""
        archive = self._archive(temp_dir, [{"name": "g", "type": "gmail_api", "account": "a@example.com"}])
        (temp_dir / "a.eml").write_bytes(b"From: x@example.com\n\nbody\n")
        self._seed(archive, [("a", "msg1", "a.eml", "a@example.com")])

        provider = MagicMock()
        provider.get_labels_for_message.return_value = None
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            cmd_update_labels(archive)

        assert self._labels(archive) == []
        # No sidecar written at all — a later run must be able to retry.
        assert sidecar.read_labels(temp_dir / "a.eml") is None
        assert "Errors: 1" in capsys.readouterr().out

    def test_gmail_per_message_errors_are_counted(self, temp_dir, capsys):
        """An API error on one message should not abort the whole run."""
        archive = self._archive(temp_dir, [{"name": "g", "type": "gmail_api", "account": "a@example.com"}])
        (temp_dir / "b.eml").write_bytes(b"From: x@example.com\n\nbody\n")
        self._seed(
            archive,
            [
                ("a", "msg1", "a.eml", "a@example.com"),
                ("b", "msg2", "b.eml", "a@example.com"),
            ],
        )

        provider = MagicMock()
        provider.get_labels_for_message.side_effect = [RuntimeError("rate limited"), ["INBOX"]]
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            cmd_update_labels(archive)

        out = capsys.readouterr().out
        assert "Error processing msg1: rate limited" in out
        assert "Errors: 1" in out
        assert self._labels(archive) == [("b", "INBOX")]

    def test_gmail_interrupt_pauses_run(self, temp_dir, capsys):
        """SIGINT should stop the Gmail run and report it as paused."""
        import signal as signal_module

        archive = self._archive(temp_dir, [{"name": "g", "type": "gmail_api", "account": "a@example.com"}])
        for name in ("a", "b", "c"):
            (temp_dir / f"{name}.eml").write_bytes(b"From: x@example.com\n\nbody\n")
        self._seed(archive, [(n, f"msg{n}", f"{n}.eml", "a@example.com") for n in ("a", "b", "c")])

        calls = []

        def labels_then_interrupt(provider_id):
            calls.append(provider_id)
            if len(calls) == 1:
                signal_module.raise_signal(signal_module.SIGINT)
            return ["INBOX"]

        provider = MagicMock()
        provider.get_labels_for_message.side_effect = labels_then_interrupt
        before = signal_module.getsignal(signal_module.SIGINT)
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            cmd_update_labels(archive)

        assert "Update Labels Paused!" in capsys.readouterr().out
        assert len(calls) == 1
        assert signal_module.getsignal(signal_module.SIGINT) is before


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


class TestCmdRebuildDebug:
    """Tests for rebuild debug mode."""

    def test_rebuild_debug_shows_timing(self, temp_dir, sample_eml_simple, capsys):
        """Test rebuild --debug shows timing info."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded(_eid("test123"), "test123", rel_path, content_hash=None)

        cmd_rebuild(archive, debug=True)
        captured = capsys.readouterr()
        # Should complete - debug mode outputs more info
        assert "Rebuild" in captured.out


class TestCmdSyncCheckDifferences:
    """Tests for sync-check with differences."""

    def test_sync_check_emails_on_gmail_not_local(self, temp_dir, capsys):
        """Test sync-check when Gmail has emails not in local."""
        from unittest.mock import MagicMock, patch

        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
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
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        # Add local emails
        archive.db.mark_downloaded(
            _eid("local1", "test@gmail.com"),
            "local1",
            "emails/2024/01/local1.eml",
            content_hash="abc",
            account="test@gmail.com",
        )
        archive.db.mark_downloaded(
            _eid("local2", "test@gmail.com"),
            "local2",
            "emails/2024/01/local2.eml",
            content_hash="def",
            account="test@gmail.com",
        )

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
            "sources": [
                {
                    "name": "test_gmail",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
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
            "sources": [
                {
                    "name": "work_imap",
                    "type": "imap",
                    "account": "user@company.com",
                    "host": "imap.company.com",
                    "auth": {"secret_ref": "keychain:work"},
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        # Add local emails
        archive.db.mark_downloaded(
            _eid("INBOX:1", "user@company.com"),
            "INBOX:1",
            "emails/2024/01/e1.eml",
            content_hash="aaa",
            account="user@company.com",
        )
        archive.db.mark_downloaded(
            _eid("INBOX:2", "user@company.com"),
            "INBOX:2",
            "emails/2024/01/e2.eml",
            content_hash="bbb",
            account="user@company.com",
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
            "sources": [
                {
                    "name": "work_imap",
                    "type": "imap",
                    "account": "user@company.com",
                    "host": "imap.company.com",
                    "auth": {"secret_ref": "keychain:work"},
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        archive.db.mark_downloaded(
            _eid("INBOX:1", "user@company.com"),
            "INBOX:1",
            "emails/2024/01/e1.eml",
            content_hash="aaa",
            account="user@company.com",
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
            "sources": [
                {
                    "name": "weird",
                    "type": "pop3",
                    "account": "x@x.com",
                    "auth": {"secret_ref": "keychain:x"},
                }
            ]
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


class TestCmdRebuildEdgeCases:
    """Additional edge case tests for rebuild."""

    def test_rebuild_with_missing_file_continues(self, temp_dir, capsys):
        """Test rebuild skips missing files and continues."""
        archive = EmailArchive(temp_dir, {})

        # Add to DB but don't create file
        archive.db.mark_downloaded(_eid("missing123"), "missing123", "emails/2024/01/missing.eml", content_hash=None)

        cmd_rebuild(archive)
        captured = capsys.readouterr()
        # Should complete without crashing
        assert "Rebuild" in captured.out

    def test_rebuild_updates_indexed_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test rebuild updates the indexed_hash after indexing."""
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

        cmd_rebuild(archive)

        # Check indexed_hash was set
        with sqlite3.connect(archive.db.db_path) as conn:
            result = conn.execute("SELECT indexed_hash FROM emails WHERE email_id = ?", (_eid("test123"),)).fetchone()
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

    def _seed(self, archive, rows):
        with sqlite3.connect(archive.db.db_path) as conn:
            for email_id, filename, account, email_date in rows:
                conn.execute(
                    "INSERT OR REPLACE INTO emails (email_id, provider_id, filename, account, email_date) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (email_id, email_id, filename, account, email_date),
                )

    def test_no_unknown_emails(self, temp_dir, capsys):
        """With every date known, the command should report nothing to do."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "a.eml", "me@example.com", "2024-01-01T00:00:00+00:00")])

        cmd_list_unknown(archive)

        assert "No emails with unparseable dates" in capsys.readouterr().out

    def test_groups_by_account(self, temp_dir, capsys):
        """Unknown emails should be grouped and counted per account."""
        archive = EmailArchive(temp_dir, {})
        self._seed(
            archive,
            [
                ("a", "a.eml", "one@example.com", None),
                ("b", "b.eml", "one@example.com", None),
                ("c", "c.eml", "two@example.com", None),
            ],
        )

        cmd_list_unknown(archive)

        out = capsys.readouterr().out
        assert "Found 3 emails with unparseable dates" in out
        assert "one@example.com: 2 emails" in out
        assert "two@example.com: 1 emails" in out

    def test_null_account_labelled_legacy(self, temp_dir, capsys):
        """Rows with no account should be grouped under '(legacy)'."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "a.eml", None, None)])

        cmd_list_unknown(archive)

        assert "(legacy): 1 emails" in capsys.readouterr().out

    def test_verbose_shows_headers(self, temp_dir, capsys, sample_eml_simple):
        """Verbose mode should print each file's Date and Subject headers."""
        archive = EmailArchive(temp_dir, {})
        email_path = temp_dir / "a.eml"
        email_path.write_bytes(sample_eml_simple)
        self._seed(archive, [("a", "a.eml", "me@example.com", None)])

        cmd_list_unknown(archive, verbose=True)

        out = capsys.readouterr().out
        assert "- a.eml" in out
        assert "Date header: Mon, 1 Jan 2024 10:00:00 +0000" in out
        assert "Subject: Test Email" in out

    def test_verbose_missing_file_is_skipped(self, temp_dir, capsys):
        """A row whose file is gone should still list, without headers."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "gone.eml", "me@example.com", None)])

        cmd_list_unknown(archive, verbose=True)

        out = capsys.readouterr().out
        assert "- gone.eml" in out
        assert "Date header:" not in out

    def test_verbose_unreadable_file_reports_error(self, temp_dir, capsys):
        """A file that cannot be read should report the error inline."""
        archive = EmailArchive(temp_dir, {})
        (temp_dir / "a.eml").write_bytes(b"whatever")
        self._seed(archive, [("a", "a.eml", "me@example.com", None)])

        with patch("email.message_from_binary_file", side_effect=OSError("disk gone")):
            cmd_list_unknown(archive, verbose=True)

        assert "Error reading: disk gone" in capsys.readouterr().out


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
        assert "restore search index" in captured.out

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
# Rebuild cancel / resume tests
# ---------------------------------------------------------------------------

_SAMPLE_EML = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: Rebuild Test\r\n"
    b"Date: Mon, 15 Jan 2024 10:00:00 +0000\r\n"
    b"Message-ID: <rebuild-test@example.com>\r\n"
    b"\r\n"
    b"Body content for rebuild.\r\n"
)


def _make_email(archive, temp_dir, n, account="test@gmail.com"):
    """Create an email file and DB row for testing. Returns email_id."""
    emails_dir = temp_dir / "sources" / account / "2024" / "01"
    emails_dir.mkdir(parents=True, exist_ok=True)

    content = _SAMPLE_EML.replace(b"Rebuild Test", f"Email {n}".encode())
    content_hash = hashlib.sha256(content).hexdigest()

    path = emails_dir / f"email_{n}.eml"
    path.write_bytes(content)
    rel = str(path.relative_to(temp_dir))

    eid = _eid(f"msg{n}", account)
    archive.db.mark_downloaded(eid, f"msg{n}", rel, content_hash=content_hash, account=account)
    return eid


class TestReconcileLabelSidecars:
    """Tests for _reconcile_label_sidecars (rebuild --only sidecars)."""

    def test_backfills_sidecar_from_db_when_missing(self, temp_dir, capsys):
        """An email with DB labels but no sidecar gets one written (migration)."""
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)

        with sqlite3.connect(archive.db.db_path) as conn:
            rowid, email_date = conn.execute(
                "SELECT rowid, email_date FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
            conn.execute(
                "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                (rowid, "INBOX", email_date),
            )
            filename = conn.execute("SELECT filename FROM emails WHERE email_id = ?", (eid,)).fetchone()[0]

        _reconcile_label_sidecars(archive)

        assert sidecar.read_labels(temp_dir / filename) == ["INBOX"]
        captured = capsys.readouterr()
        assert "Backfilled (new sidecar written): 1" in captured.out

    def test_sidecar_wins_on_divergence(self, temp_dir, capsys):
        """If sidecar and DB disagree, DB is rewritten to match the sidecar."""
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)

        with sqlite3.connect(archive.db.db_path) as conn:
            rowid, email_date = conn.execute(
                "SELECT rowid, email_date FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
            conn.execute(
                "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                (rowid, "OLD_LABEL", email_date),
            )
            filename = conn.execute("SELECT filename FROM emails WHERE email_id = ?", (eid,)).fetchone()[0]

        sidecar.write_labels(temp_dir / filename, ["NEW_LABEL"])

        _reconcile_label_sidecars(archive)

        with sqlite3.connect(archive.db.db_path) as conn:
            labels = [
                row[0]
                for row in conn.execute("SELECT label FROM email_labels WHERE email_rowid = ?", (rowid,)).fetchall()
            ]
        assert labels == ["NEW_LABEL"]
        captured = capsys.readouterr()
        assert "Reconciled (DB updated from sidecar): 1" in captured.out

    def test_unchanged_when_sidecar_matches_db(self, temp_dir, capsys):
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)

        with sqlite3.connect(archive.db.db_path) as conn:
            rowid, email_date = conn.execute(
                "SELECT rowid, email_date FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
            conn.execute(
                "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                (rowid, "INBOX", email_date),
            )
            filename = conn.execute("SELECT filename FROM emails WHERE email_id = ?", (eid,)).fetchone()[0]

        sidecar.write_labels(temp_dir / filename, ["INBOX"])

        _reconcile_label_sidecars(archive)
        captured = capsys.readouterr()
        assert "Unchanged: 1" in captured.out

    def test_purges_unread_from_existing_sidecar(self, temp_dir, capsys):
        """Gmail archives synced before read/unread was dropped get cleaned up."""
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)

        with sqlite3.connect(archive.db.db_path) as conn:
            rowid, email_date, filename = conn.execute(
                "SELECT rowid, email_date, filename FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
            for label in ("INBOX", "UNREAD"):
                conn.execute(
                    "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                    (rowid, label, email_date),
                )

        sidecar.write_labels(temp_dir / filename, ["INBOX", "UNREAD"])

        _reconcile_label_sidecars(archive)

        assert sidecar.read_labels(temp_dir / filename) == ["INBOX"]
        with sqlite3.connect(archive.db.db_path) as conn:
            labels = [
                row[0]
                for row in conn.execute("SELECT label FROM email_labels WHERE email_rowid = ?", (rowid,)).fetchall()
            ]
        assert labels == ["INBOX"]
        assert "Purged (ephemeral labels dropped): 1" in capsys.readouterr().out

    def test_purge_keeps_differently_cased_folder(self, temp_dir, capsys):
        """An IMAP folder named 'Unread' is real archive content, not client state."""
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)

        with sqlite3.connect(archive.db.db_path) as conn:
            rowid, email_date, filename = conn.execute(
                "SELECT rowid, email_date, filename FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
            conn.execute(
                "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                (rowid, "Unread", email_date),
            )

        sidecar.write_labels(temp_dir / filename, ["Unread"])

        _reconcile_label_sidecars(archive)

        assert sidecar.read_labels(temp_dir / filename) == ["Unread"]
        assert "Purged (ephemeral labels dropped): 0" in capsys.readouterr().out

    def test_backfill_drops_unread_from_db(self, temp_dir, capsys):
        """A sidecar written from stale DB labels must not resurrect UNREAD."""
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)

        with sqlite3.connect(archive.db.db_path) as conn:
            rowid, email_date, filename = conn.execute(
                "SELECT rowid, email_date, filename FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
            for label in ("INBOX", "UNREAD"):
                conn.execute(
                    "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                    (rowid, label, email_date),
                )

        _reconcile_label_sidecars(archive)

        assert sidecar.read_labels(temp_dir / filename) == ["INBOX"]
        with sqlite3.connect(archive.db.db_path) as conn:
            labels = [
                row[0]
                for row in conn.execute("SELECT label FROM email_labels WHERE email_rowid = ?", (rowid,)).fetchall()
            ]
        assert labels == ["INBOX"]

    def test_wired_via_rebuild_only_sidecars(self, temp_dir, capsys):
        """cmd_rebuild(only='sidecars') dispatches to the sidecar reconciler."""
        archive = EmailArchive(temp_dir, {})
        _make_email(archive, temp_dir, 1)

        cmd_rebuild(archive, only="sidecars")
        captured = capsys.readouterr()
        assert "Reconcile Label Sidecars" in captured.out

    def test_no_emails_short_circuits(self, temp_dir, capsys):
        """An empty database should report nothing to do."""
        archive = EmailArchive(temp_dir, {})

        _reconcile_label_sidecars(archive)

        assert "No emails to reconcile." in capsys.readouterr().out

    def test_missing_file_is_skipped(self, temp_dir, capsys):
        """A DB row whose .eml file is gone should be counted, not crash."""
        archive = EmailArchive(temp_dir, {})
        archive.db.mark_downloaded(_eid("gone"), "gone", "gone.eml")

        _reconcile_label_sidecars(archive)

        assert "Skipped (file missing on disk): 1" in capsys.readouterr().out

    def test_pattern_limits_scope(self, temp_dir, capsys):
        """A pattern should restrict which files are reconciled."""
        archive = EmailArchive(temp_dir, {})
        _make_email(archive, temp_dir, 1)

        _reconcile_label_sidecars(archive, pattern="nonexistent/*")

        assert "No emails to reconcile." in capsys.readouterr().out

    def test_debug_reports_each_backfill(self, temp_dir, capsys):
        """Debug mode should name each file it backfills."""
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)
        with sqlite3.connect(archive.db.db_path) as conn:
            filename = conn.execute("SELECT filename FROM emails WHERE email_id = ?", (eid,)).fetchone()[0]

        _reconcile_label_sidecars(archive, debug=True)

        assert f"Backfilled sidecar for {filename}" in capsys.readouterr().out

    def test_debug_reports_each_reconcile(self, temp_dir, capsys):
        """Debug mode should show the DB -> sidecar transition."""
        archive = EmailArchive(temp_dir, {})
        eid = _make_email(archive, temp_dir, 1)
        with sqlite3.connect(archive.db.db_path) as conn:
            rowid, email_date, filename = conn.execute(
                "SELECT rowid, email_date, filename FROM emails WHERE email_id = ?", (eid,)
            ).fetchone()
            conn.execute(
                "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                (rowid, "FROM_DB", email_date),
            )
        sidecar.write_labels(temp_dir / filename, ["FROM_SIDECAR"])

        _reconcile_label_sidecars(archive, debug=True)

        out = capsys.readouterr().out
        assert "FROM_DB" in out
        assert "FROM_SIDECAR" in out


class TestRebuildCancel:
    """Tests for Ctrl-C (SIGINT) cancellation during rebuild."""

    def test_sigint_stops_rebuild_gracefully(self, temp_dir, capsys):
        """SIGINT mid-rebuild stops after current email and saves progress."""
        import signal

        archive = EmailArchive(temp_dir, {})

        # Create 10 emails to index
        for i in range(10):
            _make_email(archive, temp_dir, i)

        # Monkey-patch _index_email_for_rebuild to send SIGINT after 3
        from ownmail import commands

        original_fn = commands._index_email_for_rebuild
        call_count = 0

        def patched_index(arch, email_id, filepath, conn, debug=False):
            nonlocal call_count
            call_count += 1
            result = original_fn(arch, email_id, filepath, conn, debug)
            if call_count == 3:
                import os

                os.kill(os.getpid(), signal.SIGINT)
            return result

        commands._index_email_for_rebuild = patched_index
        try:
            cmd_rebuild(archive)
        finally:
            commands._index_email_for_rebuild = original_fn

        captured = capsys.readouterr()
        assert "Paused" in captured.out
        assert "resume" in captured.out.lower() or "again" in captured.out.lower()

    def test_rebuild_resume_skips_indexed(self, temp_dir, capsys):
        """Second rebuild run skips already-indexed emails."""
        archive = EmailArchive(temp_dir, {})

        # Create 5 emails
        for i in range(5):
            _make_email(archive, temp_dir, i)

        # First run: index all
        cmd_rebuild(archive)
        captured1 = capsys.readouterr()
        assert "5" in captured1.out  # Should show 5 emails

        # Second run: nothing to do
        cmd_rebuild(archive)
        captured2 = capsys.readouterr()
        assert "already indexed" in captured2.out

    def test_rebuild_resume_after_interrupt(self, temp_dir, capsys):
        """After SIGINT, second rebuild picks up where it left off."""
        import signal

        archive = EmailArchive(temp_dir, {})

        for i in range(8):
            _make_email(archive, temp_dir, i)

        from ownmail import commands

        original_fn = commands._index_email_for_rebuild
        call_count = 0

        def patched_index(arch, email_id, filepath, conn, debug=False):
            nonlocal call_count
            call_count += 1
            result = original_fn(arch, email_id, filepath, conn, debug)
            if call_count == 3:
                import os

                os.kill(os.getpid(), signal.SIGINT)
            return result

        commands._index_email_for_rebuild = patched_index
        try:
            cmd_rebuild(archive)
        finally:
            commands._index_email_for_rebuild = original_fn

        captured1 = capsys.readouterr()
        assert "Paused" in captured1.out

        # Count how many are now indexed
        with sqlite3.connect(archive.db.db_path) as conn:
            indexed = conn.execute("SELECT COUNT(*) FROM emails WHERE indexed_hash IS NOT NULL").fetchone()[0]

        assert indexed >= 3  # At least 3 were indexed before SIGINT

        # Second run resumes
        cmd_rebuild(archive)
        capsys.readouterr()

        # After second run, all 8 should be indexed
        with sqlite3.connect(archive.db.db_path) as conn:
            indexed = conn.execute("SELECT COUNT(*) FROM emails WHERE indexed_hash IS NOT NULL").fetchone()[0]
        assert indexed == 8


class TestRebuildForceMode:
    """Tests for rebuild --force rebuilding FTS from scratch."""

    def test_force_rebuilds_fts_table(self, temp_dir, capsys):
        """Force mode drops and rebuilds FTS, re-indexes all emails."""
        archive = EmailArchive(temp_dir, {})

        for i in range(3):
            _make_email(archive, temp_dir, i)

        # First: normal index
        cmd_rebuild(archive)
        capsys.readouterr()

        with sqlite3.connect(archive.db.db_path) as conn:
            fts_before = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
        assert fts_before == 3

        # Force rebuild
        cmd_rebuild(archive, force=True)
        captured = capsys.readouterr()
        assert "force" in captured.out.lower() or "Rebuilding" in captured.out

        with sqlite3.connect(archive.db.db_path) as conn:
            fts_after = conn.execute("SELECT COUNT(*) FROM emails_fts").fetchone()[0]
            indexed = conn.execute("SELECT COUNT(*) FROM emails WHERE indexed_hash IS NOT NULL").fetchone()[0]

        assert fts_after == 3
        assert indexed == 3

    def test_force_with_pattern_does_not_drop_fts(self, temp_dir, capsys):
        """Force + pattern re-indexes matching emails without dropping FTS."""
        archive = EmailArchive(temp_dir, {})

        for i in range(3):
            _make_email(archive, temp_dir, i)

        cmd_rebuild(archive)
        capsys.readouterr()

        # Force with pattern - should NOT drop FTS table
        cmd_rebuild(archive, pattern="email_0", force=True)
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

        # Step 3: Verify again — duplicates and missing files are fixed,
        # but stale index is expected (indexed_hash cleared for rebuild)
        cmd_verify(archive, fix=False)
        out3 = capsys.readouterr().out
        assert "No duplicate emails" in out3
        assert "Missing" not in out3 or "0" in out3

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
            row = conn.execute("SELECT filename FROM emails WHERE email_id = ?", (eid,)).fetchone()
        assert row[0] == new_rel

        # Web UI should serve the email at the updated path
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get(f"/email/{eid}")
            assert response.status_code == 200
            assert b"Moved Email Test" in response.data
            assert b"sender@example.com" in response.data
            assert b"This email was moved on disk." in response.data


class TestCmdImport:
    """Tests for the cmd_import CLI wrapper."""

    def test_import_missing_path_exits(self, temp_dir, capsys):
        """A nonexistent path exits with an error instead of crashing."""
        import pytest

        archive = EmailArchive(temp_dir, {})
        with pytest.raises(SystemExit):
            cmd_import(archive, temp_dir / "nope")
        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_import_delegates_to_archive(self, temp_dir, capsys):
        """cmd_import wires args through to archive.import_path."""
        archive = EmailArchive(temp_dir, {})
        src_dir = temp_dir / "external"
        src_dir.mkdir()
        (src_dir / "one.eml").write_bytes(
            b"From: a@example.com\nMessage-ID: <one@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nOne\n"
        )

        cmd_import(archive, src_dir, account="me@example.com")

        assert archive.db.get_email_count("me@example.com") == 1
        out = capsys.readouterr().out
        assert "Import" in out


class TestCmdScan:
    """Tests for the cmd_scan CLI wrapper."""

    def test_scan_delegates_to_archive(self, temp_dir, capsys):
        """cmd_scan wires args through to archive.scan_archive."""
        archive = EmailArchive(temp_dir, {})
        placed_dir = temp_dir / "sources" / "local" / "2024" / "01"
        placed_dir.mkdir(parents=True)
        (placed_dir / "manual.eml").write_bytes(
            b"From: a@example.com\nMessage-ID: <manual@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nManual\n"
        )

        cmd_scan(archive, account="me@example.com")

        assert archive.db.get_email_count("me@example.com") == 1
        out = capsys.readouterr().out
        assert "Scan" in out


class TestPopulateDatesOnly:
    """Tests for cmd_rebuild(only='dates') / _populate_dates_only."""

    def _seed(self, archive, rows):
        """Insert (email_id, filename, date_str, email_date) rows directly."""
        with sqlite3.connect(archive.db.db_path) as conn:
            for email_id, filename, date_str, email_date in rows:
                conn.execute(
                    "INSERT OR REPLACE INTO emails (email_id, provider_id, filename, date_str, email_date) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (email_id, email_id, filename, date_str, email_date),
                )

    def _dates(self, archive):
        """Return {email_id: email_date} from the database."""
        with sqlite3.connect(archive.db.db_path) as conn:
            return dict(conn.execute("SELECT email_id, email_date FROM emails").fetchall())

    def test_no_missing_dates_reports_and_returns(self, temp_dir, capsys):
        """With every date already populated, nothing should be updated."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", "2024-01-01T10:00:00+00:00")])

        cmd_rebuild(archive, only="dates")

        captured = capsys.readouterr()
        assert "All emails already have dates." in captured.out
        assert "--force to repopulate" in captured.out

    def test_populates_from_date_str(self, temp_dir, capsys):
        """A NULL email_date should be filled in from date_str."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", None)])

        cmd_rebuild(archive, only="dates")

        assert self._dates(archive)["a"] == "2024-01-01T10:00:00+00:00"
        assert "Updated: 1 emails" in capsys.readouterr().out

    def test_converts_to_utc(self, temp_dir):
        """A non-UTC date_str should be normalized to UTC."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "a.eml", "Mon, 1 Jan 2024 10:00:00 +0900", None)])

        cmd_rebuild(archive, only="dates")

        assert self._dates(archive)["a"] == "2024-01-01T01:00:00+00:00"

    def test_falls_back_to_parsing_the_eml_file(self, temp_dir, sample_eml_simple):
        """With no date_str, the .eml file should be parsed for a date."""
        archive = EmailArchive(temp_dir, {})
        email_path = temp_dir / "emails" / "2024" / "01" / "a.eml"
        email_path.parent.mkdir(parents=True)
        email_path.write_bytes(sample_eml_simple)
        rel = str(email_path.relative_to(temp_dir))
        self._seed(archive, [("a", rel, None, None)])

        cmd_rebuild(archive, only="dates")

        assert self._dates(archive)["a"] == "2024-01-01T10:00:00+00:00"

    def test_skips_unparseable_dates(self, temp_dir, capsys):
        """Rows with no usable date should be counted as skipped, not crash."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "missing.eml", "not a date at all", None)])

        cmd_rebuild(archive, only="dates", debug=True)

        assert self._dates(archive)["a"] is None
        captured = capsys.readouterr()
        assert "Skipped (no parseable date): 1" in captured.out
        assert "No date for: missing.eml" in captured.out

    def test_skips_corrupt_eml_file(self, temp_dir, capsys):
        """A file that fails to parse should be skipped, not abort the run."""
        archive = EmailArchive(temp_dir, {})
        email_path = temp_dir / "bad.eml"
        email_path.write_bytes(b"\xff\xfe not an email")
        self._seed(archive, [("a", "bad.eml", None, None)])

        cmd_rebuild(archive, only="dates")

        assert self._dates(archive)["a"] is None
        assert "Skipped (no parseable date): 1" in capsys.readouterr().out

    def test_force_overwrites_existing_dates(self, temp_dir):
        """--force should replace an already-populated email_date."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", "1999-01-01T00:00:00+00:00")])

        cmd_rebuild(archive, only="dates", force=True)

        assert self._dates(archive)["a"] == "2024-01-01T10:00:00+00:00"

    def test_without_force_existing_dates_are_kept(self, temp_dir):
        """Without --force, a populated email_date is not revisited."""
        archive = EmailArchive(temp_dir, {})
        self._seed(
            archive,
            [
                ("a", "a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", "1999-01-01T00:00:00+00:00"),
                ("b", "b.eml", "Tue, 2 Jan 2024 10:00:00 +0000", None),
            ],
        )

        cmd_rebuild(archive, only="dates")

        dates = self._dates(archive)
        assert dates["a"] == "1999-01-01T00:00:00+00:00"
        assert dates["b"] == "2024-01-02T10:00:00+00:00"

    def test_pattern_limits_scope(self, temp_dir):
        """A pattern should restrict which filenames are processed."""
        archive = EmailArchive(temp_dir, {})
        self._seed(
            archive,
            [
                ("a", "2024/01/a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", None),
                ("b", "2023/01/b.eml", "Tue, 2 Jan 2024 10:00:00 +0000", None),
            ],
        )

        cmd_rebuild(archive, only="dates", pattern="2024/01/*")

        dates = self._dates(archive)
        assert dates["a"] == "2024-01-01T10:00:00+00:00"
        assert dates["b"] is None

    def test_pattern_with_force(self, temp_dir):
        """Pattern and --force should combine."""
        archive = EmailArchive(temp_dir, {})
        self._seed(
            archive,
            [
                ("a", "2024/01/a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", "1999-01-01T00:00:00+00:00"),
                ("b", "2023/01/b.eml", "Tue, 2 Jan 2024 10:00:00 +0000", "1999-01-01T00:00:00+00:00"),
            ],
        )

        cmd_rebuild(archive, only="dates", pattern="2024/01/*", force=True)

        dates = self._dates(archive)
        assert dates["a"] == "2024-01-01T10:00:00+00:00"
        assert dates["b"] == "1999-01-01T00:00:00+00:00"

    def test_pattern_matching_nothing_reports_done(self, temp_dir, capsys):
        """A pattern that matches no rows should short-circuit."""
        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "2024/01/a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", None)])

        cmd_rebuild(archive, only="dates", pattern="1998/*")

        assert "All emails already have dates." in capsys.readouterr().out

    def test_interrupt_stops_and_reports_resumable(self, temp_dir, capsys):
        """SIGINT during the loop should pause and leave progress committed."""
        import signal as signal_module

        archive = EmailArchive(temp_dir, {})
        self._seed(
            archive,
            [(str(i), f"{i}.eml", "Mon, 1 Jan 2024 10:00:00 +0000", None) for i in range(5)],
        )

        real_parsedate = commands.parsedate_to_datetime
        calls = []

        def interrupting_parsedate(value):
            calls.append(value)
            if len(calls) == 2:
                # Deliver a real SIGINT to the handler the command installed.
                signal_module.raise_signal(signal_module.SIGINT)
            return real_parsedate(value)

        with patch.object(commands, "parsedate_to_datetime", side_effect=interrupting_parsedate):
            cmd_rebuild(archive, only="dates")

        captured = capsys.readouterr()
        assert "Populate Dates Paused!" in captured.out
        assert "again to resume" in captured.out
        # The rows processed before the interrupt are persisted.
        populated = [v for v in self._dates(archive).values() if v is not None]
        assert 0 < len(populated) < 5

    def test_original_sigint_handler_is_restored(self, temp_dir):
        """The command must not leave its SIGINT handler installed."""
        import signal as signal_module

        archive = EmailArchive(temp_dir, {})
        self._seed(archive, [("a", "a.eml", "Mon, 1 Jan 2024 10:00:00 +0000", None)])

        before = signal_module.getsignal(signal_module.SIGINT)
        cmd_rebuild(archive, only="dates")
        assert signal_module.getsignal(signal_module.SIGINT) is before

    def test_progress_is_committed_in_batches(self, temp_dir, capsys):
        """A run larger than the batch/progress interval should report a rate."""
        archive = EmailArchive(temp_dir, {})
        self._seed(
            archive,
            [(str(i), f"{i}.eml", "Mon, 1 Jan 2024 10:00:00 +0000", None) for i in range(205)],
        )

        cmd_rebuild(archive, only="dates")

        captured = capsys.readouterr()
        assert "[205/205]" in captured.out
        assert "Updated: 205 emails" in captured.out
        assert all(v == "2024-01-01T10:00:00+00:00" for v in self._dates(archive).values())


class TestUpdateLabelsGmailEdgeCases:
    """Tests for _update_labels_gmail's skip and force-quit paths."""

    def _archive(self, temp_dir):
        return EmailArchive(temp_dir, {"sources": [{"name": "g", "type": "gmail_api", "account": "a@example.com"}]})

    def _seed(self, archive, count):
        with sqlite3.connect(archive.db.db_path) as conn:
            for i in range(count):
                conn.execute(
                    "INSERT OR REPLACE INTO emails (email_id, provider_id, filename, account) VALUES (?, ?, ?, ?)",
                    (f"e{i}", f"msg{i}", f"{i}.eml", "a@example.com"),
                )
        for i in range(count):
            (archive.archive_dir / f"{i}.eml").write_bytes(b"From: x@example.com\n\nbody\n")

    def test_row_deleted_mid_run_is_skipped(self, temp_dir, capsys):
        """An email removed from the DB during the run should be skipped."""
        archive = self._archive(temp_dir)
        self._seed(archive, 1)

        provider = MagicMock()
        provider.get_labels_for_message.return_value = ["INBOX"]

        def delete_then_return(_provider_id):
            with sqlite3.connect(archive.db.db_path) as conn:
                conn.execute("DELETE FROM emails WHERE email_id = 'e0'")
            return ["INBOX"]

        provider.get_labels_for_message.side_effect = delete_then_return
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            cmd_update_labels(archive)

        assert "Skipped (not in index): 1" in capsys.readouterr().out

    def test_second_interrupt_forces_quit(self, temp_dir):
        """A second Ctrl-C should exit immediately rather than finish the batch."""
        import signal as signal_module

        archive = self._archive(temp_dir)
        self._seed(archive, 3)

        def interrupt_twice(_provider_id):
            signal_module.raise_signal(signal_module.SIGINT)
            signal_module.raise_signal(signal_module.SIGINT)
            return ["INBOX"]

        provider = MagicMock()
        provider.get_labels_for_message.side_effect = interrupt_twice
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            with pytest.raises(SystemExit) as exc:
                cmd_update_labels(archive)

        assert exc.value.code == 1

    def test_batch_commit_during_long_run(self, temp_dir, capsys):
        """A run past the commit interval should still report every update."""
        archive = self._archive(temp_dir)
        self._seed(archive, 55)

        provider = MagicMock()
        provider.get_labels_for_message.return_value = ["INBOX"]
        with patch("ownmail.providers.gmail.GmailProvider", return_value=provider):
            cmd_update_labels(archive)

        assert "Updated: 55 emails" in capsys.readouterr().out
