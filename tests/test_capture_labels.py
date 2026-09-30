"""Configured label inheritance never becomes message selection or a rewrite."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from ownmail import reconcile, sidecar
from ownmail.archive import EmailArchive
from ownmail.commands import cmd_reconcile
from ownmail.config import validate_config
from tests.test_active_scope_config import config
from tests.test_live_gmail_batch import GmailTransport, provider_for
from tests.test_live_providers import RAW, gmail, imap
from tests.test_live_scope import IncrementalServer, saved_state, seed_state
from tests.test_live_sync import message, owned_rows, sync


@pytest.mark.parametrize("kind", ["gmail_api", "imap"])
@pytest.mark.parametrize("value", [None, "Waiting", {}, [1], [""], [" "]])
def test_capture_exclusions_require_a_list_of_nonblank_strings(kind, value):
    assert validate_config(config(kind, exclude_labels=value)) == [
        "Source 'mail': exclude_labels must be a list of nonempty names"
    ]


@pytest.mark.parametrize("kind", ["gmail_api", "imap"])
def test_capture_exclusions_accept_literal_names_without_query_restrictions(kind):
    names = ['Receipts, "taxes"', "Waiting\\Later", "保管", " spaced ", "CATEGORY_*", "A\tB"]
    configured = config(kind, exclude_labels=names)
    assert validate_config(configured) == []
    assert configured["sources"][0]["exclude_labels"] == names


def configured_archive(tmp_path, provider, exclusions, *, kind="gmail_api"):
    settings = config(kind)
    source = settings["sources"][0]
    source.update(name=provider.source_name, account=provider.account)
    if exclusions is not None:
        source["exclude_labels"] = exclusions
    return EmailArchive(tmp_path / "archive", settings)


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("include_labels", [False, True])
@pytest.mark.parametrize("excluded", [None, [], ["Waiting"], ["Waiting", "CATEGORY_UPDATES"]])
def test_gmail_capture_preserves_defaults_status_filters_and_empty_snapshot(tmp_path, live, include_labels, excluded):
    provider = gmail(["Label_1", "CATEGORY_UPDATES", "UNREAD", "STARRED", "IMPORTANT"], include_labels=include_labels)
    provider.get_new_message_ids.return_value = (["a"], "next-cursor")
    catalog = provider._service.users().labels().list().execute.return_value["labels"]
    catalog[-1]["name"] = "Waiting"
    catalog.append({"id": "CATEGORY_UPDATES", "name": "CATEGORY_UPDATES", "type": "system"})
    archive = configured_archive(tmp_path, provider, excluded)

    result = archive.backup(provider, active_downloads=live)

    assert result["success_count"] == 1
    assert result["error_count"] == 0
    email_id, filename = owned_rows(archive)[0]
    expected = (
        [name for name in ["Waiting", "CATEGORY_UPDATES"] if name not in (excluded or [])] if include_labels else []
    )
    assert (archive.archive_dir / filename).read_bytes() == RAW
    assert sidecar.read_labels(archive.archive_dir / filename) == expected
    assert set(archive.db.get_labels_for_email(email_id)) == set(expected)
    archive._index_email(email_id, archive.archive_dir / filename)
    assert set(archive.db.get_labels_for_email(email_id)) == set(expected)
    saved = sidecar.sidecar_path(archive.archive_dir / filename).read_bytes()
    archive.config["sources"][0]["exclude_labels"] = ["Waiting", "CATEGORY_UPDATES"]
    assert archive.backup(provider, active_downloads=live)["success_count"] == 0
    assert sidecar.sidecar_path(archive.archive_dir / filename).read_bytes() == saved
    if not live:
        assert provider.get_new_message_ids.call_args.args == ("next-cursor",)


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("gmail_imap", [False, True])
def test_imap_capture_omits_labels_without_excluding_mail(tmp_path, live, gmail_imap):
    provider = imap("Waiting", gmail_labels=b'"Waiting" \\Starred \\Important' if gmail_imap else None)
    provider.get_new_message_ids = MagicMock(return_value=(["Waiting:1"], "next-cursor"))
    provider._folder_lookup = {"Waiting:1": ["Waiting", "Status"]}
    provider._status_folders = {"Status"}
    archive = configured_archive(tmp_path, provider, ["Waiting"], kind="imap")

    result = archive.backup(provider, active_downloads=live)

    assert result["success_count"] == 1
    assert result["error_count"] == 0
    email_id, filename = owned_rows(archive)[0]
    assert (archive.archive_dir / filename).read_bytes() == RAW
    assert sidecar.read_labels(archive.archive_dir / filename) == []
    assert archive.db.get_labels_for_email(email_id) == []
    assert all(command[2] is True for command in provider._conn.commands if command[0] == "select")


@pytest.mark.parametrize("label,state", [("CHAT", "unknown"), ("INBOX", "active"), ("TRASH", "discarded")])
def test_omitting_a_gmail_state_name_cannot_authorize_capture(tmp_path, label, state):
    provider = gmail([label])
    provider._service.users().labels().list().execute.return_value["labels"].append(
        {"id": "CHAT", "name": "CHAT", "type": "system"}
    )
    archive = configured_archive(tmp_path, provider, [label])
    assert provider.read_live_message("a").state == state

    result = sync(archive, provider)

    assert result["success_count"] == 0
    assert owned_rows(archive) == []
    cached = archive.active_cache().list_entries()
    assert len(cached) == int(state != "discarded")
    if cached:
        assert cached[0]["labels"] == [label]
        assert cached[0]["state"] == state


def test_literal_matching_and_source_isolation_at_live_capture(tmp_path):
    names = ['Receipts, "taxes"', "Waiting\\Later", "保管", " spaced ", "CATEGORY_*", "A\tB"]
    retained = ['receipts, "taxes"', "spaced", "CATEGORY_UPDATES", "Saved"]
    server = IncrementalServer([message(state="eligible", labels=names + retained)])
    archive = configured_archive(tmp_path, server, names, kind="imap")
    archive.config["sources"].insert(
        0, {"name": "other", "type": "imap", "account": server.account, "exclude_labels": retained}
    )

    assert sync(archive, server)["success_count"] == 1

    email_id, filename = owned_rows(archive)[0]
    assert sidecar.read_labels(archive.archive_dir / filename) == retained
    assert set(archive.db.get_labels_for_email(email_id)) == set(retained)


def test_setting_changes_preserve_saved_labels_and_incremental_cursor(tmp_path):
    server = IncrementalServer([message(state="eligible", labels=["Waiting", "Saved"])])
    archive = configured_archive(tmp_path, server, ["Waiting"], kind="imap")
    seed_state(archive, server)
    assert sync(archive, server)["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename
    assert sidecar.read_labels(path) == ["Saved"]
    archive.set_local_labels(email_id, ["Waiting", "Local"])
    saved_bytes = sidecar.sidecar_path(path).read_bytes()
    archive.config["sources"][0]["exclude_labels"] = ["Waiting", "Local", "Saved"]
    server.messages["2"] = message("2", state="eligible", labels=["Saved"])

    assert sync(archive, server)["success_count"] == 1

    assert server.states == ["old-cursor", "next-cursor"]
    assert saved_state(archive, server) == "next-cursor"
    assert sidecar.sidecar_path(path).read_bytes() == saved_bytes
    assert set(archive.db.get_labels_for_email(email_id)) == {"Waiting", "Local"}
    new_id, new_file = next(row for row in owned_rows(archive) if row[0] != email_id)
    assert sidecar.read_labels(archive.archive_dir / new_file) == []
    assert archive.db.get_labels_for_email(new_id) == []


def test_index_retry_preserves_the_first_filtered_sidecar(tmp_path, monkeypatch):
    server = IncrementalServer([message(state="eligible", labels=["Waiting", "Saved"])])
    archive = configured_archive(tmp_path, server, ["Waiting"], kind="imap")
    seed_state(archive, server)
    with monkeypatch.context() as patch:
        patch.setattr(archive.db, "index_email", MagicMock(side_effect=OSError("synthetic index unavailable")))
        assert sync(archive, server)["error_count"] == 1
    assert saved_state(archive, server) == "old-cursor"
    path = next(archive.archive_dir.rglob("*.eml"))
    first = sidecar.sidecar_path(path).read_bytes()
    assert sidecar.read_labels(path) == ["Saved"]
    archive.config["sources"][0]["exclude_labels"] = ["Saved"]
    server.messages["1"] = replace(server.messages["1"], labels=("Later",))

    assert sync(archive, server)["success_count"] == 1

    assert sidecar.sidecar_path(path).read_bytes() == first
    assert archive.db.get_labels_for_email(owned_rows(archive)[0][0]) == ["Saved"]
    assert server.states == ["old-cursor", "old-cursor"]


@pytest.mark.parametrize("excluded,should_sweep", [([], False), (["Waiting"], True)])
def test_reconcile_preview_uses_only_the_labels_actually_retained(tmp_path, excluded, should_sweep):
    server = IncrementalServer([message(state="eligible", labels=["Saved", "Waiting"])])
    archive = configured_archive(tmp_path, server, excluded, kind="imap")
    assert sync(archive, server)["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename
    before = (path.read_bytes(), sidecar.sidecar_path(path).read_bytes())
    archive.config["sources"][0]["exclude_folders"] = ["Saved"]

    preview = reconcile.build_plan(archive.db.db_path, archive.config)
    cmd_reconcile(archive)

    assert [item.email_id for item in preview.sweep] == ([email_id] if should_sweep else [])
    assert [item.email_id for item in preview.reported] == ([] if should_sweep else [email_id])
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before
    assert archive.db.get_trash_count() == 0


def test_gmail_option_change_keeps_history_cursor_without_backfill(tmp_path):
    transport = GmailTransport(1)
    provider = provider_for(transport)
    archive = configured_archive(tmp_path, provider, [])
    assert sync(archive, provider)["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename
    before = (path.read_bytes(), sidecar.sidecar_path(path).read_bytes())
    cache = archive.active_cache()
    original = cache.source_status(provider.source_name, provider.account)
    archive.config["sources"][0]["exclude_labels"] = ["Projects"]
    transport.requests.clear()
    transport.batch_formats.clear()

    assert sync(archive, provider)["success_count"] == 0

    current = cache.source_status(provider.source_name, provider.account)
    assert current["capture_state"] == original["capture_state"]
    assert current["capture_scope_signature"] == original["capture_scope_signature"]
    assert transport.requests["GET", "/gmail/v1/users/me/history"] == 1
    assert transport.requests["GET", "/gmail/v1/users/me/profile"] == 0
    assert transport.batch_formats["raw"] == 0
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before
    assert archive.db.get_labels_for_email(email_id) == ["Projects"]


def test_exclusion_cannot_turn_failed_gmail_label_lookup_into_empty_capture(tmp_path):
    transport = GmailTransport(1)
    provider = provider_for(transport)
    archive = configured_archive(tmp_path, provider, ["Projects"])
    read = provider.read_live_messages

    def fail_content_catalog(message_ids):
        transport.catalog = {"labels": [{"id": "Label_1"}]}
        return read(message_ids)

    provider.read_live_messages = fail_content_catalog

    result = sync(archive, provider)

    assert result["error_count"] > 0
    assert result["success_count"] == 0
    assert owned_rows(archive) == []
    assert archive.active_cache().source_status(provider.source_name, provider.account)["capture_state"] is None
