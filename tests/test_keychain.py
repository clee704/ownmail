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
        with patch("ownmail.keyring") as mock_keyring:
            storage = KeychainStorage("test-service")

            valid_creds = json.dumps({"installed": {"client_id": "test123"}})
            storage.save_client_credentials(valid_creds)

            mock_keyring.set_password.assert_called_once()

    def test_save_invalid_json_raises(self):
        """Test that invalid JSON raises an error."""
        with patch("ownmail.keyring"):
            storage = KeychainStorage("test-service")

            try:
                storage.save_client_credentials("not valid json {{{")
                raise AssertionError("Should have raised ValueError")
            except ValueError as e:
                assert "Invalid JSON" in str(e)

    def test_save_invalid_credentials_format_raises(self):
        """Test that credentials without installed/web key raises."""
        with patch("ownmail.keyring"):
            storage = KeychainStorage("test-service")

            try:
                storage.save_client_credentials('{"wrong_key": "value"}')
                raise AssertionError("Should have raised ValueError")
            except ValueError as e:
                assert "Invalid credentials format" in str(e)

    def test_has_client_credentials(self):
        """Test checking if credentials exist."""
        with patch("ownmail.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = '{"installed": {}}'
            storage = KeychainStorage("test-service")

            assert storage.has_client_credentials() is True

            mock_keyring.get_password.return_value = None
            assert storage.has_client_credentials() is False

    def test_delete_client_credentials(self):
        """Test deleting credentials."""
        with patch("ownmail.keyring") as mock_keyring:
            storage = KeychainStorage("test-service")
            storage.delete_client_credentials()

            mock_keyring.delete_password.assert_called_once()

    def test_delete_nonexistent_credentials_no_error(self):
        """Test that deleting nonexistent credentials doesn't raise."""
        with patch("ownmail.keyring") as mock_keyring:
            # Create a proper exception class
            class MockPasswordDeleteError(Exception):
                pass

            mock_keyring.errors.PasswordDeleteError = MockPasswordDeleteError
            mock_keyring.delete_password.side_effect = MockPasswordDeleteError()

            storage = KeychainStorage("test-service")
            # Should not raise
            storage.delete_client_credentials()
