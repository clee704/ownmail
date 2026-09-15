"""Strict, read-only IMAP lifecycle observations with UIDVALIDITY identity.

Inbox, Drafts, the Draft flag, Scheduled (RFC 9979), and SubmitPending
(RFC 5550) keep mail Active. Other successfully checked mail is eligible;
unrecognized state is held. Optional attributes cannot expose a provider's
unadvertised state. Folder names such as Outbox have ambiguous semantics.
"""

import base64
import json
import re
from dataclasses import dataclass, replace

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
_KNOWN_KEYWORDS = {"$forwarded", "$submitted", "$submitpending", "$mdnsent", "$important"}
_NONSTATE_ATTRIBUTES = {
    "\\flagged",
    "\\haschildren",
    "\\hasnochildren",
    "\\important",
    "\\marked",
    "\\noinferiors",
    "\\nonexistent",
    "\\remote",
    "\\subscribed",
    "\\unmarked",
}


@dataclass(frozen=True)
class _FolderState:
    roles: frozenset[str]
    unfinished: bool = False
    uncertain: bool = False


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
        attributes = set(flags.lower().split())
        if "\\noselect" in attributes:
            continue
        current_roles = {roles.role_for_imap_folder("", flag, "") for flag in flags.split()} - {None}
        if not current_roles:
            role = roles.role_for_imap_folder(name, flags, "" if delimiter == "NIL" else _unquote(delimiter))
            current_roles = {role} if role else set()
        unknown = {
            flag
            for flag in attributes
            if flag != "\\scheduled"
            and flag not in _NONSTATE_ATTRIBUTES
            and roles.role_for_imap_folder("", flag, "") is None
        }
        found[name] = _FolderState(frozenset(current_roles), "\\scheduled" in attributes, bool(unknown))
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


def _fetch(provider, folder, validity, uid, folder_state, *, raw=False):
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
    current_roles = set() if gmail else set(folder_state.roles)
    flag_set = set(flags[1].decode("ascii").lower().split())
    if "\\draft" in flag_set:
        current_roles.add(roles.DRAFTS)
    if "\\deleted" in flag_set:
        current_roles.add(roles.TRASH)
    message_id = _message_id(folder, validity, uid)
    token, thread_id = message_id, None
    labels = [folder]
    unfinished = folder_state.unfinished or "$submitpending" in flag_set
    uncertain = folder_state.uncertain or bool(flag_set - _STANDARD_FLAGS - _KNOWN_KEYWORDS)
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
    state = message_state(current_roles, unfinished=unfinished, uncertain=uncertain)
    return LiveMessage(
        message_id,
        tuple(labels),
        current_roles,
        state,
        token,
        thread_id,
        content,
        "IMAP message state is unrecognized" if state == "unknown" else None,
        folder not in provider._exclude_folders,
    )


def _check_gmail_folders(provider, message, folders):
    """Check role evidence that Gmail's cross-folder labels may not expose."""
    if message.state != "eligible" or not message.identity_token.startswith("gmail:"):
        return message
    gmail_id = str(int(message.identity_token.removeprefix("gmail:"), 16))
    uncertain = False
    for folder, folder_state in folders.items():
        if not (folder_state.unfinished or folder_state.uncertain):
            continue
        _select(provider, folder)
        if not _uids(provider, "X-GM-MSGID " + gmail_id):
            continue
        if folder_state.unfinished:
            return replace(message, state="active", reason=None)
        uncertain = True
    if uncertain:
        return replace(message, state="unknown", reason="IMAP mailbox state is unrecognized")
    return message


def list_messages(provider) -> LiveSnapshot:
    """List selectable folders without capture filters or header deduplication."""
    result = LiveSnapshot(provider.source_name, provider.account)
    failed = False
    seen = {}
    try:
        folders = _folders(provider)
        for folder, folder_state in sorted(folders.items(), key=lambda item: roles.ALL not in item[1].roles):
            try:
                validity = _select(provider, folder)
                for uid in _uids(provider):
                    try:
                        message = _fetch(provider, folder, validity, uid, folder_state)
                        previous_index = seen.get(message.identity_token)
                        if previous_index is not None:
                            previous = result.messages[previous_index]
                            if previous.roles != message.roles or set(previous.labels) != set(message.labels):
                                failed = True
                            priority = {"eligible": 0, "unknown": 1, "active": 2, "discarded": 3}
                            if priority[message.state] > priority[previous.state]:
                                result.messages[previous_index] = message
                            continue
                        seen[message.identity_token] = len(result.messages)
                        result.messages.append(message)
                    except Exception:
                        failed = True
            except Exception:
                failed = True
        for index, message in enumerate(result.messages):
            try:
                result.messages[index] = _check_gmail_folders(provider, message, folders)
            except Exception:
                failed = True
                result.messages[index] = replace(message, state="unknown", reason="IMAP mailbox state lookup failed")
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
        message = _fetch(provider, folder, validity, uid, folders[folder], raw=True)
        checked = _check_gmail_folders(provider, message, folders)
        if message.identity_token.startswith("gmail:") and any(
            state.unfinished or state.uncertain for state in folders.values()
        ):
            if _select(provider, folder) != validity:
                raise LiveLookupError("IMAP UIDVALIDITY changed during state checks")
        return checked
    except LiveLookupError:
        raise
    except Exception as error:
        raise LiveLookupError("IMAP live lookup failed") from error
