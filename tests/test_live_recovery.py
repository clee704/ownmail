"""Saved lifecycle provenance survives missing indexes and interrupted capture."""

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ownmail import roles, sidecar
from ownmail.active_search import capture_id
from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase
from tests.test_live_sync import MailServer, message, owned_rows, sync


def test_gmail_filing_hands_off_a_cached_copy_without_sent(tmp_path):
    """Exercise the provider-to-storage handoff using actual Gmail label parsing."""
    from tests.test_live_providers import RAW, gmail

    archive = EmailArchive(tmp_path / "archive")
    provider = gmail(["INBOX", "Label_1"])
    assert archive.backup(provider, active_downloads=True)["active_refreshed"] == 1
    assert owned_rows(archive) == []
    cached_id = archive.active_cache().list_entries()[0]["id"]

    provider._service.users().messages().get().execute.return_value["labelIds"] = ["Label_1"]
    result = archive.backup(provider, active_downloads=True)

    assert result["success_count"] == 1
    assert result["error_count"] == 0
    email_id, filename = owned_rows(archive)[0]
    assert (archive.archive_dir / filename).read_bytes() == RAW
    assert sidecar.read_labels(archive.archive_dir / filename) == ["Projects"]
    assert archive.active_cache().get(cached_id) is None
    assert [row[0] for row in archive.search("is:archived")] == [email_id]
    assert archive.backup(provider, active_downloads=True)["success_count"] == 0


def test_gmail_filed_listing_cannot_override_fresh_unfinished_state(tmp_path):
    from tests.test_live_providers import gmail

    archive = EmailArchive(tmp_path / "archive")
    provider = gmail(["Label_1"])
    filed = dict(provider._service.users().messages().get().execute.return_value)
    draft = {**filed, "labelIds": ["DRAFT", "Label_1"]}
    provider._service.users().messages().get().execute.side_effect = [filed, draft]

    result = archive.backup(provider, active_downloads=True)

    assert result["success_count"] == 0
    assert result["active_refreshed"] == 1
    assert owned_rows(archive) == []
    assert archive.active_cache().list_entries()[0]["state"] == "active"


def test_gmail_catalog_not_found_retains_cached_mail_until_capture_retry(tmp_path):
    from types import SimpleNamespace

    from googleapiclient.errors import HttpError

    from tests.test_live_providers import RAW, gmail

    archive = EmailArchive(tmp_path / "archive")
    provider = gmail(["INBOX", "Label_1"])
    archive.backup(provider, active_downloads=True)
    cached = archive.active_cache().list_entries()[0]

    provider._service.users().messages().get().execute.return_value["labelIds"] = ["Label_1"]
    catalog = provider._service.users().labels().list().execute
    catalog.side_effect = [catalog.return_value, HttpError(SimpleNamespace(status=404, reason="not found"), b"{}")]
    failed = archive.backup(provider, active_downloads=True)

    assert failed["error_count"] == 1
    assert failed["success_count"] == 0
    assert not failed["active_complete"]
    assert archive.active_cache().get(cached["id"]) == cached
    assert archive.active_cache().read(cached["id"]) == RAW
    assert owned_rows(archive) == []

    catalog.side_effect = None
    retried = archive.backup(provider, active_downloads=True)
    assert retried["success_count"] == 1
    assert retried["active_complete"]
    assert archive.active_cache().get(cached["id"]) is None
    email_id, filename = owned_rows(archive)[0]
    assert (archive.archive_dir / filename).read_bytes() == RAW
    assert archive.db.get_labels_for_email(email_id) == ["Projects"]


@pytest.fixture
def archive(tmp_path):
    return EmailArchive(tmp_path / "archive")


def leave_unindexed_capture(archive, monkeypatch, *, raw=None):
    active = message(raw=raw)
    server = MailServer([active])
    sync(archive, server)
    server.messages[active.message_id] = replace(
        active, state="eligible", roles=frozenset({roles.SENT}), labels=("Saved snapshot",)
    )

    def fail_index(*args, **kwargs):
        raise sqlite3.OperationalError("Synthetic index failure")

    with monkeypatch.context() as patched:
        patched.setattr(archive.db, "index_email", fail_index)
        failed = sync(archive, server)
    assert failed["error_count"] == 1
    assert owned_rows(archive) == []
    files = list(archive.archive_dir.rglob("*.eml"))
    assert len(files) == 1
    return server, files[0]


@pytest.mark.parametrize("account_override", [None, "different@example.test"])
def test_scan_recovers_interrupted_capture_without_duplicate_identity(archive, monkeypatch, account_override):
    server, path = leave_unindexed_capture(archive, monkeypatch)
    before = path.read_bytes(), sidecar.sidecar_path(path).read_bytes()
    captured = server.messages["1"]
    expected_id = ArchiveDatabase.make_email_id(
        server.account, capture_id(server.source_name, server.account, captured.identity_token)
    )
    scanned = archive.scan_archive(account=account_override)
    assert scanned["imported_count"] == 1
    assert scanned["error_count"] == 0
    assert owned_rows(archive) == [(expected_id, str(path.relative_to(archive.archive_dir)))]
    with sqlite3.connect(archive.db.db_path) as conn:
        assert conn.execute("SELECT account FROM emails").fetchall() == [(server.account,)]
    assert archive.db.get_labels_for_email(expected_id) == ["Saved snapshot"]

    server.messages["1"] = replace(captured, labels=("Later server edit",))
    assert sync(archive, server)["success_count"] == 0
    assert archive.active_count() == 0
    assert owned_rows(archive) == [(expected_id, str(path.relative_to(archive.archive_dir)))]
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before
    assert archive.db.get_labels_for_email(expected_id) == ["Saved snapshot"]
    assert [row[0] for row in archive.search("Body is:archived")] == [expected_id]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("source_name", "other"),
        ("account", None),
        ("identity", "different-identity"),
        ("content_hash", "0" * 64),
        ("labels_complete", False),
    ],
)
def test_scan_rejects_mismatched_or_incomplete_capture_provenance(archive, monkeypatch, key, value):
    _server, path = leave_unindexed_capture(archive, monkeypatch)
    metadata = sidecar.read_metadata(path)
    metadata["capture"][key] = value
    sidecar.write_metadata(path, metadata)
    before = path.read_bytes(), sidecar.sidecar_path(path).read_bytes()
    scanned = archive.scan_archive()
    assert scanned["error_count"] == 1
    assert scanned["imported_count"] == 0
    assert owned_rows(archive) == []
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before


@pytest.mark.parametrize("metadata_bytes", [b"{", b"[]", b'{"version": 1, "labels": [null]}'])
def test_scan_does_not_adopt_malformed_capture_sidecar(archive, monkeypatch, metadata_bytes):
    _server, path = leave_unindexed_capture(archive, monkeypatch)
    sidecar.sidecar_path(path).write_bytes(metadata_bytes)
    scanned = archive.scan_archive()
    assert scanned["error_count"] == 1
    assert scanned["imported_count"] == 0
    assert owned_rows(archive) == []
    assert sidecar.sidecar_path(path).read_bytes() == metadata_bytes


def test_scan_leaves_capture_without_saved_labels_retryable(archive, monkeypatch):
    active = message()
    server = MailServer([active])
    sync(archive, server)
    server.messages["1"] = replace(active, state="eligible", roles=frozenset({roles.SENT}), labels=("Saved",))

    def fail_metadata(*args, **kwargs):
        raise OSError("Synthetic metadata failure")

    with monkeypatch.context() as patched:
        patched.setattr(sidecar, "write_metadata", fail_metadata)
        assert sync(archive, server)["error_count"] == 1
    path = next(archive.archive_dir.rglob("*.eml"))
    assert path.name.startswith("capture-")
    assert not sidecar.sidecar_path(path).exists()
    scanned = archive.scan_archive()
    assert scanned["imported_count"] == 0
    assert scanned["error_count"] == 1
    assert owned_rows(archive) == []
    assert archive.active_count() == 1
    assert sync(archive, server)["success_count"] == 1
    assert len(owned_rows(archive)) == 1
    assert archive.active_count() == 0


@pytest.mark.parametrize("date_header", [b"", b"Date: unusable date\r\n"])
def test_undated_promotion_and_file_recovery_preserve_search_account_and_labels(archive, date_header):
    raw = (
        b"From: sender@example.test\r\nSubject: Undated correspondence\r\n"
        b"Message-ID: <undated@example.test>\r\n" + date_header + b"\r\nSearchable body"
    )
    active = message(raw=raw)
    server = MailServer([active])
    sync(archive, server)
    assert len(archive.search("Searchable is:active")) == 1
    before_capture = datetime.now(timezone.utc)
    server.messages["1"] = replace(active, state="eligible", roles=frozenset({roles.SENT}), labels=("Frozen",))
    assert sync(archive, server)["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename
    metadata = sidecar.read_metadata(path)
    captured_at = datetime.fromisoformat(metadata["captured_at"])
    assert captured_at.utcoffset().total_seconds() == 0
    assert before_capture <= captured_at <= datetime.now(timezone.utc)
    assert [row[0] for row in archive.search("Searchable is:archived")] == [email_id]
    assert archive.active_count() == 0
    with sqlite3.connect(archive.db.db_path) as conn:
        first_date = conn.execute("SELECT email_date FROM emails WHERE email_id = ?", (email_id,)).fetchone()[0]
        conn.execute("DELETE FROM emails")
    frozen = path.read_bytes(), sidecar.sidecar_path(path).read_bytes()

    assert archive.scan_archive()["imported_count"] == 1
    assert owned_rows(archive) == [(email_id, filename)]
    assert archive.db.get_labels_for_email(email_id) == ["Frozen"]
    assert [row[0] for row in archive.search("Searchable is:archived")] == [email_id]
    with sqlite3.connect(archive.db.db_path) as conn:
        restored = conn.execute("SELECT account, email_date FROM emails WHERE email_id = ?", (email_id,)).fetchone()
    assert restored == (server.account, first_date)
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == frozen
    assert sync(archive, server)["success_count"] == 0
    assert owned_rows(archive) == [(email_id, filename)]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("labels", [None]),
        ("labels", [""]),
        ("captured_at", None),
        ("captured_at", "invalid"),
        ("captured_at", "2026-09-14T12:00:00"),
    ],
)
def test_scan_rejects_malformed_saved_labels_or_capture_time(archive, monkeypatch, key, value):
    _server, path = leave_unindexed_capture(archive, monkeypatch)
    metadata = sidecar.read_metadata(path)
    metadata[key] = value
    sidecar.write_metadata(path, metadata)
    before = sidecar.sidecar_path(path).read_bytes()
    scanned = archive.scan_archive()
    assert scanned["error_count"] == 1
    assert scanned["imported_count"] == 0
    assert owned_rows(archive) == []
    assert sidecar.sidecar_path(path).read_bytes() == before


def test_scan_accepts_existing_external_filename_with_capture_word(archive):
    path = archive.archive_dir / "capture-message.eml"
    path.write_bytes(message().raw)
    scanned = archive.scan_archive()
    assert scanned["imported_count"] == 1
    assert scanned["error_count"] == 0
    assert len(owned_rows(archive)) == 1
