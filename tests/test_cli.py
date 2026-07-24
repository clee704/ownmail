"""Tests for CLI module."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from ownmail.cli import (
    cmd_search,
    cmd_sources_list,
    cmd_stats,
)
from ownmail.database import ArchiveDatabase


def _eid(provider_id, account=""):
    return ArchiveDatabase.make_email_id(account, provider_id)


class TestCmdSearch:
    """Tests for search command."""

    def test_search_no_results(self, temp_dir, capsys):
        """Test search with no results."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir, {})
        cmd_search(archive, "nonexistent_query_xyz123")
        captured = capsys.readouterr()
        assert "No results found" in captured.out

    def test_search_with_results(self, temp_dir, capsys):
        """Test search with results."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(temp_dir, {})

        # Add an indexed email
        archive.db.mark_downloaded(_eid("test123"), "test123", "test.eml", email_date="2024-01-15T00:00:00")
        archive.db.index_email(
            email_id=_eid("test123"),
            subject="Test Invoice",
            sender="billing@example.com",
            recipients="user@test.com",
            date_str="2024-01-15",
            body="This is a test invoice for services.",
            attachments="",
        )

        cmd_search(archive, "invoice")
        captured = capsys.readouterr()
        assert "Found" in captured.out
        assert "invoice" in captured.out.lower()


class TestCmdStats:
    """Tests for stats command."""

    def test_stats_empty_archive(self, temp_dir, capsys):
        """Test stats on empty archive."""
        from ownmail.archive import EmailArchive

        config = {}
        archive = EmailArchive(temp_dir, config)
        cmd_stats(archive, config)
        captured = capsys.readouterr()
        assert "Statistics" in captured.out
        assert str(temp_dir) in captured.out

    def test_stats_with_sources(self, temp_dir, capsys):
        """Test stats with configured sources."""
        from ownmail.archive import EmailArchive

        config = {"sources": [{"name": "gmail_personal", "account": "test@gmail.com"}]}
        archive = EmailArchive(temp_dir, config)
        archive.db.mark_downloaded(_eid("msg1", "test@gmail.com"), "msg1", "test.eml", account="test@gmail.com")

        cmd_stats(archive, config)
        captured = capsys.readouterr()
        assert "gmail_personal" in captured.out
        assert "test@gmail.com" in captured.out


class TestCmdSourcesList:
    """Tests for sources list command."""

    def test_list_empty_sources(self, capsys):
        """Test listing when no sources configured."""
        config = {}
        cmd_sources_list(config)
        captured = capsys.readouterr()
        assert "No sources configured" in captured.out

    def test_list_configured_sources(self, capsys):
        """Test listing configured sources."""
        config = {
            "sources": [
                {"name": "gmail_personal", "type": "gmail_api", "account": "alice@gmail.com"},
                {"name": "work_imap", "type": "imap", "account": "alice@company.com"},
            ]
        }
        cmd_sources_list(config)
        captured = capsys.readouterr()
        assert "Configured sources" in captured.out
        assert "gmail_personal" in captured.out
        assert "gmail_api" in captured.out
        assert "alice@gmail.com" in captured.out
        assert "work_imap" in captured.out
        assert "imap" in captured.out


class TestMainEntryPoint:
    """Tests for main() entry point."""

    def test_main_no_command_shows_help(self, capsys):
        """Test that running without command shows help."""
        from ownmail.cli import main

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["ownmail"]):
                main()
        assert exc_info.value.code == 1

    def test_main_version_flag(self, capsys):
        """Test --version flag."""
        from ownmail.cli import main

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["ownmail", "--version"]):
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "ownmail" in captured.out

    def test_main_stats_command(self, temp_dir, capsys, monkeypatch):
        """Test stats command via main."""
        from ownmail.cli import main

        # Create a minimal config
        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "stats"]):
            main()

        captured = capsys.readouterr()
        assert "Statistics" in captured.out

    def test_main_sources_list_command(self, temp_dir, capsys, monkeypatch):
        """Test sources list command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_source
    type: gmail_api
    account: test@test.com
    auth:
      secret_ref: keychain:test
""")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "sources", "list"]):
            main()

        captured = capsys.readouterr()
        assert "test_source" in captured.out

    def test_main_search_command(self, temp_dir, capsys, monkeypatch):
        """Test search command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "search", "test query"]):
            main()

        captured = capsys.readouterr()
        assert "Searching for" in captured.out

    def test_main_rebuild_command(self, temp_dir, capsys, monkeypatch):
        """Test rebuild command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "rebuild"]):
            main()

        captured = capsys.readouterr()
        assert "Rebuild" in captured.out

    def test_main_verify_command(self, temp_dir, capsys, monkeypatch):
        """Test verify command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "verify"]):
            main()

        captured = capsys.readouterr()
        assert "Verify" in captured.out


class TestCmdDownload:
    """Tests for download command."""

    def test_download_no_sources_exits(self, temp_dir, capsys, monkeypatch):
        """Test download exits when no sources configured."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_download

        archive = EmailArchive(temp_dir, {})
        config = {}

        with pytest.raises(SystemExit):
            cmd_download(archive, config)

        captured = capsys.readouterr()
        assert "No sources configured" in captured.out

    def test_download_source_not_found(self, temp_dir, capsys):
        """Test download with nonexistent source name."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_download

        config = {"sources": [{"name": "existing", "type": "gmail_api", "account": "test@test.com"}]}
        archive = EmailArchive(temp_dir, config)

        with pytest.raises(SystemExit):
            cmd_download(archive, config, source_name="nonexistent")

        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_download_unknown_source_type(self, temp_dir, capsys):
        """Test download with unknown source type."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_download

        config = {"sources": [{"name": "test", "type": "unknown_type", "account": "test@test.com"}]}
        archive = EmailArchive(temp_dir, config)

        cmd_download(archive, config)

        captured = capsys.readouterr()
        assert "Unknown source type" in captured.out

    def test_download_imap(self, temp_dir, capsys):
        """Test download with IMAP source."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_download

        config = {
            "sources": [
                {
                    "name": "test",
                    "type": "imap",
                    "account": "test@test.com",
                    "host": "imap.test.com",
                    "auth": {"secret_ref": "keychain:test"},
                }
            ]
        }
        archive = EmailArchive(temp_dir, config)

        with patch("ownmail.providers.imap.ImapProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.account = "test@gmail.com"
            mock_provider.name = "imap"
            mock_provider.get_new_message_ids.return_value = ([], None)
            mock_provider.get_current_sync_state.return_value = None
            mock_provider_cls.return_value = mock_provider

            cmd_download(archive, config)

        captured = capsys.readouterr()
        assert "Download" in captured.out or "Connected" in captured.out or "up to date" in captured.out.lower()


class TestCmdSetup:
    """Tests for setup command."""

    def test_setup_oauth_first_time_prompts_for_paste(self, temp_dir, capsys, monkeypatch):
        """Test OAuth setup prompts for credentials when none exist."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup
        from ownmail.keychain import KeychainStorage

        mock_keychain = MagicMock(spec=KeychainStorage)
        mock_keychain.has_client_credentials.return_value = False

        config = {}

        # Simulate user input - empty path (paste mode), then credentials, then email/source
        inputs = iter(
            [
                "",  # press Enter to paste credentials
                '{"installed": {"client_id": "test"}}',  # credentials
                "",  # end of paste
                "",
                "test@gmail.com",  # email (now first)
                "test_source",  # source name
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        # Mock the OAuth flow
        with patch("ownmail.cli.GmailProvider") as mock_provider:
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance
            mock_keychain.load_gmail_token.return_value = None

            # Will fail because we're not fully mocking everything
            try:
                cmd_setup(mock_keychain, config, None, method="oauth")
            except (StopIteration, Exception):
                pass  # Expected due to mock limitations

        captured = capsys.readouterr()
        assert "Setup" in captured.out

    def test_setup_imap_method(self, temp_dir, capsys, monkeypatch):
        """Test IMAP setup flow."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        config = {}

        inputs = iter(
            [
                "user@gmail.com",  # email address
                "test-app-password",  # app password (via getpass)
                "my_source",  # source name
                "",  # archive root (accept default)
            ]
        )

        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.chdir(temp_dir)

        with patch("getpass.getpass", return_value="test-app-password"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_conn = MagicMock()
                mock_imap.return_value = mock_conn

                cmd_setup(mock_keychain, config, None, method="imap")

        captured = capsys.readouterr()
        assert "Setup complete" in captured.out
        mock_keychain.save_imap_password.assert_called_once()
        # Verify config file was created
        assert (temp_dir / "config.yaml").exists()

    def test_setup_creates_config_with_comments(self, temp_dir, capsys, monkeypatch):
        """Test that setup creates a config.yaml with commented options when none exists."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        config = {}

        inputs = iter(
            [
                "user@example.com",  # email address
                "imap.example.com",  # IMAP host (non-Gmail)
                "my_source",  # source name
                "",  # archive root (accept default)
            ]
        )

        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.chdir(temp_dir)

        with patch("getpass.getpass", return_value="secret"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_imap.return_value = MagicMock()
                cmd_setup(mock_keychain, config, None, method="imap")

        config_file = temp_dir / "config.yaml"
        assert config_file.exists()
        content = config_file.read_text()
        # Source is present
        assert "my_source" in content
        assert "imap.example.com" in content
        assert "user@example.com" in content
        # archive_root is set to absolute path
        assert "archive_root:" in content
        assert str((temp_dir / "archive").resolve()) in content
        # Commented options are present
        assert "# db_dir:" in content
        assert "# web:" in content
        assert "port:" in content
        assert "block_images:" in content

    def test_setup_appends_source_to_existing_config(self, temp_dir, capsys, monkeypatch):
        """Test that setup appends a new source to an existing config.yaml."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()

        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "archive_root: /tmp/mail\n\nsources:\n  - name: existing\n    type: imap\n    host: imap.old.com\n    account: old@example.com\n    auth:\n      secret_ref: keychain:imap-password/old@example.com\n"
        )

        config = {
            "archive_root": "/tmp/mail",
            "sources": [
                {
                    "name": "existing",
                    "type": "imap",
                    "host": "imap.old.com",
                    "account": "old@example.com",
                    "auth": {"secret_ref": "keychain:imap-password/old@example.com"},
                }
            ],
        }

        inputs = iter(
            [
                "new@example.com",
                "imap.new.com",
                "new_source",
            ]
        )

        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("getpass.getpass", return_value="secret"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_imap.return_value = MagicMock()
                cmd_setup(mock_keychain, config, config_path, method="imap")

        content = config_path.read_text()
        assert "new_source" in content
        assert "existing" in content  # Original source still there

    def test_setup_skips_existing_source(self, temp_dir, capsys, monkeypatch):
        """Test that setup skips config update when source already exists."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()

        config = {
            "sources": [
                {
                    "name": "my_source",
                    "type": "imap",
                    "host": "imap.gmail.com",
                    "account": "user@gmail.com",
                    "auth": {"secret_ref": "keychain:imap-password/user@gmail.com"},
                }
            ],
        }

        inputs = iter(
            [
                "user@gmail.com",
                "my_source",
            ]
        )

        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("getpass.getpass", return_value="secret"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_imap.return_value = MagicMock()
                cmd_setup(mock_keychain, config, None, method="imap")

        captured = capsys.readouterr()
        assert "already exists" in captured.out

    def test_setup_imap_empty_email_exits(self, temp_dir, capsys, monkeypatch):
        """Test that setup exits when email address is empty."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        monkeypatch.setattr("builtins.input", lambda _: "")

        with pytest.raises(SystemExit):
            cmd_setup(mock_keychain, {}, None, method="imap")

    def test_setup_imap_empty_password_exits(self, temp_dir, capsys, monkeypatch):
        """Test that setup exits when password is empty."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        monkeypatch.setattr("builtins.input", lambda _: "user@gmail.com")

        with patch("getpass.getpass", return_value=""):
            with pytest.raises(SystemExit):
                cmd_setup(mock_keychain, {}, None, method="imap")

    def test_setup_imap_connection_failure_exits(self, temp_dir, capsys, monkeypatch):
        """Test that setup exits on IMAP auth failure."""
        import imaplib
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        monkeypatch.setattr("builtins.input", lambda _: "user@gmail.com")

        with patch("getpass.getpass", return_value="bad-password"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_conn = MagicMock()
                mock_conn.login.side_effect = imaplib.IMAP4.error("AUTHENTICATIONFAILED")
                mock_imap.return_value = mock_conn
                with pytest.raises(SystemExit):
                    cmd_setup(mock_keychain, {}, None, method="imap")

        captured = capsys.readouterr()
        assert "Failed" in captured.out

    def test_setup_imap_non_gmail_host(self, temp_dir, capsys, monkeypatch):
        """Test IMAP setup for non-Gmail server."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        config = {}

        inputs = iter(
            [
                "user@company.com",  # email
                "imap.company.com",  # hostname
                "my_source",  # source name
                "",  # archive root default
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.chdir(temp_dir)

        with patch("getpass.getpass", return_value="password123"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_imap.return_value = MagicMock()
                cmd_setup(mock_keychain, config, None, method="imap")

        captured = capsys.readouterr()
        assert "Setup complete" in captured.out
        # Should have saved password
        mock_keychain.save_imap_password.assert_called_once()

    def test_setup_imap_non_gmail_empty_host_exits(self, temp_dir, capsys, monkeypatch):
        """Test that setup exits when non-Gmail host is empty."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        inputs = iter(
            [
                "user@company.com",  # email (not gmail)
                "",  # empty hostname
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with pytest.raises(SystemExit):
            cmd_setup(mock_keychain, {}, None, method="imap")

    def test_setup_imap_generic_connection_error(self, temp_dir, capsys, monkeypatch):
        """Test setup handles generic connection errors."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        monkeypatch.setattr("builtins.input", lambda _: "user@gmail.com")

        with patch("getpass.getpass", return_value="password"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_imap.side_effect = OSError("Connection refused")
                with pytest.raises(SystemExit):
                    cmd_setup(mock_keychain, {}, None, method="imap")

    def test_setup_method_prompt_chooses_imap(self, temp_dir, capsys, monkeypatch):
        """Test method selection prompt defaults to IMAP."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()

        inputs = iter(
            [
                "1",  # choose IMAP
                "user@gmail.com",  # email
                "my_source",  # source name
                "",  # archive root default
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.chdir(temp_dir)

        with patch("getpass.getpass", return_value="password"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_imap.return_value = MagicMock()
                cmd_setup(mock_keychain, {}, None)

        captured = capsys.readouterr()
        assert "Setup complete" in captured.out

    def test_setup_method_prompt_chooses_oauth(self, temp_dir, capsys, monkeypatch):
        """Test method selection prompt choosing OAuth."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = False

        inputs = iter(
            [
                "2",  # choose OAuth
                "",  # press Enter to paste credentials
                '{"installed": {"client_id": "test"}}',  # paste credentials
                "",  # end of paste
                "",
                "test@gmail.com",  # email
                "test_source",  # source name
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("ownmail.cli.GmailProvider") as mock_provider:
            mock_keychain.load_gmail_token.return_value = None
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance

            try:
                cmd_setup(mock_keychain, {}, None)
            except (StopIteration, Exception):
                pass

        captured = capsys.readouterr()
        assert "OAuth" in captured.out

    def test_setup_credentials_file(self, temp_dir, capsys, monkeypatch):
        """Test setup with credentials file via interactive prompt."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = False

        creds_file = temp_dir / "client_secret.json"
        creds_file.write_text('{"installed": {"client_id": "test"}}')

        inputs = iter(
            [
                str(creds_file),  # path to credentials file
                "test@gmail.com",
                "test_source",
                "",
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.chdir(temp_dir)

        with patch("ownmail.cli.GmailProvider") as mock_provider:
            mock_keychain.load_gmail_token.return_value = None
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance

            try:
                cmd_setup(mock_keychain, {}, None, method="oauth")
            except (StopIteration, Exception):
                pass

        mock_keychain.save_client_credentials.assert_called_once()

    def test_setup_credentials_file_not_found(self, temp_dir, capsys, monkeypatch):
        """Test setup exits when credentials file doesn't exist."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = False

        # Provide a nonexistent file path interactively
        monkeypatch.setattr("builtins.input", lambda _: "/nonexistent/file.json")

        with pytest.raises(SystemExit):
            cmd_setup(mock_keychain, {}, None, method="oauth")

    def test_setup_oauth_empty_email_exits(self, temp_dir, capsys, monkeypatch):
        """Test OAuth setup exits when email is empty."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True

        monkeypatch.setattr("builtins.input", lambda _: "")

        with pytest.raises(SystemExit):
            cmd_setup(mock_keychain, {}, None, method="oauth")

    def test_setup_oauth_existing_token(self, temp_dir, capsys, monkeypatch):
        """Test OAuth setup when token already exists."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = True
        mock_keychain.load_gmail_token.return_value = MagicMock()  # Token exists

        inputs = iter(
            [
                "test@gmail.com",
                "test_source",
                "",
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.chdir(temp_dir)

        cmd_setup(mock_keychain, {}, None, method="oauth")

        captured = capsys.readouterr()
        assert "already exists" in captured.out

    def test_setup_oauth_empty_credentials_paste(self, temp_dir, capsys, monkeypatch):
        """Test OAuth setup exits when no credentials are pasted."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()
        mock_keychain.has_client_credentials.return_value = False

        # Simulate immediate EOF
        monkeypatch.setattr("builtins.input", MagicMock(side_effect=EOFError))

        with pytest.raises(SystemExit):
            cmd_setup(mock_keychain, {}, None, method="oauth")

    def test_update_config_with_custom_archive_path(self, temp_dir, capsys, monkeypatch):
        """Test config creation with custom archive path."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup

        mock_keychain = MagicMock()

        custom_path = str(temp_dir / "my_archive")
        inputs = iter(
            [
                "user@gmail.com",
                "my_source",
                custom_path,
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.chdir(temp_dir)

        with patch("getpass.getpass", return_value="password"):
            with patch("imaplib.IMAP4_SSL") as mock_imap:
                mock_imap.return_value = MagicMock()
                cmd_setup(mock_keychain, {}, None, method="imap")

        config_content = (temp_dir / "config.yaml").read_text()
        assert custom_path in config_content


class TestMainEdgeCases:
    """Edge case tests for main entry point."""

    def test_main_with_archive_root_override(self, temp_dir, capsys, monkeypatch):
        """Test --archive-root overrides config."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text("archive_root: /ignored/path\n")
        monkeypatch.chdir(temp_dir)

        custom_dir = temp_dir / "custom"
        custom_dir.mkdir()

        with patch.object(sys, "argv", ["ownmail", "--archive-root", str(custom_dir), "stats"]):
            main()

        captured = capsys.readouterr()
        assert str(custom_dir) in captured.out

    def test_main_sync_check_command(self, temp_dir, capsys, monkeypatch):
        """Test sync-check command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "sync-check"]):
            main()

        captured = capsys.readouterr()
        # Should fail gracefully without sources
        assert "No sources" in captured.out or "Sync Check" in captured.out

    def test_main_update_labels_command(self, temp_dir, capsys, monkeypatch):
        """Test update-labels command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "update-labels"]):
            main()

        captured = capsys.readouterr()
        # Should fail gracefully without sources
        assert "No sources" in captured.out or "Update Labels" in captured.out

    def test_main_verify_command_2(self, temp_dir, capsys, monkeypatch):
        """Test verify command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "verify"]):
            main()

        captured = capsys.readouterr()
        assert "Verify" in captured.out

    def test_main_verify_fix_command(self, temp_dir, capsys, monkeypatch):
        """Test verify --fix command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "verify", "--fix"]):
            main()

        captured = capsys.readouterr()
        assert "Verify" in captured.out

    def test_main_search_with_limit(self, temp_dir, capsys, monkeypatch):
        """Test search with --limit option."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "search", "test", "--limit", "5"]):
            main()

        captured = capsys.readouterr()
        assert "Searching" in captured.out

    def test_main_rebuild_force(self, temp_dir, capsys, monkeypatch):
        """Test rebuild --force command."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "rebuild", "--force"]):
            main()

        captured = capsys.readouterr()
        assert "(force)" in captured.out

    def test_main_rebuild_pattern(self, temp_dir, capsys, monkeypatch):
        """Test rebuild --pattern command."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "rebuild", "--pattern", "2024/*"]):
            main()

        captured = capsys.readouterr()
        assert "matching '2024/*'" in captured.out

    def test_main_verify_verbose(self, temp_dir, capsys, monkeypatch):
        """Test verify --verbose command."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "verify", "--verbose"]):
            main()

        capsys.readouterr()
        # Should not crash

    def test_main_refuses_duplicate_source_names(self, temp_dir, capsys, monkeypatch):
        """Test that CLI exits with error on duplicate source names."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            f"archive_root: {temp_dir}\n"
            "sources:\n"
            "  - name: personal\n"
            "    type: gmail_api\n"
            "    account: a@test.com\n"
            "    auth:\n"
            "      secret_ref: keychain:tok-a\n"
            "  - name: personal\n"
            "    type: gmail_api\n"
            "    account: b@test.com\n"
            "    auth:\n"
            "      secret_ref: keychain:tok-b\n"
        )
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "download"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Duplicate source name" in captured.out

    def test_setup_skips_validation(self, temp_dir, capsys, monkeypatch):
        """Test that setup command skips config validation (config may not exist yet)."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            f"archive_root: {temp_dir}\n"
            "sources:\n"
            "  - name: dup\n"
            "    type: gmail_api\n"
            "    account: a@test.com\n"
            "    auth:\n"
            "      secret_ref: keychain:tok\n"
            "  - name: dup\n"
            "    type: gmail_api\n"
            "    account: b@test.com\n"
            "    auth:\n"
            "      secret_ref: keychain:tok\n"
        )
        monkeypatch.chdir(temp_dir)

        # setup should not fail on duplicate names — it needs to run
        # to let the user fix the config
        with patch.object(sys, "argv", ["ownmail", "setup"]):
            with patch("ownmail.cli.cmd_setup") as mock_setup:
                main()
                mock_setup.assert_called_once()


class TestDownloadCommand:
    """Tests for download command with mocked provider."""

    def test_download_with_gmail_source(self, temp_dir, capsys, monkeypatch):
        """Test download command with Gmail source configured."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_gmail
    type: gmail_api
    account: test@gmail.com
    auth:
      secret_ref: keychain:test_token
    include_labels: true
""")
        monkeypatch.chdir(temp_dir)

        # Mock the GmailProvider
        with patch("ownmail.cli.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.account = "test@gmail.com"
            mock_provider.get_new_message_ids.return_value = ([], None)
            mock_provider.get_current_sync_state.return_value = "12345"
            mock_provider_class.return_value = mock_provider

            with patch.object(sys, "argv", ["ownmail", "download"]):
                main()

        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower() or "Download" in captured.out

    def test_download_source_specified(self, temp_dir, capsys, monkeypatch):
        """Test download with source specified via --source."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_gmail
    type: gmail_api
    account: test@gmail.com
    auth:
      secret_ref: keychain:test_token
""")
        monkeypatch.chdir(temp_dir)

        # Mock the GmailProvider
        with patch("ownmail.cli.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.account = "test@gmail.com"
            mock_provider.get_new_message_ids.return_value = ([], None)
            mock_provider.get_current_sync_state.return_value = "12345"
            mock_provider_class.return_value = mock_provider

            with patch.object(sys, "argv", ["ownmail", "download", "--source", "test_gmail"]):
                main()

        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower() or "Download" in captured.out

    def test_download_missing_auth(self, temp_dir, capsys, monkeypatch):
        """Test download with missing auth config."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_gmail
    type: gmail_api
    account: test@gmail.com
""")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "download"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        # Should report missing auth
        assert "missing" in captured.out.lower() or "auth" in captured.out.lower()

    def test_download_with_new_emails(self, temp_dir, capsys, monkeypatch):
        """Test download fetches new emails."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_gmail
    type: gmail_api
    account: test@gmail.com
    auth:
      secret_ref: keychain:test_token
""")
        monkeypatch.chdir(temp_dir)

        # Mock the GmailProvider
        with patch("ownmail.cli.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.account = "test@gmail.com"
            mock_provider.get_new_message_ids.return_value = (["msg1", "msg2"], None)
            mock_provider.get_current_sync_state.return_value = "12345"
            mock_provider.download_message.return_value = (
                b"From: test@example.com\nDate: Mon, 15 Jan 2024 10:00:00 +0000\n\nBody",
                ["INBOX"],
            )
            mock_provider_class.return_value = mock_provider

            with patch.object(sys, "argv", ["ownmail", "download"]):
                main()

        captured = capsys.readouterr()
        assert "Downloaded" in captured.out or "Download" in captured.out

    def test_download_with_errors(self, temp_dir, capsys, monkeypatch):
        """Test download handles errors."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_gmail
    type: gmail_api
    account: test@gmail.com
    auth:
      secret_ref: keychain:test_token
""")
        monkeypatch.chdir(temp_dir)

        # Mock the GmailProvider with download failures
        with patch("ownmail.cli.GmailProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.account = "test@gmail.com"
            mock_provider.get_new_message_ids.return_value = (["msg1"], None)
            mock_provider.get_current_sync_state.return_value = "12345"
            mock_provider.download_message.return_value = (None, None)  # Download fails
            mock_provider_class.return_value = mock_provider

            with patch.object(sys, "argv", ["ownmail", "download"]):
                main()

        captured = capsys.readouterr()
        assert "Error" in captured.out or "Download" in captured.out

    def test_download_invalid_secret_ref(self, temp_dir, capsys, monkeypatch):
        """Test download with invalid secret_ref format."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"""
archive_root: {temp_dir}
sources:
  - name: test_gmail
    type: gmail_api
    account: test@gmail.com
    auth:
      secret_ref: invalid_format
""")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, "argv", ["ownmail", "download"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        # Should report error about secret_ref format
        assert (
            "error" in captured.out.lower() or "invalid" in captured.out.lower() or "keychain:" in captured.out.lower()
        )


class TestCmdTrash:
    """Tests for the trash CLI command."""

    def _archive(self):
        archive = MagicMock()
        archive.db = MagicMock()
        return archive

    def test_empty_permanently_deletes(self, capsys):
        """--empty should permanently delete everything in trash."""
        from ownmail.cli import cmd_trash

        archive = self._archive()
        archive.empty_trash.return_value = 7

        cmd_trash(archive, empty=True)

        archive.empty_trash.assert_called_once_with(expired_only=False)
        assert "Permanently deleted 7 email(s)" in capsys.readouterr().out

    def test_expire_removes_old_entries(self, capsys):
        """--expire should drop entries older than the retention window."""
        from ownmail.cli import cmd_trash

        archive = self._archive()
        archive.auto_expire_trash.return_value = 3

        cmd_trash(archive, expire=True)

        archive.auto_expire_trash.assert_called_once_with(days=30)
        assert "Expired 3 email(s) from trash" in capsys.readouterr().out

    def test_empty_trash_reports_nothing(self, capsys):
        """An empty trash should say so and list nothing."""
        from ownmail.cli import cmd_trash

        archive = self._archive()
        archive.db.get_trashed_emails.return_value = []
        archive.db.get_trash_count.return_value = 0

        cmd_trash(archive)

        assert "Trash is empty" in capsys.readouterr().out

    def test_lists_trashed_emails(self, capsys):
        """Trashed emails should be listed with date, sender and subject."""
        from ownmail.cli import cmd_trash

        archive = self._archive()
        archive.db.get_trashed_emails.return_value = [
            ("id1", "f1.eml", "Hello there", "someone@example.com", "2024-03-04T05:06:07", "o1.eml"),
        ]
        archive.db.get_trash_count.return_value = 1

        cmd_trash(archive)

        out = capsys.readouterr().out
        assert "Trash (1 email(s))" in out
        assert "2024-03-04" in out
        assert "someone@example.com" in out
        assert "Hello there" in out

    def test_missing_subject_and_sender_get_placeholders(self, capsys):
        """Rows with no subject/sender should render placeholders."""
        from ownmail.cli import cmd_trash

        archive = self._archive()
        archive.db.get_trashed_emails.return_value = [
            ("id1", "f1.eml", None, None, "2024-03-04T05:06:07", "o1.eml"),
        ]
        archive.db.get_trash_count.return_value = 1

        cmd_trash(archive)

        out = capsys.readouterr().out
        assert "(No subject)" in out
        assert "(Unknown)" in out

    def test_truncation_notice_beyond_page(self, capsys):
        """More than 50 trashed emails should show a '... and N more' notice."""
        from ownmail.cli import cmd_trash

        archive = self._archive()
        archive.db.get_trashed_emails.return_value = [
            (f"id{i}", f"f{i}.eml", "Subj", "a@example.com", "2024-03-04T05:06:07", f"o{i}.eml") for i in range(50)
        ]
        archive.db.get_trash_count.return_value = 63

        cmd_trash(archive)

        assert "... and 13 more" in capsys.readouterr().out


class TestMainServeCommand:
    """Tests for the `serve` dispatch in main()."""

    def _write_config(self, temp_dir, body):
        config = temp_dir / "config.yaml"
        config.write_text(body)
        return config

    def test_serve_passes_web_config_through(self, temp_dir, monkeypatch):
        """Values from config.yaml [web] should reach run_server."""
        from ownmail.cli import main

        self._write_config(
            temp_dir,
            "archive_root: .\n"
            "web:\n"
            "  page_size: 33\n"
            "  block_images: false\n"
            "  trusted_senders:\n"
            "    - a@example.com\n"
            "  date_format: '%Y-%m-%d'\n"
            "  detail_date_format: '%Y-%m-%d %H:%M'\n"
            "  auto_scale: false\n"
            "  brand_name: MyMail\n"
            "  timezone: Asia/Seoul\n",
        )
        monkeypatch.chdir(temp_dir)

        with patch("ownmail.web.run_server") as mock_run:
            with patch.object(sys, "argv", ["ownmail", "serve"]):
                main()

        args, kwargs = mock_run.call_args
        assert args[1] == "127.0.0.1"  # host
        assert args[2] == 8080  # port
        assert args[6] == 33  # page_size
        assert args[7] == ["a@example.com"]  # trusted_senders
        assert args[9] == "%Y-%m-%d"  # date_format
        assert args[10] is False  # auto_scale
        assert args[11] == "MyMail"  # brand_name
        assert args[12] == "Asia/Seoul"  # display_timezone
        assert args[13] == "%Y-%m-%d %H:%M"  # detail_date_format
        assert kwargs["open_browser"] is True

    def test_serve_defaults_without_web_config(self, temp_dir, monkeypatch):
        """With no [web] section, run_server should get the documented defaults."""
        from ownmail.cli import main

        self._write_config(temp_dir, "archive_root: .\n")
        monkeypatch.chdir(temp_dir)

        with patch("ownmail.web.run_server") as mock_run:
            with patch.object(sys, "argv", ["ownmail", "serve"]):
                main()

        args, _ = mock_run.call_args
        assert args[5] is True  # block_images defaults on
        assert args[6] == 20  # page_size
        assert args[7] == []  # trusted_senders
        assert args[10] is True  # auto_scale
        assert args[11] == "ownmail"  # brand_name

    def test_serve_cli_flags_override(self, temp_dir, monkeypatch):
        """--host/--port/--no-browser should be honoured."""
        from ownmail.cli import main

        self._write_config(temp_dir, "archive_root: .\n")
        monkeypatch.chdir(temp_dir)

        with patch("ownmail.web.run_server") as mock_run:
            with patch.object(sys, "argv", ["ownmail", "serve", "--host", "0.0.0.0", "--port", "9000", "--no-browser"]):
                main()

        args, kwargs = mock_run.call_args
        assert args[1] == "0.0.0.0"
        assert args[2] == 9000
        assert kwargs["open_browser"] is False

    def test_serve_archive_dir_overrides_root(self, temp_dir, monkeypatch):
        """serve --archive-dir should serve that directory instead of the root."""
        from ownmail.cli import main

        self._write_config(temp_dir, "archive_root: .\n")
        other = temp_dir / "other-archive"
        other.mkdir()
        monkeypatch.chdir(temp_dir)

        with patch("ownmail.web.run_server") as mock_run:
            with patch.object(sys, "argv", ["ownmail", "serve", "--archive-dir", str(other)]):
                main()

        served = mock_run.call_args.args[0]
        assert served.archive_dir == other


class TestMainErrorHandling:
    """Tests for main()'s top-level error handling."""

    def _config(self, temp_dir):
        (temp_dir / "config.yaml").write_text("archive_root: .\n")

    def test_keyboard_interrupt_exits_1(self, temp_dir, capsys, monkeypatch):
        """Ctrl-C should exit cleanly with status 1."""
        from ownmail.cli import main

        self._config(temp_dir)
        monkeypatch.chdir(temp_dir)

        with patch("ownmail.cli.cmd_search", side_effect=KeyboardInterrupt):
            with patch.object(sys, "argv", ["ownmail", "search", "x"]):
                with pytest.raises(SystemExit) as exc:
                    main()

        assert exc.value.code == 1
        assert "interrupted by user" in capsys.readouterr().out

    def test_unexpected_error_is_reported_and_exits_1(self, temp_dir, capsys, monkeypatch):
        """An unexpected error should print a message and exit 1."""
        from ownmail.cli import main

        self._config(temp_dir)
        monkeypatch.chdir(temp_dir)

        with patch("ownmail.cli.cmd_search", side_effect=RuntimeError("kaboom")):
            with patch.object(sys, "argv", ["ownmail", "search", "x"]):
                with pytest.raises(SystemExit) as exc:
                    main()

        assert exc.value.code == 1
        assert "Error: kaboom" in capsys.readouterr().out

    def test_verbose_reraises_for_traceback(self, temp_dir, monkeypatch):
        """--verbose should re-raise so the traceback is visible."""
        from ownmail.cli import main

        self._config(temp_dir)
        monkeypatch.chdir(temp_dir)

        # cmd_verify is imported lazily inside main(), so patch it at its source.
        # --verbose must follow the subcommand here: see TASK-12, the global
        # form is currently swallowed by the subparser's duplicate flag.
        with patch("ownmail.commands.cmd_verify", side_effect=RuntimeError("kaboom")):
            with patch.object(sys, "argv", ["ownmail", "verify", "--verbose"]):
                with pytest.raises(RuntimeError, match="kaboom"):
                    main()


class TestCmdDownloadSources:
    """Tests for cmd_download's per-source-type handling."""

    def _archive(self, temp_dir):
        from ownmail.archive import EmailArchive

        return EmailArchive(temp_dir, {})

    def _result(self, success=2, errors=0, interrupted=False):
        return {"success_count": success, "error_count": errors, "interrupted": interrupted, "failed_ids": []}

    def _gmail_config(self, **overrides):
        source = {
            "name": "personal",
            "type": "gmail_api",
            "account": "alice@gmail.com",
            "auth": {"secret_ref": "keychain:oauth-token/alice@gmail.com"},
        }
        source.update(overrides)
        return {"sources": [source]}

    def _imap_config(self, **overrides):
        source = {
            "name": "work",
            "type": "imap",
            "account": "alice@example.com",
            "host": "imap.example.com",
            "auth": {"secret_ref": "keychain:imap-password/alice@example.com"},
        }
        source.update(overrides)
        return {"sources": [source]}

    def test_gmail_source_downloads(self, temp_dir, capsys):
        """A gmail_api source should authenticate and back up."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        provider = MagicMock()
        with patch("ownmail.cli.GmailProvider", return_value=provider):
            with patch.object(archive, "backup", return_value=self._result()) as mock_backup:
                cmd_download(archive, self._gmail_config())

        provider.authenticate.assert_called_once()
        mock_backup.assert_called_once()
        out = capsys.readouterr().out
        assert "Download Complete!" in out
        assert "Downloaded: 2 emails" in out

    def test_gmail_missing_secret_ref_is_skipped(self, temp_dir, capsys):
        """A source without auth.secret_ref should be skipped with a message."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider") as mock_provider:
            cmd_download(archive, self._gmail_config(auth={}))

        mock_provider.assert_not_called()
        assert "missing auth.secret_ref" in capsys.readouterr().out

    def test_gmail_malformed_secret_ref_is_skipped(self, temp_dir, capsys):
        """An unparseable secret_ref should be reported and skipped."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider") as mock_provider:
            with patch("ownmail.cli.parse_secret_ref", side_effect=ValueError("bad ref")):
                cmd_download(archive, self._gmail_config())

        mock_provider.assert_not_called()
        assert "bad ref" in capsys.readouterr().out

    def test_interrupted_download_reports_resume(self, temp_dir, capsys):
        """An interrupted run should tell the user how to resume."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider"):
            with patch.object(archive, "backup", return_value=self._result(success=1, interrupted=True)):
                cmd_download(archive, self._gmail_config())

        out = capsys.readouterr().out
        assert "Download Paused!" in out
        assert "Run 'download' again to resume" in out

    def test_errors_are_reported(self, temp_dir, capsys):
        """A run with errors should surface the error count."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider"):
            with patch.object(archive, "backup", return_value=self._result(errors=3)):
                cmd_download(archive, self._gmail_config())

        assert "Errors: 3" in capsys.readouterr().out

    def test_date_filter_is_shown_and_passed_through(self, temp_dir, capsys):
        """since/until should be echoed and forwarded to backup."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider"):
            with patch.object(archive, "backup", return_value=self._result()) as mock_backup:
                cmd_download(archive, self._gmail_config(), since="2024-01-01", until="2024-02-01")

        out = capsys.readouterr().out
        assert "Date filter: from 2024-01-01 until 2024-02-01" in out
        assert mock_backup.call_args.kwargs["since"] == "2024-01-01"
        assert mock_backup.call_args.kwargs["until"] == "2024-02-01"

    def test_verbose_narrates_provider_setup(self, temp_dir, capsys):
        """Verbose mode should log provider creation and authentication."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider"):
            with patch.object(archive, "backup", return_value=self._result()):
                cmd_download(archive, self._gmail_config(), verbose=True)

        out = capsys.readouterr().out
        assert "Creating Gmail provider" in out
        assert "Authenticating" in out
        assert "Starting download" in out

    def test_imap_source_downloads(self, temp_dir, capsys):
        """An imap source should build an ImapProvider from config."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        provider = MagicMock()
        with patch("ownmail.providers.imap.ImapProvider", return_value=provider) as mock_cls:
            with patch.object(archive, "backup", return_value=self._result()):
                cmd_download(archive, self._imap_config(port=1993, exclude_folders=["Spam"]))

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["host"] == "imap.example.com"
        assert kwargs["port"] == 1993
        assert kwargs["exclude_folders"] == ["Spam"]
        provider.authenticate.assert_called_once()
        provider.close.assert_called_once()
        assert "Download Complete!" in capsys.readouterr().out

    def test_imap_defaults(self, temp_dir):
        """Omitted host/port should fall back to the Gmail IMAP defaults."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        config = self._imap_config()
        del config["sources"][0]["host"]
        with patch("ownmail.providers.imap.ImapProvider") as mock_cls:
            with patch.object(archive, "backup", return_value=self._result()):
                cmd_download(archive, config)

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["host"] == "imap.gmail.com"
        assert kwargs["port"] == 993

    def test_unknown_source_type_is_skipped(self, temp_dir, capsys):
        """An unrecognized source type should be reported, not crash."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        cmd_download(archive, {"sources": [{"name": "x", "type": "pop3", "account": "a@example.com"}]})

        assert "Unknown source type: pop3" in capsys.readouterr().out

    def test_named_source_selects_one(self, temp_dir, capsys):
        """--source should restrict the run to that source."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        config = {"sources": self._gmail_config()["sources"] + self._imap_config()["sources"]}
        with patch("ownmail.providers.imap.ImapProvider"):
            with patch("ownmail.cli.GmailProvider") as mock_gmail:
                with patch.object(archive, "backup", return_value=self._result()):
                    cmd_download(archive, config, source_name="work")

        mock_gmail.assert_not_called()
        assert "Source: work" in capsys.readouterr().out

    def test_unknown_source_name_exits(self, temp_dir, capsys):
        """An unknown --source name should exit with an error."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with pytest.raises(SystemExit):
            cmd_download(archive, self._gmail_config(), source_name="nope")

        assert "not found in config" in capsys.readouterr().out

    def test_expired_trash_is_reported(self, temp_dir, capsys):
        """Auto-expired trash should be announced before downloading."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider"):
            with patch.object(archive, "auto_expire_trash", return_value=4):
                with patch.object(archive, "backup", return_value=self._result()):
                    cmd_download(archive, self._gmail_config())

        assert "Auto-expired 4 email(s) from trash" in capsys.readouterr().out

    def test_trash_expiry_failure_does_not_block_download(self, temp_dir):
        """A failure expiring trash must not stop the download."""
        from ownmail.cli import cmd_download

        archive = self._archive(temp_dir)
        with patch("ownmail.cli.GmailProvider"):
            with patch.object(archive, "auto_expire_trash", side_effect=OSError("locked")):
                with patch.object(archive, "backup", return_value=self._result()) as mock_backup:
                    cmd_download(archive, self._gmail_config())

        mock_backup.assert_called_once()
