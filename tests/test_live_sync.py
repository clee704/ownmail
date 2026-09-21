"""Lifecycle contracts across real Active cache and owned archive storage."""

import json
import sqlite3
from dataclasses import replace

import pytest

from ownmail import roles, sidecar
from ownmail.archive import EmailArchive
from ownmail.download_progress import DownloadProgress
from ownmail.live import LiveLookupError, LiveMessage, LiveSnapshot


class MailServer:
    """Expose controlled fresh observations without network access."""

    def __init__(self, messages=(), *, source_name="mail", account="reader@example.test"):
        self.source_name = source_name
        self.account = account
        self.messages = {message.message_id: message for message in messages}
        self.listed = None
        self.complete = True
        self.list_error = None
        self.reads = []
        self.exclude_roles = []

    def list_live_messages(self, *, on_progress=None):
        if self.list_error:
            raise self.list_error
        listed = self.listed if self.listed is not None else list(self.messages.values())
        if on_progress:
            on_progress(len(listed))
        return LiveSnapshot(
            self.source_name, self.account, listed, self.complete, None if self.complete else "Partial listing"
        )

    def read_live_message(self, message_id):
        self.reads.append(message_id)
        message = self.messages.get(message_id)
        if isinstance(message, BaseException):
            raise message
        return message


def message(message_id="1", *, state="active", identity=None, labels=None, current_roles=None, raw=None, **kwargs):
    if current_roles is None:
        current_roles = {
            "active": {roles.INBOX},
            "eligible": {roles.ARCHIVE},
            "discarded": {roles.TRASH},
            "unknown": set(),
        }[state]
    if raw is None:
        raw = f"Subject: Message {message_id}\nMessage-ID: <{message_id}@example.test>\nFrom: sender@example.test\nDate: Mon, 01 Jan 2024 12:00:00 +0000\n\nBody {message_id}".encode()
    return LiveMessage(
        message_id,
        labels=("INBOX",) if labels is None else tuple(labels),
        roles=frozenset(current_roles),
        state=state,
        identity_token=identity or f"epoch:10:{message_id}",
        raw=raw,
        **kwargs,
    )


@pytest.fixture
def archive(tmp_path):
    return EmailArchive(tmp_path / "archive")


def sync(archive, server, **kwargs):
    return archive.backup(server, active_downloads=True, **kwargs)


def owned_rows(archive):
    with sqlite3.connect(archive.db.db_path) as conn:
        return conn.execute("SELECT email_id, filename FROM emails ORDER BY email_id").fetchall()


def source_status(archive, server):
    return archive.active_cache().source_status(server.source_name, server.account)


def test_active_handoff_captures_one_owned_snapshot(archive):
    active = message()
    server = MailServer([active])
    initial = sync(archive, server)
    assert initial["active_refreshed"] == 1
    assert initial["success_count"] == 0
    assert owned_rows(archive) == []
    assert archive.active_cache().read(archive.active_cache().list_entries()[0]["id"]) == active.raw
    assert len(archive.search("Body is:active")) == 1

    server.messages["1"] = replace(active, state="eligible", roles=frozenset({roles.ARCHIVE}), labels=("Saved",))
    captured = sync(archive, server)
    assert captured["success_count"] == 1
    assert captured["active_complete"] is True
    assert archive.active_cache().list_entries() == []
    row = owned_rows(archive)[0]
    assert (archive.archive_dir / row[1]).read_bytes() == active.raw
    assert archive.db.get_labels_for_email(row[0]) == ["Saved"]
    assert [result[0] for result in archive.search("Body")] == [row[0]]
    assert sync(archive, server)["success_count"] == 0
    assert owned_rows(archive) == [row]


def test_returned_inbox_preserves_owned_bytes_labels_and_one_result(archive):
    original = message(state="eligible", labels=("Saved",))
    server = MailServer([original])
    sync(archive, server)
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename
    before = (path.read_bytes(), sidecar.sidecar_path(path).read_bytes())
    server.messages["1"] = replace(
        original, state="active", roles=frozenset({roles.INBOX}), labels=("INBOX", "Changed")
    )
    refreshed = sync(archive, server)
    assert refreshed["success_count"] == 0
    assert refreshed["active_refreshed"] == 1
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before
    assert archive.db.get_labels_for_email(email_id) == ["Saved"]
    assert [row[0] for row in archive.search("Body")] == [email_id]
    assert [row[0] for row in archive.search("is:active")] == [email_id]
    assert archive.active_info(email_id)["archived"] is True
    assert archive.consolidated_count() == 1


def test_returned_inbox_edit_does_not_replace_owned_copy_or_duplicate_identity(archive):
    original = message(state="eligible", labels=("Saved",))
    server = MailServer([original])
    sync(archive, server)
    email_id, filename = owned_rows(archive)[0]
    server.messages["1"] = replace(
        original, state="active", roles=frozenset({roles.INBOX}), raw=original.raw.replace(b"Body", b"Edited")
    )
    sync(archive, server)
    assert (archive.archive_dir / filename).read_bytes() == original.raw
    assert [row[0] for row in archive.search("")] == [email_id]
    assert archive.active_info(email_id)["archived"] is True


@pytest.mark.parametrize("failure_stage", ["metadata", "index"])
def test_capture_failure_keeps_active_copy_and_retries_once(archive, monkeypatch, failure_stage):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    cached_id = archive.active_cache().list_entries()[0]["id"]
    server.messages["1"] = replace(
        active, state="eligible", roles=frozenset({roles.ARCHIVE}), labels=("First saved label",)
    )

    def fail(*args, **kwargs):
        raise OSError("write unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(sidecar, "write_metadata", fail) if failure_stage == "metadata" else patch.setattr(
            archive.db, "index_email", fail
        )
        failed = sync(archive, server)
    assert failed["error_count"] == 1
    assert failed["success_count"] == 0
    assert failed["active_complete"] is False
    assert owned_rows(archive) == []
    assert archive.active_cache().read(cached_id) == active.raw

    server.messages["1"] = replace(server.messages["1"], labels=("Later server label",))
    retried = sync(archive, server)
    assert retried["success_count"] == 1
    assert retried["error_count"] == 0
    assert archive.active_cache().get(cached_id) is None
    rows = owned_rows(archive)
    assert len(rows) == 1
    expected_labels = ["First saved label"] if failure_stage == "index" else ["Later server label"]
    assert archive.db.get_labels_for_email(rows[0][0]) == expected_labels
    assert sidecar.read_labels(archive.archive_dir / rows[0][1]) == expected_labels
    assert len(list(archive.archive_dir.rglob("*.eml"))) == 1
    assert sync(archive, server)["success_count"] == 0


def test_raw_capture_write_failure_preserves_cache_until_retry(archive, monkeypatch):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    cached = archive.active_cache().list_entries()[0]
    server.messages["1"] = replace(active, state="eligible", roles=frozenset({roles.ARCHIVE}))

    def fail(*args, **kwargs):
        raise OSError("archive unavailable")

    with monkeypatch.context() as patch:
        patch.setattr("ownmail.live_sync.os.link", fail)
        failed = sync(archive, server)
    assert failed["error_count"] == 1
    assert owned_rows(archive) == []
    assert archive.active_cache().read(cached["id"]) == active.raw
    assert sync(archive, server)["success_count"] == 1


@pytest.mark.parametrize("failure_stage", ["metadata", "index"])
def test_active_storage_failure_marks_refresh_incomplete_and_retries(archive, monkeypatch, failure_stage):
    original = message()
    server = MailServer([original])
    sync(archive, server)
    cache = archive.active_cache()
    entry = cache.list_entries()[0]
    edited = replace(original, raw=original.raw.replace(b"Body", b"Updated"))
    server.messages["1"] = edited
    atomic = cache._atomic_write

    def fail_metadata(path, raw):
        if path.parent.name == "entries":
            raise OSError("metadata unavailable")
        return atomic(path, raw)

    def fail_index(*args, **kwargs):
        raise sqlite3.OperationalError("cache index unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(cache, "_atomic_write", fail_metadata) if failure_stage == "metadata" else patch.setattr(
            cache, "_index_entry", fail_index
        )
        failed = sync(archive, server)
    assert failed["error_count"] == 1
    assert source_status(archive, server)["complete"] is False
    assert cache.read(entry["id"]) == (original.raw if failure_stage == "metadata" else edited.raw)
    assert sync(archive, server)["active_complete"] is True
    assert cache.read(entry["id"]) == edited.raw
    assert len(archive.search("Updated")) == 1
    assert archive.search("Body") == []
    assert owned_rows(archive) == []


@pytest.mark.parametrize("failure", ["list", "partial", "lookup"])
def test_incomplete_observation_keeps_previous_cache_and_reports_stale(archive, failure):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    cached = archive.active_cache().list_entries()[0]
    before = source_status(archive, server)["completed_at"]
    server.listed = []
    server.messages = {}
    if failure == "list":
        server.list_error = ConnectionError("offline")
    elif failure == "partial":
        server.complete = False
    else:
        server.messages["1"] = LiveLookupError("state unavailable")
    result = sync(archive, server)
    assert result["active_complete"] is False
    assert archive.active_cache().read(cached["id"]) == active.raw
    assert source_status(archive, server)["completed_at"] == before


@pytest.mark.parametrize("cause", ["trash", "spam", "deleted"])
def test_confirmed_server_removal_clears_only_disposable_copy(archive, cause):
    original = message(state="eligible", labels=("Saved",))
    server = MailServer([original])
    sync(archive, server)
    row = owned_rows(archive)[0]
    path = archive.archive_dir / row[1]
    before = (path.read_bytes(), sidecar.sidecar_path(path).read_bytes())
    server.messages["1"] = replace(original, state="active", roles=frozenset({roles.INBOX}))
    sync(archive, server)
    assert archive.active_count() == 1
    if cause == "deleted":
        server.messages = {}
    else:
        server.messages["1"] = replace(original, state="discarded", roles=frozenset({cause}), raw=None)
    result = sync(archive, server)
    assert result["active_complete"] is True
    assert archive.active_count() == 0
    assert owned_rows(archive) == [row]
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before


def test_partial_listing_does_not_remove_even_observed_discarded_cache(archive):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    server.complete = False
    server.messages["1"] = replace(active, state="discarded", roles=frozenset({roles.TRASH}), raw=None)
    assert sync(archive, server)["active_complete"] is False
    assert archive.active_count() == 1


def test_another_message_failure_defers_cache_removal_until_complete_refresh(archive):
    first, second = message("1"), message("2")
    server = MailServer([first, second])
    sync(archive, server)
    server.listed = [first, second]
    server.messages = {"1": None, "2": LiveLookupError("unavailable")}
    assert sync(archive, server)["active_complete"] is False
    assert archive.active_count() == 2
    server.messages["2"] = second
    assert sync(archive, server)["active_complete"] is True
    assert archive.active_count() == 1


@pytest.mark.parametrize("role", [roles.INBOX, roles.DRAFTS])
@pytest.mark.parametrize("enabled", [True, False])
def test_download_preferences_never_make_unfinished_mail_owned(archive, role, enabled):
    active = message(current_roles={role}, labels=(role,))
    server = MailServer([active])
    server.exclude_roles = []
    result = archive.backup(server, active_downloads=enabled)
    assert result["success_count"] == 0
    assert owned_rows(archive) == []
    assert list(archive.archive_dir.rglob("*.eml")) == []
    assert archive.active_count() == int(enabled)
    assert result["active_complete"] is enabled


def test_active_disabled_still_captures_finished_mail(archive):
    server = MailServer([message(state="eligible", labels=("Saved",))])
    result = archive.backup(server, active_downloads=False)
    assert result["success_count"] == 1
    assert len(owned_rows(archive)) == 1
    assert archive.active_count() == 0
    assert result["active_complete"] is False


def test_unknown_state_is_readable_but_never_captured(archive):
    unknown = message(state="unknown", reason="Missing state metadata")
    server = MailServer([unknown])
    result = sync(archive, server)
    assert result["active_complete"] is False
    assert result["active_refreshed"] == 1
    assert owned_rows(archive) == []
    assert len(archive.search("Body is:active")) == 1
    assert "Missing state metadata" in source_status(archive, server)["error"]


def test_partial_snapshot_allows_independently_verified_capture(archive):
    server = MailServer([message(state="eligible")])
    server.complete = False
    result = sync(archive, server)
    assert result["success_count"] == 1
    assert len(owned_rows(archive)) == 1
    assert result["active_complete"] is False


@pytest.mark.parametrize("fresh", [message(state="unknown"), LiveLookupError("Candidate state unavailable")])
def test_partial_listing_never_substitutes_for_fresh_candidate_state(archive, fresh):
    server = MailServer([message(state="eligible")])
    server.listed = list(server.messages.values())
    server.messages["1"] = fresh
    server.complete = False
    result = sync(archive, server)
    assert result["success_count"] == 0
    assert owned_rows(archive) == []
    assert result["active_complete"] is False


@pytest.mark.parametrize("scope", ["source", "account"])
def test_same_remote_id_is_isolated_between_sources_and_accounts(archive, scope):
    original = message(state="eligible", labels=("Saved",))
    first = MailServer([original])
    second = MailServer(
        [original],
        source_name="other" if scope == "source" else "mail",
        account="other@example.test" if scope == "account" else "reader@example.test",
    )
    sync(archive, first)
    sync(archive, second)
    assert len(owned_rows(archive)) == 2
    first.messages["1"] = replace(original, state="active", roles=frozenset({roles.INBOX}))
    second.messages["1"] = replace(original, state="active", roles=frozenset({roles.INBOX}))
    sync(archive, first)
    sync(archive, second)
    assert archive.active_count() == 2
    assert archive.consolidated_count() == 2
    first.messages = {}
    sync(archive, first)
    remaining = archive.active_cache().list_entries()
    assert len(remaining) == 1
    assert remaining[0]["source_name"] == second.source_name
    assert remaining[0]["account"] == second.account


def test_uidvalidity_change_preserves_unverified_previous_identity(archive):
    old = message(identity="uidvalidity:10:1")
    server = MailServer([old])
    sync(archive, server)
    server.messages["1"] = message(identity="uidvalidity:11:1", raw=old.raw.replace(b"Body", b"Other"))
    result = sync(archive, server)
    assert result["active_complete"] is False
    assert {entry["identity"] for entry in archive.active_cache().list_entries()} == {
        "uidvalidity:10:1",
        "uidvalidity:11:1",
    }
    assert owned_rows(archive) == []


def test_identity_change_during_read_cannot_overwrite_previous_cache(archive):
    old = message()
    server = MailServer([old])
    sync(archive, server)
    server.listed = [old]
    server.messages["1"] = replace(old, identity_token="uidvalidity:11:1")
    result = sync(archive, server)
    assert result["error_count"] == 1
    assert archive.active_cache().list_entries()[0]["identity"] == old.identity_token
    assert archive.active_count() == 1


def test_interrupt_retains_completed_capture_and_retryable_remaining_mail(archive, tmp_path):
    first, second = message("1"), message("2")
    server = MailServer([first, second])
    sync(archive, server)
    finished_first = replace(first, state="eligible", roles=frozenset({roles.ARCHIVE}))
    finished_second = replace(second, state="eligible", roles=frozenset({roles.ARCHIVE}))
    server.listed = [finished_first, finished_second]
    server.messages = {"1": finished_first, "2": KeyboardInterrupt()}
    progress = DownloadProgress(tmp_path / "progress.json")
    result = sync(archive, server, progress=progress)
    assert result["interrupted"] is True
    assert result["active_complete"] is False
    assert result["success_count"] == 1
    assert len(owned_rows(archive)) == 1
    assert archive.consolidated_count() == 2
    state = json.loads(progress.path.read_text())
    assert state["downloaded"] == 1
    assert state["active_complete"] is False
    assert "interrupted" in state["failure_reason"].lower()
    server.messages["2"] = finished_second
    retried = sync(archive, server)
    assert retried["success_count"] == 1
    assert retried["active_complete"] is True
    assert len(owned_rows(archive)) == 2
    assert archive.active_count() == 0


@pytest.mark.parametrize("filters", [{"since": "2024-01-02"}, {"until": "2024-01-01"}])
def test_date_filter_keeps_eligible_mail_retryable_and_refresh_incomplete(archive, filters):
    server = MailServer([message(state="eligible")])
    result = sync(archive, server, **filters)
    assert result["success_count"] == 0
    assert result["active_complete"] is False
    assert archive.active_count() == 1
    assert owned_rows(archive) == []
    assert sync(archive, server)["success_count"] == 1


def test_unavailable_content_cannot_authorize_capture_or_evict_previous_copy(archive):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    server.messages["1"] = replace(active, state="eligible", roles=frozenset({roles.ARCHIVE}), raw=None)
    result = sync(archive, server)
    assert result["success_count"] == 0
    assert result["error_count"] == 1
    assert archive.active_count() == 1
    assert owned_rows(archive) == []


def test_excluded_folder_retains_cache_without_reading_or_capturing(archive):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    server.messages["1"] = replace(active, state="eligible", download_allowed=False)
    server.reads.clear()
    result = sync(archive, server)
    assert result["active_complete"] is False
    assert server.reads == []
    assert archive.active_count() == 1
    assert owned_rows(archive) == []


def test_changed_owned_file_is_preserved_and_capture_requires_repair(archive):
    original = message(state="eligible")
    server = MailServer([original])
    sync(archive, server)
    row = owned_rows(archive)[0]
    path = archive.archive_dir / row[1]
    changed = original.raw + b"\nLocal change"
    path.write_bytes(changed)
    result = sync(archive, server)
    assert result["success_count"] == 0
    assert result["error_count"] == 1
    assert result["active_complete"] is False
    assert path.read_bytes() == changed
    assert owned_rows(archive) == [row]


def test_local_trash_stays_owned_when_server_copy_returns(archive):
    original = message(state="eligible", labels=("Saved",))
    server = MailServer([original])
    sync(archive, server)
    email_id = owned_rows(archive)[0][0]
    assert archive.trash_email(email_id)
    row = archive.db.get_email_by_id(email_id)
    trashed = archive.archive_dir / row[1]
    saved = (trashed.read_bytes(), sidecar.sidecar_path(trashed).read_bytes())
    server.messages["1"] = replace(original, state="active", roles=frozenset({roles.INBOX}))
    sync(archive, server)
    assert archive.active_count() == 1
    assert len(archive.search("Body")) == 1
    assert archive.search("Body")[0][0].startswith("active-")
    server.messages["1"] = original
    assert sync(archive, server)["success_count"] == 0
    assert archive.active_count() == 0
    assert archive.db.get_email_by_id(email_id) == row
    assert (trashed.read_bytes(), sidecar.sidecar_path(trashed).read_bytes()) == saved


def test_incomplete_capture_with_malformed_sidecar_is_preserved_for_repair(archive, monkeypatch):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    server.messages["1"] = replace(active, state="eligible", roles=frozenset({roles.ARCHIVE}))

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("index unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(archive.db, "index_email", fail)
        assert sync(archive, server)["error_count"] == 1
    capture = next(archive.archive_dir.rglob("*.eml"))
    metadata = sidecar.sidecar_path(capture)
    metadata.write_text("{invalid")
    result = sync(archive, server)
    assert result["error_count"] == 1
    assert result["success_count"] == 0
    assert archive.active_count() == 1
    assert owned_rows(archive) == []
    assert metadata.read_text() == "{invalid"


def test_filtered_capture_includes_since_and_excludes_until(archive):
    server = MailServer([message(state="eligible")])
    result = sync(archive, server, since="2024-01-01", until="2024-01-02")
    assert result["success_count"] == 1
    assert len(owned_rows(archive)) == 1
    assert result["active_complete"] is False


def test_local_trash_in_one_source_does_not_suppress_another_source_capture(archive):
    original = message(state="eligible", labels=("Saved",))
    first = MailServer([original])
    sync(archive, first)
    trashed_id = owned_rows(archive)[0][0]
    assert archive.trash_email(trashed_id)
    trashed = archive.db.get_email_by_id(trashed_id)
    second = MailServer([original], source_name="other")
    result = sync(archive, second)
    assert result["success_count"] == 1
    assert len(owned_rows(archive)) == 2
    assert archive.db.get_email_by_id(trashed_id) == trashed
    visible = archive.search("Body")
    assert len(visible) == 1
    assert visible[0][0] != trashed_id
    assert visible[0][1].startswith("sources/other/")


def test_real_cached_mail_is_readable_in_web_and_rejects_local_label_edits(archive):
    from lxml import html

    from ownmail.web import create_app

    active = message()
    server = MailServer([active])
    sync(archive, server)
    cache = archive.active_cache()
    entry = cache.list_entries()[0]
    client = create_app(archive, display_timezone="UTC").test_client()
    response = client.get("/search?q=is%3Aactive")
    assert response.status_code == 200
    listing = html.fromstring(response.data)
    rows = listing.xpath('//ul[@id="ownmail-email-list"]/li')
    assert len(rows) == 1
    assert "ownmail-email-row-active" in rows[0].get("class")
    assert "Checked" in rows[0].text_content()
    reader = client.get(f"/email/{entry['id']}")
    assert reader.status_code == 200
    assert b"Body 1" in reader.data
    assert b"Manage this message in your mail client." in reader.data
    assert client.get(f"/download/{entry['id']}").data == active.raw
    assert client.post(f"/labels/{entry['id']}", json={"labels": ["Local edit"]}).status_code == 404
    assert cache.get(entry["id"])["labels"] == ["INBOX"]
    assert owned_rows(archive) == []


def test_real_owned_reader_links_to_edited_server_copy_with_distinct_contents(archive):
    from lxml import html

    from ownmail.web import create_app

    original = message(state="eligible", labels=("Saved",))
    server = MailServer([original])
    sync(archive, server)
    email_id = owned_rows(archive)[0][0]
    server.messages["1"] = replace(
        original, state="active", roles=frozenset({roles.INBOX}), raw=original.raw.replace(b"Body", b"Edited")
    )
    sync(archive, server)
    cached_id = archive.active_cache().list_entries()[0]["id"]
    client = create_app(archive, display_timezone="UTC").test_client()
    listing = html.fromstring(client.get("/search").data)
    assert len(listing.xpath('//ul[@id="ownmail-email-list"]/li')) == 1
    owned = html.fromstring(client.get(f"/email/{email_id}").data)
    live = html.fromstring(client.get(f"/email/{cached_id}").data)
    assert "Body 1" in owned.text_content()
    assert "Edited 1" not in owned.text_content()
    assert "Edited 1" in live.text_content()
    assert owned.xpath(f'//section[@aria-label="Active message status"]//a[starts-with(@href, "/email/{cached_id}")]')
    assert live.xpath(f'//section[@aria-label="Active message status"]//a[starts-with(@href, "/email/{email_id}")]')
    assert owned.xpath('//*[@id="ownmail-edit-labels"]')
    assert not live.xpath('//*[@id="ownmail-edit-labels"]')
