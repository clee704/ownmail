"""IMAP state observations control the handoff from cache to owned files."""

from ownmail import roles
from ownmail.archive import EmailArchive
from tests.test_live_providers import RAW, imap
from tests.test_live_sync import owned_rows, sync


def test_imap_pending_message_is_captured_only_after_submission(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = imap("Sent", b"$SubmitPending $Submitted")
    pending = sync(archive, provider)
    assert pending["success_count"] == 0
    assert pending["active_refreshed"] == 1
    entry = archive.active_cache().list_entries()[0]
    assert entry["state"] == "active"
    assert roles.DRAFTS not in entry["roles"]
    assert owned_rows(archive) == []

    provider._conn.flags = b"$Submitted"
    submitted = sync(archive, provider)
    assert submitted["success_count"] == 1
    assert submitted["active_complete"]
    assert archive.active_cache().list_entries() == []
    email_id, filename = owned_rows(archive)[0]
    assert (archive.archive_dir / filename).read_bytes() == RAW
    assert archive.db.get_labels_for_email(email_id) == ["Sent"]
    assert len(archive.search("is:archived")) == 1


def test_imap_filed_message_checks_pending_state_again_before_capture(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    provider = imap("Projects")
    read = provider.read_live_message

    def queue_before_read(message_id):
        provider._conn.flags = b"$SubmitPending"
        return read(message_id)

    provider.read_live_message = queue_before_read
    result = sync(archive, provider)
    assert result["success_count"] == 0
    assert result["active_refreshed"] == 1
    assert owned_rows(archive) == []
    assert archive.active_cache().list_entries()[0]["state"] == "active"
