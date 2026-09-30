"""Live scans report work before capture without exposing message details."""

import json
import sqlite3
from dataclasses import replace

import pytest

from ownmail.archive import EmailArchive
from ownmail.download_progress import FAILURE_REASONS, DownloadProgress
from ownmail.live import LiveLookupError
from tests.test_live_providers import imap
from tests.test_live_sync import MailServer, message, source_status, sync


@pytest.mark.parametrize("web", [False, True])
def test_scan_progress_is_visible_and_bounded_before_first_capture(tmp_path, monkeypatch, capsys, web):
    now = [0.0]
    monkeypatch.setattr("ownmail.live_sync.time.monotonic", lambda: now[0])
    archive = EmailArchive(tmp_path / "archive")
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path) if web else None
    server = MailServer(
        [message(str(index), active_allowed=False) for index in range(999)] + [message("saved", state="eligible")]
    )
    read = server.read_live_message

    def listing(*, on_progress):
        assert "Scanning live mail before capture..." in capsys.readouterr().out
        if web:
            state = json.loads(path.read_text())
            assert state["phase"] == "scanning"
            assert state["scan_checked"] == state["downloaded"] == 0
        for count in range(1, 1001):
            now[0] = count / 500
            on_progress(count)
        assert capsys.readouterr().out.splitlines() == [
            "  Scanning live mail: 500 messages checked...",
            "  Scanning live mail: 1000 messages checked...",
        ]
        if web:
            state = json.loads(path.read_text())
            assert state["phase"] == "scanning"
            assert 0 < state["scan_checked"] <= 1000
            assert state["downloaded"] == 0
            assert server.account not in path.read_text()
        assert archive.db.get_email_count() == 0
        return MailServer.list_live_messages(server)

    def first_read(message_id):
        assert "Live scan complete: 1000 messages checked." in capsys.readouterr().out
        if web:
            state = json.loads(path.read_text())
            assert state["phase"] == "refreshing"
            assert state["scan_checked"] == 1000
            assert state["downloaded"] == 0
        return read(message_id)

    server.list_live_messages = listing
    server.read_live_message = first_read
    result = archive.backup(server, progress=progress, active_downloads=True)
    assert result["success_count"] == 1
    assert result["error_count"] == 0
    assert archive.db.get_email_count() == 1


def test_interrupted_scan_keeps_cached_mail_and_restarts_counts(tmp_path, capsys):
    archive = EmailArchive(tmp_path / "archive")
    server = MailServer([message()])
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path)
    assert archive.backup(server, progress=progress, active_downloads=True)["active_complete"]
    before = archive.active_cache().list_entries()
    server.reads.clear()
    capsys.readouterr()

    def interrupted(*, on_progress):
        assert json.loads(path.read_text())["scan_checked"] == 0
        on_progress(50)
        raise KeyboardInterrupt

    server.list_live_messages = interrupted
    result = archive.backup(server, progress=progress, active_downloads=True)
    assert result["interrupted"]
    assert not result["active_complete"]
    assert server.reads == []
    assert archive.active_cache().list_entries() == before
    assert not source_status(archive, server)["complete"]
    assert "Live scan complete" not in capsys.readouterr().out
    state = json.loads(path.read_text())
    assert state["scan_checked"] == 50
    assert "interrupted" in state["failure_reason"].lower()


@pytest.mark.parametrize("web", [False, True])
@pytest.mark.parametrize(
    "kind",
    [
        "owned",
        "discarded",
        "download_excluded",
        "active_excluded",
        "fresh_download_excluded",
        "fresh_active_excluded",
        "date_excluded",
    ],
)
def test_post_scan_skips_advance_bounded_private_progress(tmp_path, monkeypatch, capsys, web, kind):
    from ownmail import live_sync

    archive = EmailArchive(tmp_path / "archive")
    messages = [
        message(f"private-message-{index}", state="eligible" if kind in {"owned", "date_excluded"} else "active")
        for index in range(5)
    ]
    server = MailServer(messages)
    if kind == "owned":
        assert sync(archive, server)["success_count"] == 5
    elif kind == "discarded":
        server.messages = {item.message_id: replace(item, state="discarded") for item in messages}
    else:
        changes = {"download_allowed": False} if "download" in kind else {"active_allowed": False}
        server.messages = {item.message_id: replace(item, **changes) for item in messages}
        if kind.startswith("fresh_"):
            server.listed = messages
    server.reads.clear()
    capsys.readouterr()
    now = [0.0]
    monkeypatch.setattr("ownmail.live_sync.time.monotonic", lambda: now[0])
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path) if web else None
    observations = []
    known_owned = live_sync._known_owned

    def checking(*args):
        now[0] += 0.5
        if web:
            observations.append(json.loads(path.read_text()))
        return known_owned(*args)

    monkeypatch.setattr(live_sync, "_known_owned", checking)
    result = sync(archive, server, progress=progress, since="2024-01-02" if kind == "date_excluded" else None)
    output = capsys.readouterr().out
    updates = [line for line in output.splitlines() if line.startswith("  Refreshing live mail:")]
    assert len(updates) == 2
    assert "2 processed" in updates[0]
    assert "4 processed" in updates[1]
    assert "5 skipped" in output
    assert "private-message" not in output
    assert server.account not in output
    assert result["success_count"] == result["active_refreshed"] == result["error_count"] == 0
    assert archive.db.get_email_count() == (5 if kind == "owned" else 0)
    assert len(server.reads) == (
        5 if kind in {"discarded", "fresh_download_excluded", "fresh_active_excluded", "date_excluded"} else 0
    )
    if web:
        assert [state["skipped"] for state in observations] == list(range(5))
        assert json.loads(path.read_text())["skipped"] == 5


@pytest.mark.parametrize("state", ["active", "eligible"])
def test_post_scan_reports_active_refresh_and_capture_without_web(tmp_path, monkeypatch, capsys, state):
    archive = EmailArchive(tmp_path / "archive")
    server = MailServer([message(str(index), state=state) for index in range(5)])
    now = [0.0]
    monkeypatch.setattr("ownmail.live_sync.time.monotonic", lambda: now[0])
    read = server.read_live_message

    def reading(message_id):
        now[0] += 0.5
        return read(message_id)

    server.read_live_message = reading
    result = sync(archive, server)
    output = capsys.readouterr().out
    updates = [line for line in output.splitlines() if line.startswith("  Refreshing live mail:")]
    assert len(updates) == 2
    assert "2 processed" in updates[0]
    assert "4 processed" in updates[1]
    count = "2 Active refreshed" if state == "active" else "2 archived"
    assert count in updates[0]
    assert result["active_refreshed"] == (5 if state == "active" else 0)
    assert result["success_count"] == (5 if state == "eligible" else 0)


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    "error_type,reason",
    [
        (TimeoutError, "timeout"),
        (ConnectionError, "network"),
        (RuntimeError, "active_refresh"),
        (PermissionError, "storage"),
        (sqlite3.OperationalError, "index"),
    ],
)
def test_live_failures_keep_safe_categories_and_retryable_cache(tmp_path, capsys, wrapped, error_type, reason):
    archive = EmailArchive(tmp_path / "archive")
    original = message("private-message")
    server = MailServer([original])
    assert sync(archive, server)["active_complete"]
    before = archive.active_cache().list_entries()
    capsys.readouterr()
    failure = error_type("token=private-secret raw-body=private-content")
    if wrapped:
        outer = LiveLookupError("private-wrapper")
        outer.__cause__ = failure
        failure = outer
        if reason in {"storage", "index"}:
            reason = "active_refresh"
    server.listed = [original]
    server.messages[original.message_id] = failure
    path = tmp_path / "progress.json"
    result = sync(archive, server, progress=DownloadProgress(path))
    report = json.loads(path.read_text())
    assert report["failure_reason"] == FAILURE_REASONS[reason]
    assert report["errors"] == result["error_count"] == 1
    assert not result["active_complete"]
    assert archive.active_cache().list_entries() == before
    assert archive.db.get_email_count() == 0
    output = capsys.readouterr().out
    assert "private-" not in output + path.read_text()
    assert FAILURE_REASONS[reason] in output
    server.messages[original.message_id] = original
    assert sync(archive, server)["active_complete"]


def test_cyclic_lookup_error_is_generic_and_terminal_errors_are_bounded(tmp_path, monkeypatch, capsys):
    archive = EmailArchive(tmp_path / "archive")
    archive.active_cache(create=True)
    capsys.readouterr()
    server = MailServer([message(f"private-{index}") for index in range(100)])
    server.listed = list(server.messages.values())
    failure = LiveLookupError("private diagnostic")
    failure.__cause__ = failure
    server.messages = dict.fromkeys(server.messages, failure)
    monkeypatch.setattr("ownmail.live_sync.time.monotonic", lambda: 0.0)
    path = tmp_path / "progress.json"
    result = sync(archive, server, progress=DownloadProgress(path))
    output = capsys.readouterr().out
    assert result["error_count"] == 100
    assert json.loads(path.read_text())["failure_reason"] == FAILURE_REASONS["active_refresh"]
    assert len(output.splitlines()) <= 5
    assert "100 failed" in output
    assert "private" not in output


@pytest.mark.parametrize("failed", [False, True])
def test_imap_progress_counts_metadata_checks_including_duplicates_and_failures(monkeypatch, failed):
    provider = imap("Sent", gmail_labels=b"\\Sent")
    provider._conn.listing = ("OK", [b'(\\Sent) "/" "Sent"', b'(\\All) "/" "All Mail"'])
    original = provider._conn.uid
    checks = 0

    def uid(command, *args):
        nonlocal checks
        if command == "fetch":
            checks += 1
            if failed and checks == 2:
                raise OSError("private diagnostic")
        return original(command, *args)

    monkeypatch.setattr(provider._conn, "uid", uid)
    counts = []
    snapshot = provider.list_live_messages(on_progress=counts.append)
    assert counts[0] == 0
    assert counts[-1] == checks == 2
    assert 1 in counts
    assert counts == sorted(counts)
    assert snapshot.complete is not failed
    assert len(snapshot.messages) == 1


@pytest.mark.parametrize("failure", [None, OSError("unavailable"), KeyboardInterrupt()])
def test_imap_empty_exceptional_folder_search_keeps_scan_conservative(monkeypatch, failure):
    provider = imap("All Mail", gmail_labels=b"\\Sent")
    provider._conn.listing = ("OK", [b'(\\All) "/" "All Mail"', b'(\\Scheduled) "/" "Queue"'])
    original_select = provider._conn.select
    original_uid = provider._conn.uid
    selected = None
    counts = []

    def select(folder, readonly):
        nonlocal selected
        selected = folder
        return original_select(folder, readonly)

    def uid(command, *args):
        if command == "search" and selected == '"Queue"':
            assert args[1] == "ALL"
            assert counts[-1] == 1
            if failure:
                raise failure
            return "OK", [b""]
        return original_uid(command, *args)

    monkeypatch.setattr(provider._conn, "select", select)
    monkeypatch.setattr(provider._conn, "uid", uid)
    if isinstance(failure, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            provider.list_live_messages(on_progress=counts.append)
    else:
        snapshot = provider.list_live_messages(on_progress=counts.append)
        assert snapshot.complete is (failure is None)
        assert snapshot.messages[0].state == ("eligible" if failure is None else "unknown")
    assert counts[-1] == 1
    assert counts == sorted(counts)
