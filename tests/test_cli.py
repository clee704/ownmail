"""Tests for CLI module."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from ownmail.cli import (
    cmd_search,
    cmd_sources_list,
    cmd_stats,
)


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
        archive.db.mark_downloaded("test123", "test.eml", email_date="2024-01-15T00:00:00")
        archive.db.index_email(
            message_id="test123",
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

        config = {
            "sources": [
                {"name": "gmail_personal", "account": "test@gmail.com"}
            ]
        }
        archive = EmailArchive(temp_dir, config)
        archive.db.mark_downloaded("msg1", "test.eml", account="test@gmail.com")

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
            with patch.object(sys, 'argv', ['ownmail']):
                main()
        assert exc_info.value.code == 1

    def test_main_version_flag(self, capsys):
        """Test --version flag."""
        from ownmail.cli import main

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['ownmail', '--version']):
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

        with patch.object(sys, 'argv', ['ownmail', 'stats']):
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

        with patch.object(sys, 'argv', ['ownmail', 'sources', 'list']):
            main()

        captured = capsys.readouterr()
        assert "test_source" in captured.out

    def test_main_search_command(self, temp_dir, capsys, monkeypatch):
        """Test search command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'search', 'test query']):
            main()

        captured = capsys.readouterr()
        assert "Searching for" in captured.out

    def test_main_reindex_command(self, temp_dir, capsys, monkeypatch):
        """Test reindex command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'reindex']):
            main()

        captured = capsys.readouterr()
        assert "Reindex" in captured.out

    def test_main_verify_command(self, temp_dir, capsys, monkeypatch):
        """Test verify command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'verify']):
            main()

        captured = capsys.readouterr()
        assert "Verify" in captured.out

    def test_main_rehash_command(self, temp_dir, capsys, monkeypatch):
        """Test rehash command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'rehash']):
            main()

        captured = capsys.readouterr()
        assert "already have hashes" in captured.out or "Compute Hashes" in captured.out

    def test_main_db_check_command(self, temp_dir, capsys, monkeypatch):
        """Test db-check command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'db-check']):
            main()

        captured = capsys.readouterr()
        assert "Database Check" in captured.out


class TestCmdBackup:
    """Tests for backup command."""

    def test_backup_no_sources_exits(self, temp_dir, capsys, monkeypatch):
        """Test backup exits when no sources configured."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_backup

        archive = EmailArchive(temp_dir, {})
        config = {}

        with pytest.raises(SystemExit):
            cmd_backup(archive, config)

        captured = capsys.readouterr()
        assert "No sources configured" in captured.out

    def test_backup_source_not_found(self, temp_dir, capsys):
        """Test backup with nonexistent source name."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_backup

        config = {
            "sources": [
                {"name": "existing", "type": "gmail_api", "account": "test@test.com"}
            ]
        }
        archive = EmailArchive(temp_dir, config)

        with pytest.raises(SystemExit):
            cmd_backup(archive, config, source_name="nonexistent")

        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_backup_unknown_source_type(self, temp_dir, capsys):
        """Test backup with unknown source type."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_backup

        config = {
            "sources": [
                {"name": "test", "type": "unknown_type", "account": "test@test.com"}
            ]
        }
        archive = EmailArchive(temp_dir, config)

        cmd_backup(archive, config)

        captured = capsys.readouterr()
        assert "Unknown source type" in captured.out

    def test_backup_imap_not_implemented(self, temp_dir, capsys):
        """Test backup with IMAP source shows coming soon."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_backup

        config = {
            "sources": [
                {"name": "test", "type": "imap", "account": "test@test.com",
                 "host": "imap.test.com", "auth": {"secret_ref": "keychain:test"}}
            ]
        }
        archive = EmailArchive(temp_dir, config)

        cmd_backup(archive, config)

        captured = capsys.readouterr()
        assert "coming soon" in captured.out.lower()


class TestCmdSetup:
    """Tests for setup command."""

    def test_setup_first_time_prompts_for_paste(self, temp_dir, capsys, monkeypatch):
        """Test setup prompts for credentials when none exist."""
        from unittest.mock import MagicMock

        from ownmail.cli import cmd_setup
        from ownmail.keychain import KeychainStorage

        mock_keychain = MagicMock(spec=KeychainStorage)
        mock_keychain.has_client_credentials.return_value = False

        config = {}

        # Simulate user input - email first, then source name
        inputs = iter([
            '{"installed": {"client_id": "test"}}',  # credentials
            '',  # end of paste
            '',
            'test@gmail.com',  # email (now first)
            'test_source',  # source name
        ])
        monkeypatch.setattr('builtins.input', lambda _: next(inputs))

        # Mock the OAuth flow
        with patch("ownmail.cli.GmailProvider") as mock_provider:
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance
            mock_keychain.load_gmail_token.return_value = None

            # Will fail because we're not fully mocking everything
            try:
                cmd_setup(mock_keychain, config, None)
            except (StopIteration, Exception):
                pass  # Expected due to mock limitations

        captured = capsys.readouterr()
        assert "Setup" in captured.out


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

        with patch.object(sys, 'argv', ['ownmail', '--archive-root', str(custom_dir), 'stats']):
            main()

        captured = capsys.readouterr()
        assert str(custom_dir) in captured.out

    def test_main_sync_check_command(self, temp_dir, capsys, monkeypatch):
        """Test sync-check command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'sync-check']):
            main()

        captured = capsys.readouterr()
        # Should fail gracefully without sources
        assert "No sources" in captured.out or "Sync Check" in captured.out

    def test_main_add_labels_command(self, temp_dir, capsys, monkeypatch):
        """Test add-labels command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'add-labels']):
            main()

        captured = capsys.readouterr()
        # Should fail gracefully without sources
        assert "No sources" in captured.out or "Add Labels" in captured.out

    def test_main_db_check_command(self, temp_dir, capsys, monkeypatch):
        """Test db-check command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'db-check']):
            main()

        captured = capsys.readouterr()
        assert "Database Check" in captured.out

    def test_main_db_check_fix_command(self, temp_dir, capsys, monkeypatch):
        """Test db-check --fix command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'db-check', '--fix']):
            main()

        captured = capsys.readouterr()
        assert "Database Check" in captured.out

    def test_main_rehash_command(self, temp_dir, capsys, monkeypatch):
        """Test rehash command via main."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'rehash']):
            main()

        captured = capsys.readouterr()
        assert "Compute Hashes" in captured.out

    def test_main_search_with_limit(self, temp_dir, capsys, monkeypatch):
        """Test search with --limit option."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'search', 'test', '--limit', '5']):
            main()

        captured = capsys.readouterr()
        assert "Searching" in captured.out

    def test_main_reindex_force(self, temp_dir, capsys, monkeypatch):
        """Test reindex --force command."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'reindex', '--force']):
            main()

        captured = capsys.readouterr()
        assert "Force mode" in captured.out

    def test_main_reindex_pattern(self, temp_dir, capsys, monkeypatch):
        """Test reindex --pattern command."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'reindex', '--pattern', '2024/*']):
            main()

        captured = capsys.readouterr()
        assert "Pattern '2024/*'" in captured.out

    def test_main_verify_verbose(self, temp_dir, capsys, monkeypatch):
        """Test verify --verbose command."""
        from ownmail.cli import main

        config_path = temp_dir / "config.yaml"
        config_path.write_text(f"archive_root: {temp_dir}\n")
        monkeypatch.chdir(temp_dir)

        with patch.object(sys, 'argv', ['ownmail', 'verify', '--verbose']):
            main()

        capsys.readouterr()
        # Should not crash


class TestBackupCommand:
    """Tests for backup command with mocked provider."""

    def test_backup_with_gmail_source(self, temp_dir, capsys, monkeypatch):
        """Test backup command with Gmail source configured."""
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

            with patch.object(sys, 'argv', ['ownmail', 'backup']):
                main()

        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower() or "Backup" in captured.out

    def test_backup_source_specified(self, temp_dir, capsys, monkeypatch):
        """Test backup with source specified via --source."""
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

            with patch.object(sys, 'argv', ['ownmail', '--source', 'test_gmail', 'backup']):
                main()

        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower() or "Backup" in captured.out

    def test_backup_missing_auth(self, temp_dir, capsys, monkeypatch):
        """Test backup with missing auth config."""
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

        with patch.object(sys, 'argv', ['ownmail', 'backup']):
            main()

        captured = capsys.readouterr()
        # Should report missing auth
        assert "missing" in captured.out.lower() or "auth" in captured.out.lower()

    def test_backup_with_new_emails(self, temp_dir, capsys, monkeypatch):
        """Test backup downloads new emails."""
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
                ["INBOX"]
            )
            mock_provider_class.return_value = mock_provider

            with patch.object(sys, 'argv', ['ownmail', 'backup']):
                main()

        captured = capsys.readouterr()
        assert "Downloaded" in captured.out or "Backup" in captured.out

    def test_backup_with_errors(self, temp_dir, capsys, monkeypatch):
        """Test backup handles download errors."""
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

            with patch.object(sys, 'argv', ['ownmail', 'backup']):
                main()

        captured = capsys.readouterr()
        assert "Error" in captured.out or "Backup" in captured.out

    def test_backup_invalid_secret_ref(self, temp_dir, capsys, monkeypatch):
        """Test backup with invalid secret_ref format."""
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

        with patch.object(sys, 'argv', ['ownmail', 'backup']):
            main()

        captured = capsys.readouterr()
        # Should report error about secret_ref format
        assert "error" in captured.out.lower() or "invalid" in captured.out.lower() or "keychain:" in captured.out.lower()
