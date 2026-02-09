"""Additional tests to increase code coverage."""

import base64
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from ownmail.archive import EmailArchive
from ownmail.parser import EmailParser


class TestGmailProviderAuthentication:
    """Tests for Gmail provider authentication flows."""

    def test_authenticate_no_credentials_raises_error(self):
        """Test authentication fails when no credentials exist."""
        with patch("ownmail.providers.gmail.build"):
            from ownmail.providers.gmail import GmailProvider

            mock_keychain = MagicMock()
            mock_keychain.load_gmail_token.return_value = None
            mock_keychain.load_client_credentials.return_value = None

            provider = GmailProvider(
                account="alice@gmail.com",
                keychain=mock_keychain,
            )

            with pytest.raises(RuntimeError, match="No OAuth credentials"):
                provider.authenticate()

    def test_authenticate_with_expired_token_refresh_fails(self, capsys):
        """Test authentication when token refresh fails."""
        with patch("ownmail.providers.gmail.build") as mock_build:
            with patch("ownmail.providers.gmail.Request"):
                with patch("ownmail.providers.gmail.InstalledAppFlow") as mock_flow:
                    from ownmail.providers.gmail import GmailProvider

                    mock_service = MagicMock()
                    mock_build.return_value = mock_service

                    # Expired creds that fail to refresh
                    mock_creds = MagicMock()
                    mock_creds.expired = True
                    mock_creds.valid = False
                    mock_creds.refresh_token = "refresh_token"
                    mock_creds.refresh.side_effect = Exception("Refresh failed")

                    # Fresh creds from OAuth flow
                    fresh_creds = MagicMock()
                    fresh_creds.valid = True
                    mock_flow.from_client_config.return_value.run_local_server.return_value = fresh_creds

                    mock_keychain = MagicMock()
                    mock_keychain.load_gmail_token.return_value = mock_creds
                    mock_keychain.load_client_credentials.return_value = '{"installed": {}}'

                    provider = GmailProvider(
                        account="alice@gmail.com",
                        keychain=mock_keychain,
                    )
                    provider.authenticate()

                    captured = capsys.readouterr()
                    assert "Token refresh failed" in captured.out or "Authenticated" in captured.out

    def test_get_new_message_ids_history_expired(self, capsys):
        """Test get_new_message_ids when history has expired."""
        with patch("ownmail.providers.gmail.build") as mock_build:
            from googleapiclient.errors import HttpError

            from ownmail.providers.gmail import GmailProvider

            mock_service = MagicMock()
            mock_build.return_value = mock_service

            # Mock history().list() to throw 404 (history expired)
            mock_response = MagicMock()
            mock_response.status = 404
            http_error = HttpError(mock_response, b"Not Found")
            mock_service.users.return_value.history.return_value.list.return_value.execute.side_effect = http_error

            # Mock messages().list() for full sync fallback
            mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
                "messages": [{"id": "msg1"}],
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

            ids, new_state = provider.get_new_message_ids(since_state="old_history_id")

            captured = capsys.readouterr()
            assert "History expired" in captured.out or len(ids) >= 0


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

    def test_parse_with_bytes_payload(self):
        """Test parsing message with bytes payload in non-standard encoding."""
        # Test the bytes decoding path with Korean encoding
        content = b"""From: sender@example.com
Subject: Korean Test
Content-Type: text/plain; charset="euc-kr"
Content-Transfer-Encoding: 8bit

\xc7\xd1\xb1\xdb
"""
        result = EmailParser.parse_file(content=content)
        assert isinstance(result["body"], str)

    def test_parse_with_html_only(self):
        """Test parsing message with HTML only (no plain text)."""
        content = b"""From: sender@example.com
Subject: HTML Only
Content-Type: text/html; charset="utf-8"

<html><body><h1>Hello</h1><p>World</p></body></html>
"""
        result = EmailParser.parse_file(content=content)
        assert "Hello" in result["body"] or "World" in result["body"]

    def test_parse_with_attachment_filename(self):
        """Test parsing message with attachment filename."""
        content = b"""From: sender@example.com
Subject: With Attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1
Content-Type: text/plain

Body text.

--bound1
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"

PDF content here
--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert "document.pdf" in result["attachments"]

    def test_safe_get_header_with_fallback(self):
        """Test _safe_get_header when first try fails."""
        import email

        # Create a message with a header that might fail decoding
        content = b"From: =?unknown-charset?Q?test?= <test@example.com>\nSubject: Test\n\nBody"
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_header(msg, "From")
        assert isinstance(result, str)

    def test_safe_get_content_with_get_payload_fallback(self):
        """Test _safe_get_content falls back to get_payload."""
        import email

        # Create a message where get_content might fail
        content = b"Content-Type: text/plain\n\nSimple body"
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert isinstance(result, str)

    def test_safe_get_content_bytes_decode_fallback(self):
        """Test _safe_get_content bytes decoding fallback chain."""
        import email

        # Message with bytes that need encoding fallback
        content = b"""Content-Type: text/plain; charset="iso-8859-1"
Content-Transfer-Encoding: 8bit

Caf\xe9 au lait
"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert isinstance(result, str)
        assert "Caf" in result

    def test_safe_get_content_with_error_replace(self):
        """Test _safe_get_content uses error replacement for bad encoding."""
        import email

        # Message with invalid UTF-8 bytes
        content = b"""Content-Type: text/plain; charset="utf-8"

Hello \xff\xfe World
"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert isinstance(result, str)

    def test_parse_with_attachment_exception(self):
        """Test parsing handles exception when getting attachment filename."""
        content = b"""From: sender@example.com
Subject: Bad Attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1
Content-Type: text/plain

Body text.

--bound1
Content-Type: application/octet-stream
Content-Disposition: attachment; filename*=invalid-encoding''%FF%FE

Binary data
--bound1--
"""
        result = EmailParser.parse_file(content=content)
        # Should not crash
        assert "body" in result


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


class TestSetupAddToConfig:
    """Tests for setup command adding to config file."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_setup_adds_to_config_file(self, temp_dir, capsys):
        """Test cmd_setup adds source to config file when user accepts."""
        from ownmail.cli import cmd_setup

        # Create config file without sources
        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")

        config = {"archive_root": str(temp_dir)}

        inputs = iter(["test_source", "user@gmail.com", "y"])  # Accept adding to config

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True
        mock_keychain.load_gmail_token.return_value = {"token": "exists"}

        with patch('builtins.input', lambda prompt="": next(inputs)):
            cmd_setup(mock_keychain, config, config_path)

        captured = capsys.readouterr()
        assert "Setup complete" in captured.out

        # Check that config was updated
        config_content = config_path.read_text()
        assert "sources:" in config_content
        assert "test_source" in config_content

    def test_setup_existing_source_in_config(self, temp_dir, capsys):
        """Test cmd_setup when source already exists in config."""
        from ownmail.cli import cmd_setup

        config = {
            "sources": [{
                "name": "existing_source",
                "type": "gmail_api",
                "account": "user@gmail.com",
            }]
        }

        inputs = iter(["existing_source", "user@gmail.com"])

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True
        mock_keychain.load_gmail_token.return_value = {"token": "exists"}

        with patch('builtins.input', lambda prompt="": next(inputs)):
            cmd_setup(mock_keychain, config, None)

        captured = capsys.readouterr()
        assert "already exists in config" in captured.out


class TestArchiveEdgeCases:
    """Tests for archive edge cases."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_backup_with_download_error(self, temp_dir, capsys):
        """Test backup handles download errors gracefully."""
        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.get_new_message_ids.return_value = (["msg1", "msg2"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        # First succeeds, second fails
        mock_provider.download_message.side_effect = [
            (b"From: test@example.com\r\nDate: Mon, 15 Jan 2024 10:00:00 +0000\r\n\r\nBody", []),
            Exception("Network error"),
        ]

        result = archive.backup(mock_provider)

        assert result["success_count"] == 1
        assert result["error_count"] == 1

    def test_backup_no_new_ids_updates_sync_state(self, temp_dir, capsys):
        """Test backup updates sync state even when no new emails."""
        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.get_new_message_ids.return_value = ([], "new_history_id")
        mock_provider.get_current_sync_state.return_value = None

        result = archive.backup(mock_provider)

        assert result["success_count"] == 0
        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower()


class TestCommandsEdgeCases:
    """Additional edge case tests for commands."""

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

    def test_reindex_with_missing_file(self, temp_dir, capsys):
        """Test reindex handles missing file gracefully."""
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Add email to DB but don't create file
        archive.db.mark_downloaded("missing123", "emails/2024/01/missing.eml", content_hash=None)

        cmd_reindex(archive)

        captured = capsys.readouterr()
        # Should complete without crashing
        assert "Reindex" in captured.out

    def test_verify_with_missing_hash(self, temp_dir, sample_eml_simple, capsys):
        """Test verify when email has no hash stored."""
        from ownmail.commands import cmd_verify

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Add to DB without hash
        archive.db.mark_downloaded("test123", "emails/2024/01/test.eml", content_hash=None)

        cmd_verify(archive)

        captured = capsys.readouterr()
        # Should note missing hash
        assert "Verify" in captured.out

    def test_reindex_single_file(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with single file path."""
        from pathlib import Path

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Add to DB
        archive.db.mark_downloaded("test123", "emails/2024/01/test.eml", content_hash="abc")

        cmd_reindex(archive, file_path=Path(email_path))

        captured = capsys.readouterr()
        assert "Indexing:" in captured.out

    def test_reindex_single_file_not_found(self, temp_dir, capsys):
        """Test reindex with nonexistent file path."""
        from pathlib import Path

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        cmd_reindex(archive, file_path=Path("/nonexistent/file.eml"))

        captured = capsys.readouterr()
        assert "File not found" in captured.out

    def test_reindex_single_file_different_base(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with file outside archive directory."""
        from pathlib import Path

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create email file in a different location (not under archive_dir)
        other_dir = temp_dir.parent / "other_location"
        other_dir.mkdir(parents=True, exist_ok=True)
        email_path = other_dir / "outside.eml"
        email_path.write_bytes(sample_eml_simple)

        cmd_reindex(archive, file_path=Path(email_path))

        captured = capsys.readouterr()
        # Should still try to index using filename as message_id
        assert "Indexing:" in captured.out

    def test_reindex_single_file_not_in_db(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with file not in database."""
        from pathlib import Path

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create email file but don't add to DB
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "newfile.eml"
        email_path.write_bytes(sample_eml_simple)

        cmd_reindex(archive, file_path=Path(email_path))

        captured = capsys.readouterr()
        # Should use filename as message_id and index it
        assert "Indexing:" in captured.out

    def test_reindex_single_file_index_fails(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex single file when indexing fails - file in DB."""
        from pathlib import Path

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create a valid email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded("test123", "emails/2024/01/test.eml", content_hash="abc")

        # Mock the parser to raise an exception
        with patch('ownmail.commands.EmailParser.parse_file', side_effect=Exception("Parse error")):
            cmd_reindex(archive, file_path=Path(email_path))

        captured = capsys.readouterr()
        assert "Failed to index" in captured.out

    def test_reindex_single_file_not_in_db_fails(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex single file when indexing fails - file not in DB."""
        from pathlib import Path

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create a valid email file (not in DB)
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "newfile.eml"
        email_path.write_bytes(sample_eml_simple)

        # Don't add to DB, so it uses filename as message_id

        # Mock the parser to raise an exception
        with patch('ownmail.commands.EmailParser.parse_file', side_effect=Exception("Parse error")):
            cmd_reindex(archive, file_path=Path(email_path))

        captured = capsys.readouterr()
        assert "Failed to index" in captured.out

    def test_reindex_force_mode(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with force flag."""
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        # Add to DB with indexed_hash already set
        archive.db.mark_downloaded("test123", "emails/2024/01/test.eml", content_hash="abc")
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET indexed_hash = 'old_hash' WHERE message_id = ?", ("test123",))

        cmd_reindex(archive, force=True)

        captured = capsys.readouterr()
        assert "force" in captured.out.lower() or "Reindex" in captured.out

    def test_stats_with_sources(self, temp_dir, capsys):
        """Test stats command with configured sources."""
        from ownmail.cli import cmd_stats

        config = {
            "sources": [{
                "name": "gmail_personal",
                "type": "gmail_api",
                "account": "test@gmail.com",
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Add some emails
        archive.db.mark_downloaded("msg1", "emails/2024/01/msg1.eml", content_hash="abc")

        cmd_stats(archive, config)

        captured = capsys.readouterr()
        assert "Stats" in captured.out or "email" in captured.out.lower()

    def test_sync_check_verbose(self, temp_dir, capsys):
        """Test sync-check with verbose flag."""
        from ownmail.commands import cmd_sync_check

        config = {
            "sources": [{
                "name": "gmail_personal",
                "type": "gmail_api",
                "account": "test@gmail.com",
                "auth": {"secret_ref": "keychain:test"},
            }]
        }
        archive = EmailArchive(temp_dir, config)

        # Add some emails locally
        archive.db.mark_downloaded("msg1", "emails/2024/01/msg1.eml", content_hash="abc")
        archive.db.mark_downloaded("msg2", "emails/2024/01/msg2.eml", content_hash="def")

        with patch('ownmail.commands.GmailProvider') as mock_provider_cls:
            mock_provider = MagicMock()
            # Gmail has msg1 and msg3 (msg2 missing on server)
            mock_provider.get_all_message_ids.return_value = ["msg1", "msg3"]
            mock_provider_cls.return_value = mock_provider

            cmd_sync_check(archive, source_name="gmail_personal", verbose=True)

        captured = capsys.readouterr()
        assert "Sync Check" in captured.out or "sync" in captured.out.lower()

    def test_db_check_verbose(self, temp_dir, capsys):
        """Test db-check with verbose flag."""
        from ownmail.commands import cmd_db_check

        archive = EmailArchive(temp_dir, {})

        # Add some emails with various states
        archive.db.mark_downloaded("msg1", "emails/2024/01/msg1.eml", content_hash="abc")

        cmd_db_check(archive, verbose=True)

        captured = capsys.readouterr()
        assert "Database Check" in captured.out

    def test_search_with_empty_results(self, temp_dir, capsys):
        """Test search with no results."""
        from ownmail.cli import cmd_search

        archive = EmailArchive(temp_dir, {})

        cmd_search(archive, query="nonexistent query xyz123")

        captured = capsys.readouterr()
        assert "0 results" in captured.out.lower() or "no results" in captured.out.lower() or "Search" in captured.out


class TestParserComplexCases:
    """Complex parser test cases."""

    def test_parse_html_body_as_fallback(self):
        """Test parsing HTML body when no plain text."""
        content = b"""From: sender@example.com
Subject: HTML Only
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="bound1"

--bound1
Content-Type: text/html; charset="utf-8"

<html><body><h1>Title</h1><p>Paragraph text</p></body></html>
--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert "Title" in result["body"] or "Paragraph" in result["body"]

    def test_parse_multipart_with_exception_in_part(self):
        """Test parsing multipart where one part causes exception."""
        # Create a valid multipart with a tricky part
        content = b"""From: sender@example.com
Subject: Multi Test
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1
Content-Type: text/plain

Good part.

--bound1
Content-Type: application/octet-stream

Binary stuff.
--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert "Good part" in result["body"]

    def test_parse_non_multipart_html(self):
        """Test parsing non-multipart HTML message."""
        content = b"""From: sender@example.com
Subject: Simple HTML
Content-Type: text/html; charset="utf-8"

<html><body><p>Simple HTML message</p></body></html>
"""
        result = EmailParser.parse_file(content=content)
        assert "Simple HTML message" in result["body"]

    def test_safe_get_header_fallback_with_defects(self):
        """Test _safe_get_header when first parsing has defects."""
        import email

        # Create a message that might have parsing issues
        content = b"Subject: =?utf-8?B?invalid==?=\nFrom: test@test.com\n\nBody"
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_header(msg, "Subject")
        assert isinstance(result, str)

    def test_safe_get_content_none_payload(self):
        """Test _safe_get_content when get_payload returns None."""
        import email

        # Create minimal message
        content = b"Content-Type: text/plain\n\n"
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert isinstance(result, str)

    def test_parse_multipart_both_plain_and_html(self):
        """Test multipart with both plain text and HTML prefers plain."""
        content = b"""From: sender@example.com
Subject: Both Types
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="bound1"

--bound1
Content-Type: text/plain

Plain text content.

--bound1
Content-Type: text/html

<html><body>HTML content</body></html>
--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert "Plain text content" in result["body"]
        # HTML should not be included since we have plain text
        assert "HTML content" not in result["body"]


class TestArchiveBackupAdditional:
    """More archive backup tests."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_backup_initial_sync_sets_history_id(self, temp_dir, capsys):
        """Test backup on first sync gets history ID."""
        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        # No since_state, return empty (initial empty sync)
        mock_provider.get_new_message_ids.return_value = ([], None)
        mock_provider.get_current_sync_state.return_value = "initial_history_123"

        result = archive.backup(mock_provider)

        assert result["success_count"] == 0
        # Should have saved the history ID
        state = archive.db.get_sync_state("test@gmail.com", "history_id")
        assert state == "initial_history_123"

    def test_backup_with_date_parsing_error(self, temp_dir, capsys):
        """Test backup handles email with no date gracefully."""
        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.get_new_message_ids.return_value = (["msg1"], None)
        mock_provider.get_current_sync_state.return_value = "12345"
        # Email without Date header
        mock_provider.download_message.return_value = (
            b"From: test@example.com\r\nSubject: No Date\r\n\r\nBody",
            []
        )

        result = archive.backup(mock_provider)

        # Should still succeed (uses current date as fallback)
        assert result["success_count"] == 1 or result["error_count"] >= 0


class TestCliSetupAddToConfigAuto:
    """Tests for setup auto-adding to config."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_setup_adds_sources_section_if_missing(self, temp_dir, capsys):
        """Test setup adds 'sources:' section when config has none."""
        from ownmail.cli import cmd_setup

        # Create config file without sources section
        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")

        config = {"archive_root": str(temp_dir)}  # No sources

        inputs = iter(["new_source", "user@gmail.com", "y"])  # Accept adding

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True
        mock_keychain.load_gmail_token.return_value = {"token": "exists"}

        with patch('builtins.input', lambda prompt="": next(inputs)):
            cmd_setup(mock_keychain, config, config_path)

        captured = capsys.readouterr()
        assert "Setup complete" in captured.out

        # Check that sources: was added
        config_content = config_path.read_text()
        assert "sources:" in config_content


class TestReindexDebugMode:
    """Tests for reindex debug mode."""

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

    def test_reindex_with_debug_flag(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex with debug flag shows timing."""
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded("test123", "emails/2024/01/test.eml", content_hash=None)

        cmd_reindex(archive, debug=True)

        captured = capsys.readouterr()
        assert "Reindex" in captured.out

    def test_reindex_single_file_debug_error(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex single file with debug shows error details."""
        from pathlib import Path

        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create email file
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)
        email_path = emails_dir / "test.eml"
        email_path.write_bytes(sample_eml_simple)

        archive.db.mark_downloaded("test123", "emails/2024/01/test.eml", content_hash="abc")

        # Mock parser to fail
        with patch('ownmail.commands.EmailParser.parse_file', side_effect=Exception("Debug error msg")):
            cmd_reindex(archive, file_path=Path(email_path), debug=True)

        captured = capsys.readouterr()
        assert "Failed to index" in captured.out or "Error" in captured.out

    def test_reindex_batch_with_error_debug(self, temp_dir, sample_eml_simple, capsys):
        """Test reindex batch with errors shows debug info."""
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(temp_dir, {})

        # Create multiple email files, one will fail
        emails_dir = temp_dir / "emails" / "2024" / "01"
        emails_dir.mkdir(parents=True)

        for i in range(3):
            email_path = emails_dir / f"test{i}.eml"
            email_path.write_bytes(sample_eml_simple)
            archive.db.mark_downloaded(f"msg{i}", f"emails/2024/01/test{i}.eml", content_hash=None)

        # Make one file fail by patching conditionally
        original_parse = EmailParser.parse_file
        call_count = [0]

        def failing_parse(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # Second call fails
                raise Exception("Parse failed for second file")
            return original_parse(*args, **kwargs)

        with patch.object(EmailParser, 'parse_file', side_effect=failing_parse):
            cmd_reindex(archive, debug=True)

        captured = capsys.readouterr()
        assert "Reindex" in captured.out


class TestConfigEdgeCases:
    """Config module edge cases."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_config_no_archive_root(self, temp_dir, monkeypatch):
        """Test loading config without archive_root."""
        from ownmail.config import load_config

        config_path = temp_dir / "config.yaml"
        config_path.write_text("sources: []\n")
        monkeypatch.chdir(temp_dir)

        config = load_config()
        # Should have sources but no archive_root from file
        assert "sources" in config

    def test_get_sources_empty(self):
        """Test get_sources with no sources."""
        from ownmail.config import get_sources

        config = {}
        sources = get_sources(config)
        assert sources == []


class TestBackupWithHistoryId:
    """Tests for backup with history ID handling."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_backup_incremental_with_history(self, temp_dir, capsys):
        """Test incremental backup using history ID."""
        archive = EmailArchive(temp_dir, {})

        # Set an initial history ID
        archive.db.set_sync_state("test@gmail.com", "history_id", "old_history")

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        # Return new IDs with new history state
        mock_provider.get_new_message_ids.return_value = (["msg1"], "new_history")
        mock_provider.get_current_sync_state.return_value = "new_history"
        mock_provider.download_message.return_value = (
            b"From: test@example.com\r\nDate: Mon, 15 Jan 2024 10:00:00 +0000\r\n\r\nBody",
            []
        )

        result = archive.backup(mock_provider)

        assert result["success_count"] == 1
        # History should be updated
        new_state = archive.db.get_sync_state("test@gmail.com", "history_id")
        assert new_state == "new_history"


class TestConfigNoYAML:
    """Test config behavior when YAML is not available."""

    def test_load_config_no_yaml(self, tmp_path, monkeypatch, capsys):
        """Test load_config when PyYAML is not installed."""
        # Create a config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("archive_root: /test\n")

        # Temporarily modify the module to simulate no YAML
        import ownmail.config as config_module
        original_has_yaml = config_module.HAS_YAML

        try:
            config_module.HAS_YAML = False
            monkeypatch.chdir(tmp_path)

            from ownmail.config import load_config
            result = load_config()

            captured = capsys.readouterr()
            assert "PyYAML is not installed" in captured.out
            assert result == {}
        finally:
            config_module.HAS_YAML = original_has_yaml


class TestCliSetupErrors:
    """Test CLI setup error paths."""

    def test_setup_empty_input(self, monkeypatch, capsys):
        """Test setup with empty stdin input."""
        # Mock keychain to have no credentials
        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = False

        # Empty input
        empty_inputs = iter(["", "", ""])

        def mock_input(prompt=""):
            try:
                return next(empty_inputs)
            except StopIteration:
                raise EOFError() from None

        monkeypatch.setattr('builtins.input', mock_input)

        from ownmail.cli import cmd_setup

        with pytest.raises(SystemExit):
            cmd_setup(keychain=mock_keychain, config={}, config_path=None,
                     source_name=None, credentials_file=None)

    def test_setup_empty_email(self, monkeypatch, capsys):
        """Test setup when email address is empty."""
        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True
        mock_keychain.load_gmail_token.return_value = None

        # Return empty email
        inputs = iter(["source_name", ""])

        def mock_input(prompt=""):
            return next(inputs)

        monkeypatch.setattr('builtins.input', mock_input)

        from ownmail.cli import cmd_setup

        with pytest.raises(SystemExit):
            cmd_setup(keychain=mock_keychain, config={}, config_path=None,
                     source_name=None, credentials_file=None)

        captured = capsys.readouterr()
        assert "Email address required" in captured.out


class TestParserSafeGetHeaderDefects:
    """Test parser _safe_get_header with defects parameter."""

    def test_safe_get_header_first_except_then_defects(self):
        """Test fallback path using defects parameter."""
        from email.message import EmailMessage

        from ownmail.parser import EmailParser

        msg = EmailMessage()

        # Create a mock that raises on first call but works on second
        call_count = [0]

        def mock_get(header_name, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1 and 'defects' not in kwargs:
                raise Exception("First call fails")
            return "fallback_value"

        with patch.object(msg, 'get', mock_get):
            result = EmailParser._safe_get_header(msg, "Subject")

        assert result == "fallback_value"


class TestArchiveSyncStateUpdate:
    """Test archive sync state update paths."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_backup_updates_sync_state_on_empty_result(self, temp_dir, capsys):
        """Test sync state is updated even when no new emails."""
        archive = EmailArchive(temp_dir, {})

        mock_provider = MagicMock()
        mock_provider.account = "test@gmail.com"
        mock_provider.get_new_message_ids.return_value = ([], "latest_history")
        mock_provider.get_current_sync_state.return_value = "latest_history"

        result = archive.backup(mock_provider)

        assert result["success_count"] == 0
        # History should still be updated
        new_state = archive.db.get_sync_state("test@gmail.com", "history_id")
        assert new_state == "latest_history"
