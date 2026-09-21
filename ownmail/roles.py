"""Canonical system-label roles, resolved per provider.

Providers spell the same concept differently — Gmail's API calls it
``TRASH``, Gmail-over-IMAP calls it ``[Gmail]/Trash``, Outlook calls it
``Deleted Items``, a Dovecot server might call it ``INBOX.Trash``, and any
of them may be localized. A role is the concept itself, independent of
spelling, so the rest of ownmail can ask "is this trash?" once.

Roles are derived, never stored: this module is a pure function over
provider state. See ``backlog/docs/doc-7`` for why, and for the resolution
order below.
"""

from __future__ import annotations

# The closed role set. Every member has a consumer; nothing speculative.
INBOX = "inbox"
SENT = "sent"
DRAFTS = "drafts"
TRASH = "trash"
SPAM = "spam"
ARCHIVE = "archive"
ALL = "all"

ROLES = frozenset({INBOX, SENT, DRAFTS, TRASH, SPAM, ARCHIVE, ALL})

# Roles no configuration can admit into the archive.
#
# Trash first, because the reason is structural rather than a preference:
# purge moves a message TO trash, so a trash-inclusive filter would keep
# passing every message it ever purged and the sweep set would grow without
# bound. The only alternative fix is a "skip what is already in trash" case
# inside purge, which is this exclusion again one layer down. Spam does not
# break convergence — purge's destination is trash, not spam — and is fixed on
# the weaker grounds that restoring a false positive in the mail client makes
# it eligible on the next run anyway, so the knob buys nothing.
#
# Accepted and documented cost: mail deleted in a client and never restored is
# never archived. See TASK-14.1 for the full argument.
FIXED_EXCLUDE_ROLES = frozenset({TRASH, SPAM})

# Roles a source may choose to exclude, on top of the fixed ones.
#
# Both mean "its owner has not acted on this yet". Inbox means no decision has
# been made about a finished message; drafts means the message itself is not
# finished, so capturing one freezes half a sentence into the archive forever.
#
# Sent is deliberately absent and must not be added: outgoing mail has no
# triage step, so a rule demanding an action before capture would mean never
# archiving your own mail. Sending is the settling action.
CONFIGURABLE_EXCLUDE_ROLES = frozenset({INBOX, DRAFTS})

# The filter a source gets when it configures nothing.
DEFAULT_EXCLUDE_ROLES = FIXED_EXCLUDE_ROLES | CONFIGURABLE_EXCLUDE_ROLES

# Excluded roles whose membership is re-read every run, so that a message
# leaving one becomes a download candidate.
#
# The split is between excluding a STATE and excluding a CONTAINER. A role is
# something a message passes through — mail leaves trash, leaves the inbox —
# so membership has to be read live or the departure is never seen. A named
# folder is a durable statement ("I never want this"), and nothing about a
# message sitting in one is going to change the answer.
#
# What makes the live read affordable is that these populations are
# self-bounding: an inbox is small by nature, and trash and spam are capped by
# the provider's own retention. A named label has no such bound and can only
# grow, which is why it is never diffed. See TASK-14.3.
TRANSIENT_EXCLUDE_ROLES = frozenset({INBOX, DRAFTS, TRASH, SPAM})

# UNREAD remains reserved by local label editing, search and legacy cleanup.
EPHEMERAL_LABELS = frozenset({"UNREAD"})

# Filter status at provider boundaries, where system IDs are distinguishable
# from real folders and labels with similar names. Existing owned snapshots
# and locally assigned labels are not rewritten.
GMAIL_STATUS_LABELS = EPHEMERAL_LABELS | {"STARRED", "IMPORTANT"}
GMAIL_IMAP_STATUS_LABELS = frozenset({"\\Starred", "\\Important"})
IMAP_STATUS_ATTRIBUTES = frozenset({"\\flagged", "\\important"})

# Labels that recorded where a message was at capture, and that nothing since
# has refreshed.
#
# Archives synced before TASK-14.3 downloaded mail on arrival, while it was
# still in the inbox, so those messages carry an INBOX label meaning "was in
# the inbox when downloaded" — not "is in the inbox". Same for a stored DRAFT.
# The mail itself is real and stays; only the label is a fossil, so it is
# hidden at read and nothing on disk is rewritten (the TASK-5.3 treatment of
# UNREAD).
#
# Matched exactly for the reason EPHEMERAL_LABELS is: these are Gmail system
# label IDs (and IMAP's INBOX, which RFC 3501 spells the same way). Running
# them through ``role_for_label`` instead would case-fold against the folder
# name table and hide a user label legitimately called 'Drafts' — see TASK-26.
#
# Trash and spam are deliberately absent: reconcile sweeps the archive for
# exactly those stored labels, so hiding them would blind it.
STALE_STATE_LABELS = frozenset({"INBOX", "DRAFT"})

# RFC 6154 SPECIAL-USE attributes, as they appear in an IMAP LIST response.
# The authoritative signal when the server advertises it.
_SPECIAL_USE = {
    "\\all": ALL,
    "\\archive": ARCHIVE,
    "\\drafts": DRAFTS,
    "\\junk": SPAM,
    "\\sent": SENT,
    "\\trash": TRASH,
}

# Fallback for servers too old to advertise SPECIAL-USE, matched against the
# leaf folder name, case-insensitively. Deliberately bounded — common English
# and provider spellings plus the most widely seen non-English forms. This is
# a safety net, not exhaustive i18n; exclude_folders is the escape hatch.
_FOLDER_NAMES = {
    TRASH: (
        "trash",
        "deleted",
        "deleted items",
        "deleted messages",
        "bin",
        "papierkorb",
        "gelöscht",
        "corbeille",
        "papelera",
        "elementos eliminados",
        "prullenbak",
        "verwijderde items",
        "cestino",
        "lixeira",
        "kosz",
        "korgen",
        "ゴミ箱",
        "휴지통",
        "已删除邮件",
    ),
    SPAM: (
        "spam",
        "junk",
        "junk e-mail",
        "junk email",
        "bulk mail",
        "unerwünscht",
        "courrier indésirable",
        "indésirables",
        "correo no deseado",
        "no deseado",
        "ongewenste e-mail",
        "posta indesiderata",
        "迷惑メール",
        "스팸편지함",
        "垃圾邮件",
    ),
    DRAFTS: (
        "drafts",
        "draft",
        "entwürfe",
        "brouillons",
        "borradores",
        "concepten",
        "bozze",
        "rascunhos",
        "下書き",
        "임시보관함",
        "草稿",
    ),
    SENT: (
        "sent",
        "sent items",
        "sent messages",
        "sent mail",
        "gesendet",
        "gesendete objekte",
        "envoyés",
        "messages envoyés",
        "enviados",
        "verzonden items",
        "posta inviata",
        "送信済み",
        "보낸편지함",
        "已发送邮件",
    ),
    ALL: (
        # Gmail's catch-all, whose SPECIAL-USE flag is gone once the folder
        # name has been stored as a label. Only multi-word spellings, so a
        # user label can't collide the way a bare 'Todos' or 'All' would.
        "all mail",
        "alle nachrichten",
        "tous les messages",
        "todos los mensajes",
        "tutti i messaggi",
        "すべてのメール",
        "전체보관함",
        "所有邮件",
    ),
    ARCHIVE: (
        "archive",
        "archives",
        "archiv",
        "archivio",
        "archivo",
        "arkiv",
        "アーカイブ",
    ),
}

# Inverted for lookup: leaf name (lowercased) -> role.
_NAME_TO_ROLE = {name: role for role, names in _FOLDER_NAMES.items() for name in names}

# Gmail API system label IDs. Stable and never localized, so a direct map.
# Note the singular DRAFT — Gmail's label ID, not a typo for DRAFTS.
_GMAIL_LABEL_IDS = {
    "INBOX": INBOX,
    "SENT": SENT,
    "DRAFT": DRAFTS,
    "TRASH": TRASH,
    "SPAM": SPAM,
}

_ROLE_TO_GMAIL_LABEL = {role: label_id for label_id, role in _GMAIL_LABEL_IDS.items()}


def resolve_exclude_roles(configured: list[str] | None) -> frozenset[str]:
    """The effective role exclusion for a source's ``exclude_roles`` setting.

    The fixed roles are unioned in unconditionally, so the answer is never
    narrower than trash and spam however the source is configured. Absent
    (``None``) takes the default; an explicit empty list is honoured as
    written, and means "only the fixed roles" — unlike ``exclude_folders``,
    where an empty list is indistinguishable from a list nobody filled in.

    Args:
        configured: Role names from config, or None if the key is absent

    Returns:
        The roles this source excludes from download.
    """
    if configured is None:
        return DEFAULT_EXCLUDE_ROLES
    return FIXED_EXCLUDE_ROLES | frozenset(configured)


def gmail_label_for_role(role: str) -> str | None:
    """Resolve a canonical role back to its Gmail API label ID.

    The inverse of ``role_for_gmail_label``, for asking Gmail *for* a role's
    members rather than classifying what it returns. Answering with a label ID
    matters: ``messages.list(labelIds=[...])`` is exact, where the search
    query it replaces reads an unrecognized term as a user label name and
    filters nothing — a wrong guess there fails silently.

    Args:
        role: Canonical role name

    Returns:
        Gmail label ID, or None for roles Gmail has no system label for.
    """
    return _ROLE_TO_GMAIL_LABEL.get(role)


def role_for_gmail_label(label_id: str) -> str | None:
    """Resolve a Gmail API label ID to a canonical role.

    Args:
        label_id: Gmail label ID (e.g., 'TRASH', 'CATEGORY_PROMOTIONS')

    Returns:
        Role name, or None for user labels and unmapped system labels.
    """
    return _GMAIL_LABEL_IDS.get(label_id)


def role_for_imap_folder(name: str, flags: str = "", delimiter: str = "/") -> str | None:
    """Resolve an IMAP folder to a canonical role.

    Resolution order, highest confidence first:
      1. RFC 6154 SPECIAL-USE attribute in the folder's LIST flags
      2. INBOX, compared case-insensitively as RFC 3501 requires
      3. Leaf-name lookup against the bounded fallback table

    Args:
        name: Folder name as the server reported it (e.g., '[Gmail]/Trash')
        flags: Flags from the LIST response (e.g., '\\HasNoChildren \\Trash')
        delimiter: Hierarchy delimiter the server reported

    Returns:
        Role name, or None if the folder has no canonical role.
    """
    for flag in flags.split():
        role = _SPECIAL_USE.get(flag.lower())
        if role:
            return role

    if name.upper() == "INBOX":
        return INBOX

    leaf = name.rsplit(delimiter, 1)[-1] if delimiter else name
    return _NAME_TO_ROLE.get(leaf.strip().lower())


def role_for_label(label: str) -> str | None:
    """Resolve a stored label string to a canonical role, best effort.

    For labels already written to the archive, where the SPECIAL-USE flags
    that were available at sync time are gone. Tries both provider
    vocabularies, since a stored label may have come from either.

    Both known hierarchy delimiters are tried because the archive doesn't
    record which one the server used.

    Args:
        label: Label as stored in a sidecar or the email_labels table

    Returns:
        Role name, or None if the label has no canonical role.
    """
    role = role_for_gmail_label(label)
    if role:
        return role
    for delimiter in ("/", "."):
        role = role_for_imap_folder(label, delimiter=delimiter)
        if role:
            return role
    return None
