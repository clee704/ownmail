"""Cleanup command dispatch preserves the local archive and authentication boundary."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ownmail import cli


@pytest.fixture
def cleanup_cli(tmp_path, monkeypatch):
    from ownmail import cleanup

    root = tmp_path / "archive"
    root.mkdir()
    source = {
        "name": "mail",
        "account": "reader@example.test",
        "type": "gmail_api",
        "auth": {"secret_ref": "keychain:oauth-token/reader@example.test"},
    }
    config = {"archive_root": str(root), "sources": [source]}
    summary = {"checked": 0, "eligible": 0, "held": 0, "trashed": 0, "errors": 0, "interrupted": False}
    actual_runner = cleanup.run_cleanup
    runner = Mock(return_value=summary)
    provider = SimpleNamespace(authenticate=Mock())
    factory = Mock(return_value=provider)
    keychain = Mock()
    archive_factory = Mock(side_effect=AssertionError("Cleanup must not initialize the archive"))
    loader = Mock(return_value=config)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_config", loader)
    monkeypatch.setattr(cli, "EmailArchive", archive_factory)
    monkeypatch.setattr(cli, "GmailProvider", factory)
    monkeypatch.setattr(cli, "KeychainStorage", keychain)
    monkeypatch.setattr(cleanup, "run_cleanup", runner)
    return SimpleNamespace(
        root=root,
        source=source,
        config=config,
        summary=summary,
        runner=runner,
        actual_runner=actual_runner,
        provider=provider,
        factory=factory,
        keychain=keychain,
        archive_factory=archive_factory,
        loader=loader,
    )


def invoke(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["ownmail", *args])
    cli.main()


@pytest.mark.parametrize("apply", [False, True])
def test_cleanup_previews_unless_apply_is_explicit(cleanup_cli, monkeypatch, capsys, apply):
    case = cleanup_cli
    case.source.update(include_labels=False, exclude_roles=[])
    args = ["cleanup", "--source", "mail"] + (["--apply"] if apply else [])

    invoke(monkeypatch, *args)

    case.factory.assert_called_once_with(
        account=case.source["account"],
        keychain=case.keychain.return_value,
        include_labels=False,
        source_name="mail",
        exclude_roles=[],
    )
    case.provider.authenticate.assert_called_once_with()
    call = case.runner.call_args
    assert call.args == (case.root, case.source, case.provider)
    assert call.kwargs["apply"] is apply
    assert call.kwargs["db_path"] == case.root / "ownmail.db"
    assert callable(call.kwargs["report"])
    case.archive_factory.assert_not_called()
    output = capsys.readouterr().out
    assert f"Cleanup {'apply' if apply else 'preview'}: mail (reader@example.test)" in output
    assert "Moved to server Trash: 0" in output


def test_cleanup_preserves_archive_index_cache_and_local_trash(monkeypatch, tmp_path, capsys):
    from ownmail.archive import EmailArchive
    from ownmail.thread_protection import ThreadProtection
    from tests.test_live_sync import MailServer, message, owned_rows, sync

    archive = EmailArchive(tmp_path / "archive")
    saved = message("saved", state="eligible", identity="gmail:saved", labels=("Saved",), thread_id="thread")
    discarded = message("local-trash", state="eligible", identity="gmail:local-trash")
    server = MailServer([saved, discarded, message("active")])
    assert sync(archive, server)["success_count"] == 2
    trash_id = next(
        email_id
        for email_id, filename in owned_rows(archive)
        if (archive.archive_dir / filename).read_bytes() == discarded.raw
    )
    assert archive.trash_email(trash_id)
    server.authenticate = Mock()
    server.verify_cleanup_account = Mock()
    server.check_thread_protection = lambda message_id: ThreadProtection(
        source_name="mail", account=server.account, message_id=message_id, thread_id="thread", complete=True
    )
    server.trash_message = Mock(side_effect=AssertionError("Preview must not move server mail"))
    config = {
        "archive_root": str(archive.archive_dir),
        "sources": [
            {
                "name": "mail",
                "account": server.account,
                "type": "gmail_api",
                "auth": {"secret_ref": "keychain:synthetic"},
            }
        ],
    }
    forbidden = Mock(side_effect=AssertionError("Cleanup must not initialize the archive"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "GmailProvider", Mock(return_value=server))
    monkeypatch.setattr(cli, "KeychainStorage", Mock())
    monkeypatch.setattr(cli, "EmailArchive", forbidden)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    invoke(monkeypatch, "cleanup", "--source", "mail")

    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before
    forbidden.assert_not_called()
    server.trash_message.assert_not_called()
    assert not (archive.archive_dir / ".download.lock").exists()
    output = capsys.readouterr().out
    assert "Eligible: 1" in output
    assert "Held: 1" in output
    assert "Errors: 0" in output


def test_cleanup_honors_archive_override_and_external_index(cleanup_cli, monkeypatch, tmp_path):
    case = cleanup_cli
    override = tmp_path / "selected-archive"
    override.mkdir()
    index_dir = tmp_path / "index"
    case.config["db_dir"] = str(index_dir)

    invoke(monkeypatch, "--archive-root", str(override), "cleanup", "--source", "mail")

    assert case.runner.call_args.args[0] == override
    assert case.runner.call_args.kwargs["db_path"] == index_dir / "ownmail.db"
    assert not index_dir.exists()
    assert list(override.iterdir()) == []


def test_unavailable_index_is_reported_without_creating_it(cleanup_cli, monkeypatch, capsys):
    from ownmail import cleanup

    case = cleanup_cli
    case.source.update(type="imap", host="imap.example.test")
    monkeypatch.setattr(cleanup, "run_cleanup", case.actual_runner)

    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "cleanup", "--source", "mail")

    assert error.value.code == 1
    assert list(case.root.iterdir()) == []
    case.keychain.assert_not_called()
    output = capsys.readouterr().out
    assert "error: archive: Archived candidates could not be read" in output
    assert "Errors: 1" in output


@pytest.mark.parametrize("apply", [False, True])
def test_imap_cleanup_stays_held_without_authentication(cleanup_cli, monkeypatch, capsys, apply):
    case = cleanup_cli
    case.source.update(type="imap", host="imap.example.test")
    case.summary.update(checked=1, held=1)

    def run(*args, report, **kwargs):
        report(
            {
                "email_id": "owned-message",
                "status": "held",
                "reason": "Complete IMAP thread state is unavailable",
                "checked_at": None,
            }
        )
        return case.summary

    case.runner.side_effect = run
    invoke(monkeypatch, "cleanup", "--source", "mail", *(["--apply"] if apply else []))

    assert case.runner.call_args.args[2] is None
    case.factory.assert_not_called()
    case.keychain.assert_not_called()
    output = capsys.readouterr().out
    assert "held: owned-message: Complete IMAP thread state is unavailable; checked unknown" in output
    assert "Held: 1" in output
    assert "Errors: 0" in output


def test_cleanup_requires_source_before_loading_config(cleanup_cli, monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "cleanup")
    assert error.value.code == 2
    assert "--source" in capsys.readouterr().err
    cleanup_cli.loader.assert_not_called()
    cleanup_cli.keychain.assert_not_called()


def test_unknown_cleanup_source_does_not_authenticate(cleanup_cli, monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "cleanup", "--source", "missing")
    assert error.value.code == 1
    assert "Source 'missing' not found" in capsys.readouterr().out
    cleanup_cli.keychain.assert_not_called()
    cleanup_cli.factory.assert_not_called()
    cleanup_cli.runner.assert_not_called()


def test_missing_archive_is_not_created_or_authenticated(cleanup_cli, monkeypatch, tmp_path, capsys):
    missing = tmp_path / "missing-archive"
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "--archive-root", str(missing), "cleanup", "--source", "mail")
    assert error.value.code == 1
    assert "Archive directory does not exist" in capsys.readouterr().out
    assert not missing.exists()
    cleanup_cli.keychain.assert_not_called()
    cleanup_cli.runner.assert_not_called()


def test_cleanup_reports_outcomes_and_fails_on_operation_errors(cleanup_cli, monkeypatch, capsys):
    case = cleanup_cli
    outcomes = {
        "eligible": None,
        "held": "Thread is Active",
        "trashed": None,
        "error": "Local file is unreadable",
        "uncertain": "Server move outcome could not be confirmed",
        "denied": "Current authorization does not permit server cleanup",
    }
    case.summary.update(checked=6, eligible=2, held=1, trashed=1, errors=3)

    def run(*args, report, **kwargs):
        for status, reason in outcomes.items():
            report(
                {
                    "email_id": status + "-message",
                    "status": status,
                    "reason": reason,
                    "checked_at": "2026-09-15T00:00:00Z",
                }
            )
        return case.summary

    case.runner.side_effect = run
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "cleanup", "--source", "mail", "--apply")

    assert error.value.code == 1
    output = capsys.readouterr().out
    for status, reason in outcomes.items():
        assert f"{status}: {status}-message" in output
        if reason:
            assert reason in output
    assert output.count("checked 2026-09-15T00:00:00Z") == 6
    assert "Checked: 6" in output
    assert "Eligible: 2" in output
    assert "Moved to server Trash: 1" in output
    assert "Errors: 3" in output
    assert "retry after resolving the reported errors" in output


def test_interrupted_cleanup_reports_partial_summary(cleanup_cli, monkeypatch, capsys):
    cleanup_cli.summary.update(checked=2, eligible=1, held=1, interrupted=True)
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "cleanup", "--source", "mail")
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "Checked: 2" in output
    assert "Held: 1" in output
    assert "Cleanup interrupted. Run cleanup again to recheck remaining candidates." in output


@pytest.mark.parametrize("error", [RuntimeError("Authentication unavailable"), KeyboardInterrupt()])
def test_cleanup_authentication_failure_exits_safely(cleanup_cli, monkeypatch, capsys, error):
    cleanup_cli.provider.authenticate.side_effect = error
    with pytest.raises(SystemExit) as result:
        invoke(monkeypatch, "cleanup", "--source", "mail")
    assert result.value.code == 1
    output = capsys.readouterr().out
    assert (
        "interrupted by user" in output
        if isinstance(error, KeyboardInterrupt)
        else "Authentication unavailable" in output
    )
    cleanup_cli.runner.assert_not_called()


@pytest.mark.parametrize("error", [RuntimeError("Verification unavailable"), KeyboardInterrupt()])
def test_unhandled_cleanup_failure_preserves_prior_reports(cleanup_cli, monkeypatch, capsys, error):
    def run(*args, report, **kwargs):
        report({"email_id": "first", "status": "held", "reason": "Thread is Active", "checked_at": None})
        raise error

    cleanup_cli.runner.side_effect = run
    with pytest.raises(SystemExit) as result:
        invoke(monkeypatch, "cleanup", "--source", "mail")
    assert result.value.code == 1
    output = capsys.readouterr().out
    assert "held: first: Thread is Active" in output
    assert (
        "interrupted by user" in output
        if isinstance(error, KeyboardInterrupt)
        else "Verification unavailable" in output
    )


def test_cleanup_help_describes_preview_and_explicit_apply(cleanup_cli, monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "cleanup", "--help")
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "Preview is the default" in output
    assert "--source" in output
    assert "--apply" in output
    cleanup_cli.keychain.assert_not_called()
