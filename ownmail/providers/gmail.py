"""Gmail email provider using OAuth2 and Gmail API."""

import base64
import json
from typing import Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ownmail.providers.base import EmailProvider

# Gmail API scopes - readonly access
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Batch size for parallel downloads (Gmail API limit is 100)
BATCH_SIZE = 50


class GmailProvider(EmailProvider):
    """Gmail provider using OAuth2 and Gmail REST API.

    Supports:
    - OAuth2 authentication with credentials stored in keychain
    - Incremental sync via Gmail History API
    - Labels as X-Gmail-Labels header
    """

    def __init__(self, account: str, keychain, include_labels: bool = True):
        """Initialize Gmail provider.

        Args:
            account: Email address (e.g., 'alice@gmail.com')
            keychain: KeychainStorage instance for credential access
            include_labels: Whether to fetch and inject Gmail labels
        """
        self._account = account
        self._keychain = keychain
        self._include_labels = include_labels
        self._service = None
        self._label_cache = {}

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def account(self) -> str:
        return self._account

    def authenticate(self) -> None:
        """Authenticate with Gmail API using OAuth2."""
        creds = self._keychain.load_gmail_token(self._account)

        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            try:
                creds.refresh(Request())
                self._keychain.save_gmail_token(self._account, creds)
            except Exception as e:
                print(f"Token refresh failed: {e}")
                creds = None

        if not creds or not creds.valid:
            # Check for client credentials
            client_credentials = self._keychain.load_client_credentials("gmail")
            if not client_credentials:
                raise RuntimeError(
                    "No OAuth credentials found. Run 'ownmail setup' first."
                )

            print("\nStarting OAuth authentication flow...")
            print("A browser window will open for you to authorize access.\n")

            client_config = json.loads(client_credentials)
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
            self._keychain.save_gmail_token(self._account, creds)

        self._service = build("gmail", "v1", credentials=creds)
        print("✓ Authenticated with Gmail API")

    def get_all_message_ids(
        self, since: Optional[str] = None, until: Optional[str] = None
    ) -> List[str]:
        """Get all message IDs from Gmail.

        Args:
            since: Only get emails after this date (YYYY-MM-DD)
            until: Only get emails before this date (YYYY-MM-DD)
        """
        all_ids = []
        page_token = None

        # Build query for date filtering
        query_parts = []
        if since:
            query_parts.append(f"after:{since.replace('-', '/')}")
        if until:
            query_parts.append(f"before:{until.replace('-', '/')}")
        query = " ".join(query_parts) if query_parts else None

        print("  Querying Gmail API...", end="\r", flush=True)

        while True:
            request_args = {
                "userId": "me",
                "pageToken": page_token,
                "maxResults": 500,
            }
            if query:
                request_args["q"] = query

            response = (
                self._service.users()
                .messages()
                .list(**request_args)
                .execute()
            )

            if "messages" in response:
                all_ids.extend([msg["id"] for msg in response["messages"]])
                print(f"  Found {len(all_ids)} messages...", end="\r", flush=True)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        print(f"  Found {len(all_ids)} total messages")
        return all_ids

    def get_new_message_ids(
        self,
        since_state: Optional[str],
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Tuple[List[str], Optional[str]]:
        """Get new message IDs since the given history ID.

        Args:
            since_state: Gmail history ID from previous sync
            since: Only get emails after this date (YYYY-MM-DD)
            until: Only get emails before this date (YYYY-MM-DD)

        Returns:
            Tuple of (new_ids, new_history_id)
        """
        # If date filter is specified, always do a full filtered sync
        if since or until:
            return self.get_all_message_ids(since=since, until=until), None

        if not since_state:
            # Full sync needed
            return self.get_all_message_ids(), None

        try:
            new_ids = self._get_messages_since_history(since_state)
            new_state = self.get_current_sync_state()
            return new_ids, new_state
        except HttpError as e:
            if e.resp.status == 404:
                print("History expired, performing full sync...")
                return self.get_all_message_ids(), None
            raise

    def _get_messages_since_history(self, history_id: str) -> List[str]:
        """Get new messages since the given history ID."""
        new_ids = []
        page_token = None

        while True:
            response = (
                self._service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    pageToken=page_token,
                )
                .execute()
            )

            if "history" in response:
                for history in response["history"]:
                    if "messagesAdded" in history:
                        for msg in history["messagesAdded"]:
                            new_ids.append(msg["message"]["id"])

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return new_ids

    def download_message(self, msg_id: str) -> Tuple[bytes, List[str]]:
        """Download a message from Gmail.

        Returns:
            Tuple of (raw_email_bytes, labels)
        """
        # Fetch raw email
        message = (
            self._service.users()
            .messages()
            .get(userId="me", id=msg_id, format="raw")
            .execute()
        )

        raw_data = base64.urlsafe_b64decode(message["raw"])

        # Fetch labels if enabled
        labels = []
        if self._include_labels:
            labels = self._get_labels_for_message(msg_id)
            if labels:
                raw_data = self._inject_labels(raw_data, labels)

        return raw_data, labels

    def download_messages_batch(
        self, msg_ids: List[str]
    ) -> Dict[str, Tuple[Optional[bytes], List[str], Optional[str]]]:
        """Download multiple messages in a batch request.

        Args:
            msg_ids: List of message IDs to download (max BATCH_SIZE)

        Returns:
            Dict mapping msg_id -> (raw_data, labels, error_message)
            If successful, error_message is None.
            If failed, raw_data is None and error_message contains the error.
        """
        results: Dict[str, Tuple[Optional[bytes], List[str], Optional[str]]] = {}

        # Pre-load label cache if needed
        if self._include_labels and not self._label_cache:
            try:
                result = self._service.users().labels().list(userId="me").execute()
                for label in result.get("labels", []):
                    self._label_cache[label["id"]] = label["name"]
            except HttpError:
                pass

        def callback(request_id: str, response, exception):
            if exception:
                results[request_id] = (None, [], str(exception))
            else:
                try:
                    raw_data = base64.urlsafe_b64decode(response["raw"])
                    labels = []

                    # Resolve labels from the response
                    if self._include_labels and "labelIds" in response:
                        label_ids = response.get("labelIds", [])
                        labels = self._resolve_label_names(label_ids)
                        if labels:
                            raw_data = self._inject_labels(raw_data, labels)

                    results[request_id] = (raw_data, labels, None)
                except Exception as e:
                    results[request_id] = (None, [], str(e))

        # Create batch request with Gmail-specific batch URI
        batch = self._service.new_batch_http_request(callback=callback)

        for msg_id in msg_ids[:BATCH_SIZE]:
            # Request raw format with labelIds included
            batch.add(
                self._service.users()
                .messages()
                .get(userId="me", id=msg_id, format="raw"),
                request_id=msg_id,
            )

        # Execute batch
        batch.execute()

        return results

    def get_labels_for_message(self, message_id: str) -> List[str]:
        """Fetch Gmail labels for a message.

        Args:
            message_id: Gmail message ID

        Returns:
            List of human-readable label names
        """
        try:
            message = (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="metadata", metadataHeaders=[])
                .execute()
            )
            label_ids = message.get("labelIds", [])
            return self._resolve_label_names(label_ids)
        except HttpError:
            return []

    # Alias for backward compatibility
    _get_labels_for_message = get_labels_for_message

    def _resolve_label_names(self, label_ids: List[str]) -> List[str]:
        """Convert label IDs to human-readable names."""
        # Cache labels on first use
        if not self._label_cache:
            try:
                result = self._service.users().labels().list(userId="me").execute()
                for label in result.get("labels", []):
                    self._label_cache[label["id"]] = label["name"]
            except HttpError:
                pass

        names = []
        for lid in label_ids:
            if lid in self._label_cache:
                names.append(self._label_cache[lid])
            else:
                names.append(lid)
        return names

    def _inject_labels(self, raw_data: bytes, labels: List[str]) -> bytes:
        """Inject X-Gmail-Labels header into raw email data."""
        labels_str = ", ".join(labels)
        header_line = f"X-Gmail-Labels: {labels_str}\r\n".encode()

        # Insert after the first line
        first_newline = raw_data.find(b"\r\n")
        if first_newline == -1:
            first_newline = raw_data.find(b"\n")
            if first_newline == -1:
                return raw_data
            header_line = f"X-Gmail-Labels: {labels_str}\n".encode()
            return raw_data[:first_newline + 1] + header_line + raw_data[first_newline + 1:]

        return raw_data[:first_newline + 2] + header_line + raw_data[first_newline + 2:]

    def get_current_sync_state(self) -> Optional[str]:
        """Get current Gmail history ID."""
        try:
            profile = self._service.users().getProfile(userId="me").execute()
            return profile.get("historyId")
        except HttpError:
            return None
