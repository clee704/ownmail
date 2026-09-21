"""Active folder exclusions keep incremental capture and fresh identity checks."""

import json

import pytest

from ownmail import capture
from ownmail.archive import EmailArchive
from ownmail.providers.live_imap import _message_id
from tests.test_live_imap_batch import provider_for


def state_for(provider, watermarks, *, validity="10", excluded=()):
    return capture.dump(
        capture.CaptureState(
            cursor=json.dumps(
                {folder: {"max_uid": uid, "uidvalidity": validity} for folder, uid in watermarks.items()}
            ),
            excluded=frozenset(excluded),
            fingerprint=provider._filter_fingerprint(),
        )
    )


def capture_state(archive, provider):
    return archive.active_cache().source_status(provider.source_name, provider.account)["capture_state"]


def metadata_fetches(provider, folder):
    return [command for command in provider._conn.commands if command[:2] == ("fetch", folder)]


def test_retained_archive_is_searched_incrementally_without_metadata_fetches():
    provider = provider_for(
        {"Archive": list(range(1, 1001)), "INBOX": [1001, 1002]}, active_exclude_folders=["Archive"]
    )
    state = state_for(provider, {"Archive": 1000, "INBOX": 1002})
    snapshot = provider.list_live_messages(incremental=True, sync_state=state)
    assert snapshot.complete and snapshot.sync_state
    assert metadata_fetches(provider, "Archive") == []
    assert ("search", "Archive", None, "UID 1001:*") in provider._conn.commands
    assert [message.message_id for message in snapshot.messages] == [
        _message_id("INBOX", "10", uid) for uid in [1001, 1002]
    ]
    assert all(message.active_allowed and message.active_scope == ("INBOX",) for message in snapshot.messages)
    assert len(provider._conn.commands) == 6


def test_new_excluded_folder_message_remains_eligible_and_raw_read_rechecks_scope():
    provider = provider_for({"Archive": [1, 2]}, active_exclude_folders=["Archive"])
    snapshot = provider.list_live_messages(incremental=True, sync_state=state_for(provider, {"Archive": 1}))
    (message,) = snapshot.messages
    assert message.message_id == _message_id("Archive", "10", 2)
    assert message.state == "eligible" and message.download_allowed and not message.active_allowed
    assert message.active_scope == ("Archive",)
    provider._active_exclude_folders.clear()
    fresh = provider.read_live_message(message.message_id)
    assert fresh.active_allowed and fresh.raw.endswith(b"Body 2")


def test_capture_watermark_comes_from_the_same_search_that_supplied_candidates():
    provider = provider_for({"Archive": [1, 2]}, active_exclude_folders=["Archive"])
    original = provider._conn.uid

    def arrive_after_search(command, *args):
        result = original(command, *args)
        if command == "search" and 3 not in provider._conn.folders["Archive"]:
            provider._conn.folders["Archive"].append(3)
        return result

    provider._conn.uid = arrive_after_search
    first = provider.list_live_messages(incremental=True, sync_state=state_for(provider, {"Archive": 1}))
    assert json.loads(capture.load(first.sync_state).cursor)["Archive"]["max_uid"] == 2
    second = provider.list_live_messages(incremental=True, sync_state=first.sync_state)
    assert [message.message_id for message in second.messages] == [_message_id("Archive", "10", 3)]


def test_uidvalidity_change_rescans_and_owned_callback_sees_new_scoped_identity():
    provider = provider_for({"Archive": [1, 2]}, active_exclude_folders=["Archive"])
    seen = []

    def is_owned(message):
        seen.append(message.identity_token)
        return message.identity_token == _message_id("Archive", "9", 1)

    snapshot = provider.list_live_messages(
        incremental=True, sync_state=state_for(provider, {"Archive": 1000}, validity="9"), is_owned=is_owned
    )
    assert snapshot.complete
    assert seen == [_message_id("Archive", "10", uid) for uid in [1, 2]]
    assert len(snapshot.messages) == 2
    assert ("search", "Archive", None, "ALL") in provider._conn.commands
    cursor = json.loads(capture.load(snapshot.sync_state).cursor)
    assert cursor["Archive"] == {"max_uid": 2, "uidvalidity": "10"}


def test_only_verified_owned_candidates_are_omitted_from_bootstrap():
    provider = provider_for({"Archive": [1, 2]}, active_exclude_folders=["Archive"])
    snapshot = provider.list_live_messages(
        incremental=True, is_owned=lambda message: message.identity_token == _message_id("Archive", "10", 1)
    )
    assert snapshot.complete
    assert [message.message_id for message in snapshot.messages] == [_message_id("Archive", "10", 2)]


@pytest.mark.parametrize("failure", ["missing_fetch", "search_failure", "owned_failure"])
def test_incomplete_capture_candidates_never_propose_a_cursor(failure):
    provider = provider_for({"Archive": [1, 2]}, active_exclude_folders=["Archive"])
    callback = None
    if failure == "missing_fetch":
        provider._conn.omitted = {2}
    elif failure == "search_failure":
        original = provider._conn.uid
        provider._conn.uid = lambda command, *args: ("NO", []) if command == "search" else original(command, *args)
    else:

        def callback(message):
            raise OSError("verification unavailable")

    snapshot = provider.list_live_messages(incremental=True, is_owned=callback)
    assert not snapshot.complete
    assert snapshot.sync_state is None


@pytest.mark.parametrize(
    "saved",
    [
        "bad",
        "[]",
        '{"Archive":{"max_uid":true,"uidvalidity":"10"}}',
        '{"Archive":{"max_uid":1000,"uidvalidity":"bad"}}',
    ],
)
def test_unusable_cursor_bootstraps_without_skipping_existing_uids(saved):
    provider = provider_for({"Archive": [1]}, active_exclude_folders=["Archive"])
    snapshot = provider.list_live_messages(incremental=True, sync_state=saved)
    assert snapshot.complete and snapshot.sync_state
    assert [message.message_id for message in snapshot.messages] == [_message_id("Archive", "10", 1)]


def test_saved_entry_scope_check_needs_no_network():
    provider = provider_for({"Archive": [1], "INBOX": [2]}, active_exclude_folders=["Archive"])
    assert not provider.live_entry_in_scope({"provider_id": _message_id("Archive", "10", 1), "labels": []})
    assert not provider.live_entry_in_scope({"provider_id": _message_id("INBOX", "10", 2), "active_scope": ["Archive"]})
    assert provider.live_entry_in_scope({"provider_id": _message_id("INBOX", "10", 2), "active_scope": ["INBOX"]})
    assert not provider.live_entry_in_scope({"provider_id": "broken"})
    assert provider._conn.commands == []


def test_excluded_archive_capture_retries_pending_state_without_populating_active(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"Archive": [1]}, active_exclude_folders=["Archive"])
    first = archive.backup(provider, active_downloads=True)
    assert first["success_count"] == 1 and first["active_refreshed"] == 0
    saved = capture_state(archive, provider)
    assert saved
    provider._conn.folders["Archive"].append(2)
    provider._conn.flags[2] = "$SubmitPending"
    pending = archive.backup(provider, active_downloads=True)
    assert pending["success_count"] == pending["active_refreshed"] == 0
    assert capture_state(archive, provider) == saved
    assert archive.active_cache().list_entries() == []
    provider._conn.flags.clear()
    complete = archive.backup(provider, active_downloads=True)
    assert complete["success_count"] == 1 and complete["active_refreshed"] == 0
    provider._conn.commands.clear()
    repeat = archive.backup(provider, active_downloads=True)
    assert repeat["success_count"] == 0 and repeat["error_count"] == 0
    assert metadata_fetches(provider, "Archive") == []


def test_excluded_all_mail_uses_arrivals_and_role_departures_not_full_metadata():
    provider = provider_for(
        {"All Mail": list(range(1, 1001)), "INBOX": [50]}, gmail=True, active_exclude_folders=["All Mail"]
    )
    provider._conn.attributes["All Mail"] = "\\All"
    provider._conn.labels[50] = ["\\Inbox"]
    saved = state_for(provider, {"All Mail": 1000, "INBOX": 50}, excluded=["All Mail:50", "All Mail:60"])
    snapshot = provider.list_live_messages(incremental=True, sync_state=saved)
    assert snapshot.complete and snapshot.sync_state
    assert metadata_fetches(provider, "All Mail")[0][2] == "60"
    assert len(metadata_fetches(provider, "All Mail")) == 1
    by_identity = {message.identity_token: message for message in snapshot.messages}
    assert by_identity["gmail:3c"].state == "eligible" and not by_identity["gmail:3c"].active_allowed
    assert by_identity["gmail:32"].active_allowed and by_identity["gmail:32"].state == "active"
    assert capture.load(snapshot.sync_state).excluded == frozenset({"All Mail:50"})


def test_gmail_departure_absence_is_confirmed_before_metadata_fetch():
    provider = provider_for({"All Mail": [1]}, gmail=True, active_exclude_folders=["All Mail"])
    provider._conn.attributes["All Mail"] = "\\All"
    saved = state_for(provider, {"All Mail": 2}, excluded=["All Mail:2"])
    snapshot = provider.list_live_messages(incremental=True, sync_state=saved)
    assert snapshot.complete and snapshot.messages == []
    assert capture.load(snapshot.sync_state).excluded == frozenset()
    assert metadata_fetches(provider, "All Mail") == []


def test_gmail_changed_uidvalidity_does_not_recover_departures_from_old_epoch():
    provider = provider_for({"All Mail": [1]}, gmail=True, active_exclude_folders=["All Mail"])
    provider._conn.attributes["All Mail"] = "\\All"
    saved = state_for(provider, {"All Mail": 1000}, validity="9", excluded=["All Mail:999"])
    snapshot = provider.list_live_messages(incremental=True, sync_state=saved)
    assert snapshot.complete
    assert [message.message_id for message in snapshot.messages] == [_message_id("All Mail", "10", 1)]
    assert metadata_fetches(provider, "All Mail")[0][2] == "1"


def test_gmail_exceptional_folders_keep_full_state_checks_as_safe_fallback():
    provider = provider_for({"All Mail": [1, 2], "Later": [1]}, gmail=True, active_exclude_folders=["All Mail"])
    provider._conn.attributes = {"All Mail": "\\All", "Later": "\\Scheduled"}
    snapshot = provider.list_live_messages(
        incremental=True, sync_state=state_for(provider, {"All Mail": 2, "Later": 1})
    )
    assert snapshot.complete and snapshot.sync_state is None
    assert metadata_fetches(provider, "All Mail")[0][2] == "1,2"
    assert any(message.state == "active" and message.active_allowed for message in snapshot.messages)


def test_gmail_fresh_label_scope_applies_even_through_all_mail():
    provider = provider_for({"All Mail": [1], "INBOX": [1]}, gmail=True, active_exclude_folders=["INBOX"])
    provider._conn.attributes["All Mail"] = "\\All"
    provider._conn.labels[1] = ["\\Inbox"]
    snapshot = provider.list_live_messages(incremental=True)
    (message,) = snapshot.messages
    assert not message.active_allowed and "INBOX" in message.active_scope
    provider._conn.labels[1] = ["Projects"]
    fresh = provider.read_live_message(_message_id("All Mail", "10", 1))
    assert fresh.active_allowed and "INBOX" not in fresh.active_scope


def test_unknown_active_folder_exclusion_fails_both_listing_and_fresh_reads():
    provider = provider_for({"Archive": [1]}, active_exclude_folders=["Arhcive"])
    snapshot = provider.list_live_messages(incremental=True)
    assert not snapshot.complete and snapshot.sync_state is None
    result = provider.read_live_messages([_message_id("Archive", "10", 1)])
    assert isinstance(result[_message_id("Archive", "10", 1)], Exception)
    assert not any(command[0] == "fetch" for command in provider._conn.commands)


def test_gmail_all_mail_exclusion_does_not_hide_fresh_inbox_membership():
    provider = provider_for({"All Mail": [1], "INBOX": [1]}, gmail=True, active_exclude_folders=["All Mail"])
    provider._conn.attributes["All Mail"] = "\\All"
    provider._conn.labels[1] = ["\\Inbox"]
    fresh = provider.read_live_message(_message_id("All Mail", "10", 1))
    assert fresh.active_allowed and fresh.active_scope == ("INBOX",)
    assert provider.live_entry_in_scope({"provider_id": fresh.message_id, "active_scope": list(fresh.active_scope)})


def test_move_into_excluded_archive_is_captured_and_old_active_copy_is_retired(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"INBOX": [1], "Archive": []}, active_exclude_folders=["Archive"])
    first = archive.backup(provider, active_downloads=True)
    assert first["active_refreshed"] == 1 and first["success_count"] == 0
    provider._conn.folders = {"INBOX": [], "Archive": [2]}
    moved = archive.backup(provider, active_downloads=True)
    assert moved["success_count"] == 1 and moved["error_count"] == 0
    assert archive.active_cache().list_entries() == []
    assert archive.db.get_email_count() == 1


def test_excluded_archive_repeat_cost_and_single_new_arrival():
    provider = provider_for({"Archive": list(range(1, 1001))}, active_exclude_folders=["Archive"])
    before = provider.list_live_messages()
    assert before.complete and len(before.messages) == 1000
    assert len(provider._conn.commands) == 5
    assert len(metadata_fetches(provider, "Archive")) == 2
    provider._conn.commands.clear()
    saved = state_for(provider, {"Archive": 1000})
    unchanged = provider.list_live_messages(incremental=True, sync_state=saved)
    assert unchanged.complete and unchanged.messages == []
    assert [command[0] for command in provider._conn.commands] == ["list", "select", "search"]
    provider._conn.commands.clear()
    provider._conn.folders["Archive"].append(1001)
    arrival = provider.list_live_messages(incremental=True, sync_state=unchanged.sync_state)
    assert len(arrival.messages) == 1 and arrival.messages[0].message_id == _message_id("Archive", "10", 1001)
    assert [command[0] for command in provider._conn.commands] == ["list", "select", "search", "fetch"]
    assert metadata_fetches(provider, "Archive")[0][2] == "1001"
    fresh = provider.read_live_message(arrival.messages[0].message_id)
    assert fresh.state == "eligible" and fresh.raw.endswith(b"Body 1001")
    assert len(provider._conn.commands) == 8


def test_narrowing_active_scope_keeps_unfinished_cached_message_retryable(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"Archive": [1]})
    provider._conn.flags[1] = "$SubmitPending"
    tracked = archive.backup(provider, active_downloads=True)
    assert tracked["active_refreshed"] == 1 and tracked["success_count"] == 0
    saved = capture_state(archive, provider)
    assert json.loads(capture.load(saved).cursor)["Archive"]["max_uid"] == 1

    provider._active_exclude_folders.append("Archive")
    provider._conn.commands.clear()
    pending = archive.backup(provider, active_downloads=True)
    assert pending["success_count"] == pending["active_refreshed"] == 0
    assert not pending["active_complete"]
    assert capture_state(archive, provider) == saved
    assert len(archive.active_cache().list_entries()) == 1
    assert ("search", "Archive", None, "ALL") in provider._conn.commands

    provider._conn.flags.clear()
    provider._conn.commands.clear()
    completed = archive.backup(provider, active_downloads=True)
    assert completed["success_count"] == 1 and completed["error_count"] == 0
    assert completed["active_complete"]
    assert archive.active_cache().list_entries() == []
    assert archive.db.get_email_count() == 1
    assert ("search", "Archive", None, "ALL") in provider._conn.commands
    provider._conn.commands.clear()
    repeated = archive.backup(provider, active_downloads=True)
    assert repeated["success_count"] == 0 and repeated["active_complete"]
    assert metadata_fetches(provider, "Archive") == []


def test_failed_scope_change_scan_retries_previously_cached_capture_candidate(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = provider_for({"Archive": [1]})
    provider._conn.flags[1] = "$SubmitPending"
    tracked = archive.backup(provider, active_downloads=True)
    assert tracked["active_refreshed"] == 1
    saved = capture_state(archive, provider)
    assert saved

    provider._active_exclude_folders.append("Archive")
    provider._conn.flags.clear()
    provider._conn.fetch_error = OSError("unavailable")
    failed = archive.backup(provider, active_downloads=True)
    assert not failed["active_complete"] and failed["success_count"] == 0
    assert capture_state(archive, provider) == saved
    assert len(archive.active_cache().list_entries()) == 1

    provider._conn.fetch_error = None
    provider._conn.commands.clear()
    retried = archive.backup(provider, active_downloads=True)
    assert retried["success_count"] == 1 and retried["error_count"] == 0
    assert retried["active_complete"]
    assert archive.active_cache().list_entries() == []
    assert ("search", "Archive", None, "ALL") in provider._conn.commands
