"""Secure credential storage using system keychain."""

import json
from datetime import datetime, timezone

import keyring
from google.oauth2.credentials import Credentials

# Service name for all ownmail credentials
SERVICE = "ownmail"


def _cleanup_credentials(data: dict) -> Credentials:
    """Validate the separate cleanup token record before constructing credentials."""
    if not isinstance(data, dict):
        raise ValueError("Invalid cleanup authorization")
    for field in ("token", "token_uri", "client_id", "client_secret"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError("Invalid cleanup authorization")
    refresh_token = data["refresh_token"]
    if refresh_token is not None and (not isinstance(refresh_token, str) or not refresh_token.strip()):
        raise ValueError("Invalid cleanup authorization")
    for field in ("scopes", "granted_scopes"):
        value = data[field]
        if not isinstance(value, list) or any(not isinstance(scope, str) or not scope.strip() for scope in value):
            raise ValueError("Invalid cleanup authorization")
    if not data["granted_scopes"]:
        raise ValueError("Cleanup authorization has no verified granted scopes")
    expiry = datetime.fromisoformat(data["expiry"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ValueError("Cleanup authorization has no verified expiry")
    return Credentials(
        token=data["token"],
        refresh_token=refresh_token,
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"],
        granted_scopes=data["granted_scopes"],
        # google-auth compares expiry with a naive UTC clock.
        expiry=expiry.astimezone(timezone.utc).replace(tzinfo=None),
    )


class KeychainStorage:
    """Store credentials securely in the system keychain.

    Keychain structure:
    - Service: "ownmail" (constant)
    - Account keys:
        - "client-credentials/gmail" - OAuth client ID for Gmail
        - "client-credentials/outlook" - OAuth client ID for Outlook
        - "oauth-token/<email>" - OAuth token per Gmail/Outlook account
        - "oauth-token-cleanup/<email>" - Separately authorized Gmail cleanup token
        - "imap-password/<email>" - Password per IMAP account
    """

    def __init__(self, service: str = SERVICE):
        """Initialize keychain storage.

        Args:
            service: Keychain service name (default: "ownmail")
        """
        self.service = service

    # -------------------------------------------------------------------------
    # Client Credentials (per provider)
    # -------------------------------------------------------------------------

    def save_client_credentials(self, provider: str, credentials_json: str) -> None:
        """Save OAuth client credentials for a provider.

        Args:
            provider: Provider name (e.g., 'gmail', 'outlook')
            credentials_json: JSON string of OAuth client credentials
        """
        # Validate JSON
        try:
            data = json.loads(credentials_json)
            if "installed" not in data and "web" not in data:
                raise ValueError("Invalid credentials format")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        account_key = f"client-credentials/{provider}"
        keyring.set_password(self.service, account_key, credentials_json)

    def load_client_credentials(self, provider: str) -> str | None:
        """Load OAuth client credentials for a provider.

        Args:
            provider: Provider name (e.g., 'gmail', 'outlook')

        Returns:
            JSON string of credentials, or None if not found
        """
        account_key = f"client-credentials/{provider}"
        return keyring.get_password(self.service, account_key)

    def has_client_credentials(self, provider: str) -> bool:
        """Check if client credentials exist for a provider."""
        return self.load_client_credentials(provider) is not None

    def delete_client_credentials(self, provider: str) -> None:
        """Delete client credentials for a provider."""
        account_key = f"client-credentials/{provider}"
        try:
            keyring.delete_password(self.service, account_key)
        except keyring.errors.PasswordDeleteError:
            pass

    # -------------------------------------------------------------------------
    # Gmail OAuth Tokens (per account)
    # -------------------------------------------------------------------------

    def save_gmail_token(self, account: str, creds: Credentials) -> None:
        """Save Gmail OAuth token for an account.

        Args:
            account: Email address (e.g., 'alice@gmail.com')
            creds: Google OAuth Credentials object
        """
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else [],
        }
        account_key = f"oauth-token/{account}"
        keyring.set_password(self.service, account_key, json.dumps(token_data))
        print(f"✓ OAuth token saved for {account}")

    def load_gmail_token(self, account: str) -> Credentials | None:
        """Load Gmail OAuth token for an account.

        Args:
            account: Email address

        Returns:
            Google Credentials object, or None if not found
        """
        account_key = f"oauth-token/{account}"
        token_json = keyring.get_password(self.service, account_key)
        if not token_json:
            return None

        try:
            token_data = json.loads(token_json)
            return Credentials(
                token=token_data["token"],
                refresh_token=token_data["refresh_token"],
                token_uri=token_data["token_uri"],
                client_id=token_data["client_id"],
                client_secret=token_data["client_secret"],
                scopes=token_data["scopes"],
            )
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse stored token for {account}: {e}")
            return None

    def delete_gmail_token(self, account: str) -> None:
        """Delete Gmail OAuth token for an account."""
        account_key = f"oauth-token/{account}"
        try:
            keyring.delete_password(self.service, account_key)
        except keyring.errors.PasswordDeleteError:
            pass

    def save_gmail_cleanup_token(self, account: str, creds: Credentials) -> None:
        """Save cleanup credentials after the caller verifies the account and grant."""
        try:
            if not isinstance(account, str) or not account.strip():
                raise ValueError("Missing account")
            expiry = creds.expiry
            if not isinstance(expiry, datetime):
                raise ValueError("Missing expiry")
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            for scopes in (creds.scopes, creds.granted_scopes):
                if scopes is not None and not isinstance(scopes, (list, tuple)):
                    raise ValueError("Invalid scopes")
            token_data = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes) if creds.scopes is not None else [],
                "granted_scopes": list(creds.granted_scopes) if creds.granted_scopes is not None else [],
                "expiry": expiry.astimezone(timezone.utc).isoformat(),
            }
            _cleanup_credentials(token_data)
            token_json = json.dumps(token_data)
        except Exception:
            raise ValueError("Invalid cleanup authorization") from None
        try:
            keyring.set_password(self.service, f"oauth-token-cleanup/{account}", token_json)
        except Exception:
            raise RuntimeError("Could not save cleanup authorization") from None

    def load_gmail_cleanup_token(self, account: str) -> Credentials | None:
        """Load a valid cleanup record without changing any stored credentials."""
        if not isinstance(account, str) or not account.strip():
            return None
        try:
            token_json = keyring.get_password(self.service, f"oauth-token-cleanup/{account}")
            if not token_json:
                return None
            return _cleanup_credentials(json.loads(token_json))
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # IMAP Passwords (per account)
    # -------------------------------------------------------------------------

    def save_imap_password(self, account: str, password: str) -> None:
        """Save IMAP password for an account.

        Args:
            account: Email address
            password: IMAP password or app-specific password
        """
        account_key = f"imap-password/{account}"
        keyring.set_password(self.service, account_key, password)

    def load_imap_password(self, account: str) -> str | None:
        """Load IMAP password for an account.

        Returns:
            Password string, or None if not found
        """
        account_key = f"imap-password/{account}"
        return keyring.get_password(self.service, account_key)

    def delete_imap_password(self, account: str) -> None:
        """Delete IMAP password for an account."""
        account_key = f"imap-password/{account}"
        try:
            keyring.delete_password(self.service, account_key)
        except keyring.errors.PasswordDeleteError:
            pass

    # -------------------------------------------------------------------------
    # Legacy compatibility (single-account)
    # -------------------------------------------------------------------------

    def load_legacy_token(self) -> Credentials | None:
        """Load legacy single-account OAuth token.

        For backward compatibility with v0.1.x archives.
        """
        token_json = keyring.get_password(self.service, "oauth-token")
        if not token_json:
            return None

        try:
            token_data = json.loads(token_json)
            return Credentials(
                token=token_data["token"],
                refresh_token=token_data["refresh_token"],
                token_uri=token_data["token_uri"],
                client_id=token_data["client_id"],
                client_secret=token_data["client_secret"],
                scopes=token_data["scopes"],
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def load_legacy_client_credentials(self) -> str | None:
        """Load legacy single-account client credentials.

        For backward compatibility with v0.1.x archives.
        """
        return keyring.get_password(self.service, "client-credentials")
