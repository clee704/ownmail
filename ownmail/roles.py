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

# Roles excluded from download unless the source overrides exclude_folders.
DEFAULT_EXCLUDE_ROLES = frozenset({TRASH, SPAM})

# Gmail label IDs for mail-client state ownmail deliberately does not archive.
#
# Read/unread is a property of a mailbox session, not of the message. Sync
# never re-fetches a message it already has, so a captured value is frozen at
# download time and only decays: mail is picked up around arrival, when it is
# usually unread, and nothing later corrects it. Standard IMAP puts the same
# fact in the \Seen flag, which ownmail does not read either — dropping it on
# the Gmail side is what makes the two providers agree.
#
# Matched exactly, never case-folded: these are Gmail system label IDs, which
# are always upper-case and cannot collide with a user label. A differently
# cased IMAP folder (`Unread`) is a real folder and is kept.
EPHEMERAL_LABELS = frozenset({"UNREAD"})

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
