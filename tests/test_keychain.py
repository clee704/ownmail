"""Tests for KeychainStorage class."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from ownmail import KeychainStorage


class TestKeychainStorage:
    """Tests for keychain storage operations."""

    def test_save_and_load_client_credentials(self):
        """Test saving and loading client credentials."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            storage = KeychainStorage("test-service")

            valid_creds = json.dumps({"installed": {"client_id": "test123"}})
            storage.save_client_credentials("gmail", valid_creds)

            mock_keyring.set_password.assert_called_once()

    def test_save_invalid_json_raises(self):
        """Test that invalid JSON raises an error."""
        with patch("ownmail.keychain.keyring"):
            storage = KeychainStorage("test-service")

            try:
                storage.save_client_credentials("gmail", "not valid json {{{")
                raise AssertionError("Should have raised ValueError")
            except ValueError as e:
                assert "Invalid JSON" in str(e)

    def test_save_invalid_credentials_format_raises(self):
        """Test that credentials without installed/web key raises."""
        with patch("ownmail.keychain.keyring"):
            storage = KeychainStorage("test-service")

            try:
                storage.save_client_credentials("gmail", '{"wrong_key": "value"}')
                raise AssertionError("Should have raised ValueError")
            except ValueError as e:
                assert "Invalid credentials format" in str(e)

    def test_has_client_credentials(self):
        """Test checking if credentials exist."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = '{"installed": {}}'
            storage = KeychainStorage("test-service")

            assert storage.has_client_credentials("gmail") is True

            mock_keyring.get_password.return_value = None
            assert storage.has_client_credentials("gmail") is False

    def test_delete_client_credentials(self):
        """Test deleting credentials."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            storage = KeychainStorage("test-service")
            storage.delete_client_credentials("gmail")

            mock_keyring.delete_password.assert_called_once()

    def test_delete_nonexistent_credentials_no_error(self):
        """Test that deleting nonexistent credentials doesn't raise."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            # Create a proper exception class
            class MockPasswordDeleteError(Exception):
                pass

            mock_keyring.errors.PasswordDeleteError = MockPasswordDeleteError
            mock_keyring.delete_password.side_effect = MockPasswordDeleteError()

            storage = KeychainStorage("test-service")
            # Should not raise
            storage.delete_client_credentials("gmail")


class TestGmailTokenStorage:
    """Tests for Gmail OAuth token storage."""

    def test_save_gmail_token(self, capsys):
        """Test saving Gmail OAuth token."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            from unittest.mock import MagicMock
            storage = KeychainStorage("test-service")

            # Create mock credentials
            mock_creds = MagicMock()
            mock_creds.token = "access_token_123"
            mock_creds.refresh_token = "refresh_token_456"
            mock_creds.token_uri = "https://oauth2.googleapis.com/token"
            mock_creds.client_id = "client_id_789"
            mock_creds.client_secret = "client_secret_abc"
            mock_creds.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

            storage.save_gmail_token("alice@gmail.com", mock_creds)

            mock_keyring.set_password.assert_called_once()
            call_args = mock_keyring.set_password.call_args
            assert call_args[0][1] == "oauth-token/alice@gmail.com"

            captured = capsys.readouterr()
            assert "alice@gmail.com" in captured.out

    def test_load_gmail_token_success(self):
        """Test loading Gmail OAuth token."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            token_data = json.dumps({
                "token": "access_token_123",
                "refresh_token": "refresh_token_456",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "client_id_789",
                "client_secret": "client_secret_abc",
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            })
            mock_keyring.get_password.return_value = token_data

            storage = KeychainStorage("test-service")
            creds = storage.load_gmail_token("alice@gmail.com")

            assert creds is not None
            assert creds.token == "access_token_123"
            assert creds.refresh_token == "refresh_token_456"

    def test_load_gmail_token_not_found(self):
        """Test loading nonexistent Gmail token returns None."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None

            storage = KeychainStorage("test-service")
            creds = storage.load_gmail_token("nobody@gmail.com")

            assert creds is None

    def test_load_gmail_token_invalid_json(self, capsys):
        """Test loading corrupted token data returns None."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "not valid json {{{"

            storage = KeychainStorage("test-service")
            creds = storage.load_gmail_token("alice@gmail.com")

            assert creds is None
            captured = capsys.readouterr()
            assert "Warning" in captured.out or creds is None

    def test_delete_gmail_token(self):
        """Test deleting Gmail OAuth token."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            storage = KeychainStorage("test-service")
            storage.delete_gmail_token("alice@gmail.com")

            mock_keyring.delete_password.assert_called_once()
            call_args = mock_keyring.delete_password.call_args
            assert call_args[0][1] == "oauth-token/alice@gmail.com"


class TestImapPasswordStorage:
    """Tests for IMAP password storage."""

    def test_save_imap_password(self):
        """Test saving IMAP password."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            storage = KeychainStorage("test-service")
            storage.save_imap_password("alice@company.com", "secret123")

            mock_keyring.set_password.assert_called_once()
            call_args = mock_keyring.set_password.call_args
            assert call_args[0][1] == "imap-password/alice@company.com"
            assert call_args[0][2] == "secret123"

    def test_load_imap_password(self):
        """Test loading IMAP password."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "secret123"

            storage = KeychainStorage("test-service")
            password = storage.load_imap_password("alice@company.com")

            assert password == "secret123"

    def test_load_imap_password_not_found(self):
        """Test loading nonexistent IMAP password returns None."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None

            storage = KeychainStorage("test-service")
            password = storage.load_imap_password("nobody@company.com")

            assert password is None

    def test_delete_imap_password(self):
        """Test deleting IMAP password."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            storage = KeychainStorage("test-service")
            storage.delete_imap_password("alice@company.com")

            mock_keyring.delete_password.assert_called_once()


class TestLegacyCompatibility:
    """Tests for legacy v0.1.x compatibility methods."""

    def test_load_legacy_token(self):
        """Test loading legacy single-account OAuth token."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            token_data = json.dumps({
                "token": "legacy_token",
                "refresh_token": "legacy_refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "legacy_client_id",
                "client_secret": "legacy_secret",
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            })
            mock_keyring.get_password.return_value = token_data

            storage = KeychainStorage("test-service")
            creds = storage.load_legacy_token()

            assert creds is not None
            assert creds.token == "legacy_token"
            # Verify the legacy key was used
            mock_keyring.get_password.assert_called_with("test-service", "oauth-token")

    def test_load_legacy_token_not_found(self):
        """Test loading legacy token when not present."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None

            storage = KeychainStorage("test-service")
            creds = storage.load_legacy_token()

            assert creds is None

    def test_load_legacy_token_corrupted(self):
        """Test loading corrupted legacy token returns None."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "invalid json"

            storage = KeychainStorage("test-service")
            creds = storage.load_legacy_token()

            assert creds is None

    def test_load_legacy_client_credentials(self):
        """Test loading legacy client credentials."""
        with patch("ownmail.keychain.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = '{"installed": {}}'

            storage = KeychainStorage("test-service")
            creds = storage.load_legacy_client_credentials()

            assert creds == '{"installed": {}}'
            mock_keyring.get_password.assert_called_with("test-service", "client-credentials")
