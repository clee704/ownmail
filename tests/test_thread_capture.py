"""Integration between archive capture and read-only thread protection."""

from unittest.mock import MagicMock

import pytest

from ownmail import sidecar
from ownmail.archive import EmailArchive
from ownmail.providers.gmail import GmailProvider


@pytest.mark.parametrize("candidate_label", ["SENT", "Label_filed"])
@pytest.mark.parametrize("active_label", ["INBOX", "DRAFT"])
def test_capture_freezes_owned_copy_while_server_thread_activity_changes(tmp_path, candidate_label, active_label):
    provider = GmailProvider(account="test@example.com", source_name="test", keychain=MagicMock())
    provider._service = MagicMock()
    candidate = {"id": "sent", "threadId": "thread", "labelIds": [candidate_label]}
    sibling = {"id": "received", "threadId": "thread", "labelIds": [active_label]}
    thread = {"id": "thread", "historyId": "1", "messages": [candidate, sibling]}
    provider._service.users.return_value.messages.return_value.get.return_value.execute.side_effect = lambda: dict(
        candidate
    )
    provider._service.users.return_value.threads.return_value.get.return_value.execute.side_effect = lambda: thread
    provider.get_new_message_ids = MagicMock(return_value=(["sent"], "cursor"))
    provider.download_message = MagicMock(
        return_value=(
            b"From: test@example.com\r\nSubject: Sent reply\r\nDate: Mon, 15 Jan 2024 10:00:00 +0000\r\n\r\nReply",
            [candidate_label, "Owned label"],
        )
    )
    archive = EmailArchive(tmp_path, {})

    assert provider.check_thread_protection("sent").active
    result = archive.backup(provider)
    assert result["success_count"] == 1
    assert result["error_count"] == 0
    owned = next(tmp_path.rglob("*.eml"))
    original = (owned.read_bytes(), sidecar.sidecar_path(owned).read_bytes())
    assert sidecar.read_labels(owned) == [candidate_label, "Owned label"]

    # A discarded member no longer holds the sent reply's server copy.
    sibling["labelIds"] = ["TRASH", active_label]
    thread["historyId"] = "2"
    assert provider.check_thread_protection("sent").allows_cleanup == (candidate_label == "SENT")

    candidate["labelIds"] = [candidate_label, "INBOX", "Label_changed_on_server"]
    thread["historyId"] = "3"
    protection = provider.check_thread_protection("sent")
    assert protection.active
    assert not protection.allows_cleanup
    assert archive.backup(provider)["success_count"] == 0
    provider.download_message.assert_called_once_with("sent")
    assert (owned.read_bytes(), sidecar.sidecar_path(owned).read_bytes()) == original
    assert len(list(tmp_path.rglob("*.eml"))) == 1
