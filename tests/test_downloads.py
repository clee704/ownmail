"""Background downloads and schedules for the web interface."""

import json
import os
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from ownmail import downloads
from ownmail.downloads import DownloadManager


class Clock:
    def __init__(self):
        self.current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self, tz):
        return self.current


def make_process():
    process = Mock()
    process.returncode = None
    process.poll.side_effect = lambda: process.returncode
    process.send_signal.side_effect = lambda sig: setattr(process, "returncode", -sig)
    process.terminate.side_effect = lambda: setattr(process, "returncode", -signal.SIGTERM)
    process.kill.side_effect = lambda: setattr(process, "returncode", -signal.SIGKILL)

    def wait(timeout):
        if process.returncode is None:
            raise subprocess.TimeoutExpired("ownmail", timeout)
        return process.returncode

    process.wait.side_effect = wait
    return process


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(downloads, "datetime", clock)
    return clock


@pytest.fixture
def process(monkeypatch):
    process = make_process()
    monkeypatch.setattr(downloads.subprocess, "Popen", Mock(return_value=process))
    return process


@pytest.fixture
def manager(tmp_path, clock, process):
    manager = DownloadManager(tmp_path / "archive", str(tmp_path / "config.yaml"))
    yield manager
    manager.stop()


def wake_and_wait(manager, waiting):
    with manager._condition:
        waiting.clear()
        manager._condition.notify_all()
    assert waiting.wait(timeout=2), "Scheduler did not return to its wait"


def watch_waits(manager, monkeypatch):
    waiting = threading.Event()
    original_wait = manager._condition.wait

    def wait(timeout=None):
        waiting.set()
        return original_wait(timeout)

    monkeypatch.setattr(manager._condition, "wait", wait)
    return waiting


def write_progress(manager, **updates):
    report = {
        "phase": "downloading",
        "source": "work",
        "downloaded": 0,
        "skipped": 0,
        "errors": 0,
        "failure_reason": None,
        **updates,
    }
    manager._progress_path.write_text(json.dumps(report))


def test_unavailable_without_config(tmp_path):
    manager = DownloadManager(tmp_path, None, interval_minutes=15)
    assert manager.snapshot() == {
        "available": False,
        "running": False,
        "state": "idle",
        "interval_minutes": 15,
        "started_at": None,
        "finished_at": None,
        "next_run": None,
        "phase": None,
        "source": None,
        "downloaded": 0,
        "skipped": 0,
        "errors": 0,
        "failure_reason": None,
        "has_progress": False,
        "active_refreshed": 0,
        "active_complete": None,
    }
    assert not manager.start_download()
    manager.stop()


def test_manual_download_starts_asynchronously(manager, process, tmp_path, clock):
    assert manager.start_download()
    progress_path = manager._progress_path
    downloads.subprocess.Popen.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "ownmail",
            "--config",
            str((tmp_path / "config.yaml").resolve()),
            "--archive-root",
            str((tmp_path / "archive").resolve()),
            "download",
            "--progress-file",
            str(progress_path),
        ],
        stdin=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
    )
    process.wait.assert_not_called()
    assert progress_path.name == "progress.json"
    assert progress_path.parent.stat().st_mode & 0o777 == 0o700
    assert not progress_path.is_relative_to(tmp_path / "archive")
    status = manager.snapshot()
    assert status["running"]
    assert status["state"] == "running"
    assert status["started_at"] == clock.current.isoformat()
    assert status["finished_at"] is None
    assert status["next_run"] is None
    assert not status["has_progress"]
    assert status["phase"] == "starting"
    assert not manager.start_download()
    downloads.subprocess.Popen.assert_called_once()


@pytest.mark.parametrize("returncode, state", [(0, "succeeded"), (1, "failed"), (75, "busy"), (-2, "failed")])
def test_completion_records_cli_outcome(manager, process, clock, returncode, state):
    manager.start_download()
    clock.current += timedelta(seconds=12)
    process.returncode = returncode
    status = manager.snapshot()
    assert not status["running"]
    assert status["state"] == state
    assert status["finished_at"] == clock.current.isoformat()
    assert status["next_run"] is None
    assert status["phase"] == "finished"
    assert not status["has_progress"]
    assert bool(status["failure_reason"]) == (returncode != 0)


def test_concurrent_manual_requests_start_one_child(manager):
    barrier = threading.Barrier(2)

    def start():
        barrier.wait(timeout=2)
        return manager.start_download()

    with ThreadPoolExecutor(max_workers=2) as executor:
        requests = [executor.submit(start) for _ in range(2)]
        assert sorted(request.result(timeout=2) for request in requests) == [False, True]
    downloads.subprocess.Popen.assert_called_once()


def test_spawn_failure_is_reported_and_next_attempt_is_scheduled(manager, clock):
    manager.set_interval(15)
    downloads.subprocess.Popen.side_effect = OSError("cannot start process")
    assert not manager.start_download()
    status = manager.snapshot()
    assert not status["running"]
    assert status["state"] == "failed"
    assert status["finished_at"] == clock.current.isoformat()
    assert status["next_run"] == (clock.current + timedelta(minutes=15)).isoformat()
    assert "Could not start the downloader" in status["failure_reason"]
    progress_path = Path(downloads.subprocess.Popen.call_args.args[0][-1])
    assert not progress_path.parent.exists()


@pytest.mark.parametrize("value", [-1, True, 1.5, "15"])
def test_invalid_interval_is_rejected(manager, value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        manager.set_interval(value)
    assert manager.snapshot()["interval_minutes"] == 0


def test_interval_changes_preserve_active_download(manager, process, clock):
    manager.start_download()
    manager.set_interval(30)
    assert manager.snapshot()["next_run"] is None
    manager.set_interval(0)
    assert manager.snapshot()["running"]
    process.send_signal.assert_not_called()
    process.returncode = 0
    assert manager.snapshot()["next_run"] is None
    manager.set_interval(15)
    assert manager.snapshot()["next_run"] == (clock.current + timedelta(minutes=15)).isoformat()


def test_scheduler_runs_without_requests_and_waits_after_completion(manager, process, clock, monkeypatch):
    waiting = watch_waits(manager, monkeypatch)
    manager.set_interval(1)
    manager.start_scheduler()
    thread = manager._thread
    manager.start_scheduler()
    assert manager._thread is thread
    assert waiting.wait(timeout=2)
    downloads.subprocess.Popen.assert_not_called()

    clock.current += timedelta(minutes=1)
    wake_and_wait(manager, waiting)
    downloads.subprocess.Popen.assert_called_once()

    clock.current += timedelta(hours=2)
    wake_and_wait(manager, waiting)
    downloads.subprocess.Popen.assert_called_once()

    process.returncode = 0
    wake_and_wait(manager, waiting)
    assert manager.snapshot()["next_run"] == (clock.current + timedelta(minutes=1)).isoformat()
    downloads.subprocess.Popen.assert_called_once()

    clock.current += timedelta(minutes=1)
    wake_and_wait(manager, waiting)
    assert downloads.subprocess.Popen.call_count == 2


def test_disabling_schedule_wakes_scheduler_and_prevents_run(manager, clock, monkeypatch):
    waiting = watch_waits(manager, monkeypatch)
    manager.set_interval(1)
    manager.start_scheduler()
    assert waiting.wait(timeout=2)
    manager.set_interval(0)
    clock.current += timedelta(days=1)
    wake_and_wait(manager, waiting)
    downloads.subprocess.Popen.assert_not_called()
    assert manager.snapshot()["next_run"] is None


@pytest.mark.parametrize("requires_terminate, requires_kill", [(False, False), (True, False), (True, True)])
def test_stop_interrupts_and_escalates_with_bounded_waits(manager, process, requires_terminate, requires_kill):
    manager.set_interval(15)
    manager.start_download()
    if requires_terminate:
        process.send_signal.side_effect = None
    if requires_kill:
        process.terminate.side_effect = None
    manager.stop()
    process.send_signal.assert_called_once_with(signal.SIGINT)
    assert process.terminate.call_count == int(requires_terminate)
    assert process.kill.call_count == int(requires_kill)
    assert all(call.kwargs["timeout"] <= 5 for call in process.wait.call_args_list)
    assert not manager.snapshot()["running"]
    assert manager.snapshot()["next_run"] is None
    assert not manager._thread.is_alive()
    assert not manager.start_download()
    manager.start_scheduler()
    assert not manager._thread.is_alive()


@pytest.mark.parametrize("error", [ProcessLookupError(), ValueError("unsupported signal")])
def test_stop_falls_back_when_interrupt_is_unavailable(manager, process, error):
    manager.start_download()
    process.send_signal.side_effect = error
    manager.stop()
    process.terminate.assert_called_once()
    assert not manager.snapshot()["running"]


def test_stop_can_retry_when_child_does_not_exit(manager, process):
    manager.start_download()
    progress_path = manager._progress_path
    write_progress(manager, downloaded=3)
    process.send_signal.side_effect = None
    process.terminate.side_effect = None
    process.kill.side_effect = None
    manager.stop()
    assert manager.snapshot()["running"]
    assert manager.snapshot()["next_run"] is None
    assert progress_path.exists()
    process.send_signal.side_effect = lambda sig: setattr(process, "returncode", -sig)
    manager.stop()
    assert not manager.snapshot()["running"]
    assert manager.snapshot()["downloaded"] == 3
    assert not progress_path.parent.exists()


def test_live_reports_update_phases_and_cumulative_counts(manager):
    manager.start_download()
    write_progress(manager, phase="checking")
    first = manager.snapshot()
    assert first["has_progress"]
    assert first["phase"] == "checking"
    assert first["downloaded"] == 0
    write_progress(manager, downloaded=2, skipped=3, errors=1, source="personal")
    latest = manager.snapshot()
    assert latest["phase"] == "downloading"
    assert latest["source"] == "personal"
    assert latest["downloaded"] == 2
    assert latest["skipped"] == 3
    assert latest["errors"] == 1


def test_final_report_is_read_before_cleanup_and_retained(manager, process):
    manager.start_download()
    progress_path = manager._progress_path
    write_progress(manager, phase="finished", downloaded=8, skipped=2, errors=1, failure_reason="Could not connect.")
    process.returncode = 1
    final = manager.snapshot()
    assert final["state"] == "failed"
    assert final["downloaded"] == 8
    assert final["skipped"] == 2
    assert final["errors"] == 1
    assert final["failure_reason"] == "Could not connect."
    assert final["has_progress"]
    assert not progress_path.parent.exists()
    assert manager.snapshot() == final


def test_new_run_resets_previous_counts_and_failure(manager, process):
    manager.start_download()
    previous_path = manager._progress_path
    write_progress(manager, downloaded=5, skipped=4, errors=3, failure_reason="Could not connect.")
    process.returncode = 1
    assert manager.snapshot()["errors"] == 3
    process.returncode = None
    assert manager.start_download()
    latest = manager.snapshot()
    assert latest["phase"] == "starting"
    assert latest["source"] is None
    assert latest["downloaded"] == latest["skipped"] == latest["errors"] == 0
    assert latest["failure_reason"] is None
    assert not latest["has_progress"]
    assert manager._progress_path != previous_path
    assert not previous_path.parent.exists()


@pytest.mark.parametrize(
    "body",
    [
        b"{unfinished",
        b"\xff",
        b"[]",
        b"{}",
        b"[" * 2000 + b"]" * 2000,
        b'{"phase":"checking","downloaded":0,"skipped":0,"errors":0}' + b" " * 65536,
    ],
)
def test_missing_or_malformed_report_keeps_last_valid_progress(manager, body):
    manager.start_download()
    assert not manager.snapshot()["has_progress"]
    manager._progress_path.write_bytes(body)
    assert not manager.snapshot()["has_progress"]
    write_progress(manager, downloaded=7)
    previous = manager.snapshot()
    manager._progress_path.write_bytes(body)
    assert manager.snapshot() == previous
    manager._progress_path.unlink()
    assert manager.snapshot() == previous


@pytest.mark.parametrize(
    "updates",
    [
        {"phase": []},
        {"phase": "unknown"},
        {"downloaded": True},
        {"downloaded": -1},
        {"skipped": "1"},
        {"errors": None},
        {"source": 42},
        {"failure_reason": []},
    ],
)
def test_invalid_progress_fields_do_not_replace_reported_values(manager, updates):
    manager.start_download()
    write_progress(manager, downloaded=5)
    previous = manager.snapshot()
    write_progress(manager, **updates)
    assert manager.snapshot() == previous


def test_unknown_report_fields_cannot_change_manager_status(manager):
    manager.start_download()
    write_progress(manager, state="succeeded", running=False, stdout="unreported output", has_progress=False)
    status = manager.snapshot()
    assert status["state"] == "running"
    assert status["running"]
    assert status["has_progress"]
    assert "stdout" not in status


def test_temp_directory_failure_reports_safe_reason(manager, monkeypatch):
    def fail(**kwargs):
        raise OSError("private path")

    monkeypatch.setattr(downloads.tempfile, "TemporaryDirectory", fail)
    assert not manager.start_download()
    status = manager.snapshot()
    assert status["state"] == "failed"
    assert "Could not start the downloader" in status["failure_reason"]
    assert "private path" not in str(status)
    downloads.subprocess.Popen.assert_not_called()


def test_shutdown_collects_the_final_progress_flush(manager, process):
    manager.start_download()
    progress_path = manager._progress_path

    def finish(sig):
        write_progress(manager, phase="finished", downloaded=4, failure_reason="Download interrupted.")
        process.returncode = -sig

    process.send_signal.side_effect = finish
    manager.stop()
    status = manager.snapshot()
    assert status["downloaded"] == 4
    assert status["failure_reason"] == "Download interrupted."
    assert not progress_path.parent.exists()
