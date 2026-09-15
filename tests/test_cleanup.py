"""Cleanup crosses the ownership boundary only after fresh local and server checks."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ownmail import roles, sidecar
from ownmail.archive import EmailArchive
from ownmail.cleanup import run_cleanup
from ownmail.live import LiveLookupError
from ownmail.providers.base import TrashResult
from ownmail.thread_protection import ThreadProtection
from tests.test_live_sync import MailServer, message, owned_rows, sync


class CleanupServer(MailServer):
    def __init__(self, count=1):
        super().__init__(
            [
                message(str(i), state="eligible", identity=f"gmail:{i}", thread_id="thread", labels=("Saved",))
                for i in range(count)
            ]
        )
        self.moves = []
        self.on_thread = None
        self.on_trash = None
        self.account_failure = None

    def verify_cleanup_account(self):
        if self.account_failure:
            raise self.account_failure

    def check_thread_protection(self, message_id):
        if self.on_thread:
            return self.on_thread(message_id)
        return self.protection(message_id)

    def protection(self, message_id):
        active = any(m.state == "active" for m in self.messages.values())
        return ThreadProtection(
            self.source_name,
            self.account,
            message_id,
            thread_id="thread",
            complete=True,
            active=active,
            reason="Thread has Active mail" if active else None,
        )

    def trash_message(self, message_id, thread_id):
        self.moves.append(message_id)
        if self.on_trash:
            return self.on_trash(message_id, thread_id)
        self.messages[message_id] = replace(
            self.messages[message_id], state="discarded", roles=frozenset({roles.TRASH})
        )
        return TrashResult(self.source_name, self.account, message_id, thread_id, "trashed")


def source(server):
    return {"name": server.source_name, "account": server.account, "type": "gmail_api"}


@pytest.fixture
def captured(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    server = CleanupServer()
    assert sync(archive, server)["success_count"] == 1
    return archive, server


def run(archive, server, **kwargs):
    events = []
    result = run_cleanup(archive.archive_dir, source(server), server, report=events.append, **kwargs)
    return result, events


def files(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_preview_then_apply_and_retry_preserve_the_owned_archive(captured):
    archive, server = captured
    before = files(archive.archive_dir)
    preview, events = run(archive, server)
    assert preview == {"checked": 1, "eligible": 1, "held": 0, "trashed": 0, "errors": 0, "interrupted": False}
    assert events[0]["status"] == "eligible"
    assert datetime.fromisoformat(events[0]["checked_at"]).tzinfo
    assert server.moves == []

    applied, _ = run(archive, server, apply=True)
    assert applied["trashed"] == 1
    assert server.moves == ["0"]
    retried, _ = run(archive, server, apply=True)
    assert retried["held"] == 1
    assert server.moves == ["0"]
    assert files(archive.archive_dir) == before


def test_active_capture_label_edit_refresh_and_cleanup_keep_local_ownership(tmp_path):
    archive = EmailArchive(tmp_path / "archive")
    server = CleanupServer()
    filed = server.messages["0"]
    server.messages["0"] = replace(filed, state="active", roles=frozenset({roles.INBOX}))
    assert sync(archive, server)["active_refreshed"] == 1
    assert archive.search("is:active")
    assert run(archive, server, apply=True)[0]["checked"] == 0

    server.messages["0"] = filed
    assert sync(archive, server)["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    archive.set_local_labels(email_id, [])
    path = archive.archive_dir / filename
    before = (path.read_bytes(), sidecar.sidecar_path(path).read_bytes())
    server.messages["0"] = replace(filed, state="active", roles=frozenset({roles.INBOX}), labels=("Server edit",))
    sync(archive, server)
    assert run(archive, server, apply=True)[0]["held"] == 1
    server.messages["0"] = replace(filed, labels=("Server edit",))
    sync(archive, server)
    assert run(archive, server, apply=True)[0]["trashed"] == 1
    assert (path.read_bytes(), sidecar.sidecar_path(path).read_bytes()) == before
    assert archive.get_local_labels(email_id) == []
    assert [row[0] for row in archive.search("is:archived")] == [email_id]


@pytest.mark.parametrize(
    "change", ["active", "draft", "unknown", "trash", "spam", "missing", "identity", "body", "thread"]
)
def test_preview_does_not_authorize_a_changed_server_copy(captured, change):
    archive, server = captured
    assert run(archive, server)[0]["eligible"] == 1
    old = server.messages["0"]
    changes = {
        "active": {"state": "active", "roles": frozenset({roles.INBOX})},
        "draft": {"state": "eligible", "roles": frozenset({roles.DRAFTS})},
        "unknown": {"state": "unknown"},
        "trash": {"state": "discarded", "roles": frozenset({roles.TRASH})},
        "spam": {"state": "discarded", "roles": frozenset({roles.SPAM})},
        "identity": {"identity_token": "gmail:another"},
        "body": {"raw": b"Changed remote body"},
        "thread": {"thread_id": None},
    }
    if change == "missing":
        del server.messages["0"]
    else:
        server.messages["0"] = replace(old, **changes[change])
    result, _ = run(archive, server, apply=True)
    assert result["held"] == 1
    assert server.moves == []


@pytest.mark.parametrize("change", ["trash", "delete", "bytes", "metadata"])
def test_final_local_check_catches_changes_during_server_reads(captured, change):
    archive, server = captured
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename

    def check(message_id):
        if change == "trash":
            archive.trash_email(email_id)
        elif change == "delete":
            path.unlink()
        elif change == "bytes":
            path.write_bytes(b"Changed local body")
        else:
            sidecar.sidecar_path(path).unlink()
        return server.protection(message_id)

    server.on_thread = check
    result, _ = run(archive, server, apply=True)
    assert result["held"] == 1
    assert server.moves == []


def test_new_activity_between_candidates_protects_remaining_server_copies(tmp_path):
    archive, server = EmailArchive(tmp_path / "archive"), CleanupServer(2)
    sync(archive, server)

    def move(message_id, thread_id):
        server.messages[message_id] = replace(
            server.messages[message_id], state="discarded", roles=frozenset({roles.TRASH})
        )
        server.messages["reply"] = message("reply", state="active", identity="gmail:reply", thread_id=thread_id)
        return TrashResult(server.source_name, server.account, message_id, thread_id, "trashed")

    server.on_trash = move
    result, _ = run(archive, server, apply=True)
    assert (result["checked"], result["trashed"], result["held"]) == (2, 1, 1)
    assert len(server.moves) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_name", "other"),
        ("account", "other@example.test"),
        ("message_id", "other"),
        ("thread_id", "other"),
        ("complete", False),
        ("active", True),
        ("checked_at", datetime(2000, 1, 1)),
        ("checked_at", datetime(2000, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_unscoped_incomplete_or_stale_thread_observation_cannot_authorize_cleanup(captured, field, value):
    archive, server = captured
    server.on_thread = lambda message_id: replace(server.protection(message_id), **{field: value})
    result, _ = run(archive, server, apply=True)
    assert result["held"] == 1
    assert server.moves == []


def test_future_thread_time_is_not_a_current_observation(captured):
    archive, server = captured
    server.on_thread = lambda message_id: replace(
        server.protection(message_id), checked_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert run(archive, server, apply=True)[0]["held"] == 1
    assert server.moves == []


@pytest.mark.parametrize("failure", [TimeoutError(), KeyboardInterrupt()])
def test_unknown_post_outcome_rechecks_server_on_retry(captured, failure):
    archive, server = captured

    def move(message_id, thread_id):
        server.messages[message_id] = replace(
            server.messages[message_id], state="discarded", roles=frozenset({roles.TRASH})
        )
        raise failure

    server.on_trash = move
    result, events = run(archive, server, apply=True)
    assert result["errors"] == 1
    assert result["interrupted"] == isinstance(failure, KeyboardInterrupt)
    assert events[0]["status"] == "uncertain"
    assert run(archive, server, apply=True)[0]["held"] == 1
    assert server.moves == ["0"]


@pytest.mark.parametrize("status", ["uncertain", "denied", "invalid"])
def test_unconfirmed_trash_result_is_not_counted_as_success(captured, status):
    archive, server = captured
    server.on_trash = lambda mid, tid: TrashResult(server.source_name, server.account, mid, tid, status, "Unconfirmed")
    result, events = run(archive, server, apply=True)
    assert (result["eligible"], result["trashed"], result["errors"]) == (1, 0, 1)
    assert events[0]["status"] == (status if status != "invalid" else "uncertain")


def test_permission_denial_stops_the_source_without_retrying_other_candidates(tmp_path):
    archive, server = EmailArchive(tmp_path / "archive"), CleanupServer(2)
    sync(archive, server)
    server.on_trash = lambda mid, tid: TrashResult(
        server.source_name, server.account, mid, tid, "denied", "Request denied"
    )
    result, _ = run(archive, server, apply=True)
    assert (result["checked"], result["errors"], len(server.moves)) == (1, 1, 1)


def test_unverified_account_stops_before_any_server_message_or_mutation(tmp_path):
    archive, server = EmailArchive(tmp_path / "archive"), CleanupServer(2)
    sync(archive, server)
    server.reads.clear()
    server.account_failure = LiveLookupError("Account mismatch")
    result, _ = run(archive, server, apply=True)
    assert (result["checked"], result["errors"]) == (1, 1)
    assert server.reads == server.moves == []


def test_partial_result_continues_then_restart_does_not_repeat_confirmed_server_moves(tmp_path):
    archive, server = EmailArchive(tmp_path / "archive"), CleanupServer(2)
    sync(archive, server)

    def move(message_id, thread_id):
        server.messages[message_id] = replace(
            server.messages[message_id], state="discarded", roles=frozenset({roles.TRASH})
        )
        status = "uncertain" if len(server.moves) == 1 else "trashed"
        return TrashResult(server.source_name, server.account, message_id, thread_id, status)

    server.on_trash = move
    result, _ = run(archive, server, apply=True)
    assert (result["checked"], result["trashed"], result["errors"]) == (2, 1, 1)
    retried, _ = run(archive, server, apply=True)
    assert (retried["held"], retried["trashed"], retried["errors"]) == (2, 0, 0)
    assert len(server.moves) == 2


def test_interruption_between_candidates_leaves_completed_moves_resumable(tmp_path, monkeypatch):
    import ownmail.cleanup as cleanup

    archive, server = EmailArchive(tmp_path / "archive"), CleanupServer(2)
    sync(archive, server)
    original = cleanup.iter_candidate_ids

    def interrupted(*args, **kwargs):
        yield next(original(*args, **kwargs))
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(cleanup, "iter_candidate_ids", interrupted)
        result, _ = run(archive, server, apply=True)
    assert result["interrupted"]
    assert result["trashed"] == 1
    retried, _ = run(archive, server, apply=True)
    assert (retried["held"], retried["trashed"]) == (1, 1)
    assert not retried["interrupted"]
    assert len(server.moves) == 2


@pytest.mark.parametrize("field", ["source_name", "account", "message_id", "thread_id"])
def test_trash_response_for_another_copy_remains_unconfirmed(captured, field):
    archive, server = captured
    server.on_trash = lambda mid, tid: replace(
        TrashResult(server.source_name, server.account, mid, tid, "trashed"), **{field: "different"}
    )
    result, events = run(archive, server, apply=True)
    assert (result["trashed"], result["errors"]) == (0, 1)
    assert events[0]["status"] == "uncertain"


def test_local_label_edit_during_remote_checks_stays_owned(captured):
    archive, server = captured
    email_id, filename = owned_rows(archive)[0]

    def check(message_id):
        archive.set_local_labels(email_id, ["Local edit"])
        return server.protection(message_id)

    server.on_thread = check
    result, _ = run(archive, server, apply=True)
    assert result["trashed"] == 1
    assert sidecar.read_labels(archive.archive_dir / filename) == ["Local edit"]
    assert archive.db.get_labels_for_email(email_id) == ["Local edit"]


@pytest.mark.parametrize("field,value", [("source_name", "other"), ("account", "other@example.test")])
def test_provider_scope_must_match_the_selected_configuration(captured, field, value):
    archive, server = captured
    selected = source(server)
    setattr(server, field, value)
    result = run_cleanup(archive.archive_dir, selected, server, apply=True)
    assert result["held"] == 1
    assert server.moves == []


def test_actual_gmail_provider_interfaces_complete_only_the_synthetic_trash_move(tmp_path):
    from copy import deepcopy

    from tests.test_live_providers import gmail

    archive, provider = EmailArchive(tmp_path / "archive"), gmail(["Label_1"])
    assert sync(archive, provider)["success_count"] == 1
    current = provider._service.users().messages().get().execute.return_value
    provider._service.users().getProfile().execute.return_value = {"emailAddress": provider.account}
    provider._service.users().threads().get().execute.side_effect = lambda: {
        "id": "thread",
        "messages": [deepcopy(current)],
    }

    def move(**kwargs):
        assert kwargs == {"num_retries": 0}
        current["labelIds"] = ["TRASH"]
        return {"id": "a", "threadId": "thread", "labelIds": ["TRASH"]}

    provider._service.users().messages().trash().execute.side_effect = move
    before = files(archive.archive_dir)
    assert run_cleanup(archive.archive_dir, source(provider), provider)["eligible"] == 1
    provider._service.users().messages().trash().execute.assert_not_called()
    assert run_cleanup(archive.archive_dir, source(provider), provider, apply=True)["trashed"] == 1
    assert run_cleanup(archive.archive_dir, source(provider), provider, apply=True)["held"] == 1
    provider._service.users().messages().trash().execute.assert_called_once_with(num_retries=0)
    assert files(archive.archive_dir) == before


def test_imap_stays_held_without_authentication_or_remote_queries(captured):
    archive, server = captured
    imap = {**source(server), "type": "imap"}
    result = run_cleanup(archive.archive_dir, imap, None, apply=True)
    assert (result["checked"], result["held"], result["trashed"]) == (1, 1, 0)


def test_missing_index_is_reported_without_creating_archive_files(tmp_path):
    root = tmp_path / "missing"
    server = CleanupServer()
    events = []
    result = run_cleanup(root, source(server), server, apply=True, report=events.append)
    assert result["errors"] == 1
    assert events[0]["email_id"] is None
    assert not root.exists()
    assert server.moves == []
