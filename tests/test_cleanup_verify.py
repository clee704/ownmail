"""Server cleanup requires current files and complete owned-capture evidence."""

import os
import sqlite3
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from ownmail import cleanup_verify, sidecar
from ownmail.archive import EmailArchive
from ownmail.cleanup_verify import CleanupHold, VerifiedCopy, iter_candidate_ids, verify_local
from tests.test_live_sync import MailServer, message, owned_rows, sync

SOURCE = {"name": "mail", "account": "reader@example.test", "type": "gmail_api"}


@pytest.fixture
def owned(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    server = MailServer([message("abc", state="eligible", identity="gmail:abc", labels=("Saved",))])
    assert sync(archive, server)["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    return archive, email_id, archive.archive_dir / filename


def update_index(archive, lookup_id, **updates):
    with sqlite3.connect(archive.db.db_path) as conn:
        for column, value in updates.items():
            conn.execute(f"UPDATE emails SET {column} = ? WHERE email_id = ?", (value, lookup_id))


def test_valid_copy_returns_frozen_remote_identity_and_local_labels(owned):
    archive, email_id, path = owned
    verified = verify_local(archive.archive_dir, SOURCE, email_id)
    assert verified == VerifiedCopy(
        email_id=email_id,
        filename=str(path.relative_to(archive.archive_dir)),
        source_name="mail",
        account="reader@example.test",
        provider_id="abc",
        identity="gmail:abc",
        content_hash=sidecar.read_metadata(path)["capture"]["content_hash"],
        labels=("Saved",),
    )
    with pytest.raises(FrozenInstanceError):
        verified.identity = "other"
    assert list(iter_candidate_ids(archive.archive_dir, SOURCE)) == [email_id]


def test_verification_and_traversal_do_not_mutate_files_or_initialize_storage(owned, monkeypatch):
    archive, email_id, path = owned
    before = {
        item.relative_to(archive.archive_dir): item.read_bytes()
        for item in archive.archive_dir.rglob("*")
        if item.is_file()
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("Cleanup must not initialize writable storage or credentials")

    monkeypatch.setattr("ownmail.archive.EmailArchive.__init__", forbidden)
    monkeypatch.setattr("ownmail.database.ArchiveDatabase.__init__", forbidden)
    monkeypatch.setattr("ownmail.keychain.KeychainStorage.__init__", forbidden)
    assert list(iter_candidate_ids(archive.archive_dir, SOURCE)) == [email_id]
    assert verify_local(archive.archive_dir, SOURCE, email_id).provider_id == "abc"
    after = {
        item.relative_to(archive.archive_dir): item.read_bytes()
        for item in archive.archive_dir.rglob("*")
        if item.is_file()
    }
    assert after == before


def test_external_index_path_is_read_without_creating_default_index(owned, tmp_path):
    archive, email_id, _ = owned
    external = tmp_path / "index with spaces & punctuation"
    external.mkdir()
    database = external / "ownmail.db"
    archive.db.db_path.rename(database)
    before = database.read_bytes()
    assert list(iter_candidate_ids(archive.archive_dir, SOURCE, db_path=database)) == [email_id]
    assert verify_local(archive.archive_dir, SOURCE, email_id, db_path=database).email_id == email_id
    assert not archive.db.db_path.exists()
    assert database.read_bytes() == before


def test_batches_filter_account_and_observe_changes_between_reads(owned, monkeypatch):
    archive, email_id, _ = owned
    monkeypatch.setattr(cleanup_verify, "_BATCH_SIZE", 2)
    with sqlite3.connect(archive.db.db_path) as conn:
        conn.execute("DELETE FROM emails")
        conn.executemany(
            "INSERT INTO emails(email_id, account) VALUES (?, ?)",
            [
                ("a", SOURCE["account"]),
                ("b", SOURCE["account"]),
                ("c", SOURCE["account"]),
                ("other", "other@example.test"),
            ],
        )
    candidates = iter_candidate_ids(archive.archive_dir, SOURCE)
    assert next(candidates) == "a"
    assert next(candidates) == "b"
    # This write must succeed while the generator is suspended and appear next batch.
    with sqlite3.connect(archive.db.db_path) as conn:
        conn.execute("DELETE FROM emails WHERE email_id = 'c'")
        conn.execute("INSERT INTO emails(email_id, account) VALUES ('d', ?)", (SOURCE["account"],))
    assert list(candidates) == ["d"]


@pytest.mark.parametrize("change", ["trash", "delete", "missing_file", "missing_sidecar", "changed_file", "active_id"])
def test_late_local_changes_are_held_on_reverification(owned, change):
    archive, email_id, path = owned
    assert verify_local(archive.archive_dir, SOURCE, email_id)
    if change == "trash":
        archive.trash_email(email_id)
    elif change == "delete":
        archive.permanently_delete_emails([email_id])
    elif change == "missing_file":
        path.unlink()
    elif change == "missing_sidecar":
        sidecar.sidecar_path(path).unlink()
    elif change == "changed_file":
        path.write_bytes(path.read_bytes() + b"\nChanged locally")
    else:
        email_id = "active-" + "0" * 64
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)


@pytest.mark.parametrize("labels", [[], ["Local", "Contains, comma"], ["INBOX", "DRAFT"]])
def test_owned_label_edits_do_not_redefine_server_eligibility(owned, labels):
    archive, email_id, _ = owned
    original = verify_local(archive.archive_dir, SOURCE, email_id)
    assert archive.set_local_labels(email_id, labels)
    current = verify_local(archive.archive_dir, SOURCE, email_id)
    assert current == replace(original, labels=tuple(labels))


@pytest.mark.parametrize("labels", [[], ["Saved"], ["INBOX"]])
def test_legacy_label_sidecar_cannot_prove_capture_completeness(owned, labels):
    archive, email_id, path = owned
    legacy = path.with_name("legacy.eml")
    path.rename(legacy)
    sidecar.sidecar_path(path).unlink()
    sidecar.write_labels(legacy, labels)
    update_index(archive, email_id, filename=str(legacy.relative_to(archive.archive_dir)))
    with pytest.raises(CleanupHold, match="Legacy capture completeness"):
        verify_local(archive.archive_dir, SOURCE, email_id)


@pytest.mark.parametrize("change", [{"name": "other"}, {"account": "other@example.test"}])
def test_scope_mismatch_cannot_authorize_another_copy(owned, change):
    archive, email_id, _ = owned
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE | change, email_id)


def test_same_remote_identity_remains_scoped_to_source_and_account(owned):
    archive, first_id, _ = owned
    copies = []
    for source in (SOURCE | {"name": "other"}, SOURCE | {"account": "other@example.test"}):
        server = MailServer(
            [message("abc", state="eligible", identity="gmail:abc")],
            source_name=source["name"],
            account=source["account"],
        )
        assert sync(archive, server)["success_count"] == 1
        for email_id in iter_candidate_ids(archive.archive_dir, source):
            try:
                copies.append(verify_local(archive.archive_dir, source, email_id))
            except CleanupHold:
                pass
    assert len(copies) == 2
    assert first_id not in {copy.email_id for copy in copies}
    assert {(copy.source_name, copy.account) for copy in copies} == {
        ("other", "reader@example.test"),
        ("mail", "other@example.test"),
    }


@pytest.mark.parametrize(
    "updates",
    [
        {"provider_id": "other"},
        {"content_hash": "0" * 64},
        {"email_id": "other"},
        {"original_filename": "sources/mail/old.eml"},
    ],
)
def test_index_identity_hash_and_trash_disagreement_are_held(owned, updates):
    archive, email_id, _ = owned
    update_index(archive, email_id, **updates)
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, updates.get("email_id", email_id))


@pytest.mark.parametrize(
    "field,value",
    [
        ("labels_complete", False),
        ("labels_complete", 1),
        ("identity", "other"),
        ("provider_id", None),
        ("source_name", "other"),
        ("account", "other@example.test"),
        ("content_hash", "0" * 64),
    ],
)
def test_mismatched_capture_provenance_cannot_authorize_cleanup(owned, field, value):
    archive, email_id, path = owned
    metadata = sidecar.read_metadata(path)
    metadata["capture"][field] = value
    sidecar.write_metadata(path, metadata)
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)


@pytest.mark.parametrize("body", [b"{", b"[]", b'{"labels": ["Saved"]}', b'{"capture": []}', b"\xff"])
def test_malformed_or_incomplete_sidecar_is_held(owned, body):
    archive, email_id, path = owned
    sidecar.sidecar_path(path).write_bytes(body)
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("labels", [None]),
        ("labels", "Saved"),
        ("labels", [""]),
        ("captured_at", "invalid"),
        ("captured_at", "2026-09-14T12:00:00"),
    ],
)
def test_invalid_labels_or_capture_time_are_held(owned, field, value):
    archive, email_id, path = owned
    metadata = sidecar.read_metadata(path)
    metadata[field] = value
    sidecar.write_metadata(path, metadata)
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)


@pytest.mark.parametrize(
    "filename",
    [
        "../outside.eml",
        "/outside.eml",
        "sources/mail/../../outside.eml",
        "trash/copy.eml",
        "sources/other/copy.eml",
        "sources/mail/copy.txt",
        "",
        None,
    ],
)
def test_unsafe_or_missing_indexed_paths_are_held(owned, filename):
    archive, email_id, _ = owned
    update_index(archive, email_id, filename=filename)
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)


@pytest.mark.parametrize("target", ["message", "sidecar", "database"])
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory"])
def test_linked_or_nonregular_files_are_held_without_reading_target(owned, tmp_path, target, kind):
    archive, email_id, path = owned
    path = {"message": path, "sidecar": sidecar.sidecar_path(path), "database": archive.db.db_path}[target]
    external = tmp_path / "external"
    path.rename(external)
    before = external.read_bytes()
    if kind == "symlink":
        path.symlink_to(external)
    elif kind == "hardlink":
        os.link(external, path)
    else:
        path.mkdir()
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)
    if target == "database":
        with pytest.raises(CleanupHold):
            list(iter_candidate_ids(archive.archive_dir, SOURCE))
    assert external.read_bytes() == before


def test_linked_source_directory_is_held(owned, tmp_path):
    archive, email_id, path = owned
    source = archive.get_emails_dir("mail")
    external = tmp_path / "external-source"
    source.rename(external)
    source.symlink_to(external, target_is_directory=True)
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)
    assert (external / path.relative_to(source)).exists()


@pytest.mark.parametrize("damage", ["missing", "corrupt", "old_schema"])
def test_unavailable_index_is_held_without_creation_or_migration(owned, damage):
    archive, email_id, _ = owned
    index = archive.db.db_path
    if damage == "missing":
        index.unlink()
    elif damage == "corrupt":
        index.write_bytes(b"broken index")
    else:
        with sqlite3.connect(index) as conn:
            conn.execute("ALTER TABLE emails RENAME TO old_emails")
    before = index.read_bytes() if index.exists() else None
    with pytest.raises(CleanupHold):
        list(iter_candidate_ids(archive.archive_dir, SOURCE))
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, SOURCE, email_id)
    assert (index.read_bytes() if index.exists() else None) == before


@pytest.mark.parametrize(
    "source", [SOURCE | {"name": ".."}, SOURCE | {"name": "a/b"}, SOURCE | {"name": None}, SOURCE | {"account": ""}]
)
def test_invalid_source_is_held(owned, source):
    archive, email_id, _ = owned
    with pytest.raises(CleanupHold):
        list(iter_candidate_ids(archive.archive_dir, source))
    with pytest.raises(CleanupHold):
        verify_local(archive.archive_dir, source, email_id)


def test_missing_archive_is_held_without_creating_it(tmp_path):
    root = tmp_path / "missing"
    with pytest.raises(CleanupHold):
        list(iter_candidate_ids(root, SOURCE))
    with pytest.raises(CleanupHold):
        verify_local(root, SOURCE, "missing")
    assert not root.exists()


def test_whitespace_labels_are_malformed_capture_evidence(owned):
    archive, email_id, path = owned
    metadata = sidecar.read_metadata(path)
    metadata["labels"] = [" "]
    sidecar.write_metadata(path, metadata)
    with pytest.raises(CleanupHold, match="labels are malformed"):
        verify_local(archive.archive_dir, SOURCE, email_id)


def test_file_replacement_during_read_is_held(owned, monkeypatch):
    archive, email_id, path = owned
    open_file = os.open

    def replace_before_open(candidate, flags, *args, **kwargs):
        if candidate == path:
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(path.read_bytes())
            replacement.replace(path)
        return open_file(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(cleanup_verify.os, "open", replace_before_open)
    with pytest.raises(CleanupHold, match="changed while opening"):
        verify_local(archive.archive_dir, SOURCE, email_id)


def test_direct_index_connections_are_read_only(owned, monkeypatch):
    archive, email_id, _ = owned
    connect = sqlite3.connect
    attempted = []

    def checked_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM emails")
        attempted.append(True)
        return conn

    monkeypatch.setattr(cleanup_verify.sqlite3, "connect", checked_connect)
    assert list(iter_candidate_ids(archive.archive_dir, SOURCE)) == [email_id]
    assert verify_local(archive.archive_dir, SOURCE, email_id).email_id == email_id
    assert len(attempted) >= 2


def test_relative_configured_index_with_parent_components_is_readable(owned, tmp_path, monkeypatch):
    archive, email_id, _ = owned
    external = tmp_path / "index"
    external.mkdir()
    archive.db.db_path.rename(external / "ownmail.db")
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    configured = Path("../index/ownmail.db")
    assert list(iter_candidate_ids(archive.archive_dir, SOURCE, db_path=configured)) == [email_id]
    assert verify_local(archive.archive_dir, SOURCE, email_id, db_path=configured).email_id == email_id
    assert not archive.db.db_path.exists()


def test_symlinked_index_directory_is_held(owned, tmp_path):
    archive, email_id, _ = owned
    external = tmp_path / "index"
    external.mkdir()
    archive.db.db_path.rename(external / "ownmail.db")
    alias = tmp_path / "linked-index"
    alias.symlink_to(external, target_is_directory=True)
    configured = alias / "ownmail.db"
    with pytest.raises(CleanupHold):
        list(iter_candidate_ids(archive.archive_dir, SOURCE, db_path=configured))
    with pytest.raises(CleanupHold, match="symbolic links"):
        verify_local(archive.archive_dir, SOURCE, email_id, db_path=configured)
