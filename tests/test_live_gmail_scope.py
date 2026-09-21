"""Active exclusions narrow Gmail requests without narrowing archival candidates."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from ownmail import capture
from ownmail.archive import EmailArchive
from ownmail.live import LiveLookupError
from ownmail.providers.gmail import GmailProvider
from tests.test_live_gmail_batch import GmailTransport, provider_for


def test_scoped_first_and_repeat_scans_omit_retained_archive_metadata():
    transport = GmailTransport(1004)
    transport.messages["m1000"]["labelIds"] = ["INBOX"]
    transport.messages["m1001"]["labelIds"] = ["DRAFT"]
    transport.messages["m1002"]["labelIds"] = ["INBOX", "Label_1"]
    provider = provider_for(transport, active_exclude_labels=["Projects"])
    owned = {f"m{index}" for index in range(1000)}

    first = provider.list_live_messages(incremental=True, is_owned=lambda message: message.message_id in owned)

    assert first.complete
    assert capture.load(first.sync_state).cursor == transport.history_id
    assert {message.message_id for message in first.messages} == {"m1000", "m1001", "m1003"}
    assert set(transport.metadata_ids) == {"m1000", "m1001", "m1003"}
    candidate = next(message for message in first.messages if message.message_id == "m1003")
    assert candidate.state == "eligible" and not candidate.active_allowed
    assert transport.requests == {
        ("GET", "/gmail/v1/users/me/labels"): 1,
        ("GET", "/gmail/v1/users/me/profile"): 1,
        ("GET", "/gmail/v1/users/me/messages"): 10,
        ("POST", "/batch"): 3,
    }
    transport.requests.clear()
    transport.metadata_ids.clear()
    transport.message_queries.clear()

    repeated = provider.list_live_messages(incremental=True, sync_state=first.sync_state, is_owned=lambda _: True)

    assert repeated.complete
    assert {message.message_id for message in repeated.messages} == {"m1000", "m1001"}
    assert set(transport.metadata_ids) == {"m1000", "m1001"}
    assert all(query.get("labelIds") for query in transport.message_queries)
    scoped_queries = [query for query in transport.message_queries if "q" in query]
    assert {tuple(query["labelIds"]) for query in scoped_queries} == {("DRAFT",), ("INBOX",), ("SCHEDULED",)}
    assert all(query["q"] == ['-label:"Projects"'] for query in scoped_queries)
    assert transport.requests == {
        ("GET", "/gmail/v1/users/me/labels"): 1,
        ("GET", "/gmail/v1/users/me/history"): 1,
        ("GET", "/gmail/v1/users/me/messages"): 7,
        ("POST", "/batch"): 2,
    }


def test_normal_download_captures_new_eligible_mail_in_excluded_active_label(tmp_path):
    transport = GmailTransport(2)
    transport.messages["m0"]["labelIds"] = ["INBOX", "Label_1"]
    provider = provider_for(transport, active_exclude_labels=["Projects"])
    archive = EmailArchive(tmp_path / "archive")

    result = archive.backup(provider, active_downloads=True)

    assert result["success_count"] == 1
    assert result["active_refreshed"] == 0
    assert archive.active_cache().list_entries() == []
    assert list(archive.archive_dir.rglob("*.eml"))
    assert transport.metadata_ids == ["m1"]
    assert transport.batch_formats == {"minimal": 1, "raw": 1}


def test_cached_mail_filed_into_excluded_label_is_captured_on_next_incremental_run(tmp_path):
    transport = GmailTransport(1)
    transport.messages["m0"]["labelIds"] = ["INBOX"]
    provider = provider_for(transport, active_exclude_labels=["Projects"])
    archive = EmailArchive(tmp_path / "archive")
    assert archive.backup(provider, active_downloads=True)["active_refreshed"] == 1
    transport.messages["m0"].update(labelIds=["Label_1"], historyId="100001")
    transport.history_id = "100001"
    transport.metadata_ids.clear()

    result = archive.backup(provider, active_downloads=True)

    assert result["success_count"] == 1
    assert result["active_complete"]
    assert archive.active_cache().list_entries() == []
    assert transport.metadata_ids == ["m0"]


@pytest.mark.parametrize("include_labels", [True, False])
def test_newly_excluded_cached_inbox_stops_body_reads_and_still_archives_when_filed(tmp_path, include_labels):
    transport = GmailTransport(1)
    transport.messages["m0"]["labelIds"] = ["INBOX"]
    provider = provider_for(transport, include_labels=include_labels, active_exclude_labels=["Projects"])
    archive = EmailArchive(tmp_path / "archive")
    assert archive.backup(provider, active_downloads=True)["active_refreshed"] == 1
    cache = archive.active_cache()
    original = cache.list_entries()[0]
    original_raw = cache.read(original["id"])
    transport.messages["m0"].update(labelIds=["INBOX", "Label_1"], historyId="100001")
    transport.history_id = "100001"
    transport.metadata_ids.clear()
    transport.batch_formats.clear()

    excluded = archive.backup(provider, active_downloads=True)

    assert excluded["active_complete"]
    assert transport.batch_formats == {"raw": 1}
    entry = cache.get(original["id"])
    assert entry["active_scope"] == ["INBOX", "Projects"]
    assert entry["checked_at"] == original["checked_at"]
    assert cache.read(original["id"]) == original_raw
    assert capture.load(cache.source_status(provider.source_name, provider.account)["capture_state"]).cursor == "100001"
    transport.history_id = "100002"
    transport.batch_formats.clear()

    assert archive.backup(provider, active_downloads=True)["active_complete"]
    assert not transport.batch_formats
    assert not transport.metadata_ids
    assert capture.load(cache.source_status(provider.source_name, provider.account)["capture_state"]).cursor == "100002"
    transport.messages["m0"].update(labelIds=["Label_1"], historyId="100003")
    transport.history_id = "100003"

    filed = archive.backup(provider, active_downloads=True)

    assert filed["success_count"] == 1 and filed["active_complete"]
    assert cache.list_entries() == []
    assert transport.batch_formats == {"minimal": 1, "raw": 1}
    assert next(archive.archive_dir.rglob("*.eml")).read_bytes() == original_raw


def test_excluded_scheduled_cache_retains_retry_scope_until_eligible_capture(tmp_path):
    transport = GmailTransport(1)
    transport.messages["m0"]["labelIds"] = ["SCHEDULED"]
    provider = provider_for(transport, active_exclude_labels=["Projects"])
    archive = EmailArchive(tmp_path / "archive")
    assert archive.backup(provider, active_downloads=True)["active_refreshed"] == 1
    cache = archive.active_cache()
    original = cache.list_entries()[0]
    original_raw = cache.read(original["id"])
    initial_state = cache.source_status(provider.source_name, provider.account)["capture_state"]
    assert capture.load(initial_state).cursor == "100000"

    for history_id in ("100001", "100002"):
        transport.messages["m0"].update(labelIds=["SCHEDULED", "Label_1"], historyId=history_id)
        transport.history_id = history_id
        transport.metadata_ids.clear()
        transport.batch_formats.clear()

        pending = archive.backup(provider, active_downloads=True)

        assert not pending["active_complete"]
        assert pending["success_count"] == pending["error_count"] == 0
        assert transport.batch_formats == {"raw": 1}
        assert not transport.metadata_ids
        entry = cache.get(original["id"])
        assert entry["active_scope"] == ["SCHEDULED"]
        assert entry["checked_at"] == original["checked_at"]
        assert cache.read(original["id"]) == original_raw
        assert cache.source_status(provider.source_name, provider.account)["capture_state"] == initial_state

    transport.messages["m0"].update(labelIds=["Label_1"], historyId="100003")
    transport.history_id = "100003"
    transport.batch_formats.clear()

    filed = archive.backup(provider, active_downloads=True)

    assert filed["success_count"] == 1 and filed["active_complete"]
    assert transport.batch_formats == {"raw": 1}
    assert cache.list_entries() == []
    assert next(archive.archive_dir.rglob("*.eml")).read_bytes() == original_raw
    assert capture.load(cache.source_status(provider.source_name, provider.account)["capture_state"]).cursor == "100003"


def test_expired_history_rescans_candidates_but_skips_verified_owned_metadata():
    transport = GmailTransport(101)
    transport.messages["m100"]["labelIds"] = ["INBOX"]
    transport.history_status = 404
    provider = provider_for(transport)
    snapshot = provider.list_live_messages(incremental=True, sync_state="1", is_owned=lambda _: True)
    assert snapshot.complete
    assert capture.load(snapshot.sync_state).cursor == transport.history_id
    assert transport.metadata_ids == ["m100"]
    assert transport.requests["GET", "/gmail/v1/users/me/history"] == 1
    assert transport.requests["GET", "/gmail/v1/users/me/profile"] == 1


def test_new_excluded_label_arrival_remains_an_incremental_capture_candidate():
    transport = GmailTransport(1)
    transport.history_events = [{"messagesAdded": [{"message": {"id": "m0"}}]}]
    provider = provider_for(transport, active_exclude_labels=["Projects"])
    snapshot = provider.list_live_messages(incremental=True, sync_state="1")
    assert snapshot.complete
    assert [message.message_id for message in snapshot.messages] == ["m0"]
    assert snapshot.messages[0].state == "eligible"
    assert not snapshot.messages[0].active_allowed
    assert transport.metadata_ids == ["m0"]
    assert all(query.get("labelIds") for query in transport.message_queries)


def test_deleted_history_candidate_advances_cursor_after_explicit_metadata_not_found(tmp_path):
    transport = GmailTransport(0)
    provider = provider_for(transport)
    archive = EmailArchive(tmp_path / "archive")
    assert archive.backup(provider, active_downloads=True)["active_complete"]
    transport.history_id = "100001"
    transport.history_events = [{"messagesAdded": [{"message": {"id": "deleted"}}]}]
    transport.errors["deleted"] = 404

    result = archive.backup(provider, active_downloads=True)

    assert result["active_complete"]
    assert result["error_count"] == 0
    assert transport.metadata_ids == ["deleted"]
    state = archive.active_cache().source_status(provider.source_name, provider.account)["capture_state"]
    assert capture.load(state).cursor == transport.history_id
    transport.history_events.clear()
    transport.metadata_ids.clear()
    transport.batch_formats.clear()

    assert archive.backup(provider, active_downloads=True)["active_complete"]
    assert not transport.metadata_ids
    assert not transport.batch_formats


@pytest.mark.parametrize("failure", [403, 429, 500, "omitted"])
def test_unconfirmed_history_candidate_retains_cursor(failure, tmp_path):
    transport = GmailTransport(0)
    provider = provider_for(transport)
    archive = EmailArchive(tmp_path / "archive")
    assert archive.backup(provider, active_downloads=True)["active_complete"]
    state = archive.active_cache().source_status(provider.source_name, provider.account)["capture_state"]
    transport.history_id = "100001"
    transport.history_events = [{"messagesAdded": [{"message": {"id": "unconfirmed"}}]}]
    if failure == "omitted":
        transport.omitted.add("unconfirmed")
    else:
        transport.errors["unconfirmed"] = failure

    result = archive.backup(provider, active_downloads=True)

    assert not result["active_complete"]
    assert archive.active_cache().source_status(provider.source_name, provider.account)["capture_state"] == state


def test_only_sampled_excluded_role_members_can_defer_without_holding_history():
    transport = GmailTransport(1)
    transport.messages["m0"]["labelIds"] = ["INBOX", "Label_1"]
    provider = provider_for(transport, active_exclude_labels=["Projects"])
    snapshot = provider.list_live_messages(incremental=True)
    fresh = provider.read_live_messages(["m0"])["m0"]
    assert not fresh.active_allowed
    assert provider.can_defer_live_message(fresh, snapshot.sync_state)
    assert not provider.can_defer_live_message(fresh, None)
    assert not provider.can_defer_live_message(replace(fresh, identity_token="gmail:other"), snapshot.sync_state)

    transport.messages["m0"]["labelIds"] = ["SCHEDULED", "Label_1"]
    next_snapshot = provider.list_live_messages(incremental=True, sync_state=snapshot.sync_state)
    assert [message.message_id for message in next_snapshot.messages] == ["m0"]
    scheduled = next_snapshot.messages[0]
    assert scheduled.state == "unknown" and not scheduled.active_allowed
    assert not provider.can_defer_live_message(scheduled, next_snapshot.sync_state)


def test_known_owned_skip_never_skips_active_overlap_or_unknown_system_labels():
    transport = GmailTransport(2)
    transport.messages["m0"]["labelIds"] = ["INBOX", "DRAFT"]
    transport.messages["m1"]["labelIds"] = ["SCHEDULED"]
    provider = provider_for(transport)
    provider.get_new_message_ids = MagicMock(return_value=(["m0", "m1"], "next"))
    owned = MagicMock(return_value=True)

    snapshot = provider.list_live_messages(incremental=True, is_owned=owned)

    assert snapshot.complete
    assert snapshot.sync_state == "next"
    assert {message.message_id for message in snapshot.messages} == {"m0", "m1"}
    assert len(transport.metadata_ids) == 2
    owned.assert_not_called()


@pytest.mark.parametrize("include_labels", [True, False])
def test_raw_read_rechecks_active_exclusion_after_listing(include_labels):
    transport = GmailTransport(1)
    transport.messages["m0"]["labelIds"] = ["INBOX"]
    provider = provider_for(transport, include_labels=include_labels, active_exclude_labels=["Projects"])
    snapshot = provider.list_live_messages(incremental=True)
    assert snapshot.complete and snapshot.messages[0].active_allowed
    transport.messages["m0"]["labelIds"].append("Label_1")

    fresh = provider.read_live_messages(["m0"])["m0"]

    assert fresh.state == "active" and not fresh.active_allowed
    assert fresh.active_scope == ("INBOX", "Projects")
    assert fresh.labels == (("INBOX", "Projects") if include_labels else ())


def test_excluded_system_label_avoids_its_active_query():
    transport = GmailTransport(1)
    transport.messages["m0"]["labelIds"] = ["INBOX"]
    provider = provider_for(transport, active_exclude_labels=["INBOX"])
    provider.get_new_message_ids = MagicMock(return_value=([], "next"))
    snapshot = provider.list_live_messages(incremental=True)
    assert snapshot.complete and not snapshot.messages
    assert {tuple(query["labelIds"]) for query in transport.message_queries} == {("DRAFT",), ("SCHEDULED",)}


@pytest.mark.parametrize("name", ['bad"label', "bad\\label", "bad\nlabel", "", " "])
def test_unsupported_label_names_cannot_broaden_gmail_queries(name):
    with pytest.raises(ValueError, match="Active exclusion labels"):
        GmailProvider("person@example.test", MagicMock(), active_exclude_labels=[name])


@pytest.mark.parametrize("catalog_change", ["missing", "ambiguous"])
def test_unresolvable_scope_is_reported_before_any_capture_or_active_query(catalog_change):
    transport = GmailTransport(1)
    if catalog_change == "missing":
        transport.catalog["labels"].pop()
    else:
        transport.catalog["labels"].append({"id": "Label_2", "name": "Projects", "type": "user"})
    provider = provider_for(transport, active_exclude_labels=["Projects"])
    snapshot = provider.list_live_messages(incremental=True)
    assert not snapshot.complete
    assert "Active exclusion label is unavailable or ambiguous" in snapshot.reason
    assert snapshot.sync_state is None
    assert not transport.message_queries
    assert isinstance(provider.read_live_messages(["m0"])["m0"], LiveLookupError)


@pytest.mark.parametrize(
    ("entry", "allowed"),
    [
        ({"active_scope": ["INBOX", "Projects"], "labels": []}, False),
        ({"active_scope": ["INBOX"], "labels": ["Projects"]}, True),
        ({"labels": ["Projects"]}, False),
        ({"labels": []}, True),
        ({"active_scope": None}, True),
        ({}, True),
    ],
)
def test_saved_scope_check_only_excludes_confirmed_label_membership(entry, allowed):
    provider = provider_for(GmailTransport(0), active_exclude_labels=["Projects"])
    assert provider.live_entry_in_scope(entry) is allowed


def test_failed_scoped_metadata_keeps_state_for_caller_without_marking_complete():
    transport = GmailTransport(2)
    transport.messages["m0"]["labelIds"] = ["INBOX"]
    transport.messages["m1"]["labelIds"] = ["DRAFT"]
    transport.errors["m0"] = 429
    provider = provider_for(transport)
    provider.get_new_message_ids = MagicMock(return_value=([], "next"))
    snapshot = provider.list_live_messages(incremental=True)
    assert not snapshot.complete
    assert snapshot.sync_state == "next"
    assert [message.message_id for message in snapshot.messages] == ["m1"]


def test_incremental_scope_interrupt_propagates():
    provider = provider_for(GmailTransport(1))
    provider.get_new_message_ids = MagicMock(side_effect=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        provider.list_live_messages(incremental=True)
