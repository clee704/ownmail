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
