"""Content refreshes share catalog reads while preserving each fresh observation."""

import base64
from unittest.mock import MagicMock

import pytest

from ownmail.archive import EmailArchive
from ownmail.live import LiveLookupError, LiveMessage
from tests.test_live_gmail_batch import GmailTransport, provider_for
from tests.test_live_providers import gmail


def test_normal_downloads_batch_initial_content_reuse_unchanged_cache_and_fetch_one_change(tmp_path):
    transport = GmailTransport(101)
    for message in transport.messages.values():
        message["labelIds"] = ["INBOX", "Label_1"]
    provider = provider_for(transport)
    archive = EmailArchive(tmp_path / "archive")

    initial = archive.backup(provider, active_downloads=True)
    assert initial["active_complete"]
    assert initial["active_refreshed"] == 101
    assert transport.requests == {
        ("GET", "/gmail/v1/users/me/labels"): 4,
        ("GET", "/gmail/v1/users/me/messages"): 1,
        ("POST", "/batch"): 6,
    }
    assert transport.batch_formats == {"minimal": 101, "raw": 101}
    transport.requests.clear()
    transport.batch_formats.clear()
    transport.catalog["labels"][-1]["name"] = "Renamed"

    repeated = archive.backup(provider, active_downloads=True)
    assert repeated["active_complete"]
    assert transport.requests == {
        ("GET", "/gmail/v1/users/me/labels"): 1,
        ("GET", "/gmail/v1/users/me/messages"): 1,
        ("POST", "/batch"): 3,
    }
    assert transport.batch_formats == {"minimal": 101}
    assert all(entry["labels"] == ["INBOX", "Renamed"] for entry in archive.active_cache().list_entries())
    transport.requests.clear()
    transport.batch_formats.clear()
    changed_raw = b"From: sender@example.test\r\nSubject: changed\r\n\r\nEdited body"
    transport.messages["m25"].update(raw=base64.urlsafe_b64encode(changed_raw).decode(), historyId="1001")

    changed = archive.backup(provider, active_downloads=True)
    assert changed["active_complete"]
    assert transport.requests == {
        ("GET", "/gmail/v1/users/me/labels"): 2,
        ("GET", "/gmail/v1/users/me/messages"): 1,
        ("POST", "/batch"): 4,
    }
    assert transport.batch_formats == {"minimal": 101, "raw": 1}
    cache = archive.active_cache()
    entry = next(entry for entry in cache.list_entries() if entry["provider_id"] == "m25")
    assert cache.read(entry["id"]) == changed_raw


@pytest.mark.parametrize("include_labels", [True, False])
def test_content_batches_share_one_fresh_catalog_and_round_trip_per_fifty_messages(include_labels):
    transport = GmailTransport(101)
    provider = provider_for(transport, include_labels=include_labels)
    assert provider.live_batch_size == 50
    messages = provider.read_live_messages(list(transport.messages))
    assert list(messages) == list(transport.messages)
    for message_id, message in messages.items():
        expected = transport.messages[message_id]
        assert message.message_id == message_id
        assert message.raw == base64.urlsafe_b64decode(expected["raw"])
        assert message.content_revision == expected["historyId"]
        assert message.labels == (("Projects",) if include_labels else ())
    assert transport.requests == {("GET", "/gmail/v1/users/me/labels"): 3, ("POST", "/batch"): 3}
    assert transport.batch_sizes == [50, 50, 1]
    assert transport.batch_formats == {"raw": 101}


def test_raw_batch_refreshes_lifecycle_labels_and_revision_after_listing():
    transport = GmailTransport(3)
    provider = provider_for(transport)
    snapshot = provider.list_live_messages()
    assert [message.state for message in snapshot.messages] == ["eligible"] * 3
    transport.messages["m0"].update(labelIds=["INBOX", "Label_1"], historyId="10")
    transport.messages["m1"].update(labelIds=["TRASH"], historyId="11", raw=None)
    transport.messages["m2"].update(labelIds=["SCHEDULED"], historyId="12")
    transport.catalog["labels"][-1]["name"] = "Renamed"
    messages = provider.read_live_messages(list(transport.messages))
    assert [message.state for message in messages.values()] == ["active", "discarded", "unknown"]
    assert messages["m0"].labels == ("INBOX", "Renamed")
    assert messages["m1"].raw is None
    assert messages["m2"].raw
    assert [message.content_revision for message in messages.values()] == ["10", "11", "12"]


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_content_batch_only_member_not_found_confirms_absence(status):
    transport = GmailTransport(3)
    transport.errors["m1"] = status
    messages = provider_for(transport).read_live_messages(list(transport.messages))
    assert isinstance(messages["m0"], LiveMessage)
    assert isinstance(messages["m2"], LiveMessage)
    if status == 404:
        assert messages["m1"] is None
    else:
        assert isinstance(messages["m1"], LiveLookupError)
        assert "private" not in str(messages["m1"])


@pytest.mark.parametrize(
    "change",
    [{"id": "other"}, {"threadId": None}, {"labelIds": "INBOX"}, {"raw": None}, {"raw": "!bad!"}],
)
def test_malformed_content_batch_member_cannot_authorize_capture(change):
    transport = GmailTransport(3)
    transport.messages["m1"].update(change)
    messages = provider_for(transport).read_live_messages(list(transport.messages))
    assert isinstance(messages["m1"], LiveLookupError)
    assert isinstance(messages["m0"], LiveMessage)
    assert isinstance(messages["m2"], LiveMessage)


@pytest.mark.parametrize("revision", [None, 42, "", " ", "x", "12.5", "-1", "１２"])
def test_malformed_revision_is_rejected_in_metadata_content_and_single_reads(revision):
    transport = GmailTransport(1)
    transport.messages["m0"]["historyId"] = revision
    provider = provider_for(transport)
    assert not provider.list_live_messages().complete
    result = provider.read_live_messages(["m0"])
    assert isinstance(result["m0"], LiveLookupError)
    single = gmail()
    single._service.users().messages().get().execute.return_value["historyId"] = revision
    with pytest.raises(LiveLookupError, match="revision is malformed"):
        single.read_live_message("a")


def test_missing_revision_keeps_content_readable_without_authorizing_reuse():
    transport = GmailTransport(1)
    del transport.messages["m0"]["historyId"]
    provider = provider_for(transport)
    snapshot = provider.list_live_messages()
    assert snapshot.complete
    assert snapshot.messages[0].content_revision is None
    assert provider.read_live_messages(["m0"])["m0"].content_revision is None
    single = gmail()
    assert single.read_live_message("a").content_revision is None


@pytest.mark.parametrize("failure", ["transport", "missing"])
def test_failed_content_batch_preserves_other_batches_and_never_implies_absence(failure):
    transport = GmailTransport(101)
    if failure == "transport":
        transport.fail_batch = 2
    else:
        transport.omitted.add("m75")
    messages = provider_for(transport).read_live_messages(list(transport.messages))
    assert [key for key, value in messages.items() if isinstance(value, LiveMessage)] == [
        f"m{index}" for index in range(50)
    ] + ["m100"]
    assert all(isinstance(messages[f"m{index}"], LiveLookupError) for index in range(50, 100))
    assert transport.batch_sizes == [50, 50, 1]


@pytest.mark.parametrize("failure", ["missing", "duplicate", "unexpected", "exception"])
def test_content_callback_failures_preserve_unambiguous_results(failure):
    transport = GmailTransport(3)
    provider = provider_for(transport)

    def new_batch(*, callback):
        def execute():
            for message_id in ["m2", "m0", "m1"]:
                if failure == "missing" and message_id == "m1":
                    continue
                callback(message_id, transport.messages[message_id], None)
            if failure == "exception":
                raise RuntimeError("private batch details")
            if failure == "duplicate":
                callback("m1", transport.messages["m1"], None)
            if failure == "unexpected":
                callback("other", transport.messages["m0"], None)

        batch = MagicMock()
        batch.execute.side_effect = execute
        return batch

    provider._service.new_batch_http_request = new_batch
    messages = provider.read_live_messages(list(transport.messages))
    assert isinstance(messages["m0"], LiveMessage)
    assert isinstance(messages["m2"], LiveMessage)
    expected = LiveLookupError if failure in {"missing", "duplicate"} else LiveMessage
    assert isinstance(messages["m1"], expected)
    assert list(messages) == ["m0", "m1", "m2"]


@pytest.mark.parametrize("include_labels", [True, False])
def test_failed_content_catalog_never_uses_old_label_names(include_labels):
    transport = GmailTransport(1)
    provider = provider_for(transport, include_labels=include_labels)
    assert provider.read_live_messages(["m0"])["m0"].raw
    transport.catalog = {"labels": [{"id": "Label_1"}]}
    result = provider.read_live_messages(["m0"])
    assert isinstance(result["m0"], LiveLookupError)
    assert transport.batch_sizes == [1]


def test_empty_or_missing_id_requests_do_not_issue_content_reads():
    transport = GmailTransport(1)
    provider = provider_for(transport)
    assert provider.read_live_messages([]) == {}
    assert all(isinstance(value, LiveLookupError) for value in provider.read_live_messages(["", " "]).values())
    assert not transport.requests


def test_content_batch_interrupt_propagates_and_stops_later_reads():
    transport = GmailTransport(101)
    transport.fail_batch = 2
    transport.failure = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        provider_for(transport).read_live_messages(list(transport.messages))
    assert transport.batch_sizes == [50, 50]
