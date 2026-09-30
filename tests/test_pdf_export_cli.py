"""PDF command dispatch and errors; renderer integration has separate tests."""

import subprocess
import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

from tests import test_export

archive = test_export.archive
store = test_export.store
run_cli = test_export.run_cli


@pytest.fixture
def pdf_export(monkeypatch):
    # The optional renderer is a lazy command boundary. No browser is needed to
    # verify argument forwarding, command status or error presentation.
    module = ModuleType("ownmail.pdf_export")
    module.export_pdf = Mock(return_value=(2, []))
    monkeypatch.setitem(sys.modules, "ownmail.pdf_export", module)
    return module.export_pdf


@pytest.mark.parametrize("query", ["", '-is:active label:"Filed mail" after:2024-01-01'])
def test_pdf_dispatch_preserves_archive_output_and_query(archive, run_cli, pdf_export, tmp_path, capsys, query):
    output = tmp_path / "documents"

    run_cli(archive, output, "--format", "pdf", f"--query={query}")

    pdf_export.assert_called_once_with(archive, output, query)
    assert f"Exported 2 message(s) to {output}" in capsys.readouterr().out


def test_pdf_zero_results_are_successful(archive, run_cli, pdf_export, tmp_path, capsys):
    pdf_export.return_value = (0, [])
    run_cli(archive, tmp_path / "empty", "--format", "pdf")
    assert "Exported 0 message(s)" in capsys.readouterr().out


def test_pdf_partial_source_reads_report_failure_and_completed_count(archive, run_cli, pdf_export, tmp_path, capsys):
    pdf_export.return_value = (1, [("missing-message", "Source file is unavailable")])

    with pytest.raises(SystemExit) as error:
        run_cli(archive, tmp_path / "partial", "--format", "pdf")

    assert error.value.code == 1
    report = capsys.readouterr().out
    assert "Exported 1 message(s)" in report
    assert "Skipped 1 unreadable message(s)" in report
    assert "missing-message: Source file is unavailable" in report


@pytest.mark.parametrize(
    "failure",
    [
        OSError("PDF renderer unavailable: Chromium is missing"),
        FileExistsError("Output already exists"),
        OSError("PDF rendering timed out"),
        OSError("Cannot publish PDF output"),
        ValueError("Invalid search: unmatched quote"),
    ],
)
def test_pdf_failures_are_explicit_and_never_report_success(archive, run_cli, pdf_export, tmp_path, capsys, failure):
    pdf_export.side_effect = failure

    with pytest.raises(SystemExit) as error:
        run_cli(archive, tmp_path / "failed", "--format", "pdf")

    assert error.value.code == 1
    report = capsys.readouterr().out
    assert f"Export failed: {failure}" in report
    assert "Exported " not in report


def test_pdf_cancellation_uses_existing_interrupted_exit(archive, run_cli, pdf_export, tmp_path, capsys):
    pdf_export.side_effect = KeyboardInterrupt()

    with pytest.raises(SystemExit) as error:
        run_cli(archive, tmp_path / "interrupted", "--format", "pdf")

    assert error.value.code == 1
    report = capsys.readouterr().out
    assert "Operation interrupted by user" in report
    assert "Exported " not in report


@pytest.mark.parametrize("command", ["help", "mbox", "default"])
def test_non_pdf_startup_never_imports_or_probes_renderer(archive, store, tmp_path, command):
    store("ordinary")
    config = tmp_path / "synthetic.yaml"
    config.write_text("sources: []\n")
    output = tmp_path / "ordinary.mbox"
    options = ["--help"] if command == "help" else ["export", "--output", str(output)]
    if command == "mbox":
        options += ["--format", "mbox"]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import builtins
import subprocess
import sys

original_import = builtins.__import__
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'ownmail.pdf_export' or (name == 'ownmail' and 'pdf_export' in (fromlist or ())):
        raise AssertionError('Normal startup imported the optional PDF renderer')
    return original_import(name, globals, locals, fromlist, level)
def forbidden_process(*args, **kwargs):
    raise AssertionError('Normal startup probed or launched an external renderer')
builtins.__import__ = guarded_import
subprocess.Popen = forbidden_process
sys.argv = ['ownmail', *sys.argv[1:]]
from ownmail.cli import main
main()
""",
            "--config",
            str(config),
            "--archive-root",
            str(archive.archive_dir),
            *options,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    if command != "help":
        assert [str(message["Subject"]) for message in test_export.read_mbox(output)] == ["ordinary"]
