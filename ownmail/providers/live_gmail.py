"""Fresh Gmail lifecycle reads, independent of capture filters and cursors.

Capture follows current reported roles. Unrecognized system labels remain
unconfirmed; the public API does not specify every scheduled-mail state.
"""

import base64
from dataclasses import replace

from googleapiclient.errors import HttpError

from ownmail import roles
from ownmail.live import LiveLookupError, LiveMessage, LiveSnapshot, message_state

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


def list_messages(provider) -> LiveSnapshot:
    """Enumerate all visible mail, keeping failures distinct from an empty mailbox."""
    result = LiveSnapshot(provider.source_name, provider.account)
    token = None
    seen_tokens = set()
    seen_ids = set()
    failed = False
    try:
        catalog = _catalog(provider) if provider._include_labels else None
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
            for entry in response.get("messages", []):
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                    failed = True
                    continue
                message_id = entry["id"]
                if message_id in seen_ids:
                    failed = True
                    continue
                seen_ids.add(message_id)
                try:
                    message = (
                        provider._service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=message_id,
                            format="minimal",
                            fields="id,threadId,labelIds",
                        )
                        .execute()
                    )
                    result.messages.append(_message(provider, message, message_id, catalog))
                except Exception:
                    failed = True
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
