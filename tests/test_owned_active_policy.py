"""Owned messages never need a second live copy after ownership is verified."""

from dataclasses import replace

import pytest

from ownmail import sidecar
from ownmail.archive import EmailArchive
from tests.test_live_sync import (
    MailServer,
    cache_message,
    message,
    owned_rows,
    sync,
)


@pytest.fixture
def archive(tmp_path):
    return EmailArchive(tmp_path / "archive")


@pytest.mark.parametrize("listing", ["partial", "failed", "excluded", "omitted"])
def test_existing_owned_cache_is_retired_using_local_evidence(archive, listing):
    owned = message("owned", state="eligible", labels=("Saved",))
    live = message("live")
    server = MailServer([owned, live])
    sync(archive, server)
    path = archive.archive_dir / owned_rows(archive)[0][1]
    frozen = path.read_bytes(), sidecar.sidecar_path(path).read_bytes()
    returned = replace(owned, state="active", raw=owned.raw + b"\nServer edit")
    cache_message(archive, server, returned)
    server.messages["owned"] = returned
    server.reads.clear()
    if listing == "partial":
        server.complete = False
    elif listing == "failed":
        server.list_error = RuntimeError("Listing unavailable")
    elif listing == "excluded":
        server.messages["owned"] = replace(returned, download_allowed=False, active_allowed=False)
        server.live_entry_in_scope = lambda entry: entry["provider_id"] != "owned"
    else:
        server.listed = []
    sync(archive, server)
    entries = archive.active_cache().list_entries()
    assert [entry["identity"] for entry in entries] == [live.identity_token]
    assert "owned" not in server.reads
    assert len(list(archive.active_cache().cache_dir.joinpath("messages").glob("*.eml"))) == 1
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == frozen


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_unverified_owned_file_cannot_authorize_cache_removal(archive, damage):
    original = message(state="eligible")
    server = MailServer([original])
    sync(archive, server)
    path = archive.archive_dir / owned_rows(archive)[0][1]
    returned = replace(original, state="active")
    cache_message(archive, server, returned)
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"Damaged local contents")
    server.list_error = RuntimeError("Listing unavailable")
    result = sync(archive, server)
    assert not result["active_complete"]
    (entry,) = archive.active_cache().list_entries()
    assert archive.active_cache().read(entry["id"]) == original.raw


def test_new_folder_identity_with_owned_contents_does_not_create_active_copy(archive):
    original = message("filed", state="eligible", identity="folder:archive:1")
    server = MailServer([original])
    sync(archive, server)
    server.messages = {"inbox": replace(original, message_id="inbox", identity_token="folder:inbox:9", state="active")}
    server.reads.clear()
    result = sync(archive, server)
    assert result["active_complete"] and result["active_refreshed"] == 0
    assert server.reads == ["inbox"]
    assert archive.active_cache().list_entries() == []
    assert len(owned_rows(archive)) == 1


@pytest.mark.parametrize("scope", ["source", "account"])
def test_other_source_or_account_remains_active_despite_matching_owned_content(archive, scope):
    original = message(state="eligible")
    first = MailServer([original])
    sync(archive, first)
    second = MailServer(
        [replace(original, state="active")],
        source_name="other" if scope == "source" else first.source_name,
        account="other@example.test" if scope == "account" else first.account,
    )
    assert sync(archive, second)["active_refreshed"] == 1
    assert sync(archive, second)["active_refreshed"] == 1
    (entry,) = archive.active_cache().list_entries()
    assert (entry["source_name"], entry["account"]) == (second.source_name, second.account)


def test_omitted_cached_identity_can_be_retired_after_fresh_owned_content_match(archive):
    original = message("filed", state="eligible")
    server = MailServer([original])
    sync(archive, server)
    returned = message("returned", raw=original.raw)
    cache_message(archive, server, replace(returned, raw=original.raw + b"Different earlier live version"))
    server.messages = {returned.message_id: returned}
    server.listed = []
    result = sync(archive, server)
    assert result["active_complete"] and result["active_refreshed"] == 0
    assert archive.active_cache().list_entries() == []


@pytest.mark.parametrize("provider_id", ["legacy", "scoped"])
def test_database_id_without_provenance_cannot_freeze_a_different_live_copy(archive, provider_id):
    original = message(state="eligible")
    server = MailServer([original])
    sync(archive, server)
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename
    sidecar.write_labels(path, ["Legacy labels"])
    if provider_id == "legacy":
        import sqlite3

        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET provider_id = ? WHERE email_id = ?", (original.message_id, email_id))
    cache_message(archive, server, replace(original, state="active", raw=original.raw + b"Earlier server edit"))
    current = replace(original, state="active", raw=original.raw + b"Current server edit")
    server.messages = {current.message_id: current}
    server.reads.clear()
    result = sync(archive, server)
    assert result["active_complete"] and result["active_refreshed"] == 1
    assert server.reads == [current.message_id]
    (entry,) = archive.active_cache().list_entries()
    assert archive.active_cache().read(entry["id"]) == current.raw
    assert path.read_bytes() == original.raw
