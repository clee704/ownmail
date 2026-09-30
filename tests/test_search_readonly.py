"""JSON search reads current local data without initializing or repairing it."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

from ownmail import cli
from ownmail.active_cache import ActiveCache
from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase
from tests import test_active_search

mixed_archive = test_active_search.mixed


def store(archive, identifier, *, body="Search body", labels=()):
    raw = f"From: sender@example.test\nSubject: {identifier}\n\n{body}\n".encode()
    path = archive.archive_dir / f"{identifier}.eml"
    path.write_bytes(raw)
    archive.db.mark_downloaded(
        identifier,
        identifier,
        path.name,
        hashlib.sha256(raw).hexdigest(),
        email_date="2024-01-01T00:00:00",
    )
    archive.db.index_email(
        identifier,
        identifier,
        "sender@example.test",
        "reader@example.test",
        "2024-01-01",
        body,
        "",
        labels=list(labels),
    )


def substantive_files(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith(("ownmail.db-wal", "ownmail.db-shm"))
    }


def run_json(monkeypatch, capsys, archive, query="", *options, config=None, config_path=None):
    monkeypatch.setattr(cli, "load_config", lambda *_: config if config is not None else {})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ownmail",
            "--archive-root",
            str(archive),
            *(["--config", str(config_path)] if config_path is not None else []),
            "search",
            "--json",
            *options,
            "--",
            query,
        ],
    )
    try:
        cli.main()
        status = 0
    except SystemExit as error:
        status = error.code
    captured = capsys.readouterr()
    return status, json.loads(captured.out), captured.err


def test_cli_json_bounds_page_and_separates_diagnostics(tmp_path, monkeypatch, capsys):
    archive = EmailArchive(tmp_path / "archive")
    for identifier in ("a", "b", "c"):
        store(archive, identifier, body="界" * 230)
    with sqlite3.connect(archive.db.db_path) as conn:
        conn.execute("UPDATE emails SET snippet=?", ("界" * 230,))
    capsys.readouterr()
    before = substantive_files(tmp_path)
    status, payload, diagnostics = run_json(
        monkeypatch, capsys, archive.archive_dir, "", "--limit", "1", "--offset", "1"
    )
    assert status == 0
    assert [row["id"] for row in payload["results"]] == ["b"]
    assert payload["results"][0]["snippet"] == "界" * 199 + "…"
    assert payload["pagination"] == {"limit": 1, "offset": 1, "has_more": True, "next_offset": 2}
    assert "[db.search]" in diagnostics
    assert substantive_files(tmp_path) == before


@pytest.mark.parametrize(
    "options",
    [
        ("--limit", "0"),
        ("--limit", "501"),
        ("--limit", "abc"),
        ("--offset", "-1"),
        ("--offset", "abc"),
        ("--offset", "2147483648"),
    ],
)
def test_bad_pagination_is_json_before_source_open(tmp_path, monkeypatch, capsys, options):
    status, payload, _ = run_json(monkeypatch, capsys, tmp_path / "absent", "", *options)
    assert status != 0
    assert payload["error"]["code"] == "invalid_pagination"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("query", ['subject:"unclosed', "is:unexpected"])
def test_invalid_query_is_json_before_source_open(tmp_path, monkeypatch, capsys, query):
    status, payload, _ = run_json(monkeypatch, capsys, tmp_path / "absent", query)
    assert status != 0
    assert payload["error"]["code"] == "invalid_query"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("kind", ["missing", "empty", "old-schema", "corrupt"])
def test_unavailable_index_is_not_created_or_migrated(tmp_path, monkeypatch, capsys, kind):
    root = tmp_path / "archive"
    if kind != "missing":
        root.mkdir()
        if kind == "corrupt":
            (root / "ownmail.db").write_bytes(b"synthetic invalid sqlite")
        else:
            with sqlite3.connect(root / "ownmail.db") as conn:
                if kind == "old-schema":
                    conn.execute("CREATE TABLE emails (email_id TEXT)")
    before = substantive_files(tmp_path)
    status, payload, _ = run_json(monkeypatch, capsys, root)
    assert status != 0
    assert payload["error"]["code"] == "unavailable"
    assert substantive_files(tmp_path) == before


def test_read_snapshot_sees_committed_wal_and_preserves_it(tmp_path, capsys):
    from ownmail.search_readonly import open_search_archive

    archive = EmailArchive(tmp_path / "archive")
    store(archive, "old")
    with closing(sqlite3.connect(archive.db.db_path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE emails SET subject='committed WAL', snippet='current WAL' WHERE email_id='old'")
        writer.commit()
        before = substantive_files(tmp_path)
        wal = Path(str(archive.db.db_path) + "-wal")
        wal_before = wal.read_bytes()
        with open_search_archive(archive.archive_dir, {}) as reader:
            first = reader.search("")
            writer.execute("UPDATE emails SET subject='later commit' WHERE email_id='old'")
            writer.commit()
            assert reader.search("")[0][2] == first[0][2] == "committed WAL"
            with reader.db._connect() as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("UPDATE emails SET subject='forbidden'")
        with open_search_archive(archive.archive_dir, {}) as reader:
            assert reader.search("")[0][2] == "later commit"
        assert substantive_files(tmp_path) == before
        assert wal.read_bytes().startswith(wal_before)


def test_json_uses_no_initializer_rebuilder_credentials_or_network(tmp_path, monkeypatch, capsys):
    archive = EmailArchive(tmp_path / "archive")
    store(archive, "one")
    capsys.readouterr()

    def forbidden(*_args, **_kwargs):
        pytest.fail("JSON search called a mutating constructor, credential or network path")

    with (
        patch.object(EmailArchive, "__init__", forbidden),
        patch.object(ArchiveDatabase, "__init__", forbidden),
        patch.object(ActiveCache, "__init__", forbidden),
        patch.object(ActiveCache, "rebuild_index", forbidden),
        patch("ownmail.keychain.KeychainStorage.__init__", forbidden),
        patch("keyring.get_password", forbidden),
        patch("keyring.set_password", forbidden),
        patch("socket.socket.connect", forbidden),
    ):
        status, payload, _ = run_json(monkeypatch, capsys, archive.archive_dir)
    assert status == 0
    assert payload["results"][0]["id"] == "one"


def test_active_existing_view_matches_search_without_rebuild(mixed_archive, tmp_path):
    from ownmail.search_readonly import open_search_archive

    archive, ids = mixed_archive
    expected = archive.search("", limit=2)
    before = substantive_files(tmp_path)
    with patch.object(ActiveCache, "rebuild_index", side_effect=AssertionError("must not rebuild")):
        with open_search_archive(archive.archive_dir, archive.config) as reader:
            assert reader.search("", limit=2) == expected
            assert {row[0] for row in reader.search("is:active")} == {ids["dual"], ids["live"]}
            info = reader.active_infos()
            assert info[ids["dual"]]["archived"] is True
            assert info[ids["live"]]["archived"] is False
            assert info[ids["live"]]["content_at"]
    assert substantive_files(tmp_path) == before


def test_all_consolidated_query_paths_use_only_two_read_only_handles(mixed_archive):
    from ownmail.search_readonly import open_search_archive

    archive, _ = mixed_archive
    queries = ["role:inbox", "from:reader@example.test", "Body is:active", "label:Original is:archived"]
    expected = {query: archive.search(query) for query in queries}
    with patch("sqlite3.connect", wraps=sqlite3.connect) as connect:
        with open_search_archive(archive.archive_dir, archive.config) as reader:
            for query in queries:
                assert reader.search(query) == expected[query]
    assert connect.call_count == 2
    for call in connect.call_args_list:
        assert call.args[0].endswith("?mode=ro")
        assert call.kwargs["uri"] is True


@pytest.mark.parametrize("damage", ["missing-index", "stale-index", "missing-marker", "stale-labels"])
def test_active_prerequisites_report_unavailable_without_repair(mixed_archive, tmp_path, damage):
    from ownmail.search_readonly import SearchUnavailable, open_search_archive

    archive, _ = mixed_archive
    cache = archive.active_cache()
    if damage == "missing-index":
        cache.db.db_path.unlink()
    elif damage == "missing-marker":
        (cache.cache_dir / "active-cache.json").unlink()
    else:
        with sqlite3.connect(cache.db.db_path) as conn:
            conn.execute(
                "DELETE FROM email_labels" if damage == "stale-labels" else "UPDATE emails SET indexed_hash='stale'"
            )
    before = substantive_files(tmp_path)
    with pytest.raises(SearchUnavailable):
        with open_search_archive(archive.archive_dir, archive.config):
            pass
    assert substantive_files(tmp_path) == before


@pytest.mark.parametrize("query,offset", [("notfound", 0), ("", 1)])
def test_empty_and_terminal_pages_succeed(tmp_path, monkeypatch, capsys, query, offset):
    archive = EmailArchive(tmp_path / "archive")
    store(archive, "one")
    capsys.readouterr()
    status, payload, _ = run_json(
        monkeypatch, capsys, archive.archive_dir, query, "--limit", "1", "--offset", str(offset)
    )
    assert status == 0
    assert payload == {
        "results": [],
        "pagination": {"limit": 1, "offset": offset, "has_more": False, "next_offset": None},
    }
    assert not (tmp_path / ".archive-active").exists()


def test_fts_error_does_not_succeed_as_an_empty_page(tmp_path, monkeypatch, capsys):
    archive = EmailArchive(tmp_path / "archive")
    store(archive, "one")
    capsys.readouterr()
    status, payload, _ = run_json(monkeypatch, capsys, archive.archive_dir, "-subject:one")
    assert status == 1
    assert payload["error"]["code"] == "invalid_query"


def test_active_json_pages_preserve_dual_ownership_and_failed_refresh(mixed_archive, tmp_path, monkeypatch, capsys):
    archive, ids = mixed_archive
    config = {
        **archive.config,
        "sources": [{**source, "auth": {"secret_ref": "keychain:synthetic"}} for source in archive.config["sources"]],
    }
    cache = archive.active_cache()
    cache.set_source_status("mail", "reader@example.test", complete=False, error="Synthetic refresh failure")
    expected = [row[0] for row in archive.search("")]
    capsys.readouterr()
    before = substantive_files(tmp_path)
    pages = []
    for offset in range(3):
        status, payload, _ = run_json(
            monkeypatch, capsys, archive.archive_dir, "", "--limit", "1", "--offset", str(offset), config=config
        )
        assert status == 0
        assert payload["pagination"]["has_more"] == (offset < 2)
        pages.extend(payload["results"])
    assert [result["id"] for result in pages] == expected
    by_id = {result["id"]: result for result in pages}
    assert by_id[ids["owned"]]["active"] is None
    assert by_id[ids["owned"]]["archived"] is True
    assert by_id[ids["dual"]]["archived"] is True
    assert by_id[ids["live"]]["archived"] is False
    for key in ("dual", "live"):
        assert by_id[ids[key]]["active"]["complete"] is False
        assert by_id[ids[key]]["active"]["refresh_error"] == "Synthetic refresh failure"
        assert by_id[ids[key]]["active"]["reason"]
    assert substantive_files(tmp_path) == before


def test_active_wal_is_current_and_substantively_unchanged(mixed_archive, tmp_path):
    from ownmail.search_readonly import open_search_archive

    archive, ids = mixed_archive
    cache = archive.active_cache()
    entry = cache.get(ids["live"])
    with closing(sqlite3.connect(cache.db.db_path)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("BEGIN")
        writer.execute("SELECT COUNT(*) FROM emails").fetchone()
        cache.put(
            source_name=entry["source_name"],
            account=entry["account"],
            provider_id=entry["provider_id"],
            identity=entry["identity"],
            raw=cache.read(entry["id"]).replace(b"Body", b"walonlytoken"),
            labels=entry["labels"],
            roles=entry["roles"],
        )
        before = substantive_files(tmp_path)
        wal = Path(str(cache.db.db_path) + "-wal")
        wal_before = wal.read_bytes()
        assert wal_before
        with open_search_archive(archive.archive_dir, archive.config) as reader:
            assert [row[0] for row in reader.search("walonlytoken")] == [ids["live"]]
        assert substantive_files(tmp_path) == before
        assert wal.read_bytes() == wal_before


def test_cache_changed_during_read_is_unavailable_and_handles_close(mixed_archive):
    from ownmail.search_readonly import SearchUnavailable, open_search_archive

    archive, _ = mixed_archive
    with pytest.raises(SearchUnavailable, match="changed during search"):
        with open_search_archive(archive.archive_dir, archive.config) as reader:
            assert reader.search("")
            archive.active_cache().set_source_status("mail", "reader@example.test", complete=False, error="Changed")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        reader.db._reader.execute("SELECT 1")


def test_standalone_cli_reads_separate_index_and_keeps_stdout_json(tmp_path):
    root = tmp_path / "archive #?"
    index = tmp_path / "index #?"
    archive = EmailArchive(root, {"db_dir": str(index)})
    store(archive, "standalone")
    config = tmp_path / "synthetic.yaml"
    config.write_text(f"sources: []\narchive_root: {json.dumps(str(root))}\ndb_dir: {json.dumps(str(index))}\n")
    before = substantive_files(tmp_path)
    result = subprocess.run(
        [sys.executable, "-B", "-m", "ownmail", "--config", str(config), "search", "standalone", "--json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert [row["id"] for row in json.loads(result.stdout)["results"]] == ["standalone"]
    assert "Loaded config" in result.stderr and "[db.search]" in result.stderr
    assert substantive_files(tmp_path) == before


@pytest.mark.parametrize("kind", ["missing-config", "invalid-config", "unreadable-config"])
def test_config_errors_are_json_before_initialization(tmp_path, monkeypatch, capsys, kind):
    config_path = tmp_path / "missing.yaml" if kind == "missing-config" else None
    config = {"active_cache_dir": 5} if kind == "invalid-config" else None
    if kind == "unreadable-config":
        monkeypatch.setattr(
            cli, "validate_config", lambda _: (_ for _ in ()).throw(ValueError("Synthetic invalid structure"))
        )
    status, payload, _ = run_json(monkeypatch, capsys, tmp_path / "absent", config=config, config_path=config_path)
    assert status == 1
    assert payload["error"]["code"] == "unavailable"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("failure,code", [(RuntimeError("Synthetic failure"), 1), (KeyboardInterrupt(), 130)])
def test_unexpected_failure_and_interrupt_leave_one_error_document(tmp_path, monkeypatch, capsys, failure, code):
    from ownmail.search_readonly import _SearchArchive

    archive = EmailArchive(tmp_path / "archive")
    capsys.readouterr()
    with patch.object(_SearchArchive, "search", side_effect=failure):
        status, payload, _ = run_json(monkeypatch, capsys, archive.archive_dir)
    assert status == code
    assert payload["error"]["code"] == "search_failed"
