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

from ownmail import capture, roles
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
    if set(provider._active_exclude_folders) - found.keys():
        raise LiveLookupError("An Active exclusion names an unavailable IMAP folder")
    provider._live_folders = found
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


def _parse_message(provider, folder, validity, folder_state, entry, *, raw=False):
    gmail = provider._is_gmail()
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
    if not re.match(rb"[1-9][0-9]* \(", entry) or (not raw and not entry.endswith(b")")):
        raise LiveLookupError("IMAP fetch framing is malformed")
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
    outside_labels = entry
    if label_match:
        outside_labels = entry[: label_match.start()] + entry[label_match.end() :]
    if b'"' in outside_labels:
        raise LiveLookupError("IMAP fetch attributes are malformed")
    flags = re.search(rb"\bFLAGS \(([^)]*)\)", metadata)
    if flags:
        metadata = metadata[: flags.start()] + b" " * len(flags[0]) + metadata[flags.end() :]
    identities = re.findall(rb"\bUID ([1-9][0-9]*)\b", metadata)
    if len(identities) != 1 or flags is None:
        raise LiveLookupError("IMAP current identity or flags are unavailable")
    uid = int(identities[0])
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
    remaining = re.sub(rb"^[1-9][0-9]* \(", b"", metadata)
    remaining = re.sub(rb"\bUID [1-9][0-9]*\b", b"", remaining, count=1)
    if gmail:
        remaining = re.sub(rb"\bX-GM-MSGID [1-9][0-9]*\b", b"", remaining, count=1)
        remaining = re.sub(rb"\bX-GM-THRID [1-9][0-9]*\b", b"", remaining, count=1)
    remaining = re.sub(rb"BODY\[\] \{[0-9]+\}$" if raw else rb"\)$", b"", remaining)
    if remaining.strip():
        raise LiveLookupError("IMAP fetch attributes are malformed")
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
        content_revision=message_id,
        active_allowed=not set(_scope_names(provider, folder, labels)).intersection(provider._active_exclude_folders),
        active_scope=_scope_names(provider, folder, labels),
    )


def _scope_names(provider, folder, labels):
    names = [folder]
    for label in labels:
        role = _GMAIL_ROLES.get(label) if provider._is_gmail() else None
        if role and role != roles.ALL:
            names.extend(name for name, state in getattr(provider, "_live_folders", {}).items() if role in state.roles)
        else:
            names.append(label)
    folders = getattr(provider, "_live_folders", {})
    if folder in folders and roles.ALL in folders[folder].roles:
        concrete = [name for name in names[1:] if name in folders and roles.ALL not in folders[name].roles]
        if concrete:
            names.remove(folder)
    return tuple(dict.fromkeys(names))


def entry_in_scope(provider, entry):
    scopes = entry.get("active_scope") or []
    if scopes:
        return not set(scopes).intersection(provider._active_exclude_folders)
    if set(entry.get("labels") or []).intersection(provider._active_exclude_folders):
        return False
    try:
        folder, _, _ = _locator(entry.get("provider_id"))
    except Exception:
        return False
    return folder not in provider._active_exclude_folders


def _fetch_many(provider, folder, validity, uids, folder_state, *, raw=False):
    fields = "UID FLAGS"
    if provider._is_gmail():
        fields += " X-GM-MSGID X-GM-THRID X-GM-LABELS"
    if raw:
        fields += " BODY.PEEK[]"
    status, data = provider._conn.uid("fetch", ",".join(map(str, uids)), "(" + fields + ")")
    if status != "OK" or not isinstance(data, list):
        raise LiveLookupError("IMAP fetch failed")
    expected = {_message_id(folder, validity, uid): uid for uid in uids}
    found = {}
    index = 0
    while index < len(data):
        entry = data[index]
        if raw:
            if index + 1 >= len(data) or data[index + 1] != b")":
                raise LiveLookupError("IMAP literal framing is incomplete")
            index += 1
        message = _parse_message(provider, folder, validity, folder_state, entry, raw=raw)
        if message.message_id not in expected:
            raise LiveLookupError("IMAP fetch returned another identity")
        uid = expected[message.message_id]
        found[uid] = LiveLookupError("IMAP fetch returned a duplicate identity") if uid in found else message
        index += 1
    return {uid: found.get(uid, LiveLookupError("IMAP fetch is incomplete")) for uid in uids}


def _folder_messages(provider, folder, folder_state, *, on_checked=None, criterion="ALL"):
    validity = _select(provider, folder)
    uids = _uids(provider, criterion)
    yield from _metadata_messages(provider, folder, validity, folder_state, uids, on_checked=on_checked)


def _metadata_messages(provider, folder, validity, folder_state, uids, *, on_checked=None):
    """Keep each metadata request bounded while retaining successful batches."""
    from ownmail.providers.imap import FETCH_BATCH_SIZE

    for offset in range(0, len(uids), FETCH_BATCH_SIZE):
        batch = uids[offset : offset + FETCH_BATCH_SIZE]
        try:
            fetched = _fetch_many(provider, folder, validity, batch, folder_state)
        except Exception as error:
            fetched = dict.fromkeys(batch, error)
        for uid in batch:
            if on_checked:
                on_checked()
            yield fetched[uid]


def _capture_cursor(provider, sync_state):
    try:
        prior = capture.load(sync_state)
        cursor = json.loads(prior.cursor) if prior.cursor else {}
        if prior.stale(provider._filter_fingerprint()) or not isinstance(cursor, dict):
            return {}, frozenset()
        for folder, value in cursor.items():
            if (
                not isinstance(folder, str)
                or not isinstance(value, dict)
                or type(value.get("max_uid")) is not int
                or value["max_uid"] < 0
                or (
                    value.get("uidvalidity") is not None
                    and (
                        not isinstance(value["uidvalidity"], str)
                        or not re.fullmatch(r"[1-9][0-9]*", value["uidvalidity"])
                    )
                )
            ):
                return {}, frozenset()
        if any(not isinstance(value, str) for value in prior.excluded):
            return {}, frozenset()
        return cursor, prior.excluded
    except (TypeError, ValueError, AttributeError):
        return {}, frozenset()


def _incremental_folder(
    provider,
    folder,
    folder_state,
    prior,
    next_cursor,
    *,
    all_mail=None,
    prior_excluded=(),
    excluded=None,
    on_checked=None,
):
    validity = _select(provider, folder)
    saved = prior.get(folder, {})
    same_epoch = saved.get("uidvalidity") == validity
    watermark = saved.get("max_uid", 0) if same_epoch else 0
    if folder == all_mail:
        from ownmail.providers.imap import _ALL_MAIL_ROLE_SEARCH

        for criterion in _ALL_MAIL_ROLE_SEARCH.values():
            excluded.update(f"{folder}:{uid}" for uid in _uids(provider, criterion))
    criterion = f"UID {watermark + 1}:*" if watermark and folder in provider._active_exclude_folders else "ALL"
    found = _uids(provider, criterion)
    uids = [uid for uid in found if uid > watermark] if criterion != "ALL" else found
    next_cursor[folder] = {"max_uid": max([watermark, *uids]), "uidvalidity": validity}
    if folder == all_mail and same_epoch:
        prefix = folder + ":"
        departed = set(prior_excluded) - excluded
        recovered = []
        for value in departed:
            if value.startswith(prefix) and re.fullmatch(r"[1-9][0-9]*", value[len(prefix) :]):
                recovered.append(int(value[len(prefix) :]))
        # A filed message retains its All Mail UID; a trashed one may be absent.
        from ownmail.providers.imap import FETCH_BATCH_SIZE

        for start in range(0, len(recovered), FETCH_BATCH_SIZE):
            batch = recovered[start : start + FETCH_BATCH_SIZE]
            present = _uids(provider, "UID " + ",".join(map(str, batch)))
            if not set(present).issubset(batch):
                raise LiveLookupError("IMAP capture lookup returned another identity")
            uids.extend(present)
        uids = sorted(set(uids))
    yield from _metadata_messages(provider, folder, validity, folder_state, uids, on_checked=on_checked)


def _membership_state(message, memberships, *, failed=False):
    if message.state != "eligible" or not message.identity_token.startswith("gmail:"):
        return message
    states = memberships.get(message.identity_token, [])
    if any(state.unfinished for state in states):
        return replace(message, state="active", reason=None)
    if failed or any(state.uncertain for state in states):
        return replace(message, state="unknown", reason="IMAP mailbox state lookup failed")
    return message


def list_messages(provider, *, on_progress=None, incremental=False, sync_state=None, is_owned=None) -> LiveSnapshot:
    """List selectable folders without capture filters or header deduplication."""
    result = LiveSnapshot(provider.source_name, provider.account)
    failed = False
    membership_failed = False
    memberships = {}
    seen = {}
    checked = 0

    def metadata_checked():
        nonlocal checked
        checked += 1
        if on_progress:
            on_progress(checked)

    try:
        folders = _folders(provider)
        all_mail = next((name for name, state in folders.items() if roles.ALL in state.roles), None)
        scoped_incremental = incremental and (
            not provider._is_gmail()
            or (
                all_mail in provider._active_exclude_folders
                and not any(state.unfinished or state.uncertain for state in folders.values())
            )
        )
        prior, prior_excluded = _capture_cursor(provider, sync_state)
        next_cursor, excluded = {}, set()
        for folder, folder_state in sorted(folders.items(), key=lambda item: roles.ALL not in item[1].roles):
            exceptional = folder_state.unfinished or folder_state.uncertain
            try:
                if on_progress:
                    on_progress(checked)
                messages = (
                    _incremental_folder(
                        provider,
                        folder,
                        folder_state,
                        prior,
                        next_cursor,
                        all_mail=all_mail if provider._is_gmail() else None,
                        prior_excluded=prior_excluded,
                        excluded=excluded,
                        on_checked=metadata_checked,
                    )
                    if scoped_incremental
                    else _folder_messages(provider, folder, folder_state, on_checked=metadata_checked)
                )
                for message in messages:
                    if isinstance(message, Exception):
                        failed = True
                        membership_failed |= exceptional
                        continue
                    if exceptional:
                        memberships.setdefault(message.identity_token, []).append(folder_state)
                    if message.state == "eligible" and not message.active_allowed and is_owned and is_owned(message):
                        continue
                    previous_index = seen.get(message.identity_token)
                    if previous_index is not None:
                        previous = result.messages[previous_index]
                        if previous.roles != message.roles or set(previous.labels) != set(message.labels):
                            failed = True
                        priority = {"eligible": 0, "unknown": 1, "active": 2, "discarded": 3}
                        if (priority[message.state], message.active_allowed) > (
                            priority[previous.state],
                            previous.active_allowed,
                        ):
                            result.messages[previous_index] = message
                        continue
                    seen[message.identity_token] = len(result.messages)
                    result.messages.append(message)
            except Exception:
                failed = True
                membership_failed |= exceptional
        result.messages[:] = [
            _membership_state(message, memberships, failed=membership_failed) for message in result.messages
        ]
        proposed = (
            capture.dump(
                capture.CaptureState(
                    cursor=json.dumps(next_cursor),
                    excluded=frozenset(excluded),
                    fingerprint=provider._filter_fingerprint(),
                )
            )
            if scoped_incremental and not failed
            else None
        )
        return replace(
            result,
            complete=not failed,
            reason="Some IMAP messages could not be checked" if failed else None,
            sync_state=proposed,
        )
    except Exception:
        return replace(result, reason="IMAP live enumeration failed")


def _locator(message_id):
    if not isinstance(message_id, str) or not message_id.startswith("imap:"):
        raise LiveLookupError("Missing IMAP identity")
    folder, validity, uid = json.loads(base64.b64decode(message_id[5:], altchars=b"-_", validate=True))
    if (
        not isinstance(folder, str)
        or not folder
        or "\r" in folder
        or "\n" in folder
        or not isinstance(validity, str)
        or not re.fullmatch(r"[1-9][0-9]*", validity)
        or type(uid) is not int
        or uid <= 0
    ):
        raise LiveLookupError("Invalid IMAP identity")
    return folder, validity, uid


def read_messages(provider, message_ids):
    """Read bounded bodies and fresh lifecycle metadata in each selected folder."""
    from ownmail.providers.imap import FETCH_BODY_BATCH_SIZE

    result = {}
    groups = {}
    for message_id in message_ids:
        try:
            folder, validity, uid = _locator(message_id)
            groups.setdefault((folder, validity), {})[uid] = message_id
        except Exception:
            result[message_id] = LiveLookupError("Invalid IMAP identity")
    try:
        folders = _folders(provider)
    except Exception:
        return {message_id: LiveLookupError("IMAP folder listing failed") for message_id in message_ids}
    checked_groups = []
    for (folder, validity), ids in groups.items():
        try:
            if folder not in folders:
                result.update(dict.fromkeys(ids.values()))
                continue
            if _select(provider, folder) != validity:
                raise LiveLookupError("IMAP UIDVALIDITY changed; prior identity is unverified")
            uids = list(ids)
            for offset in range(0, len(uids), FETCH_BODY_BATCH_SIZE):
                batch = uids[offset : offset + FETCH_BODY_BATCH_SIZE]
                try:
                    present = _uids(provider, "UID " + ",".join(map(str, batch)))
                    if not set(present).issubset(batch):
                        raise LiveLookupError("IMAP lookup returned another identity")
                    fetched = (
                        _fetch_many(provider, folder, validity, present, folders[folder], raw=True) if present else {}
                    )
                    result.update({ids[uid]: fetched.get(uid) for uid in batch})
                except Exception as error:
                    result.update(dict.fromkeys((ids[uid] for uid in batch), error))
            checked_groups.append((folder, validity, ids))
        except Exception as error:
            result.update(dict.fromkeys(ids.values(), error))
    exceptional = {folder: state for folder, state in folders.items() if state.unfinished or state.uncertain}
    if provider._is_gmail() and exceptional:
        try:
            memberships = {}
            tokens = {
                message.identity_token
                for message in result.values()
                if isinstance(message, LiveMessage) and message.state == "eligible"
            }
            token_list = sorted(tokens)
            for offset in range(0, len(token_list), FETCH_BODY_BATCH_SIZE):
                batch_tokens = token_list[offset : offset + FETCH_BODY_BATCH_SIZE]
                criterion = ""
                for token in reversed(batch_tokens):
                    key = "X-GM-MSGID " + str(int(token.removeprefix("gmail:"), 16))
                    criterion = "OR " + key + " " + criterion if criterion else key
                for folder, state in exceptional.items():
                    for message in _folder_messages(provider, folder, state, criterion=criterion):
                        if isinstance(message, Exception):
                            raise message
                        if message.identity_token not in batch_tokens:
                            raise LiveLookupError("IMAP membership lookup returned another identity")
                        memberships.setdefault(message.identity_token, []).append(state)
            for message_id, message in result.items():
                if isinstance(message, LiveMessage):
                    result[message_id] = _membership_state(message, memberships)
        except Exception as error:
            for message_id, message in result.items():
                if isinstance(message, LiveMessage) and message.state == "eligible":
                    result[message_id] = error
        for folder, validity, ids in checked_groups:
            try:
                if _select(provider, folder) != validity:
                    raise LiveLookupError("IMAP UIDVALIDITY changed during state checks")
            except Exception as error:
                result.update(dict.fromkeys(ids.values(), error))
    return result


def read_message(provider, message_id: str) -> LiveMessage | None:
    """Confirm UID identity before reading; partial protocol responses retain cache."""
    try:
        result = read_messages(provider, [message_id])[message_id]
        if isinstance(result, Exception):
            raise result
        return result
    except LiveLookupError:
        raise
    except Exception as error:
        raise LiveLookupError("IMAP live lookup failed") from error
