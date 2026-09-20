"""Separate, explicit Gmail cleanup authorization and consent-free loading."""

import json
import logging
import shlex
from contextlib import contextmanager
from datetime import datetime, timezone

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ownmail.live import LiveLookupError

CLEANUP_SCOPES = ("https://www.googleapis.com/auth/gmail.modify",)


@contextmanager
def _quiet_auth_logs():
    # OAuth transport and loopback request logs can contain tokens or codes.
    previous = logging.root.manager.disable
    logging.disable(max(previous, logging.CRITICAL))
    try:
        yield
    finally:
        logging.disable(previous)


def _reauthorize(provider, reason):
    command = f"ownmail authorize-cleanup --source {shlex.quote(provider.source_name)}"
    return LiveLookupError(f"{reason}. Run {command} to authorize cleanup.")


def _scopes(value):
    if isinstance(value, str):
        value = value.split()
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("Missing granted permission")
    if any(not isinstance(scope, str) or not scope.strip() or scope != scope.strip() for scope in value):
        raise ValueError("Malformed granted permission")
    return list(value)


def _validate_credentials(creds):
    if not isinstance(creds, Credentials):
        raise ValueError("Missing cleanup credential")
    if list(creds.scopes or []) != list(CLEANUP_SCOPES):
        raise ValueError("Unexpected requested permission")
    if not set(CLEANUP_SCOPES).issubset(_scopes(creds.granted_scopes)):
        raise ValueError("Cleanup permission was not granted")
    for value in (creds.token, creds.refresh_token, creds.token_uri, creds.client_id, creds.client_secret):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Incomplete cleanup credential")
    if not isinstance(creds.expiry, datetime):
        raise ValueError("Unknown cleanup expiry")


def _service_for_account(provider, creds):
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me", fields="emailAddress").execute()
    address = profile.get("emailAddress") if isinstance(profile, dict) else None
    if not isinstance(address, str) or not address or address.casefold() != provider.account.casefold():
        raise _reauthorize(provider, "Cleanup authorization belongs to a different or unverified Gmail account")
    # A service request can refresh credentials after an authentication failure.
    _validate_credentials(creds)
    if not creds.valid:
        raise ValueError("Cleanup credential is no longer valid")
    return service


def authorize(provider) -> None:
    """Open desktop consent, then save a verified cleanup grant and account."""
    provider._cleanup_credentials = None
    with _quiet_auth_logs():
        try:
            saved_client = provider._keychain.load_client_credentials("gmail")
            config = json.loads(saved_client) if saved_client else None
            if not isinstance(config, dict) or not isinstance(config.get("installed"), dict):
                raise LiveLookupError(
                    "Cleanup authorization needs Gmail desktop client credentials from ownmail setup."
                )
            flow = InstalledAppFlow.from_client_config(
                config, scopes=list(CLEANUP_SCOPES), autogenerate_code_verifier=True
            )
            returned = flow.run_local_server(
                host="127.0.0.1",
                port=0,
                timeout_seconds=300,
                authorization_prompt_message=None,
                success_message="Authorization response received. Return to ownmail.",
                login_hint=provider.account,
                prompt="consent",
                access_type="offline",
            )
            token = flow.oauth2session.token
            if not isinstance(token, dict) or not isinstance(returned, Credentials):
                raise ValueError("Malformed token response")
            if not token.get("access_token") or token["access_token"] != returned.token:
                raise ValueError("Unverified token response")
            # RFC 6749 section 5.1: omitted scope means the exact requested grant.
            granted = _scopes(token["scope"] if "scope" in token else CLEANUP_SCOPES)
            expiry = returned.expiry
            if isinstance(expiry, datetime) and expiry.tzinfo is not None:
                expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
            creds = Credentials(
                returned.token,
                refresh_token=returned.refresh_token,
                token_uri=returned.token_uri,
                client_id=returned.client_id,
                client_secret=returned.client_secret,
                scopes=list(CLEANUP_SCOPES),
                granted_scopes=granted,
                expiry=expiry,
            )
            _validate_credentials(creds)
            if not creds.valid:
                raise ValueError("Cleanup credential has expired")
            service = _service_for_account(provider, creds)
            provider._keychain.save_gmail_cleanup_token(provider.account, creds)
            provider._service = service
            provider._cleanup_credentials = creds
        except LiveLookupError:
            raise
        except Exception:
            raise _reauthorize(provider, "Cleanup authorization could not be verified or saved") from None


def authenticate(provider) -> None:
    """Load or refresh the cleanup credential without opening consent."""
    provider._cleanup_credentials = None
    with _quiet_auth_logs():
        try:
            creds = provider._keychain.load_gmail_cleanup_token(provider.account)
            _validate_credentials(creds)
        except Exception:
            raise _reauthorize(provider, "A valid saved cleanup authorization is required") from None
        original = (creds.token, creds.refresh_token, creds.expiry)
        if not creds.valid:
            try:
                # google-auth retains proven granted_scopes when refresh omits scope
                # (RFC 6749 sections 5.1 and 6), and replaces it when supplied.
                creds.refresh(Request())
                _validate_credentials(creds)
                if not creds.valid:
                    raise ValueError("Refreshed cleanup credential is invalid")
            except (RefreshError, ValueError):
                raise _reauthorize(provider, "Saved cleanup authorization could not be refreshed") from None
            except Exception:
                raise LiveLookupError(
                    "Cleanup authorization refresh failed; retry when the connection is available."
                ) from None
        try:
            service = _service_for_account(provider, creds)
            if original != (creds.token, creds.refresh_token, creds.expiry):
                provider._keychain.save_gmail_cleanup_token(provider.account, creds)
            provider._service = service
            provider._cleanup_credentials = creds
        except LiveLookupError:
            raise
        except Exception:
            raise LiveLookupError(
                "Cleanup account verification or credential save failed; cleanup was not started."
            ) from None


def mutation_headers(provider) -> dict:
    """Use the verified grant without refreshing after final cleanup checks."""
    creds = provider._cleanup_credentials
    _validate_credentials(creds)
    if not creds.valid:
        raise ValueError("Cleanup credential has expired")
    headers = {}
    creds.apply(headers)
    return headers
