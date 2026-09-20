"""Cleanup authorization and apply cross the CLI, keychain, and Gmail boundaries."""

import base64
import http.client
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ownmail import cli, sidecar
from ownmail.archive import EmailArchive
from ownmail.keychain import SERVICE, KeychainStorage
from ownmail.providers import cleanup_auth, gmail
from tests.test_cleanup import files
from tests.test_cleanup_cli import invoke
from tests.test_keychain_cleanup import ACCOUNT, CLEANUP_KEY, MODIFY, READONLY, TOKEN_KEY, credentials
from tests.test_live_sync import MailServer, message, owned_rows, sync


@pytest.fixture
def cleanup_backend(tmp_path, monkeypatch):
    records = {}
    backend = SimpleNamespace(
        get_password=Mock(side_effect=lambda service, key: records.get((service, key))),
        set_password=Mock(side_effect=lambda service, key, value: records.__setitem__((service, key), value)),
        delete_password=Mock(side_effect=AssertionError("Cleanup must not remove credentials")),
    )
    monkeypatch.setattr("ownmail.keychain.keyring", backend)
    storage = KeychainStorage()
    storage.save_gmail_token(ACCOUNT, credentials(token="synthetic-readonly", scopes=[READONLY]))
    storage.save_client_credentials(
        "gmail",
        json.dumps({"installed": {"client_id": "synthetic-client", "client_secret": "synthetic-client-secret"}}),
    )

    saved = message("saved", state="eligible", identity="gmail:saved", labels=("Saved",), thread_id="thread")
    archive = EmailArchive(tmp_path / "archive")
    assert sync(archive, MailServer([saved]))["success_count"] == 1
    email_id, filename = owned_rows(archive)[0]
    path = archive.archive_dir / filename
    sidecar.write_metadata(path, sidecar.read_metadata(path) | {"labels": ["Local only"]})
    archive.db.set_labels_for_email(email_id, ["Local only"])
    config = {
        "archive_root": str(archive.archive_dir),
        "sources": [
            {
                "name": "mail",
                "account": ACCOUNT,
                "type": "gmail_api",
                "auth": {"secret_ref": f"keychain:{TOKEN_KEY}"},
            }
        ],
    }
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "EmailArchive", Mock(side_effect=AssertionError("Cleanup cannot initialize archives")))

    grant = credentials(granted_scopes=[MODIFY])
    flow = SimpleNamespace(
        run_local_server=Mock(return_value=grant),
        oauth2session=SimpleNamespace(token={"access_token": grant.token, "scope": MODIFY}),
    )
    consent = Mock(return_value=flow)
    monkeypatch.setattr(cleanup_auth.InstalledAppFlow, "from_client_config", consent)
    case = SimpleNamespace(
        archive=archive,
        records=records,
        backend=backend,
        storage=storage,
        grant=grant,
        flow=flow,
        consent=consent,
        profile=ACCOUNT,
        labels=["Label_saved"],
        services=[],
        moves=[],
        events=[],
        connections=[],
    )

    def build(api, version, *, credentials):
        assert (api, version) == ("gmail", "v1")
        service = Mock()
        case.services.append(credentials)

        def profile():
            case.events.append("profile")
            return {"emailAddress": case.profile}

        def current():
            return {"id": "saved", "threadId": "thread", "labelIds": list(case.labels)}

        def read(*, userId, id, format, **kwargs):
            assert userId == "me" and id == "saved"

            def execute():
                case.events.append(format)
                result = current()
                if format == "raw":
                    result["raw"] = base64.urlsafe_b64encode(saved.raw).decode()
                return result

            return SimpleNamespace(execute=execute)

        def thread(*, userId, id, **kwargs):
            assert userId == "me" and id == "thread"

            def execute():
                case.events.append("thread")
                return {"id": "thread", "messages": [current()]}

            return SimpleNamespace(execute=execute)

        users = service.users.return_value
        users.getProfile.return_value.execute.side_effect = profile
        users.messages.return_value.get.side_effect = read
        users.messages.return_value.trash.side_effect = AssertionError("Cleanup cannot use a retrying transport")
        users.messages.return_value.delete.side_effect = AssertionError("Cleanup cannot permanently delete mail")
        users.threads.return_value.get.side_effect = thread
        users.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"id": "Label_saved", "name": "Server label", "type": "user"},
                {"id": "TRASH", "name": "TRASH", "type": "system"},
            ]
        }
        return service

    def connect(host, *, timeout):
        assert host == "gmail.googleapis.com" and timeout == 60
        connection = Mock()
        case.connections.append(connection)

        def request(method, path, *, headers):
            assert method == "POST" and path == "/gmail/v1/users/me/messages/saved/trash"
            creds = case.services[-1]
            assert creds.scopes == [MODIFY] and MODIFY in creds.granted_scopes
            assert headers["authorization"] == f"Bearer {creds.token}"
            case.events.append("trash")
            case.moves.append("saved")
            case.labels = ["TRASH"]

        connection.request.side_effect = request
        connection.getresponse.return_value = SimpleNamespace(
            status=200,
            read=lambda: json.dumps({"id": "saved", "threadId": "thread", "labelIds": ["TRASH"]}).encode(),
        )
        return connection

    monkeypatch.setattr(cleanup_auth, "build", build)
    monkeypatch.setattr(gmail, "build", build)
    monkeypatch.setattr(http.client, "HTTPSConnection", connect)
    return case


def test_authorize_preview_apply_and_restart_preserve_owned_data(cleanup_backend, monkeypatch, capsys):
    case = cleanup_backend
    before_files = files(case.archive.archive_dir)
    before_records = case.records.copy()
    capsys.readouterr()

    invoke(monkeypatch, "authorize-cleanup", "--source", "mail")

    assert "Cleanup authorization saved" in capsys.readouterr().out
    assert case.consent.call_args.kwargs["scopes"] == [MODIFY]
    assert case.flow.run_local_server.call_args.kwargs["login_hint"] == ACCOUNT
    persisted = json.loads(case.records[SERVICE, CLEANUP_KEY])
    assert persisted["scopes"] == persisted["granted_scopes"] == [MODIFY]
    assert persisted["expiry"] == "2030-01-02T03:04:05.006789+00:00"
    assert {key: value for key, value in case.records.items() if key != (SERVICE, CLEANUP_KEY)} == before_records
    assert files(case.archive.archive_dir) == before_files
    assert case.moves == []
    case.consent.side_effect = AssertionError("Preview and apply cannot open cleanup consent")

    invoke(monkeypatch, "cleanup", "--source", "mail")

    preview = capsys.readouterr().out
    assert "Eligible: 1" in preview and "Moved to server Trash: 0" in preview
    assert case.services[-1].scopes == [READONLY]
    assert case.services[-1].token == "synthetic-readonly"
    assert case.moves == []
    case.events.clear()

    invoke(monkeypatch, "cleanup", "--source", "mail", "--apply")

    applied = capsys.readouterr().out
    assert "Moved to server Trash: 1" in applied and "Errors: 0" in applied
    assert case.services[-1].scopes == case.services[-1].granted_scopes == [MODIFY]
    assert case.services[-1].token == case.grant.token
    assert case.services[-1] is not case.grant
    assert case.events == ["profile", "profile", "raw", "minimal", "thread", "trash"]
    assert case.moves == ["saved"]
    assert len(case.connections) == 1
    case.connections[0].request.assert_called_once()
    case.connections[0].close.assert_called_once()

    invoke(monkeypatch, "cleanup", "--source", "mail", "--apply")

    restarted = capsys.readouterr().out
    assert "Held: 1" in restarted and "Moved to server Trash: 0" in restarted
    assert case.moves == ["saved"]
    assert case.consent.call_count == case.flow.run_local_server.call_count == 1
    assert case.records[SERVICE, TOKEN_KEY] == before_records[SERVICE, TOKEN_KEY]
    assert case.records[SERVICE, CLEANUP_KEY] == json.dumps(persisted)
    assert files(case.archive.archive_dir) == before_files


@pytest.mark.parametrize("failure", ["missing", "ungranted", "wrong-account"])
def test_invalid_cleanup_grant_blocks_the_command_before_remote_reads(cleanup_backend, monkeypatch, capsys, failure):
    case = cleanup_backend
    if failure != "missing":
        case.storage.save_gmail_cleanup_token(
            ACCOUNT, credentials(granted_scopes=[READONLY] if failure == "ungranted" else [MODIFY])
        )
    if failure == "wrong-account":
        case.profile = "other@example.test"
    case.consent.side_effect = AssertionError("Apply cannot request new consent")
    before_records = case.records.copy()
    before_files = files(case.archive.archive_dir)
    capsys.readouterr()

    with pytest.raises(SystemExit) as result:
        invoke(monkeypatch, "cleanup", "--source", "mail", "--apply")

    assert result.value.code == 1
    output = capsys.readouterr().out
    assert "authorize-cleanup --source mail" in output
    assert "synthetic" not in output
    assert case.events == (["profile"] if failure == "wrong-account" else [])
    assert case.moves == []
    case.consent.assert_not_called()
    assert case.records == before_records
    assert files(case.archive.archive_dir) == before_files


def test_expired_serialized_grant_refreshes_before_apply_without_consent(cleanup_backend, monkeypatch, capsys):
    case = cleanup_backend
    invoke(monkeypatch, "authorize-cleanup", "--source", "mail")
    stored = json.loads(case.records[SERVICE, CLEANUP_KEY])
    stored["expiry"] = "2000-01-01T00:00:00+00:00"
    case.records[SERVICE, CLEANUP_KEY] = json.dumps(stored)
    before_readonly = case.records[SERVICE, TOKEN_KEY]
    before_files = files(case.archive.archive_dir)
    case.consent.side_effect = AssertionError("Refresh cannot open consent")
    response = SimpleNamespace(
        status=200,
        data=json.dumps({"access_token": "synthetic-refreshed", "expires_in": 3600, "token_type": "Bearer"}).encode(),
    )
    request = Mock(return_value=response)
    monkeypatch.setattr(cleanup_auth, "Request", Mock(return_value=request))
    capsys.readouterr()

    invoke(monkeypatch, "cleanup", "--source", "mail", "--apply")

    assert "Moved to server Trash: 1" in capsys.readouterr().out
    request.assert_called_once()
    refreshed = case.storage.load_gmail_cleanup_token(ACCOUNT)
    assert refreshed.token == "synthetic-refreshed"
    assert refreshed.granted_scopes == [MODIFY]
    assert refreshed.valid
    assert case.services[-1].token == refreshed.token
    assert case.records[SERVICE, TOKEN_KEY] == before_readonly
    assert case.consent.call_count == case.flow.run_local_server.call_count == 1
    assert case.moves == ["saved"]
    assert files(case.archive.archive_dir) == before_files
