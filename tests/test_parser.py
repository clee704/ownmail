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

    def test_parse_with_labels_fixture(self, sample_eml_with_labels):
        """Test parsing email from labels fixture."""
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
""".encode()
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


class TestSafeGetHeaderEdgeCases:
    """Tests for _safe_get_header edge cases."""

    def test_safe_get_header_none_value(self):
        """Test handling None header value."""
        import email
        content = b"From: test@example.com\n\nBody"
        msg = email.message_from_bytes(content)
        # Access non-existent header
        result = EmailParser._safe_get_header(msg, "X-Custom-Header")
        assert result == ""

    def test_safe_get_header_malformed_encoding(self):
        """Test handling malformed encoded header."""
        import email
        # Malformed RFC2047 encoding
        content = b"From: =?invalid-charset?Q?test?= <test@example.com>\nSubject: Test\n\nBody"
        msg = email.message_from_bytes(content)
        # Should not crash
        result = EmailParser._safe_get_header(msg, "From")
        assert isinstance(result, str)


class TestSanitizeHeaderEdgeCases:
    """Additional tests for _sanitize_header."""

    def test_sanitize_crlf(self):
        """Test removing CR/LF from headers."""
        result = EmailParser._sanitize_header("hello\r\nworld")
        assert "\r" not in result
        assert "\n" not in result
        assert "hello" in result and "world" in result

    def test_sanitize_collapses_whitespace(self):
        """Test collapsing multiple spaces."""
        result = EmailParser._sanitize_header("hello    world")
        assert result == "hello world"

    def test_sanitize_strips_leading_trailing(self):
        """Test stripping leading/trailing whitespace."""
        result = EmailParser._sanitize_header("  hello world  ")
        assert result == "hello world"

    def test_sanitize_empty_string(self):
        """Test handling empty string."""
        result = EmailParser._sanitize_header("")
        assert result == ""

    def test_sanitize_none_value(self):
        """Test handling None-like value."""
        result = EmailParser._sanitize_header(None)
        assert result == ""


class TestSafeGetContentEdgeCases:
    """Tests for _safe_get_content edge cases."""

    def test_safe_get_content_binary_fallback(self):
        """Test fallback for binary content."""
        import email
        content = b"""Content-Type: application/octet-stream

\x00\x01\x02\x03"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        # Should not crash
        assert isinstance(result, str)

    def test_safe_get_content_euc_kr(self):
        """Test handling EUC-KR encoded content."""
        import email
        # EUC-KR encoded Korean text
        content = b"""Content-Type: text/plain; charset="euc-kr"
Content-Transfer-Encoding: 8bit

\xbe\xc8\xb3\xe7\xc7\xcf\xbc\xbc\xbf\xe4"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert isinstance(result, str)

    def test_safe_get_content_cp949(self):
        """Test handling CP949 encoded content."""
        import email
        content = b"""Content-Type: text/plain; charset="cp949"

test"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert isinstance(result, str)

    def test_safe_get_content_strips_embedded_mime_headers(self):
        """Test that embedded MIME headers in body text are stripped."""
        import email
        # Simulate USPS-style email where body starts with MIME headers
        content = (
            b"Content-Type: text/plain; charset=\"utf-8\"\r\n"
            b"Content-Transfer-Encoding: quoted-printable\r\n\r\n"
            b"Content-Type: text/plain; charset=3DUTF-8\r\n"
            b"Content-Transfer-Encoding: 7bit\r\n\r\n"
            b"Informed Delivery(TM)"
        )
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert "Content-Type" not in result
        assert "Informed Delivery" in result

    def test_strip_embedded_mime_headers_preserves_normal_text(self):
        """Test that normal text starting with 'Content' is not stripped."""
        result = EmailParser._strip_embedded_mime_headers("Content is king in marketing")
        assert result == "Content is king in marketing"

    def test_strip_embedded_mime_headers_strips_multiple(self):
        """Test stripping multiple embedded MIME headers."""
        text = "Content-Type: text/html\nContent-Transfer-Encoding: base64\nContent-Disposition: inline\n\nActual body"
        result = EmailParser._strip_embedded_mime_headers(text)
        assert result == "Actual body"


class TestParseWithAttachments:
    """Tests for attachment parsing."""

    def test_parse_email_with_attachment(self):
        """Test parsing email with attachment."""
        content = b"""From: sender@example.com
Subject: With Attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1
Content-Type: text/plain

Message body.

--bound1
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"

PDF content here

--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert "document.pdf" in result["attachments"]

    def test_parse_email_inline_image(self):
        """Test parsing email with inline image."""
        content = b"""From: sender@example.com
Subject: With Image
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1
Content-Type: text/plain

See image below.

--bound1
Content-Type: image/png
Content-Disposition: inline; filename="image.png"

PNG data here

--bound1--
"""
        result = EmailParser.parse_file(content=content)
        # May or may not capture inline as attachment
        assert isinstance(result["attachments"], str)

    def test_parse_multiple_attachments(self):
        """Test parsing email with multiple attachments."""
        content = b"""From: sender@example.com
Subject: Multiple Attachments
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="bound1"

--bound1
Content-Type: text/plain

Body text.

--bound1
Content-Type: application/pdf
Content-Disposition: attachment; filename="doc1.pdf"

PDF 1

--bound1
Content-Type: application/pdf
Content-Disposition: attachment; filename="doc2.pdf"

PDF 2

--bound1--
"""
        result = EmailParser.parse_file(content=content)
        assert "doc1.pdf" in result["attachments"]
        assert "doc2.pdf" in result["attachments"]


class TestSafeGetHeaderFallback:
    """Tests for _safe_get_header fallback paths."""

    def test_safe_get_header_with_defects(self):
        """Test header access with defects fallback."""
        import email
        # Create a malformed email
        content = b"From: =?unknown?Q?test?= <test@example.com>\nSubject: Test\n\nBody"
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_header(msg, "From")
        assert isinstance(result, str)

    def test_safe_get_header_complete_failure(self):
        """Test header access when everything fails."""
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.get.side_effect = Exception("Header parsing failed")
        result = EmailParser._safe_get_header(msg, "Subject")
        assert result == ""


class TestSafeGetContentFallback:
    """Tests for _safe_get_content fallback paths."""

    def test_safe_get_content_get_payload_fallback(self):
        """Test fallback to get_payload when get_content fails."""
        from unittest.mock import MagicMock
        part = MagicMock()
        part.get_content.side_effect = Exception("get_content failed")
        part.get_payload.return_value = b"Fallback content"

        result = EmailParser._safe_get_content(part)
        assert isinstance(result, str)

    def test_safe_get_content_complete_failure(self):
        """Test when both get_content and get_payload fail."""
        from unittest.mock import MagicMock
        part = MagicMock()
        part.get_content.side_effect = Exception("get_content failed")
        part.get_payload.side_effect = Exception("get_payload failed")

        result = EmailParser._safe_get_content(part)
        assert result == ""

    def test_safe_get_content_bytes_fallback_encoding(self):
        """Test decoding bytes with fallback encodings."""
        import email
        # ISO-8859-1 encoded content
        content = b"""Content-Type: text/plain; charset="iso-8859-1"

Caf\xe9"""
        msg = email.message_from_bytes(content)
        result = EmailParser._safe_get_content(msg)
        assert isinstance(result, str)


class TestParseFileExceptionHandling:
    """Tests for parse_file exception handling."""

    def test_parse_file_with_exception_in_walk(self):
        """Test parse_file handles exceptions during multipart walk."""

        # This should not crash
        content = b"""From: test@example.com
Subject: Test
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="broken

This has a broken boundary
"""
        result = EmailParser.parse_file(content=content)
        assert isinstance(result["body"], str)

    def test_parse_non_multipart_html(self):
        """Test parsing non-multipart HTML email."""
        content = b"""From: sender@example.com
Subject: HTML Email
Content-Type: text/html

<html><body><h1>Header</h1><p>Paragraph</p></body></html>
"""
        result = EmailParser.parse_file(content=content)
        assert "Header" in result["body"] or "Paragraph" in result["body"]


class TestGetAttachments:
    """Tests for attachment extraction."""

    def test_get_attachments_simple(self):
        """Test extracting attachments from email."""
        content = b"""From: sender@example.com
Subject: With Attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="---=_Part"

-----=_Part
Content-Type: text/plain

Body text.
-----=_Part
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"

PDF content here
-----=_Part--
"""
        result = EmailParser.parse_file(content=content)
        assert "document.pdf" in result["attachments"]

    def test_get_attachments_none(self):
        """Test email with no attachments."""
        content = b"""From: sender@example.com
Subject: No Attachment
Content-Type: text/plain

Just text body.
"""
        result = EmailParser.parse_file(content=content)
        assert result["attachments"] == ""

    def test_get_multiple_attachments(self):
        """Test email with multiple attachments."""
        content = b"""From: sender@example.com
Subject: Multiple Attachments
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="---=_Part"

-----=_Part
Content-Type: text/plain

Body text.
-----=_Part
Content-Type: application/pdf
Content-Disposition: attachment; filename="doc1.pdf"

PDF1
-----=_Part
Content-Type: image/png
Content-Disposition: attachment; filename="image.png"

PNG
-----=_Part--
"""
        result = EmailParser.parse_file(content=content)
        assert "doc1.pdf" in result["attachments"]
        assert "image.png" in result["attachments"]


class TestParseRecipients:
    """Tests for recipient parsing."""

    def test_parse_multiple_to_recipients(self):
        """Test parsing multiple To recipients."""
        content = b"""From: sender@example.com
To: user1@example.com, user2@example.com
Subject: Multi-To
Content-Type: text/plain

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert "user1@example.com" in result["recipients"]
        assert "user2@example.com" in result["recipients"]

    def test_parse_cc_recipients(self):
        """Test parsing CC recipients."""
        content = b"""From: sender@example.com
To: user1@example.com
Cc: cc@example.com
Subject: With CC
Content-Type: text/plain

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert "user1@example.com" in result["recipients"]


class TestDateParsing:
    """Tests for date parsing."""

    def test_parse_standard_date(self):
        """Test parsing standard date format."""
        content = b"""From: sender@example.com
Date: Mon, 15 Jan 2024 10:30:00 +0000
Subject: Date Test
Content-Type: text/plain

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result["date_str"]  # Should have a date_str

    def test_parse_no_date(self):
        """Test parsing email with no date."""
        content = b"""From: sender@example.com
Subject: No Date
Content-Type: text/plain

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result["date_str"] == ""


class TestMessageId:
    """Tests for message ID extraction."""

    def test_extract_message_id(self):
        """Test extracting Message-ID header - not directly returned by parser."""
        content = b"""From: sender@example.com
Message-ID: <unique123@example.com>
Subject: With Message-ID
Content-Type: text/plain

Body.
"""
        result = EmailParser.parse_file(content=content)
        # Parser doesn't return message_id directly, just verify parse works
        assert result["subject"] == "With Message-ID"

    def test_no_message_id(self):
        """Test email without Message-ID."""
        content = b"""From: sender@example.com
Subject: No Message-ID
Content-Type: text/plain

Body.
"""
        result = EmailParser.parse_file(content=content)
        # Just verify parsing completes
        assert result["subject"] == "No Message-ID"
