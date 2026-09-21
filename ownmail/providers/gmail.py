"""Gmail email provider using OAuth2 and Gmail API."""

import base64
import http.client
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import quote

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ownmail import capture, roles
from ownmail.live import LiveLookupError
from ownmail.providers import cleanup_auth, live_gmail
from ownmail.providers.base import EmailProvider, TrashResult
from ownmail.thread_protection import ThreadProtection

# Gmail API scopes - readonly access
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Batch download settings
# Gmail API limits:
# - Max 100 requests per batch (recommended max: 50)
# - "Too many concurrent requests" error at high batch sizes
# - 15,000 quota units/min, messages.get = 5 units = 3,000 msg/min max
# Conservative settings to avoid 429 concurrent request errors
BATCH_SIZE = 10  # Messages per batch request (Gmail API limit)
BATCH_DELAY = 0.2  # Seconds between batches


class _InvalidThreadState(ValueError):
    """A provider response cannot establish current thread state."""


def _thread_message_roles(message: dict, thread_id: str | None = None) -> frozenset[str]:
    """Validate a thread member before interpreting optional label IDs."""
    if not isinstance(message, dict):
        raise _InvalidThreadState("Malformed thread member")
    for key in ("id", "threadId"):
        if not isinstance(message.get(key), str) or not message[key].strip():
            raise _InvalidThreadState("Missing message or thread identity")
    if thread_id is not None and message["threadId"] != thread_id:
        raise _InvalidThreadState("Thread member identity changed")
    labels = message.get("labelIds", [])
    if not isinstance(labels, list) or any(not isinstance(label, str) or not label.strip() for label in labels):
        raise _InvalidThreadState("Malformed message labels")
    return frozenset(role for label in labels if (role := roles.role_for_gmail_label(label)))


class GmailProvider(EmailProvider):
    """Gmail provider using OAuth2 and Gmail REST API.

    Supports:
    - OAuth2 authentication with credentials stored in keychain
    - Incremental sync via Gmail History API
    - Labels stored in database
    """

    def __init__(
        self,
        account: str,
        keychain,
        include_labels: bool = True,
        source_name: str = "gmail",
        exclude_roles: list[str] | None = None,
    ):
        """Initialize Gmail provider.

        Args:
            account: Email address (e.g., 'alice@gmail.com')
            keychain: KeychainStorage instance for credential access
            include_labels: Whether to fetch and inject Gmail labels
            source_name: Source name from config
            exclude_roles: Canonical roles this source keeps out of the
                archive, or None for the default. Trash and spam are added
                whatever this says.
        """
        self._account = account
        self._keychain = keychain
        self._include_labels = include_labels
        self._source_name = source_name
        self._exclude_roles = roles.resolve_exclude_roles(exclude_roles)
        self._cleanup_credentials = None
        self._service = None
        self._label_cache = {}

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def account(self) -> str:
        return self._account

    @property
    def download_batch_size(self) -> int:
        """Number of messages to download per batch."""
        return BATCH_SIZE

    def list_live_messages(self, *, on_progress=None):
        """Enumerate current state independently of capture preferences."""
        return live_gmail.list_messages(self, on_progress=on_progress)

    def read_live_message(self, message_id):
        """Read current roles and contents without changing server mail."""
        return live_gmail.read_message(self, message_id)

    def verify_cleanup_account(self) -> None:
        """Verify the current account without changing credentials or consent."""
        try:
            profile = self._service.users().getProfile(userId="me", fields="emailAddress").execute()
            address = profile.get("emailAddress") if isinstance(profile, dict) else None
            if not isinstance(address, str) or not address or address.casefold() != self.account.casefold():
                raise LiveLookupError("Gmail cleanup account could not be verified")
        except LiveLookupError:
            raise
        except Exception as error:
            raise LiveLookupError("Gmail cleanup account lookup failed") from error

    def authorize_cleanup(self) -> None:
        """Request separate Gmail cleanup consent for the configured account."""
        cleanup_auth.authorize(self)

    def authenticate_cleanup(self) -> None:
        """Use saved cleanup authorization without opening consent."""
        cleanup_auth.authenticate(self)

    def trash_message(self, message_id: str, thread_id: str) -> TrashResult:
        """Move one freshly verified candidate to Trash without automatic retries.

        The caller must finish account, ownership, message, and thread checks
        immediately beforehand. Gmail cannot make those checks atomic with
        this request. An uncertain result requires fresh checks before retry.
        """
        result = TrashResult(self.source_name, self.account, message_id, thread_id)
        if any(not isinstance(value, str) or not value.strip() for value in (message_id, thread_id)):
            return replace(result, status="denied", reason="Gmail cleanup identity is unavailable")
        try:
            headers = cleanup_auth.mutation_headers(self)
        except Exception:
            return replace(result, status="denied", reason="Gmail cleanup authorization is missing or expired")
        connection = None
        try:
            # The discovery client's HTTP transport retries some failed POSTs even
            # with num_retries=0. A mutation must get exactly one transmission.
            connection = http.client.HTTPSConnection("gmail.googleapis.com", timeout=60)
            connection.request(
                "POST", f"/gmail/v1/users/me/messages/{quote(message_id, safe='')}/trash", headers=headers
            )
            reply = connection.getresponse()
            if reply.status in {400, 401, 403}:
                return replace(
                    result,
                    status="denied",
                    reason="Gmail rejected cleanup; authorization, policy, quota, or request restrictions may apply",
                )
            if reply.status != 200:
                return replace(result, reason="Gmail cleanup outcome is unconfirmed; recheck before retrying")
            response = json.loads(reply.read())
            response_roles = _thread_message_roles(response, thread_id)
            if response["id"] != message_id or roles.TRASH not in response_roles:
                raise _InvalidThreadState("Gmail Trash response did not confirm the requested move")
            return replace(result, status="trashed")
        except Exception:
            return replace(result, reason="Gmail cleanup outcome is unconfirmed; recheck before retrying")
        finally:
            if connection is not None:
                connection.close()

    def check_thread_protection(self, message_id: str) -> ThreadProtection:
        """Read current candidate and thread state without capture filters.

        Sent and filed members use their current reported roles. Unrecognized
        system labels cannot establish clearance, and failed reads remain held.
        Gmail supplies no atomic condition connecting this read to trashing.
        """
        result = ThreadProtection(self.source_name, self.account, message_id)
        try:
            if not isinstance(message_id, str) or not message_id.strip():
                raise _InvalidThreadState("Missing candidate identity")
            candidate = (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="minimal", fields="id,threadId,labelIds")
                .execute()
            )
            candidate_roles = _thread_message_roles(candidate)
            if candidate["id"] != message_id:
                raise _InvalidThreadState("Candidate identity changed")
            thread_id = candidate["threadId"]
            result = replace(
                result,
                thread_id=thread_id,
                candidate_roles=candidate_roles,
                active=bool(candidate_roles.intersection({roles.INBOX, roles.DRAFTS}))
                and not candidate_roles.intersection({roles.TRASH, roles.SPAM}),
            )
            thread = (
                self._service.users()
                .threads()
                .get(
                    userId="me",
                    id=thread_id,
                    format="minimal",
                    fields="id,historyId,messages(id,threadId,labelIds)",
                )
                .execute()
            )
            if not isinstance(thread, dict) or thread.get("id") != thread_id:
                raise _InvalidThreadState("Thread identity changed")
            revision = thread.get("historyId")
            if revision is not None and (not isinstance(revision, str) or not revision.strip()):
                raise _InvalidThreadState("Malformed thread revision")
            result = replace(result, revision=revision)
            members = thread.get("messages")
            if not isinstance(members, list) or not members:
                raise _InvalidThreadState("Thread membership is unavailable")
            seen = set()
            unknown = False
            unverified_labels = set()
            for member in members:
                member_roles = _thread_message_roles(member, thread_id)
                member_id = member["id"]
                if member_id in seen:
                    raise _InvalidThreadState("Duplicate thread member")
                seen.add(member_id)
                discarded = member_roles.intersection({roles.TRASH, roles.SPAM})
                if not discarded and member_roles.intersection({roles.INBOX, roles.DRAFTS}):
                    result = replace(result, active=True)
                if member_id == message_id and member_roles != candidate_roles:
                    raise _InvalidThreadState("Candidate roles changed during the check")
                if discarded:
                    continue
                if not member_roles.intersection({roles.INBOX, roles.DRAFTS}):
                    unverified_labels.update(set(member.get("labelIds", [])) - live_gmail.KNOWN_SYSTEM_LABELS)
            if message_id not in seen:
                raise _InvalidThreadState("Candidate is missing from its thread")
            if unverified_labels:
                catalog = self._service.users().labels().list(userId="me").execute()
                if not isinstance(catalog, dict) or not isinstance(catalog.get("labels", []), list):
                    raise _InvalidThreadState("Malformed label catalog")
                label_types = {}
                for label in catalog.get("labels", []):
                    if (
                        not isinstance(label, dict)
                        or not isinstance(label.get("id"), str)
                        or label.get("type") not in {"system", "user"}
                        or label["id"] in label_types
                    ):
                        raise _InvalidThreadState("Malformed label catalog")
                    label_types[label["id"]] = label["type"]
                unknown = any(label_types.get(label) != "user" for label in unverified_labels)
            if unknown:
                result = replace(result, reason="Thread contains a message whose finished state is unknown")
            else:
                result = replace(
                    result,
                    complete=True,
                    reason="Thread has Active mail" if result.active else None,
                )
        except _InvalidThreadState as error:
            result = replace(result, reason=str(error))
        except Exception:
            result = replace(result, reason="Gmail thread lookup failed")
        return replace(result, checked_at=datetime.now(timezone.utc))

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
            creds = self._run_oauth_flow()

        self._service = build("gmail", "v1", credentials=creds)

        # Verify token actually works (catches revoked/expired tokens that
        # appear valid locally but have been invalidated on Google's side)
        try:
            self._service.users().getProfile(userId="me").execute()
        except RefreshError:
            print("⚠ Token has been expired or revoked. Re-authenticating...")
            creds = self._run_oauth_flow()
            self._service = build("gmail", "v1", credentials=creds)

        print("✓ Authenticated with Gmail API", flush=True)

    def _run_oauth_flow(self):
        """Run the interactive OAuth2 flow to get new credentials."""
        client_credentials = self._keychain.load_client_credentials("gmail")
        if not client_credentials:
            raise RuntimeError(
                f"No Gmail OAuth app credentials found in keychain for account '{self._account}'.\n"
                "  This is the client_id/client_secret from your Google Cloud OAuth app "
                "(different from the per-account token saved after you authorize access).\n"
                "  Run 'ownmail setup' to store them."
            )

        print("\nStarting OAuth authentication flow...")
        print("A browser window will open for you to authorize access.\n")

        client_config = json.loads(client_credentials)
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=0)
        self._keychain.save_gmail_token(self._account, creds)
        return creds

    def _list_message_ids(
        self,
        query: str = "",
        label_ids: list[str] | None = None,
        include_spam_trash: bool = False,
        progress: str | None = None,
    ) -> list[str]:
        """Page through ``messages.list`` and collect every id it returns.

        Args:
            query: Gmail search query, or empty for none
            label_ids: Restrict to messages carrying all of these label IDs
            include_spam_trash: Whether trash and spam are in scope
            progress: Noun for the progress line, or None to stay quiet
        """
        all_ids: list[str] = []
        page_token = None

        if progress:
            print("  Querying Gmail API...\033[K", end="\r", flush=True)

        try:
            while True:
                response = (
                    self._service.users()
                    .messages()
                    .list(
                        userId="me",
                        pageToken=page_token,
                        maxResults=500,
                        q=query,
                        labelIds=label_ids,
                        includeSpamTrash=include_spam_trash,
                    )
                    .execute()
                )

                if "messages" in response:
                    all_ids.extend([msg["id"] for msg in response["messages"]])
                    if progress:
                        print(f"  Found {len(all_ids)} {progress}...\033[K", end="\r", flush=True)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except KeyboardInterrupt:
            print("\n\n⏸ Interrupted during Gmail query.")
            raise

        return all_ids

    def get_all_message_ids(self, since: str | None = None, until: str | None = None) -> list[str]:
        """Every message id currently ELIGIBLE for download.

        Not "everything on the server": mail sitting in an excluded role is
        left out, so callers comparing this against the archive — sync-check —
        see what is genuinely missing rather than the whole inbox.

        Args:
            since: Only get emails after this date (YYYY-MM-DD)
            until: Only get emails before this date (YYYY-MM-DD)
        """
        return self._eligible(self._enumerate_excluded(), since, until)

    def _eligible(
        self,
        excluded: frozenset[str],
        since: str | None = None,
        until: str | None = None,
    ) -> list[str]:
        """List every message, minus a membership snapshot the caller took.

        The snapshot is the caller's because it has to be the same one that
        gets persisted. Enumerating again after the listing would let a
        message that left the inbox mid-listing fall out of both the listing
        and the stored membership, so the next run's diff would never see it.

        Args:
            excluded: Ids in an excluded role, as of before this listing
            since: Only get emails after this date (YYYY-MM-DD)
            until: Only get emails before this date (YYYY-MM-DD)
        """
        # Date filtering only. Trash and spam exclusion is the request
        # parameter, not a query term: a matching ``-in:trash -in:spam`` in
        # ``q`` used to sit here restating it, so editing the exclusion there
        # did nothing. The remaining roles have no negatable query form that
        # fails loudly, so they are subtracted rather than asked for.
        query_parts = []
        if since:
            query_parts.append(f"after:{since.replace('-', '/')}")
        if until:
            query_parts.append(f"before:{until.replace('-', '/')}")

        all_ids = self._list_message_ids(query=" ".join(query_parts), progress="messages")
        eligible = [mid for mid in all_ids if mid not in excluded]
        print(f"  Found {len(all_ids)} total messages, {len(eligible)} eligible")
        return eligible

    def _excluded_roles(self) -> frozenset[str]:
        """Roles this source excludes from download.

        The single place the filter is read: the enumeration below, the
        fingerprint that invalidates the cursor when the filter moves, and the
        eligibility test in ``get_new_message_ids`` all come through here.
        """
        return self._exclude_roles

    def _enumerate_excluded(self) -> frozenset[str]:
        """Message ids currently sitting in a transient excluded role.

        This is the set whose membership is diffed across runs, so that a
        message *leaving* an excluded role becomes a download candidate. Gmail
        emits no event for that: ``history.list`` reports ``messageAdded``, and
        a filed inbox message or a rescued spam false positive was added long
        ago.

        Asked by label ID rather than by search query — ``in:trash`` is
        reliable but an unrecognized term would be read as a user label name
        and filter nothing, which fails silently. Cost is flat in mailbox
        size: these roles are bounded by the provider's own retention.
        """
        # Every transient role has a Gmail system label, so the lookup is
        # total here — a new one without a label would have to add the mapping
        # in roles.py rather than be skipped silently.
        label_ids = [
            roles.gmail_label_for_role(r) for r in sorted(self._excluded_roles() & roles.TRANSIENT_EXCLUDE_ROLES)
        ]

        ids: set[str] = set()
        for label_id in label_ids:
            ids.update(self._list_message_ids(label_ids=[label_id], include_spam_trash=True))
        return frozenset(ids)

    def get_new_message_ids(
        self,
        since_state: str | None,
        since: str | None = None,
        until: str | None = None,
    ) -> tuple[list[str], str | None]:
        """Get download candidates and the state to store for the next run.

        Candidates are not "what arrived". They are what arrived *plus* what
        left an excluded role, minus whatever is excluded right now::

            (arrivals ∪ departures) − excluded_now

        The final subtraction is what makes this eligibility-driven rather
        than arrival-driven: a message is judged by where it sits now, not by
        the labels its ``messageAdded`` event happened to carry. That event's
        labels are a fact about the past, and acting on them is how mail that
        lands in spam and is later rescued becomes permanently invisible.

        Args:
            since_state: Capture state from the previous sync
            since: Only get emails after this date (YYYY-MM-DD)
            until: Only get emails before this date (YYYY-MM-DD)

        Returns:
            Tuple of (candidate_ids, new_state). ``new_state`` is None only
            for date-filtered runs, which are partial and store nothing.
        """
        # If date filter is specified, always do a full filtered sync
        # (History API doesn't support date filtering)
        if since or until:
            print("  Searching Gmail (this may take a minute)...", flush=True)
            return self.get_all_message_ids(since=since, until=until), None

        state = capture.load(since_state)
        fingerprint = capture.fingerprint(*self._excluded_roles())

        cursor = state.cursor
        if cursor and state.stale(fingerprint):
            # Messages the old filter skipped sit below the watermark, so a
            # widened filter would otherwise capture nothing retroactively —
            # and do it silently.
            print("  Download filter changed since last sync, rescanning...")
            cursor = None

        # Read membership BEFORE listing arrivals, and persist this same
        # snapshot: see _eligible. The cost is being one run eager about a
        # message that entered an excluded role mid-listing; the alternative
        # is losing one that left mid-listing, permanently.
        excluded_now = self._enumerate_excluded()
        arrivals, new_cursor = self._get_arrivals(cursor, excluded_now)

        candidates = [mid for mid in arrivals if mid not in excluded_now]
        recovered = sorted(state.departed(excluded_now) - set(arrivals))
        if recovered:
            print(f"  {len(recovered)} message(s) became eligible since last sync")
            candidates.extend(recovered)

        new_state = capture.CaptureState(cursor=new_cursor, excluded=excluded_now, fingerprint=fingerprint)
        return candidates, capture.dump(new_state)

    def _get_arrivals(self, cursor: str | None, excluded: frozenset[str]) -> tuple[list[str], str | None]:
        """Messages added since ``cursor``, falling back to a full listing.

        The full-sync watermark is read *before* the listing rather than after
        it. A message arriving mid-listing is in neither the listing nor the
        history that follows a later watermark, which is the same silent loss
        the incremental path was fixed for in TASK-17.
        """
        if cursor:
            try:
                return self._get_messages_since_history(cursor)
            except HttpError as e:
                if e.resp.status != 404:
                    raise
                print("History expired, performing full sync...")

        watermark = self.get_current_sync_state()
        return self._eligible(excluded), watermark

    def _get_messages_since_history(self, history_id: str) -> tuple[list[str], str]:
        """Get new messages since the given history ID, and the next watermark.

        The watermark comes from the history response itself rather than a
        follow-up ``getProfile``. A message arriving between the two calls
        would sit below the profile's historyId without ever having been
        listed, and the next run would start past it — silent, permanent loss.
        """
        new_ids = []
        new_history_id = history_id
        page_token = None

        try:
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

                new_history_id = response.get("historyId", new_history_id)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except KeyboardInterrupt:
            print("\n\n⏸ Interrupted during Gmail query.")
            raise

        return new_ids, new_history_id

    def download_message(self, msg_id: str) -> tuple[bytes, list[str]]:
        """Download a message from Gmail.

        Returns:
            Tuple of (raw_email_bytes, labels)
        """
        # Fetch raw email
        message = self._service.users().messages().get(userId="me", id=msg_id, format="raw").execute()

        raw_data = base64.urlsafe_b64decode(message["raw"])

        # Fetch labels if enabled (stored in DB, not injected into .eml)
        labels = []
        if self._include_labels:
            labels = self._get_labels_for_message(msg_id)
            if labels is None:
                raise RuntimeError("Required Gmail labels unavailable; retry capture")

        return raw_data, labels

    def download_messages_batch(self, msg_ids: list[str]) -> dict[str, tuple[bytes | None, list[str], str | None]]:
        """Download multiple messages in a batch request.

        Args:
            msg_ids: List of message IDs to download (max BATCH_SIZE)

        Returns:
            Dict mapping msg_id -> (raw_data, labels, error_message)
            If successful, error_message is None.
            If failed, raw_data is None and error_message contains the error.
        """
        results: dict[str, tuple[bytes | None, list[str], str | None]] = {}

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

                    if self._include_labels:
                        if "labelIds" in response:
                            labels = self._resolve_label_names(response["labelIds"])
                        else:
                            # Fallback: fetch labels individually if not in batch response
                            labels = self._get_labels_for_message(request_id)
                            if labels is None:
                                raise RuntimeError("Required Gmail labels unavailable; retry capture")

                    results[request_id] = (raw_data, labels, None)
                except Exception as e:
                    results[request_id] = (None, [], str(e))

        # Retry logic for rate limiting (if entire batch fails)
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            # Create batch request with Gmail-specific batch URI
            batch = self._service.new_batch_http_request(callback=callback)

            for msg_id in msg_ids[:BATCH_SIZE]:
                # Request raw format with labelIds explicitly included
                batch.add(
                    self._service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="raw",
                        fields="id,labelIds,raw",
                    ),
                    request_id=msg_id,
                )

            try:
                # Execute batch
                batch.execute()
                break  # Success, exit retry loop
            except HttpError as e:
                if e.resp.status in (429, 503) and attempt < max_retries - 1:
                    # Rate limited (429) or service unavailable (503), wait and retry
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    results.clear()  # Clear partial results
                    continue
                raise

        # Note: Individual 429 errors within the batch are NOT retried here.
        # They're returned as errors and will be picked up on the next backup run.
        # This keeps the code simple and follows our "resumable operations" design.

        # Small delay between batches to avoid rate limiting
        time.sleep(BATCH_DELAY)

        return results

    def get_labels_for_message(self, message_id: str) -> list[str] | None:
        """Fetch Gmail labels for a message.

        Args:
            message_id: Gmail message ID

        Returns:
            List of human-readable label names, or None if the call failed.
            An empty list means the server confirmed the message has no
            labels; None means we don't know. Callers that write label state
            must tell the two apart — a rate-limited request answered as "no
            labels" would look like a message to clear.
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
            return None

    # Alias for backward compatibility
    _get_labels_for_message = get_labels_for_message

    def _resolve_label_names(self, label_ids: list[str]) -> list[str]:
        """Convert label IDs to human-readable names.

        Ephemeral client state (``UNREAD``) is dropped rather than archived —
        see ``roles.EPHEMERAL_LABELS``.
        """
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
            if lid in roles.EPHEMERAL_LABELS:
                continue
            if lid in self._label_cache:
                names.append(self._label_cache[lid])
            else:
                names.append(lid)
        return names

    def get_current_sync_state(self) -> str | None:
        """Get current Gmail history ID."""
        try:
            profile = self._service.users().getProfile(userId="me").execute()
            return profile.get("historyId")
        except HttpError:
            return None
