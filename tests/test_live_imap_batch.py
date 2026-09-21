"""Bounded IMAP requests preserve fresh state and scoped message identity."""

import re
from unittest.mock import MagicMock

import pytest

from ownmail.live import LiveLookupError
from ownmail.providers.imap import ImapProvider
from ownmail.providers.live_imap import _message_id


class BatchMailbox:
    def __init__(self, folders, *, gmail=False):
        self.folders = folders
        self.gmail = gmail
        self.selected = None
        self.commands = []
        self.validity = dict.fromkeys(folders, "10")
        self.attributes = {}
        self.flags = {}
        self.labels = {}
        self.omitted = set()
        self.fetch_error = None
        self.transform = lambda rows: rows

    def list(self):
        self.commands.append(("list",))
        return "OK", [f'({self.attributes.get(folder, "")}) "/" "{folder}"'.encode() for folder in self.folders]

    def select(self, folder, readonly):
        assert readonly
        self.selected = folder[1:-1]
        self.commands.append(("select", self.selected))
        return "OK", [str(len(self.folders[self.selected])).encode()]

    def response(self, name):
        assert name == "UIDVALIDITY"
        return name, [self.validity[self.selected].encode()]

    def uid(self, command, *args):
        self.commands.append((command, self.selected, *args))
        if command == "search":
            criterion = args[1]
            if criterion.startswith("UID ") and criterion.endswith(":*"):
                boundary = min(int(criterion[4:-2]), max(self.folders[self.selected], default=0))
                requested = {uid for uid in self.folders[self.selected] if uid >= boundary}
            else:
                requested = set(map(int, criterion[4:].split(","))) if criterion.startswith("UID ") else None
            if criterion == 'X-GM-RAW "in:inbox"':
                requested = {uid for uid in self.folders[self.selected] if "\\Inbox" in self.labels.get(uid, [])}
            elif criterion == "DRAFT":
                requested = {uid for uid in self.folders[self.selected] if "\\Draft" in self.flags.get(uid, "")}
            if "X-GM-MSGID " in criterion:
                requested = set(map(int, re.findall(r"X-GM-MSGID ([0-9]+)", criterion)))
            found = [uid for uid in self.folders[self.selected] if requested is None or uid in requested]
            return "OK", [" ".join(map(str, found)).encode()]
        assert command == "fetch"
        if self.fetch_error:
            raise self.fetch_error
        rows = []
        for seq, uid in enumerate(map(int, args[0].split(",")), 1):
            if uid in self.omitted or uid not in self.folders[self.selected]:
                continue
            metadata = f"{seq} (UID {uid} FLAGS ({self.flags.get(uid, '')})".encode()
            if self.gmail:
                labels = " ".join(self.labels.get(uid, ["Projects"]))
                metadata += f" X-GM-MSGID {uid} X-GM-THRID {uid} X-GM-LABELS ({labels})".encode()
            if "BODY.PEEK[]" in args[1]:
                raw = f"Subject: {uid}\r\n\r\nBody {uid}".encode()
                rows.extend([(metadata + f" BODY[] {{{len(raw)}}}".encode(), raw), b")"])
            else:
                rows.append(metadata + b")")
        return "OK", self.transform(rows)


def provider_for(folders, *, gmail=False, **kwargs):
    provider = ImapProvider(
        "person@example.com",
        MagicMock(),
        source_name="source",
        host="imap.gmail.com" if gmail else "imap.example.com",
        **kwargs,
    )
    provider._conn = BatchMailbox(folders, gmail=gmail)
    return provider


def test_thousand_message_scan_uses_two_metadata_fetches():
    provider = provider_for({"Projects": list(range(1, 1001))})
    counts = []
    snapshot = provider.list_live_messages(on_progress=counts.append)
    assert snapshot.complete
    assert len(snapshot.messages) == 1000
    assert counts[0] == 0 and counts[-1] == 1000
    assert [command[0] for command in provider._conn.commands] == ["list", "select", "search", "fetch", "fetch"]
    assert all(message.raw is None and message.content_revision == message.message_id for message in snapshot.messages)


def test_body_batches_group_folders_and_refresh_flags():
    provider = provider_for({"Projects": list(range(1, 41)), "INBOX": list(range(41, 61))})
    mailbox = provider._conn
    mailbox.flags[1] = "$SubmitPending"
    ids = [_message_id("Projects" if uid <= 40 else "INBOX", "10", uid) for uid in range(1, 61)]
    messages = provider.read_live_messages(ids)
    assert list(messages) == ids
    assert all(message.raw.endswith(f"Body {uid}".encode()) for uid, message in enumerate(messages.values(), 1))
    assert messages[ids[0]].state == "active"
    assert messages[ids[1]].state == "eligible"
    assert messages[ids[-1]].state == "active"
    assert all(message.content_revision == message.message_id for message in messages.values())
    commands = [command[0] for command in mailbox.commands]
    assert commands.count("list") == 1
    assert commands.count("select") == 2
    assert commands.count("search") == commands.count("fetch") == 3
    assert provider.live_batch_size == 25


def test_missing_fetch_result_is_error_but_scoped_search_can_confirm_absence():
    provider = provider_for({"Projects": [1, 2]})
    provider._conn.omitted = {2}
    ids = [_message_id("Projects", "10", uid) for uid in [1, 2, 3]]
    messages = provider.read_live_messages(ids)
    assert messages[ids[0]].raw.endswith(b"Body 1")
    assert isinstance(messages[ids[1]], LiveLookupError)
    assert messages[ids[2]] is None
    snapshot = provider.list_live_messages()
    assert not snapshot.complete
    assert [message.message_id for message in snapshot.messages] == ids[:1]


def test_duplicate_fetch_identity_does_not_discard_other_results():
    provider = provider_for({"Projects": [1, 2]})
    provider._conn.transform = lambda rows: rows + rows[:2]
    ids = [_message_id("Projects", "10", uid) for uid in [1, 2]]
    messages = provider.read_live_messages(ids)
    assert isinstance(messages[ids[0]], LiveLookupError)
    assert messages[ids[1]].raw.endswith(b"Body 2")


@pytest.mark.parametrize(
    "rewrite",
    [
        lambda rows: [(rows[0][0].replace(b"UID 1 ", b"UID 3 "), rows[0][1]), *rows[1:]],
        lambda rows: [(rows[0][0].replace(b"UID 1 ", b"UID 1 UID 2 "), rows[0][1]), *rows[1:]],
        lambda rows: [rows[0], b"FLAGS () )", *rows[2:]],
        lambda rows: [(b"garbage " + rows[0][0], rows[0][1]), *rows[1:]],
    ],
)
def test_malformed_or_foreign_fetch_cannot_supply_another_messages_body(rewrite):
    provider = provider_for({"Projects": [1, 2]})
    provider._conn.transform = rewrite
    ids = [_message_id("Projects", "10", uid) for uid in [1, 2]]
    assert all(isinstance(value, LiveLookupError) for value in provider.read_live_messages(ids).values())


def test_uidvalidity_failure_is_scoped_to_its_folder():
    provider = provider_for({"Projects": [1], "INBOX": [2]})
    provider._conn.validity["Projects"] = "11"
    old = _message_id("Projects", "10", 1)
    current = _message_id("INBOX", "10", 2)
    messages = provider.read_live_messages([old, current])
    assert isinstance(messages[old], LiveLookupError)
    assert "UIDVALIDITY changed" in str(messages[old])
    assert messages[current].raw.endswith(b"Body 2")


def test_gmail_exceptional_membership_is_fetched_once_for_a_body_batch():
    provider = provider_for({"All Mail": list(range(1, 26)), "Later": [1, 2]}, gmail=True)
    mailbox = provider._conn
    mailbox.attributes = {"All Mail": "\\All", "Later": "\\Scheduled"}
    ids = [_message_id("All Mail", "10", uid) for uid in range(1, 26)]
    messages = provider.read_live_messages(ids)
    assert [message.state for message in messages.values()] == ["active"] * 2 + ["eligible"] * 23
    commands = [command[0] for command in mailbox.commands]
    assert commands.count("list") == 1
    assert commands.count("select") == 3
    assert commands.count("search") == commands.count("fetch") == 2
    searches = [command[-1] for command in mailbox.commands if command[0] == "search"]
    assert searches[1].count("X-GM-MSGID ") == 25
    mailbox.commands.clear()
    snapshot = provider.list_live_messages()
    assert snapshot.complete
    assert len(snapshot.messages) == 25
    assert sum(message.state == "active" for message in snapshot.messages) == 2
    assert [command[0] for command in mailbox.commands].count("fetch") == 2


def test_metadata_failed_batch_retains_successful_batch_and_counts_every_uid():
    provider = provider_for({"Projects": list(range(1, 502))})
    original = provider._conn.uid

    def fail_first(command, *args):
        if command == "fetch" and args[0].startswith("1,"):
            raise OSError("unavailable")
        return original(command, *args)

    provider._conn.uid = fail_first
    counts = []
    snapshot = provider.list_live_messages(on_progress=counts.append)
    assert not snapshot.complete
    assert [message.message_id for message in snapshot.messages] == [_message_id("Projects", "10", 501)]
    assert counts[-1] == 501


@pytest.mark.parametrize("method", ["list_live_messages", "read_live_messages"])
def test_batch_interrupts_propagate(method):
    provider = provider_for({"Projects": [1]})
    provider._conn.fetch_error = KeyboardInterrupt()
    args = [] if method == "list_live_messages" else [[_message_id("Projects", "10", 1)]]
    with pytest.raises(KeyboardInterrupt):
        getattr(provider, method)(*args)


def test_quoted_draft_flag_cannot_be_masked_into_finished_mail():
    provider = provider_for({"Projects": [1]})
    provider._conn.flags[1] = '"\\Draft"'
    snapshot = provider.list_live_messages()
    assert not snapshot.complete
    assert snapshot.messages == []
    result = provider.read_live_messages([_message_id("Projects", "10", 1)])
    assert all(isinstance(value, LiveLookupError) for value in result.values())


def test_large_exceptional_folder_fetches_only_requested_memberships():
    provider = provider_for({"All Mail": list(range(1, 26)), "Later": list(range(1, 1001))}, gmail=True)
    provider._conn.attributes = {"All Mail": "\\All", "Later": "\\Scheduled"}
    ids = [_message_id("All Mail", "10", uid) for uid in range(1, 26)]
    messages = provider.read_live_messages(ids)
    assert all(message.state == "active" for message in messages.values())
    membership_fetches = [command for command in provider._conn.commands if command[:2] == ("fetch", "Later")]
    assert len(membership_fetches) == 1
    assert len(membership_fetches[0][2].split(",")) == 25


def test_real_archive_repeat_imap_refresh_reuses_immutable_cached_bodies(tmp_path):
    from ownmail.archive import EmailArchive

    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"INBOX": list(range(1, 52))})
    first = archive.backup(provider, active_downloads=True)
    assert first["active_refreshed"] == 51
    assert first["error_count"] == 0 and first["active_complete"]
    body_fetches = [
        command for command in provider._conn.commands if command[0] == "fetch" and "BODY.PEEK[]" in command[-1]
    ]
    assert len(body_fetches) == 3
    cache = archive.active_cache()
    entries = cache.list_entries()
    assert len(entries) == 51
    assert all(entry["content_revision"] == entry["provider_id"] for entry in entries)
    provider._conn.commands.clear()
    second = archive.backup(provider, active_downloads=True)
    assert second["active_refreshed"] == 51
    assert second["error_count"] == 0 and second["active_complete"]
    assert [command[0] for command in provider._conn.commands] == ["list", "select", "search", "fetch"]
    assert "BODY.PEEK[]" not in provider._conn.commands[-1][-1]
    expected = {_message_id("INBOX", "10", uid): f"Subject: {uid}\r\n\r\nBody {uid}".encode() for uid in range(1, 52)}
    assert {entry["provider_id"]: cache.read(entry["id"]) for entry in cache.list_entries()} == expected
