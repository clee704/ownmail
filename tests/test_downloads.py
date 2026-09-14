"""Background downloads and schedules for the web interface."""

import os
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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
    }
    assert not manager.start_download()
    manager.stop()


def test_manual_download_starts_asynchronously(manager, process, tmp_path, clock):
    assert manager.start_download()
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
        ],
        stdin=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
    )
    process.wait.assert_not_called()
    status = manager.snapshot()
    assert status["running"]
    assert status["state"] == "running"
    assert status["started_at"] == clock.current.isoformat()
    assert status["finished_at"] is None
    assert status["next_run"] is None
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
    process.send_signal.side_effect = None
    process.terminate.side_effect = None
    process.kill.side_effect = None
    manager.stop()
    assert manager.snapshot()["running"]
    assert manager.snapshot()["next_run"] is None
    process.send_signal.side_effect = lambda sig: setattr(process, "returncode", -sig)
    manager.stop()
    assert not manager.snapshot()["running"]
