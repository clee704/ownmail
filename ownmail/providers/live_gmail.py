"""Fresh Gmail lifecycle reads, independent of capture filters and cursors.

Capture follows current reported roles. Unrecognized system labels remain
unconfirmed; the public API does not specify every scheduled-mail state.
"""

import base64
from dataclasses import replace

from googleapiclient.errors import HttpError

from ownmail import roles
from ownmail.live import LiveLookupError, LiveMessage, LiveSnapshot, message_state

# Gmail recommends no more than 50 calls per batch to limit throttling.
LIVE_BATCH_SIZE = 50

KNOWN_SYSTEM_LABELS = frozenset(
    {
        "SENT",
        "INBOX",
        "DRAFT",
        "TRASH",
        "SPAM",
        "UNREAD",
        "STARRED",
        "IMPORTANT",
        "CATEGORY_PERSONAL",
        "CATEGORY_SOCIAL",
        "CATEGORY_PROMOTIONS",
        "CATEGORY_UPDATES",
        "CATEGORY_FORUMS",
    }
)


def _catalog(provider) -> dict[str, tuple[str, str]]:
    response = provider._service.users().labels().list(userId="me").execute()
    if not isinstance(response, dict) or not isinstance(response.get("labels"), list):
        raise LiveLookupError("Gmail label catalog is unavailable")
    labels = {}
    for label in response["labels"]:
        if (
            not isinstance(label, dict)
            or not isinstance(label.get("id"), str)
            or not label["id"]
            or not isinstance(label.get("name"), str)
            or not label["name"]
            or label.get("type") not in {"system", "user"}
            or label["id"] in labels
        ):
            raise LiveLookupError("Gmail label catalog is malformed")
        labels[label["id"]] = (label["name"], label["type"])
    return labels


def _message(provider, response, message_id, catalog=None, *, raw=False):
    if (
        not isinstance(response, dict)
        or response.get("id") != message_id
        or not isinstance(response.get("threadId"), str)
        or not response["threadId"]
    ):
        raise LiveLookupError("Gmail message identity is unavailable")
    label_ids = response.get("labelIds", [])
    if not isinstance(label_ids, list) or any(not isinstance(label, str) or not label for label in label_ids):
        raise LiveLookupError("Gmail message labels are malformed")
    revision = response.get("historyId")
    if "historyId" in response and (
        not isinstance(revision, str) or not revision.isascii() or not revision.isdecimal()
    ):
        raise LiveLookupError("Gmail message revision is malformed")
    if catalog is None and (provider._include_labels or set(label_ids) - KNOWN_SYSTEM_LABELS):
        catalog = _catalog(provider)
    current_roles = frozenset(role for label in label_ids if (role := roles.role_for_gmail_label(label)))
    unknown = any(
        label not in KNOWN_SYSTEM_LABELS and (catalog or {}).get(label, (None, None))[1] != "user"
        for label in label_ids
    )
    state = message_state(current_roles, uncertain=unknown)
    labels = []
    if provider._include_labels:
        for label in label_ids:
            if label in roles.EPHEMERAL_LABELS:
                continue
            if label not in catalog:
                raise LiveLookupError("Required Gmail label names are unavailable")
            labels.append(catalog[label][0])
    content = None
    if raw and state != "discarded":
        encoded = response.get("raw")
        if not isinstance(encoded, str) or not encoded:
            raise LiveLookupError("Gmail message content is unavailable")
        try:
            content = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        except (ValueError, TypeError) as error:
            raise LiveLookupError("Gmail message content is malformed") from error
    return LiveMessage(
        message_id,
        tuple(labels),
        current_roles,
        state,
        "gmail:" + message_id,
        response["threadId"],
        content,
        "An unrecognized Gmail system label needs interpretation" if state == "unknown" else None,
        content_revision=revision,
    )


def read_message(provider, message_id: str) -> LiveMessage | None:
    """Read content and current labels together; only a 404 confirms absence."""
    try:
        if not isinstance(message_id, str) or not message_id.strip():
            raise LiveLookupError("Missing Gmail message identity")
        try:
            response = provider._service.users().messages().get(userId="me", id=message_id, format="raw").execute()
        except HttpError as error:
            if error.resp.status == 404:
                return None
            raise
        return _message(provider, response, message_id, raw=True)
    except LiveLookupError:
        raise
    except Exception as error:
        raise LiveLookupError("Gmail live lookup failed") from error


def _message_batch(provider, message_ids, *, raw=False):
    responses = {}
    seen = set()
    failed = False

    def callback(request_id, response, exception):
        nonlocal failed
        if request_id not in message_ids or request_id in seen:
            failed = True
            responses.pop(request_id, None)
            return
        seen.add(request_id)
        if exception is not None:
            failed = True
            responses[request_id] = exception
        else:
            responses[request_id] = response

    try:
        batch = provider._service.new_batch_http_request(callback=callback)
        for message_id in message_ids:
            batch.add(
                provider._service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="raw" if raw else "minimal",
                    fields="id,threadId,labelIds,historyId" + (",raw" if raw else ""),
                ),
                request_id=message_id,
            )
        batch.execute()
    except Exception:
        failed = True
    return responses, failed or len(responses) != len(message_ids)


def read_messages(provider, message_ids: list[str]) -> dict[str, LiveMessage | None | Exception]:
    """Read fresh content in bounded batches; only a member's 404 proves absence."""
    results = {message_id: LiveLookupError("Gmail live lookup failed") for message_id in message_ids}
    valid_ids = [message_id for message_id in results if isinstance(message_id, str) and message_id.strip()]
    for offset in range(0, len(valid_ids), LIVE_BATCH_SIZE):
        current_ids = valid_ids[offset : offset + LIVE_BATCH_SIZE]
        try:
            catalog = _catalog(provider)
        except Exception:
            continue
        responses, _ = _message_batch(provider, current_ids, raw=True)
        for message_id in current_ids:
            response = responses.get(message_id)
            if isinstance(response, HttpError) and response.resp.status == 404:
                results[message_id] = None
                continue
            try:
                results[message_id] = _message(provider, response, message_id, catalog, raw=True)
            except LiveLookupError as error:
                results[message_id] = error
            except Exception:
                pass
    return results


def list_messages(provider, *, on_progress=None) -> LiveSnapshot:
    """Enumerate all visible mail, keeping failures distinct from an empty mailbox."""
    result = LiveSnapshot(provider.source_name, provider.account)
    token = None
    seen_tokens = set()
    seen_ids = set()
    failed = False
    checked = 0
    try:
        catalog = _catalog(provider)
        while True:
            response = (
                provider._service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=500,
                    pageToken=token,
                    includeSpamTrash=True,
                )
                .execute()
            )
            if not isinstance(response, dict) or not isinstance(response.get("messages", []), list):
                raise LiveLookupError("Gmail listing is malformed")
            message_ids = []
            for entry in response.get("messages", []):
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                    failed = True
                    continue
                message_id = entry["id"]
                if message_id in seen_ids:
                    failed = True
                    continue
                seen_ids.add(message_id)
                message_ids.append(message_id)
            for offset in range(0, len(message_ids), LIVE_BATCH_SIZE):
                current_ids = message_ids[offset : offset + LIVE_BATCH_SIZE]
                messages, batch_failed = _message_batch(provider, current_ids)
                failed |= batch_failed
                for message_id in current_ids:
                    try:
                        result.messages.append(_message(provider, messages.get(message_id), message_id, catalog))
                    except Exception:
                        failed = True
                checked += len(current_ids)
                if on_progress is not None:
                    on_progress(checked)
            token = response.get("nextPageToken")
            if token is None:
                break
            if not isinstance(token, str) or not token or token in seen_tokens:
                raise LiveLookupError("Gmail listing pagination is incomplete")
            seen_tokens.add(token)
        return replace(
            result, complete=not failed, reason="Some Gmail messages could not be checked" if failed else None
        )
    except Exception:
        return replace(result, reason="Gmail live enumeration failed")
