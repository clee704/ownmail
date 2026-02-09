"""Secure credential storage using system keychain."""

import json
from typing import Optional

import keyring
from google.oauth2.credentials import Credentials

# Service name for all ownmail credentials
SERVICE = "ownmail"


class KeychainStorage:
    """Store credentials securely in the system keychain.

    Keychain structure:
    - Service: "ownmail" (constant)
    - Account keys:
        - "client-credentials/gmail" - OAuth client ID for Gmail
        - "client-credentials/outlook" - OAuth client ID for Outlook
        - "oauth-token/<email>" - OAuth token per Gmail/Outlook account
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

    def load_client_credentials(self, provider: str) -> Optional[str]:
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

    def load_gmail_token(self, account: str) -> Optional[Credentials]:
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
        print(f"✓ Password saved for {account}")

    def load_imap_password(self, account: str) -> Optional[str]:
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

    def load_legacy_token(self) -> Optional[Credentials]:
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

    def load_legacy_client_credentials(self) -> Optional[str]:
        """Load legacy single-account client credentials.

        For backward compatibility with v0.1.x archives.
        """
        return keyring.get_password(self.service, "client-credentials")
