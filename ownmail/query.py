"""Search query parser for ownmail.

Parses user-friendly email search queries and translates them into
FTS5 queries + SQL WHERE clauses. Handles validation and error reporting
so users never see raw SQLite FTS5 errors.

Supported syntax:
    invoice                     Full-text search across all fields
    "exact phrase"              Phrase match
    from:alice@example.com      Sender filter (email)
    from:alice                  Sender filter (name, uses FTS)
    to:bob@example.com          Recipient filter (email)
    to:bob                      Recipient filter (name, uses FTS)
    subject:meeting             Subject field search (FTS)
    label:inbox                 Label/folder filter
    has:attachment              Emails with attachments
    before:2024-06-01           Date filter
    after:2024-01-01            Date filter
    -keyword                    Exclude emails containing keyword
    invoice OR receipt          Boolean OR (AND is implicit)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto


class TokenType(Enum):
    """Types of tokens in search queries."""
    WORD = auto()           # Plain word: invoice
    PHRASE = auto()         # Quoted phrase: "exact phrase"
    FILTER = auto()         # Field filter: from:alice
    NEGATION = auto()       # Negated term: -spam
    OR = auto()             # Boolean OR operator
    LPAREN = auto()         # Left parenthesis (
    RPAREN = auto()         # Right parenthesis )


@dataclass
class Token:
    """A single token from the search query."""
    type: TokenType
    value: str
    field: str = ""  # For FILTER tokens: from, to, subject, etc.
    negated: bool = False  # For negated filters: -from:alice


@dataclass
class ParsedQuery:
    """Result of parsing a search query.

    Attributes:
        fts_query: Safe FTS5 MATCH string (may be empty)
        where_clauses: SQL WHERE conditions (without leading AND)
        params: Bound parameters for WHERE clauses
        error: Parse error message, if any
    """
    fts_query: str = ""
    where_clauses: list[str] = field(default_factory=list)
    params: list = field(default_factory=list)
    error: str | None = None

    def has_fts(self) -> bool:
        """Return True if there's an FTS query to execute."""
        return bool(self.fts_query.strip())

    def has_error(self) -> bool:
        """Return True if there was a parse error."""
        return self.error is not None


# FTS5 special characters that need quoting
FTS5_SPECIAL_CHARS = set('.@-+*"():^')

# Date pattern: YYYY-MM-DD or YYYYMMDD
DATE_PATTERN = re.compile(r'^(\d{4})-?(\d{2})-?(\d{2})$')


def _tokenize(query: str) -> tuple[list[Token], str | None]:
    """Tokenize a search query into structured tokens.

    Returns:
        Tuple of (tokens, error_message). If error_message is set, tokens may be incomplete.
    """
    tokens = []
    i = 0
    query = query.strip()

    while i < len(query):
        # Skip whitespace
        while i < len(query) and query[i].isspace():
            i += 1
        if i >= len(query):
            break

        char = query[i]

        # Quoted phrase
        if char == '"':
            end = query.find('"', i + 1)
            if end == -1:
                # Unclosed quote - find the partial phrase for error message
                partial = query[i+1:i+20]
                if len(query) > i + 20:
                    partial += "..."
                return tokens, f"Unclosed quote after '{partial}'"
            phrase = query[i+1:end]
            tokens.append(Token(TokenType.PHRASE, phrase))
            i = end + 1
            continue

        # Parentheses
        if char == '(':
            tokens.append(Token(TokenType.LPAREN, '('))
            i += 1
            continue
        if char == ')':
            tokens.append(Token(TokenType.RPAREN, ')'))
            i += 1
            continue

        # Negation (must be followed by a word or quote, not whitespace)
        if char == '-' and i + 1 < len(query) and not query[i+1].isspace():
            next_char = query[i + 1]

            # Negated phrase: -"exact phrase"
            if next_char == '"':
                end = query.find('"', i + 2)
                if end == -1:
                    partial = query[i+2:i+22]
                    if len(query) > i + 22:
                        partial += "..."
                    return tokens, f"Unclosed quote after '{partial}'"
                phrase = query[i+2:end]
                # Negated phrase - add as NEGATION with the phrase value
                tokens.append(Token(TokenType.NEGATION, phrase))
                i = end + 1
                continue

            # Find the word after -
            j = i + 1
            while j < len(query) and not query[j].isspace() and query[j] not in '()':
                j += 1
            word = query[i+1:j]
            if word:
                # Check if it's a negated filter (-from:alice@example.com)
                colon_pos = word.find(':')
                if colon_pos > 0:
                    field_name = word[:colon_pos].lower()
                    field_value = word[colon_pos+1:]

                    # Check if it's a known filter field
                    known_filters = {
                        'from', 'sender', 'to', 'recipients', 'subject',
                        'label', 'tag', 'before', 'after', 'has', 'attachment', 'attachments'
                    }

                    if field_name in known_filters:
                        if not field_value:
                            return tokens, f"Empty value for '-{field_name}:' filter"
                        # Normalize field names
                        if field_name == 'sender':
                            field_name = 'from'
                        elif field_name == 'recipients':
                            field_name = 'to'
                        elif field_name == 'tag':
                            field_name = 'label'
                        elif field_name == 'attachments':
                            field_name = 'attachment'
                        # Note: has:attachment stays as-is, attachment:pdf stays as-is

                        tokens.append(Token(TokenType.FILTER, field_value, field=field_name, negated=True))
                        i = j
                        continue

                # Regular negation (not a filter)
                tokens.append(Token(TokenType.NEGATION, word))
            i = j
            continue

        # Word or filter (field:value)
        # Collect until whitespace or special char
        j = i
        while j < len(query) and not query[j].isspace() and query[j] not in '()"':
            j += 1
        segment = query[i:j]

        if not segment:
            i = j + 1
            continue

        # Check if it's OR operator
        if segment.upper() == 'OR':
            tokens.append(Token(TokenType.OR, 'OR'))
            i = j
            continue

        # Check if it's AND operator (we'll strip these later)
        if segment.upper() == 'AND':
            # Skip AND - it's implicit in FTS5
            i = j
            continue

        # Check if it's a filter (field:value)
        colon_pos = segment.find(':')
        if colon_pos > 0:
            field_name = segment[:colon_pos].lower()
            field_value = segment[colon_pos+1:]

            # Validate known filter fields
            known_filters = {
                'from', 'sender', 'to', 'recipients', 'subject',
                'label', 'tag', 'before', 'after', 'has', 'attachment', 'attachments'
            }

            if field_name in known_filters:
                if not field_value:
                    return tokens, f"Empty value for '{field_name}:' filter"
                # Normalize field names
                if field_name == 'sender':
                    field_name = 'from'
                elif field_name == 'recipients':
                    field_name = 'to'
                elif field_name == 'tag':
                    field_name = 'label'
                elif field_name == 'attachments':
                    field_name = 'attachment'
                # Note: has:attachment stays as-is, attachment:pdf stays as-is

                tokens.append(Token(TokenType.FILTER, field_value, field=field_name))
                i = j
                continue

        # Plain word
        tokens.append(Token(TokenType.WORD, segment))
        i = j

    return tokens, None


def _validate_tokens(tokens: list[Token]) -> str | None:
    """Validate token sequence for logical errors.

    Returns error message if invalid, None if valid.
    """
    if not tokens:
        return None

    # Check for OR at start or end
    if tokens[0].type == TokenType.OR:
        return "Search cannot start with OR"
    if tokens[-1].type == TokenType.OR:
        return "Search cannot end with OR"

    # Check for consecutive ORs or OR followed by nothing useful
    for i, token in enumerate(tokens):
        if token.type == TokenType.OR:
            if i + 1 < len(tokens) and tokens[i + 1].type == TokenType.OR:
                return "Invalid: consecutive OR operators"

    # Check parentheses balance
    depth = 0
    for token in tokens:
        if token.type == TokenType.LPAREN:
            depth += 1
        elif token.type == TokenType.RPAREN:
            depth -= 1
            if depth < 0:
                return "Unmatched closing parenthesis"
    if depth > 0:
        return "Unclosed parenthesis"

    return None


def _escape_fts5_value(value: str) -> str:
    """Escape a value for safe inclusion in FTS5 query.

    Wraps in quotes if it contains special characters or whitespace.
    Escapes internal quotes by doubling them.
    Preserves trailing * for prefix matching.
    """
    # Handle prefix matching: meet* should stay as meet* (unquoted)
    if value.endswith('*'):
        prefix = value[:-1]
        # Check if the prefix part needs quoting
        needs_quoting = any(c in FTS5_SPECIAL_CHARS or c.isspace() for c in prefix)
        if needs_quoting:
            escaped = prefix.replace('"', '""')
            return f'"{escaped}"*'
        return value  # Return as-is: meet*

    # Check if quoting is needed (special chars or whitespace)
    needs_quoting = any(c in FTS5_SPECIAL_CHARS or c.isspace() for c in value)

    if needs_quoting:
        # Escape internal quotes by doubling
        escaped = value.replace('"', '""')
        return f'"{escaped}"'
    return value


def _normalize_date(date_str: str) -> str | None:
    """Normalize date string to YYYY-MM-DD format.

    Accepts YYYY-MM-DD or YYYYMMDD.
    Returns None if invalid.
    """
    match = DATE_PATTERN.match(date_str)
    if not match:
        return None
    year, month, day = match.groups()
    # Basic validation
    try:
        m, d = int(month), int(day)
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return None
    except ValueError:
        return None
    return f"{year}-{month}-{day}"


def parse_query(query: str) -> ParsedQuery:
    """Parse a user search query into FTS5 query and SQL WHERE clauses.

    Args:
        query: User's search query string

    Returns:
        ParsedQuery with fts_query, where_clauses, params, and optional error
    """
    if not query or not query.strip():
        return ParsedQuery()

    # Tokenize
    tokens, error = _tokenize(query)
    if error:
        return ParsedQuery(error=error)

    # Validate
    error = _validate_tokens(tokens)
    if error:
        return ParsedQuery(error=error)

    # Translate tokens into FTS5 query parts and SQL WHERE clauses
    fts_parts = []
    where_clauses = []
    params = []

    for token in tokens:
        if token.type == TokenType.WORD:
            fts_parts.append(_escape_fts5_value(token.value))

        elif token.type == TokenType.PHRASE:
            # Phrases are already quoted, just escape internal quotes
            escaped = token.value.replace('"', '""')
            fts_parts.append(f'"{escaped}"')

        elif token.type == TokenType.NEGATION:
            # FTS5 NOT syntax
            fts_parts.append(f'NOT {_escape_fts5_value(token.value)}')

        elif token.type == TokenType.OR:
            fts_parts.append('OR')

        elif token.type == TokenType.LPAREN:
            fts_parts.append('(')

        elif token.type == TokenType.RPAREN:
            fts_parts.append(')')

        elif token.type == TokenType.FILTER:
            field = token.field
            value = token.value
            negated = token.negated

            if field == 'from':
                if '@' in value:
                    # Email address - exact match on sender_email column
                    if negated:
                        where_clauses.append("e.sender_email != ?")
                    else:
                        where_clauses.append("e.sender_email = ?")
                    params.append(value.lower())
                else:
                    # Name search - use FTS on sender field
                    escaped = _escape_fts5_value(value)
                    if negated:
                        fts_parts.append(f'NOT sender:{escaped}')
                    else:
                        fts_parts.append(f'sender:{escaped}')

            elif field == 'to':
                if '@' in value:
                    # Email address - use normalized table
                    # This is handled specially in search() - we set a flag
                    if negated:
                        where_clauses.append("__NOT_RECIPIENT_EMAIL__")
                    else:
                        where_clauses.append("__RECIPIENT_EMAIL__")
                    params.append(value.lower())
                else:
                    # Name search - use FTS on recipients field
                    escaped = _escape_fts5_value(value)
                    if negated:
                        fts_parts.append(f'NOT recipients:{escaped}')
                    else:
                        fts_parts.append(f'recipients:{escaped}')

            elif field == 'subject':
                # Subject search via FTS
                escaped = _escape_fts5_value(value)
                if negated:
                    fts_parts.append(f'NOT subject:{escaped}')
                else:
                    fts_parts.append(f'subject:{escaped}')

            elif field == 'label':
                # Label filter on labels column
                if negated:
                    where_clauses.append("(e.labels IS NULL OR e.labels NOT LIKE ?)")
                else:
                    where_clauses.append("e.labels LIKE ?")
                params.append(f"%{value}%")

            elif field == 'before':
                normalized = _normalize_date(value)
                if normalized is None:
                    return ParsedQuery(error=f"Invalid date format for 'before:': {value}")
                if negated:
                    where_clauses.append("e.email_date >= ?")
                else:
                    where_clauses.append("e.email_date < ?")
                params.append(normalized)

            elif field == 'after':
                normalized = _normalize_date(value)
                if normalized is None:
                    return ParsedQuery(error=f"Invalid date format for 'after:': {value}")
                if negated:
                    where_clauses.append("e.email_date < ?")
                else:
                    where_clauses.append("e.email_date >= ?")
                params.append(normalized)

            elif field == 'has' and value in ('attachment', 'attachments'):
                # Emails with attachments - use has_attachments column in emails table
                if negated:
                    where_clauses.append("e.has_attachments = 0")
                else:
                    where_clauses.append("e.has_attachments = 1")

            elif field == 'attachment':
                # Filter by attachment filename/type (e.g., attachment:pdf)
                # Use FTS column search since attachments only in emails_fts
                escaped = _escape_fts5_value(value)
                if negated:
                    fts_parts.append(f'NOT attachments:{escaped}')
                else:
                    fts_parts.append(f'attachments:{escaped}')

    # Build final FTS query
    fts_query = ' '.join(fts_parts)

    # Clean up FTS query - remove empty parts, normalize whitespace
    fts_query = ' '.join(fts_query.split())

    return ParsedQuery(
        fts_query=fts_query,
        where_clauses=where_clauses,
        params=params
    )
