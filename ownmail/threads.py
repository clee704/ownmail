"""Thread grouping from message headers.

Each indexed message stores the header inputs that grouping needs; components
are computed from those inputs alone. The rules are specified in
backlog/docs/doc-11.
"""

import json
import re
import sqlite3
from email.message import Message

IDENTIFIER_RE = re.compile(r"<[^<>\s]+>")
REPLY_PREFIX_RE = re.compile(r"^(?:\s*(?:re|fwd?):)+", re.IGNORECASE)


def _identifiers(msg: Message, name: str) -> list[str]:
    """Return valid <...> identifiers from every raw `name` header, in order."""
    found = []
    for key, value in msg.raw_items():
        if key.lower() == name.lower():
            found.extend(IDENTIFIER_RE.findall(str(value)))
    return found


def derive_thread_inputs(msg: Message, subject: str) -> dict:
    """Derive a message's grouping inputs.

    Args:
        msg: Parsed message, for its identifier headers
        subject: The message's subject, already decoded by the parser
    """
    message_ids = _identifiers(msg, "Message-ID")
    prefix = REPLY_PREFIX_RE.match(subject)
    stripped = subject[prefix.end() :] if prefix else subject
    return {
        "message_id": message_ids[0] if message_ids else None,
        "references": _identifiers(msg, "References"),
        "in_reply_to": _identifiers(msg, "In-Reply-To"),
        "subject_key": " ".join(stripped.split()).casefold(),
        "is_reply": prefix is not None,
    }


def set_thread_inputs(conn: sqlite3.Connection, email_id: str, inputs: dict) -> None:
    """Replace an indexed message's grouping inputs, keyed to its emails row."""
    conn.execute(
        """
        INSERT OR REPLACE INTO thread_inputs
            (email_id, account, message_id, references_json, in_reply_to_json, subject_key, is_reply)
        SELECT email_id, account, ?, ?, ?, ?, ? FROM emails WHERE email_id = ?
        """,
        (
            inputs["message_id"],
            json.dumps(inputs["references"]),
            json.dumps(inputs["in_reply_to"]),
            inputs["subject_key"],
            int(inputs["is_reply"]),
            email_id,
        ),
    )


def group_threads(records) -> dict[str, str]:
    """Map each message in a multi-message thread to its thread ID.

    Args:
        records: Iterable of (email_id, account, message_id, references,
            in_reply_to, subject_key, is_reply) tuples

    Returns:
        {email_id: thread_id} for components of two or more messages, where
        thread_id is the component's smallest email_id.
    """
    parent: dict = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a, b):
        parent[find(a)] = find(b)

    records = list(records)
    # Reference components: messages sharing any identifier, seen or not.
    for email_id, _account, message_id, references, in_reply_to, _key, _is_reply in records:
        node = ("email", email_id)
        find(node)
        for identifier in ([message_id] if message_id else []) + list(references) + list(in_reply_to):
            union(node, ("id", identifier))

    roots = {email_id: find(("email", email_id)) for email_id, *_ in records}
    sizes: dict = {}
    for root in roots.values():
        sizes[root] = sizes.get(root, 0) + 1

    # Matching messages per (account, subject key) and the components that
    # qualify as fallback candidates for them.
    candidates: dict = {}
    for email_id, account, _mid, _refs, _irt, key, is_reply in records:
        root = roots[email_id]
        if key and (sizes[root] >= 2 or not is_reply):
            candidates.setdefault((account, key), set()).add(root)

    # Decide every fallback against the reference components, then apply.
    joins = []
    for email_id, account, _mid, references, in_reply_to, key, is_reply in records:
        if not is_reply or not key or references or in_reply_to:
            continue
        others = candidates.get((account, key), set()) - {roots[email_id]}
        if len(others) == 1:
            joins.append((("email", email_id), next(iter(others))))
    for node, root in joins:
        union(node, root)

    members: dict = {}
    for email_id, *_ in records:
        members.setdefault(find(("email", email_id)), []).append(email_id)
    return {email_id: min(group) for group in members.values() if len(group) >= 2 for email_id in group}
