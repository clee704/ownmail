"""Default Active discovery checks live state without revisiting filed history."""

import json

import pytest

from ownmail import capture
from ownmail.archive import EmailArchive
from tests.test_imap_active_scope import capture_state, metadata_fetches, state_for
from tests.test_live_imap_batch import provider_for


@pytest.mark.parametrize("gmail", [False, True])
def test_default_repeat_skips_retained_history_without_exclusions(gmail):
    provider = provider_for({"Archive": list(range(1, 1001)), "INBOX": [1001]}, gmail=gmail)
    provider._conn.labels[1001] = [r"\Inbox"]
    snapshot = provider.list_live_messages(
        incremental=True, sync_state=state_for(provider, {"Archive": 1000, "INBOX": 1001})
    )
    assert snapshot.complete and snapshot.sync_state
    assert metadata_fetches(provider, "Archive") == []
    assert len(snapshot.messages) == 1 and snapshot.messages[0].state == "active"
    assert len(metadata_fetches(provider, "INBOX")) == 1


@pytest.mark.parametrize(
    "flag,state", [(r"\Draft", "active"), ("$SubmitPending", "active"), ("$Unrecognized", "unknown")]
)
def test_old_uid_flag_change_is_discovered_outside_inbox(flag, state):
    provider = provider_for({"Archive": list(range(1, 1001))})
    provider._conn.flags[4] = flag
    snapshot = provider.list_live_messages(incremental=True, sync_state=state_for(provider, {"Archive": 1000}))
    assert snapshot.complete
    assert len(snapshot.messages) == 1
    assert snapshot.messages[0].state == state
    assert metadata_fetches(provider, "Archive")[0][2] == "4"
    assert capture.load(snapshot.sync_state).excluded == frozenset({snapshot.messages[0].identity_token})


def test_unresolved_identity_is_rechecked_without_holding_other_arrivals(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"Archive": list(range(1, 21))}, active_exclude_folders=["Archive"])
    provider._conn.flags[1] = "$Unrecognized"
    first = archive.backup(provider, active_downloads=True)
    assert first["success_count"] == 19 and first["active_refreshed"] == 0
    assert len(capture.load(capture_state(archive, provider)).excluded) == 1
    provider._conn.commands.clear()
    provider._conn.folders["Archive"].append(21)
    second = archive.backup(provider, active_downloads=True)
    assert second["success_count"] == 1 and second["error_count"] == 0
    assert metadata_fetches(provider, "Archive")[0][2] == "1,21"
    assert json.loads(capture.load(capture_state(archive, provider)).cursor)["Archive"]["max_uid"] == 21
    provider._conn.flags.clear()
    provider._conn.commands.clear()
    third = archive.backup(provider, active_downloads=True)
    assert third["success_count"] == 1
    assert capture.load(capture_state(archive, provider)).excluded == frozenset()
    provider._conn.commands.clear()
    assert archive.backup(provider, active_downloads=True)["success_count"] == 0
    assert metadata_fetches(provider, "Archive") == []


def test_gmail_scheduled_departure_is_found_in_all_mail_under_same_identity(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"All Mail": [1, 2], "Later": [1]}, gmail=True)
    provider._conn.attributes = {"All Mail": r"\All", "Later": r"\Scheduled"}
    assert archive.backup(provider, active_downloads=True)["active_refreshed"] == 1
    provider._conn.folders["Later"] = []
    provider._conn.commands.clear()
    completed = archive.backup(provider, active_downloads=True)
    assert completed["success_count"] == 1 and completed["active_complete"]
    assert metadata_fetches(provider, "All Mail")[0][2] == "1"
    assert archive.active_cache().list_entries() == []
    assert capture.load(capture_state(archive, provider)).excluded == frozenset()


@pytest.mark.parametrize(
    "flags", [None, b"garbage", b"(\\Unknown)", b"(bad\\keyword)", b"(bad]keyword)", b'(bad"keyword)', b"(\xff)"]
)
def test_unusable_flag_catalog_falls_back_to_complete_metadata(flags):
    provider = provider_for({"Archive": [1, 2]})
    response = provider._conn.response
    provider._conn.response = lambda name: ("FLAGS", [flags]) if name == "FLAGS" else response(name)
    snapshot = provider.list_live_messages(incremental=True, sync_state=state_for(provider, {"Archive": 2}))
    assert snapshot.complete
    assert len(snapshot.messages) == 2
    assert metadata_fetches(provider, "Archive")[0][2] == "1,2"


@pytest.mark.parametrize("failure", ["search", "missing_metadata", "interrupt"])
def test_failed_active_discovery_never_proposes_a_checkpoint(failure):
    provider = provider_for({"Archive": [1]})
    provider._conn.flags[1] = r"\Draft"
    if failure == "missing_metadata":
        provider._conn.omitted = {1}
    else:
        original = provider._conn.uid

        def uid(command, *args):
            if command == "search" and args[1] in {"DRAFT", "ALL"}:
                if failure == "interrupt":
                    raise KeyboardInterrupt
                return "NO", []
            return original(command, *args)

        provider._conn.uid = uid
    if failure == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            provider.list_live_messages(incremental=True)
    else:
        snapshot = provider.list_live_messages(incremental=True)
        assert not snapshot.complete and snapshot.sync_state is None


def test_foreign_gmail_pending_search_result_is_not_accepted():
    provider = provider_for({"All Mail": [1, 2]}, gmail=True)
    provider._conn.attributes = {"All Mail": r"\All"}
    original = provider._conn.uid

    def uid(command, *args):
        if command == "search" and "X-GM-MSGID" in args[1]:
            return "OK", [b"2"]
        return original(command, *args)

    provider._conn.uid = uid
    snapshot = provider.list_live_messages(
        incremental=True, sync_state=state_for(provider, {"All Mail": 2}, excluded=["gmail:1"])
    )
    assert not snapshot.complete and snapshot.sync_state is None
    assert snapshot.messages == []


def test_deleted_pending_identity_is_removed_from_next_checkpoint(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"Archive": [1]}, active_exclude_folders=["Archive"])
    provider._conn.flags[1] = "$SubmitPending"
    assert archive.backup(provider, active_downloads=True)["active_complete"]
    assert capture.load(capture_state(archive, provider)).excluded
    provider._conn.folders["Archive"] = []
    result = archive.backup(provider, active_downloads=True)
    assert result["active_complete"] and result["success_count"] == 0
    assert not capture.load(capture_state(archive, provider)).excluded


def test_previous_selection_checkpoint_is_rescanned_once_for_migration():
    provider = provider_for({"Archive": [1]})
    old = capture.CaptureState(
        cursor=json.dumps({"Archive": {"max_uid": 1, "uidvalidity": "10"}}), fingerprint=provider._filter_fingerprint()
    )
    first = provider.list_live_messages(incremental=True, sync_state=capture.dump(old))
    assert first.complete and len(first.messages) == 1
    provider._conn.commands.clear()
    repeat = provider.list_live_messages(incremental=True, sync_state=first.sync_state)
    assert repeat.complete and repeat.messages == []
    assert metadata_fetches(provider, "Archive") == []


@pytest.mark.parametrize("bad", ["not-an-id", None])
def test_invalid_pending_checkpoint_bootstraps_instead_of_skipping_capture(bad):
    provider = provider_for({"Archive": [1]})
    state = json.loads(state_for(provider, {"Archive": 1}))
    state["excluded"] = [bad]
    snapshot = provider.list_live_messages(incremental=True, sync_state=json.dumps(state))
    assert snapshot.complete and len(snapshot.messages) == 1


@pytest.mark.parametrize("attributes", [r"\Scheduled", r"\Unrecognized"])
def test_excluded_gmail_exceptional_membership_stays_pending_without_caching(tmp_path, attributes):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"All Mail": [1], "Later": [1]}, gmail=True, active_exclude_folders=["Later"])
    provider._conn.attributes = {"All Mail": r"\All", "Later": attributes}
    for _ in range(3):
        result = archive.backup(provider, active_downloads=True)
        assert result["active_complete"] and result["success_count"] == 0
        assert archive.active_cache().list_entries() == []
        assert capture.load(capture_state(archive, provider)).excluded == frozenset({"gmail:1"})
    provider._conn.folders["Later"] = []
    completed = archive.backup(provider, active_downloads=True)
    assert completed["active_complete"] and completed["success_count"] == 1
    assert not capture.load(capture_state(archive, provider)).excluded


@pytest.mark.parametrize("rejected", ["DRAFT", "KEYWORD $submitpending"])
def test_rejected_targeted_search_falls_back_to_successful_full_scan(rejected):
    provider = provider_for({"Archive": [1, 2]})
    provider._conn.flags[1] = "$SubmitPending"
    original = provider._conn.uid

    def uid(command, *args):
        if command == "search" and args[1] == rejected:
            return "BAD", []
        return original(command, *args)

    provider._conn.uid = uid
    snapshot = provider.list_live_messages(incremental=True, sync_state=state_for(provider, {"Archive": 2}))
    assert snapshot.complete and snapshot.sync_state
    assert len(snapshot.messages) == 2
    assert snapshot.messages[0].state == "active"
    assert metadata_fetches(provider, "Archive")[0][2] == "1,2"
