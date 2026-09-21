"""Account-local candidate indexes preserve verification during a live sync."""

import hashlib
import sqlite3

import pytest

from ownmail.active_search import OwnedLookup, owned_match
from ownmail.archive import EmailArchive
from tests.test_live_sync import MailServer, message, owned_rows, sync


def entry_for(current, **updates):
    return {
        "source_name": "mail",
        "account": "reader@example.test",
        "identity": current.identity_token,
        "provider_id": current.message_id,
        "content_hash": hashlib.sha256(current.raw).hexdigest(),
        **updates,
    }


@pytest.fixture
def owned(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    current = message("owned", state="eligible")
    assert sync(archive, MailServer([current]))["success_count"] == 1
    return archive, entry_for(current), owned_rows(archive)[0]


def trace_queries(monkeypatch):
    queries = []
    connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(queries.append)
        return conn

    monkeypatch.setattr("ownmail.active_search.sqlite3.connect", traced_connect)
    return queries


def test_lookup_loads_account_once_for_repeated_identity_and_content_matches(owned, monkeypatch):
    archive, entry, row = owned
    queries = trace_queries(monkeypatch)
    lookup = OwnedLookup(archive, entry["account"])
    for _ in range(25):
        assert owned_match(archive, {**entry, "content_hash": None}, lookup=lookup)[0] == row[0]
        assert owned_match(archive, entry, lookup=lookup)[0] == row[0]
        assert owned_match(archive, {**entry, "provider_id": "other", "identity": "other"}, lookup=lookup)[0] == row[0]
    assert len(queries) == 1
    assert "FROM emails WHERE account =" in queries[0]


def test_lookup_rechecks_owned_bytes_after_candidates_are_loaded(owned):
    archive, entry, row = owned
    lookup = OwnedLookup(archive, entry["account"])
    assert owned_match(archive, entry, lookup=lookup)[0] == row[0]
    path = archive.archive_dir / row[1]
    path.write_bytes(path.read_bytes() + b"\nChanged locally")
    assert owned_match(archive, entry, lookup=lookup) is None


@pytest.mark.parametrize("scope", ["same", "other_account", "other_source"])
@pytest.mark.parametrize("include_trash", [False, True])
@pytest.mark.parametrize("original_filename", [False, True])
def test_lookup_keeps_account_source_and_trash_boundaries(owned, scope, include_trash, original_filename):
    archive, entry, row = owned
    assert archive.trash_email(row[0])
    if not original_filename:
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET original_filename = NULL WHERE email_id = ?", (row[0],))
    lookup = OwnedLookup(archive, entry["account"])
    if scope == "other_account":
        entry = {**entry, "account": "other@example.test"}
    elif scope == "other_source":
        entry = {**entry, "source_name": "other"}
    expected = owned_match(archive, entry, include_trash=include_trash)
    assert owned_match(archive, entry, include_trash=include_trash, lookup=lookup) == expected
    assert (expected is not None) is (scope == "same" and include_trash)


def test_added_capture_is_found_without_reloading_the_account(tmp_path, monkeypatch):
    archive = EmailArchive(tmp_path / "archive")
    current = message("new", state="eligible")
    entry = entry_for(current)
    lookup = OwnedLookup(archive, entry["account"])
    assert sync(archive, MailServer([current]))["success_count"] == 1
    email_id = owned_rows(archive)[0][0]
    assert owned_match(archive, entry, lookup=lookup) is None
    queries = trace_queries(monkeypatch)
    lookup.add(email_id)
    lookup.add(email_id)
    lookup.add("missing")
    assert owned_match(archive, entry, lookup=lookup)[0] == email_id
    assert owned_match(archive, {**entry, "content_hash": None}, lookup=lookup)[0] == email_id
    assert len(queries) == 3
    assert all("FROM emails WHERE email_id =" in query and "AND account =" in query for query in queries)


def test_lookup_add_cannot_import_another_accounts_candidate(owned):
    archive, entry, row = owned
    lookup = OwnedLookup(archive, "other@example.test")
    lookup.add(row[0])
    assert lookup.candidates({**entry, "account": "other@example.test"}) == []
