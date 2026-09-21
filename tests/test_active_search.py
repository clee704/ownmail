"""Ownership filters and pagination over independent archive and cache indexes."""

import sqlite3
from dataclasses import replace

import pytest

from ownmail import sidecar
from ownmail.active_search import OwnedLookup, archive_links, owned_match
from ownmail.archive import EmailArchive
from ownmail.query import parse_query
from tests.test_live_sync import MailServer, cache_message, message, owned_rows, sync


@pytest.fixture
def mixed(tmp_path):
    archive = EmailArchive(
        tmp_path / "archive",
        {
            "sources": [
                {"name": "mail", "type": "gmail_api", "account": "reader@example.test", "active_downloads": True}
            ]
        },
    )
    archived = message("owned", state="eligible", labels=("Local",))
    dual = message("dual", state="eligible", labels=("Original",))
    server = MailServer([archived, dual])
    sync(archive, server)
    owned_id = archive.search("subject:owned")[0][0]
    dual_id = archive.search("subject:dual")[0][0]
    server.messages["live"] = message("live", labels=("Inbox", "LiveLabel"))
    server.messages["dual"] = replace(dual, state="active", labels=("Inbox", "ServerLabel"))
    sync(archive, server)
    cache_message(archive, server, server.messages["dual"])
    live_id = next(entry["id"] for entry in archive.active_cache().list_entries() if entry["provider_id"] == "live")
    return archive, {"owned": owned_id, "dual": dual_id, "live": live_id}


@pytest.mark.parametrize(
    ("query", "names"),
    [
        ("", {"owned", "dual", "live"}),
        ("is:active", {"dual", "live"}),
        ("is:archived", {"owned", "dual"}),
        ("is:active is:archived", {"dual"}),
        ("is:active is:active", {"dual", "live"}),
        ("-is:active", {"owned"}),
        ("-is:archived", {"live"}),
        ("-is:active -is:archived", set()),
        ("Body is:active", {"dual", "live"}),
        ("subject:owned is:archived", {"owned"}),
        ("label:Original is:archived", {"dual"}),
        ("label:LiveLabel is:active", {"live"}),
        ("is:unexpected", set()),
    ],
)
def test_ownership_filters_match_consolidated_results(mixed, query, names):
    archive, ids = mixed
    assert {row[0] for row in archive.search(query)} == {ids[name] for name in names}


@pytest.mark.parametrize("query", ["is:other", "-is:other", 'is:"other"'])
def test_unknown_ownership_values_report_parse_errors(query):
    assert "Unknown ownership state" in parse_query(query).error


@pytest.mark.parametrize("sort", ["date_desc", "date_asc", "relevance"])
@pytest.mark.parametrize("query", ["", "Body", "is:active", "Body is:archived"])
def test_pagination_neither_duplicates_nor_omits_mixed_results(mixed, sort, query):
    archive, _ = mixed
    expected = archive.search(query, limit=-1, sort=sort)
    pages = [archive.search(query, limit=1, offset=index, sort=sort) for index in range(len(expected) + 1)]
    assert [row for page in pages for row in page] == expected
    assert len({row[0] for row in expected}) == len(expected)


@pytest.mark.parametrize("sort", ["date_desc", "date_asc", "relevance"])
@pytest.mark.parametrize("query", ["", "Body", "label:Original"])
def test_active_results_come_first_before_pagination(mixed, sort, query):
    archive, ids = mixed
    server = MailServer()
    for index in range(6):
        candidate = message(f"extra{index}", state="eligible", labels=("Original",))
        server.messages[candidate.message_id] = candidate
    sync(archive, server)
    # Restore the live entries after the complete snapshot removed them.
    for name in ("live", "dual"):
        cache_message(archive, server, message(name))
    cache = archive.active_cache()
    active_ids = {ids["dual"], ids["live"]}
    with sqlite3.connect(archive.db.db_path) as conn:
        conn.execute("UPDATE emails SET email_date = '2025-01-01T00:00:00+00:00'")
        conn.execute("UPDATE emails SET email_date = '2023-01-01T00:00:00+00:00' WHERE email_id = ?", (ids["dual"],))
        conn.execute("UPDATE email_labels SET email_date = (SELECT email_date FROM emails WHERE rowid = email_rowid)")

    options = {"sort": sort, "limit": -1, "_with_order": True}
    archived = archive.db.search(query, **options)
    live = cache.db.search(query, **options)
    by_id = {row[0]: row for row in live if row[0] != archive.active_info(ids["dual"])["cache_id"]}
    by_id.update({row[0]: row for row in archived})
    relevance = sort == "relevance" and query == "Body"
    selected_order = sorted(
        by_id.values(), key=lambda row: (row[-1], row[0]), reverse=not relevance and sort != "date_asc"
    )
    expected = [row[0] for row in selected_order if row[0] in active_ids]
    expected += [row[0] for row in selected_order if row[0] not in active_ids]

    assert [row[0] for row in archive.search(query, sort=sort, limit=-1)] == expected
    pages = [archive.search(query, sort=sort, limit=1, offset=index) for index in range(len(expected) + 1)]
    assert [row[0] for page in pages for row in page] == expected


def test_live_only_text_match_links_to_owned_result(mixed):
    archive, ids = mixed
    entry = next(entry for entry in archive.active_cache().list_entries() if entry["provider_id"] == "dual")
    cache = archive.active_cache()
    cache.put(
        source_name=entry["source_name"],
        account=entry["account"],
        provider_id=entry["provider_id"],
        identity=entry["identity"],
        roles=entry["roles"],
        labels=entry["labels"],
        raw=cache.read(entry["id"]).replace(b"Body", b"uniquelivecontent"),
    )
    assert [row[0] for row in archive.search("uniquelivecontent")] == [ids["dual"]]
    assert b"uniquelivecontent" not in (archive.archive_dir / archive.get_readable_email(ids["dual"])[1]).read_bytes()


def test_active_metadata_uses_persisted_freshness_not_owned_labels(mixed):
    archive, ids = mixed
    cache = archive.active_cache()
    entry = cache.list_entries()[0]
    cache.set_source_status(entry["source_name"], entry["account"], complete=False, error="Synthetic failed refresh")
    info = archive.active_info(ids["dual"])
    assert not info["complete"]
    assert info["reason"] == "Active mail has not been refreshed for the current scope"
    assert info["refresh_error"] == "Synthetic failed refresh"
    assert info["archive_id"] == ids["dual"]
    assert info["checked_at"]
    assert archive.active_info(ids["owned"]) is None
    assert archive.active_info("unknown") is None
    assert archive.active_infos()[info["cache_id"]] == info


def test_empty_archive_does_not_create_a_cache_for_reading(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    assert archive.search("is:active") == []
    assert archive.active_count() == 0
    assert archive.active_info("unknown") is None
    assert archive.active_infos() == {}
    assert archive.get_readable_email("active-" + "0" * 64) is None
    assert not (tmp_path / ".archive-active").exists()


@pytest.mark.parametrize("use_lookup", [False, True])
def test_ambiguous_legacy_content_matches_remain_separate(tmp_path, use_lookup):
    archive = EmailArchive(tmp_path / "archive")
    source = archive.get_emails_dir("mail")
    source.mkdir(parents=True)
    current = message("legacy")
    first = source / "one.eml"
    second = source / "two.eml"
    first.write_bytes(current.raw)
    second.write_bytes(current.raw)
    archive.register_scanned_email(first, account="reader@example.test")
    # Deliberately represent two distinct historical IDs with identical bytes.
    with sqlite3.connect(archive.db.db_path) as conn:
        content_hash = conn.execute("SELECT content_hash FROM emails").fetchone()[0]
        archive.db.mark_downloaded(
            "second",
            "other",
            str(second.relative_to(archive.archive_dir)),
            content_hash,
            "reader@example.test",
            conn=conn,
        )
    sync(archive, MailServer([current]))
    entry = archive.active_cache().list_entries()[0]
    lookup = OwnedLookup(archive, entry["account"]) if use_lookup else None
    assert owned_match(archive, entry, lookup=lookup) is None
    assert not archive_links(archive)
    assert archive.active_count() == 1


@pytest.mark.parametrize("change", ["missing", "changed", "external", "source"])
@pytest.mark.parametrize("use_lookup", [False, True])
def test_invalid_owned_match_does_not_hide_live_copy(mixed, tmp_path, change, use_lookup):
    archive, ids = mixed
    cache_entry = next(entry for entry in archive.active_cache().list_entries() if entry["provider_id"] == "dual")
    row = archive.get_readable_email(ids["dual"])
    path = archive.archive_dir / row[1]
    if change == "missing":
        path.unlink()
    elif change == "changed":
        path.write_bytes(b"locally changed content")
    elif change == "external":
        external = tmp_path / "external.eml"
        external.write_bytes(path.read_bytes())
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET filename = ? WHERE email_id = ?", (str(external), ids["dual"]))
    else:
        cache_entry = {**cache_entry, "source_name": "../outside"}
    lookup = OwnedLookup(archive, cache_entry["account"]) if use_lookup else None
    assert owned_match(archive, cache_entry, lookup=lookup) is None


def test_legacy_gmail_stable_id_links_edited_live_content_within_source(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    raw = message("old", identity="gmail:old").raw
    source = archive.get_emails_dir("mail")
    source.mkdir(parents=True)
    path = source / "old.eml"
    path.write_bytes(raw)
    archive.register_scanned_email(path, account="reader@example.test")
    with sqlite3.connect(archive.db.db_path) as conn:
        conn.execute("UPDATE emails SET provider_id = 'old'")
    server = MailServer([message("old", identity="gmail:old", raw=raw.replace(b"Body", b"Edited"))])
    sync(archive, server)
    owned_id = owned_rows(archive)[0][0]
    assert archive.search("Edited") == []
    assert [row[0] for row in archive.search("is:archived")] == [owned_id]
    assert archive.active_count() == 0


def test_search_account_filter_applies_to_both_indexes(mixed):
    archive, ids = mixed
    assert len(archive.search("", account="reader@example.test")) == len(ids)
    assert archive.search("", account="other@example.test") == []


def test_invalid_or_corrupt_cache_reads_do_not_hide_owned_results(mixed):
    archive, ids = mixed
    cache = archive.active_cache()
    path = cache.path(ids["live"])
    path.write_bytes(b"corrupted disposable content")
    assert archive.get_readable_email(ids["live"]) is None
    assert archive.get_readable_email("active-malformed") is None
    assert {row[0] for row in archive.search("")} == {ids["owned"], ids["dual"]}


def test_corrupt_freshness_metadata_is_reported_as_unknown(mixed):
    archive, ids = mixed
    for path in (archive.active_cache().cache_dir / "sources").glob("*.json"):
        path.write_text("{invalid json")
    info = archive.active_info(ids["dual"])
    assert info["complete"] is False
    assert info["reason"] == "Refresh metadata is unavailable"


def test_removed_archive_link_falls_back_to_live_copy(mixed, monkeypatch):
    archive, ids = mixed
    monkeypatch.setattr("ownmail.active_search.archive_links", lambda archive: {ids["live"]: "removed-owned-copy"})
    assert [row[0] for row in archive.search("subject:live")] == [ids["live"]]


def test_active_queries_leave_existing_archive_schema_unchanged(mixed):
    archive, _ = mixed
    with sqlite3.connect(archive.db.db_path) as conn:
        before = conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
    archive.search("is:active is:archived")
    archive.search("Body -is:active -is:archived")
    with sqlite3.connect(archive.db.db_path) as conn:
        assert conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall() == before


@pytest.mark.parametrize("provenance", [[], None, "invalid", 42])
def test_malformed_capture_provenance_keeps_verified_content_searchable(mixed, provenance):
    archive, ids = mixed
    path = archive.archive_dir / archive.get_readable_email(ids["dual"])[1]
    sidecar.write_metadata(path, {"capture": provenance})
    assert {row[0] for row in archive.search("Body")} == set(ids.values())
    assert archive.active_info(ids["dual"])["archived"]


@pytest.mark.parametrize("historical_label", ["INBOX", "DRAFT"])
def test_historical_state_labels_remain_owned_until_fresh_server_observation(tmp_path, historical_label):
    archive = EmailArchive(tmp_path / "archive")
    original = message("abcd1234", identity="gmail:abcd1234")
    source = archive.get_emails_dir("mail")
    source.mkdir(parents=True)
    path = source / "legacy.eml"
    path.write_bytes(original.raw)
    sidecar.write_labels(path, [historical_label, "Kept locally"])
    archive.register_scanned_email(path, account="reader@example.test")
    with sqlite3.connect(archive.db.db_path) as conn:
        conn.execute("UPDATE emails SET provider_id = ?", (original.message_id,))
    email_id = owned_rows(archive)[0][0]
    frozen = path.read_bytes(), sidecar.sidecar_path(path).read_bytes()

    assert archive.active_info(email_id) is None
    assert archive.active_count() == 0
    assert archive.search("is:active") == []
    assert [row[0] for row in archive.search("is:archived")] == [email_id]
    assert archive.active_cache() is None
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == frozen

    returned = replace(original, raw=original.raw.replace(b"Body", b"Edited"), labels=("INBOX", "Current server label"))
    assert sync(archive, MailServer([returned]))["active_refreshed"] == 0
    assert archive.active_cache().list_entries() == []
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == frozen
    assert archive.db.get_labels_for_email(email_id) == [historical_label, "Kept locally"]
    assert archive.active_info(email_id) is None
    assert [row[0] for row in archive.search("")] == [email_id]
    assert archive.search("is:active") == []
    assert archive.consolidated_count() == 1
