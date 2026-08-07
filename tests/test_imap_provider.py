"""Tests for IMAP provider."""

import json
from unittest.mock import MagicMock, patch

import pytest

from ownmail import capture


def _watermarks(state_json):
    """The per-folder watermark map inside a stored capture state."""
    return json.loads(capture.load(state_json).cursor)


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
        """No literal exclude list by default — exclusion happens by role."""
        from ownmail.providers.imap import ImapProvider

        mock_keychain = MagicMock()
        provider = ImapProvider(
            account="alice@gmail.com",
            keychain=mock_keychain,
        )

        assert provider._exclude_folders == []


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
                b'(\\HasNoChildren) "/" "Receipts"',
                b'(\\HasNoChildren) "/" "Sent"',
                b'(\\HasNoChildren) "/" "Archive"',
            ],
        )

        folders = provider._list_folders()
        assert "Receipts" in folders
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
        provider._exclude_folders = ["Receipts"]
        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "Work"',
                b'(\\HasNoChildren) "/" "Receipts"',
                b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Trash"',
                b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"',
            ],
        )

        folders = provider._list_folders()
        assert "Work" in folders
        assert "Receipts" not in folders
        assert "[Gmail]/Trash" not in folders
        assert "[Gmail]/Spam" not in folders


class TestImapRoleExclusion:
    """Trash and spam are skipped whatever the server calls them.

    The bug this replaced: exclusion matched the literal names
    '[Gmail]/Trash' and '[Gmail]/Spam', so every other server archived its
    deleted mail as normal mail.
    """

    def _make_provider(self, exclude_folders=None, exclude_roles=None):
        from ownmail.providers.imap import ImapProvider

        provider = ImapProvider(
            account="alice@company.com",
            keychain=MagicMock(),
            host="imap.company.com",
            exclude_folders=exclude_folders,
            exclude_roles=exclude_roles,
        )
        provider._conn = MagicMock()
        return provider

    def _listing(self, provider, lines):
        provider._conn.list.return_value = ("OK", lines)
        return provider._list_folders()

    def test_special_use_trash_excluded_under_any_name(self):
        provider = self._make_provider()
        folders = self._listing(
            provider,
            [
                b'(\\HasNoChildren) "/" "Receipts"',
                b'(\\HasNoChildren \\Trash) "/" "Prullenbak"',
                b'(\\HasNoChildren \\Junk) "/" "Ongewenst"',
            ],
        )
        assert folders == ["Receipts"]

    @pytest.mark.parametrize(
        "folder",
        [
            b'(\\HasNoChildren) "/" "Trash"',
            b'(\\HasNoChildren) "/" "Deleted Items"',
            b'(\\HasNoChildren) "." "INBOX.Trash"',
        ],
    )
    def test_named_trash_excluded_without_special_use(self, folder):
        """Servers that don't advertise SPECIAL-USE fall back to names."""
        provider = self._make_provider()
        assert self._listing(provider, [b'(\\HasNoChildren) "/" "Receipts"', folder]) == ["Receipts"]

    def test_ordinary_folders_kept(self):
        provider = self._make_provider()
        folders = self._listing(
            provider,
            [
                b'(\\HasNoChildren) "/" "Work"',
                b'(\\HasNoChildren) "/" "Receipts"',
                b'(\\HasNoChildren \\Sent) "/" "Sent"',
            ],
        )
        assert folders == ["Work", "Receipts", "Sent"]

    def test_named_exclusion_adds_to_the_roles_rather_than_replacing_them(self):
        """Naming a folder never re-admits a role.

        It used to: an explicit list took over wholesale, which was the only
        way to archive your own trash. That configuration is gone — purge
        moves mail TO trash, so a trash-inclusive filter would keep passing
        everything it ever purged and the sweep would never settle.
        """
        provider = self._make_provider(exclude_folders=["Receipts"])
        folders = self._listing(
            provider,
            [
                b'(\\HasNoChildren) "/" "Work"',
                b'(\\HasNoChildren) "/" "Receipts"',
                b'(\\HasNoChildren \\Trash) "/" "Trash"',
            ],
        )
        assert folders == ["Work"]

    def test_empty_list_still_excludes_the_roles(self):
        provider = self._make_provider(exclude_folders=[])
        folders = self._listing(
            provider,
            [b'(\\HasNoChildren) "/" "Work"', b'(\\HasNoChildren \\Trash) "/" "Trash"'],
        )
        assert folders == ["Work"]

    def test_inbox_and_drafts_excluded_by_default(self):
        """The filter admits a message once its owner has acted on it."""
        provider = self._make_provider()
        folders = self._listing(
            provider,
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\Drafts) "/" "Concepten"',
                b'(\\HasNoChildren \\Sent) "/" "Verzonden"',
            ],
        )
        # Sent stays: outgoing mail has no triage step, so waiting for one
        # would mean never archiving your own mail.
        assert folders == ["Verzonden"]

    def test_inbox_can_be_admitted_by_config(self):
        provider = self._make_provider(exclude_roles=["drafts"])
        folders = self._listing(
            provider,
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\Drafts) "/" "Concepten"',
                b'(\\HasNoChildren \\Trash) "/" "Trash"',
            ],
        )
        assert folders == ["INBOX"]

    def test_roles_recorded_for_kept_folders(self):
        provider = self._make_provider()
        self._listing(
            provider,
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\Sent) "/" "Verzonden"',
                b'(\\HasNoChildren) "/" "Receipts"',
            ],
        )
        assert provider._folder_roles == {"INBOX": "inbox", "Verzonden": "sent"}


class TestParseListResponse:
    def test_skips_non_bytes_entries(self):
        """imaplib mixes continuation tuples into the response list."""
        from ownmail.providers.imap import parse_list_response

        parsed = parse_list_response([b'(\\HasNoChildren) "/" "INBOX"', (b"x", b"y"), None])
        assert parsed == [("INBOX", "\\HasNoChildren", "/")]

    def test_skips_unparseable_lines(self):
        """Includes NIL-delimiter listings — see TASK-16."""
        from ownmail.providers.imap import parse_list_response

        assert parse_list_response([b'(\\HasNoChildren) NIL "INBOX"']) == []


class TestDiscoverRoleFolders:
    """Setup's live lookup of a server's real trash/spam folder names."""

    def test_returns_matching_folders(self):
        from ownmail import roles
        from ownmail.providers.imap import discover_role_folders

        conn = MagicMock()
        conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\Trash) "/" "Papierkorb"',
                b'(\\HasNoChildren) "/" "Junk"',
            ],
        )

        assert discover_role_folders(conn, roles.DEFAULT_EXCLUDE_ROLES) == ["INBOX", "Papierkorb", "Junk"]

    def test_bad_status_returns_empty(self):
        from ownmail import roles
        from ownmail.providers.imap import discover_role_folders

        conn = MagicMock()
        conn.list.return_value = ("NO", [])
        assert discover_role_folders(conn, roles.DEFAULT_EXCLUDE_ROLES) == []

    def test_failure_is_swallowed(self):
        """Informational only — it must never fail a working setup."""
        from ownmail import roles
        from ownmail.providers.imap import discover_role_folders

        conn = MagicMock()
        conn.list.side_effect = OSError("connection reset")
        assert discover_role_folders(conn, roles.DEFAULT_EXCLUDE_ROLES) == []


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
        """Test that same message in Work and Sent is downloaded once."""
        provider = self._make_provider()

        # Two folders
        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "Work"',
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
                        (b"1 (UID 1 BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <same@example.com>\r\n\r\n"),
                        b")",
                    ],
                )
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        ids = provider.get_all_message_ids()

        # Should only return one ID (deduplicated)
        assert len(ids) == 1
        assert ids[0] == "Work:1"

    def test_different_messages_not_deduped(self):
        """Test that different messages are both returned."""
        provider = self._make_provider()

        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "Work"',
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
                            (
                                b"1 (UID 1 BODY[HEADER.FIELDS (MESSAGE-ID)] {35}",
                                b"Message-ID: <first@example.com>\r\n\r\n",
                            ),
                            b")",
                        ],
                    )
                else:
                    return (
                        "OK",
                        [
                            (
                                b"1 (UID 1 BODY[HEADER.FIELDS (MESSAGE-ID)] {36}",
                                b"Message-ID: <second@example.com>\r\n\r\n",
                            ),
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
                b'(\\HasNoChildren) "/" "Work"',
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
                        (b"1 (UID 1 BODY[HEADER.FIELDS (MESSAGE-ID)] {35}", b"Message-ID: <same@example.com>\r\n\r\n"),
                        b")",
                    ],
                )
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        ids = provider.get_all_message_ids()
        assert len(ids) == 1

        # The primary ID maps to both folders
        primary = ids[0]
        assert "Work" in provider._folder_lookup[primary]
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
                (b"1 (BODY[] {42}", raw_email),
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
                (b"1 (BODY[] {42}", raw_email),
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

        old_state = json.dumps(
            {
                "Work": {"max_uid": 100, "uidvalidity": "1"},
            }
        )

        # Only one folder
        provider._conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "Work"'],
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
                        (
                            b"101 (UID 101 BODY[HEADER.FIELDS (MESSAGE-ID)] {35}",
                            b"Message-ID: <msg101@test.com>\r\n\r\n",
                        ),
                        b")",
                        (
                            b"102 (UID 102 BODY[HEADER.FIELDS (MESSAGE-ID)] {35}",
                            b"Message-ID: <msg102@test.com>\r\n\r\n",
                        ),
                        b")",
                        (
                            b"103 (UID 103 BODY[HEADER.FIELDS (MESSAGE-ID)] {35}",
                            b"Message-ID: <msg103@test.com>\r\n\r\n",
                        ),
                        b")",
                    ],
                )
            return ("OK", [])

        provider._conn.uid.side_effect = mock_uid

        ids, new_state = provider.get_new_message_ids(old_state)
        assert len(ids) == 3
        assert all(id.startswith("Work:") for id in ids)


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
            [b'(\\HasNoChildren) "/" "Work"'],
        )
        provider._conn.select.return_value = ("OK", [b"50"])
        provider._conn.response.return_value = ("OK", [b"12345"])
        provider._conn.uid.return_value = ("OK", [b"1 2 3 50"])

        state = _watermarks(provider.get_current_sync_state())

        assert "Work" in state
        assert state["Work"]["max_uid"] == 50


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
        # Nothing is sitting in the inbox unless a test says so. Pinned
        # because every All-Mail scan now reads it, and a mock that answers
        # every SEARCH the same way would report the whole folder excluded.
        provider._enumerate_excluded = lambda all_mail: frozenset()
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
        provider._folder_roles = {"[Gmail]/All Mail": "all", "[Gmail]/Sent Mail": "sent"}
        assert provider._get_all_mail_folder(folders) == "[Gmail]/All Mail"

    def test_get_all_mail_folder_not_found(self):
        provider = self._make_provider()
        folders = ["INBOX", "Sent"]
        provider._folder_roles = {"INBOX": "inbox", "Sent": "sent"}
        assert provider._get_all_mail_folder(folders) is None

    def test_get_all_mail_folder_any_locale(self):
        """\\All identifies All Mail in locales no name list could enumerate."""
        provider = self._make_provider()
        provider._conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\All) "/" "[Gmail]/\xec\xa0\x84\xec\x9a\xb0\xed\x8e\xb8\xec\xa7\x80"',
            ],
        )
        folders = provider._list_folders()
        assert provider._get_all_mail_folder(folders) == "[Gmail]/전우편지"

    def test_scan_gmail_returns_all_mail_uids(self, capsys):
        provider = self._make_provider()
        provider._conn.select.return_value = ("OK", [b"100"])
        provider._conn.uid.return_value = ("OK", [b"1 2 3 4 5"])

        folders = ["[Gmail]/All Mail", "INBOX"]
        provider._label_folders = folders  # normally set by _list_folders
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
                return (
                    "OK",
                    [
                        (b"10 (UID 10 BODY[HEADER.FIELDS (MESSAGE-ID)] {30}", b"Message-ID: <msg1@test.com>\r\n\r\n"),
                        b")",
                        (b"20 (UID 20 BODY[HEADER.FIELDS (MESSAGE-ID)] {30}", b"Message-ID: <msg2@test.com>\r\n\r\n"),
                        b")",
                    ],
                )

        provider._conn.select.side_effect = mock_select
        provider._conn.uid.side_effect = mock_uid

        folders = ["[Gmail]/All Mail", "INBOX"]
        provider._label_folders = folders  # normally set by _list_folders
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

        provider._label_folders = ["[Gmail]/All Mail"]
        result = provider._scan_gmail(["[Gmail]/All Mail"], "[Gmail]/All Mail", "2024-01-01", "2024-12-31")
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
                return (
                    "OK",
                    [
                        (b"1 (UID 1 BODY[HEADER.FIELDS (MESSAGE-ID)] {30}", b"Message-ID: <msg1@test.com>\r\n\r\n"),
                        b")",
                        (b"2 (UID 2 BODY[HEADER.FIELDS (MESSAGE-ID)] {30}", b"Message-ID: <msg2@test.com>\r\n\r\n"),
                        b")",
                    ],
                )

        provider._conn.select.side_effect = mock_select
        provider._conn.uid.side_effect = mock_uid

        folders = ["INBOX", "Sent"]
        provider._label_folders = folders  # normally set by _list_folders
        result = provider._scan_standard(folders, None, None)

        # msg1 and msg2 appear in both folders, but should be deduped
        # First folder adds both, second folder dedupes
        assert len(result) == 2  # 2 unique messages

    def test_scan_standard_empty_folder(self, capsys):
        provider = self._make_provider(host="imap.fastmail.com")

        provider._conn.select.return_value = ("OK", [b"0"])
        provider._conn.uid.return_value = ("OK", [b""])

        provider._label_folders = ["EmptyFolder"]
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
            [(b"1 (BODY[] {100}", b"From: test@example.com\r\nSubject: Hello\r\n\r\nBody"), b")"],
        )

        raw_data, labels = provider.download_message("INBOX:1")
        assert b"From: test@example.com" in raw_data
        assert "INBOX" in labels
        # BODY.PEEK[], not RFC822 — see test_fetches_with_body_peek
        provider._conn.uid.assert_called_once_with("fetch", "1", "(BODY.PEEK[])")

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
                (b"1 (UID 1 BODY[] {10}", b"From: a@b.com\r\n\r\nBody1"),
                b")",
                (b"2 (UID 2 BODY[] {10}", b"From: c@d.com\r\n\r\nBody2"),
                b")",
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
                (b"1 (UID 1 BODY[] {10}", b"From: a@b.com\r\n\r\nBody"),
                b")",
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
                (b"1 (UID 10 BODY[] {10}", b"From: a@b.com\r\n\r\nBody"),
                b")",
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
        labels = provider._get_labels_for_downloaded("[Gmail]/All Mail:1", raw_data, "[Gmail]/All Mail")
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
            '{"INBOX": {"max_uid": 10, "uidvalidity": "1"}}', since="2024-01-01"
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

        state = json.dumps(
            {
                "[Gmail]/All Mail": {"max_uid": 10, "uidvalidity": "99"},
            }
        )
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

        state = json.dumps(
            {
                "[Gmail]/All Mail": {"max_uid": 10, "uidvalidity": "100"},
            }
        )
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
                return (
                    "OK",
                    [
                        (b"11 (UID 11 BODY[HEADER.FIELDS (MESSAGE-ID)] {30}", b"Message-ID: <new@test.com>\r\n\r\n"),
                        b")",
                    ],
                )

        provider._conn.uid.side_effect = mock_uid

        state = json.dumps(
            {
                "INBOX": {"max_uid": 10, "uidvalidity": "1"},
                "Sent": {"max_uid": 10, "uidvalidity": "1"},
            }
        )
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

        result = provider._filter_uids_by_date("INBOX", [1, 2, 3, 4, 5], "2024-01-01", "2024-12-31")
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


def _imap_provider(conn, **kwargs):
    """Build an authenticated ImapProvider wired to a mock connection."""
    from ownmail.providers.imap import ImapProvider

    keychain = MagicMock()
    keychain.load_imap_password.return_value = "pw"
    provider = ImapProvider(account="alice@gmail.com", keychain=keychain, **kwargs)
    provider._conn = conn
    return provider


class TestImapBatchDownload:
    """Tests for download_messages_batch."""

    def test_groups_by_folder_and_returns_payloads(self):
        """Messages in one folder should need only a single SELECT."""
        conn = MagicMock()
        conn.select.return_value = ("OK", [b"2"])
        conn.uid.return_value = (
            "OK",
            [(b"1 (UID 10 BODY[] {5}", b"body1"), (b"2 (UID 11 BODY[] {5}", b"body2")],
        )
        provider = _imap_provider(conn)

        results = provider.download_messages_batch(["INBOX:10", "INBOX:11"])

        assert conn.select.call_count == 1
        assert results["INBOX:10"][0] == b"body1"
        assert results["INBOX:11"][0] == b"body2"
        assert results["INBOX:10"][2] is None

    def test_fetches_with_body_peek(self):
        """The batch FETCH must ask for BODY.PEEK[], not RFC822.

        iCloud answers an RFC822 fetch with a bare '* 1 FETCH (UID 194)' — OK
        status, no message data — so every download fails. BODY.PEEK[] also
        keeps \\Seen off without relying on the read-only SELECT.
        """
        conn = MagicMock()
        conn.select.return_value = ("OK", [b"2"])
        conn.uid.return_value = ("OK", [(b"1 (UID 10 BODY[] {5}", b"body1")])
        provider = _imap_provider(conn)

        provider.download_messages_batch(["INBOX:10"])

        conn.uid.assert_called_once_with("fetch", "10", "(BODY.PEEK[])")

    def test_response_without_message_data_is_flagged(self):
        """A FETCH that returns UIDs but no bodies should error, not crash.

        This is what iCloud does for RFC822: status OK, one bare line per UID.
        """
        conn = MagicMock()
        conn.select.return_value = ("OK", [b"2"])
        conn.uid.return_value = ("OK", [b"1 (UID 10)", b"2 (UID 11)"])
        provider = _imap_provider(conn)

        results = provider.download_messages_batch(["INBOX:10", "INBOX:11"])

        assert results["INBOX:10"] == (None, [], "No data for UID 10")
        assert results["INBOX:11"] == (None, [], "No data for UID 11")

    def test_unselectable_folder_errors_every_message(self):
        """If SELECT fails, every message in that folder should error."""
        conn = MagicMock()
        conn.select.return_value = ("NO", [b""])
        provider = _imap_provider(conn)

        results = provider.download_messages_batch(["Gone:1", "Gone:2"])

        assert all(r[0] is None for r in results.values())
        assert "Cannot select folder: Gone" in results["Gone:1"][2]

    def test_fetch_exception_is_recorded(self):
        """An exception during FETCH should be captured per message."""
        conn = MagicMock()
        conn.select.return_value = ("OK", [b"1"])
        conn.uid.side_effect = OSError("connection reset")
        provider = _imap_provider(conn)

        results = provider.download_messages_batch(["INBOX:10"])

        assert results["INBOX:10"][0] is None
        assert results["INBOX:10"][2] == "connection reset"

    def test_fetch_failure_status_is_recorded(self):
        """A non-OK FETCH status should be reported for the batch."""
        conn = MagicMock()
        conn.select.return_value = ("OK", [b"1"])
        conn.uid.return_value = ("NO", [None])
        provider = _imap_provider(conn)

        results = provider.download_messages_batch(["INBOX:10"])

        assert "FETCH failed in INBOX" in results["INBOX:10"][2]

    def test_missing_uid_in_response_is_flagged(self):
        """A UID the server never returned should be reported as missing."""
        conn = MagicMock()
        conn.select.return_value = ("OK", [b"2"])
        conn.uid.return_value = ("OK", [(b"1 (UID 10 BODY[] {5}", b"body1")])
        provider = _imap_provider(conn)

        results = provider.download_messages_batch(["INBOX:10", "INBOX:11"])

        assert results["INBOX:10"][0] == b"body1"
        assert results["INBOX:11"][0] is None
        assert "No data for UID 11" in results["INBOX:11"][2]

    def test_labels_default_to_the_source_folder(self):
        """Without a dedup map, a message is labelled with its folder."""
        conn = MagicMock()
        conn.select.return_value = ("OK", [b"1"])
        conn.uid.return_value = ("OK", [(b"1 (UID 10 BODY[] {5}", b"body1")])
        provider = _imap_provider(conn)

        results = provider.download_messages_batch(["INBOX:10"])

        assert results["INBOX:10"][1] == ["INBOX"]


class TestImapLabelResolution:
    """Tests for _get_labels_for_downloaded."""

    def test_folder_lookup_wins(self):
        """A composite id present in the dedup lookup should use it."""
        provider = _imap_provider(MagicMock())
        provider._folder_lookup = {"INBOX:10": ["INBOX", "Work"]}

        assert provider._get_labels_for_downloaded("INBOX:10", b"", "INBOX") == ["INBOX", "Work"]

    def test_gmail_message_id_lookup(self):
        """The Gmail path should add folders matched by Message-ID."""
        provider = _imap_provider(MagicMock())
        provider._message_id_to_folders = {"<abc@example.com>": ["Work", "Starred"]}
        raw = b"Message-ID: <abc@example.com>\r\nSubject: S\r\n\r\nbody\r\n"

        labels = provider._get_labels_for_downloaded("[Gmail]/All Mail:10", raw, "[Gmail]/All Mail")

        assert labels == ["[Gmail]/All Mail", "Work", "Starred"]

    def test_unknown_message_id_falls_back_to_folder(self):
        """A Message-ID not in the map should yield just the folder."""
        provider = _imap_provider(MagicMock())
        provider._message_id_to_folders = {"<other@example.com>": ["Work"]}
        raw = b"Message-ID: <abc@example.com>\r\n\r\nbody\r\n"

        assert provider._get_labels_for_downloaded("INBOX:10", raw, "INBOX") == ["INBOX"]

    def test_unparseable_raw_falls_back_to_folder(self):
        """Raw bytes that fail to parse should not break label resolution."""
        from unittest.mock import patch

        provider = _imap_provider(MagicMock())
        provider._message_id_to_folders = {"<abc@example.com>": ["Work"]}

        with patch("email.message_from_bytes", side_effect=ValueError("bad")):
            assert provider._get_labels_for_downloaded("INBOX:10", b"junk", "INBOX") == ["INBOX"]


class TestImapMessageIdExtraction:
    """Tests for _extract_message_id and _get_message_ids_for_uids."""

    def test_extracts_message_id(self):
        """A Message-ID header should be returned stripped."""
        provider = _imap_provider(MagicMock())
        assert provider._extract_message_id(b"Message-ID: <abc@example.com>\r\n") == "<abc@example.com>"

    def test_missing_message_id_returns_empty(self):
        """Headers without a Message-ID should yield an empty string."""
        provider = _imap_provider(MagicMock())
        assert provider._extract_message_id(b"Subject: no id\r\n") == ""

    def test_parse_failure_returns_none(self):
        """A parse failure should return None rather than raise."""
        from unittest.mock import patch

        provider = _imap_provider(MagicMock())
        with patch("email.message_from_bytes", side_effect=ValueError("bad")):
            assert provider._extract_message_id(b"junk") is None

    def test_empty_uid_list_short_circuits(self):
        """No UIDs means no FETCH should be issued."""
        conn = MagicMock()
        provider = _imap_provider(conn)

        assert provider._get_message_ids_for_uids("INBOX", []) == {}
        conn.uid.assert_not_called()

    def test_maps_uids_to_message_ids(self):
        """Each fetched UID should map to its Message-ID."""
        conn = MagicMock()
        conn.uid.return_value = (
            "OK",
            [
                (b"1 (UID 10 BODY[HEADER.FIELDS (MESSAGE-ID)] {30}", b"Message-ID: <a@example.com>\r\n"),
                (b"2 (UID 11 BODY[HEADER.FIELDS (MESSAGE-ID)] {30}", b"Message-ID: <b@example.com>\r\n"),
            ],
        )
        provider = _imap_provider(conn)

        result = provider._get_message_ids_for_uids("INBOX", [10, 11])

        # Keyed by UID, not by the leading sequence number
        assert result == {10: "<a@example.com>", 11: "<b@example.com>"}

    def test_failed_fetch_batch_is_skipped(self):
        """A non-OK FETCH should contribute nothing rather than raise."""
        conn = MagicMock()
        conn.uid.return_value = ("NO", [None])
        provider = _imap_provider(conn)

        assert provider._get_message_ids_for_uids("INBOX", [10]) == {}


class TestImapUidValidity:
    """Tests for _get_uidvalidity."""

    def test_reads_uidvalidity_response(self):
        """The UIDVALIDITY response code should be decoded."""
        conn = MagicMock()
        conn.response.return_value = ("OK", [b"12345"])
        provider = _imap_provider(conn)

        assert provider._get_uidvalidity(None) == "12345"

    def test_missing_uidvalidity_returns_none(self):
        """An empty response should yield None."""
        conn = MagicMock()
        conn.response.return_value = ("OK", [None])
        provider = _imap_provider(conn)

        assert provider._get_uidvalidity(None) is None

    def test_error_returns_none(self):
        """An exception reading the response should yield None."""
        conn = MagicMock()
        conn.response.side_effect = OSError("closed")
        provider = _imap_provider(conn)

        assert provider._get_uidvalidity(None) is None


class TestImapFolderListing:
    """Tests for _list_folders."""

    def test_failed_list_raises(self):
        """A non-OK LIST should raise rather than return partial data."""
        conn = MagicMock()
        conn.list.return_value = ("NO", [])
        provider = _imap_provider(conn)

        with pytest.raises(RuntimeError, match="Failed to list IMAP folders"):
            provider._list_folders()

    def test_noselect_folders_are_skipped(self):
        """Container folders marked \\Noselect should be excluded."""
        conn = MagicMock()
        conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "Work"',
                b'(\\Noselect \\HasChildren) "/" "[Gmail]"',
                b'(\\HasNoChildren) "/" "Work"',
            ],
        )
        provider = _imap_provider(conn)

        folders = provider._list_folders()

        assert "Work" in folders
        assert "Work" in folders
        assert "[Gmail]" not in folders


class TestImapIncrementalScan:
    """Tests for the UID-based incremental sync scan."""

    def _conn(self, folders, uids_by_folder, uidvalidity="100"):
        """A connection whose LIST/SELECT/SEARCH replay the given folders."""
        conn = MagicMock()
        conn.list.return_value = ("OK", [f'(\\HasNoChildren) "/" "{f}"'.encode() for f in folders])
        conn.select.return_value = ("OK", [b"1"])
        conn.response.return_value = ("OK", [uidvalidity.encode()])

        selected = {"folder": None}

        def select(spec, readonly=False):
            selected["folder"] = spec.strip('"')
            return ("OK", [b"1"])

        def uid(command, *args):
            folder = selected["folder"]
            if command == "search":
                uids = uids_by_folder.get(folder, [])
                return ("OK", [b" ".join(str(u).encode() for u in uids)])
            return ("OK", [])

        conn.select.side_effect = select
        conn.uid.side_effect = uid
        return conn

    def test_only_uids_above_the_watermark_are_returned(self):
        """Messages at or below the stored max_uid should be skipped."""
        conn = self._conn(["Work"], {"Work": [8, 9, 10, 11]})
        provider = _imap_provider(conn, exclude_folders=[])
        state = json.dumps({"Work": {"max_uid": 9, "uidvalidity": "100"}})

        with patch("time.sleep"):
            new_ids, new_state = provider.get_new_message_ids(state)

        assert new_ids == ["Work:10", "Work:11"]
        assert _watermarks(new_state)["Work"]["max_uid"] == 11

    def test_changed_uidvalidity_forces_full_rescan(self, capsys):
        """A rebuilt folder (new UIDVALIDITY) should be rescanned from zero."""
        conn = self._conn(["Work"], {"Work": [1, 2]}, uidvalidity="999")
        provider = _imap_provider(conn, exclude_folders=[])
        state = json.dumps({"Work": {"max_uid": 5, "uidvalidity": "100"}})

        with patch("time.sleep"):
            new_ids, _ = provider.get_new_message_ids(state)

        assert new_ids == ["Work:1", "Work:2"]
        assert "UIDVALIDITY changed for Work" in capsys.readouterr().out

    def test_invalid_sync_state_falls_back_to_full_scan(self, capsys):
        """Unparseable state should trigger a full scan, not a crash."""
        conn = self._conn(["INBOX"], {"INBOX": [1]})
        provider = _imap_provider(conn, exclude_folders=[])

        with patch("time.sleep"):
            with patch.object(provider, "get_all_message_ids", return_value=["INBOX:1"]) as mock_full:
                new_ids, new_state = provider.get_new_message_ids("{not json")

        mock_full.assert_called_once()
        assert new_ids == ["INBOX:1"]
        assert new_state is None
        assert "Invalid sync state" in capsys.readouterr().out

    def test_date_filter_forces_full_scan(self):
        """A date filter should bypass incremental sync entirely."""
        provider = _imap_provider(self._conn(["INBOX"], {}))

        with patch.object(provider, "get_all_message_ids", return_value=[]) as mock_full:
            new_ids, new_state = provider.get_new_message_ids("{}", since="2024-01-01")

        mock_full.assert_called_once_with(since="2024-01-01", until=None)
        assert new_state is None

    def test_unselectable_folder_is_skipped(self):
        """A folder that cannot be selected should not abort the scan."""
        conn = self._conn(["Work", "Broken"], {"Work": [1]})
        selected = {"folder": None}

        def select(spec, readonly=False):
            folder = spec.strip('"')
            selected["folder"] = folder
            return ("NO", [b""]) if folder == "Broken" else ("OK", [b"1"])

        def uid(command, *args):
            if command == "search":
                return ("OK", [b"1"]) if selected["folder"] == "Work" else ("OK", [b""])
            return ("OK", [])

        conn.select.side_effect = select
        conn.uid.side_effect = uid
        provider = _imap_provider(conn, exclude_folders=[])

        with patch("time.sleep"):
            new_ids, _ = provider.get_new_message_ids(json.dumps({}))

        assert new_ids == ["Work:1"]

    def test_empty_search_result_yields_nothing(self):
        """A folder with no matching UIDs should contribute no ids."""
        conn = self._conn(["INBOX"], {"INBOX": []})
        provider = _imap_provider(conn, exclude_folders=[])

        with patch("time.sleep"):
            new_ids, _ = provider.get_new_message_ids(json.dumps({}))

        assert new_ids == []


class TestImapProviderProperties:
    """Tests for the provider's identity and batching properties."""

    def test_source_name_defaults_to_imap(self):
        """With no explicit source name the provider defaults to 'imap'."""
        provider = _imap_provider(MagicMock())
        assert provider.source_name == "imap"

    def test_explicit_source_name_is_kept(self):
        """An explicit source name should be returned as-is."""
        provider = _imap_provider(MagicMock(), source_name="work")
        assert provider.source_name == "work"

    def test_download_batch_size_is_the_fetch_batch(self):
        """The advertised batch size should match the FETCH body batch."""
        from ownmail.providers.imap import FETCH_BODY_BATCH_SIZE

        assert _imap_provider(MagicMock()).download_batch_size == FETCH_BODY_BATCH_SIZE

    def test_is_gmail_detection(self):
        """Gmail's IMAP host should be recognised, others not."""
        assert _imap_provider(MagicMock(), host="imap.gmail.com")._is_gmail() is True
        assert _imap_provider(MagicMock(), host="imap.example.com")._is_gmail() is False


def _wire_folders(conn, folder_msgs):
    """Make a mock connection serve {folder: {uid: message_id}} to a scan."""
    selected = {"folder": None}

    def mock_select(folder, readonly=True):
        selected["folder"] = folder.strip('"')
        return ("OK", [b"1"])

    def mock_uid(cmd, *args):
        msgs = folder_msgs.get(selected["folder"], {})
        if cmd == "search":
            if not msgs:
                return ("OK", [b""])
            return ("OK", [" ".join(str(u) for u in msgs).encode()])
        if cmd == "fetch":
            data = []
            for uid, msg_id in msgs.items():
                data.append(
                    (
                        f"1 (UID {uid} BODY[HEADER.FIELDS (MESSAGE-ID)] {{30}}".encode(),
                        f"Message-ID: {msg_id}\r\n\r\n".encode(),
                    )
                )
                data.append(b")")
            return ("OK", data)
        return ("OK", [b""])

    conn.select.side_effect = mock_select
    conn.uid.side_effect = mock_uid


class TestImapFolderMembership:
    """Tests for the composite-id -> folders map `relabel` runs on."""

    def test_every_composite_id_maps_to_all_folders(self):
        """A duplicate's own folder:uid resolves to the full folder set.

        Only the elected primary is ever downloaded, so the scan used to
        record only that one. `relabel` has to match rows captured on an
        earlier run, where a different folder may have won the election.
        """
        conn = MagicMock()
        conn.list.return_value = ("OK", [b'(\\HasNoChildren) "/" "Work"', b'(\\HasNoChildren) "/" "Receipts"'])
        _wire_folders(conn, {"Work": {1: "<m1@test>"}, "Receipts": {7: "<m1@test>"}})
        provider = _imap_provider(conn, host="imap.fastmail.com")

        with patch("time.sleep"):
            membership = provider.scan_folder_membership()

        assert membership["Work:1"] == ["Work", "Receipts"]
        assert membership["Receipts:7"] == ["Work", "Receipts"]

    def test_single_folder_message_maps_to_itself(self):
        conn = MagicMock()
        conn.list.return_value = ("OK", [b'(\\HasNoChildren) "/" "Work"'])
        _wire_folders(conn, {"Work": {4: "<solo@test>"}})
        provider = _imap_provider(conn, host="imap.fastmail.com")

        with patch("time.sleep"):
            membership = provider.scan_folder_membership()

        assert membership == {"Work:4": ["Work"]}

    def test_gmail_all_mail_path_has_no_membership(self):
        """All Mail keys membership by Message-ID, which relabel can't join on."""
        conn = MagicMock()
        conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"'],
        )
        _wire_folders(conn, {"INBOX": {1: "<m1@test>"}, "[Gmail]/All Mail": {9: "<m1@test>"}})
        provider = _imap_provider(conn, host="imap.gmail.com")

        with patch("time.sleep"):
            assert provider.scan_folder_membership() is None

    def test_standard_scan_clears_stale_gmail_map(self):
        """A standard scan must not leave a Message-ID map for label lookup."""
        conn = MagicMock()
        conn.list.return_value = ("OK", [b'(\\HasNoChildren) "/" "INBOX"'])
        _wire_folders(conn, {"INBOX": {1: "<m1@test>"}})
        provider = _imap_provider(conn, host="imap.fastmail.com")
        provider._message_id_to_folders = {"<m1@test>": ["Stale"]}

        with patch("time.sleep"):
            provider.scan_folder_membership()

        assert provider._message_id_to_folders == {}


class TestImapLabelSources:
    """Not downloading from a folder is not the same as disowning its name."""

    def _conn(self, folders, contents):
        """A connection where ``contents`` maps folder -> {uid: message-id}."""
        conn = MagicMock()
        conn.list.return_value = ("OK", [f'(\\HasNoChildren) "/" "{f}"'.encode() for f in folders])
        conn.response.return_value = ("OK", [b"100"])
        selected = {"folder": None}

        def select(spec, readonly=False):
            selected["folder"] = spec.strip('"')
            return ("OK", [b"1"])

        def uid(command, *args):
            held = contents.get(selected["folder"], {})
            if command == "search":
                return ("OK", [b" ".join(str(u).encode() for u in held)])
            payload = []
            for u, msg_id in held.items():
                payload.append(
                    (f"1 (UID {u} BODY[HEADER.FIELDS (MESSAGE-ID)]".encode(), f"Message-ID: {msg_id}\r\n\r\n".encode())
                )
                payload.append(b")")
            return ("OK", payload)

        conn.select.side_effect = select
        conn.uid.side_effect = uid
        return conn

    def test_named_exclusion_still_contributes_a_label(self):
        """The folder describes real organization even when nothing is pulled from it."""
        conn = self._conn(
            ["Work", "Newsletters"],
            {"Work": {1: "<a@x>"}, "Newsletters": {7: "<a@x>"}},
        )
        provider = _imap_provider(conn, host="imap.fastmail.com", exclude_folders=["Newsletters"])

        with patch("time.sleep"):
            ids = provider.get_all_message_ids()

        assert ids == ["Work:1"]
        assert provider._folder_lookup["Work:1"] == ["Work", "Newsletters"]

    def test_role_excluded_folder_is_not_a_label_source(self):
        """A trash copy shares its Message-ID with the filed copy.

        Adopting the folder would relabel real mail as trash — the archive
        damage TASK-25 exists to clean up.
        """
        conn = self._conn(
            ["Work", "Trash"],
            {"Work": {1: "<a@x>"}, "Trash": {7: "<a@x>"}},
        )
        provider = _imap_provider(conn, host="imap.fastmail.com")

        with patch("time.sleep"):
            ids = provider.get_all_message_ids()

        assert ids == ["Work:1"]
        assert provider._folder_lookup["Work:1"] == ["Work"]

    def test_a_message_held_only_in_an_excluded_folder_is_not_downloaded(self):
        """Contributing a label must not smuggle the message into the archive."""
        conn = self._conn(["INBOX", "Newsletters"], {"INBOX": {}, "Newsletters": {7: "<only@x>"}})
        provider = _imap_provider(conn, host="imap.fastmail.com", exclude_folders=["Newsletters"])

        with patch("time.sleep"):
            assert provider.get_all_message_ids() == []

    def test_download_source_wins_the_election_whatever_the_scan_order(self):
        """The excluded copy is seen first here, so the primary must move."""
        conn = self._conn(
            ["Newsletters", "Work"],
            {"Newsletters": {7: "<a@x>"}, "Work": {1: "<a@x>"}},
        )
        provider = _imap_provider(conn, host="imap.fastmail.com", exclude_folders=["Newsletters"])

        with patch("time.sleep"):
            assert provider.get_all_message_ids() == ["Work:1"]


class TestImapFilterChange:
    """Widening the filter has to invalidate the watermark."""

    def _conn(self, folders, uids_by_folder):
        conn = MagicMock()
        conn.list.return_value = ("OK", [f'(\\HasNoChildren) "/" "{f}"'.encode() for f in folders])
        conn.response.return_value = ("OK", [b"100"])
        selected = {"folder": None}

        def select(spec, readonly=False):
            selected["folder"] = spec.strip('"')
            return ("OK", [b"1"])

        def uid(command, *args):
            if command == "search":
                return ("OK", [b" ".join(str(u).encode() for u in uids_by_folder.get(selected["folder"], []))])
            return ("OK", [])

        conn.select.side_effect = select
        conn.uid.side_effect = uid
        return conn

    def test_changed_filter_rescans_from_zero(self, capsys):
        """Previously-skipped messages sit below the watermark."""
        conn = self._conn(["Work"], {"Work": [1, 2, 3]})
        provider = _imap_provider(conn, host="imap.fastmail.com")
        stale = capture.dump(
            capture.CaptureState(
                cursor=json.dumps({"Work": {"max_uid": 3, "uidvalidity": "100"}}),
                fingerprint="a-different-filter",
            )
        )

        with patch("time.sleep"):
            ids, _ = provider.get_new_message_ids(stale)

        assert ids == ["Work:1", "Work:2", "Work:3"]
        assert "filter changed" in capsys.readouterr().out

    def test_unchanged_filter_keeps_the_watermark(self):
        conn = self._conn(["INBOX"], {"INBOX": [1, 2, 3]})
        provider = _imap_provider(conn, host="imap.fastmail.com")
        current = capture.dump(
            capture.CaptureState(
                cursor=json.dumps({"INBOX": {"max_uid": 3, "uidvalidity": "100"}}),
                fingerprint=provider._filter_fingerprint(),
            )
        )

        with patch("time.sleep"):
            ids, _ = provider.get_new_message_ids(current)

        assert ids == []

    def test_legacy_watermark_state_does_not_force_a_rescan(self):
        """State written before the envelope existed carries no fingerprint."""
        conn = self._conn(["INBOX"], {"INBOX": [1, 2, 3]})
        provider = _imap_provider(conn, host="imap.fastmail.com")
        legacy = json.dumps({"INBOX": {"max_uid": 3, "uidvalidity": "100"}})

        with patch("time.sleep"):
            ids, _ = provider.get_new_message_ids(legacy)

        assert ids == []

    def test_reordering_exclude_folders_is_not_a_filter_change(self):
        conn = self._conn(["INBOX"], {"INBOX": []})
        one = _imap_provider(conn, host="imap.fastmail.com", exclude_folders=["a", "b"])
        two = _imap_provider(conn, host="imap.fastmail.com", exclude_folders=["b", "a"])

        assert one._filter_fingerprint() == two._filter_fingerprint()

    def test_mail_moved_out_of_an_excluded_folder_becomes_a_candidate(self):
        """IMAP needs no membership diff to be eligibility-driven.

        The move is a delivery, so the destination allocates a UID above its
        watermark and the transition arrives as an ordinary arrival.
        """
        conn = self._conn(["Work", "Trash"], {"Work": [1, 2], "Trash": [7]})
        provider = _imap_provider(conn, host="imap.fastmail.com")
        before = capture.dump(
            capture.CaptureState(
                cursor=json.dumps({"Work": {"max_uid": 1, "uidvalidity": "100"}}),
                fingerprint=provider._filter_fingerprint(),
            )
        )

        with patch("time.sleep"):
            ids, _ = provider.get_new_message_ids(before)

        assert ids == ["Work:2"]
