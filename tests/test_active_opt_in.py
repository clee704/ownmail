"""Active synchronization requires explicit opt-in without changing legacy downloads."""

from unittest.mock import MagicMock, call

import pytest

from ownmail.archive import EmailArchive
from tests.test_live_sync import MailServer, message


def legacy_provider(kind, count=0):
    provider = MagicMock()
    provider.name = kind
    provider.source_name = "Synthetic"
    provider.account = "reader@example.test"
    provider.download_batch_size = 10 if kind == "gmail" else 25
    ids = [f"message-{index}" for index in range(count)]
    provider.get_new_message_ids.side_effect = [(ids, "next-cursor"), ([], "next-cursor")]
    provider.get_current_sync_state.side_effect = AssertionError("Candidate cursor must be retained")
    provider.list_live_messages.side_effect = AssertionError("Opt-out must not scan live mail")
    provider.read_live_messages.side_effect = AssertionError("Opt-out must not refresh live mail")

    def body(message_id):
        return (
            f"From: sender@example.test\r\nSubject: {message_id}\r\n"
            f"Message-ID: <{message_id}@example.test>\r\n\r\nBody {message_id}".encode(),
            ["Saved"],
        )

    provider.download_message.side_effect = body
    provider.download_messages_batch.side_effect = lambda batch: {key: (*body(key), None) for key in batch}
    return provider, ids


@pytest.mark.parametrize("kind", ["gmail", "imap"])
@pytest.mark.parametrize("options", [{}, {"active_downloads": None}, {"active_downloads": False}])
def test_opt_out_keeps_incremental_candidates_and_batched_downloads(tmp_path, monkeypatch, kind, options):
    archive = EmailArchive(tmp_path / "archive")
    provider, ids = legacy_provider(kind, 51)
    cache = MagicMock(side_effect=AssertionError("Opt-out must not initialize the Active cache"))
    monkeypatch.setattr(archive, "active_cache", cache)

    first = archive.backup(provider, **options)
    assert first == {"success_count": 51, "error_count": 0, "interrupted": False, "failed_ids": []}
    assert archive.db.get_email_count() == 51
    size = provider.download_batch_size
    assert provider.download_messages_batch.call_args_list == [
        call(ids[offset : offset + size]) for offset in range(0, 50, size)
    ]
    provider.download_message.assert_called_once_with(ids[-1])

    repeated = archive.backup(provider, **options)
    assert repeated == {"success_count": 0, "error_count": 0, "interrupted": False, "failed_ids": []}
    assert provider.get_new_message_ids.call_args_list == [
        call(None, since=None, until=None),
        call("next-cursor", since=None, until=None),
    ]
    assert provider.download_messages_batch.call_count == 50 // size
    provider.download_message.assert_called_once_with(ids[-1])
    provider.list_live_messages.assert_not_called()
    provider.read_live_messages.assert_not_called()
    cache.assert_not_called()
    assert not (tmp_path / ".archive-active").exists()


def test_explicit_opt_in_refreshes_active_mail_without_legacy_candidates(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    server = MailServer([message()])
    server.get_new_message_ids = MagicMock(side_effect=AssertionError("Active sync must use live observations"))

    result = archive.backup(server, active_downloads=True)

    assert result["active_complete"]
    assert result["active_refreshed"] == 1
    assert result["success_count"] == 0
    assert archive.active_cache().list_entries()[0]["provider_id"] == "1"
    server.get_new_message_ids.assert_not_called()


@pytest.mark.parametrize("options", [{}, {"active_downloads": False}])
def test_opt_out_after_active_sync_preserves_existing_cache_and_owned_files(tmp_path, monkeypatch, options):
    archive = EmailArchive(tmp_path / "archive")
    server = MailServer([message(), message("owned", state="eligible")])
    assert archive.backup(server, active_downloads=True)["active_complete"]
    cache = archive.active_cache()

    def saved_files(root):
        return {
            path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*")
            if path.is_file()
        }

    cached = saved_files(cache.cache_dir)
    owned = {path: path.read_bytes() for path in archive.archive_dir.rglob("*.eml")}
    assert cached and owned
    monkeypatch.setattr(
        archive, "active_cache", MagicMock(side_effect=AssertionError("Opt-out must not open existing Active cache"))
    )
    provider, _ = legacy_provider("imap")

    result = archive.backup(provider, **options)

    assert result["error_count"] == 0
    assert result["success_count"] == 0
    assert saved_files(cache.cache_dir) == cached
    assert {path: path.read_bytes() for path in archive.archive_dir.rglob("*.eml")} == owned
    archive.active_cache.assert_not_called()
    provider.list_live_messages.assert_not_called()
