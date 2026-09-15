"""Synthetic Gmail Trash requests preserve identity and uncertain outcomes."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from ownmail.live import LiveLookupError
from ownmail.providers.base import TrashResult
from ownmail.providers.gmail import GmailProvider
from ownmail.providers.imap import ImapProvider


@pytest.fixture
def provider():
    result = GmailProvider("reader@example.test", MagicMock(), source_name="mail")
    result._service = MagicMock()
    result._service.users().getProfile().execute.return_value = {"emailAddress": result.account}
    result._service.users().messages().trash().execute.return_value = {
        "id": "message",
        "threadId": "thread",
        "labelIds": ["TRASH"],
    }
    result._service.reset_mock()
    return result


def test_trash_result_is_immutable_and_unconfirmed_by_default():
    result = TrashResult("mail", "reader@example.test", "message")
    assert result.status == "uncertain"
    with pytest.raises(FrozenInstanceError):
        result.status = "trashed"


@pytest.mark.parametrize("host", ["imap.gmail.com", "imap.example.test"])
def test_unsupported_cleanup_never_uses_imap_commands(host):
    provider = ImapProvider("reader@example.test", MagicMock(), host=host, source_name="mail")
    provider._conn = MagicMock()
    with pytest.raises(LiveLookupError, match="cannot verify"):
        provider.verify_cleanup_account()
    result = provider.trash_message("message", "thread")
    assert result == TrashResult(
        "mail", "reader@example.test", "message", "thread", "denied", "Provider does not support server cleanup"
    )
    assert provider._conn.mock_calls == []
    assert provider._keychain.mock_calls == []


def test_cleanup_account_verification_is_fresh_and_allows_only_case_differences(provider):
    profile = provider._service.users().getProfile().execute
    profile.return_value = {"emailAddress": "Reader@Example.Test"}
    assert provider.verify_cleanup_account() is None
    provider._service.users().getProfile.assert_called_with(userId="me", fields="emailAddress")
    profile.return_value = {"emailAddress": "other@example.test"}
    with pytest.raises(LiveLookupError, match="account could not be verified"):
        provider.verify_cleanup_account()
    assert profile.call_count == 2
    assert provider._keychain.mock_calls == []


@pytest.mark.parametrize("profile", [None, [], {}, {"emailAddress": None}, {"emailAddress": 42}, {"emailAddress": ""}])
def test_incomplete_profile_cannot_verify_cleanup_account(provider, profile):
    provider._service.users().getProfile().execute.return_value = profile
    with pytest.raises(LiveLookupError, match="account could not be verified"):
        provider.verify_cleanup_account()
    provider._service.users().messages().trash.assert_not_called()


@pytest.mark.parametrize(
    "error", [RuntimeError("private response"), HttpError(SimpleNamespace(status=404, reason="not found"), b"{}")]
)
def test_profile_errors_are_held_without_exposing_provider_details(provider, error):
    provider._service.users().getProfile().execute.side_effect = error
    with pytest.raises(LiveLookupError, match="^Gmail cleanup account lookup failed$"):
        provider.verify_cleanup_account()
    provider._service.users().messages().trash.assert_not_called()


def test_gmail_trash_confirms_scoped_message_move_with_no_automatic_retry(provider):
    result = provider.trash_message("message", "thread")
    assert result == TrashResult("mail", "reader@example.test", "message", "thread", "trashed")
    provider._service.users().messages().trash.assert_called_once_with(userId="me", id="message")
    provider._service.users().messages().trash().execute.assert_called_once_with(num_retries=0)
    provider._service.users().messages().delete.assert_not_called()
    provider._service.users().threads.assert_not_called()
    assert provider._keychain.mock_calls == []


@pytest.mark.parametrize("identity", [(None, "thread"), ("", "thread"), ("message", None), ("message", " ")])
def test_missing_cleanup_identity_cannot_issue_trash_request(provider, identity):
    result = provider.trash_message(*identity)
    assert result.status == "denied"
    assert provider._service.mock_calls == []


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"id": "different", "threadId": "thread", "labelIds": ["TRASH"]},
        {"id": "message", "threadId": "different", "labelIds": ["TRASH"]},
        {"id": "message", "threadId": "thread"},
        {"id": "message", "threadId": "thread", "labelIds": ["INBOX"]},
        {"id": "message", "threadId": "thread", "labelIds": "TRASH"},
        {"id": "message", "threadId": "thread", "labelIds": [None]},
    ],
)
def test_unconfirmed_trash_responses_are_uncertain_and_never_retried(provider, response):
    provider._service.users().messages().trash().execute.return_value = response
    result = provider.trash_message("message", "thread")
    assert result.status == "uncertain"
    assert (result.source_name, result.account, result.message_id, result.thread_id) == (
        "mail",
        "reader@example.test",
        "message",
        "thread",
    )
    provider._service.users().messages().trash().execute.assert_called_once_with(num_retries=0)


@pytest.mark.parametrize(
    ("status", "outcome"),
    [(400, "denied"), (401, "denied"), (403, "denied"), (404, "uncertain"), (429, "uncertain"), (500, "uncertain")],
)
def test_trash_http_failures_are_not_success_or_missing_message(provider, status, outcome):
    provider._service.users().messages().trash().execute.side_effect = HttpError(
        SimpleNamespace(status=status, reason="private response"), b'{"error":{"message":"private response"}}'
    )
    result = provider.trash_message("message", "thread")
    assert result.status == outcome
    assert "private" not in result.reason
    if status == 403:
        assert "quota" in result.reason
        assert "consent" not in result.reason
    provider._service.users().messages().trash().execute.assert_called_once_with(num_retries=0)


def test_trash_transport_failure_is_uncertain_without_exposing_details(provider):
    provider._service.users().messages().trash().execute.side_effect = TimeoutError("private response")
    result = provider.trash_message("message", "thread")
    assert result.status == "uncertain"
    assert "private" not in result.reason
    provider._service.users().messages().trash().execute.assert_called_once_with(num_retries=0)


def test_cleanup_interruption_propagates_without_retry(provider):
    provider._service.users().getProfile().execute.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        provider.verify_cleanup_account()
    provider._service.users().messages().trash().execute.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        provider.trash_message("message", "thread")
    provider._service.users().messages().trash().execute.assert_called_once_with(num_retries=0)
