"""Strict, read-only IMAP lifecycle observations with UIDVALIDITY identity.

Standard IMAP proves Inbox/Drafts through folder roles or the Draft flag.
Only recognized Sent folders establish finished state. Other folders
remain unknown because IMAP has no general scheduled/outgoing-mail state.
Gmail's extension supplies message identity and current cross-folder labels;
only its Sent state establishes completion.
"""

import base64
import json
import re
from dataclasses import replace

from ownmail import roles
from ownmail.live import LiveLookupError, LiveMessage, LiveSnapshot, message_state

_STRING = r'"(?:[^"\\]|\\.)*"|[^\s()"]+'
_LIST = re.compile(r'^\(([^)]*)\) ("(?:[^"\\]|\\.)*"|NIL) (' + _STRING + r")$")
_GMAIL_ROLES = {
    "\\Inbox": roles.INBOX,
    "\\Drafts": roles.DRAFTS,
    "\\Sent": roles.SENT,
    "\\Trash": roles.TRASH,
    "\\Spam": roles.SPAM,
    "\\All": roles.ALL,
}
_GMAIL_NONSTATE = {"\\Important", "\\Starred"}
_STANDARD_FLAGS = {"\\seen", "\\answered", "\\flagged", "\\deleted", "\\draft", "\\recent"}


def _unquote(value):
    return re.sub(r"\\(.)", r"\1", value[1:-1]) if value.startswith('"') else value


def _folders(provider):
    status, data = provider._conn.list()
    if status != "OK" or not isinstance(data, list):
        raise LiveLookupError("IMAP folder listing failed")
    found = {}
    for row in data:
        if not isinstance(row, bytes):
            raise LiveLookupError("IMAP folder listing is incomplete")
        match = _LIST.fullmatch(row.decode("ascii"))
        if not match:
            raise LiveLookupError("IMAP folder listing is malformed")
        flags, delimiter, name = match.groups()
        name = _unquote(name)
        if not name or name in found or "\r" in name or "\n" in name:
            raise LiveLookupError("IMAP folder identity is malformed")
        if "\\noselect" in flags.lower().split():
            continue
        current_roles = {roles.role_for_imap_folder("", flag, "") for flag in flags.split()} - {None}
        if not current_roles:
            role = roles.role_for_imap_folder(name, flags, "" if delimiter == "NIL" else _unquote(delimiter))
            current_roles = {role} if role else set()
        found[name] = frozenset(current_roles)
    return found


def _select(provider, folder):
    quoted = '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'
    status, _ = provider._conn.select(quoted, readonly=True)
    if status != "OK":
        raise LiveLookupError("IMAP folder selection failed")
    status, data = provider._conn.response("UIDVALIDITY")
    if status != "UIDVALIDITY" or not isinstance(data, list) or len(data) != 1:
        raise LiveLookupError("IMAP UIDVALIDITY is unavailable")
    if not isinstance(data[0], bytes) or not re.fullmatch(rb"[1-9][0-9]*", data[0]):
        raise LiveLookupError("IMAP UIDVALIDITY is malformed")
    return data[0].decode("ascii")


def _uids(provider, criterion="ALL"):
    status, data = provider._conn.uid("search", None, criterion)
    if status != "OK" or not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], bytes):
        raise LiveLookupError("IMAP search is incomplete")
    if not re.fullmatch(rb"(?:[1-9][0-9]*(?: [1-9][0-9]*)*)?", data[0]):
        raise LiveLookupError("IMAP search is malformed")
    values = [int(value) for value in data[0].split()]
    if len(values) != len(set(values)):
        raise LiveLookupError("IMAP search contains duplicate identities")
    return values


def _message_id(folder, validity, uid):
    value = json.dumps([folder, validity, uid], separators=(",", ":")).encode()
    return "imap:" + base64.urlsafe_b64encode(value).decode()


def _fetch(provider, folder, validity, uid, folder_roles, *, raw=False):
    gmail = provider._is_gmail()
    fields = "UID FLAGS"
    if gmail:
        fields += " X-GM-MSGID X-GM-THRID X-GM-LABELS"
    if raw:
        fields += " BODY.PEEK[]"
    status, data = provider._conn.uid("fetch", str(uid), "(" + fields + ")")
    if status != "OK" or not isinstance(data, list):
        raise LiveLookupError("IMAP fetch failed")
    entries = [item for item in data if item not in (b")", None)]
    if len(entries) != 1:
        raise LiveLookupError("IMAP fetch is incomplete")
    entry = entries[0]
    content = None
    if raw:
        if not isinstance(entry, tuple) or len(entry) != 2 or not isinstance(entry[1], bytes) or not entry[1]:
            raise LiveLookupError("IMAP message content is unavailable")
        entry, content = entry
        size = re.search(rb"BODY\[\] \{([0-9]+)\}$", entry) if isinstance(entry, bytes) else None
        if size is None or int(size[1]) != len(content):
            raise LiveLookupError("IMAP message content is incomplete")
    if not isinstance(entry, bytes):
        raise LiveLookupError("IMAP fetch metadata is malformed")
    metadata = re.sub(rb'"(?:[^"\\]|\\.)*"', lambda match: b" " * len(match[0]), entry)
    label_match = None
    if gmail:
        label_start = re.search(rb"\bX-GM-LABELS \(", metadata)
        if label_start:
            label_match = re.compile(rb'\bX-GM-LABELS \(((?:"(?:[^"\\]|\\.)*"|[^)])*)\)').match(
                entry, label_start.start()
            )
        if label_match:
            metadata = metadata[: label_match.start()] + b" " * len(label_match[0]) + metadata[label_match.end() :]
    flags = re.search(rb"\bFLAGS \(([^)]*)\)", metadata)
    if flags:
        metadata = metadata[: flags.start()] + b" " * len(flags[0]) + metadata[flags.end() :]
    identity = re.search(rb"\bUID ([0-9]+)\b", metadata)
    if identity is None or int(identity[1]) != uid or flags is None:
        raise LiveLookupError("IMAP current identity or flags are unavailable")
    current_roles = set() if gmail else set(folder_roles)
    flag_set = set(flags[1].decode("ascii").lower().split())
    if "\\draft" in flag_set:
        current_roles.add(roles.DRAFTS)
    if "\\deleted" in flag_set:
        current_roles.add(roles.TRASH)
    message_id = _message_id(folder, validity, uid)
    token, thread_id = message_id, None
    labels = [folder]
    uncertain = bool(flag_set - _STANDARD_FLAGS)
    if gmail:
        gmail_id = re.search(rb"\bX-GM-MSGID ([1-9][0-9]*)\b", metadata)
        thread = re.search(rb"\bX-GM-THRID ([1-9][0-9]*)\b", metadata)
        if gmail_id is None or thread is None or label_match is None:
            raise LiveLookupError("Gmail IMAP identity or labels are unavailable")
        token = "gmail:" + format(int(gmail_id[1]), "x")
        thread_id = format(int(thread[1]), "x")
        label_text = label_match[1].decode("ascii")
        parts = re.findall(_STRING, label_text)
        if " ".join(parts) != label_text:
            raise LiveLookupError("Gmail IMAP labels are malformed")
        labels = [_unquote(value) for value in parts]
        current_roles.update(_GMAIL_ROLES[label] for label in labels if label in _GMAIL_ROLES)
        uncertain = uncertain or any(
            label.startswith("\\") and label not in _GMAIL_ROLES and label not in _GMAIL_NONSTATE for label in labels
        )
    current_roles = frozenset(current_roles)
    finished = roles.SENT in current_roles
    state = message_state(current_roles, finished=finished, uncertain=uncertain)
    return LiveMessage(
        message_id,
        tuple(labels),
        current_roles,
        state,
        token,
        thread_id,
        content,
        "Finished state is unverified" if state == "unknown" else None,
        folder not in provider._exclude_folders,
    )


def list_messages(provider) -> LiveSnapshot:
    """List selectable folders without capture filters or header deduplication."""
    result = LiveSnapshot(provider.source_name, provider.account)
    failed = False
    seen = {}
    try:
        folders = _folders(provider)
        for folder, folder_roles in sorted(folders.items(), key=lambda item: roles.ALL not in item[1]):
            try:
                validity = _select(provider, folder)
                for uid in _uids(provider):
                    try:
                        message = _fetch(provider, folder, validity, uid, folder_roles)
                        previous = seen.get(message.identity_token)
                        if previous is not None:
                            if previous.state != message.state or set(previous.labels) != set(message.labels):
                                failed = True
                            continue
                        seen[message.identity_token] = message
                        result.messages.append(message)
                    except Exception:
                        failed = True
            except Exception:
                failed = True
        return replace(
            result, complete=not failed, reason="Some IMAP messages could not be checked" if failed else None
        )
    except Exception:
        return replace(result, reason="IMAP live enumeration failed")


def read_message(provider, message_id: str) -> LiveMessage | None:
    """Confirm UID identity before reading; partial protocol responses retain cache."""
    try:
        if not isinstance(message_id, str) or not message_id.startswith("imap:"):
            raise LiveLookupError("Missing IMAP identity")
        folder, validity, uid = json.loads(base64.b64decode(message_id[5:], altchars=b"-_", validate=True))
        if not isinstance(folder, str) or not isinstance(validity, str) or type(uid) is not int or uid <= 0:
            raise LiveLookupError("Invalid IMAP identity")
        folders = _folders(provider)
        if folder not in folders:
            return None
        if _select(provider, folder) != validity:
            raise LiveLookupError("IMAP UIDVALIDITY changed; prior identity is unverified")
        found = _uids(provider, "UID " + str(uid))
        if not found:
            return None
        if found != [uid]:
            raise LiveLookupError("IMAP lookup returned another identity")
        return _fetch(provider, folder, validity, uid, folders[folder], raw=True)
    except LiveLookupError:
        raise
    except Exception as error:
        raise LiveLookupError("IMAP live lookup failed") from error
