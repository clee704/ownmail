"""Synthetic Gmail Trash requests preserve identity and uncertain outcomes."""

import http.client
import io
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from ownmail.live import LiveLookupError
from ownmail.providers.base import TrashResult
from ownmail.providers.cleanup_auth import CLEANUP_SCOPES
from ownmail.providers.gmail import GmailProvider
from ownmail.providers.imap import ImapProvider


@pytest.fixture
def provider():
    result = GmailProvider("reader@example.test", MagicMock(), source_name="mail")
    result._service = MagicMock()
    result._service.users().getProfile().execute.return_value = {"emailAddress": result.account}
    result._cleanup_credentials = Credentials(
        "synthetic-access-token",
        refresh_token="synthetic-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="synthetic-client",
        client_secret="synthetic-client-secret",
        scopes=list(CLEANUP_SCOPES),
        granted_scopes=list(CLEANUP_SCOPES),
        expiry=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
    )
    result._service.reset_mock()
    return result


@pytest.fixture
def transport(monkeypatch):
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = 200
    response.read.return_value = json.dumps({"id": "message", "threadId": "thread", "labelIds": ["TRASH"]}).encode()
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr("ownmail.providers.gmail.http.client.HTTPSConnection", factory)
    return factory, connection


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


def test_gmail_trash_confirms_scoped_message_move_with_no_automatic_retry(provider, transport):
    factory, connection = transport
    result = provider.trash_message("message", "thread")
    assert result == TrashResult("mail", "reader@example.test", "message", "thread", "trashed")
    factory.assert_called_once_with("gmail.googleapis.com", timeout=60)
    connection.request.assert_called_once_with(
        "POST",
        "/gmail/v1/users/me/messages/message/trash",
        headers={"authorization": "Bearer synthetic-access-token"},
    )
    connection.close.assert_called_once_with()
    assert provider._service.mock_calls == []
    assert provider._keychain.mock_calls == []


@pytest.mark.parametrize("identity", [(None, "thread"), ("", "thread"), ("message", None), ("message", " ")])
def test_missing_cleanup_identity_cannot_issue_trash_request(provider, transport, identity):
    factory, _ = transport
    result = provider.trash_message(*identity)
    assert result.status == "denied"
    factory.assert_not_called()
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
def test_unconfirmed_trash_responses_are_uncertain_and_never_retried(provider, transport, response):
    _, connection = transport
    connection.getresponse.return_value.read.return_value = json.dumps(response).encode()
    result = provider.trash_message("message", "thread")
    assert result.status == "uncertain"
    assert (result.source_name, result.account, result.message_id, result.thread_id) == (
        "mail",
        "reader@example.test",
        "message",
        "thread",
    )
    connection.request.assert_called_once()
    connection.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("status", "outcome"),
    [(400, "denied"), (401, "denied"), (403, "denied"), (404, "uncertain"), (429, "uncertain"), (500, "uncertain")],
)
def test_trash_http_failures_are_not_success_or_missing_message(provider, transport, status, outcome):
    _, connection = transport
    connection.getresponse.return_value.status = status
    connection.getresponse.return_value.read.return_value = b'{"error":{"message":"private response"}}'
    result = provider.trash_message("message", "thread")
    assert result.status == outcome
    assert "private" not in result.reason
    if status == 403:
        assert "quota" in result.reason
        assert "consent" not in result.reason
    connection.request.assert_called_once()
    connection.close.assert_called_once_with()


@pytest.mark.parametrize("phase", ["request", "getresponse", "read"])
def test_trash_transport_failure_is_uncertain_without_exposing_details(provider, transport, phase):
    _, connection = transport
    operation = connection.getresponse.return_value.read if phase == "read" else getattr(connection, phase)
    operation.side_effect = TimeoutError("private response")
    result = provider.trash_message("message", "thread")
    assert result.status == "uncertain"
    assert "private" not in result.reason
    connection.request.assert_called_once()
    connection.close.assert_called_once_with()


def test_cleanup_interruption_propagates_without_retry(provider, transport):
    _, connection = transport
    provider._service.users().getProfile().execute.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        provider.verify_cleanup_account()
    connection.getresponse.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        provider.trash_message("message", "thread")
    connection.request.assert_called_once()
    connection.close.assert_called_once_with()


@pytest.mark.parametrize("invalid", ["missing", "expired", "scope"])
def test_mutation_never_refreshes_or_connects_with_invalid_credentials(provider, transport, monkeypatch, invalid):
    creds = provider._cleanup_credentials
    refresh = MagicMock(side_effect=AssertionError("Mutation must not refresh"))
    monkeypatch.setattr(creds, "refresh", refresh)
    if invalid == "missing":
        del provider._cleanup_credentials
    elif invalid == "expired":
        creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    else:
        creds._granted_scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    result = provider.trash_message("message", "thread")
    assert result.status == "denied"
    refresh.assert_not_called()
    transport[0].assert_not_called()


def test_message_id_is_one_url_segment(provider, transport):
    _, connection = transport
    provider.trash_message("message/other?query=#fragment", "thread")
    assert connection.request.call_args.args[1] == (
        "/gmail/v1/users/me/messages/message%2Fother%3Fquery%3D%23fragment/trash"
    )


@pytest.mark.parametrize(
    ("wire_response", "outcome"),
    [
        (b"", "uncertain"),
        (b"broken status\r\n\r\n", "uncertain"),
        (b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n", "denied"),
        (b"HTTP/1.1 302 Found\r\nLocation: https://other.example.test/\r\nContent-Length: 0\r\n\r\n", "uncertain"),
    ],
)
def test_real_http_transport_never_retransmits_lost_or_rejected_post(provider, monkeypatch, wire_response, outcome):
    transmissions = []
    sockets = []

    class Socket:
        closed = False

        def sendall(self, data):
            transmissions.append(data)

        def makefile(self, mode):
            return io.BytesIO(wire_response)

        def close(self):
            self.closed = True

    def connect(connection):
        connection.sock = Socket()
        sockets.append(connection.sock)

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", connect)
    refresh = MagicMock(side_effect=AssertionError("Mutation must not refresh"))
    monkeypatch.setattr(provider._cleanup_credentials, "refresh", refresh)
    result = provider.trash_message("message", "thread")
    assert result.status == outcome
    assert len(transmissions) == 1
    assert transmissions[0].startswith(b"POST /gmail/v1/users/me/messages/message/trash HTTP/1.1\r\n")
    assert len(sockets) == 1 and sockets[0].closed
    refresh.assert_not_called()
    assert provider._service.mock_calls == []
