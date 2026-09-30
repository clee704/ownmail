"""Read selected search results as bounded JSON without changing local mail."""

import hashlib
import json
import sys
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

import pytest

from ownmail import cli
from ownmail.archive import EmailArchive
from ownmail.parser import EmailParser
from tests import test_active_search
from tests.test_search_readonly import run_json, substantive_files

mixed_archive = test_active_search.mixed


def store_message(tmp_path, raw):
    archive = EmailArchive(tmp_path / "archive #?")
    identifier = "selected-message"
    path = archive.archive_dir / "original #?.eml"
    path.write_bytes(raw)
    parsed = EmailParser.parse_file(content=raw)
    archive.db.mark_downloaded(
        identifier, identifier, path.name, hashlib.sha256(raw).hexdigest(), email_date="2024-01-01T00:00:00"
    )
    archive.db.index_email(
        identifier,
        parsed["subject"],
        parsed["sender"],
        parsed["recipients"],
        parsed["date_str"],
        parsed["body"],
        parsed["attachments"],
    )
    return archive, identifier, path


def run_read(monkeypatch, capsys, archive, identifier, *options, config=None):
    monkeypatch.setattr(cli, "load_config", lambda *_: config or {})
    monkeypatch.setattr(sys, "argv", ["ownmail", "--archive-root", str(archive), "read", identifier, *options])
    try:
        cli.main()
        status = 0
    except SystemExit as error:
        status = error.code
    captured = capsys.readouterr()
    return status, json.loads(captured.out), captured.err


def test_search_to_read_decodes_headers_and_names_without_attachment_contents(tmp_path, monkeypatch, capsys):
    msg = EmailMessage()
    msg["From"] = "Élodie <sender@example.test>"
    msg["To"] = "Reader <reader@example.test>"
    msg["Subject"] = "Résumé"
    msg["Date"] = "Mon, 1 Jan 2024 10:00:00 +0000"
    msg.set_content("Readable body\n")
    msg.add_attachment("Private attachment text", subtype="plain", filename="Q1, été.txt")
    archive, identifier, path = store_message(tmp_path, msg.as_bytes())
    capsys.readouterr()
    before = substantive_files(tmp_path)
    status, search, _ = run_json(monkeypatch, capsys, archive.archive_dir, "Résumé")
    assert status == 0
    selected = search["results"][0]
    status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, selected["id"])
    assert status == 0
    assert result["id"] == identifier
    assert result["sender"] == "Élodie <sender@example.test>"
    assert result["subject"] == "Résumé"
    assert result["recipients"] == "Reader <reader@example.test>"
    assert result["date"] == "Mon, 01 Jan 2024 10:00:00 +0000"
    assert result["body"] == "Readable body\n"
    assert result["attachment_names"] == ["Q1, été.txt"]
    assert result["archived"] == selected["archived"] is True
    assert result["active"] is selected["active"] is None
    assert result["original"] == {"uri": path.resolve().as_uri(), "media_type": "message/rfc822"}
    assert result["body_limit"] == 20000 and result["truncated"] is False
    assert substantive_files(tmp_path) == before


def test_html_only_is_readable_text_without_scripts_or_remote_requests(tmp_path, monkeypatch, capsys):
    msg = EmailMessage()
    msg["Subject"] = "HTML"
    msg.set_content(
        '<html><head><style>hidden</style></head><body>Hello &amp; welcome<script>bad()</script><img src="https://example.test/pixel"></body></html>',
        subtype="html",
    )
    archive, identifier, _ = store_message(tmp_path, msg.as_bytes())
    capsys.readouterr()
    with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
        status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier)
    assert status == 0
    assert result["body"] == "Hello & welcome"
    assert result["attachment_names"] == []


@pytest.mark.parametrize("limit,expected,truncated", [(3, "😀漢🙂", True), (4, "😀漢🙂\n", False)])
def test_body_limit_counts_unicode_characters(tmp_path, monkeypatch, capsys, limit, expected, truncated):
    msg = EmailMessage()
    msg.set_content("😀漢🙂\n")
    archive, identifier, _ = store_message(tmp_path, msg.as_bytes())
    capsys.readouterr()
    status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier, "--body-limit", str(limit))
    assert status == 0
    assert result["body"] == expected
    assert result["body_limit"] == limit
    assert result["truncated"] is truncated


@pytest.mark.parametrize("limit", ["0", "100001", "abc"])
def test_bad_body_limit_is_json_before_any_source_open(tmp_path, monkeypatch, capsys, limit):
    status, result, _ = run_read(monkeypatch, capsys, tmp_path / "absent", "id", "--body-limit", limit)
    assert status == 1
    assert result["error"]["code"] == "invalid_limit"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "failure,code", [("unknown", "not_found"), ("missing-file", "unavailable"), ("parse", "parse_failed")]
)
def test_defined_read_errors_are_json_and_do_not_modify_sources(tmp_path, monkeypatch, capsys, failure, code):
    archive, identifier, path = store_message(tmp_path, b"Subject: Body\n\nReadable\n")
    if failure == "unknown":
        identifier = "unknown-id"
    elif failure == "missing-file":
        path.unlink()
    else:
        monkeypatch.setattr(
            "ownmail.parser.email.message_from_bytes",
            lambda *_a, **_k: (_ for _ in ()).throw(ValueError("Synthetic MIME failure")),
        )
    capsys.readouterr()
    before = substantive_files(tmp_path)
    status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier)
    assert status == 1
    assert result["error"]["code"] == code
    assert substantive_files(tmp_path) == before


@pytest.mark.parametrize("body_limit", [None, 100000])
def test_default_and_maximum_body_caps_are_effective(tmp_path, monkeypatch, capsys, body_limit):
    msg = EmailMessage()
    msg.set_content("界" * 100005)
    archive, identifier, _ = store_message(tmp_path, msg.as_bytes())
    capsys.readouterr()
    options = () if body_limit is None else ("--body-limit", str(body_limit))
    status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier, *options)
    assert status == 0
    assert result["body"] == "界" * (body_limit or 20000)
    assert result["truncated"] is True


@pytest.mark.parametrize("kind", ["outside-path", "outside-symlink", "directory", "loop"])
def test_index_cannot_make_reader_open_an_unavailable_or_outside_file(tmp_path, monkeypatch, capsys, kind):
    import sqlite3

    archive, identifier, path = store_message(tmp_path, b"Subject: Safe\n\nSafe body\n")
    outside = tmp_path / "outside.eml"
    outside.write_bytes(b"Subject: Outside\n\nOutside private text\n")
    if kind == "outside-path":
        with sqlite3.connect(archive.db.db_path) as conn:
            conn.execute("UPDATE emails SET filename=?", (str(outside),))
    else:
        path.unlink()
        if kind == "outside-symlink":
            path.symlink_to(outside)
        elif kind == "loop":
            path.symlink_to(path.name)
        else:
            path.mkdir()
    capsys.readouterr()
    before = substantive_files(tmp_path)
    status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier)
    assert status == 1
    assert result["error"]["code"] == "unavailable"
    assert "Outside private text" not in json.dumps(result)
    assert substantive_files(tmp_path) == before


def test_current_archive_wal_resolves_the_selected_file_without_writing(tmp_path, monkeypatch, capsys):
    import sqlite3
    from contextlib import closing

    archive, identifier, _ = store_message(tmp_path, b"Subject: Earlier\n\nEarlier body\n")
    later = archive.archive_dir / "wal-current.eml"
    later.write_bytes(b"Subject: Current\n\nCurrent body\n")
    with closing(sqlite3.connect(archive.db.db_path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE emails SET filename=? WHERE email_id=?", (later.name, identifier))
        writer.commit()
        wal = Path(str(archive.db.db_path) + "-wal")
        before, wal_before = substantive_files(tmp_path), wal.read_bytes()
        assert wal_before
        capsys.readouterr()
        with patch("sqlite3.connect", wraps=sqlite3.connect) as connect:
            status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier)
        assert status == 0
        assert result["body"] == "Current body\n"
        assert result["original"]["uri"] == later.as_uri()
        assert connect.call_count == 1
        assert connect.call_args.args[0].endswith("?mode=ro")
        assert connect.call_args.kwargs == {"uri": True}
        assert substantive_files(tmp_path) == before
        assert wal.read_bytes() == wal_before


def test_read_has_no_initialization_credentials_or_network(tmp_path, monkeypatch, capsys):
    from ownmail.active_cache import ActiveCache
    from ownmail.database import ArchiveDatabase

    archive, identifier, _ = store_message(tmp_path, b"Subject: Safe\n\nReadable\n")
    capsys.readouterr()
    before = substantive_files(tmp_path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Read called an initializer, rebuild, credential or network path")

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
        status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier)
    assert status == 0 and result["body"] == "Readable\n"
    assert substantive_files(tmp_path) == before
    assert not (tmp_path / ".archive #?-active").exists()


def test_search_to_read_preserves_archived_active_and_dual_identity(mixed_archive, tmp_path, monkeypatch, capsys):
    import sqlite3

    archive, ids = mixed_archive
    config = {
        **archive.config,
        "sources": [{**source, "auth": {"secret_ref": "keychain:synthetic"}} for source in archive.config["sources"]],
    }
    archive.active_cache().set_source_status("mail", "reader@example.test", complete=False, error="Refresh failed")
    capsys.readouterr()
    before = substantive_files(tmp_path)
    status, search, _ = run_json(monkeypatch, capsys, archive.archive_dir, config=config)
    assert status == 0 and len(search["results"]) == 3
    for selected in search["results"]:
        with patch("sqlite3.connect", wraps=sqlite3.connect) as connect:
            status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, selected["id"], config=config)
        assert status == 0
        assert result["id"] == selected["id"]
        assert result["subject"] == selected["subject"]
        assert "Body" in result["body"]
        assert result["archived"] == selected["archived"]
        assert result["active"] == selected["active"]
        if result["id"] != ids["owned"]:
            assert result["active"]["complete"] is False
            assert result["active"]["refresh_error"] == "Refresh failed"
        assert connect.call_count == 2
        assert all(call.args[0].endswith("?mode=ro") for call in connect.call_args_list)
    assert substantive_files(tmp_path) == before


def test_active_changes_reject_buffered_read_and_close_handles(mixed_archive, monkeypatch, capsys):
    from ownmail import read_json
    from ownmail.search_readonly import _SearchArchive

    archive, ids = mixed_archive
    config = {
        **archive.config,
        "sources": [{**source, "auth": {"secret_ref": "keychain:synthetic"}} for source in archive.config["sources"]],
    }
    captured = []
    original = read_json.read_message_json

    def change_after_read(reader, *args, **kwargs):
        captured.append(reader)
        result = original(reader, *args, **kwargs)
        archive.active_cache().set_source_status("mail", "reader@example.test", complete=False, error="Changed")
        return result

    monkeypatch.setattr(read_json, "read_message_json", change_after_read)
    capsys.readouterr()
    status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, ids["live"], config=config)
    assert status == 1 and result["error"]["code"] == "unavailable"
    assert "body" not in result
    assert isinstance(captured[0], _SearchArchive)
    import sqlite3

    for db in (captured[0].db, captured[0].active_cache().db):
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            db._reader.execute("SELECT 1")


@pytest.mark.parametrize("failure,status", [(RuntimeError("Unexpected failure"), 1), (KeyboardInterrupt(), 130)])
def test_read_failure_and_interruption_return_one_json_document(tmp_path, monkeypatch, capsys, failure, status):
    from ownmail import read_json

    archive, identifier, _ = store_message(tmp_path, b"Subject: Safe\n\nReadable\n")
    capsys.readouterr()
    with patch.object(read_json, "read_message_json", side_effect=failure):
        code, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, identifier)
    assert code == status
    assert result["error"]["code"] == "read_failed"


def test_empty_id_is_rejected_before_source_acquisition(tmp_path, monkeypatch, capsys):
    status, result, _ = run_read(monkeypatch, capsys, tmp_path / "absent", "")
    assert status == 1 and result["error"]["code"] == "invalid_id"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "raw,expected",
    [
        (b"Subject: Standalone\n\nReadable body\n", "Readable body\n"),
        (
            b"Subject: Standalone\nContent-Type: text/html; charset=utf-8\n\n"
            b"<div><style>hidden CSS</style>Visible <script>hiddenScript()</script>following text</div>",
            "Visible following text",
        ),
    ],
)
def test_standalone_search_to_read_uses_explicit_config_and_clean_json(tmp_path, raw, expected):
    import subprocess

    archive, identifier, path = store_message(tmp_path, raw)
    config = tmp_path / "synthetic.yaml"
    config.write_text(f"sources: []\narchive_root: {json.dumps(str(archive.archive_dir))}\n")
    before = substantive_files(tmp_path)
    common = [sys.executable, "-B", "-m", "ownmail", "--config", str(config)]
    search = subprocess.run([*common, "search", "Standalone", "--json"], capture_output=True, text=True, timeout=15)
    assert search.returncode == 0, search.stderr
    selected = json.loads(search.stdout)["results"][0]["id"]
    result = subprocess.run([*common, "read", selected], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["id"] == identifier
    assert payload["body"] == expected
    assert payload["original"]["uri"] == path.as_uri()
    assert "Loaded config" in result.stderr
    assert substantive_files(tmp_path) == before


@pytest.mark.parametrize(
    "payload,expected",
    [
        (b"Content-Type: text/plain; charset=x-unknown\n\nPlain fallback\n", "Plain fallback\n"),
        (b"Content-Type: text/plain\n\n\xbe\xc8\xb3\xe7\xc7\xcf\xbc\xbc\xbf\xe4\n", "안녕하세요\n"),
        (b"Content-Type: text/plain; charset=iso-8859-1\n\nCaf\xc3\xa9\n", "Café\n"),
        (b"Content-Type: text/plain; charset=windows-1251\n\n\xcf\xf0\xe8\xe2\xe5\xf2\n", "Привет\n"),
    ],
)
def test_reader_retains_existing_charset_recovery(payload, expected):
    assert EmailParser.parse_file(content=payload, for_reading=True)["body"] == expected


def test_reader_prefers_plain_and_skips_nested_or_inline_attachment_text():
    msg = EmailMessage()
    msg.set_content("Visible plain\n")
    msg.add_alternative("<p>Duplicate HTML</p>", subtype="html")
    forwarded = EmailMessage()
    forwarded.set_content("Forwarded attachment secret\n")
    msg.add_attachment(forwarded, filename="forwarded.eml")
    msg.add_attachment("Inline attachment secret", subtype="plain", disposition="inline", filename="named.txt")
    parsed = EmailParser.parse_file(content=msg.as_bytes(), for_reading=True)
    assert parsed["body"] == "Visible plain\n"
    assert parsed["attachment_names"] == ["forwarded.eml", "named.txt"]
    # Existing indexing behavior is deliberately unchanged.
    assert "Inline attachment secret" in EmailParser.parse_file(content=msg.as_bytes())["body"]


def test_empty_plain_alternative_falls_back_to_html_and_root_attachment_has_no_body():
    msg = EmailMessage()
    msg.set_content("")
    msg.add_alternative("<p>Visible HTML</p>", subtype="html")
    assert EmailParser.parse_file(content=msg.as_bytes(), for_reading=True)["body"].strip() == "Visible HTML"
    attached = EmailMessage()
    attached.set_content("Attachment content")
    attached.add_header("Content-Disposition", "attachment", filename="single.txt")
    parsed = EmailParser.parse_file(content=attached.as_bytes(), for_reading=True)
    assert parsed["body"] == "" and parsed["attachment_names"] == ["single.txt"]


def test_current_active_wal_is_read_without_rebuild_or_payload_changes(mixed_archive, tmp_path, monkeypatch, capsys):
    import sqlite3
    from contextlib import closing

    archive, ids = mixed_archive
    config = {
        **archive.config,
        "sources": [{**source, "auth": {"secret_ref": "keychain:synthetic"}} for source in archive.config["sources"]],
    }
    cache = archive.active_cache()
    entry = cache.get(ids["live"])
    with closing(sqlite3.connect(cache.db.db_path)) as observer:
        observer.execute("PRAGMA journal_mode=WAL")
        observer.execute("PRAGMA wal_autocheckpoint=0")
        observer.execute("BEGIN")
        observer.execute("SELECT COUNT(*) FROM emails").fetchone()
        cache.put(
            source_name=entry["source_name"],
            account=entry["account"],
            provider_id=entry["provider_id"],
            identity=entry["identity"],
            raw=cache.read(entry["id"]).replace(b"Body", b"Current Active WAL body"),
            labels=entry["labels"],
            roles=entry["roles"],
        )
        wal = Path(str(cache.db.db_path) + "-wal")
        before, wal_before = substantive_files(tmp_path), wal.read_bytes()
        assert wal_before
        capsys.readouterr()
        status, result, _ = run_read(monkeypatch, capsys, archive.archive_dir, ids["live"], config=config)
        assert status == 0
        assert "Current Active WAL body" in result["body"]
        assert result["archived"] is False and result["active"] is not None
        assert result["original"]["uri"] == cache.path(ids["live"]).as_uri()
        assert substantive_files(tmp_path) == before and wal.read_bytes() == wal_before


@pytest.mark.parametrize("damage", ["absent-archive", "missing-index", "bad-config"])
def test_read_unavailable_prerequisites_never_create_or_repair_state(tmp_path, monkeypatch, capsys, damage):
    if damage == "absent-archive":
        root, identifier = tmp_path / "absent", "unknown"
    else:
        archive, identifier, _ = store_message(tmp_path, b"Subject: Read\n\nBody\n")
        root = archive.archive_dir
        if damage == "missing-index":
            archive.db.db_path.unlink()
    capsys.readouterr()
    before = substantive_files(tmp_path)
    status, result, _ = run_read(
        monkeypatch, capsys, root, identifier, config={"active_cache_dir": 5} if damage == "bad-config" else None
    )
    assert status == 1 and result["error"]["code"] == "unavailable"
    assert substantive_files(tmp_path) == before


def test_liberal_mime_recovery_still_reads_headerless_text():
    parsed = EmailParser.parse_file(content=b"Just a body with no headers\n", for_reading=True)
    assert parsed["subject"] == "" and parsed["body"] == "Just a body with no headers\n"


def test_read_routes_parser_diagnostics_to_stderr(tmp_path, monkeypatch, capsys):
    archive, identifier, _ = store_message(tmp_path, b"Subject: Diagnostic\n\nReadable\n")
    parse = EmailParser.parse_file

    def diagnostic(*args, **kwargs):
        print("Synthetic parser recovery diagnostic")
        return parse(*args, **kwargs)

    monkeypatch.setattr(EmailParser, "parse_file", diagnostic)
    capsys.readouterr()
    status, result, diagnostics = run_read(monkeypatch, capsys, archive.archive_dir, identifier)
    assert status == 0 and result["body"] == "Readable\n"
    assert "Synthetic parser recovery diagnostic" in diagnostics
