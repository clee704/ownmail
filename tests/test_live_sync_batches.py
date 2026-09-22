"""Batching and content reuse retain the live download lifecycle contracts."""

from dataclasses import replace

import pytest

from ownmail import roles
from ownmail.archive import EmailArchive
from ownmail.live import LiveLookupError
from tests.test_live_sync import MailServer, message, owned_rows, sync


class BatchServer(MailServer):
    live_batch_size = 3

    def __init__(self, messages):
        super().__init__(messages)
        self.batches = []
        self.batch_error = None

    def read_live_messages(self, message_ids):
        self.batches.append(message_ids)
        if self.batch_error:
            raise self.batch_error
        return {key: self.messages.get(key) for key in message_ids}


@pytest.fixture
def archive(tmp_path):
    return EmailArchive(tmp_path / "archive")


def test_initial_batches_and_unchanged_repeat_reuse_verified_content(archive):
    server = BatchServer([message(str(i), content_revision="1") for i in range(8)])
    assert sync(archive, server)["active_refreshed"] == 8
    assert server.batches == [["0", "1", "2"], ["3", "4", "5"], ["6", "7"]]
    server.batches.clear()
    # The listing carries metadata only, as real providers do.
    server.listed = [replace(item, raw=None, labels=("Fresh label",)) for item in server.messages.values()]
    assert sync(archive, server)["active_complete"] is True
    assert server.batches == []
    cache = archive.active_cache()
    assert len(cache.db.search('label:"Fresh label"')) == 8
    assert all(cache.read(entry["id"]) == server.messages[entry["provider_id"]].raw for entry in cache.list_entries())


@pytest.mark.parametrize("revision", [None, "2"])
def test_missing_or_changed_revision_requires_new_content(archive, revision):
    original = message(content_revision="1")
    server = BatchServer([original])
    sync(archive, server)
    server.batches.clear()
    edited = replace(original, raw=original.raw.replace(b"Body", b"Edited"), content_revision=revision)
    server.messages["1"] = edited
    assert sync(archive, server)["active_refreshed"] == 1
    assert server.batches == [["1"]]
    entry = archive.active_cache().list_entries()[0]
    assert archive.active_cache().read(entry["id"]) == edited.raw


def test_eligible_transition_rechecks_state_even_when_revision_matches(archive):
    original = message(content_revision="1")
    server = BatchServer([original])
    sync(archive, server)
    server.batches.clear()
    server.listed = [replace(original, state="eligible", roles=frozenset({roles.ARCHIVE}))]
    server.messages["1"] = replace(original, roles=frozenset({roles.DRAFTS}), labels=("Drafts",))
    assert sync(archive, server)["success_count"] == 0
    assert server.batches == [["1"]]
    assert owned_rows(archive) == []
    assert archive.active_cache().list_entries()[0]["labels"] == ["Drafts"]


def test_corrupt_cached_content_is_downloaded_and_repaired(archive):
    original = message(content_revision="1")
    server = BatchServer([original])
    sync(archive, server)
    cache = archive.active_cache()
    entry = cache.list_entries()[0]
    (cache.cache_dir / entry["filename"]).write_bytes(b"broken")
    server.batches.clear()
    assert sync(archive, server)["active_complete"] is True
    assert server.batches == [["1"]]
    assert cache.read(entry["id"]) == original.raw


def test_batch_partial_failure_preserves_good_saves_and_retries(archive):
    messages = [message(str(i), content_revision="1") for i in range(4)]
    server = BatchServer(messages)
    server.listed = messages
    server.messages["1"] = LiveLookupError("Unavailable")
    result = sync(archive, server)
    assert result["active_refreshed"] == 3
    assert result["failed_ids"] == ["1"]
    assert result["active_complete"] is False
    server.messages["1"] = messages[1]
    server.batches.clear()
    assert sync(archive, server)["active_complete"] is True
    assert server.batches == [["1"]]


def test_batch_transport_failure_retains_cache_and_continues_other_batches(archive):
    server = BatchServer([message(str(i)) for i in range(4)])
    sync(archive, server)
    server.batch_error = ConnectionError("Offline")
    result = sync(archive, server)
    assert result["failed_ids"] == ["0", "1", "2", "3"]
    assert len(archive.active_cache().list_entries()) == 4


@pytest.mark.parametrize("reply", [{}, {"outside": None}, {"1": "bad"}])
def test_invalid_batch_reply_cannot_remove_previous_copy(archive, monkeypatch, reply):
    server = BatchServer([message()])
    sync(archive, server)
    monkeypatch.setattr(server, "read_live_messages", lambda ids: reply)
    result = sync(archive, server)
    assert result["error_count"] == 1
    assert result["active_complete"] is False
    assert len(archive.active_cache().list_entries()) == 1


def test_reconciliation_batches_confirmed_absence(archive):
    server = BatchServer([message(str(i)) for i in range(8)])
    sync(archive, server)
    server.batches.clear()
    server.messages.clear()
    assert sync(archive, server)["active_complete"] is True
    assert sorted(len(batch) for batch in server.batches) == [2, 3, 3]
    assert archive.active_cache().list_entries() == []


@pytest.mark.parametrize("complete", [True, False])
def test_reconciliation_rejects_a_different_message_locator(archive, complete):
    original = message()
    server = BatchServer([original])
    sync(archive, server)
    server.listed = []
    server.complete = complete
    server.messages["1"] = replace(original, message_id="other", state="discarded")
    assert sync(archive, server)["active_complete"] is False
    assert len(archive.active_cache().list_entries()) == 1


def test_interrupt_after_a_batch_keeps_completed_saves(archive, monkeypatch):
    server = BatchServer([message(str(i)) for i in range(4)])
    read = server.read_live_messages

    def interrupted(ids):
        if ids == ["3"]:
            raise KeyboardInterrupt
        return read(ids)

    monkeypatch.setattr(server, "read_live_messages", interrupted)
    result = sync(archive, server)
    assert result["interrupted"] is True
    assert result["active_refreshed"] == 3
    assert len(archive.active_cache().list_entries()) == 3
