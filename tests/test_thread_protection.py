"""Current server thread protection and its provider limits."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ownmail import roles
from ownmail.providers.gmail import GmailProvider
from ownmail.providers.imap import ImapProvider
from ownmail.thread_protection import ThreadProtection


def _message(message_id="candidate", labels=None):
    return {"id": message_id, "threadId": "thread", "labelIds": ["SENT"] if labels is None else labels}


def _provider(members=None, **kwargs):
    provider = GmailProvider(account=kwargs.pop("account", "person@example.com"), keychain=MagicMock(), **kwargs)
    provider._service = MagicMock()
    members = [_message()] if members is None else members
    provider._service.users().messages().get().execute.return_value = deepcopy(members[0])
    provider._service.users().threads().get().execute.return_value = {
        "id": "thread",
        "historyId": "100",
        "messages": deepcopy(members),
    }
    provider._service.reset_mock()
    return provider


def test_result_is_immutable_and_unknown_by_default():
    result = ThreadProtection("source", "person@example.com", "candidate")
    assert not result.allows_cleanup
    assert result.checked_at.tzinfo == timezone.utc
    with pytest.raises(FrozenInstanceError):
        result.complete = True


@pytest.mark.parametrize("role", [roles.INBOX, roles.DRAFTS, roles.TRASH, roles.SPAM])
def test_candidate_role_prevents_cleanup_even_without_thread_activity(role):
    result = ThreadProtection("source", "person@example.com", "candidate", complete=True)
    assert result.allows_cleanup
    assert not replace(result, candidate_roles=frozenset({role})).allows_cleanup


@pytest.mark.parametrize("host", ["imap.gmail.com", "imap.example.com"])
def test_imap_cannot_establish_clearance_from_its_visible_thread_state(host):
    provider = ImapProvider("person@example.com", MagicMock(), host=host, source_name="source")
    provider._conn = MagicMock()
    result = provider.check_thread_protection("Sent:1")
    assert (result.source_name, result.account, result.message_id) == ("source", "person@example.com", "Sent:1")
    assert not result.complete
    assert not result.allows_cleanup
    assert "cannot establish" in result.reason
    assert provider._conn.mock_calls == []


def test_sent_thread_has_a_scoped_current_observation():
    provider = _provider([_message(), _message("reply")], source_name="source")
    before = datetime.now(timezone.utc)
    result = provider.check_thread_protection("candidate")
    assert result.allows_cleanup
    assert not result.active
    assert result.reason is None
    assert (result.source_name, result.account, result.message_id, result.thread_id) == (
        "source",
        "person@example.com",
        "candidate",
        "thread",
    )
    assert result.candidate_roles == frozenset({roles.SENT})
    assert result.revision == "100"
    assert before <= result.checked_at <= datetime.now(timezone.utc)
    provider._service.users().messages().get.assert_called_once_with(
        userId="me", id="candidate", format="minimal", fields="id,threadId,labelIds"
    )
    provider._service.users().threads().get.assert_called_once_with(
        userId="me", id="thread", format="minimal", fields="id,historyId,messages(id,threadId,labelIds)"
    )


@pytest.mark.parametrize("label", ["INBOX", "DRAFT"])
def test_active_members_hold_even_when_capture_ignores_their_roles(label):
    provider = _provider([_message(), _message("reply", [label, "SENT"])], include_labels=False, exclude_roles=[])
    result = provider.check_thread_protection("candidate")
    assert result.complete
    assert result.active
    assert not result.allows_cleanup
    provider._service.users().labels.assert_not_called()
    provider._service.users().messages().list.assert_not_called()


@pytest.mark.parametrize("label", ["TRASH", "SPAM"])
def test_discarded_thread_members_override_active_labels(label):
    provider = _provider([_message(), _message("reply", [label, "INBOX", "DRAFT"])])
    result = provider.check_thread_protection("candidate")
    assert result.complete
    assert not result.active
    assert result.allows_cleanup


def test_discarded_candidate_is_never_cleared():
    provider = _provider([_message(labels=["TRASH", "INBOX"])])
    result = provider.check_thread_protection("candidate")
    assert result.complete
    assert not result.active
    assert not result.allows_cleanup


@pytest.mark.parametrize("labels", [["SCHEDULED"], ["FUTURE_STATE"]])
def test_unrecognized_system_state_holds_the_thread(labels):
    provider = _provider([_message(), _message("reply", labels)])
    provider._service.users().labels().list().execute.return_value = {
        "labels": [{"id": label, "type": "system"} for label in labels]
    }
    result = provider.check_thread_protection("candidate")
    assert not result.complete
    assert not result.active
    assert not result.allows_cleanup
    assert "finished state is unknown" in result.reason


@pytest.mark.parametrize("labels", [[], ["UNREAD", "IMPORTANT"]])
def test_filed_members_without_active_state_clear_the_thread(labels):
    provider = _provider([_message(labels=labels), _message("reply", labels)])
    result = provider.check_thread_protection("candidate")
    assert result.complete
    assert not result.active
    assert result.allows_cleanup


def test_known_activity_survives_another_members_unknown_state():
    provider = _provider([_message(), _message("active", ["INBOX"]), _message("unknown", ["FUTURE_STATE"])])
    provider._service.users().labels().list().execute.return_value = {"labels": []}
    result = provider.check_thread_protection("candidate")
    assert result.active
    assert not result.complete
    assert not result.allows_cleanup


def test_omitted_labels_mean_empty_reported_state():
    member = _message()
    del member["labelIds"]
    provider = _provider([member])
    result = provider.check_thread_protection("candidate")
    assert result.candidate_roles == frozenset()
    assert result.complete
    assert result.allows_cleanup


@pytest.mark.parametrize("active_label", ["INBOX", "DRAFT"])
def test_new_reply_and_later_role_changes_protect_next_candidate_after_enumeration(active_label):
    provider = _provider([_message(), _message("next", [])])
    provider._list_message_ids = MagicMock(return_value=["candidate", "next"])
    provider._enumerate_excluded = MagicMock(return_value=frozenset())
    assert provider.get_all_message_ids(since="2000-01-01", until="2001-01-01") == ["candidate", "next"]
    assert provider.check_thread_protection("candidate").allows_cleanup

    thread = provider._service.users().threads().get().execute.return_value
    thread["messages"].append(_message("reply", [active_label]))
    thread["historyId"] = "101"
    provider._service.users().messages().get().execute.return_value = deepcopy(thread["messages"][1])
    active = provider.check_thread_protection("next")
    assert active.active
    assert not active.allows_cleanup
    assert active.message_id == "next"
    assert active.revision == "101"

    thread["messages"][2]["labelIds"] = []
    thread["historyId"] = "102"
    cleared = provider.check_thread_protection("next")
    assert cleared.allows_cleanup
    assert cleared.revision == "102"
    assert cleared.checked_at >= active.checked_at
    provider._list_message_ids.assert_called_once()


def test_candidate_role_change_between_reads_holds_until_rechecked():
    provider = _provider()
    thread = provider._service.users().threads().get().execute.return_value
    thread["messages"][0]["labelIds"] = ["INBOX", "SENT"]
    changed = provider.check_thread_protection("candidate")
    assert not changed.complete
    assert changed.active
    assert not changed.allows_cleanup
    assert "roles changed" in changed.reason

    provider._service.users().messages().get().execute.return_value = deepcopy(thread["messages"][0])
    current = provider.check_thread_protection("candidate")
    assert current.complete
    assert current.active
    assert current.candidate_roles == frozenset({roles.INBOX, roles.SENT})
    assert not current.allows_cleanup


def test_failed_thread_read_preserves_known_candidate_activity():
    provider = _provider([_message(labels=["INBOX"])])
    provider._service.users().threads().get().execute.side_effect = RuntimeError
    result = provider.check_thread_protection("candidate")
    assert result.active
    assert not result.complete
    assert not result.allows_cleanup


@pytest.mark.parametrize("prefix", [[], ["SENT"]])
def test_custom_labels_require_a_fresh_user_type_in_the_catalog(prefix):
    provider = _provider([_message(labels=prefix + ["custom"])], include_labels=False)
    catalog = {"labels": [{"id": "custom", "type": "user"}]}
    provider._service.users().labels().list().execute.return_value = catalog
    assert provider.check_thread_protection("candidate").allows_cleanup
    catalog["labels"][0]["type"] = "system"
    assert not provider.check_thread_protection("candidate").allows_cleanup
    assert provider._service.users().labels().list().execute.call_count == 2


@pytest.mark.parametrize("catalog", [{}, {"labels": [{"id": "SCHEDULED", "type": "system"}]}])
def test_sent_does_not_override_an_unrecognized_system_state(catalog):
    provider = _provider([_message(labels=["SENT", "SCHEDULED"])])
    provider._service.users().labels().list().execute.return_value = catalog
    result = provider.check_thread_protection("candidate")
    assert not result.complete
    assert not result.allows_cleanup
    assert "finished state is unknown" in result.reason


@pytest.mark.parametrize(
    "catalog",
    [
        None,
        {"labels": None},
        {"labels": [None]},
        {"labels": [{"id": 1, "type": "user"}]},
        {"labels": [{"id": "custom", "type": "unexpected"}]},
        {"labels": [{"id": "custom", "type": "user"}, {"id": "custom", "type": "system"}]},
    ],
)
def test_malformed_label_catalog_does_not_establish_finished_state(catalog):
    provider = _provider([_message(labels=["SENT", "custom"])])
    provider._service.users().labels().list().execute.return_value = catalog
    result = provider.check_thread_protection("candidate")
    assert not result.allows_cleanup
    assert result.reason == "Malformed label catalog"


@pytest.mark.parametrize(
    ("account", "source_name"), [("another@example.com", "source"), ("person@example.com", "another")]
)
def test_matching_provider_ids_do_not_share_account_or_source_state(account, source_name):
    first = _provider(source_name="source")
    second = _provider([_message(labels=["INBOX"])], account=account, source_name=source_name)
    clear = first.check_thread_protection("candidate")
    held = second.check_thread_protection("candidate")
    assert clear.allows_cleanup
    assert not held.allows_cleanup
    assert (clear.account, clear.source_name) != (held.account, held.source_name)
    assert first.check_thread_protection("candidate").allows_cleanup


@pytest.mark.parametrize("stage", ["messages", "threads", "labels"])
@pytest.mark.parametrize(
    "failure", [RuntimeError("request failed"), TimeoutError("request timed out"), ValueError("bad")]
)
def test_request_failure_is_not_an_empty_or_clear_thread(stage, failure):
    provider = _provider([_message(labels=["SENT", "custom"])])
    endpoint = getattr(provider._service.users(), stage)()
    request = endpoint.list() if stage == "labels" else endpoint.get()
    request.execute.side_effect = failure
    result = provider.check_thread_protection("candidate")
    assert not result.complete
    assert not result.allows_cleanup
    assert result.reason == "Gmail thread lookup failed"


@pytest.mark.parametrize("stage", ["messages", "threads"])
def test_interrupts_propagate(stage):
    provider = _provider()
    getattr(provider._service.users(), stage)().get().execute.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        provider.check_thread_protection("candidate")


@pytest.mark.parametrize("message_id", [None, "", " "])
def test_missing_candidate_id_never_queries_gmail(message_id):
    provider = _provider()
    result = provider.check_thread_protection(message_id)
    assert not result.allows_cleanup
    assert result.reason == "Missing candidate identity"
    assert provider._service.mock_calls == []


@pytest.mark.parametrize(
    "candidate",
    [None, [], {}, {"id": "candidate", "threadId": ""}, _message("different"), {"id": 1, "threadId": "thread"}],
)
def test_malformed_candidate_identity_holds(candidate):
    provider = _provider()
    provider._service.users().messages().get().execute.return_value = candidate
    result = provider.check_thread_protection("candidate")
    assert not result.complete
    assert not result.allows_cleanup
    provider._service.users().threads().get.assert_not_called()


@pytest.mark.parametrize("stage", ["messages", "threads"])
@pytest.mark.parametrize("labels", [None, "SENT", {}, [None], [1], [""]])
def test_malformed_label_values_hold(stage, labels):
    provider = _provider()
    if stage == "messages":
        provider._service.users().messages().get().execute.return_value["labelIds"] = labels
    else:
        provider._service.users().threads().get().execute.return_value["messages"][0]["labelIds"] = labels
    result = provider.check_thread_protection("candidate")
    assert not result.complete
    assert not result.allows_cleanup
    assert result.reason == "Malformed message labels"


@pytest.mark.parametrize(
    "thread",
    [
        None,
        [],
        {},
        {"id": "another", "messages": [_message()]},
        {"id": "thread"},
        {"id": "thread", "messages": []},
        {"id": "thread", "messages": {}},
        {"id": "thread", "messages": [_message("other")]},
        {"id": "thread", "messages": [_message(), _message()]},
        {"id": "thread", "messages": [dict(_message(), threadId="different")]},
        {"id": "thread", "messages": [_message(), None]},
        {"id": "thread", "messages": [_message()], "historyId": 1},
        {"id": "thread", "messages": [_message()], "historyId": ""},
    ],
)
def test_incomplete_or_inconsistent_thread_snapshot_holds(thread):
    provider = _provider()
    provider._service.users().threads().get().execute.return_value = thread
    result = provider.check_thread_protection("candidate")
    assert not result.complete
    assert not result.allows_cleanup
    assert result.reason


def test_revision_is_optional_and_does_not_authorize_reusing_the_check():
    provider = _provider()
    del provider._service.users().threads().get().execute.return_value["historyId"]
    first = provider.check_thread_protection("candidate")
    assert first.allows_cleanup
    assert first.revision is None
    provider._service.users().threads().get().execute.side_effect = RuntimeError
    assert not provider.check_thread_protection("candidate").allows_cleanup
