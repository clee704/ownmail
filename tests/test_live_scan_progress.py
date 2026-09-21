"""Live scans report work before capture without exposing message details."""

import json

import pytest

from ownmail.archive import EmailArchive
from ownmail.download_progress import DownloadProgress
from tests.test_live_providers import imap
from tests.test_live_sync import MailServer, message, source_status


@pytest.mark.parametrize("web", [False, True])
def test_scan_progress_is_visible_and_bounded_before_first_capture(tmp_path, monkeypatch, capsys, web):
    now = [0.0]
    monkeypatch.setattr("ownmail.live_sync.time.monotonic", lambda: now[0])
    archive = EmailArchive(tmp_path / "archive")
    path = tmp_path / "progress.json"
    progress = DownloadProgress(path) if web else None
    server = MailServer([message(str(index)) for index in range(999)] + [message("saved", state="eligible")])
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
    result = archive.backup(server, progress=progress, active_downloads=False)
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
