"""Active refresh reporting stays distinct from archive capture."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from ownmail import downloads
from ownmail.cli import cmd_download
from ownmail.config import validate_config
from ownmail.download_progress import DownloadProgress
from tests import test_download_ui, test_downloads

clock = test_downloads.clock
process = test_downloads.process
manager = test_downloads.manager
shell_app = test_download_ui.shell_app
download_browser = test_download_ui.download_browser


def source(kind="imap", **updates):
    return {
        "name": "Synthetic",
        "type": kind,
        "account": "reader@example.com",
        "host": "mail.example.com",
        "auth": {"secret_ref": "keychain:synthetic"},
        **updates,
    }


@pytest.mark.parametrize("kind", ["imap", "gmail_api"])
@pytest.mark.parametrize("settings, enabled", [({}, True), ({"active_downloads": False}, False)])
def test_cli_forwards_active_download_default_and_source_override(tmp_path, kind, settings, enabled):
    archive = MagicMock()
    archive.archive_dir = tmp_path / "archive"
    archive.auto_expire_trash.return_value = 0
    archive.db.get_email_count.return_value = 0
    archive.backup.return_value = {"success_count": 0, "error_count": 0, "interrupted": False}
    provider = Mock()
    constructor = "ownmail.cli.GmailProvider" if kind == "gmail_api" else "ownmail.providers.imap.ImapProvider"
    progress = DownloadProgress(tmp_path / "progress.json")
    with patch(constructor, return_value=provider):
        assert cmd_download(archive, {"sources": [source(kind, **settings)]}, progress=progress)
    assert archive.backup.call_args.args == (provider,)
    assert archive.backup.call_args.kwargs["active_downloads"] is enabled
    assert archive.backup.call_args.kwargs["progress"] is progress


@pytest.mark.parametrize("completions", [(True, False), (False, True), (False, False), (True, True)])
def test_cumulative_progress_cannot_hide_an_incomplete_source(tmp_path, completions):
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    for name, complete in zip(("First", "Second"), completions):
        progress.set_phase("refreshing", name)
        progress.advance(downloaded=1, active_refreshed=3)
        progress.set_active_complete(complete)
    progress.finish()
    final = json.loads(path.read_text())
    assert final["active_complete"] is all(completions)
    assert final["downloaded"] == 2
    assert final["active_refreshed"] == 6
    assert final["errors"] == final["skipped"] == 0
    assert final["phase"] == "finished"
    assert final["source"] == "Second"


@pytest.mark.parametrize("trigger", ["manual", "scheduled"])
def test_existing_download_path_reports_active_refresh(manager, process, clock, monkeypatch, trigger):
    if trigger == "manual":
        assert manager.start_download()
    else:
        waiting = test_downloads.watch_waits(manager, monkeypatch)
        manager.set_interval(1)
        manager.start_scheduler()
        assert waiting.wait(timeout=2)
        clock.current += timedelta(minutes=1)
        test_downloads.wake_and_wait(manager, waiting)
    command = downloads.subprocess.Popen.call_args.args[0]
    assert command[1:3] == ["-m", "ownmail"]
    assert command[-3:] == ["download", "--progress-file", str(manager._progress_path)]
    reporter = DownloadProgress(manager._progress_path)
    reporter.set_phase("refreshing", "Synthetic")
    reporter.advance(downloaded=2, active_refreshed=4)
    reporter.flush()
    live = manager.snapshot()
    assert live["running"]
    assert live["phase"] == "refreshing"
    assert live["downloaded"] == 2
    assert live["active_refreshed"] == 4
    assert live["active_complete"] is None
    reporter.set_active_complete(False)
    reporter.finish()
    process.returncode = 0
    final = manager.snapshot()
    assert final["state"] == "succeeded"
    assert final["active_complete"] is False
    assert final["active_refreshed"] == 4


@pytest.mark.parametrize(
    "updates",
    [
        {"active_refreshed": -1},
        {"active_refreshed": True},
        {"active_refreshed": 1.5},
        {"active_refreshed": "1"},
        {"active_refreshed": None},
        {"active_complete": 0},
        {"active_complete": 1},
        {"active_complete": "false"},
        {"active_complete": []},
    ],
)
def test_invalid_active_progress_preserves_last_valid_snapshot(manager, updates):
    manager.start_download()
    test_downloads.write_progress(manager, phase="refreshing", downloaded=2, active_refreshed=3, active_complete=False)
    previous = manager.snapshot()
    test_downloads.write_progress(manager, downloaded=9, **updates)
    assert manager.snapshot() == previous


@pytest.mark.parametrize("value", ["", "  ", None, True, 12, [], {}])
def test_invalid_active_cache_directory_is_reported(value):
    assert validate_config({"sources": [source()], "active_cache_dir": value}) == [
        "active_cache_dir must be a nonempty directory path"
    ]


@pytest.mark.parametrize("value", [None, "false", 0, 1, []])
def test_source_active_download_setting_requires_boolean(value):
    assert validate_config({"sources": [source(active_downloads=value)]}) == [
        "Source 'Synthetic': active_downloads must be true or false"
    ]


@pytest.mark.parametrize("enabled", [True, False])
def test_active_settings_accept_directory_path_and_boolean(enabled):
    assert validate_config({"sources": [source(active_downloads=enabled)], "active_cache_dir": "~/mail-cache"}) == []


def test_running_refresh_shows_active_counts_before_completion(shell_app, download_browser):
    app, _ = shell_app
    test_download_ui.run_download_browser(
        app,
        download_browser,
        """
        state = {...state, running: true, state: 'running', has_progress: true, phase: 'refreshing',
            source: 'Synthetic', downloaded: 2, active_refreshed: 4, active_complete: null};
        await refresh();
        await waitStatus('Refreshing live mail from Synthetic');
        assert.equal(await counts.textContent(), '2 archived · 4 Active refreshed · 0 failed');
        assert.doesNotMatch(await page.locator('#ownmail-download-message').textContent(), /Capture finished/);
        """,
    )


@pytest.mark.parametrize("complete", [True, False])
def test_finished_download_distinguishes_active_refresh_completeness(shell_app, download_browser, complete):
    app, _ = shell_app
    test_download_ui.run_download_browser(
        app,
        download_browser,
        """
        state = {...state, running: false, state: 'succeeded', has_progress: true, phase: 'finished',
            downloaded: 2, active_refreshed: 4, active_complete: __COMPLETE__};
        await refresh();
        await waitStatus(__COMPLETE__ ? 'Capture finished. Active mail refreshed.' : 'Active refresh incomplete.');
        assert.equal(await counts.textContent(), '2 archived · 4 Active refreshed · 0 failed');
        const message = await page.locator('#ownmail-download-message').textContent();
        if (!__COMPLETE__) assert.doesNotMatch(message, /Active mail refreshed|current|up to date/i);
        """.replace("__COMPLETE__", json.dumps(complete)),
    )
