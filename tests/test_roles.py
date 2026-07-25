"""Tests for canonical system-label role resolution."""

import pytest

from ownmail import roles


class TestGmailLabels:
    """Gmail API system label IDs are stable and unlocalized."""

    @pytest.mark.parametrize(
        "label_id,expected",
        [
            ("INBOX", roles.INBOX),
            ("SENT", roles.SENT),
            ("DRAFT", roles.DRAFTS),  # Gmail spells it singular
            ("TRASH", roles.TRASH),
            ("SPAM", roles.SPAM),
        ],
    )
    def test_system_labels_resolve(self, label_id, expected):
        assert roles.role_for_gmail_label(label_id) == expected

    @pytest.mark.parametrize("label_id", ["CATEGORY_PROMOTIONS", "STARRED", "IMPORTANT", "Receipts", ""])
    def test_other_labels_have_no_role(self, label_id):
        assert roles.role_for_gmail_label(label_id) is None

    def test_lookup_is_case_sensitive(self):
        """Gmail IDs are uppercase; a user label 'Trash' must not match."""
        assert roles.role_for_gmail_label("Trash") is None


class TestImapSpecialUse:
    """RFC 6154 attributes are the authoritative signal."""

    @pytest.mark.parametrize(
        "flag,expected",
        [
            ("\\All", roles.ALL),
            ("\\Archive", roles.ARCHIVE),
            ("\\Drafts", roles.DRAFTS),
            ("\\Junk", roles.SPAM),
            ("\\Sent", roles.SENT),
            ("\\Trash", roles.TRASH),
        ],
    )
    def test_attributes_resolve(self, flag, expected):
        assert roles.role_for_imap_folder("Whatever", f"\\HasNoChildren {flag}") == expected

    def test_case_insensitive(self):
        assert roles.role_for_imap_folder("x", "\\TRASH") == roles.TRASH

    def test_beats_a_conflicting_name(self):
        """The server's own answer wins over the fallback table."""
        assert roles.role_for_imap_folder("Archive", "\\Trash") == roles.TRASH

    def test_resolves_names_no_table_could_cover(self):
        """The point of SPECIAL-USE: works for names we've never seen."""
        assert roles.role_for_imap_folder("Prullenbak", "\\Trash") == roles.TRASH
        assert roles.role_for_imap_folder("[Gmail]/전우편지", "\\All") == roles.ALL

    def test_unrelated_flags_ignored(self):
        assert roles.role_for_imap_folder("Receipts", "\\HasChildren \\Marked") is None


class TestImapInbox:
    def test_inbox_is_case_insensitive(self):
        """RFC 3501 mandates INBOX and mandates it be case-insensitive."""
        for name in ("INBOX", "inbox", "Inbox", "InBoX"):
            assert roles.role_for_imap_folder(name) == roles.INBOX

    def test_subfolder_of_inbox_is_not_inbox(self):
        assert roles.role_for_imap_folder("INBOX.Receipts", delimiter=".") is None


class TestImapNameFallback:
    """For servers too old to advertise SPECIAL-USE."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Trash", roles.TRASH),
            ("Deleted Items", roles.TRASH),
            ("Papierkorb", roles.TRASH),
            ("Junk", roles.SPAM),
            ("Junk E-Mail", roles.SPAM),
            ("Spam", roles.SPAM),
            ("Drafts", roles.DRAFTS),
            ("Sent Items", roles.SENT),
            ("Archive", roles.ARCHIVE),
        ],
    )
    def test_common_names(self, name, expected):
        assert roles.role_for_imap_folder(name) == expected

    def test_case_insensitive(self):
        assert roles.role_for_imap_folder("DELETED ITEMS") == roles.TRASH

    @pytest.mark.parametrize(
        "name,delimiter",
        [
            ("[Gmail]/Trash", "/"),
            ("INBOX.Trash", "."),
            ("Mail/Archive/Trash", "/"),
        ],
    )
    def test_matches_leaf_not_whole_path(self, name, delimiter):
        assert roles.role_for_imap_folder(name, delimiter=delimiter) == roles.TRASH

    def test_wrong_delimiter_does_not_split(self):
        assert roles.role_for_imap_folder("INBOX.Trash", delimiter="/") is None

    def test_empty_delimiter_uses_whole_name(self):
        """Some servers report a flat namespace with no delimiter."""
        assert roles.role_for_imap_folder("Trash", delimiter="") == roles.TRASH

    def test_user_folder_has_no_role(self):
        assert roles.role_for_imap_folder("Receipts") is None


class TestStoredLabels:
    """Resolving labels already written to the archive."""

    def test_resolves_gmail_and_imap_vocabularies(self):
        assert roles.role_for_label("TRASH") == roles.TRASH
        assert roles.role_for_label("[Gmail]/Spam") == roles.SPAM

    def test_tries_both_delimiters(self):
        """The archive doesn't record which delimiter the server used."""
        assert roles.role_for_label("INBOX.Trash") == roles.TRASH
        assert roles.role_for_label("[Gmail]/Trash") == roles.TRASH

    def test_plain_name(self):
        assert roles.role_for_label("Deleted Items") == roles.TRASH

    def test_user_label_has_no_role(self):
        assert roles.role_for_label("Receipts") is None


class TestRoleSet:
    def test_default_exclusions_are_real_roles(self):
        assert roles.DEFAULT_EXCLUDE_ROLES <= roles.ROLES

    def test_every_resolvable_role_is_in_the_set(self):
        resolved = {
            roles.role_for_imap_folder("INBOX"),
            roles.role_for_imap_folder("x", "\\All"),
            roles.role_for_imap_folder("x", "\\Archive"),
            roles.role_for_imap_folder("x", "\\Drafts"),
            roles.role_for_imap_folder("x", "\\Junk"),
            roles.role_for_imap_folder("x", "\\Sent"),
            roles.role_for_imap_folder("x", "\\Trash"),
        }
        assert resolved == set(roles.ROLES)
