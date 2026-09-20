"""Separate Gmail cleanup authorization with synthetic OAuth transports."""

import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.oauth2.credentials import Credentials

from ownmail.keychain import KeychainStorage
from ownmail.live import LiveLookupError
from ownmail.providers import cleanup_auth
from ownmail.providers.gmail import GmailProvider

MODIFY = cleanup_auth.CLEANUP_SCOPES[0]
READONLY = "https://www.googleapis.com/auth/gmail.readonly"
ACCOUNT = "alice@example.test"
SECRET = "synthetic-sensitive-response"


def credentials(**overrides):
    values = {
        "token": "access-token",
        "refresh_token": "refresh-token",
        "token_uri": "https://oauth.example.test/token",
        "client_id": "desktop-client",
        "client_secret": "client-secret",
        "scopes": [MODIFY],
        "granted_scopes": [MODIFY],
        "expiry": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
    }
    values.update(overrides)
    return Credentials(**values)


@pytest.fixture
def auth(monkeypatch):
    keychain = MagicMock(spec=KeychainStorage)
    config = {"installed": {"client_id": "desktop-client"}}
    keychain.load_client_credentials.return_value = json.dumps(config)
    keychain.load_gmail_cleanup_token.return_value = credentials()
    provider = GmailProvider(ACCOUNT, keychain, source_name="personal mail")
    previous_service = object()
    provider._service = previous_service
    provider._cleanup_credentials = credentials(token="previous-access-token")
    flow = MagicMock()
    flow.run_local_server.return_value = credentials()
    flow.oauth2session.token = {"access_token": "access-token", "scope": MODIFY}
    flow_factory = MagicMock(return_value=flow)
    monkeypatch.setattr(cleanup_auth.InstalledAppFlow, "from_client_config", flow_factory)
    service = MagicMock()
    profile = service.users.return_value.getProfile.return_value.execute
    profile.return_value = {"emailAddress": ACCOUNT.upper()}
    build = MagicMock(return_value=service)
    monkeypatch.setattr(cleanup_auth, "build", build)
    request_factory = MagicMock(side_effect=AssertionError("Unexpected OAuth transport"))
    monkeypatch.setattr(cleanup_auth, "Request", request_factory)
    return SimpleNamespace(
        provider=provider,
        keychain=keychain,
        config=config,
        flow=flow,
        flow_factory=flow_factory,
        service=service,
        profile=profile,
        build=build,
        request_factory=request_factory,
        previous_service=previous_service,
    )


def assert_unsaved(auth):
    auth.keychain.save_gmail_cleanup_token.assert_not_called()
    auth.keychain.save_gmail_token.assert_not_called()
    assert auth.provider._service is auth.previous_service
    assert auth.provider._cleanup_credentials is None


@pytest.mark.parametrize("scope", [MODIFY, [MODIFY], f"{MODIFY} {READONLY}", None])
def test_authorize_saves_verified_grant_with_expiry(auth, scope):
    if scope is None:
        del auth.flow.oauth2session.token["scope"]
    else:
        auth.flow.oauth2session.token["scope"] = scope
    expiry = datetime.now(timezone(timedelta(hours=5))) + timedelta(hours=1)
    auth.flow.run_local_server.return_value = credentials(expiry=expiry)

    auth.provider.authorize_cleanup()

    auth.flow_factory.assert_called_once_with(auth.config, scopes=[MODIFY], autogenerate_code_verifier=True)
    options = auth.flow.run_local_server.call_args.kwargs
    assert options == {
        "host": "127.0.0.1",
        "port": 0,
        "timeout_seconds": 300,
        "authorization_prompt_message": None,
        "success_message": "Authorization response received. Return to ownmail.",
        "login_hint": ACCOUNT,
        "prompt": "consent",
        "access_type": "offline",
    }
    account, saved = auth.keychain.save_gmail_cleanup_token.call_args.args
    assert account == ACCOUNT
    assert saved.scopes == [MODIFY]
    expected_scopes = scope.split() if isinstance(scope, str) else scope or [MODIFY]
    assert saved.granted_scopes == expected_scopes
    assert saved.expiry == expiry.astimezone(timezone.utc).replace(tzinfo=None)
    assert saved.refresh_token == "refresh-token"
    assert auth.provider._cleanup_credentials is saved
    assert auth.provider._service is auth.service
    auth.service.users.return_value.getProfile.assert_called_once_with(userId="me", fields="emailAddress")
    auth.keychain.save_gmail_token.assert_not_called()
    auth.keychain.load_gmail_token.assert_not_called()
    auth.request_factory.assert_not_called()


@pytest.mark.parametrize("scope", [None, "", [], READONLY, [MODIFY, None], [f" {MODIFY}"]])
def test_authorize_rejects_explicit_missing_or_denied_scope(auth, scope):
    auth.flow.oauth2session.token["scope"] = scope

    with pytest.raises(LiveLookupError, match="authorize-cleanup --source 'personal mail'"):
        auth.provider.authorize_cleanup()

    assert_unsaved(auth)
    auth.build.assert_not_called()


@pytest.mark.parametrize("token", [None, {}, {"access_token": "different"}, {"scope": MODIFY}])
def test_authorize_requires_matching_token_response(auth, token):
    auth.flow.oauth2session.token = token

    with pytest.raises(LiveLookupError, match="Cleanup authorization could not be verified or saved"):
        auth.provider.authorize_cleanup()

    assert_unsaved(auth)
    auth.build.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        {"expiry": None},
        {"expiry": datetime(2000, 1, 1)},
        {"refresh_token": None},
        {"token_uri": ""},
        {"client_id": None},
        {"client_secret": " "},
    ],
)
def test_authorize_rejects_incomplete_or_expired_credentials(auth, overrides):
    auth.flow.run_local_server.return_value = credentials(**overrides)

    with pytest.raises(LiveLookupError):
        auth.provider.authorize_cleanup()

    assert_unsaved(auth)
    auth.build.assert_not_called()


@pytest.mark.parametrize("profile", [{"emailAddress": "other@example.test"}, {}, None, {"emailAddress": 7}])
def test_authorize_requires_matching_account_before_save(auth, profile):
    auth.profile.return_value = profile

    with pytest.raises(LiveLookupError, match="different or unverified Gmail account"):
        auth.provider.authorize_cleanup()

    assert_unsaved(auth)


@pytest.mark.parametrize("config", [None, "not json", "[]", "{}", '{"web": {}}', '{"installed": null}'])
def test_authorize_requires_desktop_client_configuration(auth, config):
    auth.keychain.load_client_credentials.return_value = config

    with pytest.raises(LiveLookupError):
        auth.provider.authorize_cleanup()

    auth.flow_factory.assert_not_called()
    assert_unsaved(auth)


@pytest.mark.parametrize("stage", ["consent", "profile"])
def test_authorize_failure_preserves_credentials_and_suppresses_sensitive_output(auth, caplog, capsys, stage):
    caplog.set_level(logging.DEBUG)
    previous_disable = logging.root.manager.disable

    def fail(*args, **kwargs):
        logging.getLogger("oauthlib.oauth2").critical(SECRET)
        logging.getLogger("google.auth.transport.requests").debug(SECRET)
        raise RuntimeError(SECRET)

    if stage == "consent":
        auth.flow.run_local_server.side_effect = fail
    else:
        auth.profile.side_effect = fail
    with pytest.raises(LiveLookupError) as error:
        auth.provider.authorize_cleanup()

    assert SECRET not in str(error.value)
    assert SECRET not in caplog.text
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert logging.root.manager.disable == previous_disable
    assert_unsaved(auth)


def test_authorize_cancellation_preserves_credentials_and_logging(auth):
    previous_disable = logging.root.manager.disable
    auth.flow.run_local_server.side_effect = KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        auth.provider.authorize_cleanup()

    assert logging.root.manager.disable == previous_disable
    assert_unsaved(auth)


def test_authorize_save_failure_does_not_claim_preservation(auth):
    auth.keychain.save_gmail_cleanup_token.side_effect = RuntimeError(SECRET)

    with pytest.raises(LiveLookupError) as error:
        auth.provider.authorize_cleanup()

    assert "saved credentials were kept" not in str(error.value)
    assert SECRET not in str(error.value)
    assert auth.provider._service is auth.previous_service
    assert auth.provider._cleanup_credentials is None
    auth.keychain.save_gmail_token.assert_not_called()


@pytest.mark.parametrize(
    "saved",
    [
        None,
        object(),
        credentials(scopes=[READONLY]),
        credentials(granted_scopes=None),
        credentials(granted_scopes=[READONLY]),
        credentials(expiry=None),
        credentials(refresh_token=None),
    ],
)
def test_authenticate_invalid_saved_grant_never_starts_consent(auth, saved):
    auth.keychain.load_gmail_cleanup_token.return_value = saved

    with pytest.raises(LiveLookupError, match="valid saved cleanup authorization is required"):
        auth.provider.authenticate_cleanup()

    auth.flow_factory.assert_not_called()
    auth.keychain.load_client_credentials.assert_not_called()
    auth.keychain.load_gmail_token.assert_not_called()
    auth.build.assert_not_called()
    assert_unsaved(auth)


def test_authenticate_valid_grant_checks_account_without_resaving_or_consent(auth):
    auth.provider.authenticate_cleanup()

    auth.keychain.load_gmail_cleanup_token.assert_called_once_with(ACCOUNT)
    auth.keychain.save_gmail_cleanup_token.assert_not_called()
    auth.keychain.load_gmail_token.assert_not_called()
    auth.keychain.load_client_credentials.assert_not_called()
    auth.flow_factory.assert_not_called()
    auth.request_factory.assert_not_called()
    assert auth.provider._service is auth.service
    assert auth.provider._cleanup_credentials is auth.keychain.load_gmail_cleanup_token.return_value


def install_refresh_response(auth, *, scope=MODIFY, omit_scope=False, status=200, expires_in=3600):
    response = {"access_token": "refreshed-token", "expires_in": expires_in, "refresh_token": "rotated-refresh"}
    if not omit_scope:
        response["scope"] = scope
    if status != 200:
        response = {"error": "invalid_grant", "error_description": SECRET}
    transport = MagicMock(return_value=SimpleNamespace(status=status, data=json.dumps(response).encode(), headers={}))
    auth.request_factory.side_effect = None
    auth.request_factory.return_value = transport
    return transport


@pytest.mark.parametrize("omit_scope", [False, True])
def test_authenticate_real_refresh_keeps_proven_scope_when_response_omits_it(auth, omit_scope):
    auth.keychain.load_gmail_cleanup_token.return_value = credentials(expiry=datetime(2000, 1, 1))
    transport = install_refresh_response(auth, omit_scope=omit_scope)

    auth.provider.authenticate_cleanup()

    assert transport.call_count == 1
    account, saved = auth.keychain.save_gmail_cleanup_token.call_args.args
    assert account == ACCOUNT
    assert saved.token == "refreshed-token"
    assert saved.refresh_token == "rotated-refresh"
    assert saved.granted_scopes == [MODIFY]
    assert saved.valid
    assert auth.provider._cleanup_credentials is saved
    assert auth.provider._service is auth.service
    auth.flow_factory.assert_not_called()
    auth.keychain.save_gmail_token.assert_not_called()


@pytest.mark.parametrize("scope", [READONLY, "", None])
def test_authenticate_real_refresh_rejects_changed_scope_without_saving(auth, scope):
    auth.keychain.load_gmail_cleanup_token.return_value = credentials(expiry=datetime(2000, 1, 1))
    install_refresh_response(auth, scope=scope)

    with pytest.raises(LiveLookupError):
        auth.provider.authenticate_cleanup()

    assert_unsaved(auth)
    auth.build.assert_not_called()
    auth.flow_factory.assert_not_called()


def test_authenticate_rejected_refresh_requires_reauthorization_without_leaking_response(auth):
    auth.keychain.load_gmail_cleanup_token.return_value = credentials(expiry=datetime(2000, 1, 1))
    install_refresh_response(auth, status=400)

    with pytest.raises(LiveLookupError, match="could not be refreshed") as error:
        auth.provider.authenticate_cleanup()

    assert SECRET not in str(error.value)
    assert_unsaved(auth)
    auth.flow_factory.assert_not_called()


def test_authenticate_network_failure_keeps_saved_credentials(auth):
    auth.keychain.load_gmail_cleanup_token.return_value = credentials(expiry=datetime(2000, 1, 1))
    transport = install_refresh_response(auth)
    transport.side_effect = ConnectionError(SECRET)

    with pytest.raises(LiveLookupError, match="retry when the connection is available") as error:
        auth.provider.authenticate_cleanup()

    assert SECRET not in str(error.value)
    assert_unsaved(auth)
    auth.flow_factory.assert_not_called()


@pytest.mark.parametrize("refresh_during_profile", [False, True])
def test_authenticate_wrong_account_does_not_save_refreshed_token(auth, refresh_during_profile):
    saved = credentials() if refresh_during_profile else credentials(expiry=datetime(2000, 1, 1))
    auth.keychain.load_gmail_cleanup_token.return_value = saved
    transport = install_refresh_response(auth)

    def profile():
        if refresh_during_profile:
            saved.refresh(transport)
        return {"emailAddress": "other@example.test"}

    auth.profile.side_effect = profile
    with pytest.raises(LiveLookupError, match="different or unverified Gmail account"):
        auth.provider.authenticate_cleanup()

    assert transport.call_count == 1
    assert_unsaved(auth)
    auth.flow_factory.assert_not_called()


@pytest.mark.parametrize("scope", [MODIFY, READONLY])
def test_authenticate_checks_scope_after_profile_automatically_refreshes(auth, scope):
    saved = auth.keychain.load_gmail_cleanup_token.return_value
    transport = install_refresh_response(auth, scope=scope)

    def profile():
        saved.refresh(transport)
        return {"emailAddress": ACCOUNT}

    auth.profile.side_effect = profile
    if scope == MODIFY:
        auth.provider.authenticate_cleanup()
        assert auth.keychain.save_gmail_cleanup_token.call_args.args[1].token == "refreshed-token"
        assert auth.provider._service is auth.service
        assert auth.provider._cleanup_credentials is saved
    else:
        with pytest.raises(LiveLookupError, match="cleanup was not started"):
            auth.provider.authenticate_cleanup()
        assert_unsaved(auth)
    auth.flow_factory.assert_not_called()


@pytest.mark.parametrize("stage", ["load", "refresh", "profile", "save"])
def test_authenticate_suppresses_logs_and_restores_logging_after_failure(auth, caplog, stage):
    caplog.set_level(logging.DEBUG)
    previous_disable = logging.root.manager.disable

    def fail(*args, **kwargs):
        logging.getLogger("google.oauth2.credentials").critical(SECRET)
        raise RuntimeError(SECRET)

    if stage == "load":
        auth.keychain.load_gmail_cleanup_token.side_effect = fail
    elif stage == "profile":
        auth.profile.side_effect = fail
    else:
        auth.keychain.load_gmail_cleanup_token.return_value = credentials(expiry=datetime(2000, 1, 1))
        transport = install_refresh_response(auth)
        if stage == "refresh":
            transport.side_effect = fail
        else:
            auth.keychain.save_gmail_cleanup_token.side_effect = fail

    with pytest.raises(LiveLookupError) as error:
        auth.provider.authenticate_cleanup()

    assert SECRET not in str(error.value)
    assert SECRET not in caplog.text
    assert logging.root.manager.disable == previous_disable
    assert auth.provider._service is auth.previous_service
    assert auth.provider._cleanup_credentials is None
    auth.flow_factory.assert_not_called()


@pytest.mark.parametrize("expires_in", [0, None])
def test_authenticate_rejects_refresh_without_usable_expiry(auth, expires_in):
    auth.keychain.load_gmail_cleanup_token.return_value = credentials(expiry=datetime(2000, 1, 1))
    install_refresh_response(auth, expires_in=expires_in)

    with pytest.raises(LiveLookupError, match="could not be refreshed"):
        auth.provider.authenticate_cleanup()

    assert_unsaved(auth)
    auth.flow_factory.assert_not_called()


def test_authenticate_rejects_credential_expiring_during_account_check(auth):
    saved = auth.keychain.load_gmail_cleanup_token.return_value

    def profile():
        saved.expiry = datetime(2000, 1, 1)
        return {"emailAddress": ACCOUNT}

    auth.profile.side_effect = profile
    with pytest.raises(LiveLookupError, match="cleanup was not started"):
        auth.provider.authenticate_cleanup()

    assert_unsaved(auth)
    auth.flow_factory.assert_not_called()


@pytest.mark.parametrize("operation", ["authorize_cleanup", "authenticate_cleanup"])
def test_cleanup_credentials_attached_only_after_account_verification_and_save(auth, operation):
    if operation == "authenticate_cleanup":
        auth.keychain.load_gmail_cleanup_token.return_value = credentials(expiry=datetime(2000, 1, 1))
        install_refresh_response(auth)

    def profile():
        assert auth.provider._cleanup_credentials is None
        return {"emailAddress": ACCOUNT}

    def save(account, creds):
        assert auth.provider._cleanup_credentials is None

    auth.profile.side_effect = profile
    auth.keychain.save_gmail_cleanup_token.side_effect = save

    getattr(auth.provider, operation)()

    auth.profile.assert_called_once()
    auth.keychain.save_gmail_cleanup_token.assert_called_once()
    saved = auth.keychain.save_gmail_cleanup_token.call_args.args[1]
    assert auth.provider._cleanup_credentials is saved
