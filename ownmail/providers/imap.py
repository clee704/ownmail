"""IMAP email provider using App Passwords or plain credentials.

This is the recommended provider for Gmail users who want simple setup.
It uses IMAP with App Passwords instead of the Gmail API + OAuth.

Also supports any standard IMAP server (Fastmail, company mail, self-hosted, etc.).
"""

import email
import imaplib
import json
import re
import time
from typing import Dict, List, Optional, Tuple

from ownmail.providers.base import EmailProvider

# Default IMAP settings
DEFAULT_PORT = 993  # IMAPS
FETCH_BATCH_SIZE = 50  # UIDs per FETCH command (headers)
FETCH_BODY_BATCH_SIZE = 25  # UIDs per FETCH command (full messages)
FOLDER_BATCH_DELAY = 0.1  # Seconds between folder scans

# Gmail-specific IMAP settings
GMAIL_IMAP_HOST = "imap.gmail.com"

# Folders to exclude by default (can be overridden in config)
DEFAULT_EXCLUDE_FOLDERS = ["[Gmail]/Trash", "[Gmail]/Spam"]


class ImapProvider(EmailProvider):
    """IMAP email provider.

    Supports:
    - Any IMAP server with SSL/TLS
    - Gmail via App Passwords (recommended for easy setup)
    - Folder-based labels (IMAP folders → labels)
    - Deduplication by Message-ID across folders
    - Incremental sync via UID tracking
    """

    def __init__(
        self,
        account: str,
        keychain,
        host: str = GMAIL_IMAP_HOST,
        port: int = DEFAULT_PORT,
        exclude_folders: Optional[List[str]] = None,
    ):
        """Initialize IMAP provider.

        Args:
            account: Email address (e.g., 'alice@gmail.com')
            keychain: KeychainStorage instance
            host: IMAP server hostname
            port: IMAP server port (default: 993 for SSL)
            exclude_folders: Folders to skip during sync
        """
        self._account = account
        self._keychain = keychain
        self._host = host
        self._port = port
        self._exclude_folders = exclude_folders or DEFAULT_EXCLUDE_FOLDERS
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    @property
    def name(self) -> str:
        return "imap"

    @property
    def account(self) -> str:
        return self._account

    @property
    def download_batch_size(self) -> int:
        """Number of messages to download per batch."""
        return FETCH_BODY_BATCH_SIZE

    def authenticate(self) -> None:
        """Connect and authenticate with the IMAP server."""
        password = self._keychain.load_imap_password(self._account)
        if not password:
            raise RuntimeError(
                f"No password found for {self._account}. "
                "Run 'ownmail setup' first."
            )

        try:
            self._conn = imaplib.IMAP4_SSL(self._host, self._port)
            self._conn.login(self._account, password)
            print(f"✓ Connected to {self._host} as {self._account}", flush=True)
        except imaplib.IMAP4.error as e:
            error_msg = str(e)
            if "AUTHENTICATIONFAILED" in error_msg or "Invalid credentials" in error_msg:
                raise RuntimeError(
                    f"Authentication failed for {self._account}.\n"
                    "  Check that your App Password is correct.\n"
                    "  Run 'ownmail setup' to update credentials."
                ) from e
            raise RuntimeError(f"IMAP connection failed: {e}") from e

    def _list_folders(self) -> List[str]:
        """List all IMAP folders, excluding configured ones.

        Returns:
            List of folder names (decoded)
        """
        status, folder_data = self._conn.list()
        if status != "OK":
            raise RuntimeError("Failed to list IMAP folders")

        folders = []
        for item in folder_data:
            if isinstance(item, bytes):
                # Parse folder list response: (\\Flags) "delimiter" "folder_name"
                match = re.match(
                    rb'\((?P<flags>.*?)\) "(?P<delim>.*?)" (?P<name>.*)',
                    item,
                )
                if match:
                    flags = match.group("flags").decode()
                    folder_name = match.group("name").decode().strip('"')

                    # Skip non-selectable folders (e.g., "[Gmail]" parent)
                    if "\\Noselect" in flags:
                        continue

                    # Skip excluded folders
                    if folder_name in self._exclude_folders:
                        continue

                    folders.append(folder_name)

        return folders

    def _get_folder_uids(self, folder: str) -> List[int]:
        """Get all UIDs in a folder.

        Args:
            folder: IMAP folder name

        Returns:
            List of message UIDs
        """
        status, _ = self._conn.select(f'"{folder}"', readonly=True)
        if status != "OK":
            return []

        status, data = self._conn.uid("search", None, "ALL")
        if status != "OK" or not data[0]:
            return []

        return [int(uid) for uid in data[0].split()]

    def _get_message_ids_for_uids(
        self, folder: str, uids: List[int]
    ) -> Dict[int, str]:
        """Fetch Message-ID headers for a batch of UIDs.

        Args:
            folder: Current selected folder
            uids: List of UIDs to fetch

        Returns:
            Dict mapping UID -> Message-ID header value
        """
        if not uids:
            return {}

        result = {}
        # Fetch in batches to avoid command-line length limits
        for i in range(0, len(uids), FETCH_BATCH_SIZE):
            batch = uids[i : i + FETCH_BATCH_SIZE]
            uid_set = ",".join(str(u) for u in batch)

            status, data = self._conn.uid(
                "fetch", uid_set, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])"
            )
            if status != "OK":
                continue

            current_uid = None
            for item in data:
                if isinstance(item, tuple):
                    # First element: b'123 (BODY[HEADER.FIELDS (MESSAGE-ID)] {xx}'
                    header_info = item[0]
                    header_body = item[1]

                    uid_match = re.search(rb"(\d+) \(", header_info)
                    if uid_match:
                        current_uid = int(uid_match.group(1))

                    if header_body and current_uid:
                        msg_id = self._extract_message_id(header_body)
                        if msg_id:
                            result[current_uid] = msg_id

        return result

    def _extract_message_id(self, header_bytes: bytes) -> Optional[str]:
        """Extract Message-ID value from header bytes."""
        try:
            msg = email.message_from_bytes(header_bytes)
            return msg.get("Message-ID", "").strip()
        except Exception:
            return None

    def get_all_message_ids(
        self, since: Optional[str] = None, until: Optional[str] = None
    ) -> List[str]:
        """Scan all folders and return deduplicated message identifiers.

        Each identifier is "folder:uid" for the first folder where a message
        appears. Messages appearing in multiple folders are deduplicated by
        Message-ID header; all folder names are tracked for labels.

        Returns:
            List of "folder:uid" strings (one per unique message)
        """
        folders = self._list_folders()
        print(f"  Found {len(folders)} folders to scan", flush=True)

        # Phase 1: Scan all folders for UIDs and Message-IDs
        # message_id -> {"primary": "folder:uid", "folders": ["folder1", ...]}
        seen: Dict[str, Dict] = {}
        all_ids = []

        for folder in folders:
            print(f"  Scanning: {folder}...\033[K", end="\r", flush=True)

            uids = self._get_folder_uids(folder)
            if not uids:
                continue

            # If date filter is specified, narrow UIDs
            if since or until:
                uids = self._filter_uids_by_date(folder, uids, since, until)
                if not uids:
                    continue

            # Fetch Message-IDs for dedup
            msg_id_map = self._get_message_ids_for_uids(folder, uids)

            for uid in uids:
                msg_id = msg_id_map.get(uid)
                composite_id = f"{folder}:{uid}"

                if msg_id and msg_id in seen:
                    # Duplicate — just add this folder as an additional label
                    seen[msg_id]["folders"].append(folder)
                else:
                    # New message
                    if msg_id:
                        seen[msg_id] = {
                            "primary": composite_id,
                            "folders": [folder],
                        }
                    all_ids.append(composite_id)

            time.sleep(FOLDER_BATCH_DELAY)

        # Store the dedup map for download_message to use
        self._seen_map = seen
        self._folder_lookup = {}  # composite_id -> all folders
        for _msg_id_val, info in seen.items():
            self._folder_lookup[info["primary"]] = info["folders"]

        total_dupes = sum(
            len(info["folders"]) - 1 for info in seen.values() if len(info["folders"]) > 1
        )
        print(f"  Found {len(all_ids)} unique messages ({total_dupes} duplicates across folders)")
        return all_ids

    def _filter_uids_by_date(
        self,
        folder: str,
        uids: List[int],
        since: Optional[str],
        until: Optional[str],
    ) -> List[int]:
        """Filter UIDs by date using IMAP SEARCH.

        Args:
            folder: Already selected folder
            uids: UIDs to filter
            since: Start date (YYYY-MM-DD)
            until: End date (YYYY-MM-DD)

        Returns:
            Filtered list of UIDs
        """
        # Re-select folder (may have changed)
        self._conn.select(f'"{folder}"', readonly=True)

        criteria = []
        if since:
            # IMAP date format: DD-Mon-YYYY
            criteria.append(f"SINCE {self._to_imap_date(since)}")
        if until:
            criteria.append(f"BEFORE {self._to_imap_date(until)}")

        if not criteria:
            return uids

        search_str = " ".join(criteria)
        status, data = self._conn.uid("search", None, search_str)
        if status != "OK" or not data[0]:
            return []

        date_uids = {int(uid) for uid in data[0].split()}
        return [uid for uid in uids if uid in date_uids]

    @staticmethod
    def _to_imap_date(date_str: str) -> str:
        """Convert YYYY-MM-DD to IMAP date format DD-Mon-YYYY."""
        from datetime import datetime

        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d-%b-%Y")

    def get_new_message_ids(
        self,
        since_state: Optional[str],
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Tuple[List[str], Optional[str]]:
        """Get new message IDs since the last sync.

        Uses UID-based incremental sync. The sync state is a JSON dict
        mapping folder names to {"max_uid": N, "uidvalidity": V}.

        Args:
            since_state: JSON string of per-folder sync state
            since: Date filter (YYYY-MM-DD)
            until: Date filter (YYYY-MM-DD)

        Returns:
            Tuple of (new_ids, new_state_json)
        """
        # Date filtering always does a full scan
        if since or until:
            return self.get_all_message_ids(since=since, until=until), None

        if not since_state:
            return self.get_all_message_ids(), None

        try:
            state = json.loads(since_state)
        except (json.JSONDecodeError, TypeError):
            print("  Invalid sync state, performing full sync...")
            return self.get_all_message_ids(), None

        folders = self._list_folders()
        new_ids = []
        new_state = {}

        # For dedup across folders
        seen: Dict[str, Dict] = {}

        for folder in folders:
            print(f"  Checking: {folder}...\033[K", end="\r", flush=True)

            status, select_data = self._conn.select(f'"{folder}"', readonly=True)
            if status != "OK":
                continue

            # Check UIDVALIDITY
            uidvalidity = self._get_uidvalidity(select_data)
            folder_state = state.get(folder, {})
            old_validity = folder_state.get("uidvalidity")
            old_max_uid = folder_state.get("max_uid", 0)

            if old_validity and uidvalidity != old_validity:
                # UIDVALIDITY changed — folder was rebuilt, full rescan needed
                print(f"  UIDVALIDITY changed for {folder}, rescanning...")
                old_max_uid = 0

            # Search for UIDs > old_max_uid
            if old_max_uid > 0:
                status, data = self._conn.uid(
                    "search", None, f"UID {old_max_uid + 1}:*"
                )
            else:
                status, data = self._conn.uid("search", None, "ALL")

            if status != "OK" or not data[0]:
                all_uids = []
            else:
                all_uids = [int(uid) for uid in data[0].split()]
                # Filter out the boundary UID (IMAP search is inclusive)
                all_uids = [uid for uid in all_uids if uid > old_max_uid]

            if all_uids:
                # Dedup by Message-ID
                msg_id_map = self._get_message_ids_for_uids(folder, all_uids)

                for uid in all_uids:
                    msg_id = msg_id_map.get(uid)
                    composite_id = f"{folder}:{uid}"

                    if msg_id and msg_id in seen:
                        seen[msg_id]["folders"].append(folder)
                    else:
                        if msg_id:
                            seen[msg_id] = {
                                "primary": composite_id,
                                "folders": [folder],
                            }
                        new_ids.append(composite_id)

            # Update state for this folder
            current_uids = self._get_folder_uids(folder)
            max_uid = max(current_uids) if current_uids else old_max_uid
            new_state[folder] = {
                "max_uid": max_uid,
                "uidvalidity": uidvalidity,
            }

            time.sleep(FOLDER_BATCH_DELAY)

        # Store dedup info
        self._seen_map = seen
        self._folder_lookup = {}
        for _msg_id_val, info in seen.items():
            self._folder_lookup[info["primary"]] = info["folders"]

        total_dupes = sum(
            len(info["folders"]) - 1 for info in seen.values() if len(info["folders"]) > 1
        )
        if total_dupes > 0:
            print(f"  ({total_dupes} duplicates across folders)")

        return new_ids, json.dumps(new_state)

    def _get_uidvalidity(self, select_data) -> Optional[str]:
        """Extract UIDVALIDITY from SELECT response."""
        # select_data is a list like [b'12345']
        # But UIDVALIDITY comes from the response code, not the data
        # We need to check the response from the last SELECT
        try:
            status, data = self._conn.response("UIDVALIDITY")
            if data and data[0]:
                return data[0].decode()
        except Exception:
            pass
        return None

    def download_message(self, msg_id: str) -> Tuple[bytes, List[str]]:
        """Download a message by its composite ID (folder:uid).

        Returns:
            Tuple of (raw_email_bytes, labels)
            Labels are the IMAP folder names where this message appears.
        """
        folder, uid_str = msg_id.rsplit(":", 1)
        uid = int(uid_str)

        # Select the folder
        status, _ = self._conn.select(f'"{folder}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"Cannot select folder: {folder}")

        # Fetch the full message
        status, data = self._conn.uid("fetch", str(uid), "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            raise RuntimeError(f"Failed to fetch message {msg_id}")

        # data is [(b'uid (RFC822 {size}', b'raw_email'), b')']
        raw_data = None
        for item in data:
            if isinstance(item, tuple) and len(item) == 2:
                raw_data = item[1]
                break

        if raw_data is None:
            raise RuntimeError(f"No message data for {msg_id}")

        # Labels = all folders this message appears in (from dedup scan)
        labels = getattr(self, "_folder_lookup", {}).get(msg_id, [folder])

        return raw_data, labels

    def download_messages_batch(
        self, msg_ids: List[str]
    ) -> Dict[str, Tuple[Optional[bytes], List[str], Optional[str]]]:
        """Download multiple messages, grouped by folder for efficiency.

        Groups message IDs by folder to minimize SELECT calls, then uses
        batched FETCH commands to download multiple messages at once.

        Args:
            msg_ids: List of composite IDs ("folder:uid")

        Returns:
            Dict mapping msg_id -> (raw_data, labels, error_msg)
        """
        results: Dict[str, Tuple[Optional[bytes], List[str], Optional[str]]] = {}

        # Group by folder to minimize SELECT calls
        folder_groups: Dict[str, List[Tuple[str, int]]] = {}
        for msg_id in msg_ids:
            folder, uid_str = msg_id.rsplit(":", 1)
            uid = int(uid_str)
            folder_groups.setdefault(folder, []).append((msg_id, uid))

        for folder, items in folder_groups.items():
            # Select folder once for all messages in it
            status, _ = self._conn.select(f'"{folder}"', readonly=True)
            if status != "OK":
                for msg_id, _ in items:
                    results[msg_id] = (None, [], f"Cannot select folder: {folder}")
                continue

            # Fetch full messages in batches
            for i in range(0, len(items), FETCH_BODY_BATCH_SIZE):
                batch = items[i : i + FETCH_BODY_BATCH_SIZE]
                uid_set = ",".join(str(uid) for _, uid in batch)
                uid_map = {uid: mid for mid, uid in batch}

                try:
                    status, data = self._conn.uid("fetch", uid_set, "(RFC822)")
                except Exception as e:
                    for mid, _ in batch:
                        results[mid] = (None, [], str(e))
                    continue

                if status != "OK":
                    for mid, _ in batch:
                        results[mid] = (None, [], f"FETCH failed in {folder}")
                    continue

                # Parse response
                fetched_uids: set = set()
                for item in data:
                    if isinstance(item, tuple) and len(item) == 2:
                        uid_match = re.search(rb"(\d+) \(", item[0])
                        if uid_match:
                            uid = int(uid_match.group(1))
                            mid = uid_map.get(uid)
                            if mid:
                                labels = getattr(self, "_folder_lookup", {}).get(
                                    mid, [folder]
                                )
                                results[mid] = (item[1], labels, None)
                                fetched_uids.add(uid)

                # Mark any missing UIDs as errors
                for mid, uid in batch:
                    if uid not in fetched_uids:
                        results.setdefault(
                            mid, (None, [], f"No data for UID {uid}")
                        )

        return results

    def get_current_sync_state(self) -> Optional[str]:
        """Get current sync state (per-folder max UID + UIDVALIDITY).

        Returns:
            JSON string of sync state
        """
        folders = self._list_folders()
        state = {}

        for folder in folders:
            status, _ = self._conn.select(f'"{folder}"', readonly=True)
            if status != "OK":
                continue

            uidvalidity = self._get_uidvalidity(None)
            uids = self._get_folder_uids(folder)
            max_uid = max(uids) if uids else 0

            state[folder] = {
                "max_uid": max_uid,
                "uidvalidity": uidvalidity,
            }

        return json.dumps(state)

    def close(self) -> None:
        """Close the IMAP connection."""
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None
