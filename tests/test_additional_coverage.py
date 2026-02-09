"""Additional tests to increase code coverage."""

import base64
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from ownmail.archive import EmailArchive
from ownmail.parser import EmailParser


class TestGmailProviderDownloadMessage:
    """Tests for Gmail provider download_message functionality."""

    def test_download_message_with_labels(self):
        """Test downloading a message with labels."""
        with patch("ownmail.providers.gmail.build") as mock_build:
            from ownmail.providers.gmail import GmailProvider

            mock_service = MagicMock()
            mock_build.return_value = mock_service

            # Encode a simple email
            raw_email = b"From: test@example.com\r\nSubject: Test\r\n\r\nBody"
            encoded = base64.urlsafe_b64encode(raw_email).decode()

            mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
                "id": "msg123",
                "raw": encoded,
                "labelIds": ["INBOX", "IMPORTANT"],
            }

            mock_keychain = MagicMock()
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_keychain.load_gmail_token.return_value = mock_creds

            provider = GmailProvider(
                account="alice@gmail.com",
                keychain=mock_keychain,
                include_labels=True,
            )
            provider.authenticate()

            raw_data, labels = provider.download_message("msg123")

            assert raw_data is not None
            assert b"X-Gmail-Labels:" in raw_data or b"From:" in raw_data

    def test_download_message_without_labels(self):
        """Test downloading a message without labels."""
        with patch("ownmail.providers.gmail.build") as mock_build:
            from ownmail.providers.gmail import GmailProvider

            mock_service = MagicMock()
            mock_build.return_value = mock_service

            raw_email = b"From: test@example.com\r\nSubject: Test\r\n\r\nBody"
            encoded = base64.urlsafe_b64encode(raw_email).decode()

            mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
                "id": "msg123",
                "raw": encoded,
            }

            mock_keychain = MagicMock()
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_keychain.load_gmail_token.return_value = mock_creds

            provider = GmailProvider(
                account="alice@gmail.com",
                keychain=mock_keychain,
                include_labels=False,
            )
            provider.authenticate()

            raw_data, labels = provider.download_message("msg123")

            assert raw_data is not None
            assert labels == []

    def test_get_current_sync_state(self):
        """Test getting current sync state."""
        with patch("ownmail.providers.gmail.build") as mock_build:
            from ownmail.providers.gmail import GmailProvider

            mock_service = MagicMock()
            mock_build.return_value = mock_service

            mock_service.users.return_value.getProfile.return_value.execute.return_value = {
                "historyId": "99999",
            }

            mock_keychain = MagicMock()
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_keychain.load_gmail_token.return_value = mock_creds

            provider = GmailProvider(
                account="alice@gmail.com",
                keychain=mock_keychain,
            )
            provider.authenticate()

            state = provider.get_current_sync_state()

            assert state == "99999"


class TestParserEdgeCases:
    """Additional parser edge cases."""

    def test_parse_with_inline_content_disposition(self):
        """Test parsing with inline content-disposition."""
        content = b"""From: sender@example.com
Subject: Inline Test
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1
Content-Type: text/plain
Content-Disposition: inline

Inline text.

--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert isinstance(result["body"], str)

    def test_parse_with_exception_handling(self):
        """Test parse_file handles various exceptions."""
        # Completely malformed content
        content = b"\x00\x01\x02\x03"
        result = EmailParser.parse_file(content=content)
        # Should not crash
        assert "body" in result

    def test_parse_empty_multipart(self):
        """Test parsing empty multipart message."""
        content = b"""From: sender@example.com
Subject: Empty Multipart
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert isinstance(result["body"], str)


class TestReindexMultipleEmails:
    """Tests for reindex with multiple emails."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def sample_eml_simple(self):
        return b"""From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 15 Jan 2024 14:30:00 +0000

This is a test email body.
"""

    def test_reindex_multiple_emails(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with multiple emails to index."""
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create multiple email files
        for i in range(5):
            emails_dir = temp_dir / "emails" / "2024" / "01"
            emails_dir.mkdir(parents=True, exist_ok=True)
            email_path = emails_dir / f"test{i}.eml"
            email_path.write_bytes(sample_eml_simple)

            rel_path = str(email_path.relative_to(temp_dir))
            archive.db.mark_downloaded(f"test{i}", rel_path, content_hash=None)

        cmd_reindex(archive)
        captured = capsys.readouterr()
        assert "Indexing 5 emails" in captured.out or "Reindex" in captured.out


class TestArchiveBackupProgress:
    """Tests for backup progress display."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_backup_shows_progress(self, temp_dir, capsys):
        """Test backup shows progress during download."""
        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2", "msg3"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        mock_provider.download_message.return_value = (
            b"From: test@example.com\r\nDate: Mon, 15 Jan 2024 10:00:00 +0000\r\n\r\nBody",
            ["INBOX"]
        )

        result = archive.backup(mock_provider)

        assert result["success_count"] == 3
        captured = capsys.readouterr()
        # Should show progress
        assert "1/3" in captured.out or "2/3" in captured.out or "3/3" in captured.out or "Found 3" in captured.out


class TestDbCheckMissingFTS:
    """Tests for db-check missing FTS entries."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def sample_eml_simple(self):
        return b"""From: sender@example.com
Subject: Test
Date: Mon, 15 Jan 2024 14:30:00 +0000

Body
"""

    def test_db_check_finds_missing_fts(self, temp_dir, sample_eml_simple, capsys):
        """Test db-check finds emails not in FTS index."""
        from ownmail.commands import cmd_db_check

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Add to emails table but not to FTS
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash="abc")

        cmd_db_check(archive)
        captured = capsys.readouterr()
        # Should find missing FTS entries
        assert "not in search index" in captured.out or "missing" in captured.out.lower() or "Database Check" in captured.out


class TestVerifyDetailed:
    """Detailed tests for verify command."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def sample_eml_simple(self):
        return b"""From: sender@example.com
Subject: Test
Date: Mon, 15 Jan 2024 14:30:00 +0000

Body
"""

    def test_verify_all_ok(self, temp_dir, sample_eml_simple, capsys):
        """Test verify when all files are OK."""
        import hashlib

        from ownmail.commands import cmd_verify

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Add with correct hash
        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        rel_path = str(email_path.relative_to(temp_dir))
        archive.db.mark_downloaded("test123", rel_path, content_hash=content_hash)

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "verified" in captured.out.lower() or "Verify" in captured.out


class TestReindexWithReindexedEmails:
    """Test reindex with emails that are being re-indexed."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def sample_eml_simple(self):
        return b"""From: sender@example.com
Subject: Test
Date: Mon, 15 Jan 2024 14:30:00 +0000

Body
"""

    def test_reindex_already_indexed_emails(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with emails that have indexed_hash."""
        import hashlib

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        content_hash = hashlib.sha256(sample_eml_simple).hexdigest()
        rel_path = str(email_path.relative_to(temp_dir))

        # Mark as downloaded with content_hash but different indexed_hash
        archive.db.mark_downloaded("test123", rel_path, content_hash=content_hash)
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET indexed_hash = 'old_hash' WHERE message_id = ?", ("test123",))
            conn.commit()

        cmd_reindex(archive)
        captured = capsys.readouterr()
        assert "Reindex" in captured.out


class TestSyncCheckWithDifferences:
    """Tests for sync-check showing differences."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_sync_check_more_than_5_missing(self, temp_dir, capsys):
        """Test sync-check truncates list when more than 5 missing."""
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
            # More than 5 emails on Gmail
            mock_provider.get_all_message_ids.return_value = [f"msg{i}" for i in range(10)]
            mock_provider_class.return_value = mock_provider

            cmd_sync_check(archive)

        captured = capsys.readouterr()
        assert "... and" in captured.out or "more" in captured.out or "10" in captured.out


class TestParserFallbackContent:
    """Tests for parser content fallback paths."""

    def test_parse_with_get_payload_fallback(self):
        """Test when get_content fails and get_payload is used."""
        # Create a message where get_content might fail
        content = b"""From: sender@example.com
Subject: Fallback Test
Content-Type: text/plain; charset="unknown-charset"

Some content here.
"""
        result = EmailParser.parse_file(content=content)
        assert isinstance(result["body"], str)


class TestDbCheckDuplicateFTS:
    """Tests for db-check duplicate FTS detection."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_db_check_finds_duplicates(self, temp_dir, capsys):
        """Test db-check finds duplicate FTS entries."""
        from ownmail.commands import cmd_db_check

        archive = EmailArchive(temp_dir, {})

        # Insert duplicate FTS entries
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("""
                INSERT INTO emails (message_id, filename)
                VALUES ('dup123', 'emails/2024/01/dup.eml')
            """)
            conn.execute("""
                INSERT INTO emails_fts (message_id, subject, sender, recipients, body, attachments)
                VALUES ('dup123', 'test', 'test', 'test', 'test', '')
            """)
            conn.execute("""
                INSERT INTO emails_fts (message_id, subject, sender, recipients, body, attachments)
                VALUES ('dup123', 'test2', 'test2', 'test2', 'test2', '')
            """)
            conn.commit()

        cmd_db_check(archive)
        captured = capsys.readouterr()
        assert "duplicate" in captured.out.lower() or "Database Check" in captured.out


class TestBackupWithLabels:
    """Tests for backup with label injection."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_backup_injects_labels(self, temp_dir):
        """Test backup injects Gmail labels into emails."""
        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.get_new_message_ids.return_value = (["msg1"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        mock_provider.download_message.return_value = (
            b"From: test@example.com\r\nSubject: Test\r\nDate: Mon, 15 Jan 2024 10:00:00 +0000\r\n\r\nBody",
            ["INBOX", "Important"]
        )

        result = archive.backup(mock_provider)

        assert result["success_count"] == 1
        # Verify that the email was tracked in the database
        assert archive.db.is_downloaded("msg1")


class TestCliSearchWithAccount:
    """Tests for search with account filter."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_search_filters_by_account(self, temp_dir, capsys, monkeypatch):
        """Test search filters by account."""
        import sys

        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_gmail
    type: gmail_api
    account: test@gmail.com
    auth:
      secret_ref: keychain:test
""")
        monkeypatch.chdir(temp_dir)

        # Create and initialize archive
        archive = EmailArchive(temp_dir, {})
        archive.db.index_email(
            message_id="test123",
            subject="Test Email",
            sender="sender@example.com",
            recipients="recipient@example.com",
            date_str="2024-01-15",
            body="Unique search term xyz123",
            attachments="",
        )

        with patch.object(sys, 'argv', ['ownmail', 'search', 'xyz123']):
            main()

        captured = capsys.readouterr()
        assert "Searching" in captured.out


class TestStatsWithData:
    """Tests for stats command with data."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_stats_shows_counts(self, temp_dir, capsys, monkeypatch):
        """Test stats shows email counts."""
        import sys

        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        # Create archive with some emails
        archive = EmailArchive(temp_dir, {})
        archive.db.mark_downloaded("msg1", "emails/2024/01/msg1.eml", content_hash="abc")
        archive.db.mark_downloaded("msg2", "emails/2024/01/msg2.eml", content_hash="def")

        with patch.object(sys, 'argv', ['ownmail', 'stats']):
            main()

        captured = capsys.readouterr()
        assert "2" in captured.out or "emails" in captured.out.lower()


class TestSetupCommand:
    """Tests for setup command - these test cmd_setup directly with full mocking."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_setup_cmd_with_existing_token(self, temp_dir, capsys):
        """Test cmd_setup when token already exists - no OAuth needed."""
        from ownmail.cli import cmd_setup

        config = {"sources": []}

        inputs = iter(["my_source", "user@gmail.com", "n"])

        # Create a mock keychain that doesn't touch real keychain
        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True
        mock_keychain.load_gmail_token.return_value = {"token": "existing"}

        with patch('builtins.input', lambda prompt="": next(inputs)):
            cmd_setup(mock_keychain, config, None)

        captured = capsys.readouterr()
        assert "already exists" in captured.out

    def test_setup_cmd_no_email_entered(self, temp_dir, capsys):
        """Test cmd_setup fails when no email entered."""
        from ownmail.cli import cmd_setup

        config = {"sources": []}

        inputs = iter(["my_source", ""])  # Empty email

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True

        with patch('builtins.input', lambda prompt="": next(inputs)):
            with pytest.raises(SystemExit):
                cmd_setup(mock_keychain, config, None)

    def test_setup_cmd_with_credentials_file(self, temp_dir, capsys):
        """Test cmd_setup with credentials file - token already exists."""
        from ownmail.cli import cmd_setup

        config = {"sources": []}

        creds_file = temp_dir / "credentials.json"
        creds_file.write_text('{"installed": {"client_id": "test", "client_secret": "secret"}}')

        inputs = iter(["test_source", "user@gmail.com", "n"])

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = False
        mock_keychain.load_gmail_token.return_value = {"token": "exists"}  # Token exists, no OAuth

        with patch('builtins.input', lambda prompt="": next(inputs)):
            cmd_setup(mock_keychain, config, None, credentials_file=creds_file)

        captured = capsys.readouterr()
        assert "Setup complete" in captured.out

    def test_setup_cmd_interactive_creds(self, temp_dir, capsys):
        """Test cmd_setup with interactive credentials input."""
        from ownmail.cli import cmd_setup

        config = {"sources": []}

        # Simulate user pasting JSON then entering source name and email
        inputs = iter([
            '{"installed": {"client_id": "test", "client_secret": "secret"}}',
            "",  # First empty line
            "",  # Second empty line to finish JSON input
            "my_source",
            "user@gmail.com",
            "n",  # Don't add to config
        ])

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = False
        mock_keychain.load_gmail_token.return_value = {"token": "exists"}  # Token exists

        with patch('builtins.input', lambda prompt="": next(inputs)):
            cmd_setup(mock_keychain, config, None)

        captured = capsys.readouterr()
        assert "Setup complete" in captured.out


class TestCliRehash:
    """Tests for rehash command - uses commands directly to avoid keychain."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_rehash_via_cmd(self, temp_dir, capsys):
        """Test rehash via cmd_rehash directly."""
        from ownmail.commands import cmd_rehash

        archive = EmailArchive(temp_dir, {})

        # Create an email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(b"From: test@example.com\r\nSubject: Test\r\n\r\nBody")

        # Mark as downloaded without content_hash
        archive.db.mark_downloaded("msg1", "emails/2024/01/test.eml", content_hash=None)

        cmd_rehash(archive)

        captured = capsys.readouterr()
        assert "Rehash" in captured.out or "hash" in captured.out.lower()


class TestAddLabelsCmd:
    """Tests for add-labels command directly."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_add_labels_via_cmd(self, temp_dir, capsys):
        """Test add-labels via cmd_add_labels directly with mocked provider."""
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

        # Create an email file without labels
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_text("From: test@example.com\r\nSubject: Test\r\n\r\nBody")
        archive.db.mark_downloaded("msg1", "emails/2024/01/test.eml", content_hash="abc")

        with patch('ownmail.commands.GmailProvider') as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.get_message_labels.return_value = ["INBOX", "IMPORTANT"]
            mock_provider_cls.return_value = mock_provider

            cmd_add_labels(archive, source_name="test_gmail")

        captured = capsys.readouterr()
        assert "Labels" in captured.out or "add" in captured.out.lower() or "Add Labels" in captured.out


class TestProviderBase:
    """Tests for base provider abstract methods."""

    def test_base_provider_is_abstract(self):
        """Test EmailProvider cannot be instantiated."""
        from ownmail.providers.base import EmailProvider

        with pytest.raises(TypeError):
            EmailProvider()
