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

from ownmail import roles
from ownmail.providers.base import EmailProvider

# Default IMAP settings
DEFAULT_PORT = 993  # IMAPS
FETCH_BATCH_SIZE = 500  # UIDs per FETCH command (headers)
FETCH_BODY_BATCH_SIZE = 25  # UIDs per FETCH command (full messages)
FOLDER_BATCH_DELAY = 0.1  # Seconds between folder scans

# Gmail-specific IMAP settings
GMAIL_IMAP_HOST = "imap.gmail.com"


def parse_list_response(folder_data) -> list[tuple[str, str, str]]:
    """Parse an IMAP LIST response into (name, flags, delimiter) tuples.

    Non-selectable folders (e.g. the "[Gmail]" parent) are dropped — nothing
    can be fetched from them.

    Args:
        folder_data: Raw response lines from IMAP4.list()

    Returns:
        List of (folder_name, flags, delimiter)
    """
    folders = []
    for item in folder_data:
        if not isinstance(item, bytes):
            continue
        # Folder list response: (\\Flags) "delimiter" "folder_name"
        match = re.match(rb'\((?P<flags>.*?)\) "(?P<delim>.*?)" (?P<name>.*)', item)
        if not match:
            continue
        flags = match.group("flags").decode()
        if "\\Noselect" in flags:
            continue
        folders.append(
            (
                match.group("name").decode().strip('"'),
                flags,
                match.group("delim").decode(),
            )
        )
    return folders


def discover_role_folders(conn, wanted: frozenset[str]) -> list[str]:
    """List folder names on a live connection whose role is in ``wanted``.

    Used by setup to show a user the real names their server uses for the
    roles ownmail excludes by default. Best effort — this is informational,
    so a server that answers LIST oddly returns nothing rather than failing
    the setup that credentials just succeeded at.

    Args:
        conn: Authenticated imaplib connection
        wanted: Roles to look for

    Returns:
        Matching folder names, in the order the server listed them
    """
    try:
        status, folder_data = conn.list()
        if status != "OK":
            return []
        return [
            name
            for name, flags, delimiter in parse_list_response(folder_data)
            if roles.role_for_imap_folder(name, flags, delimiter) in wanted
        ]
    except Exception:
        return []


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
        exclude_folders: list[str] | None = None,
        source_name: str = "imap",
    ):
        """Initialize IMAP provider.

        Args:
            account: Email address (e.g., 'alice@gmail.com')
            keychain: KeychainStorage instance
            host: IMAP server hostname
            port: IMAP server port (default: 993 for SSL)
            exclude_folders: Literal folder names to skip during sync. When
                left unset, folders are skipped by role instead, so trash and
                spam are excluded whatever the server calls them.
            source_name: Source name from config
        """
        self._account = account
        self._keychain = keychain
        self._host = host
        self._port = port
        self._exclude_folders = exclude_folders or []
        self._source_name = source_name
        self._conn: imaplib.IMAP4_SSL | None = None
        self._folder_roles: dict[str, str] = {}
        self._scan_used_all_mail = False

    @property
    def name(self) -> str:
        return "imap"

    @property
    def source_name(self) -> str:
        return self._source_name

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
            raise RuntimeError(f"No password found for {self._account}. Run 'ownmail setup' first.")

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

    def _list_folders(self) -> list[str]:
        """List all IMAP folders, excluding trash/spam or the configured ones.

        Also records each folder's canonical role in ``_folder_roles``, which
        is where the SPECIAL-USE flags from the LIST response are captured —
        they're only available here.

        Returns:
            List of folder names (decoded)
        """
        status, folder_data = self._conn.list()
        if status != "OK":
            raise RuntimeError("Failed to list IMAP folders")

        folders = []
        self._folder_roles = {}
        for folder_name, flags, delimiter in parse_list_response(folder_data):
            role = roles.role_for_imap_folder(folder_name, flags, delimiter)
            if role:
                self._folder_roles[folder_name] = role

            if self._is_excluded(folder_name, role):
                continue

            folders.append(folder_name)

        return folders

    def _is_excluded(self, folder_name: str, role: str | None) -> bool:
        """Whether a folder should be skipped during sync.

        An explicit ``exclude_folders`` list replaces the role-based default
        wholesale, so a source can opt into syncing its trash by listing
        something else. Unset — the case for every config that never set the
        option — excludes by role, which is what makes exclusion work on
        servers that don't spell their folders the Gmail way.
        """
        if self._exclude_folders:
            return folder_name in self._exclude_folders
        return role in roles.DEFAULT_EXCLUDE_ROLES

    def _get_folder_uids(self, folder: str) -> list[int]:
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

    def _get_message_ids_for_uids(self, folder: str, uids: list[int]) -> dict[int, str]:
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

            status, data = self._conn.uid("fetch", uid_set, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            if status != "OK":
                continue

            for item in data:
                if not isinstance(item, tuple):
                    continue
                # First element: b'SEQ (UID NNNN BODY[HEADER.FIELDS (MESSAGE-ID)] {xx}'.
                # Match the UID, not the leading sequence number — callers look
                # these up by UID, and on servers where the two differ (any
                # mailbox with deletions) a seq-keyed map silently misses every
                # message, which loses cross-folder dedup and labels.
                uid_match = re.search(rb"UID (\d+)", item[0])
                if not uid_match or not item[1]:
                    continue
                msg_id = self._extract_message_id(item[1])
                if msg_id:
                    result[int(uid_match.group(1))] = msg_id

        return result

    def _extract_message_id(self, header_bytes: bytes) -> str | None:
        """Extract Message-ID value from header bytes."""
        try:
            msg = email.message_from_bytes(header_bytes)
            return msg.get("Message-ID", "").strip()
        except Exception:
            return None

    def _is_gmail(self) -> bool:
        """Check if this is a Gmail IMAP connection."""
        return self._host == GMAIL_IMAP_HOST

    def _get_all_mail_folder(self, folders: list[str]) -> str | None:
        """Find the All Mail folder if it exists.

        Matched by SPECIAL-USE role rather than name, so it works in every
        Gmail locale rather than the handful that were hardcoded here.
        """
        for f in folders:
            if self._folder_roles.get(f) == roles.ALL:
                return f
        return None

    def get_all_message_ids(self, since: str | None = None, until: str | None = None) -> list[str]:
        """Scan all folders and return deduplicated message identifiers.

        For Gmail: uses [Gmail]/All Mail as sole download source (it contains
        every message). Other folders are scanned only for label mapping.

        For other IMAP servers: scans all folders with Message-ID deduplication.

        Returns:
            List of "folder:uid" strings (one per unique message)
        """
        folders = self._list_folders()
        print(f"  Found {len(folders)} folders to scan", flush=True)

        all_mail = self._get_all_mail_folder(folders) if self._is_gmail() else None
        self._scan_used_all_mail = bool(all_mail)
        if all_mail:
            return self._scan_gmail(folders, all_mail, since, until)
        else:
            return self._scan_standard(folders, since, until)

    def scan_folder_membership(self) -> dict[str, list[str]] | None:
        """Full scan returning composite_id -> every folder holding that message.

        This is the map the dedup scan already builds to label messages as they
        download, and which is otherwise discarded once the run ends. ``relabel``
        uses it to repair the labels on messages already in the archive, so no
        bodies are fetched.

        Returns:
            "folder:uid" -> every folder name holding that message. None for
            the Gmail All-Mail path, which keys membership by Message-ID rather
            than by the composite id archived rows carry.
        """
        self.get_all_message_ids()
        if self._scan_used_all_mail:
            return None
        return self._folder_lookup

    def _scan_gmail(
        self,
        folders: list[str],
        all_mail: str,
        since: str | None,
        until: str | None,
    ) -> list[str]:
        """Gmail-optimized scan: use [Gmail]/All Mail as sole download source.

        [Gmail]/All Mail contains every message, so no dedup is needed.
        Other folders are scanned for label mapping only (Message-ID headers
        fetched from smaller folders, not from All Mail).
        """
        # Phase 1: Get all UIDs from All Mail (just SEARCH, no header fetch)
        print(f"  Scanning: {all_mail}...\033[K", end="\r", flush=True)
        all_mail_uids = self._get_folder_uids(all_mail)

        if since or until:
            all_mail_uids = self._filter_uids_by_date(all_mail, all_mail_uids, since, until)

        all_ids = [f"{all_mail}:{uid}" for uid in all_mail_uids]

        # Phase 2: Scan other folders for label mapping
        # Build message_id -> [folders] from smaller folders
        message_id_to_folders: dict[str, list[str]] = {}
        other_folders = [f for f in folders if f != all_mail]
        total_label_msgs = 0

        for folder in other_folders:
            print(f"  Scanning labels: {folder}...\033[K", end="\r", flush=True)
            uids = self._get_folder_uids(folder)
            if not uids:
                continue
            if since or until:
                uids = self._filter_uids_by_date(folder, uids, since, until)
                if not uids:
                    continue

            msg_id_map = self._get_message_ids_for_uids(folder, uids)
            for _uid, msg_id in msg_id_map.items():
                message_id_to_folders.setdefault(msg_id, []).append(folder)
            total_label_msgs += len(uids)
            time.sleep(FOLDER_BATCH_DELAY)

        # Store for label enrichment during download
        self._message_id_to_folders = message_id_to_folders
        self._folder_lookup = {}
        self._seen_map = {}

        print(f"  Found {len(all_ids)} messages ({total_label_msgs} label entries from {len(other_folders)} folders)")
        return all_ids

    def _scan_standard(
        self,
        folders: list[str],
        since: str | None,
        until: str | None,
    ) -> list[str]:
        """Standard IMAP scan with Message-ID deduplication across folders."""

        # Phase 1: Scan all folders for UIDs and Message-IDs
        # message_id -> {"primary": "folder:uid", "folders": ["folder1", ...]}
        seen: dict[str, dict] = {}
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
                    seen[msg_id]["ids"].append(composite_id)
                else:
                    # New message
                    if msg_id:
                        seen[msg_id] = {
                            "primary": composite_id,
                            "folders": [folder],
                            "ids": [composite_id],
                        }
                    all_ids.append(composite_id)

            time.sleep(FOLDER_BATCH_DELAY)

        # Store the dedup map for download_message to use
        self._seen_map = seen
        self._message_id_to_folders = {}
        # Every composite id gets an entry, not just the elected primary. Only
        # primaries are ever downloaded, so the rest are inert here — but
        # `relabel` matches archived rows by the provider_id they were captured
        # under, which is whichever folder won the election on that earlier run.
        self._folder_lookup = {}  # composite_id -> all folders holding it
        for info in seen.values():
            for composite_id in info["ids"]:
                self._folder_lookup[composite_id] = info["folders"]

        total_dupes = sum(len(info["folders"]) - 1 for info in seen.values() if len(info["folders"]) > 1)
        print(f"  Found {len(all_ids)} unique messages ({total_dupes} duplicates across folders)")
        return all_ids

    def _filter_uids_by_date(
        self,
        folder: str,
        uids: list[int],
        since: str | None,
        until: str | None,
    ) -> list[int]:
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
        since_state: str | None,
        since: str | None = None,
        until: str | None = None,
    ) -> tuple[list[str], str | None]:
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

        # Gmail optimization: only check [Gmail]/All Mail for new messages
        all_mail = self._get_all_mail_folder(folders) if self._is_gmail() else None

        # For dedup across folders (standard path only)
        seen: dict[str, dict] = {}
        # For Gmail label mapping
        message_id_to_folders: dict[str, list[str]] = {}

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
                status, data = self._conn.uid("search", None, f"UID {old_max_uid + 1}:*")
            else:
                status, data = self._conn.uid("search", None, "ALL")

            if status != "OK" or not data[0]:
                all_uids = []
            else:
                all_uids = [int(uid) for uid in data[0].split()]
                # Filter out the boundary UID (IMAP search is inclusive)
                all_uids = [uid for uid in all_uids if uid > old_max_uid]

            if all_uids:
                if all_mail and folder == all_mail:
                    # Gmail: All Mail UIDs are download candidates, no header fetch needed
                    for uid in all_uids:
                        new_ids.append(f"{all_mail}:{uid}")
                elif all_mail:
                    # Gmail: other folders just contribute labels
                    msg_id_map = self._get_message_ids_for_uids(folder, all_uids)
                    for _uid, msg_id in msg_id_map.items():
                        message_id_to_folders.setdefault(msg_id, []).append(folder)
                else:
                    # Standard IMAP: dedup by Message-ID
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

        # Store dedup/label info
        if all_mail:
            self._message_id_to_folders = message_id_to_folders
            self._folder_lookup = {}
            self._seen_map = {}
        else:
            self._seen_map = seen
            self._folder_lookup = {}
            for _msg_id_val, info in seen.items():
                self._folder_lookup[info["primary"]] = info["folders"]

            total_dupes = sum(len(info["folders"]) - 1 for info in seen.values() if len(info["folders"]) > 1)
            if total_dupes > 0:
                print(f"  ({total_dupes} duplicates across folders)")

        return new_ids, json.dumps(new_state)

    def _get_uidvalidity(self, select_data) -> str | None:
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

    def _get_labels_for_downloaded(self, composite_id: str, raw_data: bytes, folder: str) -> list[str]:
        """Determine labels for a downloaded message.

        For standard IMAP: uses _folder_lookup from dedup scan.
        For Gmail optimized path: extracts Message-ID from raw email
        and looks up which other folders contain it.
        """
        # Standard path: folder lookup populated during dedup scan
        folder_lookup = getattr(self, "_folder_lookup", {})
        if composite_id in folder_lookup:
            return folder_lookup[composite_id]

        # Gmail optimized path: look up Message-ID from raw email content
        msg_id_to_folders = getattr(self, "_message_id_to_folders", None)
        if msg_id_to_folders:
            try:
                msg = email.message_from_bytes(raw_data)
                message_id = msg.get("Message-ID", "").strip()
                if message_id and message_id in msg_id_to_folders:
                    return [folder] + msg_id_to_folders[message_id]
            except Exception:
                pass

        return [folder]

    def download_message(self, msg_id: str) -> tuple[bytes, list[str]]:
        """Download a message by its composite ID (folder:uid).

        Returns:
            Tuple of (raw_email_bytes, labels)
            Labels are the IMAP folder names where this message appears.
        """
        folder, uid_str = msg_id.rsplit(":", 1)
        uid = int(uid_str)

        # readonly=True and BODY.PEEK[] both keep \Seen off: RFC 3501 says a
        # plain RFC822/BODY[] fetch sets \Seen as a side effect, which would
        # mark the user's entire mailbox read while archiving it. Don't drop
        # either one.
        status, _ = self._conn.select(f'"{folder}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"Cannot select folder: {folder}")

        # Fetch the full message. BODY.PEEK[] rather than RFC822 because iCloud
        # answers an RFC822 fetch with a bare '* 1 FETCH (UID 194)' — OK status,
        # no message data — and every download fails.
        status, data = self._conn.uid("fetch", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not data or data[0] is None:
            raise RuntimeError(f"Failed to fetch message {msg_id}")

        # data is [(b'seq (UID nnn BODY[] {size}', b'raw_email'), b')']
        raw_data = None
        for item in data:
            if isinstance(item, tuple) and len(item) == 2:
                raw_data = item[1]
                break

        if raw_data is None:
            raise RuntimeError(f"No message data for {msg_id}")

        # Labels = all folders this message appears in
        labels = self._get_labels_for_downloaded(msg_id, raw_data, folder)

        return raw_data, labels

    def download_messages_batch(self, msg_ids: list[str]) -> dict[str, tuple[bytes | None, list[str], str | None]]:
        """Download multiple messages, grouped by folder for efficiency.

        Groups message IDs by folder to minimize SELECT calls, then uses
        batched FETCH commands to download multiple messages at once.

        Args:
            msg_ids: List of composite IDs ("folder:uid")

        Returns:
            Dict mapping msg_id -> (raw_data, labels, error_msg)
        """
        results: dict[str, tuple[bytes | None, list[str], str | None]] = {}

        # Group by folder to minimize SELECT calls
        folder_groups: dict[str, list[tuple[str, int]]] = {}
        for msg_id in msg_ids:
            folder, uid_str = msg_id.rsplit(":", 1)
            uid = int(uid_str)
            folder_groups.setdefault(folder, []).append((msg_id, uid))

        for folder, items in folder_groups.items():
            # Select folder once for all messages in it. readonly=True is the
            # second half of the \Seen protection — see download_message.
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
                    status, data = self._conn.uid("fetch", uid_set, "(BODY.PEEK[])")
                except Exception as e:
                    for mid, _ in batch:
                        results[mid] = (None, [], str(e))
                    continue

                if status != "OK":
                    for mid, _ in batch:
                        results[mid] = (None, [], f"FETCH failed in {folder}")
                    continue

                # Parse response — extract UID from inside parens.
                # IMAP response: b'SEQ (UID NNNN BODY[] {size}'. Keying on the
                # UID rather than position matters: iCloud returns the messages
                # of a batch in whatever order it likes.
                fetched_uids: set = set()
                for item in data:
                    if isinstance(item, tuple) and len(item) == 2:
                        uid_match = re.search(rb"UID (\d+)", item[0])
                        if uid_match:
                            uid = int(uid_match.group(1))
                            mid = uid_map.get(uid)
                            if mid:
                                results[mid] = (item[1], None, None)  # labels resolved below
                                fetched_uids.add(uid)

                # Mark any missing UIDs as errors
                for mid, uid in batch:
                    if uid not in fetched_uids:
                        results.setdefault(mid, (None, [], f"No data for UID {uid}"))

        # Resolve labels for successfully downloaded messages
        for mid, (raw_data, labels, _error) in list(results.items()):
            if raw_data is not None and labels is None:
                folder = mid.rsplit(":", 1)[0]
                results[mid] = (raw_data, self._get_labels_for_downloaded(mid, raw_data, folder), None)

        return results

    def get_current_sync_state(self) -> str | None:
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
