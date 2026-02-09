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
