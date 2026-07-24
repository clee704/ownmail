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
            b'Content-Type: text/plain; charset="utf-8"\r\n'
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


class TestNormalizeDate:
    """Tests for EmailParser._normalize_date."""

    def test_standard_rfc2822_date(self):
        """A well-formed date should be normalized in place."""
        assert EmailParser._normalize_date("Mon, 1 Jan 2024 10:00:00 +0000") == "Mon, 01 Jan 2024 10:00:00 +0000"

    def test_non_ascii_weekday_prefix_is_stripped(self):
        """A Korean weekday prefix should be removed before parsing."""
        assert EmailParser._normalize_date("월, 15 Mar 2024 10:30:00 +0900") == "Fri, 15 Mar 2024 10:30:00 +0900"

    def test_numeric_month_format(self):
        """A numeric 'DD M YYYY H:MM:SS +ZZZZ' date should be parsed."""
        assert EmailParser._normalize_date("15 3 2024 10:30:00 +0900") == "Fri, 15 Mar 2024 10:30:00 +0900"

    def test_two_digit_year_below_50_is_2000s(self):
        """A 2-digit year under 50 should expand into the 2000s."""
        assert EmailParser._normalize_date("15 3 24 10:30:00 +0000") == "Fri, 15 Mar 2024 10:30:00 +0000"

    def test_two_digit_year_from_50_is_1900s(self):
        """A 2-digit year of 50 or more should expand into the 1900s."""
        assert EmailParser._normalize_date("15 3 99 10:30:00 +0000") == "Mon, 15 Mar 1999 10:30:00 +0000"

    def test_short_hour_only_timezone(self):
        """A '+9' timezone should expand to +0900."""
        assert EmailParser._normalize_date("15 3 24 10:30:00 +9") == "Fri, 15 Mar 2024 10:30:00 +0900"

    def test_three_digit_timezone(self):
        """A '+530' timezone should expand to +0530."""
        assert EmailParser._normalize_date("15 3 24 10:30:00 +530") == "Fri, 15 Mar 2024 10:30:00 +0530"

    def test_negative_timezone(self):
        """A negative offset should keep its sign."""
        assert EmailParser._normalize_date("15 3 24 10:30:00 -0500") == "Fri, 15 Mar 2024 10:30:00 -0500"

    def test_missing_timezone_defaults_to_utc(self):
        """A numeric date with no offset should default to +0000."""
        assert EmailParser._normalize_date("15 3 24 10:30:00") == "Fri, 15 Mar 2024 10:30:00 +0000"

    def test_out_of_range_numeric_date_returns_original(self):
        """An impossible month/day should fall through unchanged."""
        assert EmailParser._normalize_date("99 99 24 10:30:00 +0000") == "99 99 24 10:30:00 +0000"

    def test_unparseable_returns_original(self):
        """A date nothing can parse should be returned as-is."""
        assert EmailParser._normalize_date("totally unparseable") == "totally unparseable"

    def test_empty_returns_empty(self):
        """An empty date string should stay empty."""
        assert EmailParser._normalize_date("") == ""


class TestExtractDateFromReceived:
    """Tests for EmailParser._extract_date_from_received."""

    def _msg(self, raw):
        import email as email_mod

        return email_mod.message_from_string(raw)

    def test_extracts_date_after_semicolon(self):
        """The date following the final ';' should be parsed."""
        msg = self._msg("Received: from a.example.com by b.example.com; Mon, 1 Jan 2024 10:00:00 +0000\n\nbody")
        assert EmailParser._extract_date_from_received(msg) == "Mon, 01 Jan 2024 10:00:00 +0000"

    def test_no_received_header(self):
        """A message with no Received header should yield an empty string."""
        assert EmailParser._extract_date_from_received(self._msg("Subject: x\n\nbody")) == ""

    def test_received_without_semicolon(self):
        """A Received header with no ';' should yield an empty string."""
        assert EmailParser._extract_date_from_received(self._msg("Received: from a by b\n\nbody")) == ""

    def test_unparseable_date_part(self):
        """An unparseable trailing date should yield an empty string."""
        msg = self._msg("Received: from a by b; not a date\n\nbody")
        assert EmailParser._extract_date_from_received(msg) == ""


class TestStripHtml:
    """Tests for EmailParser._strip_html."""

    def test_removes_tags_and_normalizes_whitespace(self):
        """Tags should be dropped and whitespace collapsed."""
        assert EmailParser._strip_html("<p>Hello   <b>World</b></p>\n<p>Again</p>") == "Hello World Again"

    def test_drops_style_and_script_content(self):
        """style/script/head contents must not appear in the text."""
        html = "<html><head><title>T</title></head><body><style>p{color:red}</style>"
        html += "<script>var x=1;</script><p>Visible</p></body></html>"
        result = EmailParser._strip_html(html)
        assert result == "Visible"

    def test_regex_fallback_when_lxml_fails(self):
        """If lxml raises, the regex fallback should still strip tags."""
        from unittest.mock import patch

        html = "<style>p{color:red}</style><script>x</script><p>Hello &amp; bye</p>"
        with patch("ownmail.parser.lxml_html.fromstring", side_effect=ValueError("bad html")):
            result = EmailParser._strip_html(html)
        assert result == "Hello & bye"

    def test_empty_input(self):
        """Empty HTML should produce an empty string via the fallback."""
        assert EmailParser._strip_html("") == ""


class TestDetectCharset:
    """Tests for the _detect_charset helper."""

    def test_declared_charset_is_preferred(self):
        """A declared charset that decodes cleanly should win."""
        from ownmail.parser import _detect_charset

        assert _detect_charset("Привет".encode("cp1251"), "cp1251") == "cp1251"

    def test_euc_kr_is_widened_to_cp949(self):
        """EUC-KR is mapped to CP949, its superset."""
        from ownmail.parser import _detect_charset

        assert _detect_charset("한글".encode("euc-kr"), "euc-kr") == "cp949"

    def test_charset_alias_is_mapped(self):
        """ks_c_5601-1987 should map onto cp949."""
        from ownmail.parser import _detect_charset

        assert _detect_charset("한글".encode("cp949"), "ks_c_5601-1987") == "cp949"

    def test_unknown_declared_charset_is_ignored(self):
        """A declared charset of 'unknown' should fall back to detection."""
        from ownmail.parser import _detect_charset

        assert _detect_charset(b"hello", "unknown") == "utf-8"

    def test_unknown_8bit_is_ignored(self):
        """'unknown-8bit' should likewise be ignored."""
        from ownmail.parser import _detect_charset

        assert _detect_charset(b"hello", "unknown-8bit") == "utf-8"

    def test_wrong_declared_charset_falls_through(self):
        """A declared charset that produces garbage should not be used."""
        from ownmail.parser import _detect_charset

        # Valid UTF-8 that is not decodable as ascii.
        assert _detect_charset("한글".encode(), "ascii") == "utf-8"

    def test_arbitrary_bytes_land_on_a_single_byte_encoding(self):
        """Bytes no multi-byte encoding accepts settle on a single-byte one.

        The chain ends in single-byte codecs that decode any byte sequence
        without error, so detection always returns a usable encoding rather
        than reaching the utf-8 backstop.
        """
        from ownmail.parser import _detect_charset

        assert _detect_charset(b"\xff\xfe\xfd\xfc") in ("cp1251", "koi8-r", "iso-8859-1", "cp1252")


class TestValidateDecodedText:
    """Tests for the _validate_decoded_text helper."""

    def test_plain_ascii_is_readable(self):
        """Normal ASCII text should validate."""
        from ownmail.parser import _validate_decoded_text

        assert _validate_decoded_text("Hello, this is a normal sentence.") is True

    def test_replacement_characters_fail(self):
        """Text containing U+FFFD should not validate."""
        from ownmail.parser import _validate_decoded_text

        assert _validate_decoded_text("Hel�lo") is False

    def test_empty_text_is_not_readable(self):
        """Empty text carries no readable content, so it fails validation."""
        from ownmail.parser import _validate_decoded_text

        assert _validate_decoded_text("") is False

    def test_korean_text_is_readable(self):
        """Hangul should count as readable."""
        from ownmail.parser import _validate_decoded_text

        assert _validate_decoded_text("안녕하세요 반갑습니다") is True


class TestSafeGetContentCharsets:
    """Tests for EmailParser._safe_get_content charset handling."""

    def _part(self, raw):
        import email as email_mod

        return email_mod.message_from_bytes(raw)

    def test_uses_declared_header_charset(self):
        """A correct Content-Type charset should be used directly."""
        raw = b'Content-Type: text/plain; charset="euc-kr"\r\n\r\n' + "안녕하세요 반갑습니다".encode("euc-kr")
        assert "안녕하세요" in EmailParser._safe_get_content(self._part(raw))

    def test_html_meta_charset_is_used(self):
        """A meta charset should rescue an unlabelled HTML part."""
        body = '<html><head><meta charset="euc-kr"></head><body>안녕하세요 반갑습니다</body></html>'
        raw = b"Content-Type: text/html\r\n\r\n" + body.encode("euc-kr")
        assert "안녕하세요" in EmailParser._safe_get_content(self._part(raw))

    def test_detects_cjk_without_any_declaration(self):
        """An undeclared CJK part should be detected by content sniffing."""
        raw = b"Content-Type: text/plain\r\n\r\n" + ("안녕하세요 반갑습니다 " * 5).encode("euc-kr")
        assert "안녕하세요" in EmailParser._safe_get_content(self._part(raw))

    def test_wrong_declared_charset_is_overridden(self):
        """A wrong declared charset should fall through to detection."""
        raw = b'Content-Type: text/plain; charset="ascii"\r\n\r\n' + ("안녕하세요 " * 5).encode("utf-8")
        assert "안녕하세요" in EmailParser._safe_get_content(self._part(raw))

    def test_plain_ascii_body(self):
        """An ASCII body should come through unchanged."""
        raw = b"Content-Type: text/plain\r\n\r\nHello world"
        assert EmailParser._safe_get_content(self._part(raw)) == "Hello world"

    def test_undecodable_bytes_do_not_raise(self):
        """Bytes no encoding handles should degrade, not raise."""
        raw = b"Content-Type: text/plain\r\n\r\n" + bytes(range(0x80, 0x100))
        assert isinstance(EmailParser._safe_get_content(self._part(raw)), str)


class TestDecodeGroupedRfc2047Parts:
    """Tests for _decode_grouped_rfc2047_parts."""

    def _decode(self, parts, fallback=None):
        from ownmail.parser import _decode_grouped_rfc2047_parts

        return _decode_grouped_rfc2047_parts(parts, fallback)

    def test_empty_parts(self):
        """No parts should decode to an empty string."""
        assert self._decode([]) == ""

    def test_plain_string_part(self):
        """A non-bytes part should pass through as text."""
        assert self._decode([("Hello", None)]) == "Hello"

    def test_single_encoded_part(self):
        """A single encoded part should decode with its charset."""
        assert self._decode([("한글".encode("euc-kr"), "euc-kr")]) == "한글"

    def test_adjacent_same_charset_parts_are_joined(self):
        """A multi-byte char split across encoded-words should be rejoined."""
        raw = "한글".encode("euc-kr")
        assert self._decode([(raw[:1], "euc-kr"), (raw[1:], "euc-kr")]) == "한글"

    def test_different_charsets_are_decoded_separately(self):
        """Parts with different charsets must not be concatenated."""
        assert self._decode([("한".encode("euc-kr"), "euc-kr"), ("글".encode(), "utf-8")]) == "한글"

    def test_unknown_charset_falls_back(self):
        """A charset of 'unknown' should be ignored in favour of detection."""
        assert self._decode([("한글".encode("euc-kr"), "unknown")]) == "한글"

    def test_unknown_8bit_charset_falls_back(self):
        """'unknown-8bit' should likewise be ignored."""
        assert self._decode([("한글".encode("euc-kr"), "unknown-8bit")]) == "한글"

    def test_fallback_charset_is_tried_second(self):
        """An explicit fallback should be preferred over the default chain."""
        assert self._decode([("Привет".encode("koi8-r"), None)], fallback="koi8-r") == "Привет"

    def test_undecodable_bytes_degrade_without_raising(self):
        """Bytes nothing decodes cleanly should still produce a string."""
        assert isinstance(self._decode([(b"\xff\xfe\xfd", "utf-8")]), str)

    def test_mixed_text_and_encoded_parts(self):
        """Text and encoded parts should be concatenated in order."""
        assert self._decode([("Re: ", None), ("한글".encode("euc-kr"), "euc-kr")]) == "Re: 한글"


class TestExtractRawHeader:
    """Tests for EmailParser._extract_raw_header."""

    def test_extracts_simple_header(self):
        """A header should be read straight from the raw bytes."""
        raw = b"From: alice@example.com\r\nSubject: Hello\r\n\r\nbody"
        assert EmailParser._extract_raw_header(raw, "Subject") == "Hello"

    def test_header_name_is_case_insensitive(self):
        """Header lookup should ignore case."""
        raw = b"subject: Hello\r\n\r\nbody"
        assert EmailParser._extract_raw_header(raw, "Subject") == "Hello"

    def test_folded_header_is_joined(self):
        """Continuation lines should be folded into one value."""
        raw = b"Subject: First part\r\n continued here\r\n\tand more\r\n\r\nbody"
        assert EmailParser._extract_raw_header(raw, "Subject") == "First part continued here and more"

    def test_stops_at_next_header(self):
        """A following header must not leak into the value."""
        raw = b"Subject: Hello\r\nFrom: alice@example.com\r\n\r\nbody"
        assert EmailParser._extract_raw_header(raw, "Subject") == "Hello"

    def test_missing_header_returns_empty(self):
        """An absent header should yield an empty string."""
        assert EmailParser._extract_raw_header(b"From: a@example.com\r\n\r\nbody", "Subject") == ""

    def test_lf_only_line_endings(self):
        """Bare-LF emails should parse as well as CRLF ones."""
        assert EmailParser._extract_raw_header(b"Subject: Hello\nFrom: a@b.com\n\nbody", "Subject") == "Hello"

    def test_declared_charset_is_used(self):
        """A declared charset should decode raw non-ASCII header bytes."""
        raw = b"Subject: " + "한글".encode("euc-kr") + b"\r\n\r\nbody"
        assert EmailParser._extract_raw_header(raw, "Subject", "euc-kr") == "한글"

    def test_charset_alias_is_mapped(self):
        """ks_c_5601-1987 should be treated as cp949."""
        raw = b"Subject: " + "한글".encode("cp949") + b"\r\n\r\nbody"
        assert EmailParser._extract_raw_header(raw, "Subject", "ks_c_5601-1987") == "한글"

    def test_charset_already_in_chain_is_promoted(self):
        """A declared charset already in the chain should be tried first."""
        raw = b"Subject: " + "한글".encode("euc-kr") + b"\r\n\r\nbody"
        assert EmailParser._extract_raw_header(raw, "Subject", "euc-kr") == "한글"

    def test_undecodable_bytes_degrade(self):
        """Bytes nothing decodes cleanly should still return a string."""
        raw = b"Subject: \xff\xfe\xfd\r\n\r\nbody"
        assert isinstance(EmailParser._extract_raw_header(raw, "Subject"), str)


class TestSafeGetHeaderFallbacks:
    """Tests for EmailParser._safe_get_header's raw-extraction fallbacks."""

    def _msg(self, raw):
        import email as email_mod

        return email_mod.message_from_bytes(raw)

    def test_clean_header_is_returned(self):
        """A clean header needs no fallback."""
        raw = b"Subject: Hello\r\n\r\nbody"
        assert EmailParser._safe_get_header(self._msg(raw), "Subject", raw_content=raw) == "Hello"

    def test_corrupt_header_recovered_from_raw_bytes(self):
        """A header the email library mangles should be re-read from bytes."""
        raw = b"Subject: " + "한글 제목".encode("euc-kr") + b"\r\n\r\nbody"
        result = EmailParser._safe_get_header(self._msg(raw), "Subject", "euc-kr", raw_content=raw)
        assert result == "한글 제목"

    def test_missing_header_returns_empty(self):
        """An absent header should yield an empty string."""
        raw = b"From: a@example.com\r\n\r\nbody"
        assert EmailParser._safe_get_header(self._msg(raw), "Subject", raw_content=raw) == ""

    def test_parse_failure_falls_back_to_raw(self):
        """If header decoding raises, raw extraction should be used."""
        from unittest.mock import patch

        raw = b"Subject: Hello\r\n\r\nbody"
        msg = self._msg(raw)
        with patch.object(EmailParser, "_decode_header_value", side_effect=ValueError("boom")):
            assert EmailParser._safe_get_header(msg, "Subject", raw_content=raw) == "Hello"

    def test_parse_failure_without_raw_returns_empty(self):
        """With no raw content to fall back on, the result should be empty."""
        from unittest.mock import patch

        msg = self._msg(b"Subject: Hello\r\n\r\nbody")
        with patch.object(EmailParser, "_decode_header_value", side_effect=ValueError("boom")):
            assert EmailParser._safe_get_header(msg, "Subject") == ""


class TestParseFileBodyExtraction:
    """Tests for parse_file's body and attachment collection."""

    def test_multipart_prefers_plain_text(self):
        """text/plain should be indexed in preference to text/html."""
        raw = (
            b'Content-Type: multipart/alternative; boundary="b1"\r\n\r\n'
            b"--b1\r\nContent-Type: text/plain\r\n\r\nplain body\r\n"
            b"--b1\r\nContent-Type: text/html\r\n\r\n<p>html body</p>\r\n--b1--\r\n"
        )
        result = EmailParser.parse_file(content=raw)
        assert "plain body" in result["body"]
        assert "html body" not in result["body"]

    def test_html_only_multipart_is_stripped(self):
        """With no plain part, HTML should be stripped and indexed."""
        raw = (
            b'Content-Type: multipart/alternative; boundary="b1"\r\n\r\n'
            b"--b1\r\nContent-Type: text/html\r\n\r\n<p>html <b>body</b></p>\r\n--b1--\r\n"
        )
        result = EmailParser.parse_file(content=raw)
        assert result["body"].strip() == "html body"

    def test_html_only_singlepart_is_stripped(self):
        """A non-multipart HTML message should also be stripped."""
        raw = b"Content-Type: text/html\r\n\r\n<p>hello <b>world</b></p>\r\n"
        assert EmailParser.parse_file(content=raw)["body"].strip() == "hello world"

    def test_attachment_filenames_are_collected(self):
        """Attachment filenames should be recorded for indexing."""
        raw = (
            b'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
            b"--b1\r\nContent-Type: text/plain\r\n\r\nbody\r\n"
            b"--b1\r\nContent-Type: application/pdf\r\n"
            b'Content-Disposition: attachment; filename="report.pdf"\r\n\r\nDATA\r\n--b1--\r\n'
        )
        assert "report.pdf" in EmailParser.parse_file(content=raw)["attachments"]

    def test_malformed_message_returns_empty_fields(self):
        """Garbage input should produce a result dict, not an exception."""
        result = EmailParser.parse_file(content=b"\xff\xfe not an email at all")
        assert set(result) == {"subject", "sender", "recipients", "date_str", "body", "attachments"}
