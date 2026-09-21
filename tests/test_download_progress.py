"""Private progress snapshots from CLI and archive download operations."""

import errno
import json
import signal
import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest
from keyring.errors import KeyringError, KeyringLocked

from ownmail.archive import EmailArchive
from ownmail.cli import cmd_download, main
from ownmail.download_lock import DownloadLock
from ownmail.download_progress import FAILURE_REASONS, DownloadProgress
from ownmail.live import LiveMessage, LiveSnapshot
from ownmail.providers.base import EmailProvider

PRIVATE_DETAIL = "private@example.com token=secret-value message-body"


def snapshot(path):
    data = path.read_text()
    assert PRIVATE_DETAIL not in data
    assert "private@example.com" not in data
    return json.loads(data)


def provider(ids=(), source="Synthetic"):
    result = MagicMock()
    result.name = "imap"
    result.source_name = source
    result.account = "private@example.com"
    result.download_batch_size = 1
    result.get_new_message_ids.return_value = (list(ids), None)
    result.get_current_sync_state.return_value = None
    result.download_message.return_value = (
        b"From: private@example.com\r\nDate: Mon, 1 Jan 2024 10:00:00 +0000\r\n\r\nmessage-body",
        [],
    )

    def list_live(*, on_progress=None):
        ids, _ = result.get_new_message_ids()
        if on_progress:
            on_progress(len(ids))
        return LiveSnapshot(
            source,
            result.account,
            [LiveMessage(message_id, identity_token=message_id, state="eligible") for message_id in ids],
            complete=True,
        )

    def read_live(message_id):
        raw, labels = result.download_message(message_id)
        return LiveMessage(message_id, labels=tuple(labels), identity_token=message_id, state="eligible", raw=raw)

    result.list_live_messages.side_effect = list_live
    result.read_live_message.side_effect = read_live
    result.live_batch_size = 1
    result.read_live_messages.side_effect = lambda ids: EmailProvider.read_live_messages(result, ids)
    return result


@pytest.fixture
def cli_download(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        "sources:\n"
        "  - name: Synthetic\n"
        "    type: imap\n"
        "    active_downloads: true\n"
        "    account: private@example.com\n"
        "    host: mail.example.com\n"
        "    auth: {secret_ref: 'keychain:synthetic'}\n"
    )
    progress = tmp_path / "progress.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ownmail",
            "--config",
            str(config),
            "--archive-root",
            str(tmp_path / "archive"),
            "download",
            "--progress-file",
            str(progress),
        ],
    )
    return config, progress


def test_reporter_throttles_counts_but_flushes_phases_and_completion(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("ownmail.download_progress.time.monotonic", lambda: now[0])
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    assert snapshot(path) == {
        "phase": "starting",
        "source": None,
        "downloaded": 0,
        "skipped": 0,
        "errors": 0,
        "failure_reason": None,
    }
    progress.advance(downloaded=1)
    assert snapshot(path)["downloaded"] == 0
    now[0] = 0.3
    progress.advance(skipped=1)
    assert snapshot(path)["downloaded"] == snapshot(path)["skipped"] == 1
    progress.advance(downloaded=1)
    progress.set_phase("checking", "Second")
    assert snapshot(path)["downloaded"] == 2
    progress.advance(downloaded=1)
    progress.finish()
    final = snapshot(path)
    assert final["downloaded"] == 3
    assert final["phase"] == "finished"
    assert final["source"] == "Second"
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".ownmail-progress-*"))


def test_failed_progress_write_preserves_previous_snapshot_and_download_state(tmp_path):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    before = path.read_bytes()

    def partial_write(data, stream):
        stream.write('{"unfinished":')
        assert path.read_bytes() == before
        raise OSError("disk full")

    with patch("ownmail.download_progress.json.dump", side_effect=partial_write):
        progress.advance(downloaded=1)
        progress.flush()
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".ownmail-progress-*"))
    progress.finish()
    assert snapshot(path)["downloaded"] == 1


@pytest.mark.parametrize("operation", ["tempfile.mkstemp", "os.replace", "Path.unlink"])
def test_progress_io_failures_do_not_raise(tmp_path, operation):
    path = tmp_path / "progress.json"
    with patch(f"ownmail.download_progress.{operation}", side_effect=OSError("unavailable")):
        progress = DownloadProgress(path)
        progress.advance(downloaded=1)
        progress.finish()
    progress.flush()
    assert snapshot(path)["downloaded"] == 1


@pytest.mark.parametrize(
    "error,context,reason",
    [
        (KeyringLocked(PRIVATE_DETAIL), "authenticating", "keychain_locked"),
        (KeyringError(PRIVATE_DETAIL), "authenticating", "keychain"),
        (PermissionError(PRIVATE_DETAIL), "archive", "storage"),
        (OSError(errno.ENOSPC, PRIVATE_DETAIL), "downloading", "storage"),
        (OSError(PRIVATE_DETAIL), "archive", "storage"),
        (sqlite3.OperationalError(PRIVATE_DETAIL), "archive", "index"),
        (TimeoutError(PRIVATE_DETAIL), "authenticating", "timeout"),
        (ConnectionError(PRIVATE_DETAIL), "checking", "network"),
        (RuntimeError(PRIVATE_DETAIL), "authenticating", "authentication"),
        (RuntimeError(PRIVATE_DETAIL), "checking", "checking"),
        (RuntimeError(PRIVATE_DETAIL), "downloading", "download"),
        (ValueError(PRIVATE_DETAIL), "config", "config"),
        (RuntimeError(PRIVATE_DETAIL), "starting", "failed"),
    ],
)
def test_exception_reporting_uses_fixed_reasons_without_counting_unattempted_mail(tmp_path, error, context, reason):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    progress.fail_exception(error, context=context)
    final = snapshot(path)
    assert final["failure_reason"] == FAILURE_REASONS[reason]
    assert final["errors"] == 0


@pytest.mark.parametrize(
    "error,reason",
    [
        (KeyringLocked(PRIVATE_DETAIL), "keychain_locked"),
        (RuntimeError(PRIVATE_DETAIL), "authentication"),
        (KeyboardInterrupt(), "interrupted"),
        (SystemExit(1), "failed"),
    ],
)
def test_authentication_failures_publish_phase_and_final_reason(cli_download, error, reason):
    _, path = cli_download
    mock_provider = provider()

    def authenticate():
        current = snapshot(path)
        assert current["phase"] == "authenticating"
        assert current["source"] == "Synthetic"
        assert current["downloaded"] == current["errors"] == 0
        raise error

    mock_provider.authenticate.side_effect = authenticate
    with patch("ownmail.providers.imap.ImapProvider", return_value=mock_provider):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
    final = snapshot(path)
    assert final["phase"] == "finished"
    assert final["failure_reason"] == FAILURE_REASONS[reason]
    assert final["errors"] == 0


@pytest.mark.parametrize("error,reason", [(PermissionError(PRIVATE_DETAIL), "storage"), (sqlite3.Error(), "index")])
def test_archive_open_failure_reports_no_failed_messages(cli_download, error, reason):
    _, path = cli_download
    with patch("ownmail.cli.EmailArchive", side_effect=error):
        with pytest.raises(SystemExit):
            main()
    final = snapshot(path)
    assert final["phase"] == "finished"
    assert final["errors"] == final["downloaded"] == 0
    assert final["failure_reason"] == FAILURE_REASONS[reason]


def test_busy_download_publishes_final_reason_before_archive_open(cli_download, tmp_path):
    _, path = cli_download
    with DownloadLock(tmp_path / "archive"):
        with patch("ownmail.cli.EmailArchive") as archive:
            with pytest.raises(SystemExit) as exc_info:
                main()
    archive.assert_not_called()
    assert exc_info.value.code == 75
    final = snapshot(path)
    assert final["phase"] == "finished"
    assert final["failure_reason"] == FAILURE_REASONS["busy"]
    assert final["errors"] == 0


def test_unknown_named_source_reports_setup_failure(cli_download, monkeypatch):
    _, path = cli_download
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--source", "Missing"])
    with pytest.raises(SystemExit):
        main()
    assert snapshot(path)["failure_reason"] == FAILURE_REASONS["setup"]
    assert snapshot(path)["errors"] == 0


@pytest.mark.parametrize("kind,auth", [("pop3", {}), ("gmail_api", {}), ("gmail_api", {"secret_ref": "invalid"})])
def test_skipped_source_setup_errors_have_no_failed_message_count(tmp_path, kind, auth):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    archive = EmailArchive(tmp_path / "archive", {})
    config = {"sources": [{"name": "Synthetic", "type": kind, "account": "private@example.com", "auth": auth}]}
    assert cmd_download(archive, config, progress=progress) is False
    assert snapshot(path)["failure_reason"] == FAILURE_REASONS["setup"]
    assert snapshot(path)["errors"] == 0


def test_zero_mail_run_finishes_successfully(cli_download):
    _, path = cli_download
    mock_provider = provider()

    def check(*args, **kwargs):
        assert snapshot(path)["phase"] == "scanning"
        return [], None

    mock_provider.get_new_message_ids.side_effect = check
    with patch("ownmail.providers.imap.ImapProvider", return_value=mock_provider):
        assert main() is None
    final = snapshot(path)
    assert final["phase"] == "finished"
    assert final["downloaded"] == final["skipped"] == final["errors"] == 0
    assert final["failure_reason"] is None


@pytest.mark.parametrize(
    "error,reason", [(TimeoutError(PRIVATE_DETAIL), "timeout"), (ConnectionError(PRIVATE_DETAIL), "network")]
)
def test_sequential_message_failures_preserve_safe_exception_classification(tmp_path, error, reason):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    archive = EmailArchive(tmp_path / "archive", {})
    mock_provider = provider(["failed"])
    mock_provider.download_message.side_effect = error
    result = archive.backup(mock_provider, progress=progress)
    assert result["error_count"] == 1
    assert snapshot(path)["errors"] == 1
    assert snapshot(path)["failure_reason"] == FAILURE_REASONS[reason]


def test_batch_exception_counts_every_affected_message(tmp_path):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    archive = EmailArchive(tmp_path / "archive", {})
    mock_provider = provider(["failed1", "failed2", "saved"])
    mock_provider.download_batch_size = 2
    mock_provider.download_messages_batch.side_effect = TimeoutError(PRIVATE_DETAIL)
    result = archive.backup(mock_provider, progress=progress)
    progress.flush()
    final = snapshot(path)
    assert result["success_count"] == final["downloaded"] == 1
    assert result["error_count"] == final["errors"] == 2
    assert final["failure_reason"] == FAILURE_REASONS["timeout"]


def test_batch_results_distinguish_saved_deleted_and_failed_messages(tmp_path):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    archive = EmailArchive(tmp_path / "archive", {})
    mock_provider = provider(["saved", "deleted", "missing", "failed"])
    mock_provider.download_batch_size = 4
    raw, labels = mock_provider.download_message.return_value
    mock_provider.download_messages_batch.return_value = {
        "saved": (raw, labels, None),
        "deleted": (None, [], "404 Not found " + PRIVATE_DETAIL),
        "failed": (None, [], PRIVATE_DETAIL),
    }
    result = archive.backup(mock_provider, progress=progress)
    progress.flush()
    final = snapshot(path)
    assert final["downloaded"] == result["success_count"] == 1
    assert final["skipped"] == 1
    assert final["errors"] == result["error_count"] == 2
    assert final["failure_reason"] == FAILURE_REASONS["download"]


def test_write_failure_counts_one_failed_message(tmp_path):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    archive = EmailArchive(tmp_path / "archive", {})
    with patch("ownmail.archive.os.write", side_effect=PermissionError(PRIVATE_DETAIL)):
        result = archive.backup(provider(["failed"]), progress=progress)
    final = snapshot(path)
    assert result["error_count"] == final["errors"] == 1
    assert final["downloaded"] == 0
    assert final["failure_reason"] == FAILURE_REASONS["storage"]


def test_index_failure_is_not_counted_as_a_completed_download(cli_download, tmp_path):
    _, path = cli_download
    with patch("ownmail.providers.imap.ImapProvider", return_value=provider(["saved"])):
        with patch(
            "ownmail.database.ArchiveDatabase.index_email", side_effect=sqlite3.OperationalError(PRIVATE_DETAIL)
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code == 1
    final = snapshot(path)
    assert final["downloaded"] == 0
    assert final["errors"] == 1
    assert final["failure_reason"] == FAILURE_REASONS["index"]
    assert len(list((tmp_path / "archive").rglob("*.eml"))) == 1


@pytest.mark.parametrize("error", [PermissionError(PRIVATE_DETAIL), OSError(errno.EIO, PRIVATE_DETAIL)])
def test_fatal_message_storage_exception_is_counted_once(cli_download, error):
    _, path = cli_download
    with patch("ownmail.providers.imap.ImapProvider", return_value=provider(["saved"])):
        with patch("ownmail.live_sync.sidecar.write_metadata", side_effect=error):
            with pytest.raises(SystemExit):
                main()
    final = snapshot(path)
    assert final["phase"] == "finished"
    assert final["errors"] == 1
    assert final["downloaded"] == 0
    assert final["failure_reason"] == FAILURE_REASONS["storage"]


@pytest.mark.parametrize("stage", ["checking", "downloading"])
def test_interrupt_flushes_current_counts_without_message_errors(cli_download, stage):
    _, path = cli_download
    mock_provider = provider(["saved", "interrupt"])
    if stage == "checking":
        mock_provider.get_new_message_ids.side_effect = KeyboardInterrupt
    else:
        raw = mock_provider.download_message.return_value

        def download(message_id):
            if message_id == "interrupt":
                signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            return raw

        mock_provider.download_message.side_effect = download
    with patch("ownmail.providers.imap.ImapProvider", return_value=mock_provider):
        with pytest.raises(SystemExit):
            main()
    final = snapshot(path)
    assert final["phase"] == "finished"
    assert final["errors"] == 0
    assert final["downloaded"] == int(stage == "downloading")
    assert final["failure_reason"] == FAILURE_REASONS["interrupted"]


def test_unwritable_progress_path_does_not_fail_a_download(cli_download, monkeypatch, tmp_path):
    _, path = cli_download
    monkeypatch.setattr(sys, "argv", [*sys.argv[:-1], str(tmp_path / "missing" / "progress.json")])
    with patch("ownmail.providers.imap.ImapProvider", return_value=provider(["saved"])):
        assert main() is None
    assert not path.exists()
    assert len(list((tmp_path / "archive").rglob("*.eml"))) == 1


def test_progress_option_is_hidden_from_help(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ownmail", "download", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert "progress-file" not in capsys.readouterr().out
