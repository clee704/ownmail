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
@pytest.mark.parametrize(
    "settings, enabled", [({}, False), ({"active_downloads": False}, False), ({"active_downloads": True}, True)]
)
def test_cli_forwards_active_download_default_and_source_override(tmp_path, kind, settings, enabled):
    archive = MagicMock()
    archive.archive_dir = tmp_path / "archive"
    archive.auto_expire_trash.return_value = 0
    archive.db.get_email_count.return_value = 0
    archive.backup.return_value = {"success_count": 0, "error_count": 0, "interrupted": False}
    provider = Mock()
    constructor = "ownmail.cli.GmailProvider" if kind == "gmail_api" else "ownmail.providers.imap.ImapProvider"
    progress = DownloadProgress(tmp_path / "progress.json")
    key = "active_exclude_labels" if kind == "gmail_api" else "active_exclude_folders"
    configured = source(kind, **settings, **{key: ["Retained", "Case-sensitive"]})
    with patch(constructor, return_value=provider) as provider_constructor:
        assert cmd_download(archive, {"sources": [configured]}, progress=progress)
    assert provider_constructor.call_args.kwargs[key] == configured[key]
    other = "active_exclude_folders" if kind == "gmail_api" else "active_exclude_labels"
    assert other not in provider_constructor.call_args.kwargs
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


def test_scan_progress_is_throttled_until_phase_changes(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("ownmail.download_progress.time.monotonic", lambda: now[0])
    path = tmp_path / "progress.json"
    reporter = DownloadProgress(path)
    reporter.set_scan_progress(0)
    reporter.set_phase("scanning", "Synthetic")
    reporter.set_scan_progress(1)
    assert json.loads(path.read_text())["scan_checked"] == 0
    now[0] = 0.3
    reporter.set_scan_progress(100)
    assert json.loads(path.read_text())["scan_checked"] == 100
    reporter.set_scan_progress(101)
    reporter.set_phase("refreshing")
    final = json.loads(path.read_text())
    assert final["scan_checked"] == 101
    assert final["phase"] == "refreshing"
    assert final["source"] == "Synthetic"
    assert final["downloaded"] == final["errors"] == 0
    assert path.stat().st_mode & 0o777 == 0o600


def test_new_source_resets_scan_count_and_retains_capture_counts(manager):
    manager.start_download()
    reporter = DownloadProgress(manager._progress_path)
    reporter.set_scan_progress(100)
    reporter.set_phase("scanning", "First")
    first = manager.snapshot()
    assert first["phase"] == "scanning"
    assert first["scan_checked"] == 100
    assert first["downloaded"] == 0
    reporter.advance(downloaded=2, active_refreshed=4)
    reporter.set_scan_progress(0)
    reporter.set_phase("scanning", "Second")
    second = manager.snapshot()
    assert second["source"] == "Second"
    assert second["scan_checked"] == 0
    assert second["downloaded"] == 2
    assert second["active_refreshed"] == 4


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
    assert live["scan_checked"] == 0
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
        {"scan_checked": -1},
        {"scan_checked": True},
        {"scan_checked": 1.5},
        {"scan_checked": "1"},
        {"scan_checked": None},
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


@pytest.mark.parametrize("source", [None, "Synthetic"])
def test_running_scan_shows_checked_count_before_capture(shell_app, download_browser, source):
    app, _ = shell_app
    test_download_ui.run_download_browser(
        app,
        download_browser,
        """
        state = {...state, running: true, state: 'running', has_progress: true, phase: 'scanning',
            source: __SOURCE__, scan_checked: 0, active_refreshed: 0, active_complete: null};
        await refresh();
        await waitStatus(__SOURCE__ ? 'Scanning live mail from Synthetic' : 'Scanning live mail…');
        assert.equal(await progress.isVisible(), true);
        assert.equal(await counts.textContent(), '0 checked · 0 archived · 0 Active refreshed · 0 failed');
        state = {...state, scan_checked: 123};
        await refresh();
        await waitStatus('123 checked');
        assert.equal(await counts.textContent(), '123 checked · 0 archived · 0 Active refreshed · 0 failed');
        state = {...state, phase: 'refreshing', downloaded: 2, active_refreshed: 4};
        await refresh();
        await waitStatus('Refreshing live mail');
        assert.equal(await counts.textContent(), '2 archived · 4 Active refreshed · 0 failed');
        """.replace("__SOURCE__", json.dumps(source)),
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
