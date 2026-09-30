"""Archive-only mbox exports preserve mail and fail without clobbering files."""

import hashlib
import mailbox
import sqlite3
import subprocess
import sys
from contextlib import closing
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from ownmail import cli, sidecar
from ownmail.archive import EmailArchive
from tests import test_active_search

mixed_archive = test_active_search.mixed


@pytest.fixture
def archive(tmp_path):
    return EmailArchive(tmp_path / "archive")


@pytest.fixture
def store(archive):
    def add(identifier, *, raw=None, labels=(), date="2024-01-15T12:00:00+00:00"):
        if raw is None:
            raw = (
                f"From: sender@example.test\r\nTo: reader@example.test\r\nSubject: {identifier}\r\n"
                f"Date: Mon, 15 Jan 2024 12:00:00 +0000\r\nMessage-ID: <{identifier}@example.test>\r\n"
                "\r\nSynthetic invoice body.\r\n"
            ).encode()
        path = archive.archive_dir / f"{identifier}.eml"
        path.write_bytes(raw)
        message = BytesParser(policy=policy.default).parsebytes(raw)
        archive.db.mark_downloaded(identifier, identifier, path.name, hashlib.sha256(raw).hexdigest(), email_date=date)
        archive.db.index_email(
            identifier,
            str(message.get("Subject", "")),
            str(message.get("From", "")),
            str(message.get("To", "")),
            str(message.get("Date", "")),
            raw.decode("utf-8", errors="replace"),
            " ".join(part.get_filename() or "" for part in message.walk()).strip(),
            labels=list(labels),
        )
        sidecar.write_labels(path, list(labels))
        return path

    return add


@pytest.fixture
def run_cli(monkeypatch, tmp_path):
    def run(archive, output, *options):
        monkeypatch.setattr(
            sys,
            "argv",
            ["ownmail", "--config", str(tmp_path / "synthetic.yaml"), "export", "--output", str(output), *options],
        )
        monkeypatch.setattr(cli, "load_config", lambda *_: {})
        monkeypatch.setattr(cli, "validate_config", lambda *_: [])
        monkeypatch.setattr(cli, "EmailArchive", lambda *_: archive)
        return cli.main()

    return run


def read_mbox(path):
    with closing(
        mailbox.mbox(
            path, create=False, factory=lambda source: BytesParser(policy=policy.default).parsebytes(source.read())
        )
    ) as box:
        return list(box)


def snapshot(archive):
    return {
        path.relative_to(archive.archive_dir): path.read_bytes()
        for path in archive.archive_dir.rglob("*")
        if path.is_file()
    }


def assert_no_temporary_exports(output):
    assert not list(output.parent.glob(".ownmail-export-*"))


def test_cli_exports_original_headers_mime_and_attachments(archive, store, run_cli, tmp_path, capsys):
    message = EmailMessage()
    message["From"] = "Sender <sender@example.test>"
    message["To"] = "reader@example.test"
    message["Subject"] = "영수증 café"
    message["Message-ID"] = "<mime@example.test>"
    message["X-Keywords"] = "original-header"
    message["X-Custom"] = "preserve this"
    message.set_content("Plain text café.")
    message.add_alternative("<p>HTML body</p>", subtype="html")
    attachment = bytes(range(256))
    message.add_attachment(attachment, maintype="application", subtype="octet-stream", filename="첨부.bin")
    raw = message.as_bytes(policy=policy.SMTP)
    store("mime", raw=raw, labels=["Local label"])
    before = snapshot(archive)
    output = tmp_path / "backup.mbox"

    run_cli(archive, output, "--format", "mbox")

    (exported,) = read_mbox(output)
    original = BytesParser(policy=policy.default).parsebytes(raw)
    assert list(exported.raw_items()) == list(original.raw_items())
    assert (
        exported.get_body(preferencelist=("plain",)).get_content()
        == original.get_body(preferencelist=("plain",)).get_content()
    )
    assert (
        exported.get_body(preferencelist=("html",)).get_content()
        == original.get_body(preferencelist=("html",)).get_content()
    )
    assert next(exported.iter_attachments()).get_payload(decode=True) == attachment
    assert next(exported.iter_attachments()).get_filename() == "첨부.bin"
    assert exported.get_all("X-Keywords") == ["original-header"]
    assert exported["X-Gmail-Labels"] is None
    assert snapshot(archive) == before
    assert "Exported 1 message" in capsys.readouterr().out
    assert_no_temporary_exports(output)


def test_mbox_from_lines_do_not_split_messages(archive, store, run_cli, tmp_path):
    store("framing", raw=b"From: sender@example.test\nSubject: Framing\n\nFrom body line\n>From quoted line\nLast line")
    store("second")
    output = tmp_path / "framing.mbox"
    run_cli(archive, output)
    assert len(read_mbox(output)) == 2
    assert b"\n>From body line\n>From quoted line\nLast line\n" in output.read_bytes()


def test_export_has_no_result_cap_and_keeps_search_trash_date_exclusions(archive, store, run_cli, tmp_path):
    for index in range(63):
        store(f"message-{index:03d}")
    store("trashed")
    store("undated", date=None)
    with sqlite3.connect(archive.db.db_path) as connection:
        connection.execute("UPDATE emails SET trashed_at = '2024-01-16' WHERE email_id = 'trashed'")
    output = tmp_path / "all.mbox"
    run_cli(archive, output)
    assert {str(message["Subject"]) for message in read_mbox(output)} == {f"message-{index:03d}" for index in range(63)}


@pytest.mark.parametrize(
    "query",
    [
        "from:sender@example.test subject:invoice",
        'label:"Local label"',
        "attachment:pdf",
        "after:2024-01-01 before:2024-02-01",
        "invoice OR receipt",
        "invoice -subject:other",
        "has:attachment",
    ],
)
def test_query_reuses_existing_archive_search(archive, store, run_cli, tmp_path, query):
    message = EmailMessage()
    message["From"] = "sender@example.test"
    message["Subject"] = "Invoice"
    message["Message-ID"] = "<invoice@example.test>"
    message.set_content("Invoice body")
    message.add_attachment(b"synthetic PDF", maintype="application", subtype="pdf", filename="receipt.pdf")
    store("invoice", raw=message.as_bytes(), labels=["Local label"])
    store("other", date="2023-01-01T00:00:00+00:00")
    expected = {row[0] for row in archive.db.search(query, limit=-1)}
    output = tmp_path / "filtered.mbox"
    run_cli(archive, output, f"--query={query}")
    assert {str(message["Message-ID"]).split("@", 1)[0][1:] for message in read_mbox(output)} == expected
    assert all(message["X-Keywords"] is None for message in read_mbox(output))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", {"owned", "dual"}),
        ("is:active", {"dual"}),
        ("-is:active", {"owned"}),
        ("-has:attachment is:active", {"dual"}),
        ("-has:attachment -is:active", {"owned"}),
        ("is:archived", {"owned", "dual"}),
        ("-is:archived", set()),
        ("label:ServerLabel", set()),
        ("label:Original", {"dual"}),
    ],
)
def test_only_owned_bytes_are_exported_with_existing_membership(
    mixed_archive, run_cli, tmp_path, monkeypatch, query, expected
):
    archive, _ = mixed_archive
    before = snapshot(archive)
    monkeypatch.setattr(
        archive, "search", lambda *_args, **_kwargs: pytest.fail("Mixed cache results must not be exported")
    )
    monkeypatch.setattr(archive, "backup", lambda *_args, **_kwargs: pytest.fail("Export must not fetch mail"))
    original_cache = archive.active_cache

    def existing_cache(*, create=False):
        assert not create, "Export must not materialize an Active cache"
        return original_cache(create=create)

    monkeypatch.setattr(archive, "active_cache", existing_cache)
    output = tmp_path / "owned.mbox"
    run_cli(archive, output, f"--query={query}")
    assert {str(message["Subject"]).removeprefix("Message ") for message in read_mbox(output)} == expected
    assert snapshot(archive) == before


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("label:active", ["owned"]),
        ("is:archived", ["owned"]),
        ("label:active is:archived", ["owned"]),
        ("is:archived label:active", ["owned"]),
        ("label:active -is:archived", []),
    ],
)
def test_archive_filters_do_not_open_unrelated_invalid_cache(archive, store, run_cli, tmp_path, query, expected):
    store("owned", labels=["active"])
    cache = tmp_path / ".archive-active"
    cache.mkdir()
    marker = cache / "unrecognized-marker"
    marker.write_bytes(b"unrelated synthetic cache")
    output = tmp_path / "archive-filters.mbox"

    run_cli(archive, output, f"--query={query}")

    assert [str(message["Subject"]) for message in read_mbox(output)] == expected
    assert list(cache.iterdir()) == [marker]
    assert marker.read_bytes() == b"unrelated synthetic cache"


@pytest.mark.parametrize("query", ['subject:"unclosed', "is:unexpected", "label:Inbox OR label:Work", "-subject:other"])
def test_invalid_query_fails_before_creating_output(archive, run_cli, tmp_path, capsys, query):
    output = tmp_path / "invalid.mbox"
    with pytest.raises(SystemExit) as error:
        run_cli(archive, output, f"--query={query}")
    assert error.value.code == 1
    assert "Invalid search:" in capsys.readouterr().out
    assert not output.exists()
    assert_no_temporary_exports(output)


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling"])
def test_existing_destination_is_never_overwritten(archive, store, run_cli, tmp_path, kind):
    source = store("source")
    original = source.read_bytes()
    output = tmp_path / "existing.mbox"
    if kind == "file":
        output.write_bytes(b"existing export")
    elif kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(source if kind == "symlink" else tmp_path / "missing")
    with pytest.raises(SystemExit) as error:
        run_cli(archive, output)
    assert error.value.code == 1
    if kind == "file":
        assert output.read_bytes() == b"existing export"
    elif kind == "directory":
        assert output.is_dir()
    else:
        assert output.is_symlink()
    assert source.read_bytes() == original
    assert_no_temporary_exports(output)


def test_source_read_failures_report_partial_export(archive, store, run_cli, tmp_path, capsys):
    store("good")
    store("missing").unlink()
    outside = tmp_path / "outside.eml"
    outside.write_bytes(b"Do not export this file")
    store("outside")
    with sqlite3.connect(archive.db.db_path) as connection:
        connection.execute("UPDATE emails SET filename = ? WHERE email_id = 'outside'", (str(outside),))
    output = tmp_path / "partial.mbox"
    with pytest.raises(SystemExit) as error:
        run_cli(archive, output)
    assert error.value.code == 1
    assert [str(message["Subject"]) for message in read_mbox(output)] == ["good"]
    report = capsys.readouterr().out
    assert "Skipped 2" in report and "missing" in report and "outside" in report
    assert_no_temporary_exports(output)


@pytest.mark.parametrize("failure", [OSError("synthetic write failure"), KeyboardInterrupt()])
@pytest.mark.parametrize("phase", ["mailbox", "publish"])
def test_output_failure_or_interrupt_cleans_up_for_a_fresh_retry(
    archive, store, run_cli, tmp_path, monkeypatch, failure, phase
):
    import ownmail.export as exporter

    store("one")
    store("two")
    before = snapshot(archive)
    output = tmp_path / "retry.mbox"
    with monkeypatch.context() as patch:
        if phase == "mailbox":
            original = mailbox.mbox.add
            calls = 0

            def broken(box, message):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise failure
                return original(box, message)

            patch.setattr(mailbox.mbox, "add", broken)
        else:

            def broken(source, destination):
                destination.write(source.read(17))
                raise failure

            patch.setattr(exporter.shutil, "copyfileobj", broken)
        with pytest.raises(SystemExit) as error:
            run_cli(archive, output)
        assert error.value.code == 1
    assert not output.exists()
    assert_no_temporary_exports(output)
    assert snapshot(archive) == before
    run_cli(archive, output)
    assert len(read_mbox(output)) == 2


def test_destination_created_during_export_is_preserved(archive, store, run_cli, tmp_path, monkeypatch):
    store("one")
    output = tmp_path / "raced.mbox"
    original = Path.open

    def raced(path, mode="r", *args, **kwargs):
        if path == output and mode == "xb":
            output.write_bytes(b"another writer")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced)
    with pytest.raises(SystemExit) as error:
        run_cli(archive, output)
    assert error.value.code == 1
    assert output.read_bytes() == b"another writer"
    assert_no_temporary_exports(output)


def test_empty_results_produce_an_empty_valid_mbox(archive, run_cli, tmp_path):
    output = tmp_path / "empty.mbox"
    run_cli(archive, output, "--query", "no-match")
    assert read_mbox(output) == []


def test_module_command_exports_from_explicit_synthetic_config(archive, store, tmp_path):
    store("standalone")
    config = tmp_path / "config.yaml"
    config.write_text("sources: []\n")
    output = tmp_path / "standalone.mbox"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ownmail",
            "--config",
            str(config),
            "--archive-root",
            str(archive.archive_dir),
            "export",
            "--format",
            "mbox",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert [str(message["Subject"]) for message in read_mbox(output)] == ["standalone"]


def test_unknown_export_format_is_explicitly_unsupported(archive, run_cli, tmp_path, capsys):
    output = tmp_path / "out.html"
    with pytest.raises(SystemExit) as error:
        run_cli(archive, output, "--format", "html")
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert not output.exists()
