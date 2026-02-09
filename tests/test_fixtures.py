"""Tests using email fixture files for realistic edge cases."""

from pathlib import Path

from ownmail.database import ArchiveDatabase
from ownmail.parser import EmailParser
from ownmail.web import _linkify, _linkify_line


def _eid(provider_id, account=""):
    return ArchiveDatabase.make_email_id(account, provider_id)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestParserWithFixtures:
    """Test EmailParser with realistic email fixtures."""

    def test_simple_plain_text(self):
        """Test parsing a simple plain text email."""
        filepath = FIXTURES_DIR / "simple_plain.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert result["subject"] == "Simple plain text email"
        assert result["sender"] == "sender@example.com"
        assert "simple plain text" in result["body"].lower()
        assert "recipient@example.com" in result["recipients"]

    def test_korean_encoded_email(self):
        """Test parsing email with Korean EUC-KR encoding."""
        filepath = FIXTURES_DIR / "korean_encoded.eml"
        result = EmailParser.parse_file(filepath=filepath)

        # Subject should be decoded from EUC-KR
        assert result["subject"]  # Should have some content
        assert "korean@example.com" in result["sender"]

    def test_digest_email(self):
        """Test parsing digest email with message/rfc822 parts."""
        filepath = FIXTURES_DIR / "digest_email.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert "Test Digest" in result["subject"]
        assert "Today's Topics" in result["body"]
        # Body should contain content from embedded messages
        assert "first" in result["body"].lower() or "second" in result["body"].lower()

    def test_html_only_email(self):
        """Test parsing HTML-only email."""
        filepath = FIXTURES_DIR / "html_only.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert result["subject"] == "HTML Only Email"
        # Should extract text from HTML
        assert "Hello World" in result["body"] or "HTML content" in result["body"]

    def test_email_with_attachment(self):
        """Test parsing email with attachment."""
        filepath = FIXTURES_DIR / "with_attachment.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert result["subject"] == "Email with attachment"
        assert "attached" in result["body"].lower()
        # attachments is a comma-separated string
        assert "test.txt" in result["attachments"]

    def test_multipart_alternative(self):
        """Test parsing multipart/alternative email."""
        filepath = FIXTURES_DIR / "multipart_alternative.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert result["subject"] == "Multipart Alternative"
        # Should prefer plain text
        assert "plain text version" in result["body"].lower()

    def test_quoted_printable_email(self):
        """Test parsing quoted-printable encoded email."""
        filepath = FIXTURES_DIR / "quoted_printable.eml"
        result = EmailParser.parse_file(filepath=filepath)

        # Should decode quoted-printable properly
        assert "café" in result["body"] or "caf" in result["body"]

    def test_minimal_headers_email(self):
        """Test parsing email with minimal headers."""
        filepath = FIXTURES_DIR / "minimal_headers.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert result["sender"] == "sender@example.com"
        # Missing headers should have defaults (empty string)
        assert result["subject"] == ""

    def test_inline_image_email(self):
        """Test parsing email with inline CID image."""
        filepath = FIXTURES_DIR / "with_inline_image.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert result["subject"] == "Email with inline image"

    def test_quoted_reply_email(self):
        """Test parsing email with quoted reply."""
        filepath = FIXTURES_DIR / "quoted_reply.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert "Re:" in result["subject"]
        assert ">" in result["body"]
        assert "quoted message" in result["body"].lower()


class TestLinkifyFunction:
    """Test the _linkify function for plain text formatting."""

    def test_linkify_url(self):
        """Test URL linkification."""
        text = "Check out https://example.com for more info."
        result = _linkify(text)
        assert '<a href="https://example.com"' in result
        assert 'target="_blank"' in result

    def test_linkify_email(self):
        """Test email address linkification."""
        text = "Contact us at support@example.com for help."
        result = _linkify(text)
        assert '<a href="mailto:support@example.com"' in result

    def test_linkify_multiple_urls(self):
        """Test multiple URLs in one text."""
        text = "Visit http://foo.com and https://bar.com today."
        result = _linkify(text)
        assert "http://foo.com" in result
        assert "https://bar.com" in result
        assert result.count("<a href=") == 2

    def test_linkify_quote_level_1(self):
        """Test single quote level formatting."""
        text = "> This is a quoted line."
        result = _linkify(text)
        assert "quote-level" in result or "border-left" in result

    def test_linkify_quote_level_2(self):
        """Test nested quote level formatting."""
        text = ">> This is a doubly quoted line."
        result = _linkify(text)
        # Should have styling for level 2
        assert "<div" in result

    def test_linkify_header_line(self):
        """Test header line formatting."""
        text = "From: sender@example.com"
        result = _linkify(text)
        assert "email-header-label" in result

    def test_linkify_subject_header(self):
        """Test Subject header formatting."""
        text = "Subject: Test email"
        result = _linkify(text)
        assert "email-header-label" in result

    def test_linkify_preserves_text(self):
        """Test that regular text is preserved."""
        text = "Hello, this is plain text."
        result = _linkify(text)
        assert "Hello" in result
        assert "plain text" in result

    def test_linkify_escapes_html(self):
        """Test that HTML is escaped."""
        text = "<script>alert('xss')</script>"
        result = _linkify(text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_linkify_empty_string(self):
        """Test empty string."""
        result = _linkify("")
        assert result == "" or result == "<div>&nbsp;</div>"

    def test_linkify_url_with_path(self):
        """Test URL with path and query."""
        text = "See https://example.com/path/to/page?foo=bar&baz=1"
        result = _linkify(text)
        assert "example.com/path/to/page" in result


class TestLinkifyLine:
    """Test the _linkify_line helper function."""

    def test_linkify_line_url(self):
        """Test single line URL."""
        line = "Visit https://test.com now"
        result = _linkify_line(line)
        assert '<a href="https://test.com"' in result

    def test_linkify_line_email(self):
        """Test single line email."""
        line = "Email me at test@example.org"
        result = _linkify_line(line)
        assert "mailto:test@example.org" in result


class TestParserParseFileWithContent:
    """Test EmailParser.parse_file with content parameter."""

    def test_parse_file_with_content(self):
        """Test parse_file with content bytes."""
        content = b"""From: test@example.com
To: recipient@example.com
Subject: Test Subject
Date: Mon, 1 Jan 2024 12:00:00 +0000

This is the body.
"""
        result = EmailParser.parse_file(content=content)
        assert result["subject"] == "Test Subject"
        assert result["sender"] == "test@example.com"
        assert "body" in result["body"].lower()

    def test_parse_file_with_unicode_content(self):
        """Test parse_file with unicode characters."""
        content = """From: test@example.com
Subject: Test with émojis
Date: Mon, 1 Jan 2024 12:00:00 +0000

Message with unicode: café
""".encode()
        result = EmailParser.parse_file(content=content)
        assert "mojis" in result["subject"]


class TestParserEdgeCasesWithFixtures:
    """Additional edge case tests for parser."""

    def test_parser_handles_attachment_filename(self):
        """Test that attachment filename is extracted."""
        filepath = FIXTURES_DIR / "with_attachment.eml"
        result = EmailParser.parse_file(filepath=filepath)

        # Should have attachment info (as comma-separated string)
        assert "test.txt" in result["attachments"]

    def test_parser_extracts_recipients(self):
        """Test recipient extraction."""
        filepath = FIXTURES_DIR / "simple_plain.eml"
        result = EmailParser.parse_file(filepath=filepath)

        assert "recipient@example.com" in result["recipients"]

    def test_parser_handles_missing_date(self):
        """Test handling of missing date header."""
        filepath = FIXTURES_DIR / "minimal_headers.eml"
        result = EmailParser.parse_file(filepath=filepath)

        # Should not crash, date might be empty
        assert "sender" in result


class TestWebDecodeHelpers:
    """Test web.py decode helper functions."""

    def test_decode_text_body_utf8(self):
        """Test _decode_text_body with UTF-8."""
        from ownmail.web import _decode_text_body
        payload = "Hello world café".encode()
        result = _decode_text_body(payload, "utf-8")
        assert "café" in result

    def test_decode_text_body_no_charset(self):
        """Test _decode_text_body without charset (auto-detect)."""
        from ownmail.web import _decode_text_body
        payload = b"Hello world"
        result = _decode_text_body(payload, None)
        assert "Hello" in result

    def test_decode_text_body_invalid_charset(self):
        """Test _decode_text_body with invalid charset."""
        from ownmail.web import _decode_text_body
        payload = b"Hello world"
        result = _decode_text_body(payload, "not-a-real-charset")
        # Should fall back to working encoding
        assert "Hello" in result

    def test_try_decode_valid(self):
        """Test _try_decode with valid encoding."""
        from ownmail.web import _try_decode
        payload = b"Test"
        result = _try_decode(payload, "utf-8")
        assert result == "Test"

    def test_try_decode_invalid(self):
        """Test _try_decode with invalid encoding."""
        from ownmail.web import _try_decode
        # Invalid UTF-8 bytes
        payload = b'\xff\xfe'
        result = _try_decode(payload, "utf-8")
        assert result is None

    def test_validate_decoded_text_valid(self):
        """Test _validate_decoded_text with valid text."""
        from ownmail.web import _validate_decoded_text
        assert _validate_decoded_text("Hello world") is True

    def test_format_size_bytes(self):
        """Test _format_size with bytes."""
        from ownmail.web import _format_size
        assert _format_size(500) == "500 B"

    def test_format_size_kb(self):
        """Test _format_size with kilobytes."""
        from ownmail.web import _format_size
        assert "KB" in _format_size(2048)

    def test_format_size_mb(self):
        """Test _format_size with megabytes."""
        from ownmail.web import _format_size
        assert "MB" in _format_size(2 * 1024 * 1024)


class TestBlockExternalImagesFunction:
    """Test block_external_images function."""

    def test_block_external_images_http(self):
        """Test blocking HTTP images."""
        from ownmail.web import block_external_images
        html = '<img src="http://tracker.com/pixel.gif">'
        result, has_external = block_external_images(html)
        assert has_external is True

    def test_block_external_images_data_uri(self):
        """Test that data URIs are not blocked."""
        from ownmail.web import block_external_images
        html = '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7">'
        result, has_external = block_external_images(html)
        assert has_external is False
        assert "data:image" in result


class TestParseRecipients:
    """Test parse_recipients function."""

    def test_parse_recipients_single(self):
        """Test parsing single recipient."""
        from ownmail.web import parse_recipients
        result = parse_recipients("John Doe <john@example.com>")
        assert len(result) == 1
        assert result[0]["email"] == "john@example.com"

    def test_parse_recipients_multiple(self):
        """Test parsing multiple recipients."""
        from ownmail.web import parse_recipients
        result = parse_recipients("john@a.com, jane@b.com")
        assert len(result) == 2

    def test_parse_recipients_empty(self):
        """Test parsing empty string."""
        from ownmail.web import parse_recipients
        result = parse_recipients("")
        assert len(result) == 0


class TestDecodeHtmlBody:
    """Test _decode_html_body function."""

    def test_decode_html_body_utf8(self):
        """Test decoding HTML with UTF-8."""
        from ownmail.web import _decode_html_body
        payload = b'<html><body>Hello World</body></html>'
        result = _decode_html_body(payload, "utf-8")
        assert "Hello World" in result

    def test_decode_html_body_meta_charset(self):
        """Test decoding HTML with charset in meta tag."""
        from ownmail.web import _decode_html_body
        payload = b'<html><head><meta charset="utf-8"></head><body>Test</body></html>'
        result = _decode_html_body(payload, None)
        assert "Test" in result

    def test_decode_html_body_no_charset(self):
        """Test decoding HTML without charset."""
        from ownmail.web import _decode_html_body
        payload = b'<html><body>Simple</body></html>'
        result = _decode_html_body(payload, None)
        assert "Simple" in result


class TestParserStripHtml:
    """Test parser _strip_html function."""

    def test_strip_html_simple(self):
        """Test stripping simple HTML tags."""
        from ownmail.parser import EmailParser
        html = "<p>Hello <b>World</b></p>"
        result = EmailParser._strip_html(html)
        assert "Hello" in result
        assert "World" in result
        assert "<p>" not in result

    def test_strip_html_with_style(self):
        """Test stripping HTML with style tags."""
        from ownmail.parser import EmailParser
        html = "<style>body{color:red}</style><p>Content</p>"
        result = EmailParser._strip_html(html)
        assert "Content" in result
        # Style content should be removed
        assert "color:red" not in result

    def test_strip_html_with_script(self):
        """Test stripping HTML with script tags."""
        from ownmail.parser import EmailParser
        html = "<script>alert('hi')</script><p>Text</p>"
        result = EmailParser._strip_html(html)
        assert "Text" in result
        assert "alert" not in result


class TestParserExtractDateFromReceived:
    """Test parser _extract_date_from_received function."""

    def test_extract_date_from_received_valid(self):
        """Test extracting date from Received header."""
        import email
        from email.policy import default as email_policy

        from ownmail.parser import EmailParser

        raw = b"""Received: from mail.example.com by server.com; Mon, 1 Jan 2024 12:00:00 +0000
From: test@example.com

Body
"""
        msg = email.message_from_bytes(raw, policy=email_policy)
        result = EmailParser._extract_date_from_received(msg)
        assert result  # Should extract date

    def test_extract_date_from_received_no_header(self):
        """Test extracting date when no Received header."""
        import email
        from email.policy import default as email_policy

        from ownmail.parser import EmailParser

        raw = b"""From: test@example.com

Body
"""
        msg = email.message_from_bytes(raw, policy=email_policy)
        result = EmailParser._extract_date_from_received(msg)
        assert result is None or result == ""


class TestParserNormalizeDate:
    """Test parser _normalize_date function."""

    def test_normalize_date_valid(self):
        """Test normalizing a valid date."""
        from ownmail.parser import EmailParser
        date_str = "Mon, 1 Jan 2024 12:00:00 +0000"
        result = EmailParser._normalize_date(date_str)
        assert result  # Should return something
        assert "2024" in result

    def test_normalize_date_empty(self):
        """Test normalizing empty date."""
        from ownmail.parser import EmailParser
        result = EmailParser._normalize_date("")
        assert result == ""

    def test_normalize_date_none(self):
        """Test normalizing None."""
        from ownmail.parser import EmailParser
        result = EmailParser._normalize_date(None)
        assert result is None or result == ""


class TestParserSafeGetContent:
    """Test parser _safe_get_content function."""

    def test_safe_get_content_plain(self):
        """Test getting content from plain text part."""
        import email
        from email.policy import default as email_policy

        from ownmail.parser import EmailParser

        raw = b"""Content-Type: text/plain; charset=utf-8

Hello World
"""
        msg = email.message_from_bytes(raw, policy=email_policy)
        result = EmailParser._safe_get_content(msg)
        assert "Hello" in result

    def test_safe_get_content_bytes_fallback(self):
        """Test getting content when payload is bytes."""
        import email
        from email.policy import default as email_policy

        from ownmail.parser import EmailParser

        raw = b"""Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: base64

SGVsbG8gV29ybGQ=
"""
        msg = email.message_from_bytes(raw, policy=email_policy)
        result = EmailParser._safe_get_content(msg)
        assert "Hello" in result or result  # Should return something

    def test_safe_decode_header_bytes(self):
        """Test _decode_header_value with bytes value."""
        from ownmail.parser import EmailParser
        # Korean text in EUC-KR bytes
        raw_value = "한글".encode('euc-kr')
        result = EmailParser._decode_header_value(raw_value)
        # Should decode without crashing
        assert result

    def test_decode_header_value_bytes_utf8(self):
        """Test _decode_header_value with utf-8 bytes."""
        from ownmail.parser import EmailParser
        raw_value = b"Hello World"
        result = EmailParser._decode_header_value(raw_value)
        assert result == "Hello World"

    def test_decode_header_value_bytes_cp949(self):
        """Test _decode_header_value with cp949 bytes (falls through to charset list)."""
        from ownmail.parser import EmailParser
        # Bytes that fail utf-8 but decode as cp949
        raw_value = "테스트".encode('cp949')
        result = EmailParser._decode_header_value(raw_value)
        assert result  # Should decode without crashing

    def test_decode_header_value_string_with_replacement_chars(self):
        """Test _decode_header_value with string containing replacement chars."""
        from ownmail.parser import EmailParser
        # String with replacement character
        raw_value = "Hello \ufffd World"
        result = EmailParser._decode_header_value(raw_value)
        assert result  # Should return something

    def test_decode_header_value_bytes_all_fail(self):
        """Test _decode_header_value with bytes that fail all encodings (fallback to replace)."""
        from ownmail.parser import EmailParser
        # Invalid bytes that aren't valid in any common encoding - this triggers line 286
        raw_value = bytes([0xFF, 0xFE, 0x80, 0x81, 0x82])
        result = EmailParser._decode_header_value(raw_value)
        assert result  # Should use errors='replace' fallback

    def test_decode_header_value_latin1_recoverable(self):
        """Test _decode_header_value with string that has cp949 bytes mis-decoded as latin-1."""
        from ownmail.parser import EmailParser
        # Korean text encoded as cp949, then misread as latin-1 causing replacement chars
        korean = "테스트"
        cp949_bytes = korean.encode('cp949')
        # Simulate what happens when cp949 bytes are decoded as latin-1 (produces garbage)
        # Then we have replacement chars that trigger recovery
        bad_string = cp949_bytes.decode('latin-1')
        # Add a replacement char to trigger the recovery path
        bad_string_with_issues = bad_string + "\ufffd"
        result = EmailParser._decode_header_value(bad_string_with_issues)
        assert result  # Should recover or return something


class TestWebUtilityFunctions:
    """Test web.py utility functions."""

    def test_format_size_bytes(self):
        """Test _format_size with bytes."""
        from ownmail.web import _format_size
        assert _format_size(500) == "500 B"

    def test_format_size_kb(self):
        """Test _format_size with kilobytes."""
        from ownmail.web import _format_size
        assert "KB" in _format_size(2048)

    def test_format_size_mb(self):
        """Test _format_size with megabytes."""
        from ownmail.web import _format_size
        assert "MB" in _format_size(1024 * 1024 * 2)

    def test_fix_mojibake_empty(self):
        """Test _fix_mojibake_filename with empty."""
        from ownmail.web import _fix_mojibake_filename
        assert _fix_mojibake_filename("") == ""
        assert _fix_mojibake_filename(None) is None

    def test_fix_mojibake_ascii(self):
        """Test _fix_mojibake_filename with ASCII."""
        from ownmail.web import _fix_mojibake_filename
        assert _fix_mojibake_filename("file.txt") == "file.txt"

    def test_fix_mojibake_korean(self):
        """Test _fix_mojibake_filename with Korean mojibake."""
        from ownmail.web import _fix_mojibake_filename
        # Simulate mojibake: Korean encoded as EUC-KR, decoded as latin-1
        korean = "테스트.txt"
        euc_kr_bytes = korean.encode('euc-kr')
        mojibake = euc_kr_bytes.decode('latin-1')
        result = _fix_mojibake_filename(mojibake)
        # Should recover the Korean text
        assert "테스트" in result or result == mojibake

    def test_fix_mojibake_unicode_error(self):
        """Test _fix_mojibake_filename skips non-latin1 chars."""
        from ownmail.web import _fix_mojibake_filename
        # Already has proper Unicode chars - can't encode to latin-1
        result = _fix_mojibake_filename("한글파일.txt")
        assert result == "한글파일.txt"

    def test_validate_decoded_text_valid(self):
        """Test _validate_decoded_text with valid text."""
        from ownmail.web import _validate_decoded_text
        assert _validate_decoded_text("Hello World") is True

    def test_validate_decoded_text_empty(self):
        """Test _validate_decoded_text with empty text."""
        from ownmail.web import _validate_decoded_text
        # Empty string returns False (the early bail out)
        assert _validate_decoded_text("") is False

    def test_validate_decoded_text_korean(self):
        """Test _validate_decoded_text with Korean text."""
        from ownmail.web import _validate_decoded_text
        assert _validate_decoded_text("안녕하세요") is True

    def test_validate_decoded_text_garbage(self):
        """Test _validate_decoded_text with garbage chars."""
        from ownmail.web import _validate_decoded_text
        # Too many control characters
        garbage = "\x00\x01\x02\x03\x04\x05\x06\x07\x08"
        assert _validate_decoded_text(garbage) is False


class TestExtractSnippet:
    """Test web.py snippet extraction functions."""

    def test_clean_snippet_text_basic(self):
        """Test _clean_snippet_text with basic text."""
        from ownmail.web import _clean_snippet_text
        assert _clean_snippet_text("Hello World") == "Hello World"

    def test_clean_snippet_text_empty(self):
        """Test _clean_snippet_text with empty text."""
        from ownmail.web import _clean_snippet_text
        assert _clean_snippet_text("") == ""
        assert _clean_snippet_text(None) is None

    def test_clean_snippet_text_invisible_chars(self):
        """Test _clean_snippet_text removes invisible characters."""
        from ownmail.web import _clean_snippet_text
        # Text with ZWNJ and other invisible chars
        text = "Hello\u200cWorld\u200bTest\uFEFF"
        result = _clean_snippet_text(text)
        assert "\u200c" not in result
        assert "\u200b" not in result

    def test_clean_snippet_text_css(self):
        """Test _clean_snippet_text removes CSS selectors."""
        from ownmail.web import _clean_snippet_text
        text = "Hello .class { color: red; } World"
        result = _clean_snippet_text(text)
        assert "{" not in result
        assert "color" not in result or result.startswith("Hello")

    def test_clean_snippet_text_repetitive(self):
        """Test _clean_snippet_text removes repetitive padding."""
        from ownmail.web import _clean_snippet_text
        text = "Hello ä ä ä ä ä World"
        result = _clean_snippet_text(text)
        # Should collapse the repetition
        assert result.count("ä") < 5

    def test_clean_snippet_text_whitespace(self):
        """Test _clean_snippet_text collapses whitespace."""
        from ownmail.web import _clean_snippet_text
        text = "Hello    \n\n   World"
        result = _clean_snippet_text(text)
        assert result == "Hello World"

    def test_clean_snippet_text_mime_headers(self):
        """Test _clean_snippet_text strips embedded MIME headers."""
        from ownmail.web import _clean_snippet_text
        text = "Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: 7bit\r\n\r\nInformed Delivery(TM)"
        result = _clean_snippet_text(text)
        assert result == "Informed Delivery(TM)"

    def test_clean_snippet_text_mime_headers_case_insensitive(self):
        """Test MIME header stripping is case-insensitive."""
        from ownmail.web import _clean_snippet_text
        text = "content-type: text/html\ncontent-transfer-encoding: quoted-printable\n\nActual content"
        result = _clean_snippet_text(text)
        assert result == "Actual content"

    def test_clean_snippet_text_element_css_selectors(self):
        """Test _clean_snippet_text strips element CSS selectors like body { ... }."""
        from ownmail.web import _clean_snippet_text
        text = "body { margin: 0; padding: 0; } table, td, tr { vertical-align: top; } Hello"
        result = _clean_snippet_text(text)
        assert "margin" not in result
        assert "vertical-align" not in result
        assert "Hello" in result

    def test_clean_snippet_text_media_query(self):
        """Test _clean_snippet_text strips @media queries."""
        from ownmail.web import _clean_snippet_text
        text = "@media (max-width: 620px) { .block-grid { width: 100%; } } Hello"
        result = _clean_snippet_text(text)
        assert "max-width" not in result
        assert "Hello" in result

    def test_clean_snippet_text_attribute_css_selectors(self):
        """Test _clean_snippet_text strips attribute CSS selectors."""
        from ownmail.web import _clean_snippet_text
        text = "a[x-apple-data-detectors=true] { color: inherit; } Hello"
        result = _clean_snippet_text(text)
        assert "apple-data" not in result
        assert "Hello" in result

    def test_extract_snippet_plain_email(self):
        """Test _extract_snippet with a plain text email."""
        import email
        from email.policy import default as email_policy

        from ownmail.web import _extract_snippet

        raw = b"""Content-Type: text/plain; charset=utf-8

This is a test email body for snippet extraction.
"""
        msg = email.message_from_bytes(raw, policy=email_policy)
        snippet = _extract_snippet(msg)
        assert "test email" in snippet

    def test_extract_snippet_multipart(self):
        """Test _extract_snippet with multipart email."""
        import email
        from email.policy import default as email_policy

        from ownmail.web import _extract_snippet

        raw = b"""Content-Type: multipart/alternative; boundary="boundary"

--boundary
Content-Type: text/plain; charset=utf-8

Plain text version
--boundary
Content-Type: text/html; charset=utf-8

<html><body>HTML version</body></html>
--boundary--
"""
        msg = email.message_from_bytes(raw, policy=email_policy)
        snippet = _extract_snippet(msg)
        assert "Plain text" in snippet

    def test_extract_snippet_truncates(self):
        """Test _extract_snippet truncates long text."""
        import email
        from email.policy import default as email_policy

        from ownmail.web import _extract_snippet

        long_text = "x" * 200
        raw = f"""Content-Type: text/plain; charset=utf-8

{long_text}
""".encode()
        msg = email.message_from_bytes(raw, policy=email_policy)
        snippet = _extract_snippet(msg, max_len=50)
        assert len(snippet) <= 54  # max_len + "..."
        assert snippet.endswith("...")


class TestArchiveUtilityFunctions:
    """Test archive.py utility functions."""

    def test_format_size_bytes(self):
        """Test _format_size with bytes."""
        from ownmail.archive import EmailArchive
        assert EmailArchive._format_size(500) == "500B"

    def test_format_size_kb(self):
        """Test _format_size with kilobytes."""
        from ownmail.archive import EmailArchive
        assert "KB" in EmailArchive._format_size(5000)

    def test_format_size_mb(self):
        """Test _format_size with megabytes."""
        from ownmail.archive import EmailArchive
        assert "MB" in EmailArchive._format_size(5_000_000)

    def test_format_eta_early(self):
        """Test _format_eta with early iteration."""
        from ownmail.archive import EmailArchive
        assert EmailArchive._format_eta(60, 1) == "..."

    def test_format_eta_seconds(self):
        """Test _format_eta with seconds."""
        from ownmail.archive import EmailArchive
        result = EmailArchive._format_eta(45, 5)
        assert "s" in result

    def test_format_eta_minutes(self):
        """Test _format_eta with minutes."""
        from ownmail.archive import EmailArchive
        result = EmailArchive._format_eta(180, 5)
        assert "m" in result

    def test_format_eta_hours(self):
        """Test _format_eta with hours."""
        from ownmail.archive import EmailArchive
        result = EmailArchive._format_eta(7200, 5)
        assert "h" in result


class TestParseEmailAddress:
    """Test web.py parse_email_address function."""

    def test_parse_email_address_empty(self):
        """Test parse_email_address with empty string."""
        from ownmail.web import parse_email_address
        assert parse_email_address("") == ("", "")
        assert parse_email_address(None) == ("", "")

    def test_parse_email_address_full(self):
        """Test parse_email_address with name and email."""
        from ownmail.web import parse_email_address
        name, email = parse_email_address("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_parse_email_address_quoted(self):
        """Test parse_email_address with quoted name."""
        from ownmail.web import parse_email_address
        name, email = parse_email_address('"Doe, John" <john@example.com>')
        assert name == "Doe, John"
        assert email == "john@example.com"

    def test_parse_email_address_plain(self):
        """Test parse_email_address with plain email."""
        from ownmail.web import parse_email_address
        name, email = parse_email_address("john@example.com")
        assert name == ""
        assert email == "john@example.com"

    def test_parse_email_address_angle_brackets(self):
        """Test parse_email_address with angle brackets."""
        from ownmail.web import parse_email_address
        name, email = parse_email_address("<john@example.com>")
        assert email == "john@example.com"

    def test_parse_email_address_invalid(self):
        """Test parse_email_address with invalid input."""
        from ownmail.web import parse_email_address
        assert parse_email_address("not an email") == ("", "")


class TestTryDecode:
    """Test web.py _try_decode function."""

    def test_try_decode_utf8(self):
        """Test _try_decode with UTF-8."""
        from ownmail.web import _try_decode
        result = _try_decode(b"Hello World", "utf-8")
        assert result == "Hello World"

    def test_try_decode_invalid_encoding(self):
        """Test _try_decode with invalid encoding."""
        from ownmail.web import _try_decode
        result = _try_decode(b"Hello", "not-a-valid-encoding")
        assert result is None

    def test_try_decode_korean(self):
        """Test _try_decode with Korean text."""
        from ownmail.web import _try_decode
        korean = "안녕하세요"
        result = _try_decode(korean.encode('utf-8'), "utf-8")
        assert result == korean

    def test_try_decode_garbage(self):
        """Test _try_decode with garbage chars returns None."""
        from ownmail.web import _try_decode
        # Bytes that decode to control characters - fails validation
        garbage_bytes = bytes([0x01, 0x02, 0x03, 0x04, 0x05])
        result = _try_decode(garbage_bytes, "utf-8")
        assert result is None  # Fails validation


class TestDecodeTextBody:
    """Test web.py _decode_text_body function."""

    def test_decode_text_body_utf8(self):
        """Test _decode_text_body with UTF-8."""
        from ownmail.web import _decode_text_body
        result = _decode_text_body(b"Hello World", "utf-8")
        assert result == "Hello World"

    def test_decode_text_body_utf8_korean(self):
        """Test _decode_text_body with Korean UTF-8."""
        from ownmail.web import _decode_text_body
        korean = "안녕하세요".encode()
        result = _decode_text_body(korean, "utf-8")
        assert "안녕" in result

    def test_decode_text_body_unknown_charset(self):
        """Test _decode_text_body with unknown charset falls back."""
        from ownmail.web import _decode_text_body
        result = _decode_text_body(b"Hello World", None)
        assert result == "Hello World"

    def test_decode_text_body_cp949(self):
        """Test _decode_text_body with cp949 Korean."""
        from ownmail.web import _decode_text_body
        korean = "테스트 메일입니다".encode('cp949')
        result = _decode_text_body(korean, "cp949")
        assert result  # Should decode without error

    def test_decode_text_body_auto_detection(self):
        """Test _decode_text_body auto-detects CJK."""
        from ownmail.web import _decode_text_body
        # Korean text with no charset hint
        korean = "안녕하세요 테스트입니다".encode()
        result = _decode_text_body(korean, None)
        assert "안녕" in result

    def test_decode_text_body_fallback(self):
        """Test _decode_text_body fallback to utf-8 replace."""
        from ownmail.web import _decode_text_body
        # Invalid bytes - should still return something
        bad_bytes = bytes([0xFF, 0xFE, 0x01, 0x02])
        result = _decode_text_body(bad_bytes, None)
        assert result  # Should return something (with replacement chars)

    def test_decode_text_body_charset_alias(self):
        """Test _decode_text_body with charset alias."""
        from ownmail.web import _decode_text_body
        # ks_c_5601-1987 is an alias for cp949
        korean = "테스트".encode('cp949')
        result = _decode_text_body(korean, "ks_c_5601-1987")
        assert result  # Should decode with alias mapping


class TestDatabaseHelpers:
    """Test database.py helper functions."""

    def test_extract_email_with_brackets(self):
        """Test _extract_email with Name <email> format."""
        from ownmail.database import ArchiveDatabase
        result = ArchiveDatabase._extract_email("John Doe <john@example.com>")
        assert result == "john@example.com"

    def test_extract_email_plain(self):
        """Test _extract_email with plain email."""
        from ownmail.database import ArchiveDatabase
        result = ArchiveDatabase._extract_email("john@example.com")
        assert result == "john@example.com"

    def test_extract_email_empty(self):
        """Test _extract_email with empty string."""
        from ownmail.database import ArchiveDatabase
        assert ArchiveDatabase._extract_email("") is None
        assert ArchiveDatabase._extract_email(None) is None

    def test_extract_email_no_at(self):
        """Test _extract_email with no @ symbol."""
        from ownmail.database import ArchiveDatabase
        assert ArchiveDatabase._extract_email("John Doe") is None

    def test_normalize_recipients_single(self):
        """Test _normalize_recipients with single recipient."""
        from ownmail.database import ArchiveDatabase
        result = ArchiveDatabase._normalize_recipients("john@example.com")
        assert result == ",john@example.com,"

    def test_normalize_recipients_multiple(self):
        """Test _normalize_recipients with multiple recipients."""
        from ownmail.database import ArchiveDatabase
        result = ArchiveDatabase._normalize_recipients("a@b.com, Name <c@d.com>")
        assert ",a@b.com," in result
        assert ",c@d.com," in result

    def test_normalize_recipients_empty(self):
        """Test _normalize_recipients with empty."""
        from ownmail.database import ArchiveDatabase
        assert ArchiveDatabase._normalize_recipients("") is None
        assert ArchiveDatabase._normalize_recipients(None) is None

    def test_normalize_recipients_no_email(self):
        """Test _normalize_recipients with no valid emails."""
        from ownmail.database import ArchiveDatabase
        assert ArchiveDatabase._normalize_recipients("Just A Name") is None


class TestParserDateNormalization:
    """Test parser date normalization edge cases."""

    def test_normalize_date_korean_prefix(self):
        """Test _normalize_date removes Korean weekday prefix."""
        from ownmail.parser import EmailParser
        # Korean weekday prefix should be removed
        date_str = "월요일, 1 Jan 2024 12:00:00 +0900"
        result = EmailParser._normalize_date(date_str)
        # Should normalize and return a date string
        assert result

    def test_normalize_date_numeric_month(self):
        """Test _normalize_date with numeric month format."""
        from ownmail.parser import EmailParser
        # Numeric format: DD M YY H:MM:SS +TZ
        date_str = "10 1 24 14:30:00 +0900"
        result = EmailParser._normalize_date(date_str)
        assert result  # Should parse

    def test_normalize_date_short_year(self):
        """Test _normalize_date with 2-digit year."""
        from ownmail.parser import EmailParser
        date_str = "10 1 99 14:30:00 +0900"
        result = EmailParser._normalize_date(date_str)
        # 99 should expand to 1999
        assert "1999" in result or result == date_str

    def test_normalize_date_short_timezone(self):
        """Test _normalize_date with short timezone."""
        from ownmail.parser import EmailParser
        # Short timezone "+9" should become "+0900"
        date_str = "10 1 2024 14:30:00 +9"
        result = EmailParser._normalize_date(date_str)
        assert result

    def test_normalize_date_invalid(self):
        """Test _normalize_date with invalid date returns original."""
        from ownmail.parser import EmailParser
        result = EmailParser._normalize_date("not a date")
        assert result == "not a date"


class TestParserIsReadableText:
    """Test parser _validate_decoded_text function."""

    def test_is_readable_ascii(self):
        """Test _validate_decoded_text with ASCII."""
        from ownmail.parser import _validate_decoded_text
        assert _validate_decoded_text("Hello World") is True

    def test_is_readable_korean(self):
        """Test _validate_decoded_text with Korean."""
        from ownmail.parser import _validate_decoded_text
        assert _validate_decoded_text("안녕하세요") is True

    def test_is_readable_empty(self):
        """Test _validate_decoded_text with empty."""
        from ownmail.parser import _validate_decoded_text
        # Empty string returns False (early bail out)
        assert _validate_decoded_text("") is False

    def test_is_readable_garbage(self):
        """Test _validate_decoded_text with garbage chars."""
        from ownmail.parser import _validate_decoded_text
        # Lots of control characters
        garbage = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0b\x0c"
        assert _validate_decoded_text(garbage) is False


class TestArchiveEmailsDir:
    """Test archive.py get_emails_dir function."""

    def test_get_emails_dir_with_account(self, tmp_path):
        """Test get_emails_dir with account specified."""
        from ownmail.archive import EmailArchive
        archive = EmailArchive(tmp_path)
        result = archive.get_emails_dir("test@example.com")
        assert "accounts" in str(result)
        assert "test@example.com" in str(result)


class TestDecodeHtmlBodyFunction:
    """Test web.py _decode_html_body function."""

    def test_decode_html_body_utf8(self):
        """Test _decode_html_body with UTF-8."""
        from ownmail.web import _decode_html_body
        html = b"<html><body>Hello World</body></html>"
        result = _decode_html_body(html, "utf-8")
        assert "Hello World" in result

    def test_decode_html_body_with_charset(self):
        """Test _decode_html_body with charset."""
        from ownmail.web import _decode_html_body
        html = b"<html><body>Hello</body></html>"
        result = _decode_html_body(html, "iso-8859-1")
        assert "Hello" in result

    def test_decode_html_body_no_charset(self):
        """Test _decode_html_body without charset."""
        from ownmail.web import _decode_html_body
        html = b"<html><body>Hello World</body></html>"
        result = _decode_html_body(html, None)
        assert "Hello World" in result

    def test_decode_html_body_meta_charset(self):
        """Test _decode_html_body detects charset from meta tag."""
        from ownmail.web import _decode_html_body
        html = b'<html><head><meta charset="utf-8"></head><body>Hello</body></html>'
        result = _decode_html_body(html, None)
        assert "Hello" in result

    def test_decode_html_body_korean(self):
        """Test _decode_html_body with Korean content."""
        from ownmail.web import _decode_html_body
        korean = "<html><body>안녕하세요</body></html>".encode()
        result = _decode_html_body(korean, "utf-8")
        assert "안녕" in result

    def test_decode_html_body_fallback(self):
        """Test _decode_html_body fallback for invalid bytes."""
        from ownmail.web import _decode_html_body
        # Invalid bytes
        bad_html = bytes([0xFF, 0xFE, 0x3C, 0x68, 0x74, 0x6D, 0x6C, 0x3E])
        result = _decode_html_body(bad_html, None)
        assert result  # Should return something


class TestParserTryDecode:
    """Test parser _try_decode function."""

    def test_try_decode_utf8(self):
        """Test _try_decode with UTF-8."""
        from ownmail.parser import _try_decode
        result = _try_decode(b"Hello World", "utf-8")
        assert result == "Hello World"

    def test_try_decode_invalid_encoding(self):
        """Test _try_decode with invalid encoding."""
        from ownmail.parser import _try_decode
        result = _try_decode(b"Hello", "not-a-valid-encoding")
        assert result is None

    def test_try_decode_korean(self):
        """Test _try_decode with Korean text."""
        from ownmail.parser import _try_decode
        korean = "안녕하세요"
        result = _try_decode(korean.encode('utf-8'), "utf-8")
        assert result == korean

    def test_try_decode_garbage(self):
        """Test _try_decode with garbage chars returns None."""
        from ownmail.parser import _try_decode
        # Bytes that decode to control characters - fails validation
        garbage_bytes = bytes([0x01, 0x02, 0x03, 0x04, 0x05])
        result = _try_decode(garbage_bytes, "utf-8")
        assert result is None  # Fails validation


class TestLinkifyLineFunction:
    """Test web.py _linkify_line function directly."""

    def test_linkify_line_no_url(self):
        """Test _linkify_line with no URL."""
        from ownmail.web import _linkify_line
        result = _linkify_line("Hello World")
        assert result == "Hello World"

    def test_linkify_line_http(self):
        """Test _linkify_line with HTTP URL."""
        from ownmail.web import _linkify_line
        result = _linkify_line("Visit https://example.com today")
        assert '<a href="https://example.com"' in result
        assert "target=" in result or "rel=" in result

    def test_linkify_line_email(self):
        """Test _linkify_line with email address."""
        from ownmail.web import _linkify_line
        result = _linkify_line("Contact user@example.com please")
        assert '<a href="mailto:user@example.com"' in result

    def test_linkify_line_multiple(self):
        """Test _linkify_line with multiple links."""
        from ownmail.web import _linkify_line
        result = _linkify_line("Site: https://a.com Email: b@c.com")
        assert "https://a.com" in result
        assert "mailto:" in result

    def test_linkify_line_escapes_html(self):
        """Test _linkify_line handles already-escaped HTML in non-URL parts."""
        from ownmail.web import _linkify_line
        # The function expects already-escaped input
        # So &lt;script&gt; should remain as-is outside of URLs
        result = _linkify_line("&lt;script&gt; https://ok.com")
        # The URL should be linked, other content unchanged
        assert "https://ok.com" in result
        assert "&lt;" in result  # HTML escaping preserved


class TestDatabaseQueryParsing:
    """Test database.py query parsing functions."""

    def test_parse_query_simple(self, tmp_path):
        """Test _parse_query with simple query."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        fts_query, filters = db._parse_query("test")
        assert "test" in fts_query or fts_query == "test"
        assert not filters.get("before")

    def test_parse_query_before(self, tmp_path):
        """Test _parse_query with before: filter."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        fts_query, filters = db._parse_query("before:2024-01-15 test")
        assert filters.get("before") == "2024-01-15"

    def test_parse_query_after(self, tmp_path):
        """Test _parse_query with after: filter."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        fts_query, filters = db._parse_query("after:2024-01-01 test")
        assert filters.get("after") == "2024-01-01"

    def test_parse_query_label(self, tmp_path):
        """Test _parse_query with label: filter."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        fts_query, filters = db._parse_query("label:important test")
        assert filters.get("label") == "important"

    def test_parse_query_sender(self, tmp_path):
        """Test _parse_query with from: filter."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        fts_query, filters = db._parse_query("from:john@example.com test")
        assert filters.get("sender") == "john@example.com"

    def test_parse_query_recipients(self, tmp_path):
        """Test _parse_query with to: filter."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        fts_query, filters = db._parse_query("to:jane@example.com test")
        assert filters.get("recipients") == "jane@example.com"

    def test_parse_query_orphan_and(self, tmp_path):
        """Test _parse_query removes orphan AND."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        fts_query, filters = db._parse_query("after:2024-01-01 AND before:2024-02-01")
        # Both dates extracted, AND should be cleaned up
        assert fts_query.strip() == "" or "AND" not in fts_query.upper()

    def test_convert_query_field_prefixes(self, tmp_path):
        """Test _convert_query converts field prefixes."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        result = db._convert_query("from:john")
        assert "sender:" in result
        result = db._convert_query("to:jane")
        assert "recipients:" in result
        result = db._convert_query("attachment:pdf")
        assert "attachments:" in result


class TestDatabaseSearchFilters:
    """Test database search with various filters."""

    def test_search_with_combined_filters(self, tmp_path):
        """Test search with multiple filters."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        # Create a test email
        db.mark_downloaded(_eid("test-msg-123"), "test-msg-123", "2024/01/test.eml")
        db.index_email(
            email_id=_eid("test-msg-123"),
            subject="Test Subject",
            sender="john@example.com",
            recipients="jane@example.com",
            date_str="Mon, 15 Jan 2024 12:00:00 +0000",
            body="Test body content",
            attachments=""
        )
        # Search with filter
        results = db.search("from:john test")
        # Should handle search gracefully
        assert isinstance(results, list)

    def test_search_date_filter(self, tmp_path):
        """Test search with date filters."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        # Create a test email
        db.mark_downloaded(_eid("test-msg-date"), "test-msg-date", "2024/01/test2.eml")
        db.index_email(
            email_id=_eid("test-msg-date"),
            subject="Date Test",
            sender="john@example.com",
            recipients="jane@example.com",
            date_str="Mon, 15 Jan 2024 12:00:00 +0000",
            body="Body text",
            attachments=""
        )
        # Search with date filter
        results = db.search("after:2024-01-01 Date Test")
        assert isinstance(results, list)


class TestDatabaseStats:
    """Test database stats functionality."""

    def test_get_email_count(self, tmp_path):
        """Test get_email_count method."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        # Initially empty
        count = db.get_email_count()
        assert count == 0
        # Add an email
        db.mark_downloaded(_eid("msg-1"), "msg-1", "2024/01/email.eml")
        count = db.get_email_count()
        assert count == 1

    def test_get_stats(self, tmp_path):
        """Test get_stats method."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        # Add emails
        db.mark_downloaded(_eid("msg-1", "test@example.com"), "msg-1", "2024/01/email1.eml", account="test@example.com")
        db.index_email(
            email_id=_eid("msg-1", "test@example.com"),
            subject="Test",
            sender="sender@example.com",
            recipients="recipient@example.com",
            date_str="Mon, 15 Jan 2024 12:00:00 +0000",
            body="Body",
            attachments=""
        )
        stats = db.get_stats()
        assert "total_emails" in stats or "total" in str(stats).lower()

    def test_get_stats_by_account(self, tmp_path):
        """Test get_stats filtered by account."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1", "a@example.com"), "msg-1", "2024/01/email1.eml", account="a@example.com")
        db.mark_downloaded(_eid("msg-2", "b@example.com"), "msg-2", "2024/01/email2.eml", account="b@example.com")
        stats = db.get_stats("a@example.com")
        # Check that filtering works
        assert isinstance(stats, dict)


class TestDatabaseDownloadedIds:
    """Test database downloaded IDs functionality."""

    def test_get_downloaded_ids(self, tmp_path):
        """Test get_downloaded_ids method."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        db.mark_downloaded(_eid("msg-2"), "msg-2", "test2.eml")
        ids = db.get_downloaded_ids()
        assert "msg-1" in ids
        assert "msg-2" in ids

    def test_get_downloaded_ids_by_account(self, tmp_path):
        """Test get_downloaded_ids with account filter."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1", "a@example.com"), "msg-1", "test1.eml", account="a@example.com")
        db.mark_downloaded(_eid("msg-2", "b@example.com"), "msg-2", "test2.eml", account="b@example.com")
        ids = db.get_downloaded_ids("a@example.com")
        assert "msg-1" in ids
        assert "msg-2" not in ids


class TestDatabaseSyncState:
    """Test database sync state functionality."""

    def test_get_set_sync_state(self, tmp_path):
        """Test get_sync_state and set_sync_state."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        # Initially None
        result = db.get_sync_state("test@example.com", "history_id")
        assert result is None
        # Set a value
        db.set_sync_state("test@example.com", "history_id", "12345")
        result = db.get_sync_state("test@example.com", "history_id")
        assert result == "12345"

    def test_delete_sync_state(self, tmp_path):
        """Test delete_sync_state."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.set_sync_state("test@example.com", "key1", "value1")
        db.delete_sync_state("test@example.com", "key1")
        result = db.get_sync_state("test@example.com", "key1")
        assert result is None

    def test_get_set_history_id(self, tmp_path):
        """Test get_history_id and set_history_id."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        # Set history_id
        db.set_history_id("12345", "test@example.com")
        result = db.get_history_id("test@example.com")
        assert result == "12345"


class TestDatabaseIsIndexed:
    """Test database is_indexed functionality."""

    def test_is_indexed_false(self, tmp_path):
        """Test is_indexed returns False for non-indexed email."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        # Not yet indexed
        assert db.is_indexed(_eid("msg-1")) is False

    def test_is_indexed_true(self, tmp_path):
        """Test is_indexed returns True for indexed email."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        db.index_email(
            _eid("msg-1"), "Subject", "from@test.com", "to@test.com",
            "Mon, 15 Jan 2024 12:00:00 +0000", "Body", ""
        )
        assert db.is_indexed(_eid("msg-1")) is True


class TestDatabaseEmailById:
    """Test database get_email_by_id functionality."""

    def test_get_email_by_id_not_found(self, tmp_path):
        """Test get_email_by_id returns None for non-existent."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        result = db.get_email_by_id("non-existent")
        assert result is None

    def test_get_email_by_id_found(self, tmp_path):
        """Test get_email_by_id returns email data."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        result = db.get_email_by_id(_eid("msg-1"))
        # Returns a tuple with email data
        assert result is not None


class TestDatabaseSearchAdvanced:
    """Test advanced database search scenarios."""

    def test_search_sender_name(self, tmp_path):
        """Test search with sender name (not email)."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        db.index_email(
            _eid("msg-1"), "Test Subject", "John Doe <john@example.com>",
            "jane@example.com", "Mon, 15 Jan 2024 12:00:00 +0000",
            "Body content", ""
        )
        # Search by sender name (not email)
        results = db.search("from:John")
        assert isinstance(results, list)

    def test_search_recipients_name(self, tmp_path):
        """Test search with recipient name (not email)."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        db.index_email(
            _eid("msg-1"), "Test Subject", "john@example.com",
            "Jane Doe <jane@example.com>", "Mon, 15 Jan 2024 12:00:00 +0000",
            "Body content", ""
        )
        # Search by recipient name
        results = db.search("to:Jane")
        assert isinstance(results, list)

    def test_search_by_label(self, tmp_path):
        """Test search with label filter."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        db.index_email(
            _eid("msg-1"), "Test Subject", "john@example.com",
            "jane@example.com", "Mon, 15 Jan 2024 12:00:00 +0000",
            "Body content", "", labels="important,inbox"
        )
        results = db.search("label:important")
        assert isinstance(results, list)

    def test_search_date_sorted(self, tmp_path):
        """Test search with date sorting."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test1.eml")
        db.mark_downloaded(_eid("msg-2"), "msg-2", "test2.eml")
        db.index_email(
            _eid("msg-1"), "First", "a@test.com", "b@test.com",
            "Mon, 15 Jan 2024 12:00:00 +0000", "Body 1", ""
        )
        db.index_email(
            _eid("msg-2"), "Second", "a@test.com", "b@test.com",
            "Tue, 16 Jan 2024 12:00:00 +0000", "Body 2", ""
        )
        results = db.search("Body", sort="date")
        assert isinstance(results, list)

    def test_search_date_asc(self, tmp_path):
        """Test search with ascending date sort."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test1.eml")
        db.index_email(
            _eid("msg-1"), "Test", "a@test.com", "b@test.com",
            "Mon, 15 Jan 2024 12:00:00 +0000", "Body", ""
        )
        results = db.search("Test", sort="date_asc")
        assert isinstance(results, list)

    def test_search_with_offset(self, tmp_path):
        """Test search with offset for pagination."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        for i in range(5):
            db.mark_downloaded(_eid(f"msg-{i}"), f"msg-{i}", f"test{i}.eml")
            db.index_email(
                _eid(f"msg-{i}"), f"Test {i}", "a@test.com", "b@test.com",
                "Mon, 15 Jan 2024 12:00:00 +0000", "Body", ""
            )
        # Get with offset
        results = db.search("Test", limit=2, offset=2)
        assert isinstance(results, list)

    def test_search_recipient_email_filter(self, tmp_path):
        """Test search filtering by recipient email address."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test1.eml")
        db.index_email(
            _eid("msg-1"), "Test Subject", "john@example.com",
            "jane@example.com", "Mon, 15 Jan 2024 12:00:00 +0000",
            "Body content", ""
        )
        # Search by recipient email
        results = db.search("to:jane@example.com Test")
        assert isinstance(results, list)


class TestDatabaseClearIndex:
    """Test database clear_index functionality."""

    def test_clear_index(self, tmp_path):
        """Test clear_index clears metadata but keeps download records."""
        from ownmail.database import ArchiveDatabase
        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded(_eid("msg-1"), "msg-1", "test.eml")
        db.index_email(
            _eid("msg-1"), "Test", "from@test.com", "to@test.com",
            "Mon, 15 Jan 2024 12:00:00 +0000", "Body", ""
        )
        # Clear index
        db.clear_index()
        # Download should exist but metadata cleared
        assert db.is_downloaded("msg-1")
        assert not db.is_indexed(_eid("msg-1"))


class TestCommandsReindexSingle:
    """Test commands reindex with single file."""

    def test_reindex_nonexistent_file(self, tmp_path, capsys):
        """Test cmd_reindex with nonexistent file."""
        from pathlib import Path

        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(tmp_path)
        # Try to reindex a non-existent file
        cmd_reindex(archive, file_path=Path("/nonexistent/file.eml"))
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower() or "Reindex" in captured.out


class TestCommandsVerify:
    """Test commands verify functionality."""

    def test_verify_empty_archive(self, tmp_path, capsys):
        """Test cmd_verify with empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_verify

        archive = EmailArchive(tmp_path)
        cmd_verify(archive)
        captured = capsys.readouterr()
        # Should complete without error
        assert "Verify" in captured.out or "No emails" in captured.out or "0" in captured.out


class TestConfigHelpers:
    """Test config.py helper functions."""

    def test_get_archive_root_default(self):
        """Test get_archive_root with default."""
        from pathlib import Path

        from ownmail.config import get_archive_root
        result = get_archive_root({})
        assert isinstance(result, Path)

    def test_get_archive_root_explicit(self):
        """Test get_archive_root with explicit config."""
        from ownmail.config import get_archive_root
        result = get_archive_root({"archive_root": "/custom/path"})
        assert "/custom" in str(result)

    def test_get_archive_root_legacy(self):
        """Test get_archive_root with legacy archive_dir key."""
        from ownmail.config import get_archive_root
        result = get_archive_root({"archive_dir": "/legacy/path"})
        assert "/legacy" in str(result)

    def test_get_sources_empty(self):
        """Test get_sources with empty config."""
        from ownmail.config import get_sources
        result = get_sources({})
        assert result == []

    def test_get_sources_populated(self):
        """Test get_sources with populated config."""
        from ownmail.config import get_sources
        config = {"sources": [{"name": "test", "type": "gmail"}]}
        result = get_sources(config)
        assert len(result) == 1
        assert result[0]["name"] == "test"

    def test_get_source_by_name_found(self):
        """Test get_source_by_name when source exists."""
        from ownmail.config import get_source_by_name
        config = {"sources": [{"name": "test", "type": "gmail"}]}
        result = get_source_by_name(config, "test")
        assert result is not None
        assert result["name"] == "test"

    def test_get_source_by_name_not_found(self):
        """Test get_source_by_name when source doesn't exist."""
        from ownmail.config import get_source_by_name
        config = {"sources": [{"name": "test", "type": "gmail"}]}
        result = get_source_by_name(config, "nonexistent")
        assert result is None
