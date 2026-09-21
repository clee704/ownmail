"""Incremental capture remains independent from the Active tracking scope."""

from dataclasses import replace

import pytest

from ownmail.live import LiveLookupError
from tests.test_live_sync import MailServer, message, owned_rows, sync


class IncrementalServer(MailServer):
    name = "imap"
    incremental_live = True

    def __init__(self, messages=()):
        super().__init__(messages)
        self.states = []
        self.scope = True

    def list_live_messages(self, *, incremental, sync_state, is_owned, on_progress=None):
        assert incremental is True
        self.states.append(sync_state)
        snapshot = super().list_live_messages(on_progress=on_progress)
        return replace(snapshot, sync_state="next-cursor")

    def live_entry_in_scope(self, entry):
        return self.scope


@pytest.fixture
def archive(tmp_path):
    from ownmail.archive import EmailArchive

    return EmailArchive(tmp_path / "archive")


def saved_state(archive, server):
    return archive.active_cache().source_status(server.source_name, server.account)["capture_state"]


def seed_state(archive, server):
    from ownmail.config import active_scope_signature

    signature = active_scope_signature("imap", [])
    archive.active_cache(create=True).set_source_status(
        server.source_name,
        server.account,
        complete=True,
        active_scope_signature=signature,
        capture_scope_signature=signature,
        capture_state="old-cursor",
    )


def test_excluded_unfinished_candidate_holds_cursor_until_it_can_be_archived(archive):
    candidate = message(active_allowed=False, active_scope=("Archive",))
    server = IncrementalServer([candidate])
    seed_state(archive, server)

    first = sync(archive, server)
    assert first["active_refreshed"] == first["success_count"] == 0
    assert not first["active_complete"]
    assert server.reads == []
    assert archive.active_cache().list_entries() == []
    assert saved_state(archive, server) == "old-cursor"

    server.messages["1"] = replace(candidate, state="eligible")
    second = sync(archive, server)
    assert second["success_count"] == 1
    assert second["active_refreshed"] == 0
    assert server.states == ["old-cursor", "old-cursor"]
    assert saved_state(archive, server) == "next-cursor"
    assert len(owned_rows(archive)) == 1


@pytest.mark.parametrize("problem", ["partial", "read", "interrupt", "date"])
def test_unsuccessful_or_partial_capture_does_not_advance_incremental_cursor(archive, problem):
    candidate = message(state="eligible", active_allowed=False)
    server = IncrementalServer([candidate])
    server.listed = [candidate]
    seed_state(archive, server)
    if problem == "partial":
        server.complete = False
    elif problem == "read":
        server.messages["1"] = LiveLookupError("retry")
    elif problem == "interrupt":
        server.messages["1"] = KeyboardInterrupt()

    result = sync(archive, server, **({"since": "2020-01-01"} if problem == "date" else {}))
    assert saved_state(archive, server) == "old-cursor"
    assert result["success_count"] == int(problem in {"partial", "date"})
    assert result["interrupted"] is (problem == "interrupt")


def test_new_exclusion_preserves_old_cache_without_reading_it(archive):
    server = IncrementalServer([message()])
    sync(archive, server)
    cache = archive.active_cache()
    entry = cache.list_entries()[0]
    contents = cache.read(entry["id"])
    server.listed = []
    server.scope = False
    server.reads.clear()

    result = sync(archive, server)
    assert result["active_complete"]
    assert server.reads == []
    assert cache.get(entry["id"]) == entry
    assert cache.read(entry["id"]) == contents


def test_missing_cached_inbox_is_captured_when_filed_outside_active_scan(archive):
    active = message(active_scope=("INBOX",))
    server = IncrementalServer([active])
    sync(archive, server)
    server.listed = []
    server.messages["1"] = replace(active, state="eligible", active_scope=("Archive",), active_allowed=False)

    result = sync(archive, server)
    assert result["success_count"] == 1
    assert result["active_complete"]
    assert archive.active_cache().list_entries() == []
    assert len(owned_rows(archive)) == 1


def test_fresh_exclusion_blocks_cache_refresh_and_cursor_advance(archive):
    candidate = message()
    server = IncrementalServer([replace(candidate, active_allowed=False)])
    server.listed = [candidate]
    result = sync(archive, server)
    assert result["active_refreshed"] == result["success_count"] == 0
    assert archive.active_cache().list_entries() == []
    assert saved_state(archive, server) is None


def test_reenable_refreshes_preserved_active_content(archive):
    active = message(content_revision="1")
    server = IncrementalServer([active])
    assert sync(archive, server)["active_refreshed"] == 1
    entry = archive.active_cache().list_entries()[0]
    server.messages["1"] = replace(active, raw=active.raw + b" edited", content_revision="2")
    from tests.test_active_opt_in import legacy_provider

    ordinary, _ = legacy_provider("imap")
    assert archive.backup(ordinary, active_downloads=False)["success_count"] == 0
    assert archive.active_cache().read(entry["id"]) == active.raw
    assert sync(archive, server)["active_refreshed"] == 1
    assert archive.active_cache().read(entry["id"]) == active.raw + b" edited"
    assert archive.active_cache().get(entry["id"])["checked_at"] > entry["checked_at"]


def test_incremental_capture_state_is_separate_for_sources_with_the_same_account(archive):
    first = IncrementalServer([message(state="eligible")])
    second = IncrementalServer([message(state="eligible", raw=b"Subject: other server\n\nDifferent mail")])
    second.source_name = "other"
    assert sync(archive, first)["success_count"] == 1
    assert sync(archive, second)["success_count"] == 1
    assert first.states == second.states == [None]
    assert len(owned_rows(archive)) == 2
    assert archive.db.get_sync_state(first.account, "sync_state") is None


def test_failed_exclusion_metadata_save_does_not_stop_other_captures(archive, monkeypatch):
    first = message("first", active_scope=("INBOX",))
    server = IncrementalServer([first])
    sync(archive, server)
    entry = archive.active_cache().list_entries()[0]
    server.messages = {
        "first": replace(first, active_allowed=False, active_scope=("Retained",)),
        "second": message("second", state="eligible"),
    }
    server.can_defer_live_message = lambda message, state: True

    def fail_update(*args):
        raise OSError("could not save metadata")

    monkeypatch.setattr(archive.active_cache(), "update_scope", fail_update)
    result = sync(archive, server)
    assert result["error_count"] == result["success_count"] == 1
    assert not result["active_complete"]
    assert archive.active_cache().get(entry["id"]) == entry
    assert len(owned_rows(archive)) == 1
