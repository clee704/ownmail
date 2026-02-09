"""Tests for IMAP provider."""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestImapProviderInit:
    """Tests for ImapProvider initialization."""

    def test_init_stores_account(self):
        """Test that account is stored."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        assert provider.account == "alice@gmail.com"
        assert provider.name == "imap"

    def test_init_default_host(self):
        """Test default host is imap.gmail.com."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        assert provider._host == "imap.gmail.com"
        assert provider._port == 993

    def test_init_custom_host(self):
        """Test custom IMAP host."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="user@company.com",
            keychain=mock_keychain,
            host="imap.company.com",
            port=993,
        )

        assert provider._host == "imap.company.com"

    def test_init_custom_exclude_folders(self):
        """Test custom exclude folders."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
            exclude_folders=["Trash", "Spam", "Drafts"],
        )

        assert provider._exclude_folders == ["Trash", "Spam", "Drafts"]

    def test_init_default_exclude_folders(self):
        """Test default exclude folders."""
        from ownmail.providers.imap import DEFAULT_EXCLUDE_FOLDERS, ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        assert provider._exclude_folders == DEFAULT_EXCLUDE_FOLDERS


class TestImapProviderAuthentication:
    """Tests for IMAP authentication."""

    def test_authenticate_with_valid_password(self, capsys):
        """Test successful authentication."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        mock_keychain.load_imap_password.return_value = "test-app-password"

        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        mock_conn = MagicMock()
        with patch("ownmail.providers.imap.imaplib.IMAP4_SSL", return_value=mock_conn):
            provider.authenticate()

        mock_conn.login.assert_called_once_with("alice@gmail.com", "test-app-password")
        captured = capsys.readouterr()
        assert "Connected" in captured.out

    def test_authenticate_no_password(self):
        """Test authentication fails without password."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        mock_keychain.load_imap_password.return_value = None

        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        with pytest.raises(RuntimeError, match="No password found"):
            provider.authenticate()

    def test_authenticate_invalid_password(self):
        """Test authentication failure with wrong password."""
        import imaplib

        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        mock_keychain.load_imap_password.return_value = "wrong-password"

        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        mock_conn = MagicMock()
        mock_conn.login.side_effect = imaplib.IMAP4.error("AUTHENTICATIONFAILED")

        with patch("ownmail.providers.imap.imaplib.IMAP4_SSL", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="Authentication failed"):
                provider.authenticate()

    def test_authenticate_connection_error(self):
        """Test authentication failure with connection error."""
        import imaplib

        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        mock_keychain.load_imap_password.return_value = "password"

        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        mock_conn = MagicMock()
        mock_conn.login.side_effect = imaplib.IMAP4.error("Connection refused")

        with patch("ownmail.providers.imap.imaplib.IMAP4_SSL", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="IMAP connection failed"):
                provider.authenticate()


class TestImapProviderFolders:
    """Tests for IMAP folder listing."""

    def _make_provider(self):
        """Create a provider with a mock connection."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        return provider

    def test_list_folders(self):
        """Test listing IMAP folders."""
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "Sent"',
                b'(\\HasNoChildren) "/" "Archive"',
            ],
        )

        folders = provider._list_folders()
        assert "INBOX" in folders
        assert "Sent" in folders
        assert "Archive" in folders

    def test_list_folders_excludes_noselect(self):
        """Test that non-selectable folders are excluded."""
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\Noselect \\HasChildren) "/" "[Gmail]"',
                b'(\\HasNoChildren) "/" "[Gmail]/Sent Mail"',
            ],
        )

        folders = provider._list_folders()
        assert "[Gmail]" not in folders
        assert "[Gmail]/Sent Mail" in folders

    def test_list_folders_excludes_configured(self):
        """Test that excluded folders are skipped."""
        provider = self._make_provider()
        provider._exclude_folders = ["[Gmail]/Trash", "[Gmail]/Spam"]
        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "[Gmail]/Trash"',
                b'(\\HasNoChildren) "/" "[Gmail]/Spam"',
            ],
        )

        folders = provider._list_folders()
        assert "INBOX" in folders
        assert "[Gmail]/Trash" not in folders
        assert "[Gmail]/Spam" not in folders


class TestImapProviderUIDs:
    """Tests for UID operations."""

    def _make_provider(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        return provider

    def test_get_folder_uids(self):
        """Test getting UIDs from a folder."""
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"3"])
        provider._conn.uid.return_value = ("OK", [b"1 2 3"])

        uids = provider._get_folder_uids("INBOX")
        assert uids == [1, 2, 3]

    def test_get_folder_uids_empty(self):
        """Test getting UIDs from empty folder."""
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"0"])
        provider._conn.uid.return_value = ("OK", [b""])

        uids = provider._get_folder_uids("INBOX")
        assert uids == []

    def test_get_folder_uids_select_fails(self):
        """Test when folder selection fails."""
        provider = self._make_provider()
        provider._conn.select.return_value = ("NO", [b""])

        uids = provider._get_folder_uids("NonExistent")
        assert uids == []


class TestImapProviderMessageId:
    """Tests for Message-ID extraction."""

    def _make_provider(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        return provider

    def test_extract_message_id(self):
        """Test extracting Message-ID from header bytes."""
        provider = self._make_provider()
        header = b"Message-ID: <test123@example.com>\r\n\r\n"
        msg_id = provider._extract_message_id(header)
        assert msg_id == "<test123@example.com>"

    def test_extract_message_id_none(self):
        """Test extracting from header without Message-ID."""
        provider = self._make_provider()
        header = b"Subject: Test\r\n\r\n"
        msg_id = provider._extract_message_id(header)
        assert msg_id == ""

    def test_extract_message_id_malformed(self):
        """Test extracting from malformed header."""
        provider = self._make_provider()
        msg_id = provider._extract_message_id(b"\xff\xfe")
        # Should not crash
        assert msg_id is None or isinstance(msg_id, str)


class TestImapProviderDedup:
    """Tests for message deduplication across folders."""

    def _make_provider(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
            exclude_folders=[],
        )
        provider._conn = MagicMock()
        return provider

    def test_dedup_same_message_in_multiple_folders(self):
        """Test that same message in INBOX and Sent is downloaded once."""
        provider = self._make_provider()

        # Two folders
        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "Sent"',
            ],
        )

        # Each folder has one UID
        def mock_select(folder, readonly=True):
            return ("OK", [b"1"])

        provider._conn.select.side_effect = mock_select

        def mock_uid(cmd, *args):
            if cmd == "search":
                return ("OK", [b"1"])
            elif cmd == "fetch":
                # Both folders have the same Message-ID
                return (
                    "OK",
                    [
                        (b"1 (BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <same@example.com>\r\n\r\n"),
                        b")",
                    ],
                )
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        ids = provider.get_all_message_ids()

        # Should only return one ID (deduplicated)
        assert len(ids) == 1
        assert ids[0] == "INBOX:1"

    def test_different_messages_not_deduped(self):
        """Test that different messages are both returned."""
        provider = self._make_provider()

        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "Sent"',
            ],
        )

        def mock_select(folder, readonly=True):
            return ("OK", [b"1"])

        provider._conn.select.side_effect = mock_select

        call_count = [0]

        def mock_uid(cmd, *args):
            if cmd == "search":
                return ("OK", [b"1"])
            elif cmd == "fetch":
                call_count[0] += 1
                if call_count[0] == 1:
                    return (
                        "OK",
                        [
                            (b"1 (BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <first@example.com>\r\n\r\n"),
                            b")",
                        ],
                    )
                else:
                    return (
                        "OK",
                        [
                            (b"1 (BODY[HEADER.FIELDS (MESSAGE-ID)] {36}", b"Message-ID: <second@example.com>\r\n\r\n"),
                            b")",
                        ],
                    )
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        ids = provider.get_all_message_ids()
        assert len(ids) == 2

    def test_dedup_tracks_all_folders(self):
        """Test that deduplication tracks all folders for labels."""
        provider = self._make_provider()

        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "Important"',
            ],
        )

        def mock_select(folder, readonly=True):
            return ("OK", [b"1"])

        provider._conn.select.side_effect = mock_select

        def mock_uid(cmd, *args):
            if cmd == "search":
                return ("OK", [b"1"])
            elif cmd == "fetch":
                return (
                    "OK",
                    [
                        (b"1 (BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <same@example.com>\r\n\r\n"),
                        b")",
                    ],
                )
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        ids = provider.get_all_message_ids()
        assert len(ids) == 1

        # The primary ID maps to both folders
        primary = ids[0]
        assert "INBOX" in provider._folder_lookup[primary]
        assert "Important" in provider._folder_lookup[primary]


class TestImapProviderDownload:
    """Tests for message download."""

    def _make_provider(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        return provider

    def test_download_message(self):
        """Test downloading a message by composite ID."""
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"1"])

        raw_email = b"From: test@example.com\r\nSubject: Test\r\n\r\nHello"
        provider._conn.uid.return_value = (
            "OK",
            [
                (b'1 (RFC822 {42}', raw_email),
                b")",
            ],
        )

        data, labels = provider.download_message("INBOX:1")
        assert data == raw_email
        assert "INBOX" in labels

    def test_download_message_with_dedup_labels(self):
        """Test that download returns all folders from dedup."""
        provider = self._make_provider()
        provider._folder_lookup = {
            "INBOX:1": ["INBOX", "Important", "Work"],
        }
        provider._conn.select.return_value = ("OK", [b"1"])

        raw_email = b"From: test@example.com\r\nSubject: Test\r\n\r\nHello"
        provider._conn.uid.return_value = (
            "OK",
            [
                (b'1 (RFC822 {42}', raw_email),
                b")",
            ],
        )

        data, labels = provider.download_message("INBOX:1")
        assert data == raw_email
        assert labels == ["INBOX", "Important", "Work"]

    def test_download_message_select_fails(self):
        """Test download failure when folder selection fails."""
        provider = self._make_provider()
        provider._conn.select.return_value = ("NO", [b""])

        with pytest.raises(RuntimeError, match="Cannot select folder"):
            provider.download_message("INBOX:1")

    def test_download_message_fetch_fails(self):
        """Test download failure when fetch fails."""
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"1"])
        provider._conn.uid.return_value = ("NO", [])

        with pytest.raises(RuntimeError, match="Failed to fetch"):
            provider.download_message("INBOX:1")


class TestImapProviderIncrementalSync:
    """Tests for incremental sync."""

    def _make_provider(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
            exclude_folders=[],
        )
        provider._conn = MagicMock()
        return provider

    def test_no_state_does_full_sync(self):
        """Test that None state triggers full sync."""
        provider = self._make_provider()

        # Mock get_all_message_ids
        provider.get_all_message_ids = MagicMock(return_value=["INBOX:1"])

        ids, state = provider.get_new_message_ids(None)
        assert ids == ["INBOX:1"]
        provider.get_all_message_ids.assert_called_once()

    def test_date_filter_does_full_sync(self):
        """Test that date filters trigger full scan."""
        provider = self._make_provider()

        provider.get_all_message_ids = MagicMock(return_value=["INBOX:1"])

        ids, state = provider.get_new_message_ids("some_state", since="2024-01-01")
        assert ids == ["INBOX:1"]
        assert state is None

    def test_invalid_state_does_full_sync(self, capsys):
        """Test that invalid JSON state triggers full scan."""
        provider = self._make_provider()

        provider.get_all_message_ids = MagicMock(return_value=["INBOX:1"])

        ids, state = provider.get_new_message_ids("not-json")
        assert ids == ["INBOX:1"]
        captured = capsys.readouterr()
        assert "Invalid sync state" in captured.out

    def test_incremental_returns_new_uids(self):
        """Test that incremental sync returns only new UIDs."""
        provider = self._make_provider()

        old_state = json.dumps({
            "INBOX": {"max_uid": 100, "uidvalidity": "1"},
        })

        # Only one folder
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "INBOX"'],
        )

        select_calls = [0]

        def mock_select(folder, readonly=True):
            select_calls[0] += 1
            return ("OK", [b"105"])

        provider._conn.select.side_effect = mock_select

        def mock_response(name):
            return ("OK", [b"1"])

        provider._conn.response.side_effect = mock_response

        uid_call_count = [0]

        def mock_uid(cmd, *args):
            uid_call_count[0] += 1
            if cmd == "search":
                # Return UIDs > 100
                return ("OK", [b"101 102 103"])
            elif cmd == "fetch":
                # Return Message-IDs
                return (
                    "OK",
                    [
                        (b"101 (BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <msg101@test.com>\r\n\r\n"),
                        b")",
                        (b"102 (BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <msg102@test.com>\r\n\r\n"),
                        b")",
                        (b"103 (BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <msg103@test.com>\r\n\r\n"),
                        b")",
                    ],
                )
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        ids, new_state = provider.get_new_message_ids(old_state)
        assert len(ids) == 3
        assert all(id.startswith("INBOX:") for id in ids)


class TestImapProviderDateConversion:
    """Tests for date format conversion."""

    def test_to_imap_date(self):
        """Test YYYY-MM-DD to IMAP date conversion."""
        from ownmail.providers.imap import ImapProvider

        assert ImapProvider._to_imap_date("2024-01-15") == "15-Jan-2024"
        assert ImapProvider._to_imap_date("2024-12-01") == "01-Dec-2024"


class TestImapProviderClose:
    """Tests for connection cleanup."""

    def test_close_logs_out(self):
        """Test that close calls logout."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        mock_conn = MagicMock()
        provider._conn = mock_conn

        provider.close()
        mock_conn.logout.assert_called_once()
        assert provider._conn is None

    def test_close_handles_error(self):
        """Test that close handles logout errors gracefully."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        mock_conn = MagicMock()
        mock_conn.logout.side_effect = Exception("already disconnected")
        provider._conn = mock_conn

        provider.close()  # Should not raise
        assert provider._conn is None

    def test_close_without_connection(self):
        """Test that close is safe when not connected."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        provider.close()  # Should not raise


class TestImapProviderSyncState:
    """Tests for sync state management."""

    def test_get_current_sync_state(self):
        """Test getting current sync state."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
            exclude_folders=[],
        )
        provider._conn = MagicMock()

        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "INBOX"'],
        )
        provider._conn.select.return_value = ("OK", [b"50"])
        provider._conn.response.return_value = ("OK", [b"12345"])
        provider._conn.uid.return_value = ("OK", [b"1 2 3 50"])

        state_json = provider.get_current_sync_state()
        state = json.loads(state_json)

        assert "INBOX" in state
        assert state["INBOX"]["max_uid"] == 50


class TestImapScanGmail:
    """Tests for Gmail-optimized scan path."""

    def _make_provider(self, host="imap.gmail.com"):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
            host=host,
            exclude_folders=["[Gmail]/Trash", "[Gmail]/Spam"],
        )
        provider._conn = MagicMock()
        return provider

    def test_is_gmail_true(self):
        provider = self._make_provider(host="imap.gmail.com")
        assert provider._is_gmail() is True

    def test_is_gmail_false(self):
        provider = self._make_provider(host="imap.fastmail.com")
        assert provider._is_gmail() is False

    def test_get_all_mail_folder_found(self):
        provider = self._make_provider()
        folders = ["INBOX", "[Gmail]/All Mail", "[Gmail]/Sent Mail"]
        assert provider._get_all_mail_folder(folders) == "[Gmail]/All Mail"

    def test_get_all_mail_folder_not_found(self):
        provider = self._make_provider()
        folders = ["INBOX", "Sent"]
        assert provider._get_all_mail_folder(folders) is None

    def test_get_all_mail_folder_localized(self):
        provider = self._make_provider()
        folders = ["INBOX", "[Gmail]/Tous les messages"]
        assert provider._get_all_mail_folder(folders) == "[Gmail]/Tous les messages"

    def test_scan_gmail_returns_all_mail_uids(self, capsys):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b"1 2 3 4 5"])

        folders = ["[Gmail]/All Mail", "INBOX"]
        result = provider._scan_gmail(folders, "[Gmail]/All Mail", None, None)

        assert len(result) == 5
        assert result[0] == "[Gmail]/All Mail:1"
        assert result[4] == "[Gmail]/All Mail:5"
        assert hasattr(provider, "_message_id_to_folders")

    def test_scan_gmail_scans_labels_from_other_folders(self, capsys):
        provider = self._make_provider()

        def mock_select(folder, readonly=True):
            return ("OK", [b"100"])

        def mock_uid(cmd, *args):
            if cmd == "search":
                return ("OK", [b"10 20"])
            elif cmd == "fetch":
                return ("OK", [
                    (b'10 (BODY[HEADER.FIELDS (MESSAGE-ID)] {30}',
                     b'Message-ID: <msg1@test.com>\r\n\r\n'),
                    b')',
                    (b'20 (BODY[HEADER.FIELDS (MESSAGE-ID)] {30}',
                     b'Message-ID: <msg2@test.com>\r\n\r\n'),
                    b')',
                ])

        provider._conn.select.side_effect = mock_select
        provider._conn.uid.side_effect = mock_uid

        folders = ["[Gmail]/All Mail", "INBOX"]
        result = provider._scan_gmail(folders, "[Gmail]/All Mail", None, None)

        assert len(result) == 2  # All Mail UIDs
        assert "INBOX" in provider._message_id_to_folders.get("<msg1@test.com>", [])

    def test_scan_gmail_with_date_filters(self, capsys):
        provider = self._make_provider()

        call_count = [0]

        def mock_uid(cmd, *args):
            call_count[0] += 1
            if cmd == "search":
                if call_count[0] == 1:
                    return ("OK", [b"1 2 3 4 5"])  # All
                else:
                    return ("OK", [b"3 4 5"])  # Filtered
            return ("OK", [])

        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.side_effect = mock_uid

        result = provider._scan_gmail(
            ["[Gmail]/All Mail"], "[Gmail]/All Mail", "2024-01-01", "2024-12-31"
        )
        # Should have filtered results
        assert len(result) <= 5

    def test_scan_standard_dedup_by_message_id(self, capsys):
        provider = self._make_provider(host="imap.fastmail.com")

        call_count = [0]

        def mock_select(folder, readonly=True):
            return ("OK", [b"100"])

        def mock_uid(cmd, *args):
            call_count[0] += 1
            if cmd == "search":
                return ("OK", [b"1 2"])
            elif cmd == "fetch":
                return ("OK", [
                    (b'1 (BODY[HEADER.FIELDS (MESSAGE-ID)] {30}',
                     b'Message-ID: <msg1@test.com>\r\n\r\n'),
                    b')',
                    (b'2 (BODY[HEADER.FIELDS (MESSAGE-ID)] {30}',
                     b'Message-ID: <msg2@test.com>\r\n\r\n'),
                    b')',
                ])

        provider._conn.select.side_effect = mock_select
        provider._conn.uid.side_effect = mock_uid

        folders = ["INBOX", "Sent"]
        result = provider._scan_standard(folders, None, None)

        # msg1 and msg2 appear in both folders, but should be deduped
        # First folder adds both, second folder dedupes
        assert len(result) == 2  # 2 unique messages

    def test_scan_standard_empty_folder(self, capsys):
        provider = self._make_provider(host="imap.fastmail.com")

        provider._conn.select.return_value = ("OK", [b"0"])
        provider._conn.uid.return_value = ("OK", [b""])

        result = provider._scan_standard(["EmptyFolder"], None, None)
        assert result == []


class TestImapDownloadMessage:
    """Tests for single and batch message download."""

    def _make_provider(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        provider._seen_map = {}
        provider._folder_lookup = {}
        provider._message_id_to_folders = None
        return provider

    def test_download_message_success(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = (
            "OK",
            [(b'1 (RFC822 {100}', b'From: test@example.com\r\nSubject: Hello\r\n\r\nBody'), b')'],
        )

        raw_data, labels = provider.download_message("INBOX:1")
        assert b"From: test@example.com" in raw_data
        assert "INBOX" in labels

    def test_download_message_select_fails(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("NO", [b"folder not found"])

        with pytest.raises(RuntimeError, match="Cannot select folder"):
            provider.download_message("BadFolder:1")

    def test_download_message_fetch_fails(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("NO", None)

        with pytest.raises(RuntimeError, match="Failed to fetch"):
            provider.download_message("INBOX:1")

    def test_download_message_no_data(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b"just a string, no tuple"])

        with pytest.raises(RuntimeError, match="No message data"):
            provider.download_message("INBOX:1")

    def test_download_messages_batch_groups_by_folder(self):
        provider = self._make_provider()

        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = (
            "OK",
            [
                (b'1 (UID 1 RFC822 {10}', b'From: a@b.com\r\n\r\nBody1'),
                b')',
                (b'2 (UID 2 RFC822 {10}', b'From: c@d.com\r\n\r\nBody2'),
                b')',
            ],
        )

        results = provider.download_messages_batch(["INBOX:1", "INBOX:2"])
        assert len(results) == 2
        assert results["INBOX:1"][0] is not None
        assert results["INBOX:2"][0] is not None
        # Should have only one SELECT call (same folder)
        assert provider._conn.select.call_count == 1

    def test_download_messages_batch_select_fails(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("NO", [b"error"])

        results = provider.download_messages_batch(["INBOX:1"])
        assert results["INBOX:1"][0] is None
        assert "Cannot select" in results["INBOX:1"][2]

    def test_download_messages_batch_fetch_exception(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.side_effect = Exception("connection reset")

        results = provider.download_messages_batch(["INBOX:1"])
        assert results["INBOX:1"][0] is None
        assert "connection reset" in results["INBOX:1"][2]

    def test_download_messages_batch_fetch_status_not_ok(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("NO", None)

        results = provider.download_messages_batch(["INBOX:1"])
        assert results["INBOX:1"][0] is None
        assert "FETCH failed" in results["INBOX:1"][2]

    def test_download_messages_batch_missing_uid(self):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        # Response has UID 1 but we asked for UIDs 1 and 2
        provider._conn.uid.return_value = (
            "OK",
            [
                (b'1 (UID 1 RFC822 {10}', b'From: a@b.com\r\n\r\nBody'),
                b')',
            ],
        )

        results = provider.download_messages_batch(["INBOX:1", "INBOX:2"])
        assert results["INBOX:1"][0] is not None
        assert results["INBOX:2"][0] is None
        assert "No data for UID" in results["INBOX:2"][2]

    def test_download_messages_batch_multiple_folders(self):
        provider = self._make_provider()

        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = (
            "OK",
            [
                (b'1 (UID 10 RFC822 {10}', b'From: a@b.com\r\n\r\nBody'),
                b')',
            ],
        )

        results = provider.download_messages_batch(["INBOX:10", "Sent:20"])  # noqa: F841
        # Two different folders = two SELECT calls
        assert provider._conn.select.call_count == 2


class TestImapLabels:
    """Tests for label resolution during download."""

    def _make_provider(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        provider._seen_map = {}
        provider._folder_lookup = {}
        return provider

    def test_labels_from_folder_lookup(self):
        provider = self._make_provider()
        provider._folder_lookup = {"INBOX:1": ["INBOX", "Important"]}
        provider._message_id_to_folders = None

        labels = provider._get_labels_for_downloaded("INBOX:1", b"data", "INBOX")
        assert labels == ["INBOX", "Important"]

    def test_labels_from_gmail_message_id_map(self):
        provider = self._make_provider()
        provider._message_id_to_folders = {"<msg1@test.com>": ["INBOX", "Work"]}

        raw_data = b"From: a@b.com\r\nMessage-ID: <msg1@test.com>\r\n\r\nBody"
        labels = provider._get_labels_for_downloaded(
            "[Gmail]/All Mail:1", raw_data, "[Gmail]/All Mail"
        )
        assert "[Gmail]/All Mail" in labels
        assert "INBOX" in labels
        assert "Work" in labels

    def test_labels_fallback_to_folder(self):
        provider = self._make_provider()
        provider._message_id_to_folders = {}

        raw_data = b"From: a@b.com\r\n\r\nBody"
        labels = provider._get_labels_for_downloaded("INBOX:1", raw_data, "INBOX")
        assert labels == ["INBOX"]

    def test_labels_gmail_message_id_not_found(self):
        provider = self._make_provider()
        provider._message_id_to_folders = {"<other@test.com>": ["Sent"]}

        raw_data = b"From: a@b.com\r\nMessage-ID: <msg1@test.com>\r\n\r\nBody"
        labels = provider._get_labels_for_downloaded("INBOX:1", raw_data, "INBOX")
        assert labels == ["INBOX"]


class TestImapGetNewMessageIds:
    """Tests for incremental sync."""

    def _make_provider(self, host="imap.gmail.com"):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
            host=host,
            exclude_folders=[],
        )
        provider._conn = MagicMock()
        return provider

    def test_no_state_does_full_scan(self, capsys):
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "[Gmail]/All Mail"'],
        )
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b"1 2 3"])

        new_ids, state = provider.get_new_message_ids(None)
        assert len(new_ids) == 3

    def test_invalid_state_does_full_scan(self, capsys):
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "[Gmail]/All Mail"'],
        )
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b"1 2"])

        new_ids, state = provider.get_new_message_ids("not valid json!!!")
        assert len(new_ids) == 2
        captured = capsys.readouterr()
        assert "Invalid sync state" in captured.out

    def test_date_filter_does_full_scan(self, capsys):
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "[Gmail]/All Mail"'],
        )
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b"1"])

        new_ids, state = provider.get_new_message_ids(
            '{"INBOX": {"max_uid": 10, "uidvalidity": "1"}}',
            since="2024-01-01"
        )
        assert state is None  # Full scan returns None state

    def test_incremental_sync_gmail(self, capsys):
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "[Gmail]/All Mail"'],
        )

        def mock_select(folder, readonly=True):
            return ("OK", [b"100"])

        call_count = [0]

        def mock_uid(cmd, *args):
            call_count[0] += 1
            if cmd == "search":
                if "UID" in (args[1] or ""):
                    return ("OK", [b"11 12"])  # New UIDs
                return ("OK", [b"1 2 3 10 11 12"])  # All UIDs
            return ("OK", [])

        provider._conn.select.side_effect = mock_select
        provider._conn.uid.side_effect = mock_uid
        provider._conn.response.return_value = ("OK", [b"99"])

        state = json.dumps({
            "[Gmail]/All Mail": {"max_uid": 10, "uidvalidity": "99"},
        })
        new_ids, new_state = provider.get_new_message_ids(state)

        assert len(new_ids) == 2
        assert "[Gmail]/All Mail:11" in new_ids
        assert "[Gmail]/All Mail:12" in new_ids

    def test_incremental_sync_uidvalidity_change(self, capsys):
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "[Gmail]/All Mail"'],
        )
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.response.return_value = ("OK", [b"999"])  # Changed!

        call_count = [0]

        def mock_uid(cmd, *args):
            call_count[0] += 1
            if cmd == "search":
                return ("OK", [b"1 2 3"])
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        state = json.dumps({
            "[Gmail]/All Mail": {"max_uid": 10, "uidvalidity": "100"},
        })
        new_ids, new_state = provider.get_new_message_ids(state)

        captured = capsys.readouterr()
        assert "UIDVALIDITY changed" in captured.out

    def test_incremental_sync_standard_imap(self, capsys):
        provider = self._make_provider(host="imap.fastmail.com")
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent"'],
        )
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.response.return_value = ("OK", [b"1"])

        call_count = [0]

        def mock_uid(cmd, *args):
            call_count[0] += 1
            if cmd == "search":
                if "UID" in (args[1] or ""):
                    return ("OK", [b"11"])
                return ("OK", [b"1 2 11"])
            elif cmd == "fetch":
                return ("OK", [
                    (b'11 (BODY[HEADER.FIELDS (MESSAGE-ID)] {30}',
                     b'Message-ID: <new@test.com>\r\n\r\n'),
                    b')',
                ])

        provider._conn.uid.side_effect = mock_uid

        state = json.dumps({
            "INBOX": {"max_uid": 10, "uidvalidity": "1"},
            "Sent": {"max_uid": 10, "uidvalidity": "1"},
        })
        new_ids, new_state = provider.get_new_message_ids(state)

        # msg appears in both INBOX and Sent with same Message-ID → deduped
        assert len(new_ids) == 1


class TestImapFilterByDate:
    """Tests for date-based filtering."""

    def test_to_imap_date(self):
        from ownmail.providers.imap import ImapProvider
        assert ImapProvider._to_imap_date("2024-01-15") == "15-Jan-2024"
        assert ImapProvider._to_imap_date("2024-12-01") == "01-Dec-2024"

    def test_filter_uids_by_date(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b"3 4 5"])

        result = provider._filter_uids_by_date(
            "INBOX", [1, 2, 3, 4, 5], "2024-01-01", "2024-12-31"
        )
        assert result == [3, 4, 5]

    def test_filter_uids_no_results(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b""])

        result = provider._filter_uids_by_date("INBOX", [1, 2], "2024-01-01", None)
        assert result == []

    def test_filter_uids_no_criteria(self):
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )
        provider._conn = MagicMock()

        result = provider._filter_uids_by_date("INBOX", [1, 2, 3], None, None)
        assert result == [1, 2, 3]
