"""Active cache persistence, search freshness, and archive isolation."""

import json
import os
import sqlite3

import pytest

from ownmail.active_cache import ActiveCache

RAW = b"Subject: Planning\nFrom: sender@example.test\nDate: Mon, 01 Jan 2024 12:00:00 +0000\n\nFirst draft"
FIRST = "2024-01-01T12:00:00+00:00"
SECOND = "2024-01-02T12:00:00+00:00"


@pytest.fixture
def cache(tmp_path):
    return ActiveCache(tmp_path / "archive")


def put(cache, **changes):
    args = {
        "source_name": "mail",
        "account": "reader@example.test",
        "provider_id": "42",
        "identity": "epoch:42",
        "roles": ["inbox"],
        "labels": ["INBOX"],
        "raw": RAW,
        "checked_at": FIRST,
    }
    args.update(changes)
    return cache.put(**args)


def metadata_path(cache, entry):
    return cache.cache_dir / "entries" / f"{entry['id']}.json"


def test_cache_default_is_outside_archive_and_does_not_create_archive(tmp_path):
    archive = tmp_path / "archive"
    cache = ActiveCache(archive)
    assert cache.cache_dir == tmp_path / ".archive-active"
    assert not archive.exists()


@pytest.mark.parametrize("location", ["same", "child", "parent", "alias"])
def test_archive_overlap_is_rejected_without_changing_archive(tmp_path, location):
    archive = tmp_path / "archive"
    archive.mkdir()
    owned = archive / "owned.eml"
    owned.write_bytes(RAW)
    if location == "same":
        target = archive
    elif location == "child":
        target = archive / "cache"
    elif location == "parent":
        target = tmp_path
    else:
        target = tmp_path / "alias"
        target.symlink_to(archive, target_is_directory=True)
    with pytest.raises(ValueError, match="separate"):
        ActiveCache(archive, target)
    assert owned.read_bytes() == RAW
    assert sorted(path.name for path in archive.iterdir()) == ["owned.eml"]


def test_nonempty_unmarked_directory_is_not_reused(tmp_path):
    target = tmp_path / "cache"
    target.mkdir()
    database = target / "ownmail.db"
    database.write_bytes(b"unrelated database")
    with pytest.raises(ValueError, match="empty"):
        ActiveCache(tmp_path / "archive", target)
    assert database.read_bytes() == b"unrelated database"


def test_cache_cannot_be_reassigned_to_another_archive(cache, tmp_path):
    with pytest.raises(ValueError, match="different archive"):
        ActiveCache(tmp_path / "other", cache.cache_dir)


def test_put_retains_source_metadata_and_indexes_content_and_exact_labels(cache):
    entry = put(cache, labels=["A, B", "INBOX", "A, B"])
    assert cache.get(entry["id"]) == entry
    assert cache.read(entry["id"]) == RAW
    assert cache.path(entry["id"]).read_bytes() == RAW
    assert entry["labels"] == ["A, B", "INBOX"]
    assert [row[0] for row in cache.db.search('label:"A, B" First')] == [entry["id"]]
    assert cache.db.get_labels_for_email(entry["id"]) == ["A, B", "INBOX"]


def test_refresh_removes_obsolete_content_labels_and_payload(cache):
    old = put(cache)
    path = cache.path(old["id"])
    changed = put(cache, labels=["DRAFT"], roles=["drafts"], raw=RAW.replace(b"First", b"Second"), checked_at=SECOND)
    assert changed["id"] == old["id"]
    assert changed["checked_at"] == changed["content_at"] == SECOND
    assert cache.db.search("First") == []
    assert cache.db.search("label:INBOX") == []
    assert [row[0] for row in cache.db.search("Second")] == [old["id"]]
    assert not path.exists()
    assert len(list((cache.cache_dir / "messages").glob("*.eml"))) == 1


def test_unchanged_content_keeps_content_age_and_updates_observation(cache):
    original = put(cache)
    refreshed = put(cache, checked_at=SECOND)
    assert refreshed["content_at"] == original["content_at"]
    assert refreshed["checked_at"] == SECOND


def test_identity_is_source_account_and_epoch_scoped_and_never_used_as_path(cache):
    entries = [put(cache, identity="../../unsafe", provider_id="../external")]
    entries.append(put(cache, source_name="other", identity="../../unsafe"))
    entries.append(put(cache, account="other@example.test", identity="../../unsafe"))
    entries.append(put(cache, identity="new-epoch:42"))
    assert len({entry["id"] for entry in entries}) == 4
    assert len(cache.db.search("First")) == 4
    assert [entry["id"] for entry in cache.list_entries("other", "reader@example.test")] == [entries[1]["id"]]
    assert len(cache.list_entries(account="other@example.test")) == 1
    assert all(cache.path(entry["id"]).parent == cache.cache_dir / "messages" for entry in entries)


@pytest.mark.parametrize(
    "raw", [b"Subject: Draft\n\nUndated", b"Subject: Draft\nDate: Mon, 01 Jan 2024 12:00:00\n\nUndated"]
)
def test_undated_and_timezone_missing_drafts_remain_searchable(cache, raw):
    entry = put(cache, raw=raw, state="unknown")
    assert [row[0] for row in cache.db.search("Undated")] == [entry["id"]]


def test_failed_metadata_replace_keeps_last_complete_copy(cache, monkeypatch):
    old = put(cache)
    original_replace = os.replace

    def fail_metadata(source, target):
        if target == metadata_path(cache, old):
            raise OSError("disk full")
        return original_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_metadata)
    with pytest.raises(OSError, match="disk full"):
        put(cache, raw=RAW.replace(b"First", b"Second"), checked_at=SECOND)
    assert cache.get(old["id"]) == old
    assert cache.read(old["id"]) == RAW
    assert [row[0] for row in cache.db.search("First")] == [old["id"]]
    assert not list(cache.cache_dir.rglob("*.tmp"))


def test_failed_index_write_recovers_committed_files_on_reopen(cache, monkeypatch):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("index unavailable")

    monkeypatch.setattr(cache, "_index_entry", fail)
    with pytest.raises(sqlite3.OperationalError, match="index unavailable"):
        put(cache)
    reopened = ActiveCache(cache.archive_dir)
    entry = reopened.list_entries()[0]
    assert reopened.read(entry["id"]) == RAW
    assert [row[0] for row in reopened.db.search("First")] == [entry["id"]]


@pytest.mark.parametrize("damage", ["deleted", "corrupt", "wrong_index"])
def test_rebuild_restores_content_labels_and_status_from_files(cache, damage):
    entry = put(cache)
    cache.set_source_status("mail", "reader@example.test", complete=True, checked_at=FIRST)
    if damage == "deleted":
        cache.db.db_path.unlink()
    elif damage == "corrupt":
        cache.db.db_path.write_bytes(b"corrupt")
    else:
        cache.db.set_labels_for_email(entry["id"], ["wrong"])
    reopened = ActiveCache(cache.archive_dir)
    assert [row[0] for row in reopened.db.search("First label:INBOX")] == [entry["id"]]
    assert reopened.db.search("label:wrong") == []
    assert reopened.source_status("mail", "reader@example.test")["completed_at"] == FIRST


def test_partial_refresh_retains_entries_and_previous_success(cache):
    entry = put(cache)
    cache.set_source_status("mail", "reader@example.test", complete=True, checked_at=FIRST)
    cache.set_source_status("mail", "reader@example.test", complete=False, error="offline", checked_at=SECOND)
    reopened = ActiveCache(cache.archive_dir)
    assert reopened.source_status("mail", "reader@example.test") == {
        "source_name": "mail",
        "account": "reader@example.test",
        "complete": False,
        "error": "offline",
        "checked_at": SECOND,
        "completed_at": FIRST,
    }
    assert reopened.read(entry["id"]) == RAW
    assert reopened.source_status("unknown", "reader@example.test") is None


def test_remove_hides_cache_content_without_touching_archive(cache):
    cache.archive_dir.mkdir()
    archive_message = cache.archive_dir / "owned.eml"
    archive_message.write_bytes(RAW)
    entry = put(cache)
    payload = cache.path(entry["id"])
    assert cache.remove(entry["id"]) is True
    assert cache.get(entry["id"]) is None
    assert cache.remove(entry["id"]) is False
    assert cache.db.search("First") == []
    assert not payload.exists()
    assert archive_message.read_bytes() == RAW
    for reader in (cache.path, cache.read):
        with pytest.raises(FileNotFoundError):
            reader(entry["id"])


@pytest.mark.parametrize("linked", ["symlink", "hardlink"])
@pytest.mark.parametrize("operation", ["read", "remove", "put"])
def test_linked_payload_cannot_read_replace_or_remove_archive(cache, linked, operation):
    entry = put(cache)
    payload = cache.path(entry["id"])
    cache.archive_dir.mkdir()
    owned = cache.archive_dir / "owned.eml"
    owned.write_bytes(RAW)
    payload.unlink()
    if linked == "symlink":
        payload.symlink_to(owned)
    else:
        os.link(owned, payload)
    with pytest.raises(ValueError, match="without links"):
        put(cache) if operation == "put" else getattr(cache, operation)(entry["id"])
    assert owned.read_bytes() == RAW
    assert metadata_path(cache, entry).exists()


@pytest.mark.parametrize(
    "relative", ["ownmail.db", "ownmail.db-journal", "entries", "messages", "sources", "active-cache.json"]
)
def test_managed_paths_cannot_redirect_to_archive(cache, relative):
    target = cache.cache_dir / relative
    original = target.with_name(target.name + ".original")
    if target.exists():
        target.rename(original)
    cache.archive_dir.mkdir()
    owned = cache.archive_dir / "owned.eml"
    owned.write_bytes(RAW)
    target.symlink_to(cache.archive_dir if relative in ("entries", "messages", "sources") else owned)
    with pytest.raises(ValueError):
        ActiveCache(cache.archive_dir)
    assert owned.read_bytes() == RAW
    assert sorted(path.name for path in cache.archive_dir.iterdir()) == ["owned.eml"]


def test_directory_redirect_after_open_cannot_remove_archive(cache, tmp_path):
    entry = put(cache)
    original = cache.cache_dir
    moved = tmp_path / "old-cache"
    original.rename(moved)
    cache.archive_dir.mkdir()
    original.symlink_to(cache.archive_dir, target_is_directory=True)
    with pytest.raises(ValueError, match="directory"):
        cache.remove(entry["id"])
    assert list(cache.archive_dir.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        None,
        {"filename": "../../owned.eml"},
        {"content_hash": "invalid"},
        {"state": "owned"},
        {"labels": "INBOX"},
        {"roles": [None]},
        {"source_name": None},
        {"identity": "another"},
        {"filename": None},
    ],
)
def test_corrupt_metadata_is_not_indexed_or_followed(cache, change, caplog):
    entry = put(cache)
    altered = entry | change if change is not None else []
    metadata_path(cache, entry).write_text(json.dumps(altered))
    with pytest.raises(ValueError):
        cache.get(entry["id"])
    cache.rebuild_index()
    assert cache.db.search("First") == []
    assert "Skipping unreadable Active cache entry" in caplog.text


def test_incomplete_metadata_is_not_indexed(cache):
    entry = put(cache)
    del entry["filename"]
    metadata_path(cache, entry).write_text(json.dumps(entry))
    with pytest.raises(ValueError, match="Incomplete"):
        cache.get(entry["id"])


def test_changed_payload_is_not_read_or_indexed(cache):
    entry = put(cache)
    cache.path(entry["id"]).write_bytes(b"changed outside ownmail")
    for reader in (cache.read, cache.path):
        with pytest.raises(ValueError, match="hash does not match"):
            reader(entry["id"])
    cache.rebuild_index()
    assert cache.db.search("First") == []


@pytest.mark.parametrize("active_id", ["../owned", "active-short", None])
def test_invalid_ids_cannot_escape_entries(cache, active_id):
    with pytest.raises(ValueError, match="Invalid Active message ID"):
        cache.get(active_id)


@pytest.mark.parametrize("change", [{"state": "owned"}, {"source_name": None}, {"labels": "INBOX"}])
def test_invalid_put_is_rejected_before_writing(cache, change):
    with pytest.raises(ValueError):
        put(cache, **change)
    assert cache.list_entries() == []


def test_source_status_rejects_inconsistent_json(cache):
    cache.set_source_status("mail", "reader@example.test", complete=False)
    path = next((cache.cache_dir / "sources").glob("*.json"))
    path.write_text('{"complete": "true"}')
    with pytest.raises(ValueError, match="Invalid Active source status"):
        cache.source_status("mail", "reader@example.test")
