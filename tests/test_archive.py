"""Tests for EmailArchive class."""

import pytest

from ownmail import sidecar
from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase


def _eid(provider_id, account=""):
    """Compute email_id from provider_id for tests."""
    return ArchiveDatabase.make_email_id(account, provider_id)


class TestEmailArchiveInit:
    """Tests for EmailArchive initialization."""

    def test_creates_archive_directory(self, temp_dir):
        """Test that archive directory is created."""
        archive_path = temp_dir / "my_archive"
        EmailArchive(archive_path, {})

        assert archive_path.exists()
        assert (archive_path / "ownmail.db").exists()

    def test_stores_config(self, temp_dir):
        """Test that config is stored."""
        config = {"archive_root": str(temp_dir), "test_key": "test_value"}
        archive = EmailArchive(temp_dir, config)
        assert archive.config == config

    def test_creates_database(self, temp_dir):
        """Test that database is initialized."""
        archive = EmailArchive(temp_dir, {})
        assert archive.db is not None
        assert archive.db.db_path == temp_dir / "ownmail.db"


class TestGetEmailsDir:
    """Tests for get_emails_dir method."""

    def test_returns_account_specific_path(self, temp_dir):
        """Test getting emails dir for specific account."""
        archive = EmailArchive(temp_dir, {})
        emails_dir = archive.get_emails_dir("alice@gmail.com")
        assert emails_dir == temp_dir / "sources" / "alice@gmail.com"


class TestFormatHelpers:
    """Tests for static format helper methods."""

    def test_format_size_bytes(self):
        """Test formatting small sizes."""
        assert EmailArchive._format_size(500) == "500B"

    def test_format_size_kb(self):
        """Test formatting KB sizes."""
        assert EmailArchive._format_size(5000) == "5KB"

    def test_format_size_mb(self):
        """Test formatting MB sizes."""
        result = EmailArchive._format_size(5_000_000)
        assert "5" in result and "MB" in result

    def test_format_eta_initial(self):
        """Test ETA formatting for initial iterations."""
        assert EmailArchive._format_eta(100, 1) == "..."
        assert EmailArchive._format_eta(100, 2) == "..."

    def test_format_eta_seconds(self):
        """Test ETA formatting for seconds."""
        assert EmailArchive._format_eta(45, 10) == "45s"

    def test_format_eta_minutes(self):
        """Test ETA formatting for minutes."""
        result = EmailArchive._format_eta(120, 10)
        assert "m" in result

    def test_format_eta_hours(self):
        """Test ETA formatting for hours."""
        result = EmailArchive._format_eta(7200, 10)
        assert "h" in result


class TestSearch:
    """Tests for search method."""

    def test_search_returns_results(self, temp_dir, sample_eml_simple):
        """Test that search returns indexed emails."""
        archive = EmailArchive(temp_dir, {})

        # Create and index an email
        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml", email_date="2024-01-15T00:00:00")
        archive.db.index_email(
            email_id=_eid("test123"),
            subject="Invoice for Amazon purchase",
            sender="orders@amazon.com",
            recipients="buyer@example.com",
            date_str="2024-01-15",
            body="Your order has shipped.",
            attachments="invoice.pdf",
        )

        results = archive.search("amazon")
        assert len(results) >= 1
        assert any("amazon" in str(r).lower() for r in results)

    def test_search_returns_empty_for_no_match(self, temp_dir):
        """Test that search returns empty for no matches."""
        archive = EmailArchive(temp_dir, {})
        results = archive.search("nonexistent_query_xyz")
        assert results == []

    def test_search_respects_limit(self, temp_dir):
        """Test that search respects limit parameter."""
        archive = EmailArchive(temp_dir, {})

        # Add multiple emails
        for i in range(10):
            archive.db.mark_downloaded(_eid(f"msg{i}"), f"msg{i}", f"email{i}.eml", email_date="2024-01-15T00:00:00")
            archive.db.index_email(
                email_id=_eid(f"msg{i}"),
                subject=f"Test email number {i}",
                sender="sender@test.com",
                recipients="recipient@test.com",
                date_str="2024-01-15",
                body="Test body with common keyword",
                attachments="",
            )

        results = archive.search("test", limit=3)
        assert len(results) <= 3


class TestIndexEmail:
    """Tests for _index_email method."""

    def test_index_email_from_content(self, temp_dir, sample_eml_simple):
        """Test indexing email from content bytes."""
        archive = EmailArchive(temp_dir, {})

        # Create email file
        email_path = temp_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml")
        result = archive._index_email(_eid("test123"), email_path, content=sample_eml_simple)

        assert result is True
        assert archive.db.is_indexed(_eid("test123"))

    def test_index_email_from_file(self, temp_dir, sample_eml_simple):
        """Test indexing email from file."""
        archive = EmailArchive(temp_dir, {})

        email_path = temp_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml")
        result = archive._index_email(_eid("test123"), email_path)

        assert result is True


class TestSaveEmail:
    """Tests for _save_email method."""

    def test_save_email_creates_directory_structure(self, temp_dir):
        """Test that save_email creates year/month directories."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        emails_dir.mkdir()

        raw_data = b"""From: test@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body
"""
        filepath, email_date = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()
        assert "2024" in str(filepath)
        assert "01" in str(filepath)
        assert filepath.suffix == ".eml"
        assert email_date is not None
        assert "2024-01-15" in email_date

    def test_save_email_atomic_write(self, temp_dir):
        """Test that save_email uses atomic writes."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        emails_dir.mkdir()

        raw_data = b"""From: test@example.com
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body
"""
        filepath, email_date = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        # File should exist and have correct content
        assert filepath.read_bytes() == raw_data

        # No temp files should remain
        temp_files = list(emails_dir.rglob("*.tmp"))
        assert len(temp_files) == 0


class TestBackupWithMockedProvider:
    """Tests for backup method with mocked provider."""

    def test_backup_no_new_emails(self, temp_dir, capsys):
        """Test backup when there are no new emails."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = ([], None)
        mock_provider.get_current_sync_state.return_value = "12345"

        result = archive.backup(mock_provider)

        assert result["success_count"] == 0
        assert result["error_count"] == 0
        assert result["interrupted"] is False

        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower()

    def test_backup_downloads_new_emails(self, temp_dir, capsys):
        """Test backup downloads new emails."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2"], None)
        mock_provider.get_current_sync_state.return_value = "12345"

        # Mock download_message to return valid email data
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body content
"""
        mock_provider.download_message.return_value = (raw_email, [])

        result = archive.backup(mock_provider)

        assert result["success_count"] == 2
        assert result["error_count"] == 0

    def test_backup_handles_download_errors(self, temp_dir, capsys):
        """Test backup handles download errors gracefully."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2"], None)
        mock_provider.get_current_sync_state.return_value = "12345"

        # First message succeeds, second fails
        raw_email = b"""From: sender@example.com
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body
"""
        mock_provider.download_message.side_effect = [
            (raw_email, []),
            Exception("Network error"),
        ]

        result = archive.backup(mock_provider)

        assert result["success_count"] == 1
        assert result["error_count"] == 1

    def test_backup_skips_already_downloaded(self, temp_dir, capsys):
        """Test backup skips already downloaded messages."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        # Mark msg1 as already downloaded
        archive.db.mark_downloaded(_eid("msg1", "test@gmail.com"), "msg1", "emails/test.eml", account="test@gmail.com")

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2"], None)
        mock_provider.get_current_sync_state.return_value = "12345"

        raw_email = b"""From: sender@example.com
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body
"""
        mock_provider.download_message.return_value = (raw_email, [])

        result = archive.backup(mock_provider)

        # Only msg2 should be downloaded
        assert result["success_count"] == 1
        mock_provider.download_message.assert_called_once_with("msg2")


class TestBackupWritesSidecars:
    """Backup writes a label sidecar file alongside every downloaded .eml,
    matching what got written to the email_labels DB table."""

    @pytest.mark.parametrize("labels", [["INBOX", "IMPORTANT"], ["Receipts, 2026", " Work "], []])
    @pytest.mark.parametrize("orphan_sidecar", [False, True])
    def test_backup_labels_survive_capture_and_reindex(self, temp_dir, labels, orphan_sidecar):
        """Provider labels survive capture, reindexing, and quoted label search."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1"], None)
        mock_provider.get_current_sync_state.return_value = "12345"

        raw_email = b"""From: sender@example.com
Subject: Test
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body content
"""
        mock_provider.download_message.return_value = (raw_email, labels)
        if orphan_sidecar:
            filepath, _ = archive._save_email(
                raw_email, "msg1", mock_provider.account, archive.get_emails_dir(mock_provider.source_name)
            )
            sidecar.write_labels(filepath, ["Old label"])

        result = archive.backup(mock_provider)
        assert result["success_count"] == 1

        eml_files = list(temp_dir.rglob("*.eml"))
        assert len(eml_files) == 1
        assert sidecar.read_labels(eml_files[0]) == labels
        email_id = _eid("msg1", mock_provider.account)
        assert sorted(archive.db.get_labels_for_email(email_id)) == sorted(labels)

        assert archive._index_email(email_id, eml_files[0]) is True

        assert sorted(archive.db.get_labels_for_email(email_id)) == sorted(labels)
        for label in labels:
            assert [row[0] for row in archive.db.search(f'label:"{label}"')] == [email_id]


class TestSaveEmailEdgeCases:
    """Edge case tests for _save_email method."""

    def test_save_email_unknown_date(self, temp_dir):
        """Test saving email with unparseable date."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        emails_dir.mkdir()

        raw_data = b"""From: test@example.com
Date: not a valid date

Body
"""
        filepath, email_date = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()
        # Should use "unknown" for unparseable dates
        assert "unknown" in str(filepath)
        assert email_date is None

    def test_save_email_no_date(self, temp_dir):
        """Test saving email without Date header."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        emails_dir.mkdir()

        raw_data = b"""From: test@example.com
Subject: No Date

Body
"""
        filepath, email_date = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()
        assert email_date is None

    def test_save_email_creates_directories(self, temp_dir):
        """Test that _save_email creates necessary directories."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        # Don't pre-create emails_dir

        raw_data = b"""From: test@example.com
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body
"""
        filepath, email_date = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()
        # Directory should have been created
        assert emails_dir.exists()

    def test_save_email_normalizes_to_utc(self, temp_dir):
        """Test that email_date is stored as UTC regardless of original timezone."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        emails_dir.mkdir()

        # KST (+0900): Feb 9, 01:00 KST = Feb 8, 16:00 UTC
        raw_kst = b"From: a@test.com\nDate: Sun, 09 Feb 2026 01:00:00 +0900\n\nBody"
        # EST (-0500): Feb 8, 23:00 EST = Feb 9, 04:00 UTC
        raw_est = b"From: b@test.com\nDate: Sun, 08 Feb 2026 23:00:00 -0500\n\nBody"

        _, date_kst = archive._save_email(raw_kst, "msg_kst", "a@test.com", emails_dir)
        _, date_est = archive._save_email(raw_est, "msg_est", "b@test.com", emails_dir)

        assert date_kst is not None
        assert date_est is not None
        # Both should be UTC (end with +00:00)
        assert "+00:00" in date_kst
        assert "+00:00" in date_est
        # KST email -> Feb 8, 16:00 UTC; EST email -> Feb 9, 04:00 UTC
        # EST email is actually newer in UTC
        assert date_est > date_kst, f"EST ({date_est}) should sort after KST ({date_kst}) in UTC"


class TestIndexEmailFromContent:
    """Tests for _index_email method with content."""

    def test_index_email_from_content(self, temp_dir, sample_eml_simple):
        """Test indexing email from raw content."""
        archive = EmailArchive(temp_dir, {})

        # Create a dummy filepath (content will be used instead)
        dummy_path = temp_dir / "dummy.eml"
        dummy_path.write_bytes(sample_eml_simple)

        result = archive._index_email(
            email_id=_eid("test123"),
            filepath=dummy_path,
            content=sample_eml_simple,
            skip_delete=True,
        )

        assert result is True

    def test_index_email_from_filepath(self, temp_dir, sample_eml_simple):
        """Test indexing email from file path."""
        archive = EmailArchive(temp_dir, {})

        # Create file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        result = archive._index_email(
            email_id=_eid("test123"),
            filepath=email_path,
            skip_delete=False,
        )

        assert result is True

    def test_index_email_handles_parse_error(self, temp_dir):
        """Test indexing handles parse errors gracefully."""
        archive = EmailArchive(temp_dir, {})

        # Create file with minimal content
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "bad.eml"
        email_path.write_bytes(b"not a valid email")

        # Should not crash
        result = archive._index_email(
            email_id=_eid("bad123"),
            filepath=email_path,
        )

        # May return True (parsing is lenient) or False
        assert isinstance(result, bool)


class TestBackupFullSync:
    """Tests for backup full sync scenarios."""

    def test_backup_with_history_id(self, temp_dir):
        """Test backup using history ID for incremental sync."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        # Set existing history ID
        archive.db.set_sync_state("test@gmail.com", "history_id", "11111")

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = ([], "22222")

        result = archive.backup(mock_provider)

        assert result["success_count"] == 0
        # History ID should be updated
        new_state = archive.db.get_sync_state("test@gmail.com", "history_id")
        assert new_state == "22222"

    def test_backup_error_handling(self, temp_dir, capsys):
        """Test backup handles download errors gracefully."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        mock_provider.download_message.return_value = (None, None)  # Download fails

        result = archive.backup(mock_provider)

        assert result["error_count"] == 1

    def test_backup_404_treated_as_soft_skip(self, temp_dir, capsys):
        """Test that 404 (deleted/trashed message) is skipped without counting as error."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2"], None)
        mock_provider.get_current_sync_state.return_value = "12345"

        # msg1 returns 404 (trashed), msg2 succeeds
        mock_provider.download_message.side_effect = [
            (None, []),  # This won't be used, we mock batch_results below
        ]
        # Simulate sequential download: msg1 returns 404 error, msg2 succeeds
        raw_email = b"From: test@test.com\nDate: Mon, 15 Jan 2024 10:00:00 +0000\n\nBody"
        mock_provider.download_message.side_effect = [
            Exception('<HttpError 404 when requesting returned "Requested entity was not found.">'),
            (raw_email, ["INBOX"]),
        ]

        result = archive.backup(mock_provider)

        # 404 should be skipped, not counted as error
        assert result["error_count"] == 0
        assert result["success_count"] == 1
        captured = capsys.readouterr()
        assert "deleted from server" in captured.out


class TestBackupMultipleEmails:
    """Tests for backup with multiple emails."""

    def test_backup_multiple_success(self, temp_dir, capsys):
        """Test backup downloads multiple emails successfully."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2", "msg3"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        mock_provider.download_message.return_value = (
            b"From: test@example.com\nDate: Mon, 15 Jan 2024 10:00:00 +0000\n\nBody",
            ["INBOX"],
        )

        result = archive.backup(mock_provider)

        assert result["success_count"] == 3
        assert result["error_count"] == 0

    def test_backup_mixed_results(self, temp_dir, capsys):
        """Test backup with mixed success/failure."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.source_name = "test_source"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2"], None)
        mock_provider.get_current_sync_state.return_value = "12345"

        # First call succeeds, second fails
        mock_provider.download_message.side_effect = [
            (b"From: test@example.com\nDate: Mon, 15 Jan 2024 10:00:00 +0000\n\nBody", ["INBOX"]),
            (None, None),
        ]

        result = archive.backup(mock_provider)

        assert result["success_count"] == 1
        assert result["error_count"] == 1


class TestArchiveSearch:
    """Tests for archive search functionality."""

    def test_search_basic(self, temp_dir, sample_eml_simple):
        """Test basic search functionality."""
        archive = EmailArchive(temp_dir, {})

        # Create and index an email
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded(
            _eid("test123"), "test123", rel_path, content_hash="abc", email_date="2024-01-15T00:00:00"
        )
        archive.db.index_email(
            email_id=_eid("test123"),
            subject="Test Email",
            sender="sender@example.com",
            recipients="recipient@example.com",
            date_str="2024-01-15",
            body="Test body content",
            attachments="",
        )

        results = archive.search("Test")
        assert len(results) >= 1

    def test_search_no_results(self, temp_dir):
        """Test search with no results."""
        archive = EmailArchive(temp_dir, {})
        results = archive.search("nonexistent query xyz123")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Cancel / Resume / Sync-state tests
# ---------------------------------------------------------------------------

_RAW_EMAIL = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: Test Email\r\n"
    b"Date: Mon, 15 Jan 2024 10:00:00 +0000\r\n"
    b"Message-ID: <unique@example.com>\r\n"
    b"\r\n"
    b"Body content\r\n"
)


def _raw_email_with_id(n: int) -> bytes:
    """Return a raw email whose content is unique per *n*."""
    return (
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: Email " + str(n).encode() + b"\r\n"
        b"Date: Mon, 15 Jan 2024 10:00:00 +0000\r\n"
        b"Message-ID: <msg" + str(n).encode() + b"@example.com>\r\n"
        b"\r\n"
        b"Body " + str(n).encode() + b"\r\n"
    )


class TestBackupCancel:
    """Tests for Ctrl-C (SIGINT) cancellation during backup."""

    def test_keyboard_interrupt_during_get_new_ids(self, temp_dir, capsys):
        """KeyboardInterrupt in get_new_message_ids returns immediately."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.get_new_message_ids.side_effect = KeyboardInterrupt

        result = archive.backup(provider)

        assert result["interrupted"] is True
        assert result["success_count"] == 0
        assert result["error_count"] == 0
        captured = capsys.readouterr()
        assert "cancelled" in captured.out.lower()

    def test_sigint_stops_after_current_email(self, temp_dir, capsys):
        """SIGINT mid-download stops after the current email."""
        import signal
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.get_new_message_ids.return_value = ([f"msg{i}" for i in range(5)], "state-after")

        call_count = 0

        def download_and_interrupt(msg_id):
            nonlocal call_count
            call_count += 1
            # After 2nd download, simulate SIGINT
            if call_count == 2:
                import os

                os.kill(os.getpid(), signal.SIGINT)
            return (_raw_email_with_id(call_count), [])

        provider.download_message.side_effect = download_and_interrupt

        result = archive.backup(provider)

        assert result["interrupted"] is True
        # At least 1 email should have been downloaded before SIGINT
        assert result["success_count"] >= 1
        # Should NOT have downloaded all 5
        assert result["success_count"] < 5

    def test_sync_state_not_updated_on_interrupt(self, temp_dir):
        """Sync state must NOT be updated when backup is interrupted."""
        import signal
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.name = "imap"
        provider.get_new_message_ids.return_value = ([f"msg{i}" for i in range(5)], "new-sync-state")

        call_count = 0

        def download_and_interrupt(msg_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                import os

                os.kill(os.getpid(), signal.SIGINT)
            return (_raw_email_with_id(call_count), [])

        provider.download_message.side_effect = download_and_interrupt

        archive.backup(provider)

        # Sync state should NOT have been updated
        state = archive.db.get_sync_state("test@gmail.com", "sync_state")
        assert state is None

    def test_progress_saved_on_interrupt(self, temp_dir):
        """Emails downloaded before SIGINT are committed to database."""
        import signal
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.get_new_message_ids.return_value = ([f"msg{i}" for i in range(5)], None)
        provider.get_current_sync_state.return_value = None

        call_count = 0

        def download_and_interrupt(msg_id):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                import os

                os.kill(os.getpid(), signal.SIGINT)
            return (_raw_email_with_id(call_count), [])

        provider.download_message.side_effect = download_and_interrupt

        result = archive.backup(provider)

        assert result["interrupted"] is True
        # Verify the downloaded emails are in the DB
        downloaded_ids = archive.db.get_downloaded_ids("test@gmail.com")
        assert len(downloaded_ids) >= 2


class TestBackupResume:
    """Tests for resumable backup — run again after interruption."""

    def test_resume_skips_already_downloaded(self, temp_dir, capsys):
        """Second backup run skips emails already saved on disk."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        # First run: download 2 emails
        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.get_new_message_ids.return_value = (["msg0", "msg1"], None)
        provider.get_current_sync_state.return_value = None
        provider.download_message.side_effect = [
            (_raw_email_with_id(0), []),
            (_raw_email_with_id(1), []),
        ]
        result1 = archive.backup(provider)
        assert result1["success_count"] == 2

        # Second run: provider returns same 2 + 1 new
        provider.get_new_message_ids.return_value = (["msg0", "msg1", "msg2"], None)
        provider.download_message.reset_mock()
        provider.download_message.side_effect = None
        provider.download_message.return_value = (_raw_email_with_id(2), [])

        result2 = archive.backup(provider)

        assert result2["success_count"] == 1
        # Only msg2 should have been downloaded
        provider.download_message.assert_called_once_with("msg2")


class TestBackupSyncState:
    """Tests for sync state update conditions."""

    def test_sync_state_updated_on_full_success(self, temp_dir):
        """Sync state IS updated when all emails download successfully."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.name = "imap"
        provider.get_new_message_ids.return_value = (["msg0"], "new-state")
        provider.download_message.return_value = (_raw_email_with_id(0), [])

        archive.backup(provider)

        state = archive.db.get_sync_state("test@gmail.com", "sync_state")
        assert state == "new-state"

    def test_sync_state_not_updated_with_date_filter(self, temp_dir):
        """Sync state NOT updated when using --since / --until."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.name = "imap"
        provider.get_new_message_ids.return_value = (["msg0"], "new-state")
        provider.download_message.return_value = (_raw_email_with_id(0), [])

        archive.backup(provider, since="2024-01-01")

        state = archive.db.get_sync_state("test@gmail.com", "sync_state")
        assert state is None

    def test_sync_state_not_updated_on_errors(self, temp_dir):
        """Sync state NOT updated when some downloads fail."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.name = "imap"
        provider.get_new_message_ids.return_value = (["msg0", "msg1"], "new-state")
        provider.download_message.side_effect = [
            (_raw_email_with_id(0), []),
            Exception("Network error"),
        ]

        archive.backup(provider)

        state = archive.db.get_sync_state("test@gmail.com", "sync_state")
        assert state is None

    def test_sync_state_not_updated_with_no_new_and_date_filter(self, temp_dir):
        """Sync state NOT updated when no new emails and date filter is used."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.name = "imap"
        provider.get_new_message_ids.return_value = ([], "new-state")

        archive.backup(provider, until="2024-12-31")

        state = archive.db.get_sync_state("test@gmail.com", "sync_state")
        assert state is None

    def test_sync_state_updated_no_new_full_sync(self, temp_dir):
        """Sync state IS updated on full sync with no new emails."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.name = "imap"
        provider.get_new_message_ids.return_value = ([], "sync-123")

        archive.backup(provider)

        state = archive.db.get_sync_state("test@gmail.com", "sync_state")
        assert state == "sync-123"


class TestBackupContentDedup:
    """Tests for content-based deduplication during backup."""

    def test_content_dedup_skips_duplicates(self, temp_dir, capsys):
        """Emails with same content but different provider_id are skipped."""
        import hashlib
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        raw = _raw_email_with_id(42)
        content_hash = hashlib.sha256(raw).hexdigest()

        # Pre-populate: same content already downloaded under different ID
        archive.db.mark_downloaded(
            _eid("INBOX:100", "test@gmail.com"),
            "INBOX:100",
            "sources/test_source/2024/01/email.eml",
            content_hash=content_hash,
            account="test@gmail.com",
        )

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.get_new_message_ids.return_value = (["AllMail:200"], None)
        provider.get_current_sync_state.return_value = None
        # Same content under a different provider_id
        provider.download_message.return_value = (raw, ["INBOX"])

        result = archive.backup(provider)

        # Should count as success (skipped, not error)
        assert result["success_count"] == 1
        assert result["error_count"] == 0
        captured = capsys.readouterr()
        assert "already downloaded" in captured.out.lower()

    def test_batch_download_failure_continues(self, temp_dir, capsys):
        """Entire batch failure is handled and continues to next batch."""
        from unittest.mock import MagicMock, PropertyMock

        archive = EmailArchive(temp_dir, {})

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.get_new_message_ids.return_value = (["msg0", "msg1", "msg2", "msg3"], None)
        provider.get_current_sync_state.return_value = None
        type(provider).download_batch_size = PropertyMock(return_value=2)
        provider.download_messages_batch.side_effect = [
            Exception("Batch failed"),
            {
                "msg2": (_raw_email_with_id(2), [], None),
                "msg3": (_raw_email_with_id(3), [], None),
            },
        ]

        result = archive.backup(provider)

        # First batch (msg0+msg1) failed, second batch (msg2+msg3) succeeded
        assert result["error_count"] == 2
        assert result["success_count"] == 2


class TestArchiveTrash:
    """Tests for archive trash operations."""

    def test_trash_and_restore_email(self, temp_dir, sample_eml_simple):
        """Test trashing and restoring moves files correctly."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir)
        # Create source dir and file
        src_dir = temp_dir / "sources" / "gmail" / "2024" / "01"
        src_dir.mkdir(parents=True)
        eml_path = src_dir / "test.eml"
        eml_path.write_bytes(sample_eml_simple)

        # Register in DB
        eid = archive.db.make_email_id("", "msg1")
        rel_path = str(eml_path.relative_to(temp_dir))
        archive.db.mark_downloaded(eid, "msg1", rel_path)

        # Trash
        assert archive.trash_email(eid)
        assert not eml_path.exists()
        assert (temp_dir / "trash" / f"{eid}.eml").exists()

        # Restore
        assert archive.restore_email(eid)
        assert eml_path.exists()
        assert not (temp_dir / "trash" / f"{eid}.eml").exists()

    def test_trash_and_restore_moves_sidecar_with_it(self, temp_dir, sample_eml_simple):
        """The label sidecar must travel with its .eml through trash/restore."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir)
        src_dir = temp_dir / "sources" / "gmail" / "2024" / "01"
        src_dir.mkdir(parents=True)
        eml_path = src_dir / "test.eml"
        eml_path.write_bytes(sample_eml_simple)
        sidecar.write_labels(eml_path, ["INBOX", "IMPORTANT"])

        eid = archive.db.make_email_id("", "msg1")
        rel_path = str(eml_path.relative_to(temp_dir))
        archive.db.mark_downloaded(eid, "msg1", rel_path)

        assert archive.trash_email(eid)
        trash_eml = temp_dir / "trash" / f"{eid}.eml"
        assert sidecar.read_labels(trash_eml) == ["INBOX", "IMPORTANT"]
        assert not sidecar.sidecar_path(eml_path).exists()

        assert archive.restore_email(eid)
        assert sidecar.read_labels(eml_path) == ["INBOX", "IMPORTANT"]
        assert not sidecar.sidecar_path(trash_eml).exists()

    def test_permanently_delete_removes_sidecar(self, temp_dir, sample_eml_simple):
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir)
        trash_dir = temp_dir / "trash"
        trash_dir.mkdir()

        eid = archive.db.make_email_id("", "msg1")
        trash_file = trash_dir / f"{eid}.eml"
        trash_file.write_bytes(sample_eml_simple)
        sidecar.write_labels(trash_file, ["INBOX"])
        rel_path = str(trash_file.relative_to(temp_dir))
        archive.db.mark_downloaded(eid, "msg1", rel_path)

        archive.permanently_delete_emails([eid])
        assert not sidecar.sidecar_path(trash_file).exists()

    def test_trash_nonexistent(self, temp_dir):
        """Test trashing a non-existent email returns False."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir)
        assert not archive.trash_email("nonexistent")

    def test_permanently_delete(self, temp_dir, sample_eml_simple):
        """Test permanently deleting removes file and DB record."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir)
        trash_dir = temp_dir / "trash"
        trash_dir.mkdir()

        eid = archive.db.make_email_id("", "msg1")
        trash_file = trash_dir / f"{eid}.eml"
        trash_file.write_bytes(sample_eml_simple)
        rel_path = str(trash_file.relative_to(temp_dir))
        archive.db.mark_downloaded(eid, "msg1", rel_path)

        count = archive.permanently_delete_emails([eid])
        assert count == 1
        assert not trash_file.exists()
        assert archive.db.get_email_by_id(eid) is None

    def test_empty_trash(self, temp_dir, sample_eml_simple):
        """Test emptying trash deletes all trashed emails."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir)
        src_dir = temp_dir / "sources" / "gmail" / "2024" / "01"
        src_dir.mkdir(parents=True)

        eid = archive.db.make_email_id("", "msg1")
        eml_path = src_dir / "test.eml"
        eml_path.write_bytes(sample_eml_simple)
        rel_path = str(eml_path.relative_to(temp_dir))
        archive.db.mark_downloaded(eid, "msg1", rel_path)

        archive.trash_email(eid)
        count = archive.empty_trash(expired_only=False)
        assert count == 1


class TestImportEmail:
    """Tests for import_email (single-file import)."""

    def test_import_derives_local_provider_id_from_message_id(self, temp_dir, sample_eml_simple):
        """Imported email gets a local:{Message-ID} provider_id."""
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "src.eml"
        src.write_bytes(sample_eml_simple)

        status = archive.import_email(src, account="me@example.com")

        assert status == "imported"
        eid = _eid("local:<test123@example.com>", "me@example.com")
        row = archive.db.get_email_by_id(eid)
        assert row is not None

    def test_import_falls_back_to_content_hash_when_no_message_id(self, temp_dir):
        """Missing Message-ID falls back to local:sha256:{hash}."""
        import hashlib

        archive = EmailArchive(temp_dir, {})
        raw = b"""From: sender@example.com\nTo: recipient@example.com\nSubject: No ID\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nNo message id here.\n"""
        src = temp_dir / "src.eml"
        src.write_bytes(raw)

        status = archive.import_email(src, account="me@example.com")

        assert status == "imported"
        expected_id = f"local:sha256:{hashlib.sha256(raw).hexdigest()}"
        eid = _eid(expected_id, "me@example.com")
        assert archive.db.get_email_by_id(eid) is not None

    def test_import_defaults_account_to_from_header(self, temp_dir, sample_eml_simple):
        """When --account isn't given, the email's own From header is used."""
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "src.eml"
        src.write_bytes(sample_eml_simple)

        status = archive.import_email(src)

        assert status == "imported"
        eid = _eid("local:<test123@example.com>", "sender@example.com")
        assert archive.db.get_email_by_id(eid) is not None

    def test_import_copies_file_into_archive_layout(self, temp_dir, sample_eml_simple):
        """The source file is copied into sources/local/YYYY/MM/."""
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "src.eml"
        src.write_bytes(sample_eml_simple)

        archive.import_email(src, account="me@example.com")

        assert src.exists()  # copy, not move, by default
        copied = list((temp_dir / "sources" / "local" / "2024" / "01").glob("*.eml"))
        assert len(copied) == 1
        assert copied[0].read_bytes() == sample_eml_simple

    def test_import_preserves_sidecar_metadata_and_label_search(self, temp_dir, sample_eml_simple):
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "src.eml"
        src.write_bytes(sample_eml_simple)
        metadata = {"version": 1, "labels": ["Receipts, 2026", " Work "], "note": "Retained metadata"}
        sidecar.write_metadata(src, metadata)

        assert archive.import_email(src, account="me@example.com") == "imported"

        copied = next((temp_dir / "sources" / "local").rglob("*.eml"))
        assert sidecar.read_metadata(copied) == metadata
        assert sidecar.read_metadata(src) == metadata
        email_id = _eid("local:<test123@example.com>", "me@example.com")
        assert sorted(archive.db.get_labels_for_email(email_id)) == sorted(metadata["labels"])
        assert [row[0] for row in archive.search('label:"Receipts, 2026"')] == [email_id]
        assert archive.search("label:Receipts") == []

    @pytest.mark.parametrize("raw_sidecar", [None, b"{invalid json", b"null", b"[]", b'{"labels":"Work"}', b"\xff"])
    def test_import_ignores_missing_or_malformed_sidecar(self, temp_dir, sample_eml_simple, raw_sidecar):
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "src.eml"
        src.write_bytes(sample_eml_simple)
        if raw_sidecar is not None:
            sidecar.sidecar_path(src).write_bytes(raw_sidecar)

        assert archive.import_email(src, account="me@example.com") == "imported"

        copied = next((temp_dir / "sources" / "local").rglob("*.eml"))
        assert not sidecar.sidecar_path(copied).exists()
        assert len(archive.search("test email")) == 1
        email_id = _eid("local:<test123@example.com>", "me@example.com")
        assert archive.db.get_labels_for_email(email_id) == []

    def test_import_move_deletes_source(self, temp_dir, sample_eml_simple):
        """--move deletes the source file after a successful import."""
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "src.eml"
        src.write_bytes(sample_eml_simple)
        sidecar.write_labels(src, ["Receipts, 2026"])

        status = archive.import_email(src, account="me@example.com", move=True)

        assert status == "imported"
        assert not src.exists()
        assert sidecar.read_labels(src) == ["Receipts, 2026"]
        copied = next((temp_dir / "sources" / "local").rglob("*.eml"))
        assert sidecar.read_labels(copied) == ["Receipts, 2026"]

    def test_import_duplicate_is_skipped(self, temp_dir, sample_eml_simple):
        """Importing the same email twice is a no-op the second time."""
        archive = EmailArchive(temp_dir, {})
        src1 = temp_dir / "src1.eml"
        src1.write_bytes(sample_eml_simple)
        src2 = temp_dir / "src2.eml"
        src2.write_bytes(sample_eml_simple)
        sidecar.write_labels(src1, ["Original, label"])
        sidecar.write_labels(src2, ["Other label"])

        first = archive.import_email(src1, account="me@example.com")
        second = archive.import_email(src2, account="me@example.com")

        assert first == "imported"
        assert second == "duplicate"
        # Only one copy should exist in the archive
        copied = list((temp_dir / "sources" / "local").rglob("*.eml"))
        assert len(copied) == 1
        assert sidecar.read_labels(copied[0]) == ["Original, label"]

    def test_import_missing_file_is_an_error(self, temp_dir):
        """Importing a nonexistent file returns 'error', not a crash."""
        archive = EmailArchive(temp_dir, {})
        status = archive.import_email(temp_dir / "does_not_exist.eml", account="me@example.com")
        assert status == "error"

    def test_imported_email_is_searchable(self, temp_dir, sample_eml_simple):
        """Imported emails are indexed and show up in search."""
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "src.eml"
        src.write_bytes(sample_eml_simple)

        archive.import_email(src, account="me@example.com")

        results = archive.search("test email")
        assert len(results) == 1


class TestImportPath:
    """Tests for import_path (directory-level import with progress/Ctrl-C)."""

    def test_import_path_directory(self, temp_dir, capsys):
        """Recursively imports all .eml files under a directory."""
        archive = EmailArchive(temp_dir, {})
        src_dir = temp_dir / "external"
        (src_dir / "nested").mkdir(parents=True)
        (src_dir / "one.eml").write_bytes(
            b"From: a@example.com\nMessage-ID: <one@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nOne\n"
        )
        (src_dir / "nested" / "two.eml").write_bytes(
            b"From: b@example.com\nMessage-ID: <two@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nTwo\n"
        )

        result = archive.import_path(src_dir, account="me@example.com")

        assert result["imported_count"] == 2
        assert result["duplicate_count"] == 0
        assert result["error_count"] == 0
        assert result["interrupted"] is False

    def test_import_path_dry_run_does_not_import(self, temp_dir, capsys):
        """--dry-run reports files without importing them."""
        archive = EmailArchive(temp_dir, {})
        src_dir = temp_dir / "external"
        src_dir.mkdir()
        (src_dir / "one.eml").write_bytes(
            b"From: a@example.com\nMessage-ID: <one@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nOne\n"
        )

        result = archive.import_path(src_dir, account="me@example.com", dry_run=True)

        assert result["imported_count"] == 0
        assert archive.db.get_email_count() == 0
        captured = capsys.readouterr()
        assert "would import" in captured.out

    def test_import_path_single_file(self, temp_dir):
        """A single .eml file path (not a directory) is imported directly."""
        archive = EmailArchive(temp_dir, {})
        src = temp_dir / "one.eml"
        src.write_bytes(
            b"From: a@example.com\nMessage-ID: <one@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nOne\n"
        )

        result = archive.import_path(src, account="me@example.com")

        assert result["imported_count"] == 1

    def test_import_path_no_eml_files(self, temp_dir, capsys):
        """A directory with no .eml files imports nothing and doesn't crash."""
        archive = EmailArchive(temp_dir, {})
        src_dir = temp_dir / "external"
        src_dir.mkdir()
        (src_dir / "notes.txt").write_text("not an email")

        result = archive.import_path(src_dir, account="me@example.com")

        assert result["imported_count"] == 0
        captured = capsys.readouterr()
        assert "No .eml files found" in captured.out

    def test_import_path_sigint_stops_after_current_file(self, temp_dir):
        """SIGINT mid-import stops after the current file and is resumable."""
        import os
        import signal

        archive = EmailArchive(temp_dir, {})
        src_dir = temp_dir / "external"
        src_dir.mkdir()
        for i in range(5):
            (src_dir / f"{i}.eml").write_bytes(
                f"From: a{i}@example.com\nMessage-ID: <{i}@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nBody {i}\n".encode()
            )

        original_import_email = archive.import_email
        call_count = 0

        def import_and_interrupt(filepath, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                os.kill(os.getpid(), signal.SIGINT)
            return original_import_email(filepath, **kwargs)

        archive.import_email = import_and_interrupt

        result = archive.import_path(src_dir, account="me@example.com")

        assert result["interrupted"] is True
        assert 0 < result["imported_count"] < 5

        # Resuming picks up where it left off (already-imported files are skipped)
        archive.import_email = original_import_email
        second_result = archive.import_path(src_dir, account="me@example.com")
        assert result["imported_count"] + second_result["imported_count"] == 5


class TestScanArchive:
    """Tests for scan_archive (registering untracked in-place .eml files)."""

    def test_scan_registers_untracked_file(self, temp_dir):
        """A manually-placed .eml file in the archive dir gets registered."""
        archive = EmailArchive(temp_dir, {})
        placed_dir = temp_dir / "sources" / "local" / "2024" / "01"
        placed_dir.mkdir(parents=True)
        (placed_dir / "manual.eml").write_bytes(
            b"From: a@example.com\nMessage-ID: <manual@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nManual\n"
        )

        result = archive.scan_archive(account="me@example.com")

        assert result["imported_count"] == 1
        eid = _eid("local:<manual@example.com>", "me@example.com")
        assert archive.db.get_email_by_id(eid) is not None

    def test_scan_skips_already_tracked_files(self, temp_dir, sample_eml_simple):
        """Files already tracked in the DB are not re-registered."""
        archive = EmailArchive(temp_dir, {})
        emails_dir = archive.get_emails_dir("gmail")
        emails_dir.mkdir(parents=True)
        filepath = emails_dir / "existing.eml"
        filepath.write_bytes(sample_eml_simple)
        rel_path = str(filepath.relative_to(temp_dir))
        archive.db.mark_downloaded(_eid("msg1", "me@example.com"), "msg1", rel_path, account="me@example.com")

        result = archive.scan_archive(account="me@example.com")

        assert result["imported_count"] == 0

    def test_scan_does_not_move_or_copy_files(self, temp_dir):
        """scan registers files in place; the file never moves."""
        archive = EmailArchive(temp_dir, {})
        placed_dir = temp_dir / "sources" / "local" / "2024" / "01"
        placed_dir.mkdir(parents=True)
        placed_file = placed_dir / "manual.eml"
        placed_file.write_bytes(
            b"From: a@example.com\nMessage-ID: <manual@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nManual\n"
        )

        archive.scan_archive(account="me@example.com")

        eid = _eid("local:<manual@example.com>", "me@example.com")
        row = archive.db.get_email_by_id(eid)
        assert row[1] == str(placed_file.relative_to(temp_dir))
        assert placed_file.exists()

    def test_scan_dry_run_does_not_register(self, temp_dir, capsys):
        """--dry-run reports untracked files without registering them."""
        archive = EmailArchive(temp_dir, {})
        placed_dir = temp_dir / "sources" / "local" / "2024" / "01"
        placed_dir.mkdir(parents=True)
        (placed_dir / "manual.eml").write_bytes(
            b"From: a@example.com\nMessage-ID: <manual@example.com>\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nManual\n"
        )

        result = archive.scan_archive(account="me@example.com", dry_run=True)

        assert result["imported_count"] == 0
        assert archive.db.get_email_count() == 0
        captured = capsys.readouterr()
        assert "would register" in captured.out

    def test_scan_no_untracked_files(self, temp_dir, capsys):
        """No untracked files scans cleanly without crashing."""
        archive = EmailArchive(temp_dir, {})
        result = archive.scan_archive()
        assert result["imported_count"] == 0
        captured = capsys.readouterr()
        assert "No untracked .eml files found" in captured.out
        assert archive.db.get_trash_count() == 0


class TestBackupVerboseAndInterrupt:
    """Tests for backup's verbose logging and cancellation handling."""

    def _provider(self, **kwargs):
        from unittest.mock import MagicMock

        provider = MagicMock()
        provider.account = "test@gmail.com"
        provider.source_name = "test_source"
        provider.name = kwargs.pop("name", "gmail")
        provider.get_new_message_ids.return_value = kwargs.pop("new_ids", ([], None))
        provider.get_current_sync_state.return_value = kwargs.pop("sync_state", "12345")
        for key, value in kwargs.items():
            setattr(provider, key, value)
        return provider

    def test_verbose_logs_each_stage(self, temp_dir, capsys):
        """Verbose mode should narrate the setup steps before downloading."""
        archive = EmailArchive(temp_dir, {})

        archive.backup(self._provider(), verbose=True)

        out = capsys.readouterr().out
        assert "Loading downloaded IDs from database" in out
        assert "Getting sync state" in out
        assert "Calling provider.get_new_message_ids()" in out
        assert "Provider returned 0 message IDs" in out

    def test_cancel_during_id_listing(self, temp_dir, capsys):
        """Ctrl-C while listing IDs should return an interrupted result."""
        archive = EmailArchive(temp_dir, {})
        provider = self._provider()
        provider.get_new_message_ids.side_effect = KeyboardInterrupt

        result = archive.backup(provider)

        assert result["interrupted"] is True
        assert result["success_count"] == 0
        assert "Backup cancelled" in capsys.readouterr().out

    def test_imap_provider_uses_sync_state_key(self, temp_dir):
        """An IMAP provider should read and write the sync_state key."""
        archive = EmailArchive(temp_dir, {})
        archive.db.set_sync_state("test@gmail.com", "sync_state", "prior")
        provider = self._provider(name="imap")

        archive.backup(provider)

        provider.get_new_message_ids.assert_called_once()
        assert provider.get_new_message_ids.call_args.args[0] == "prior"

    def test_gmail_provider_uses_history_id_key(self, temp_dir):
        """A Gmail provider should read and write the history_id key."""
        archive = EmailArchive(temp_dir, {})
        archive.db.set_sync_state("test@gmail.com", "history_id", "prior")
        provider = self._provider(name="gmail")

        archive.backup(provider)

        assert provider.get_new_message_ids.call_args.args[0] == "prior"

    def test_sync_state_recorded_after_first_full_sync(self, temp_dir):
        """With no prior state, the provider's current state should be stored."""
        archive = EmailArchive(temp_dir, {})
        provider = self._provider(sync_state="99")

        archive.backup(provider)

        assert archive.db.get_sync_state("test@gmail.com", "history_id") == "99"

    def test_provider_supplied_state_is_stored(self, temp_dir):
        """A state returned alongside the IDs should be persisted."""
        archive = EmailArchive(temp_dir, {})
        provider = self._provider(new_ids=([], "from-provider"))

        archive.backup(provider)

        assert archive.db.get_sync_state("test@gmail.com", "history_id") == "from-provider"

    def test_date_filtered_run_does_not_touch_sync_state(self, temp_dir):
        """A partial (date-filtered) sync must not advance the sync state."""
        archive = EmailArchive(temp_dir, {})
        provider = self._provider(new_ids=([], "from-provider"))

        archive.backup(provider, since="2024-01-01")

        assert archive.db.get_sync_state("test@gmail.com", "history_id") is None

    def test_already_downloaded_ids_are_filtered_out(self, temp_dir, capsys):
        """IDs already in the database should not be downloaded again."""
        archive = EmailArchive(temp_dir, {})
        archive.db.mark_downloaded(_eid("msg1", "test@gmail.com"), "msg1", "a.eml", account="test@gmail.com")
        provider = self._provider(new_ids=(["msg1"], None))

        result = archive.backup(provider)

        assert result["success_count"] == 0
        assert "up to date" in capsys.readouterr().out.lower()


class TestSaveEmailAtomicWrite:
    """Tests for _save_email's atomic write behaviour."""

    RAW = b"From: a@example.com\r\nSubject: S\r\nDate: Mon, 15 Jan 2024 10:00:00 +0000\r\n\r\nbody\r\n"

    def test_writes_into_year_month_directory(self, temp_dir):
        """Saved emails should land under emails/<year>/<month>/."""
        archive = EmailArchive(temp_dir, {})
        emails_dir = archive.get_emails_dir("src")
        emails_dir.mkdir(parents=True, exist_ok=True)

        filepath, date_iso = archive._save_email(self.RAW, "msg1", "a@example.com", emails_dir)

        assert filepath is not None
        assert filepath.parts[-3:-1] == ("2024", "01")
        assert filepath.read_bytes() == self.RAW
        assert date_iso.startswith("2024-01-15")

    def test_temp_file_cleaned_up_on_write_failure(self, temp_dir, capsys):
        """A failed write must not leave a .tmp file behind."""
        from unittest.mock import patch

        archive = EmailArchive(temp_dir, {})
        emails_dir = archive.get_emails_dir("src")
        emails_dir.mkdir(parents=True, exist_ok=True)

        with patch("os.write", side_effect=OSError("disk full")):
            filepath, date_iso = archive._save_email(self.RAW, "msg1", "a@example.com", emails_dir)

        assert filepath is None
        assert date_iso is None
        assert list(emails_dir.rglob("*.tmp")) == []
        assert "Error saving msg1" in capsys.readouterr().out

    def test_unparseable_date_still_saves(self, temp_dir):
        """An email with no usable date should still be archived."""
        archive = EmailArchive(temp_dir, {})
        emails_dir = archive.get_emails_dir("src")
        emails_dir.mkdir(parents=True, exist_ok=True)
        raw = b"From: a@example.com\r\nSubject: No date\r\n\r\nbody\r\n"

        filepath, _ = archive._save_email(raw, "msg1", "a@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()


class TestIndexEmailFailure:
    """Tests for _index_email error handling."""

    def test_index_failure_is_reported_not_raised(self, temp_dir, capsys):
        """A parse failure should be reported and return False."""
        from unittest.mock import patch

        archive = EmailArchive(temp_dir, {})
        filepath = temp_dir / "bad.eml"
        filepath.write_bytes(b"whatever")

        with patch("ownmail.archive.EmailParser.parse_file", side_effect=ValueError("bad email")):
            assert archive._index_email("id1", filepath) is False

        assert "Error indexing" in capsys.readouterr().out


class TestTrashSidecarHandling:
    """Tests for label sidecars travelling with trashed/restored emails."""

    def _archive_with_email(self, temp_dir, labels=("Work",)):
        from ownmail import sidecar as sidecar_mod

        archive = EmailArchive(temp_dir, {})
        rel = "emails/2024/01/mail.eml"
        filepath = temp_dir / rel
        filepath.parent.mkdir(parents=True)
        filepath.write_bytes(b"From: a@example.com\r\nSubject: S\r\n\r\nbody\r\n")
        email_id = _eid("msg1")
        archive.db.mark_downloaded(email_id, "msg1", rel, email_date="2024-01-01T00:00:00+00:00")
        if labels:
            sidecar_mod.write_labels(filepath, list(labels))
        return archive, email_id, filepath

    def test_trash_moves_file_and_sidecar(self, temp_dir):
        """Trashing should move both the .eml and its sidecar."""
        from ownmail import sidecar as sidecar_mod

        archive, email_id, filepath = self._archive_with_email(temp_dir)

        assert archive.trash_email(email_id) is True

        assert not filepath.exists()
        trashed = temp_dir / "trash" / f"{email_id}.eml"
        assert trashed.exists()
        assert sidecar_mod.read_labels(trashed) == ["Work"]

    def test_restore_moves_file_and_sidecar_back(self, temp_dir):
        """Restoring should return both files to their original location."""
        from ownmail import sidecar as sidecar_mod

        archive, email_id, filepath = self._archive_with_email(temp_dir)
        archive.trash_email(email_id)

        assert archive.restore_email(email_id) is True

        assert filepath.exists()
        assert sidecar_mod.read_labels(filepath) == ["Work"]

    def test_trash_unknown_email_returns_false(self, temp_dir):
        """Trashing an unknown id should report failure."""
        archive = EmailArchive(temp_dir, {})
        assert archive.trash_email("nope") is False

    def test_restore_untrashed_email_returns_false(self, temp_dir):
        """Restoring an email that isn't trashed should report failure."""
        archive, email_id, _ = self._archive_with_email(temp_dir)
        assert archive.restore_email(email_id) is False

    def test_trash_tolerates_missing_file(self, temp_dir):
        """A DB row whose file is gone should still be trashed in the DB."""
        archive, email_id, filepath = self._archive_with_email(temp_dir, labels=())
        filepath.unlink()

        assert archive.trash_email(email_id) is True

    def test_permanent_delete_removes_file_and_sidecar(self, temp_dir):
        """Permanent deletion should remove both files from disk."""
        from ownmail import sidecar as sidecar_mod

        archive, email_id, filepath = self._archive_with_email(temp_dir)
        sidecar_file = sidecar_mod.sidecar_path(filepath)

        assert archive.permanently_delete_emails([email_id]) == 1

        assert not filepath.exists()
        assert not sidecar_file.exists()

    def test_permanent_delete_ignores_unknown_ids(self, temp_dir):
        """Unknown ids should not raise during permanent deletion."""
        archive = EmailArchive(temp_dir, {})
        assert archive.permanently_delete_emails(["nope"]) == 0

    def test_empty_trash_removes_files_and_directory(self, temp_dir):
        """Emptying trash should delete the files and prune the directory."""
        archive, email_id, _ = self._archive_with_email(temp_dir)
        archive.trash_email(email_id)

        assert archive.empty_trash() == 1
        assert not archive.trash_dir.exists()

    def test_empty_trash_when_already_empty(self, temp_dir):
        """Emptying an empty trash should be a no-op returning zero."""
        archive = EmailArchive(temp_dir, {})
        assert archive.empty_trash() == 0

    def test_auto_expire_only_removes_old_entries(self, temp_dir):
        """A freshly trashed email should survive auto-expiry."""
        archive, email_id, _ = self._archive_with_email(temp_dir)
        archive.trash_email(email_id)

        assert archive.auto_expire_trash(days=30) == 0
        assert (temp_dir / "trash" / f"{email_id}.eml").exists()

    def test_auto_expire_removes_entries_past_the_threshold(self, temp_dir):
        """An email trashed longer ago than the window should be expired."""
        import sqlite3

        archive, email_id, _ = self._archive_with_email(temp_dir)
        archive.trash_email(email_id)
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute(
                "UPDATE emails SET trashed_at = datetime('now', '-45 days') WHERE email_id = ?",
                (email_id,),
            )

        assert archive.auto_expire_trash(days=30) == 1
        assert not (temp_dir / "trash" / f"{email_id}.eml").exists()


class TestImportAndScanErrors:
    """Tests for error paths in import_email and register_scanned_email."""

    RAW = b"From: a@example.com\r\nSubject: S\r\nDate: Mon, 1 Jan 2024 10:00:00 +0000\r\n\r\nbody\r\n"

    def test_import_unreadable_file_reports_error(self, temp_dir, capsys):
        """A file that cannot be read should be counted as an error."""
        archive = EmailArchive(temp_dir, {})
        assert archive.import_email(temp_dir / "gone.eml") == "error"
        assert "Error reading" in capsys.readouterr().out

    def test_import_duplicate_is_detected(self, temp_dir):
        """Importing the same file twice should report a duplicate."""
        archive = EmailArchive(temp_dir, {})
        source = temp_dir / "incoming.eml"
        source.write_bytes(self.RAW)

        assert archive.import_email(source) == "imported"
        assert archive.import_email(source) == "duplicate"

    def test_import_with_move_deletes_source(self, temp_dir):
        """--move should remove the source file after a successful import."""
        archive = EmailArchive(temp_dir, {})
        source = temp_dir / "incoming.eml"
        source.write_bytes(self.RAW)

        assert archive.import_email(source, move=True) == "imported"
        assert not source.exists()

    def test_import_move_tolerates_undeletable_source(self, temp_dir):
        """A failure deleting the source must not fail the import."""
        from unittest.mock import patch

        archive = EmailArchive(temp_dir, {})
        source = temp_dir / "incoming.eml"
        source.write_bytes(self.RAW)

        with patch("pathlib.Path.unlink", side_effect=OSError("read-only")):
            assert archive.import_email(source, move=True) == "imported"

    def test_import_failure_is_reported(self, temp_dir, capsys):
        """An unexpected error during import should be caught and reported."""
        from unittest.mock import patch

        archive = EmailArchive(temp_dir, {})
        source = temp_dir / "incoming.eml"
        source.write_bytes(self.RAW)

        with patch.object(archive, "_save_email", side_effect=RuntimeError("boom")):
            assert archive.import_email(source) == "error"

        assert "Error importing" in capsys.readouterr().out

    def test_import_save_failure_returns_error(self, temp_dir):
        """A save that yields no path should be reported as an error."""
        from unittest.mock import patch

        archive = EmailArchive(temp_dir, {})
        source = temp_dir / "incoming.eml"
        source.write_bytes(self.RAW)

        with patch.object(archive, "_save_email", return_value=(None, None)):
            assert archive.import_email(source) == "error"

    def test_register_scanned_unreadable_file(self, temp_dir, capsys):
        """A scan of an unreadable file should be counted as an error."""
        archive = EmailArchive(temp_dir, {})
        assert archive.register_scanned_email(temp_dir / "gone.eml") == "error"
        assert "Error reading" in capsys.readouterr().out

    def test_register_scanned_failure_is_reported(self, temp_dir, capsys):
        """An unexpected error while registering should be caught."""
        from unittest.mock import patch

        archive = EmailArchive(temp_dir, {})
        filepath = temp_dir / "sitting.eml"
        filepath.write_bytes(self.RAW)

        with patch.object(archive, "_register_and_index", side_effect=RuntimeError("boom")):
            assert archive.register_scanned_email(filepath) == "error"

        assert "Error registering" in capsys.readouterr().out

    def test_register_scanned_indexes_in_place(self, temp_dir):
        """A scanned file should be registered without being moved."""
        archive = EmailArchive(temp_dir, {})
        filepath = temp_dir / "sitting.eml"
        filepath.write_bytes(self.RAW)
        labels = ["Receipts, 2026", " Work "]
        sidecar.write_labels(filepath, labels)

        assert archive.register_scanned_email(filepath) == "imported"

        assert filepath.exists()
        matches = archive.db.search('label:"Receipts, 2026"', include_unknown=True)
        assert len(matches) == 1
        assert sorted(archive.db.get_labels_for_email(matches[0][0])) == sorted(labels)
