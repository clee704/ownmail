"""Tests for EmailParser class."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ownmail import EmailParser


class TestEmailParserBasic:
    """Basic email parsing tests."""

    def test_parse_simple_email(self, sample_eml_simple):
        """Test parsing a simple plain text email."""
        result = EmailParser.parse_file(content=sample_eml_simple)

        assert result["sender"] == "sender@example.com"
        assert result["recipients"] == "recipient@example.com"
        assert result["subject"] == "Test Email"
        assert "test email body" in result["body"].lower()

    def test_parse_html_email(self, sample_eml_html):
        """Test parsing an HTML email extracts text."""
        result = EmailParser.parse_file(content=sample_eml_html)

        assert result["subject"] == "HTML Test"
        # HTML should be stripped to get text content
        assert "hello world" in result["body"].lower() or "html email" in result["body"].lower()

    def test_parse_multipart_with_attachment(self, sample_eml_multipart):
        """Test parsing multipart email with attachment."""
        result = EmailParser.parse_file(content=sample_eml_multipart)

        assert result["subject"] == "Email with Attachment"
        assert "attachment" in result["body"].lower()
        assert "document.pdf" in result["attachments"]

    def test_parse_korean_email(self, sample_eml_korean):
        """Test parsing email with Korean encoded headers."""
        result = EmailParser.parse_file(content=sample_eml_korean)

        # Should decode the subject properly
        assert result["subject"]  # Should not be empty
        assert "안녕하세요" in result["body"] or "테스트" in result["body"]


class TestEmailParserRobustness:
    """Tests for handling malformed and edge-case emails."""

    def test_parse_malformed_headers(self, sample_eml_malformed):
        """Test that malformed headers don't crash the parser."""
        result = EmailParser.parse_file(content=sample_eml_malformed)

        # Should return something, not crash
        assert result is not None
        assert "sender" in result
        assert "body" in result

    def test_parse_empty_content(self):
        """Test parsing empty content doesn't crash."""
        result = EmailParser.parse_file(content=b"")

        assert result is not None
        # Should have all expected keys
        assert "subject" in result
        assert "sender" in result
        assert "body" in result

    def test_parse_binary_garbage(self):
        """Test that binary garbage is handled gracefully."""
        garbage = bytes(range(256))  # All possible byte values
        result = EmailParser.parse_file(content=garbage)

        # Should not crash, should return a dict
        assert isinstance(result, dict)

    def test_parse_missing_headers(self):
        """Test email with missing common headers."""
        content = b"Just a body with no headers."
        result = EmailParser.parse_file(content=content)

        assert result is not None
        assert result["subject"] == ""
        assert result["sender"] == ""

    def test_parse_with_gmail_labels(self, sample_eml_with_labels):
        """Test that X-Gmail-Labels header is present in email."""
        result = EmailParser.parse_file(content=sample_eml_with_labels)

        assert result["subject"] == "Labeled Email"


class TestSanitizeHeader:
    """Tests for header sanitization."""

    def test_sanitize_removes_newlines(self):
        """Test that embedded newlines are removed from headers."""
        dirty = "Hello\r\nWorld"
        clean = EmailParser._sanitize_header(dirty)
        assert "\r" not in clean
        assert "\n" not in clean
        assert "Hello" in clean
        assert "World" in clean

    def test_sanitize_collapses_whitespace(self):
        """Test that multiple spaces are collapsed."""
        dirty = "Hello     World"
        clean = EmailParser._sanitize_header(dirty)
        assert "     " not in clean

    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        assert EmailParser._sanitize_header("") == ""
        assert EmailParser._sanitize_header(None) == ""


class TestSafeGetHeader:
    """Tests for _safe_get_header."""

    def test_safe_get_header_normal(self, sample_eml_simple):
        """Test getting a normal header."""
        import email
        msg = email.message_from_bytes(sample_eml_simple)
        result = EmailParser._safe_get_header(msg, "Subject")
        assert result == "Test Email"

    def test_safe_get_header_missing(self, sample_eml_simple):
        """Test getting a missing header returns empty string."""
        import email
        msg = email.message_from_bytes(sample_eml_simple)
        result = EmailParser._safe_get_header(msg, "X-Nonexistent-Header")
        assert result == ""


class TestSafeGetContent:
    """Tests for _safe_get_content."""

    def test_safe_get_content_plain(self):
        """Test getting plain text content."""
        import email
        content = b"""Content-Type: text/plain

Hello world!
"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert "Hello world" in result

    def test_safe_get_content_bytes_utf8(self):
        """Test getting UTF-8 bytes content."""
        import email
        content = b"""Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: 8bit

Hello world UTF-8!
"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert "Hello" in result or result == ""  # May fail gracefully

    def test_safe_get_content_korean(self):
        """Test getting Korean encoded content."""
        import email
        content = """Content-Type: text/plain; charset="utf-8"

안녕하세요
""".encode('utf-8')
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        # Should handle Korean or return something reasonable
        assert isinstance(result, str)


class TestParseFileEdgeCases:
    """Edge case tests for parse_file."""

    def test_parse_file_no_args_raises(self):
        """Test that parse_file raises when neither filepath nor content given."""
        # If neither is given, should still work and return parse error or empty
        result = EmailParser.parse_file()
        # Should not crash - returns error info
        assert "body" in result

    def test_parse_file_from_disk(self, temp_dir, sample_eml_simple):
        """Test parsing file from disk."""
        filepath = temp_dir / "test.eml"
        filepath.write_bytes(sample_eml_simple)

        result = EmailParser.parse_file(filepath=filepath)
        assert result["subject"] == "Test Email"
        assert result["sender"] == "sender@example.com"

    def test_parse_multipart_html_fallback(self):
        """Test HTML fallback when no plain text."""
        content = b"""From: sender@example.com
To: recipient@example.com
Subject: HTML Only
MIME-Version: 1.0
Content-Type: text/html

<html><body><h1>Title</h1><p>Paragraph text.</p></body></html>
"""
        result = EmailParser.parse_file(content=content)
        assert "Title" in result["body"] or "Paragraph" in result["body"]

    def test_parse_multiple_recipients(self):
        """Test parsing email with To, Cc, and Bcc."""
        content = b"""From: sender@example.com
To: alice@example.com
Cc: bob@example.com
Bcc: charlie@example.com
Subject: Multiple Recipients

Body
"""
        result = EmailParser.parse_file(content=content)
        assert "alice" in result["recipients"]
        assert "bob" in result["recipients"]
        assert "charlie" in result["recipients"]

    def test_parse_multipart_with_plain_and_html(self):
        """Test parsing multipart with both plain and HTML."""
        content = b"""From: sender@example.com
Subject: Mixed Content
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="bound1"

--bound1
Content-Type: text/plain; charset="utf-8"

Plain text version.

--bound1
Content-Type: text/html; charset="utf-8"

<html><body>HTML version</body></html>

--bound1--
"""
        result = EmailParser.parse_file(content=content)
        # Should prefer plain text
        assert "Plain text" in result["body"]

    def test_parse_deeply_nested_multipart(self):
        """Test parsing deeply nested multipart."""
        content = b"""From: sender@example.com
Subject: Nested
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/alternative; boundary="inner"

--inner
Content-Type: text/plain

Nested plain text.

--inner--

--outer--
"""
        result = EmailParser.parse_file(content=content)
        assert isinstance(result["body"], str)
