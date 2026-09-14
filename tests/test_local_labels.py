"""Local label edits preserve the sidecar through failures and maintenance."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

from ownmail import sidecar
from ownmail.archive import EmailArchive
from ownmail.commands import cmd_rebuild, cmd_update_labels
from ownmail.database import ArchiveDatabase


@pytest.fixture
def owned_message(tmp_path, sample_eml_simple):
    account = "reader@example.com"
    provider_id = "Filed:1"
    archive = EmailArchive(
        tmp_path / "archive",
        {"sources": [{"name": "mail", "type": "imap", "account": account}]},
    )
    provider = Mock()
    provider.name = "imap"
    provider.account = account
    provider.source_name = "mail"
    provider.get_new_message_ids.return_value = ([provider_id], "cursor")
    provider.download_message.return_value = (sample_eml_simple, ["Server"])
    assert archive.backup(provider)["success_count"] == 1
    email_id = ArchiveDatabase.make_email_id(account, provider_id)
    filepath = archive.archive_dir / archive.db.get_email_by_id(email_id)[1]
    sidecar.write_metadata(filepath, {"version": 1, "labels": ["Server"], "extra": {"preserved": True}})
    provider.reset_mock()
    return archive, email_id, filepath, provider


def test_edits_preserve_exact_labels_metadata_content_and_search(owned_message):
    archive, email_id, filepath, provider = owned_message
    raw = filepath.read_bytes()
    labels = ["Receipts, taxes", 'Notes "quoted"', "  spaced label  ", "Unread", "Receipts, taxes"]

    assert archive.set_local_labels(email_id, labels) is True

    expected = labels[:-1]
    assert archive.get_local_labels(email_id) == expected
    assert sidecar.read_metadata(filepath) == {"version": 1, "labels": expected, "extra": {"preserved": True}}
    assert set(archive.db.get_labels_for_email(email_id)) == set(expected)
    assert [row[0] for row in archive.search('label:"Receipts, taxes"')] == [email_id]
    assert archive.search("label:Server") == []
    with sqlite3.connect(archive.db.db_path) as conn:
        dates = conn.execute("SELECT DISTINCT email_date FROM email_labels").fetchall()
        assert dates == conn.execute("SELECT email_date FROM emails WHERE email_id = ?", (email_id,)).fetchall()
    assert filepath.read_bytes() == raw
    assert provider.mock_calls == []


def test_sidecar_wins_over_stale_index_and_empty_is_explicit(owned_message):
    archive, email_id, filepath, _provider = owned_message
    sidecar.write_metadata(filepath, {"version": 1, "labels": ["Local", "Local"]})
    assert archive.get_local_labels(email_id) == ["Local"]

    assert archive.set_local_labels(email_id, []) is True

    assert archive.get_local_labels(email_id) == []
    assert sidecar.read_labels(filepath) == []
    assert archive.db.get_labels_for_email(email_id) == []


def test_missing_sidecar_uses_database_until_first_edit(owned_message):
    archive, email_id, filepath, _provider = owned_message
    metadata_path = sidecar.sidecar_path(filepath)
    metadata_path.unlink()
    assert archive.get_local_labels(email_id) == ["Server"]
    assert not metadata_path.exists()

    assert archive.set_local_labels(email_id, ["Local"]) is True

    assert sidecar.read_metadata(filepath) == {"version": 1, "labels": ["Local"]}


@pytest.mark.parametrize("labels", [None, "Work", ("Work",), [None], [1], [""], [" \t"], ["UNREAD"]])
def test_invalid_labels_leave_sidecar_and_index_unchanged(owned_message, labels):
    archive, email_id, filepath, _provider = owned_message
    original = sidecar.sidecar_path(filepath).read_bytes()

    with pytest.raises(ValueError):
        archive.set_local_labels(email_id, labels)

    assert sidecar.sidecar_path(filepath).read_bytes() == original
    assert archive.db.get_labels_for_email(email_id) == ["Server"]


@pytest.mark.parametrize(
    "metadata", [b"{broken", b"\xff", b"null", b"[]", b"{}", b'{"labels":[1]}', b'{"labels":[" "]}']
)
def test_malformed_sidecar_cannot_be_replaced_with_database_labels(owned_message, metadata):
    archive, email_id, filepath, _provider = owned_message
    metadata_path = sidecar.sidecar_path(filepath)
    metadata_path.write_bytes(metadata)

    with pytest.raises(ValueError, match="metadata is unreadable or malformed"):
        archive.get_local_labels(email_id)
    with pytest.raises(ValueError, match="metadata is unreadable or malformed"):
        archive.set_local_labels(email_id, ["New"])

    assert metadata_path.read_bytes() == metadata
    assert archive.db.get_labels_for_email(email_id) == ["Server"]


@pytest.mark.parametrize("sidecar_kind", ["symlink", "dangling", "directory"])
def test_unsafe_sidecar_is_never_read_or_replaced(owned_message, tmp_path, monkeypatch, sidecar_kind):
    archive, email_id, filepath, _provider = owned_message
    metadata_path = sidecar.sidecar_path(filepath)
    metadata_path.unlink()
    target = tmp_path / "outside.json"
    if sidecar_kind == "directory":
        metadata_path.mkdir()
    else:
        if sidecar_kind == "symlink":
            target.write_text('{"labels": ["Private"]}')
        metadata_path.symlink_to(target)
    reader = Mock(side_effect=AssertionError("unsafe metadata was read"))
    monkeypatch.setattr(sidecar, "read_metadata", reader)

    with pytest.raises(ValueError, match="regular file in the archive"):
        archive.get_local_labels(email_id)
    with pytest.raises(ValueError, match="regular file in the archive"):
        archive.set_local_labels(email_id, ["New"])

    reader.assert_not_called()
    assert archive.db.get_labels_for_email(email_id) == ["Server"]
    if sidecar_kind == "directory":
        assert metadata_path.is_dir()
    else:
        assert metadata_path.is_symlink()
        if sidecar_kind == "symlink":
            assert target.read_text() == '{"labels": ["Private"]}'
        else:
            assert not target.exists()


@pytest.mark.parametrize(
    "file_kind", ["unknown", "missing", "outside", "outside_alias", "symlink", "directory", "loop", "null"]
)
def test_only_existing_owned_archive_files_can_be_edited(owned_message, tmp_path, file_kind):
    archive, email_id, filepath, _provider = owned_message
    original = sidecar.sidecar_path(filepath).read_bytes()
    if file_kind == "unknown":
        email_id = "active-only-message"
    elif file_kind == "null":
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET filename = NULL")
    elif file_kind in ("outside", "outside_alias"):
        outside = tmp_path / "external.eml"
        if file_kind == "outside_alias":
            outside.symlink_to(filepath)
        else:
            outside.write_bytes(filepath.read_bytes())
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET filename = ?", (str(outside),))
    else:
        raw = filepath.read_bytes()
        filepath.unlink()
        if file_kind == "directory":
            filepath.mkdir()
        elif file_kind == "symlink":
            outside = tmp_path / "external.eml"
            outside.write_bytes(raw)
            filepath.symlink_to(outside)
        elif file_kind == "loop":
            filepath.symlink_to(filepath)

    with pytest.raises(FileNotFoundError, match="Archived message file is unavailable"):
        archive.get_local_labels(email_id)
    with pytest.raises(FileNotFoundError, match="Archived message file is unavailable"):
        archive.set_local_labels(email_id, ["New"])

    assert sidecar.sidecar_path(filepath).read_bytes() == original


def test_scanned_email_symlink_edits_its_tracked_sidecar(owned_message, sample_eml_simple):
    archive, _email_id, _filepath, _provider = owned_message
    target = archive.archive_dir / "z-target.eml"
    target.write_bytes(sample_eml_simple.replace(b"test123@example.com", b"linked@example.com"))
    alias = archive.archive_dir / "a-alias.eml"
    alias.symlink_to(target)
    sidecar.write_metadata(alias, {"version": 1, "labels": ["Alias"], "extra": {"alias": True}})
    sidecar.write_metadata(target, {"version": 1, "labels": ["Target"]})
    target_metadata = sidecar.sidecar_path(target).read_bytes()
    raw = target.read_bytes()

    result = archive.scan_archive()

    assert result["imported_count"] == 1
    assert result["duplicate_count"] == 1
    email_id = archive.search("label:Alias")[0][0]
    assert archive.db.get_email_by_id(email_id)[1] == alias.name
    assert archive.get_local_labels(email_id) == ["Alias"]

    assert archive.set_local_labels(email_id, ["Edited alias"]) is True
    cmd_rebuild(archive, only="sidecars")

    assert archive.get_local_labels(email_id) == ["Edited alias"]
    assert archive.db.get_labels_for_email(email_id) == ["Edited alias"]
    assert sidecar.read_metadata(alias) == {"version": 1, "labels": ["Edited alias"], "extra": {"alias": True}}
    assert sidecar.sidecar_path(target).read_bytes() == target_metadata
    assert target.read_bytes() == raw
    assert alias.is_symlink()


def test_imported_message_is_owned(tmp_path, sample_eml_simple):
    source = tmp_path / "import.eml"
    source.write_bytes(sample_eml_simple)
    archive = EmailArchive(tmp_path / "archive")
    assert archive.import_email(source) == "imported"
    email_id = archive.search("")[0][0]

    assert archive.set_local_labels(email_id, ["Imported label"]) is True

    assert archive.get_local_labels(email_id) == ["Imported label"]
    assert archive.db.get_labels_for_email(email_id) == ["Imported label"]
    assert source.read_bytes() == sample_eml_simple


@pytest.mark.parametrize("failure", [OSError("disk full"), KeyboardInterrupt()])
def test_failed_atomic_write_preserves_old_labels(owned_message, monkeypatch, failure):
    archive, email_id, filepath, _provider = owned_message
    original = sidecar.sidecar_path(filepath).read_bytes()

    def failed_dump(data, stream):
        stream.write('{"partial":')
        raise failure

    monkeypatch.setattr(json, "dump", failed_dump)
    with pytest.raises(type(failure)):
        archive.set_local_labels(email_id, ["New"])

    assert sidecar.sidecar_path(filepath).read_bytes() == original
    assert archive.db.get_labels_for_email(email_id) == ["Server"]
    assert list(filepath.parent.glob("*.json.tmp")) == []


@pytest.mark.parametrize("labels", [["Local, precise", "  spaced  "], []])
@pytest.mark.parametrize("failure", [sqlite3.OperationalError("index locked"), KeyboardInterrupt()])
def test_index_failure_after_save_preserves_recoverable_labels(owned_message, monkeypatch, labels, failure):
    archive, email_id, filepath, _provider = owned_message
    with monkeypatch.context() as patch:
        patch.setattr(archive.db, "set_labels_for_email", Mock(side_effect=failure))
        if isinstance(failure, KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                archive.set_local_labels(email_id, labels)
        else:
            assert archive.set_local_labels(email_id, labels) is False

    assert archive.get_local_labels(email_id) == labels
    assert archive.db.get_labels_for_email(email_id) == ["Server"]
    assert sidecar.read_metadata(filepath)["extra"] == {"preserved": True}

    cmd_rebuild(archive, only="sidecars")

    assert set(archive.db.get_labels_for_email(email_id)) == set(labels)
    assert sidecar.read_labels(filepath) == labels


@pytest.mark.parametrize("read_target", ["message", "labels"])
def test_database_read_failure_before_save_propagates(owned_message, monkeypatch, read_target):
    archive, email_id, filepath, _provider = owned_message
    metadata_path = sidecar.sidecar_path(filepath)
    if read_target == "labels":
        metadata_path.unlink()
    else:
        original = metadata_path.read_bytes()
    method = "get_email_by_id" if read_target == "message" else "get_labels_for_email"
    monkeypatch.setattr(archive.db, method, Mock(side_effect=sqlite3.OperationalError("index unavailable")))

    with pytest.raises(sqlite3.OperationalError, match="index unavailable"):
        archive.set_local_labels(email_id, ["New"])

    if read_target == "labels":
        assert not metadata_path.exists()
    else:
        assert metadata_path.read_bytes() == original


def test_unreadable_sidecar_does_not_fall_back_to_index(owned_message, monkeypatch):
    archive, email_id, filepath, _provider = owned_message
    original = sidecar.sidecar_path(filepath).read_bytes()
    monkeypatch.setattr(sidecar, "read_metadata", Mock(return_value=None))

    with pytest.raises(ValueError, match="metadata is unreadable or malformed"):
        archive.set_local_labels(email_id, ["New"])

    assert sidecar.sidecar_path(filepath).read_bytes() == original


@pytest.mark.parametrize("labels", [["Local, precise", "  spaced  "], []])
@pytest.mark.parametrize("maintenance", ["download", "update-labels", "rebuild", "sidecars"])
def test_edited_labels_survive_routine_maintenance(owned_message, labels, maintenance):
    archive, email_id, filepath, provider = owned_message
    assert archive.set_local_labels(email_id, labels) is True
    saved = sidecar.sidecar_path(filepath).read_bytes()
    raw = filepath.read_bytes()
    if maintenance == "download":
        provider.download_message.return_value = (raw, ["Changed on server"])
        assert archive.backup(provider)["success_count"] == 0
        provider.download_message.assert_not_called()
    elif maintenance == "update-labels":
        archive.db.set_labels_for_email(email_id, [])
        cmd_update_labels(archive)
    elif maintenance == "rebuild":
        archive.db.set_labels_for_email(email_id, ["Stale index"])
        cmd_rebuild(archive, force=True)
    else:
        archive.db.set_labels_for_email(email_id, ["Stale index"])
        cmd_rebuild(archive, only="sidecars")

    assert sidecar.sidecar_path(filepath).read_bytes() == saved
    assert set(archive.db.get_labels_for_email(email_id)) == set(labels)
    assert filepath.read_bytes() == raw


def test_removed_index_row_does_not_report_success(owned_message, monkeypatch):
    archive, email_id, filepath, _provider = owned_message
    write_metadata = sidecar.write_metadata

    def save_then_remove_row(path, metadata):
        write_metadata(path, metadata)
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("DELETE FROM emails WHERE email_id = ?", (email_id,))

    monkeypatch.setattr(sidecar, "write_metadata", save_then_remove_row)

    assert archive.set_local_labels(email_id, ["New"]) is False

    assert sidecar.read_labels(filepath) == ["New"]
    assert archive.db.get_email_by_id(email_id) is None


def test_sidecar_stat_failure_is_not_missing_metadata(owned_message, monkeypatch):
    archive, email_id, filepath, _provider = owned_message
    metadata_path = sidecar.sidecar_path(filepath)
    original = metadata_path.read_bytes()
    original_lstat = Path.lstat

    def deny_metadata(path):
        if path == metadata_path:
            raise PermissionError("metadata inaccessible")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", deny_metadata)
    with pytest.raises(PermissionError, match="metadata inaccessible"):
        archive.set_local_labels(email_id, ["New"])

    assert metadata_path.read_bytes() == original
