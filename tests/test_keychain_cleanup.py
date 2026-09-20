"""Separate cleanup credentials preserve verified grant and expiration evidence."""

import json
import traceback
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.oauth2.credentials import Credentials

from ownmail.keychain import KeychainStorage

ACCOUNT = "reader@example.test"
SERVICE = "synthetic-test-service"
TOKEN_KEY = f"oauth-token/{ACCOUNT}"
CLEANUP_KEY = f"oauth-token-cleanup/{ACCOUNT}"
READONLY = "https://www.googleapis.com/auth/gmail.readonly"
MODIFY = "https://www.googleapis.com/auth/gmail.modify"


def credentials(**changes):
    values = {
        "token": "synthetic-access-secret",
        "refresh_token": "synthetic-refresh-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "synthetic-client",
        "client_secret": "synthetic-client-secret",
        "scopes": [MODIFY],
        "granted_scopes": [MODIFY, READONLY],
        "expiry": datetime(2030, 1, 2, 3, 4, 5, 6789),
    }
    return Credentials(**(values | changes))


@pytest.fixture
def keychain(monkeypatch):
    records = {
        (SERVICE, TOKEN_KEY): "original-readonly-token",
        (SERVICE, CLEANUP_KEY): "original-cleanup-token",
    }
    backend = SimpleNamespace(
        get_password=Mock(side_effect=lambda service, key: records.get((service, key))),
        set_password=Mock(side_effect=lambda service, key, value: records.__setitem__((service, key), value)),
        delete_password=Mock(),
    )
    monkeypatch.setattr("ownmail.keychain.keyring", backend)
    return KeychainStorage(SERVICE), backend, records


@pytest.mark.parametrize(
    "expiry",
    [
        datetime(2030, 1, 2, 3, 4, 5, 6789),
        datetime(2030, 1, 2, 8, 34, 5, 6789, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    ],
)
def test_cleanup_roundtrip_preserves_expiry_grants_and_readonly_token(keychain, expiry, capsys):
    storage, backend, records = keychain
    original = credentials(expiry=expiry)
    storage.save_gmail_cleanup_token(ACCOUNT, original)
    loaded = storage.load_gmail_cleanup_token(ACCOUNT)

    assert isinstance(loaded, Credentials)
    assert loaded.token == original.token
    assert loaded.refresh_token == original.refresh_token
    assert loaded.token_uri == original.token_uri
    assert loaded.client_id == original.client_id
    assert loaded.client_secret == original.client_secret
    assert loaded.scopes == [MODIFY]
    assert loaded.granted_scopes == [MODIFY, READONLY]
    assert loaded.expiry == datetime(2030, 1, 2, 3, 4, 5, 6789)
    assert loaded.expired is False
    payload = json.loads(records[SERVICE, CLEANUP_KEY])
    assert payload["expiry"] == "2030-01-02T03:04:05.006789+00:00"
    assert records[SERVICE, TOKEN_KEY] == "original-readonly-token"
    backend.get_password.assert_called_once_with(SERVICE, CLEANUP_KEY)
    backend.set_password.assert_called_once_with(SERVICE, CLEANUP_KEY, records[SERVICE, CLEANUP_KEY])
    backend.delete_password.assert_not_called()
    assert capsys.readouterr() == ("", "")


def test_cleanup_token_is_isolated_by_account_and_service(keychain):
    storage, backend, records = keychain
    storage.save_gmail_cleanup_token(ACCOUNT, credentials())

    assert storage.load_gmail_cleanup_token("other@example.test") is None
    assert KeychainStorage("another-test-service").load_gmail_cleanup_token(ACCOUNT) is None
    assert set(records) == {(SERVICE, TOKEN_KEY), (SERVICE, CLEANUP_KEY)}
    assert backend.set_password.call_count == 1
    backend.delete_password.assert_not_called()


def test_missing_cleanup_token_never_falls_back_to_readonly(keychain):
    storage, backend, records = keychain
    del records[SERVICE, CLEANUP_KEY]
    before = records.copy()

    assert storage.load_gmail_cleanup_token(ACCOUNT) is None
    backend.get_password.assert_called_once_with(SERVICE, CLEANUP_KEY)
    backend.set_password.assert_not_called()
    backend.delete_password.assert_not_called()
    assert records == before


@pytest.mark.parametrize(
    "change",
    [
        {"granted_scopes": None},
        {"granted_scopes": []},
        {"granted_scopes": MODIFY},
        {"granted_scopes": [MODIFY, 1]},
        {"granted_scopes": [""]},
        {"scopes": MODIFY},
        {"expiry": None},
        {"expiry": "synthetic-secret"},
        {"token": None},
        {"token_uri": 1},
        {"client_id": ""},
        {"client_secret": " "},
        {"refresh_token": []},
        {"refresh_token": ""},
    ],
)
def test_invalid_new_cleanup_credentials_preserve_both_saved_tokens(keychain, change, capsys):
    storage, backend, records = keychain
    before = records.copy()

    with pytest.raises(ValueError, match="^Invalid cleanup authorization$"):
        storage.save_gmail_cleanup_token(ACCOUNT, credentials(**change))

    assert records == before
    backend.get_password.assert_not_called()
    backend.set_password.assert_not_called()
    backend.delete_password.assert_not_called()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("account", [None, "", " "])
def test_invalid_account_cannot_access_stored_credentials(keychain, account):
    storage, backend, records = keychain
    before = records.copy()

    with pytest.raises(ValueError, match="Invalid cleanup authorization"):
        storage.save_gmail_cleanup_token(account, credentials())
    assert storage.load_gmail_cleanup_token(account) is None

    assert records == before
    backend.get_password.assert_not_called()
    backend.set_password.assert_not_called()
    backend.delete_password.assert_not_called()


@pytest.mark.parametrize(
    "stored",
    ["synthetic-secret-invalid-json", "null", "[]", '"synthetic-secret"', "{}"],
)
def test_malformed_cleanup_record_is_held_without_output_or_mutation(keychain, stored, capsys):
    storage, backend, records = keychain
    records[SERVICE, CLEANUP_KEY] = stored
    before = records.copy()

    assert storage.load_gmail_cleanup_token(ACCOUNT) is None
    assert records == before
    backend.set_password.assert_not_called()
    backend.delete_password.assert_not_called()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "field,value",
    [
        ("granted_scopes", None),
        ("granted_scopes", []),
        ("granted_scopes", MODIFY),
        ("granted_scopes", [MODIFY, False]),
        ("expiry", None),
        ("expiry", "synthetic-secret"),
        ("expiry", "2030-01-02T03:04:05"),
        ("scopes", None),
        ("token", {"secret": "synthetic-secret"}),
        ("refresh_token", " "),
    ],
)
def test_malformed_cleanup_fields_cannot_supply_authorization(keychain, field, value):
    storage, backend, records = keychain
    storage.save_gmail_cleanup_token(ACCOUNT, credentials())
    data = json.loads(records[SERVICE, CLEANUP_KEY])
    data[field] = value
    records[SERVICE, CLEANUP_KEY] = json.dumps(data)
    before = records.copy()
    backend.set_password.reset_mock()

    assert storage.load_gmail_cleanup_token(ACCOUNT) is None
    assert records == before
    backend.set_password.assert_not_called()
    backend.delete_password.assert_not_called()


def test_expired_cleanup_token_retains_refresh_data_without_becoming_valid(keychain):
    storage, _, _ = keychain
    storage.save_gmail_cleanup_token(ACCOUNT, credentials(expiry=datetime(2000, 1, 1)))
    loaded = storage.load_gmail_cleanup_token(ACCOUNT)

    assert loaded.expired is True
    assert loaded.refresh_token == "synthetic-refresh-secret"
    assert loaded.granted_scopes == [MODIFY, READONLY]


def test_requested_scopes_do_not_replace_actual_grants(keychain):
    storage, _, _ = keychain
    storage.save_gmail_cleanup_token(ACCOUNT, credentials(scopes=[MODIFY], granted_scopes=[READONLY]))
    loaded = storage.load_gmail_cleanup_token(ACCOUNT)

    assert loaded.scopes == [MODIFY]
    assert loaded.granted_scopes == [READONLY]
    assert MODIFY not in loaded.granted_scopes


def test_storage_retains_optional_refresh_and_requested_scope_fields(keychain):
    storage, _, _ = keychain
    storage.save_gmail_cleanup_token(ACCOUNT, credentials(refresh_token=None, scopes=None, granted_scopes=(MODIFY,)))
    loaded = storage.load_gmail_cleanup_token(ACCOUNT)

    assert loaded.refresh_token is None
    assert loaded.scopes == []
    assert loaded.granted_scopes == [MODIFY]


def test_keychain_read_error_is_silent_and_preserves_credentials(keychain, capsys):
    storage, backend, records = keychain
    before = records.copy()
    backend.get_password.side_effect = RuntimeError("synthetic-backend-secret")

    assert storage.load_gmail_cleanup_token(ACCOUNT) is None
    assert records == before
    backend.set_password.assert_not_called()
    backend.delete_password.assert_not_called()
    assert capsys.readouterr() == ("", "")


def test_keychain_write_error_has_no_raw_secret_and_does_not_delete_old_token(keychain, capsys):
    storage, backend, records = keychain
    before = records.copy()
    backend.set_password.side_effect = RuntimeError("synthetic-backend-secret")

    with pytest.raises(RuntimeError, match="^Could not save cleanup authorization$") as caught:
        storage.save_gmail_cleanup_token(ACCOUNT, credentials())

    assert "synthetic-backend-secret" not in "".join(traceback.format_exception(caught.value))
    assert records == before
    backend.get_password.assert_not_called()
    backend.delete_password.assert_not_called()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("operation", ["get_password", "set_password"])
def test_keychain_interruption_propagates_without_deleting_tokens(keychain, operation):
    storage, backend, records = keychain
    before = records.copy()
    getattr(backend, operation).side_effect = KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        if operation == "get_password":
            storage.load_gmail_cleanup_token(ACCOUNT)
        else:
            storage.save_gmail_cleanup_token(ACCOUNT, credentials())

    assert records == before
    backend.delete_password.assert_not_called()
