"""Tests for EmailArchive class."""



from ownmail.archive import EmailArchive


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
        assert emails_dir == temp_dir / "accounts" / "alice@gmail.com" / "emails"

    def test_returns_legacy_path_when_no_account(self, temp_dir):
        """Test getting legacy emails dir when no account specified."""
        archive = EmailArchive(temp_dir, {})
        emails_dir = archive.get_emails_dir()
        assert emails_dir == temp_dir / "emails"


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
        archive.db.mark_downloaded("test123", "test.eml")
        archive.db.index_email(
            message_id="test123",
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
            archive.db.mark_downloaded(f"msg{i}", f"email{i}.eml")
            archive.db.index_email(
                message_id=f"msg{i}",
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

        archive.db.mark_downloaded("test123", "test.eml")
        result = archive._index_email("test123", email_path, content=sample_eml_simple)

        assert result is True
        assert archive.db.is_indexed("test123")

    def test_index_email_from_file(self, temp_dir, sample_eml_simple):
        """Test indexing email from file."""
        archive = EmailArchive(temp_dir, {})

        email_path = temp_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded("test123", "test.eml")
        result = archive._index_email("test123", email_path)

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
        filepath = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()
        assert "2024" in str(filepath)
        assert "01" in str(filepath)
        assert filepath.suffix == ".eml"

    def test_save_email_atomic_write(self, temp_dir):
        """Test that save_email uses atomic writes."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        emails_dir.mkdir()

        raw_data = b"""From: test@example.com
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body
"""
        filepath = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

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
        archive.db.mark_downloaded("msg1", "emails/test.eml", account="test@gmail.com")

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
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
        filepath = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()
        # Should use "unknown" for unparseable dates
        assert "unknown" in str(filepath)

    def test_save_email_no_date(self, temp_dir):
        """Test saving email without Date header."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        emails_dir.mkdir()

        raw_data = b"""From: test@example.com
Subject: No Date

Body
"""
        filepath = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()

    def test_save_email_creates_directories(self, temp_dir):
        """Test that _save_email creates necessary directories."""
        archive = EmailArchive(temp_dir, {})

        emails_dir = temp_dir / "emails"
        # Don't pre-create emails_dir

        raw_data = b"""From: test@example.com
Date: Mon, 15 Jan 2024 10:00:00 +0000

Body
"""
        filepath = archive._save_email(raw_data, "msg123", "test@example.com", emails_dir)

        assert filepath is not None
        assert filepath.exists()
        # Directory should have been created
        assert emails_dir.exists()


class TestIndexEmailFromContent:
    """Tests for _index_email method with content."""

    def test_index_email_from_content(self, temp_dir, sample_eml_simple):
        """Test indexing email from raw content."""
        archive = EmailArchive(temp_dir, {})

        # Create a dummy filepath (content will be used instead)
        dummy_path = temp_dir / "dummy.eml"
        dummy_path.write_bytes(sample_eml_simple)

        result = archive._index_email(
            message_id="test123",
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
            message_id="test123",
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
            message_id="bad123",
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
        mock_provider.get_new_message_ids.return_value = (["msg1"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        mock_provider.download_message.return_value = (None, None)  # Download fails

        result = archive.backup(mock_provider)

        assert result["error_count"] == 1


class TestBackupMultipleEmails:
    """Tests for backup with multiple emails."""

    def test_backup_multiple_success(self, temp_dir, capsys):
        """Test backup downloads multiple emails successfully."""
        from unittest.mock import MagicMock

        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2", "msg3"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        mock_provider.download_message.return_value = (
            b"From: test@example.com\nDate: Mon, 15 Jan 2024 10:00:00 +0000\n\nBody",
            ["INBOX"]
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
        archive.db.mark_downloaded("test123", rel_path, content_hash="abc")
        archive.db.index_email(
            message_id="test123",
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
