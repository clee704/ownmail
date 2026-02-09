"""Tests for the search query parser."""

import pytest

from ownmail.query import (
    Token,
    TokenType,
    ParsedQuery,
    _tokenize,
    _validate_tokens,
    _escape_fts5_value,
    _normalize_date,
    parse_query,
)


class TestTokenize:
    """Tests for the tokenizer."""

    def test_simple_word(self):
        """Test tokenizing a simple word."""
        tokens, error = _tokenize("invoice")
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "invoice"

    def test_multiple_words(self):
        """Test tokenizing multiple words (implicit AND)."""
        tokens, error = _tokenize("invoice report")
        assert error is None
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "invoice"
        assert tokens[1].type == TokenType.WORD
        assert tokens[1].value == "report"

    def test_quoted_phrase(self):
        """Test tokenizing a quoted phrase."""
        tokens, error = _tokenize('"exact phrase"')
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.PHRASE
        assert tokens[0].value == "exact phrase"

    def test_unclosed_quote(self):
        """Test that unclosed quotes return an error."""
        tokens, error = _tokenize('"unclosed phrase')
        assert error is not None
        assert "Unclosed quote" in error

    def test_filter_from(self):
        """Test tokenizing from: filter."""
        tokens, error = _tokenize("from:alice@example.com")
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "from"
        assert tokens[0].value == "alice@example.com"

    def test_filter_to(self):
        """Test tokenizing to: filter."""
        tokens, error = _tokenize("to:bob@example.com")
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "to"
        assert tokens[0].value == "bob@example.com"

    def test_filter_sender_normalized(self):
        """Test that sender: is normalized to from:."""
        tokens, error = _tokenize("sender:alice")
        assert error is None
        assert tokens[0].field == "from"

    def test_filter_label(self):
        """Test tokenizing label: filter."""
        tokens, error = _tokenize("label:inbox")
        assert error is None
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "label"
        assert tokens[0].value == "inbox"

    def test_filter_tag_normalized(self):
        """Test that tag: is normalized to label:."""
        tokens, error = _tokenize("tag:important")
        assert error is None
        assert tokens[0].field == "label"

    def test_filter_before(self):
        """Test tokenizing before: filter."""
        tokens, error = _tokenize("before:2024-06-01")
        assert error is None
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "before"
        assert tokens[0].value == "2024-06-01"

    def test_filter_after(self):
        """Test tokenizing after: filter."""
        tokens, error = _tokenize("after:2024-01-01")
        assert error is None
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "after"
        assert tokens[0].value == "2024-01-01"

    def test_filter_has_attachment(self):
        """Test tokenizing has:attachment filter."""
        tokens, error = _tokenize("has:attachment")
        assert error is None
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "has"
        assert tokens[0].value == "attachment"

    def test_filter_empty_value_error(self):
        """Test that empty filter values return an error."""
        tokens, error = _tokenize("from:")
        assert error is not None
        assert "Empty value" in error

    def test_negation(self):
        """Test tokenizing negation."""
        tokens, error = _tokenize("-spam")
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.NEGATION
        assert tokens[0].value == "spam"

    def test_negated_from_filter(self):
        """Test tokenizing negated from: filter."""
        tokens, error = _tokenize("-from:alice@example.com")
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "from"
        assert tokens[0].value == "alice@example.com"
        assert tokens[0].negated is True

    def test_negated_to_filter(self):
        """Test tokenizing negated to: filter."""
        tokens, error = _tokenize("-to:bob@example.com")
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "to"
        assert tokens[0].value == "bob@example.com"
        assert tokens[0].negated is True

    def test_negated_label_filter(self):
        """Test tokenizing negated label: filter."""
        tokens, error = _tokenize("-label:spam")
        assert error is None
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FILTER
        assert tokens[0].field == "label"
        assert tokens[0].value == "spam"
        assert tokens[0].negated is True

    def test_or_operator(self):
        """Test tokenizing OR operator."""
        tokens, error = _tokenize("invoice OR receipt")
        assert error is None
        assert len(tokens) == 3
        assert tokens[0].type == TokenType.WORD
        assert tokens[1].type == TokenType.OR
        assert tokens[2].type == TokenType.WORD

    def test_and_stripped(self):
        """Test that AND is stripped (implicit in FTS5)."""
        tokens, error = _tokenize("invoice AND receipt")
        assert error is None
        assert len(tokens) == 2
        assert tokens[0].value == "invoice"
        assert tokens[1].value == "receipt"

    def test_parentheses(self):
        """Test tokenizing parentheses."""
        tokens, error = _tokenize("(invoice OR receipt)")
        assert error is None
        assert len(tokens) == 5
        assert tokens[0].type == TokenType.LPAREN
        assert tokens[4].type == TokenType.RPAREN

    def test_complex_query(self):
        """Test tokenizing a complex query."""
        tokens, error = _tokenize('from:alice@test.com "quarterly report" invoice OR receipt -spam')
        assert error is None
        assert len(tokens) == 6
        assert tokens[0].type == TokenType.FILTER
        assert tokens[1].type == TokenType.PHRASE
        assert tokens[2].type == TokenType.WORD
        assert tokens[3].type == TokenType.OR
        assert tokens[4].type == TokenType.WORD
        assert tokens[5].type == TokenType.NEGATION


class TestValidateTokens:
    """Tests for token validation."""

    def test_valid_query(self):
        """Test valid token sequence passes."""
        tokens, _ = _tokenize("invoice receipt")
        error = _validate_tokens(tokens)
        assert error is None

    def test_or_at_start_error(self):
        """Test OR at start returns error."""
        tokens, _ = _tokenize("OR invoice")
        error = _validate_tokens(tokens)
        assert "start with OR" in error

    def test_or_at_end_error(self):
        """Test OR at end returns error."""
        tokens, _ = _tokenize("invoice OR")
        error = _validate_tokens(tokens)
        assert "end with OR" in error

    def test_consecutive_or_error(self):
        """Test consecutive ORs return error."""
        tokens = [
            Token(TokenType.WORD, "invoice"),
            Token(TokenType.OR, "OR"),
            Token(TokenType.OR, "OR"),
            Token(TokenType.WORD, "receipt"),
        ]
        error = _validate_tokens(tokens)
        assert "consecutive OR" in error

    def test_unmatched_closing_paren_error(self):
        """Test unmatched closing paren returns error."""
        tokens = [
            Token(TokenType.WORD, "invoice"),
            Token(TokenType.RPAREN, ")"),
        ]
        error = _validate_tokens(tokens)
        assert "closing parenthesis" in error

    def test_unclosed_paren_error(self):
        """Test unclosed paren returns error."""
        tokens = [
            Token(TokenType.LPAREN, "("),
            Token(TokenType.WORD, "invoice"),
        ]
        error = _validate_tokens(tokens)
        assert "Unclosed parenthesis" in error


class TestEscapeFTS5Value:
    """Tests for FTS5 value escaping."""

    def test_plain_word_not_escaped(self):
        """Test plain word is not modified."""
        assert _escape_fts5_value("invoice") == "invoice"

    def test_email_address_quoted(self):
        """Test email address with @ is quoted."""
        result = _escape_fts5_value("alice@example.com")
        assert result == '"alice@example.com"'

    def test_hyphenated_word_quoted(self):
        """Test hyphenated word is quoted."""
        result = _escape_fts5_value("year-end")
        assert result == '"year-end"'

    def test_internal_quotes_escaped(self):
        """Test internal quotes are escaped."""
        result = _escape_fts5_value('o"brien')
        assert result == '"o""brien"'


class TestNormalizeDate:
    """Tests for date normalization."""

    def test_iso_format(self):
        """Test ISO format is normalized."""
        assert _normalize_date("2024-06-15") == "2024-06-15"

    def test_compact_format(self):
        """Test compact format is normalized."""
        assert _normalize_date("20240615") == "2024-06-15"

    def test_invalid_month(self):
        """Test invalid month returns None."""
        assert _normalize_date("2024-13-01") is None

    def test_invalid_day(self):
        """Test invalid day returns None."""
        assert _normalize_date("2024-06-32") is None

    def test_invalid_format(self):
        """Test invalid format returns None."""
        assert _normalize_date("not-a-date") is None


class TestParseQuery:
    """Tests for the full query parser."""

    def test_simple_term(self):
        """Test parsing simple term."""
        result = parse_query("invoice")
        assert result.error is None
        assert result.fts_query == "invoice"
        assert not result.where_clauses

    def test_phrase(self):
        """Test parsing phrase."""
        result = parse_query('"exact phrase"')
        assert result.error is None
        assert result.fts_query == '"exact phrase"'

    def test_from_email_filter(self):
        """Test from: with email becomes SQL WHERE."""
        result = parse_query("from:alice@test.com")
        assert result.error is None
        assert "e.sender_email = ?" in result.where_clauses
        assert "alice@test.com" in result.params
        assert result.fts_query == ""

    def test_from_name_filter(self):
        """Test from: with name becomes FTS."""
        result = parse_query("from:alice")
        assert result.error is None
        assert "sender:alice" in result.fts_query

    def test_to_email_filter(self):
        """Test to: with email becomes special marker."""
        result = parse_query("to:bob@test.com")
        assert result.error is None
        assert "__RECIPIENT_EMAIL__" in result.where_clauses
        assert "bob@test.com" in result.params

    def test_subject_filter(self):
        """Test subject: filter becomes FTS."""
        result = parse_query("subject:meeting")
        assert result.error is None
        assert "subject:" in result.fts_query

    def test_label_filter(self):
        """Test label: filter becomes SQL WHERE."""
        result = parse_query("label:inbox")
        assert result.error is None
        assert "e.labels LIKE ?" in result.where_clauses
        assert "%inbox%" in result.params

    def test_before_filter(self):
        """Test before: filter becomes SQL WHERE."""
        result = parse_query("before:2024-06-01")
        assert result.error is None
        assert "e.email_date < ?" in result.where_clauses
        assert "2024-06-01" in result.params

    def test_after_filter(self):
        """Test after: filter becomes SQL WHERE."""
        result = parse_query("after:2024-01-01")
        assert result.error is None
        assert "e.email_date >= ?" in result.where_clauses
        assert "2024-01-01" in result.params

    def test_invalid_date_error(self):
        """Test invalid date returns error."""
        result = parse_query("before:not-a-date")
        assert result.error is not None
        assert "Invalid date" in result.error

    def test_has_attachment(self):
        """Test has:attachment filter."""
        result = parse_query("has:attachment")
        assert result.error is None
        assert "e.attachments IS NOT NULL" in result.where_clauses[0]

    def test_negation(self):
        """Test negation becomes FTS NOT."""
        result = parse_query("-spam")
        assert result.error is None
        assert "NOT spam" in result.fts_query

    def test_negated_from_email_filter(self):
        """Test -from:email generates != WHERE clause."""
        result = parse_query("snupo -from:snupo@snupo.org")
        assert result.error is None
        assert "snupo" in result.fts_query
        assert "e.sender_email != ?" in result.where_clauses
        assert "snupo@snupo.org" in result.params

    def test_negated_from_name_filter(self):
        """Test -from:name generates FTS NOT."""
        result = parse_query("-from:alice")
        assert result.error is None
        assert "NOT sender:alice" in result.fts_query

    def test_negated_to_email_filter(self):
        """Test -to:email generates NOT_RECIPIENT_EMAIL marker."""
        result = parse_query("-to:bob@example.com")
        assert result.error is None
        assert "__NOT_RECIPIENT_EMAIL__" in result.where_clauses
        assert "bob@example.com" in result.params

    def test_negated_subject_filter(self):
        """Test -subject:word generates FTS NOT."""
        result = parse_query("-subject:spam")
        assert result.error is None
        assert "NOT subject:spam" in result.fts_query

    def test_negated_label_filter(self):
        """Test -label:name generates NOT LIKE WHERE clause."""
        result = parse_query("-label:spam")
        assert result.error is None
        assert "(e.labels IS NULL OR e.labels NOT LIKE ?)" in result.where_clauses
        assert "%spam%" in result.params

    def test_negated_has_attachment(self):
        """Test -has:attachment excludes attachments."""
        result = parse_query("-has:attachment")
        assert result.error is None
        assert "(e.attachments IS NULL OR e.attachments = '')" in result.where_clauses

    def test_or_operator(self):
        """Test OR operator."""
        result = parse_query("invoice OR receipt")
        assert result.error is None
        assert "OR" in result.fts_query

    def test_combined_query(self):
        """Test query with filters and text."""
        result = parse_query("from:alice@test.com label:inbox invoice")
        assert result.error is None
        assert "e.sender_email = ?" in result.where_clauses
        assert "e.labels LIKE ?" in result.where_clauses
        assert result.fts_query == "invoice"

    def test_unclosed_quote_error(self):
        """Test unclosed quote returns error."""
        result = parse_query('"unclosed')
        assert result.error is not None
        assert "Unclosed quote" in result.error

    def test_or_at_end_error(self):
        """Test OR at end returns error."""
        result = parse_query("invoice OR")
        assert result.error is not None
        assert "end with OR" in result.error

    def test_empty_query(self):
        """Test empty query returns empty ParsedQuery."""
        result = parse_query("")
        assert result.error is None
        assert result.fts_query == ""
        assert not result.where_clauses

    def test_empty_filter_value_error(self):
        """Test empty filter value returns error."""
        result = parse_query("from:")
        assert result.error is not None
        assert "Empty value" in result.error

    def test_from_obrien_escaped(self):
        """Test special characters in values are escaped."""
        result = parse_query("from:o'brien")
        assert result.error is None
        # The apostrophe doesn't need FTS escaping, but @ would
        # Just verify no error
        assert "sender:" in result.fts_query

    def test_special_chars_in_search(self):
        """Test special characters in search terms are handled."""
        result = parse_query("c++ tutorial")
        assert result.error is None
        # ++ might need escaping but should not error

    def test_has_fts_method(self):
        """Test has_fts() method."""
        result = parse_query("invoice")
        assert result.has_fts() is True

        result2 = parse_query("from:alice@test.com")
        assert result2.has_fts() is False

    def test_has_error_method(self):
        """Test has_error() method."""
        result = parse_query("invoice")
        assert result.has_error() is False

        result2 = parse_query('"unclosed')
        assert result2.has_error() is True
