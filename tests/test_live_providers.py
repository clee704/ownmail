"""Provider lifecycle observations stay conservative across partial responses."""

import base64
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from ownmail import roles
from ownmail.live import LiveLookupError, LiveMessage, LiveSnapshot
from ownmail.providers.base import EmailProvider
from ownmail.providers.gmail import GmailProvider
from ownmail.providers.imap import ImapProvider
from ownmail.providers.live_imap import _message_id

RAW = b"From: sender@example.com\r\nSubject: live\r\n\r\nCurrent body"


def gmail(labels=None, *, include_labels=True):
    provider = GmailProvider(
        "person@example.com", MagicMock(), include_labels=include_labels, source_name="source", exclude_roles=[]
    )
    provider._service = MagicMock()
    message = {
        "id": "a",
        "threadId": "thread",
        "labelIds": ["INBOX"] if labels is None else labels,
        "raw": base64.urlsafe_b64encode(RAW).decode(),
    }
    provider._service.users().messages().get().execute.return_value = message
    provider._service.users().messages().list().execute.return_value = {"messages": [{"id": "a"}]}
    catalog = [
        {"id": label, "name": label, "type": "system"}
        for label in ["INBOX", "DRAFT", "SENT", "TRASH", "SPAM", "UNREAD", "SCHEDULED"]
    ]
    catalog.append({"id": "Label_1", "name": "Projects", "type": "user"})
    provider._service.users().labels().list().execute.return_value = {"labels": catalog}

    def new_batch(*, callback):
        requests = []
        batch = MagicMock()
        batch.add.side_effect = lambda request, request_id: requests.append((request_id, request))

        def execute():
            for request_id, request in requests:
                try:
                    response = request.execute()
                except Exception as error:
                    callback(request_id, None, error)
                else:
                    callback(request_id, response, None)

        batch.execute.side_effect = execute
        return batch

    provider._service.new_batch_http_request.side_effect = new_batch
    provider._service.reset_mock()
    return provider


def test_live_records_default_to_unknown_and_incomplete():
    message = LiveMessage("a")
    snapshot = LiveSnapshot("source", "person@example.com")
    assert message.state == "unknown"
    assert not snapshot.complete
    with pytest.raises(FrozenInstanceError):
        message.state = "eligible"
    assert EmailProvider.list_live_messages(None) is None
    with pytest.raises(LiveLookupError, match="does not support"):
        EmailProvider.read_live_message(None, "a")


@pytest.mark.parametrize(
    ("labels", "state"),
    [
        (["INBOX", "SENT"], "active"),
        (["DRAFT", "SENT"], "active"),
        (["TRASH", "INBOX", "DRAFT"], "discarded"),
        (["SPAM", "DRAFT"], "discarded"),
        (["SENT"], "eligible"),
        (["SENT", "Label_1"], "eligible"),
        (["SENT", "SCHEDULED"], "unknown"),
        (["Label_1"], "eligible"),
        ([], "eligible"),
    ],
)
@pytest.mark.parametrize("include_labels", [True, False])
def test_gmail_fresh_roles_override_capture_preferences(labels, state, include_labels):
    provider = gmail(labels, include_labels=include_labels)
    result = provider.read_live_message("a")
    assert result.state == state
    assert result.identity_token == "gmail:a"
    assert result.thread_id == "thread"
    assert result.raw == (None if state == "discarded" else RAW)
    assert result.labels == (() if not include_labels else tuple("Projects" if x == "Label_1" else x for x in labels))
    if "INBOX" in labels:
        assert roles.INBOX in result.roles
    provider._service.users().messages().get.assert_called_once_with(userId="me", id="a", format="raw")


def test_gmail_labels_and_state_are_refreshed_together():
    provider = gmail(["INBOX", "UNREAD", "Label_1"])
    result = provider.list_live_messages()
    assert result.complete
    assert (result.source_name, result.account) == ("source", "person@example.com")
    assert result.messages[0].labels == ("INBOX", "Projects")
    provider._service.users().messages().get().execute.return_value["labelIds"] = ["SENT", "Label_1"]
    provider._service.users().labels().list().execute.return_value["labels"][-1]["name"] = "Renamed"
    fresh = provider.read_live_message("a")
    assert fresh.state == "eligible"
    assert fresh.labels == ("SENT", "Renamed")
    provider._service.users().messages().list.assert_called_once_with(
        userId="me", maxResults=500, pageToken=None, includeSpamTrash=True
    )


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"labels": "bad"},
        {"labels": [None]},
        {"labels": [{"id": "x", "name": "x", "type": "unknown"}]},
        {"labels": [{"id": "x", "name": "x", "type": "user"}] * 2},
    ],
)
def test_gmail_missing_or_malformed_required_catalog_is_never_empty_success(response):
    provider = gmail()
    provider._service.users().labels().list().execute.return_value = response
    assert not provider.list_live_messages().complete
    with pytest.raises(LiveLookupError):
        provider.read_live_message("a")


@pytest.mark.parametrize(
    "change",
    [
        {"id": "other"},
        {"threadId": None},
        {"labelIds": "INBOX"},
        {"labelIds": [None]},
        {"labelIds": [""]},
        {"labelIds": ["Missing"]},
        {"raw": None},
        {"raw": "!bad!"},
    ],
)
def test_gmail_malformed_content_or_metadata_cannot_authorize_capture(change):
    provider = gmail()
    provider._service.users().messages().get().execute.return_value.update(change)
    with pytest.raises(LiveLookupError):
        provider.read_live_message("a")


@pytest.mark.parametrize("identity", [None, ""])
def test_gmail_missing_lookup_identity_is_not_absence(identity):
    with pytest.raises(LiveLookupError):
        gmail().read_live_message(identity)


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_gmail_only_not_found_confirms_absence(status):
    provider = gmail()
    provider._service.users().messages().get().execute.side_effect = HttpError(
        SimpleNamespace(status=status, reason="unavailable"), b"{}"
    )
    if status == 404:
        assert provider.read_live_message("a") is None
    else:
        with pytest.raises(LiveLookupError):
            provider.read_live_message("a")
    assert not provider.list_live_messages().complete


def test_gmail_other_failures_hide_exception_details_and_interrupts_propagate():
    provider = gmail()
    execute = provider._service.users().messages().get().execute
    execute.side_effect = RuntimeError("private remote response")
    with pytest.raises(LiveLookupError, match="^Gmail live lookup failed$"):
        provider.read_live_message("a")
    execute.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        provider.list_live_messages()


@pytest.mark.parametrize(
    "pages",
    [
        [None],
        [{"messages": {}}],
        [{"messages": [None]}],
        [{"messages": [{"id": ""}]}],
        [{"messages": [{"id": "a"}, {"id": "a"}]}],
        [{"nextPageToken": ""}],
        [{"nextPageToken": "again"}, {"nextPageToken": "again"}],
    ],
)
def test_gmail_partial_or_malformed_listing_is_not_current(pages):
    provider = gmail()
    provider._service.users().messages().list().execute.side_effect = pages
    assert not provider.list_live_messages().complete


def test_gmail_valid_empty_and_paginated_listings():
    provider = gmail()
    provider._service.users().messages().list().execute.side_effect = [
        {"messages": [{"id": "a"}], "nextPageToken": "next"},
        {},
    ]
    result = provider.list_live_messages()
    assert result.complete
    assert [m.message_id for m in result.messages] == ["a"]
    provider._service.users().messages().list().execute.side_effect = None
    provider._service.users().messages().list().execute.return_value = {}
    assert provider.list_live_messages() == LiveSnapshot("source", "person@example.com", [], True)


class Mailbox:
    """An IMAP transcript with explicit read-only commands and current state."""

    def __init__(self, folder="INBOX", flags=b"", *, gmail_labels=None):
        self.folder = folder
        self.flags = flags
        self.gmail_labels = gmail_labels
        self.listing = ("OK", [b'() "/" "' + folder.encode() + b'"'])
        self.selection = ("OK", [b"1"])
        self.validity = ("UIDVALIDITY", [b"10"])
        self.search = ("OK", [b"1"])
        self.fetch = None
        self.commands = []

    def list(self):
        self.commands.append(("list",))
        return self.listing

    def select(self, folder, readonly):
        self.commands.append(("select", folder, readonly))
        assert readonly
        return self.selection

    def response(self, name):
        assert name == "UIDVALIDITY"
        return self.validity

    def uid(self, command, *args):
        self.commands.append((command, *args))
        if command == "search":
            return self.search
        assert command == "fetch"
        if self.fetch is not None:
            return self.fetch
        metadata = b"1 (UID 1 FLAGS (" + self.flags + b")"
        if self.gmail_labels is not None:
            metadata += b" X-GM-MSGID 255 X-GM-THRID 256 X-GM-LABELS (" + self.gmail_labels + b")"
        if "BODY.PEEK[]" in args[1]:
            metadata += b" BODY[] {" + str(len(RAW)).encode() + b"}"
            return "OK", [(metadata, RAW), b")"]
        return "OK", [metadata + b")"]


def imap(folder="INBOX", flags=b"", *, gmail_labels=None, **kwargs):
    provider = ImapProvider(
        "person@example.com",
        MagicMock(),
        source_name="source",
        exclude_roles=[],
        host="imap.gmail.com" if gmail_labels is not None else "imap.example.com",
        **kwargs,
    )
    provider._conn = Mailbox(folder, flags, gmail_labels=gmail_labels)
    return provider


@pytest.mark.parametrize(
    ("folder", "flags", "state"),
    [
        ("INBOX", b"", "active"),
        ("Drafts", b"", "active"),
        ("Sent", b"\\Draft", "active"),
        ("Trash", b"\\Draft", "discarded"),
        ("Junk", b"", "discarded"),
        ("INBOX", b"\\Deleted", "discarded"),
        ("Sent", b"", "eligible"),
        ("Archive", b"", "eligible"),
        ("Outbox", b"", "eligible"),
        ("Projects", b"", "eligible"),
        ("Projects", b"$Forwarded $Submitted $MDNSent $Important", "eligible"),
        ("Sent", b"$SubmitPending", "active"),
        ("Projects", b"$SubmitPending $Submitted", "active"),
        ("Trash", b"$SubmitPending", "discarded"),
    ],
)
def test_imap_current_folder_roles_and_flags_establish_ownership(folder, flags, state):
    provider = imap(folder, flags)
    snapshot = provider.list_live_messages()
    assert snapshot.complete
    assert len(snapshot.messages) == 1
    message = snapshot.messages[0]
    assert message.state == state
    assert message.identity_token == _message_id(folder, "10", 1)
    assert message.labels == (folder,)
    fresh = provider.read_live_message(message.message_id)
    assert fresh.raw == RAW
    assert fresh.state == state
    assert ("fetch", "1", "(UID FLAGS BODY.PEEK[])") in provider._conn.commands


def test_imap_folder_exclusion_keeps_state_but_disables_downloads():
    provider = imap(exclude_folders=["INBOX"])
    message = provider.list_live_messages().messages[0]
    assert message.state == "active"
    assert not message.download_allowed
    assert not provider.read_live_message(message.message_id).download_allowed


@pytest.mark.parametrize(
    ("labels", "flags", "state"),
    [
        (b"\\Inbox \\Sent", b"", "active"),
        (b"\\Sent", b"\\Draft", "active"),
        (b"\\Drafts \\Trash", b"", "discarded"),
        (b"\\Spam \\Inbox", b"", "discarded"),
        (b'\\Sent \\Important \\Starred "Project (A)"', b"", "eligible"),
        (b"\\Sent \\Scheduled", b"", "unknown"),
        (b"", b"", "eligible"),
        (b"\\Sent", b"$SubmitPending $Submitted", "active"),
    ],
)
def test_gmail_imap_uses_current_labels_and_immutable_identity(labels, flags, state):
    provider = imap("[Gmail]/All Mail", flags, gmail_labels=labels)
    snapshot = provider.list_live_messages()
    assert snapshot.complete
    message = snapshot.messages[0]
    assert message.state == state
    assert message.identity_token == "gmail:ff"
    assert message.thread_id == "100"
    assert provider.read_live_message(message.message_id).state == state


def test_gmail_imap_deduplicates_stable_identity_across_folders():
    provider = imap("[Gmail]/All Mail", gmail_labels=b"\\Sent")
    provider._conn.listing = ("OK", [b'(\\Sent) "/" "Sent"', b'(\\All) "/" "All Mail"'])
    result = provider.list_live_messages()
    assert result.complete
    assert len(result.messages) == 1
    assert result.messages[0].message_id == _message_id("All Mail", "10", 1)


def test_gmail_imap_conflicting_fresh_labels_make_enumeration_partial():
    provider = imap("Sent", gmail_labels=b"\\Sent")
    provider._conn.listing = ("OK", [b'(\\Sent) "/" "Sent"', b'() "/" "INBOX"'])
    select = provider._conn.select

    def change_labels(folder, readonly):
        provider._conn.gmail_labels = b"\\Inbox" if folder == '"INBOX"' else b"\\Sent"
        return select(folder, readonly)

    provider._conn.select = change_labels
    assert not provider.list_live_messages().complete


@pytest.mark.parametrize(
    "listing",
    [
        ("NO", []),
        ("OK", None),
        ("OK", [None]),
        ("OK", [b"broken"]),
        ("OK", [b'() "/" ""']),
        ("OK", [b'() "/" "INBOX"'] * 2),
    ],
)
def test_imap_invalid_folder_listing_cannot_confirm_absence(listing):
    provider = imap()
    provider._conn.listing = listing
    assert not provider.list_live_messages().complete
    with pytest.raises(LiveLookupError):
        provider.read_live_message(_message_id("INBOX", "10", 1))


def test_imap_nonselectable_and_nil_delimiter_folders():
    provider = imap()
    provider._conn.listing = ("OK", [b'(\\Noselect) "/" "Parent"', b"(\\Sent) NIL Sent"])
    result = provider.list_live_messages()
    assert result.complete
    assert len(result.messages) == 1
    assert result.messages[0].state == "eligible"
    assert ("select", '"Parent"', True) not in provider._conn.commands


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("selection", ("NO", [])),
        ("validity", ("NO", [b"10"])),
        ("validity", ("UIDVALIDITY", [None])),
        ("validity", ("UIDVALIDITY", [b"0"])),
        ("search", ("NO", [])),
        ("search", ("OK", [None])),
        ("search", ("OK", [b"bad"])),
        ("search", ("OK", [b"1 1"])),
        ("fetch", ("NO", [])),
        ("fetch", ("OK", [None])),
        ("fetch", ("OK", [42])),
        ("fetch", ("OK", [b"1 (UID 2 FLAGS ())"])),
        ("fetch", ("OK", [b"1 (UID 1)"])),
    ],
)
def test_imap_failed_protocol_steps_produce_partial_snapshot(attribute, value):
    provider = imap()
    setattr(provider._conn, attribute, value)
    assert not provider.list_live_messages().complete
    with pytest.raises(LiveLookupError):
        provider.read_live_message(_message_id("INBOX", "10", 1))


@pytest.mark.parametrize(
    "value",
    [
        ("OK", [(b"1 (UID 1 FLAGS () BODY[] {99}", RAW), b")"]),
        ("OK", [(b"1 (UID 1 FLAGS ()", RAW), b")"]),
        ("OK", [(b"1 (UID 1 FLAGS () BODY[] {0}", b""), b")"]),
    ],
)
def test_imap_incomplete_literal_never_becomes_saved_content(value):
    provider = imap()
    provider._conn.fetch = value
    with pytest.raises(LiveLookupError):
        provider.read_live_message(_message_id("INBOX", "10", 1))


@pytest.mark.parametrize(
    "metadata",
    [
        b"1 (UID 1 FLAGS ())",
        b'1 (UID 1 FLAGS () X-GM-MSGID 255 X-GM-THRID 256 X-GM-LABELS (broken"))',
    ],
)
def test_gmail_imap_missing_extensions_and_malformed_labels_stay_unknown(metadata):
    provider = imap(gmail_labels=b"\\Inbox")
    provider._conn.fetch = ("OK", [metadata])
    assert not provider.list_live_messages().complete


@pytest.mark.parametrize(
    "identity",
    [None, "INBOX:1", "imap:!!!", _message_id("INBOX", "10", -1), _message_id("INBOX", 10, 1), _message_id(1, "10", 1)],
)
def test_imap_invalid_identity_is_not_absence(identity):
    with pytest.raises(LiveLookupError):
        imap().read_live_message(identity)


def test_imap_uid_reuse_retains_the_previous_copy_until_identity_is_resolved():
    provider = imap()
    old = provider.list_live_messages().messages[0]
    provider._conn.validity = ("UIDVALIDITY", [b"11"])
    new = provider.list_live_messages().messages[0]
    assert old.identity_token != new.identity_token
    with pytest.raises(LiveLookupError, match="UIDVALIDITY changed"):
        provider.read_live_message(old.message_id)


def test_imap_confirmed_empty_search_or_removed_folder_confirms_absence():
    provider = imap()
    provider._conn.search = ("OK", [b""])
    assert provider.list_live_messages().complete
    assert provider.read_live_message(_message_id("INBOX", "10", 1)) is None
    provider._conn.listing = ("OK", [])
    assert provider.read_live_message(_message_id("INBOX", "10", 1)) is None


def test_imap_unexpected_search_identity_never_fetches_another_message():
    provider = imap()
    provider._conn.search = ("OK", [b"2"])
    with pytest.raises(LiveLookupError, match="another identity"):
        provider.read_live_message(_message_id("INBOX", "10", 1))
    assert not any(command[0] == "fetch" for command in provider._conn.commands)


@pytest.mark.parametrize("flags", [b"$Scheduled", b"\\Unknown"])
def test_unrecognized_imap_flags_cannot_establish_finished_state(flags):
    provider = imap("Sent", flags)
    assert provider.list_live_messages().messages[0].state == "unknown"
    provider = imap("All Mail", flags, gmail_labels=b"\\Sent")
    assert provider.list_live_messages().messages[0].state == "unknown"


def test_imap_conflicting_folder_roles_preserve_active_precedence():
    provider = imap("Mixed")
    provider._conn.listing = ("OK", [b'(\\Sent \\Drafts) "/" "Mixed"'])
    assert provider.list_live_messages().messages[0].state == "active"
    provider._conn.listing = ("OK", [b'(\\Sent \\Drafts \\Trash) "/" "Mixed"'])
    assert provider.list_live_messages().messages[0].state == "discarded"


def test_gmail_imap_selected_folder_does_not_override_current_labels():
    provider = imap("Sent", gmail_labels=b"Projects")
    message = provider.list_live_messages().messages[0]
    assert message.state == "eligible"
    assert roles.SENT not in message.roles


@pytest.mark.parametrize("gmail_labels", [None, b"\\Sent"])
def test_imap_advertised_scheduled_mail_stays_active_without_becoming_draft(gmail_labels):
    provider = imap("Later", gmail_labels=gmail_labels)
    provider._conn.listing = ("OK", [b'(\\Scheduled \\HasNoChildren) "/" "Later"'])
    message = provider.list_live_messages().messages[0]
    assert message.state == "active"
    assert roles.DRAFTS not in message.roles
    fresh = provider.read_live_message(message.message_id)
    assert fresh.state == "active"
    assert roles.DRAFTS not in fresh.roles


@pytest.mark.parametrize("attribute", [b"\\Unknown", b"\\Outbox", b"\\Submission"])
def test_imap_unknown_mailbox_attributes_hold_messages(attribute):
    provider = imap("Projects")
    provider._conn.listing = ("OK", [b"(" + attribute + b') "/" "Projects"'])
    message = provider.list_live_messages().messages[0]
    assert message.state == "unknown"
    assert provider.read_live_message(message.message_id).state == "unknown"


def test_imap_scheduled_attribute_changes_are_read_fresh():
    provider = imap("Later")
    provider._conn.listing = ("OK", [b'(\\Scheduled) "/" "Later"'])
    message = provider.list_live_messages().messages[0]
    provider._conn.listing = ("OK", [b'() "/" "Later"'])
    assert provider.read_live_message(message.message_id).state == "eligible"
    provider._conn.flags = b"$sUBMITpENDING $Submitted"
    fresh = provider.read_live_message(message.message_id)
    assert fresh.state == "active"
    assert roles.DRAFTS not in fresh.roles


def gmail_scheduled_mailbox():
    provider = imap("All Mail", gmail_labels=b"Projects")
    mailbox = provider._conn
    mailbox.listing = ("OK", [b'(\\All) "/" "All Mail"', b'(\\Scheduled) "/" "Later"'])
    mailbox.scheduled = True
    mailbox.membership_error = False
    select, uid = mailbox.select, mailbox.uid

    def select_folder(folder, readonly):
        mailbox.selected = folder
        return select(folder, readonly)

    def command(name, *args):
        if name == "search" and mailbox.selected == '"Later"':
            mailbox.commands.append((name, *args))
            if mailbox.membership_error:
                return "NO", []
            return "OK", [b"1" if mailbox.scheduled else b""]
        return uid(name, *args)

    mailbox.select, mailbox.uid = select_folder, command
    return provider


def test_gmail_imap_all_mail_duplicate_scheduled_membership_stays_active():
    provider = gmail_scheduled_mailbox()
    snapshot = provider.list_live_messages()
    assert snapshot.complete
    assert len(snapshot.messages) == 1
    assert snapshot.messages[0].state == "active"
    assert roles.DRAFTS not in snapshot.messages[0].roles
    fresh = provider.read_live_message(_message_id("All Mail", "10", 1))
    assert fresh.state == "active"
    assert fresh.raw == RAW
    assert ("search", None, "X-GM-MSGID 255") in provider._conn.commands


def test_gmail_imap_scheduled_membership_is_checked_again_before_capture():
    provider = gmail_scheduled_mailbox()
    provider._conn.scheduled = False
    message = provider.list_live_messages().messages[0]
    assert message.state == "eligible"
    provider._conn.scheduled = True
    assert provider.read_live_message(message.message_id).state == "active"
    provider._conn.membership_error = True
    with pytest.raises(LiveLookupError, match="search is incomplete"):
        provider.read_live_message(message.message_id)
    snapshot = provider.list_live_messages()
    assert not snapshot.complete
    assert snapshot.messages[0].state == "unknown"


def test_gmail_imap_unrecognized_folder_membership_is_held():
    provider = gmail_scheduled_mailbox()
    provider._conn.listing = ("OK", [b'(\\All) "/" "All Mail"', b'(\\Unknown) "/" "Later"'])
    snapshot = provider.list_live_messages()
    assert snapshot.messages[0].state == "unknown"
    message_id = _message_id("All Mail", "10", 1)
    assert provider.read_live_message(message_id).state == "unknown"
    provider._conn.scheduled = False
    assert provider.read_live_message(message_id).state == "eligible"


def test_gmail_imap_candidate_uidvalidity_is_checked_after_folder_membership():
    provider = gmail_scheduled_mailbox()
    provider._conn.scheduled = False
    uid = provider._conn.uid

    def change_epoch(command, *args):
        result = uid(command, *args)
        if command == "search" and args[-1] == "X-GM-MSGID 255":
            provider._conn.validity = ("UIDVALIDITY", [b"11"])
        return result

    provider._conn.uid = change_epoch
    with pytest.raises(LiveLookupError, match="UIDVALIDITY changed during state checks"):
        provider.read_live_message(_message_id("All Mail", "10", 1))


def test_gmail_imap_label_text_cannot_spoof_current_flags_or_identity():
    provider = imap("All Mail", gmail_labels=b"")
    provider._conn.fetch = (
        "OK",
        [b'1 (X-GM-LABELS ("FLAGS ()" UID 99 \\Sent) FLAGS (\\Draft) UID 1 X-GM-MSGID 255 X-GM-THRID 256)'],
    )
    result = provider.list_live_messages()
    assert result.complete
    assert result.messages[0].state == "active"
    assert result.messages[0].identity_token == "gmail:ff"
