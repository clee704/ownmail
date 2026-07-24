"""Tests for web interface."""

import email
from unittest.mock import MagicMock

import pytest

from ownmail.web import (
    _extract_body_content,
    _extract_snippet,
    _format_date_long,
    _format_date_short,
    _format_size,
    _get_server_timezone_name,
    _resolve_timezone,
    _to_local_datetime,
    block_external_images,
    create_app,
    decode_header,
    parse_email_address,
    parse_recipients,
)


class TestDecodeHeader:
    """Tests for decode_header function."""

    def test_plain_text(self):
        """Plain text should pass through unchanged."""
        assert decode_header("Hello World") == "Hello World"

    def test_empty_string(self):
        """Empty string should return empty."""
        assert decode_header("") == ""

    def test_none(self):
        """None should return empty string."""
        assert decode_header(None) == ""

    def test_utf8_base64(self):
        """UTF-8 Base64 encoded header should be decoded."""
        # "테스트" in Korean, Base64 encoded
        encoded = "=?UTF-8?B?7YWM7Iqk7Yq4?="
        result = decode_header(encoded)
        assert result == "테스트"

    def test_utf8_quoted_printable(self):
        """UTF-8 quoted-printable encoded header should be decoded."""
        encoded = "=?UTF-8?Q?Hello_World?="
        result = decode_header(encoded)
        assert result == "Hello World"

    def test_mixed_encoded_plain(self):
        """Mixed encoded and plain text should be decoded."""
        encoded = "=?UTF-8?B?7YWM7Iqk7Yq4?= Test"
        result = decode_header(encoded)
        assert "테스트" in result
        assert "Test" in result

    def test_split_multibyte_encoded_words(self):
        """Split multi-byte chars across encoded-words should be decoded."""
        # This is a malformed header where a multi-byte char is split
        # "PhpBB2 forum at ROPAS에 오신것을 환영합니다" split across two encoded-words
        encoded = "=?utf-8?B?UGhwQkIyIGZvcnVtIGF0IFJPUEFT7JeQIOyYpOyLoOqyg+ydhCDtmZjsmIHtla?= =?utf-8?B?nri4jri6Q=?="
        result = decode_header(encoded)
        # Should decode to readable Korean, not return the raw encoded string
        assert "=?" not in result
        assert "ROPAS" in result

    def test_malformed_base64_fallback(self):
        """Malformed base64 should not crash, return best effort."""
        # Invalid base64 that can't be decoded
        encoded = "=?utf-8?B?invalid!!!base64?="
        result = decode_header(encoded)
        # Should return something, not crash
        assert isinstance(result, str)


class TestBlockExternalImages:
    """Tests for block_external_images function."""

    def test_no_images(self):
        """HTML without images should pass through unchanged."""
        html = "<p>Hello World</p>"
        result, has_external = block_external_images(html)
        assert result == html
        assert has_external is False

    def test_external_http_image(self):
        """External HTTP image should be blocked."""
        html = '<img src="http://example.com/image.jpg">'
        result, has_external = block_external_images(html)
        assert "data-src" in result
        assert 'data-src="http://example.com/image.jpg"' in result
        assert has_external is True

    def test_external_https_image(self):
        """External HTTPS image should be blocked."""
        html = '<img src="https://example.com/image.jpg">'
        result, has_external = block_external_images(html)
        assert "data-src" in result
        assert 'data-src="https://example.com/image.jpg"' in result
        assert has_external is True

    def test_data_uri_not_blocked(self):
        """Data URI images should not be blocked."""
        html = '<img src="data:image/png;base64,abc123">'
        result, has_external = block_external_images(html)
        assert result == html
        assert has_external is False


class TestParseEmailAddress:
    """Tests for parse_email_address function."""

    def test_name_and_email(self):
        """Parse name and email address."""
        name, email_addr = parse_email_address("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email_addr == "john@example.com"

    def test_email_only(self):
        """Parse email-only address."""
        name, email_addr = parse_email_address("john@example.com")
        assert name == ""
        assert email_addr == "john@example.com"

    def test_quoted_name(self):
        """Parse quoted name."""
        name, email_addr = parse_email_address('"Doe, John" <john@example.com>')
        assert name == "Doe, John"  # Quotes are stripped
        assert email_addr == "john@example.com"

    def test_empty(self):
        """Empty string should return empty tuple."""
        name, email_addr = parse_email_address("")
        assert name == ""
        assert email_addr == ""


class TestParseRecipients:
    """Tests for parse_recipients function."""

    def test_single_recipient(self):
        """Parse single recipient."""
        result = parse_recipients("john@example.com")
        assert len(result) == 1
        assert result[0]["email"] == "john@example.com"

    def test_multiple_recipients(self):
        """Parse multiple comma-separated recipients."""
        result = parse_recipients("john@example.com, jane@example.com")
        assert len(result) == 2
        assert result[0]["email"] == "john@example.com"
        assert result[1]["email"] == "jane@example.com"

    def test_recipients_with_names(self):
        """Parse recipients with names."""
        result = parse_recipients("John <john@example.com>, Jane <jane@example.com>")
        assert len(result) == 2
        assert result[0]["name"] == "John"
        assert result[0]["email"] == "john@example.com"


class TestExtractSnippet:
    """Tests for _extract_snippet function."""

    def test_plain_text_email(self):
        """Extract snippet from plain text email."""
        msg = email.message_from_string("Content-Type: text/plain\n\nHello, this is a test email body.")
        snippet = _extract_snippet(msg)
        assert "Hello" in snippet
        assert "test email" in snippet

    def test_long_text_truncation(self):
        """Long text should be truncated."""
        long_text = "A" * 200
        msg = email.message_from_string(f"Content-Type: text/plain\n\n{long_text}")
        snippet = _extract_snippet(msg, max_len=50)
        assert len(snippet) <= 54  # 50 + "..."
        assert snippet.endswith("...")


class TestFormatSize:
    """Tests for _format_size function."""

    def test_bytes(self):
        """Small sizes should be in bytes."""
        assert _format_size(500) == "500 B"

    def test_kilobytes(self):
        """Medium sizes should be in KB."""
        assert _format_size(2048) == "2.0 KB"

    def test_megabytes(self):
        """Large sizes should be in MB."""
        assert _format_size(2 * 1024 * 1024) == "2.0 MB"


class TestCreateApp:
    """Tests for Flask app creation and routes."""

    @pytest.fixture
    def mock_archive(self, tmp_path):
        """Create a mock archive for testing."""
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_stats.return_value = {
            "total_emails": 100,
            "indexed_emails": 100,
        }
        archive.search.return_value = []
        return archive

    def test_app_creation(self, mock_archive):
        """App should be created successfully."""
        app = create_app(mock_archive)
        assert app is not None

    def test_index_route(self, mock_archive):
        """Index route should redirect to search."""
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/")
            assert response.status_code == 302
            assert response.location == "/search"

    def test_search_route_empty(self, mock_archive):
        """Search route with no query should return search page."""
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search")
            assert response.status_code == 200

    def test_search_route_with_query(self, mock_archive):
        """Search route with query should call archive.search."""
        mock_archive.search.return_value = []
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test")
            assert response.status_code == 200
            mock_archive.search.assert_called()

    def test_search_error_handling(self, mock_archive):
        """Search errors should be handled gracefully."""
        mock_archive.search.side_effect = Exception("FTS syntax error")
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=tpc-ds")
            assert response.status_code == 200
            assert b"error" in response.data.lower()

    def test_help_route(self, mock_archive):
        """Help route should return help page."""
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/help")
            assert response.status_code == 200
            assert b"Search syntax" in response.data

    def test_email_route_not_found(self, mock_archive):
        """Email route with invalid ID should return 404."""
        mock_archive.db.get_email_by_id.return_value = None
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/nonexistent")
            assert response.status_code == 404

    def test_trusted_senders_config(self, mock_archive):
        """Trusted senders should be configured."""
        app = create_app(
            mock_archive,
            trusted_senders=["trusted@example.com"],
        )
        assert "trusted@example.com" in app.config["trusted_senders"]

    def test_trust_sender_route(self, mock_archive, tmp_path):
        """Trust sender route should add to trusted set."""
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post(
                "/trust-sender",
                data={"email": "new@example.com", "redirect": "/"},
                follow_redirects=False,
            )
            assert response.status_code == 302
            assert "new@example.com" in app.config["trusted_senders"]

    def test_untrust_sender_route(self, mock_archive):
        """Untrust sender route should remove from trusted set."""
        app = create_app(mock_archive, trusted_senders=["trusted@example.com"])
        with app.test_client() as client:
            response = client.post(
                "/untrust-sender",
                data={"email": "trusted@example.com"},
            )
            assert response.status_code == 200
            assert "trusted@example.com" not in app.config["trusted_senders"]

    def test_untrust_sender_empty_email(self, mock_archive):
        """Untrust sender with empty email should return error."""
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post(
                "/untrust-sender",
                data={"email": ""},
            )
            assert response.status_code == 200
            assert b"error" in response.data

    def test_search_with_pagination(self, mock_archive):
        """Search with pagination should work."""
        # Return more than one page of results
        mock_archive.search.return_value = [
            (f"msg{i}", f"file{i}.eml", f"Subject {i}", "sender@example.com", "2024-01-01", "snippet")
            for i in range(25)  # More than default page size
        ]
        app = create_app(mock_archive, page_size=20)
        with app.test_client() as client:
            response = client.get("/search?q=test&page=1")
            assert response.status_code == 200
            assert b"ownmail-toolbar-arrow" in response.data  # Has pagination

    def test_search_sort_options(self, mock_archive):
        """Search with different sort options should work."""
        mock_archive.search.return_value = []
        app = create_app(mock_archive)
        with app.test_client() as client:
            # Date desc sort
            response = client.get("/search?q=test&sort=date_desc")
            assert response.status_code == 200

            # Date asc sort
            response = client.get("/search?q=test&sort=date_asc")
            assert response.status_code == 200

            # Invalid sort should default to relevance
            response = client.get("/search?q=test&sort=invalid")
            assert response.status_code == 200

    def test_verbose_mode(self, mock_archive, capsys):
        """Verbose mode should print timing info."""
        app = create_app(mock_archive, verbose=True)
        with app.test_client() as client:
            response = client.get("/search")
            assert response.status_code == 200
            # Verbose logging happens via print


class TestDecodeTextBody:
    """Tests for _decode_text_body function."""

    def test_utf8_content(self):
        """UTF-8 content should decode correctly."""
        from ownmail.web import _decode_text_body

        payload = b"Hello World"
        result = _decode_text_body(payload, "utf-8")
        assert result == "Hello World"

    def test_korean_content_euc_kr(self):
        """Korean EUC-KR content should decode correctly."""
        from ownmail.web import _decode_text_body

        payload = "안녕하세요".encode("euc-kr")
        result = _decode_text_body(payload, "euc-kr")
        assert "안녕하세요" in result

    def test_no_charset_auto_detect(self):
        """Content without charset should auto-detect."""
        from ownmail.web import _decode_text_body

        payload = b"Hello World"
        result = _decode_text_body(payload, None)
        assert "Hello" in result

    def test_invalid_charset_fallback(self):
        """Invalid charset should fallback to auto-detection."""
        from ownmail.web import _decode_text_body

        payload = b"Hello World"
        result = _decode_text_body(payload, "invalid-charset-xyz")
        assert "Hello" in result

    def test_charset_alias_is_mapped(self):
        """ks_c_5601-1987 should be treated as cp949."""
        from ownmail.web import _decode_text_body

        assert _decode_text_body("안녕하세요".encode("cp949"), "ks_c_5601-1987") == "안녕하세요"

    def test_wrong_declared_charset_falls_through_to_detection(self):
        """A wrong declared charset should not corrupt the output."""
        from ownmail.web import _decode_text_body

        assert _decode_text_body("안녕하세요 반갑습니다".encode(), "euc-kr") == "안녕하세요 반갑습니다"

    def test_undeclared_cjk_is_detected(self):
        """CJK bytes with no declared charset should still decode."""
        from ownmail.web import _decode_text_body

        payload = ("안녕하세요 반갑습니다 " * 5).encode("euc-kr")
        assert "안녕하세요" in _decode_text_body(payload, None)

    def test_undecodable_bytes_degrade(self):
        """Bytes nothing decodes cleanly should still return a string."""
        from ownmail.web import _decode_text_body

        assert isinstance(_decode_text_body(bytes(range(0x80, 0x100)), None), str)


class TestDecodeHtmlBody:
    """Tests for _decode_html_body function."""

    def test_html_with_meta_charset(self):
        """HTML with meta charset should use it."""
        from ownmail.web import _decode_html_body

        html = b'<html><head><meta charset="utf-8"></head><body>Hello</body></html>'
        result = _decode_html_body(html, None)
        assert "Hello" in result

    def test_html_with_header_charset(self):
        """HTML with header charset should use it."""
        from ownmail.web import _decode_html_body

        html = "Hello 안녕".encode()
        result = _decode_html_body(html, "utf-8")
        assert "Hello" in result

    def test_html_no_charset_fallback(self):
        """HTML without charset should fallback."""
        from ownmail.web import _decode_html_body

        html = b"<html><body>Hello World</body></html>"
        result = _decode_html_body(html, None)
        assert "Hello" in result

    def test_wrong_declared_charset_falls_back_to_meta(self):
        """A bad header charset should not prevent meta-tag detection."""
        from ownmail.web import _decode_html_body

        html = '<html><head><meta charset="euc-kr"></head><body>안녕하세요 반갑습니다</body></html>'
        assert "안녕하세요" in _decode_html_body(html.encode("euc-kr"), "utf-8")

    def test_undeclared_cjk_is_detected(self):
        """CJK HTML with no charset anywhere should still decode."""
        from ownmail.web import _decode_html_body

        payload = ("<p>안녕하세요 반갑습니다</p>" * 5).encode("euc-kr")
        assert "안녕하세요" in _decode_html_body(payload, None)

    def test_unknown_charset_name_falls_back(self):
        """An unrecognized charset name should not raise."""
        from ownmail.web import _decode_html_body

        assert _decode_html_body(b"<p>Hello</p>", "not-a-real-charset") == "<p>Hello</p>"


class TestValidateDecodedText:
    """Tests for _validate_decoded_text function."""

    def test_valid_ascii_text(self):
        """Valid ASCII text should pass."""
        from ownmail.web import _validate_decoded_text

        assert _validate_decoded_text("Hello World") is True

    def test_valid_korean_text(self):
        """Valid Korean text should pass."""
        from ownmail.web import _validate_decoded_text

        assert _validate_decoded_text("안녕하세요") is True

    def test_replacement_characters_fail(self):
        """Text with replacement characters should fail."""
        from ownmail.web import _validate_decoded_text

        assert _validate_decoded_text("Hello\ufffd\ufffd") is False

    def test_empty_text(self):
        """Empty text should fail."""
        from ownmail.web import _validate_decoded_text

        assert _validate_decoded_text("") is False


class TestTryDecode:
    """Tests for _try_decode function."""

    def test_valid_decode(self):
        """Valid decoding should return text."""
        from ownmail.web import _try_decode

        result = _try_decode(b"Hello", "utf-8")
        assert result == "Hello"

    def test_invalid_decode(self):
        """Invalid decoding should return None."""
        from ownmail.web import _try_decode

        # EUC-KR bytes that won't decode as UTF-8
        korean_bytes = "안녕".encode("euc-kr")
        result = _try_decode(korean_bytes, "utf-8")
        # Should return None or invalid result
        assert result is None or "\ufffd" not in result


class TestRawEmailRoute:
    """Tests for /raw/<email_id> route."""

    def test_raw_email_found(self, tmp_path):
        """Raw email route should return file content."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        # Create test .eml file
        eml_content = b"From: test@example.com\nSubject: Test\n\nBody"
        eml_path = tmp_path / "emails" / "test.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/test.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/raw/msg1")
            assert response.status_code == 200
            assert b"From: test@example.com" in response.data

    def test_raw_email_not_found(self, tmp_path):
        """Raw email route should 404 for missing email."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = None
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/raw/nonexistent")
            assert response.status_code == 404


class TestAttachmentRoute:
    """Tests for /attachment/<email_id>/<index> route."""

    def test_attachment_not_found(self, tmp_path):
        """Attachment route should 404 for missing email."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = None
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/attachment/msg1/0")
            assert response.status_code == 404

    def test_attachment_file_missing(self, tmp_path):
        """Attachment route should 404 for missing file."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "missing.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/attachment/msg1/0")
            assert response.status_code == 404


class TestExtractSnippetMultipart:
    """Tests for _extract_snippet with multipart emails."""

    def test_multipart_email_snippet(self):
        """Extract snippet from multipart email."""
        import email

        from ownmail.web import _extract_snippet

        content = b"""MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="boundary"

--boundary
Content-Type: text/plain

This is plain text content.
--boundary
Content-Type: text/html

<html><body>This is HTML</body></html>
--boundary--
"""
        msg = email.message_from_bytes(content)
        snippet = _extract_snippet(msg)
        assert "plain text" in snippet.lower()

    def test_html_only_message_yields_nothing(self):
        """A message with no text/plain part should produce no snippet."""
        raw = "Content-Type: text/html\n\n<p>only html</p>"
        assert _extract_snippet(email.message_from_string(raw)) == ""

    def test_empty_payload_yields_nothing(self):
        """An empty body should produce an empty snippet."""
        assert _extract_snippet(email.message_from_string("Content-Type: text/plain\n\n")) == ""


class TestViewEmailRoute:
    """Tests for /email/<email_id> route."""

    def test_view_email_success(self, tmp_path):
        """View email should render email detail page."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        # Create test .eml file
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Mon, 15 Jan 2024 10:30:00 +0000
Content-Type: text/plain

This is the email body.
"""
        eml_path = tmp_path / "emails" / "test.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/test.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/msg1")
            assert response.status_code == 200
            assert b"Test Subject" in response.data
            assert b"sender@example.com" in response.data

    def test_view_email_with_html_body(self, tmp_path):
        """View email with HTML body should render HTML."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: HTML Email
Content-Type: text/html

<html><body><h1>HTML Title</h1><p>Paragraph text.</p></body></html>
"""
        eml_path = tmp_path / "emails" / "html.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg2", "emails/html.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/msg2")
            assert response.status_code == 200

    def test_view_email_with_attachment(self, tmp_path):
        """View email with attachment should show attachment info."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: With Attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="---=_Part"

-----=_Part
Content-Type: text/plain

Body text here.
-----=_Part
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"

PDF content here
-----=_Part--
"""
        eml_path = tmp_path / "emails" / "attach.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg3", "emails/attach.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/msg3")
            assert response.status_code == 200
            assert b"document.pdf" in response.data

    def test_view_email_file_missing(self, tmp_path):
        """View email with missing file should 404."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/missing.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/msg1")
            assert response.status_code == 404

    def test_view_email_multipart_alternative(self, tmp_path):
        """View multipart/alternative email should prefer HTML."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Multipart Alternative
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="---=_Part"

-----=_Part
Content-Type: text/plain

Plain text version.
-----=_Part
Content-Type: text/html

<html><body>HTML version</body></html>
-----=_Part--
"""
        eml_path = tmp_path / "emails" / "multipart.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg4", "emails/multipart.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/msg4")
            assert response.status_code == 200


class TestDownloadAttachment:
    """Tests for /attachment/<email_id>/<index> route."""

    def test_download_attachment_success(self, tmp_path):
        """Downloading attachment should return file."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
Subject: With Attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="---=_Part"

-----=_Part
Content-Type: text/plain

Body text.
-----=_Part
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"

PDF CONTENT HERE
-----=_Part--
"""
        eml_path = tmp_path / "emails" / "attach.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/attach.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/attachment/msg1/0")
            assert response.status_code == 200
            assert b"PDF CONTENT HERE" in response.data

    def test_download_attachment_wrong_index(self, tmp_path):
        """Wrong attachment index should 404."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
Subject: With Attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="---=_Part"

-----=_Part
Content-Type: text/plain

Body text.
-----=_Part
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"

PDF CONTENT
-----=_Part--
"""
        eml_path = tmp_path / "emails" / "attach.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/attach.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            # Index 99 doesn't exist
            response = client.get("/attachment/msg1/99")
            assert response.status_code == 404


class TestTrustSenderWithConfig:
    """Tests for trust sender with config file."""

    def test_trust_sender_updates_config(self, tmp_path):
        """Trust sender should update config.yaml."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app
        from ownmail.yaml_util import load_yaml

        # Create config file
        config_path = tmp_path / "config.yaml"
        config_path.write_text("web:\n  trusted_senders: []\n")

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive, config_path=str(config_path))
        with app.test_client() as client:
            # When redirect is "/", returns JSON 200 instead of redirect
            response = client.post(
                "/trust-sender",
                data={"email": "newtrust@example.com", "redirect": "/"},
            )
            assert response.status_code == 200
            assert b"ok" in response.data

            # Check config was updated
            config = load_yaml(config_path)
            assert "newtrust@example.com" in config["web"]["trusted_senders"]

    def test_trust_sender_with_actual_redirect(self, tmp_path):
        """Trust sender should redirect when redirect path is not '/'."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        # Create config file
        config_path = tmp_path / "config.yaml"
        config_path.write_text("web:\n  trusted_senders: []\n")

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive, config_path=str(config_path))
        with app.test_client() as client:
            response = client.post(
                "/trust-sender",
                data={"email": "another@example.com", "redirect": "/email/msg1"},
            )
            assert response.status_code == 302
            assert "/email/msg1" in response.location

    def test_untrust_sender_updates_config(self, tmp_path):
        """Untrust sender should update config.yaml."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app
        from ownmail.yaml_util import load_yaml

        # Create config file with trusted sender
        config_path = tmp_path / "config.yaml"
        config_path.write_text("web:\n  trusted_senders:\n    - remove@example.com\n")

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive, config_path=str(config_path), trusted_senders=["remove@example.com"])
        with app.test_client() as client:
            response = client.post(
                "/untrust-sender",
                data={"email": "remove@example.com"},
            )
            assert response.status_code == 200

            # Check config was updated
            config = load_yaml(config_path)
            assert "remove@example.com" not in config["web"]["trusted_senders"]


class TestBlockImages:
    """Tests for image blocking feature."""

    def test_block_images_enabled(self, tmp_path):
        """Images should be blocked when enabled."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
Subject: With Images
Content-Type: text/html

<html><body><img src="http://example.com/track.gif"></body></html>
"""
        eml_path = tmp_path / "emails" / "img.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/img.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive, block_images=True)
        with app.test_client() as client:
            response = client.get("/email/msg1")
            assert response.status_code == 200
            # Image blocking banner should be shown
            assert b"data-src" in response.data or b"blocked" in response.data.lower()

    def test_trusted_sender_not_blocked(self, tmp_path):
        """Images from trusted senders should not be blocked."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: trusted@example.com
Subject: Trusted Images
Content-Type: text/html

<html><body><img src="http://example.com/logo.gif"></body></html>
"""
        eml_path = tmp_path / "emails" / "trusted.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/trusted.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive, block_images=True, trusted_senders=["trusted@example.com"])
        with app.test_client() as client:
            response = client.get("/email/msg1")
            assert response.status_code == 200
            # Should NOT show blocking banner
            assert b"Images are blocked" not in response.data or b"trusted" in response.data.lower()

    def test_block_images_respects_runtime_config_change(self, tmp_path):
        """Changing block_images via app.config should take effect immediately."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
Subject: Runtime Test
Content-Type: text/html

<html><body><img src="http://example.com/track.gif"></body></html>
"""
        eml_path = tmp_path / "emails" / "rt.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/rt.eml", None, None, None, None)
        mock_archive.db.get_email_count.return_value = 100

        # Start with block_images=True
        app = create_app(mock_archive, block_images=True)
        with app.test_client() as client:
            resp1 = client.get("/email/msg1")
            assert b"data-src" in resp1.data or b"blocked" in resp1.data.lower()

            # Simulate settings page toggling block_images off
            app.config["block_images"] = False

            resp2 = client.get("/email/msg1")
            # The original src should be intact (not replaced with data-src)
            assert b'src="http://example.com/track.gif"' in resp2.data

    def test_page_size_respects_runtime_config_change(self, tmp_path):
        """Changing page_size via app.config should take effect immediately."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        # Start with page_size=10
        app = create_app(mock_archive, page_size=10)
        with app.test_client() as client:
            client.get("/search?q=hello")
            # Search should use limit=10+1 (fetches one extra to detect "more")
            call_args = mock_archive.search.call_args
            assert call_args[1]["limit"] == 11  # 10 + 1

            mock_archive.search.reset_mock()

            # Simulate settings page changing page_size
            app.config["page_size"] = 50
            client.get("/search?q=hello")
            call_args = mock_archive.search.call_args
            # Should now use limit=50+1
            assert call_args[1]["limit"] == 51  # 50 + 1


class TestExtractBodyContent:
    """Tests for _extract_body_content function."""

    def test_full_html_document(self):
        """Extract body from full HTML document."""
        html = "<html><head><title>Hi</title></head><body><p>Hello</p></body></html>"
        result = _extract_body_content(html)
        assert "<p>Hello</p>" in result
        assert "<html>" not in result
        assert "<head>" not in result
        assert "<body>" not in result

    def test_preserves_style_tags(self):
        """Style tags from head should be preserved."""
        html = '<html><head><style>.red { color: red; }</style></head><body><p class="red">Hi</p></body></html>'
        result = _extract_body_content(html)
        assert "<style>" in result
        assert "color: red" in result
        assert '<p class="red">Hi</p>' in result

    def test_fragment_passthrough(self):
        """HTML fragments without body tag pass through."""
        html = "<p>Just a paragraph</p>"
        result = _extract_body_content(html)
        assert "<p>Just a paragraph</p>" in result

    def test_empty_html(self):
        """Empty string returns empty."""
        assert _extract_body_content("") == ""

    def test_none_html(self):
        """None returns None."""
        assert _extract_body_content(None) is None

    def test_strips_html_wrapper(self):
        """Strip html/head wrappers from fragments without body."""
        html = "<html><head></head><p>Content</p></html>"
        result = _extract_body_content(html)
        assert "<p>Content</p>" in result
        assert "<html>" not in result


class TestToLocalDatetime:
    """Tests for _to_local_datetime."""

    def test_converts_utc_to_local(self):
        """UTC date string is parsed and converted to local timezone."""
        result = _to_local_datetime("Mon, 15 Jan 2024 10:30:00 +0000")
        assert result is not None
        # Should be aware datetime in local timezone
        assert result.tzinfo is not None
        # The underlying instant should be the same
        from datetime import timezone

        assert result.astimezone(timezone.utc).strftime("%H:%M") == "10:30"

    def test_converts_different_timezone(self):
        """Date with explicit timezone is converted to local."""
        result = _to_local_datetime("Mon, 15 Jan 2024 19:30:00 +0900")
        assert result is not None
        from datetime import timezone

        assert result.astimezone(timezone.utc).strftime("%H:%M") == "10:30"

    def test_converts_to_specified_timezone(self):
        """Date is converted to the specified timezone, not local."""
        from zoneinfo import ZoneInfo

        tokyo = ZoneInfo("Asia/Tokyo")  # UTC+9
        result = _to_local_datetime("Mon, 15 Jan 2024 10:30:00 +0000", tokyo)
        assert result is not None
        assert result.strftime("%H:%M") == "19:30"
        assert str(result.tzinfo) == "Asia/Tokyo"

    def test_empty_string_returns_none(self):
        assert _to_local_datetime("") is None

    def test_none_returns_none(self):
        assert _to_local_datetime(None) is None

    def test_invalid_date_returns_none(self):
        assert _to_local_datetime("not a date") is None


class TestFormatDateShort:
    """Tests for _format_date_short."""

    def test_default_format(self):
        """Default format is '%b %d, %Y'."""
        from datetime import datetime, timezone

        dt = datetime(2026, 3, 15, tzinfo=timezone.utc)
        result = _format_date_short(dt)
        assert result == "Mar 15, 2026"

    def test_different_year_same_format(self):
        """Dates in other years use same default format."""
        from datetime import datetime, timezone

        dt = datetime(2020, 6, 5, tzinfo=timezone.utc)
        result = _format_date_short(dt)
        assert result == "Jun 05, 2020"

    def test_custom_format(self):
        """Custom format string is used when provided."""
        from datetime import datetime, timezone

        dt = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        result = _format_date_short(dt, "%Y-%m-%d")
        assert result == "2024-01-15"


class TestFormatDateLong:
    """Tests for _format_date_long."""

    def test_formats_without_timezone(self):
        """Default format does not include timezone."""
        from datetime import datetime, timezone

        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _format_date_long(dt)
        assert result == "Mon, 15 Jan 2024 10:30:00"

    def test_custom_format(self):
        """Custom format string is used when provided."""
        from datetime import datetime, timezone

        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _format_date_long(dt, "%Y-%m-%d %H:%M")
        assert result == "2024-01-15 10:30"


class TestResolveTimezone:
    """Tests for _resolve_timezone."""

    def test_valid_timezone(self):
        from zoneinfo import ZoneInfo

        result = _resolve_timezone("America/New_York")
        assert result == ZoneInfo("America/New_York")

    def test_empty_string_returns_none(self):
        assert _resolve_timezone("") is None

    def test_none_returns_none(self):
        assert _resolve_timezone(None) is None

    def test_invalid_timezone_returns_none(self):
        assert _resolve_timezone("Not/ATimezone") is None


class TestGetServerTimezoneName:
    """Tests for _get_server_timezone_name."""

    def test_returns_non_empty_string(self):
        result = _get_server_timezone_name()
        assert isinstance(result, str)
        assert len(result) > 0


class TestTimezoneSettings:
    """Tests for timezone in settings page and create_app."""

    def test_create_app_default_timezone(self, tmp_path):
        """Default timezone is None (server local)."""
        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        app = create_app(mock_archive)
        assert app.config["timezone"] is None
        assert app.config["timezone_name"] == ""

    def test_create_app_with_timezone(self, tmp_path):
        """Timezone is set when provided."""
        from zoneinfo import ZoneInfo

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        app = create_app(mock_archive, display_timezone="Asia/Tokyo")
        assert app.config["timezone"] == ZoneInfo("Asia/Tokyo")
        assert app.config["timezone_name"] == "Asia/Tokyo"

    def test_settings_page_shows_timezone(self, tmp_path):
        """Settings page shows timezone field with server default."""
        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 0
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/settings")
            assert response.status_code == 200
            assert b"Timezone" in response.data or b"timezone" in response.data

    def test_search_uses_configured_timezone(self, tmp_path):
        """Search results use configured timezone for date display."""
        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        # UTC midnight → Tokyo is +9 hours → still Jan 2
        mock_archive.search.return_value = [
            ("msg1", "test.eml", "Test", "a@b.com", "Thu, 02 Jan 2020 00:00:00 +0000", "snippet")
        ]
        app = create_app(mock_archive, display_timezone="Asia/Tokyo")
        with app.test_client() as client:
            response = client.get("/search?q=test")
            assert response.status_code == 200
            # Tokyo time: Jan 2 00:00 UTC = Jan 2 09:00 JST → still 2020
            assert b"2020" in response.data

    def test_search_passes_timezone_to_archive(self, tmp_path):
        """Search passes configured timezone to archive.search."""
        from zoneinfo import ZoneInfo

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []
        app = create_app(mock_archive, display_timezone="Asia/Tokyo")
        with app.test_client() as client:
            client.get("/search?q=before:2024-01-01")
            mock_archive.search.assert_called_once()
            call_kwargs = mock_archive.search.call_args
            assert call_kwargs.kwargs.get("tz") == ZoneInfo("Asia/Tokyo")


class TestCleanSnippetLxml:
    """Tests for lxml-based HTML stripping in _clean_snippet_text."""

    def test_strips_truncated_tag_at_end(self):
        """Truncated HTML tag at end of string is removed."""
        from ownmail.web import _clean_snippet_text

        text = 'Hello world <meta name="view'
        result = _clean_snippet_text(text)
        assert "<" not in result
        assert "Hello world" in result

    def test_strips_complete_and_partial_tags(self):
        """Both complete and partial HTML tags are stripped."""
        from ownmail.web import _clean_snippet_text

        text = '<p>Hello</p> world <div class="foo'
        result = _clean_snippet_text(text)
        assert "<" not in result
        assert "Hello" in result
        assert "world" in result

    def test_strips_style_and_script_blocks(self):
        """Style and script blocks are fully removed by lxml."""
        from ownmail.web import _clean_snippet_text

        text = "<style>.foo{color:red}</style>Hello<script>alert(1)</script> world"
        result = _clean_snippet_text(text)
        assert "color" not in result
        assert "alert" not in result
        assert "Hello" in result
        assert "world" in result

    def test_plain_text_without_html_unchanged(self):
        """Plain text without HTML tags passes through unchanged."""
        from ownmail.web import _clean_snippet_text

        text = "Just plain text here"
        assert _clean_snippet_text(text) == "Just plain text here"


class TestTrashRoutes:
    """Tests for trash web routes."""

    def test_view_trash_empty(self, tmp_path):
        """Test viewing empty trash."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 10
        mock_archive.db.get_trash_count.return_value = 0
        mock_archive.db.get_trashed_emails.return_value = []
        mock_archive.auto_expire_trash.return_value = 0

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/trash")
            assert response.status_code == 200
            assert b"Trash is empty" in response.data

    def test_view_trash_with_items(self, tmp_path):
        """Test viewing trash with items."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 10
        mock_archive.db.get_trash_count.return_value = 1
        mock_archive.db.get_trashed_emails.return_value = [
            (
                "abc123",
                "trash/abc123.eml",
                "Test Subject",
                "sender@test.com",
                "2024-01-15T10:00:00",
                "This is a snippet...",
                "2024-01-15T10:00:00",
                "sources/gmail/2024/01/test.eml",
            )
        ]
        mock_archive.auto_expire_trash.return_value = 0

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/trash")
            assert response.status_code == 200
            assert b"Test Subject" in response.data

    def test_trash_email_route(self, tmp_path):
        """Test POST /trash/<email_id>."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 10
        mock_archive.db.get_trash_count.return_value = 0
        mock_archive.trash_email.return_value = True
        mock_archive.auto_expire_trash.return_value = 0

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post("/trash/abc123")
            assert response.status_code == 204
            mock_archive.trash_email.assert_called_once_with("abc123")

    def test_restore_email_route(self, tmp_path):
        """Test POST /restore/<email_id>."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 10
        mock_archive.db.get_trash_count.return_value = 0
        mock_archive.restore_email.return_value = True
        mock_archive.auto_expire_trash.return_value = 0

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post("/restore/abc123")
            assert response.status_code == 204
            mock_archive.restore_email.assert_called_once_with("abc123")

    def test_trash_bulk_route(self, tmp_path):
        """Test POST /trash-bulk."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 10
        mock_archive.db.get_trash_count.return_value = 0
        mock_archive.auto_expire_trash.return_value = 0

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post("/trash-bulk", data={"ids": "abc,def"})
            assert response.status_code == 204
            assert mock_archive.trash_email.call_count == 2

    def test_empty_trash_route(self, tmp_path):
        """Test POST /empty-trash."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 10
        mock_archive.db.get_trash_count.return_value = 0
        mock_archive.empty_trash.return_value = 5
        mock_archive.auto_expire_trash.return_value = 0

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post("/empty-trash")
            assert response.status_code == 302  # redirect to /trash
            mock_archive.empty_trash.assert_called_once()

    def test_delete_forever_route(self, tmp_path):
        """Test POST /delete-forever."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 10
        mock_archive.db.get_trash_count.return_value = 0
        mock_archive.auto_expire_trash.return_value = 0

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post("/delete-forever", data={"ids": "abc,def"})
            assert response.status_code == 204
            mock_archive.permanently_delete_emails.assert_called_once_with(["abc", "def"])


class TestServerTimezoneName:
    """Tests for _get_server_timezone_name fallback paths."""

    def test_reads_etc_localtime_symlink(self):
        """A /etc/localtime symlink into zoneinfo/ should yield the zone name."""
        from unittest.mock import patch

        result = MagicMock()
        result.returncode = 0
        result.stdout = "/var/db/timezone/zoneinfo/Asia/Seoul\n"
        with patch("subprocess.run", return_value=result):
            assert _get_server_timezone_name() == "Asia/Seoul"

    def test_falls_back_to_tz_env(self):
        """When readlink fails, the TZ env var should be used."""
        import os
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=OSError("no readlink")):
            with patch.dict(os.environ, {"TZ": "Europe/Paris"}):
                assert _get_server_timezone_name() == "Europe/Paris"

    def test_falls_back_to_utc_offset(self):
        """With no symlink and no TZ, a UTC offset string should be returned."""
        import os
        from unittest.mock import patch

        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        env = {k: v for k, v in os.environ.items() if k != "TZ"}
        with patch("subprocess.run", return_value=result):
            with patch.dict(os.environ, env, clear=True):
                name = _get_server_timezone_name()
        assert name.startswith("UTC")
        assert ":" in name


class TestExtractAttachmentFilenameEncodings:
    """Tests for _extract_attachment_filename CJK decoding paths."""

    def _part(self, raw_header: bytes):
        """Build a message part the way view_email does (policy=default)."""
        from email.policy import default as email_policy

        raw = b"Content-Type: application/octet-stream\r\n" + raw_header + b"\r\n\r\npayload\r\n"
        return email.message_from_bytes(raw, policy=email_policy)

    def test_raw_euc_kr_filename_is_decoded(self):
        """A raw EUC-KR filename= value should decode to Hangul."""
        from ownmail.web import _extract_attachment_filename

        name = "한글.txt".encode("euc-kr")
        part = self._part(b'Content-Disposition: attachment; filename="' + name + b'"')
        assert _extract_attachment_filename(part) == "한글.txt"

    def test_ascii_filename_passes_through(self):
        """A plain ASCII filename should be returned unchanged."""
        from ownmail.web import _extract_attachment_filename

        part = self._part(b'Content-Disposition: attachment; filename="report.pdf"')
        assert _extract_attachment_filename(part) == "report.pdf"

    def test_mime_encoded_filename_is_decoded(self):
        """A MIME encoded-word filename should be decoded."""
        from ownmail.web import _extract_attachment_filename

        part = self._part(b'Content-Disposition: attachment; filename="=?UTF-8?B?7YWM7Iqk7Yq4LnR4dA==?="')
        assert _extract_attachment_filename(part) == "테스트.txt"

    def test_no_filename_returns_default(self):
        """A part with no filename should fall back to 'attachment'."""
        from ownmail.web import _extract_attachment_filename

        part = self._part(b"Content-Disposition: attachment")
        assert _extract_attachment_filename(part) == "attachment"

    def test_rfc2231_encoded_filename(self):
        """An RFC 2231 filename*=charset''value should be decoded."""
        from ownmail.web import _extract_attachment_filename

        part = self._part(b"Content-Disposition: attachment; filename*=UTF-8''%ED%85%8C%EC%8A%A4%ED%8A%B8.txt")
        assert _extract_attachment_filename(part) == "테스트.txt"

    def test_rfc2231_unknown_8bit_treated_as_euc_kr(self):
        """charset unknown-8bit should be decoded as EUC-KR."""
        from ownmail.web import _extract_attachment_filename

        part = self._part(b"Content-Disposition: attachment; filename*=unknown-8bit''%C7%D1%B1%DB.txt")
        assert _extract_attachment_filename(part) == "한글.txt"

    def test_rfc2231_mime_hybrid_continuation(self):
        """RFC 2231 continuations holding MIME encoded-words should be joined."""
        from ownmail.web import _extract_attachment_filename

        part = self._part(
            b'Content-Disposition: attachment; filename*0="=?UTF-8?B?7YWM7Iqk?="; filename*1="=?UTF-8?B?7Yq4?="'
        )
        assert _extract_attachment_filename(part) == "테스트"


class TestBlockExternalImagesCss:
    """Tests for CSS url() blocking in block_external_images."""

    def test_inline_style_background_is_blocked(self):
        """An external url() in a style attribute should be replaced and stashed."""
        html = '<div style="background-image: url(https://tracker.example.com/px.png)">hi</div>'
        result, has_external = block_external_images(html)
        assert has_external is True
        assert "tracker.example.com" not in result.split("data-bg-urls=")[0]
        assert 'data-bg-urls="https://tracker.example.com/px.png"' in result
        assert "url(data:image/gif;base64," in result

    def test_inline_style_without_external_url_untouched(self):
        """A style attribute with no external url() should be left alone."""
        html = '<div style="color: red">hi</div>'
        result, has_external = block_external_images(html)
        assert has_external is False
        assert result == html


class TestCsrfCheck:
    """Tests for the Origin/Referer CSRF guard on POST requests."""

    @pytest.fixture
    def app(self, tmp_path):
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_email_count.return_value = 1
        archive.db.get_trash_count.return_value = 0
        archive.auto_expire_trash.return_value = 0
        archive.trash_email.return_value = True
        return create_app(archive)

    def test_matching_origin_allowed(self, app):
        """A POST whose Origin matches the host should be accepted."""
        with app.test_client() as client:
            response = client.post("/trash/abc", headers={"Origin": "http://localhost"})
            assert response.status_code == 204

    def test_matching_referer_allowed(self, app):
        """A POST whose Referer is under the host URL should be accepted."""
        with app.test_client() as client:
            response = client.post("/trash/abc", headers={"Referer": "http://localhost/search?q=x"})
            assert response.status_code == 204

    def test_foreign_origin_rejected(self, app):
        """A POST from another origin should be rejected with 403."""
        with app.test_client() as client:
            response = client.post("/trash/abc", headers={"Origin": "http://evil.example.com"})
            assert response.status_code == 403

    def test_foreign_referer_rejected(self, app):
        """A POST with a foreign Referer should be rejected with 403."""
        with app.test_client() as client:
            response = client.post("/trash/abc", headers={"Referer": "http://evil.example.com/page"})
            assert response.status_code == 403

    def test_get_request_not_checked(self, app):
        """GET requests should bypass the CSRF check entirely."""
        with app.test_client() as client:
            response = client.get("/search", headers={"Origin": "http://evil.example.com"})
            assert response.status_code == 200


class TestSettingsRoutes:
    """Tests for the settings page and its POST handler."""

    @pytest.fixture
    def archive(self, tmp_path):
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_email_count.return_value = 42
        archive.db.get_trash_count.return_value = 3
        archive.auto_expire_trash.return_value = 0
        return archive

    def test_settings_page_without_config_path(self, archive):
        """Settings page should render defaults when no config path is set."""
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/settings")
            assert response.status_code == 200
            assert b"(not set)" in response.data

    def test_settings_page_reads_config(self, archive, tmp_path):
        """Settings page should show values loaded from config.yaml."""
        config = tmp_path / "config.yaml"
        config.write_text("web:\n  page_size: 77\n  brand_name: MyMail\n")
        app = create_app(archive, config_path=str(config))
        with app.test_client() as client:
            response = client.get("/settings")
            assert response.status_code == 200
            assert b"77" in response.data
            assert b"MyMail" in response.data

    def test_settings_page_unreadable_config(self, archive, tmp_path):
        """An unreadable config should fall back to defaults, not error."""
        app = create_app(archive, config_path=str(tmp_path / "missing.yaml"))
        with app.test_client() as client:
            response = client.get("/settings")
            assert response.status_code == 200

    def test_settings_page_saved_banner(self, archive):
        """?saved=1 should be passed through to the template."""
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/settings?saved=1").status_code == 200

    def test_save_settings_without_config_path_redirects(self, archive):
        """POST with no config path should redirect without writing."""
        app = create_app(archive)
        with app.test_client() as client:
            response = client.post("/settings", data={"page_size": "50"})
            assert response.status_code == 302
            assert response.location == "/settings"
            assert app.config["page_size"] == 20

    def test_save_settings_writes_config(self, archive, tmp_path):
        """POST should persist settings to config.yaml and update app config."""
        from ownmail.yaml_util import load_yaml

        config = tmp_path / "config.yaml"
        config.write_text("web:\n  page_size: 20\n")
        app = create_app(archive, config_path=str(config))
        with app.test_client() as client:
            response = client.post(
                "/settings",
                data={
                    "page_size": "50",
                    "block_images": "on",
                    "auto_scale": "on",
                    "date_format": "%Y-%m-%d",
                    "detail_date_format": "%Y-%m-%d %H:%M",
                    "timezone": "Asia/Seoul",
                    "brand_name": "MyMail",
                    "trusted_senders": "A@Example.com\n\n b@example.com \n",
                },
            )
            assert response.status_code == 302
            assert response.location == "/settings?saved=1"

        assert app.config["page_size"] == 50
        assert app.config["block_images"] is True
        assert app.config["auto_scale"] is True
        assert app.config["date_format"] == "%Y-%m-%d"
        assert app.config["detail_date_format"] == "%Y-%m-%d %H:%M"
        assert app.config["timezone_name"] == "Asia/Seoul"
        assert app.config["brand_name"] == "MyMail"
        assert app.config["trusted_senders"] == {"a@example.com", "b@example.com"}

        saved = load_yaml(config)["web"]
        assert saved["page_size"] == 50
        assert saved["brand_name"] == "MyMail"
        assert saved["trusted_senders"] == ["a@example.com", "b@example.com"]

    def test_save_settings_unchecked_boxes_are_false(self, archive, tmp_path):
        """Omitted checkboxes should store False, not stay at the old value."""
        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config), block_images=True, auto_scale=True)
        with app.test_client() as client:
            client.post("/settings", data={"page_size": "20"})
        assert app.config["block_images"] is False
        assert app.config["auto_scale"] is False

    def test_save_settings_blank_formats_reset_to_none(self, archive, tmp_path):
        """Empty format fields should clear the configured formats."""
        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config), date_format="%x", detail_date_format="%c")
        with app.test_client() as client:
            client.post("/settings", data={"date_format": "", "detail_date_format": ""})
        assert app.config["date_format"] is None
        assert app.config["detail_date_format"] is None

    def test_save_settings_blank_brand_falls_back(self, archive, tmp_path):
        """A blank brand name should fall back to 'ownmail'."""
        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config), brand_name="Custom")
        with app.test_client() as client:
            client.post("/settings", data={"brand_name": "   "})
        assert app.config["brand_name"] == "ownmail"

    @pytest.mark.parametrize(
        ("submitted", "expected"),
        [("0", 1), ("-5", 1), ("9999", 500), ("notanumber", 20), ("", 20)],
    )
    def test_save_settings_clamps_page_size(self, archive, tmp_path, submitted, expected):
        """Page size should be clamped to 1..500, falling back to 20 if invalid."""
        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config))
        with app.test_client() as client:
            client.post("/settings", data={"page_size": submitted})
        assert app.config["page_size"] == expected

    def test_save_settings_unloadable_config_starts_fresh(self, archive, tmp_path):
        """A corrupt config file should be replaced rather than crash the save."""
        config = tmp_path / "config.yaml"
        config.write_text("{{{ not yaml")
        app = create_app(archive, config_path=str(config))
        with app.test_client() as client:
            response = client.post("/settings", data={"page_size": "30"})
            assert response.status_code == 302
        assert app.config["page_size"] == 30

    def test_save_settings_write_failure_is_survivable(self, archive, tmp_path):
        """A failing save_yaml should not break the response."""
        from unittest.mock import patch

        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config), verbose=True)
        with patch("ownmail.yaml_util.save_yaml", side_effect=OSError("read-only")):
            with app.test_client() as client:
                response = client.post("/settings", data={"page_size": "30"})
        assert response.status_code == 302
        assert app.config["page_size"] == 30


class TestTrustedSenderPersistence:
    """Tests for trust/untrust routes writing through to config.yaml."""

    @pytest.fixture
    def archive(self, tmp_path):
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_email_count.return_value = 1
        archive.db.get_trash_count.return_value = 0
        archive.auto_expire_trash.return_value = 0
        return archive

    def test_trust_sender_writes_config(self, archive, tmp_path):
        """Trusting a sender should append it to config.yaml."""
        from ownmail.yaml_util import load_yaml

        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config), verbose=True)
        with app.test_client() as client:
            response = client.post("/trust-sender", data={"email": "New@Example.com", "redirect": "/search"})
            assert response.status_code == 302
        assert "new@example.com" in app.config["trusted_senders"]
        assert load_yaml(config)["web"]["trusted_senders"] == ["new@example.com"]

    def test_trust_sender_is_idempotent(self, archive, tmp_path):
        """Trusting an already-trusted sender should not duplicate the entry."""
        from ownmail.yaml_util import load_yaml

        config = tmp_path / "config.yaml"
        config.write_text("web:\n  trusted_senders:\n    - a@example.com\n")
        app = create_app(archive, config_path=str(config))
        with app.test_client() as client:
            client.post("/trust-sender", data={"email": "a@example.com", "redirect": "/search"})
        assert load_yaml(config)["web"]["trusted_senders"] == ["a@example.com"]

    def test_trust_sender_empty_email_redirects(self, archive):
        """An empty email should redirect without touching the trusted set."""
        app = create_app(archive)
        with app.test_client() as client:
            response = client.post("/trust-sender", data={"email": "  ", "redirect": "/search"})
            assert response.status_code == 302
            assert response.location == "/search"
        assert app.config["trusted_senders"] == set()

    def test_trust_sender_rejects_offsite_redirect(self, archive):
        """An absolute redirect target should be forced back to '/'."""
        app = create_app(archive)
        with app.test_client() as client:
            response = client.post(
                "/trust-sender",
                data={"email": "a@example.com", "redirect": "https://evil.example.com"},
            )
            assert response.status_code == 302
            assert response.location == "/"
        assert "a@example.com" in app.config["trusted_senders"]

    def test_trust_sender_config_error_is_survivable(self, archive, tmp_path):
        """A config write failure should not break the redirect."""
        from unittest.mock import patch

        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config), verbose=True)
        with patch("ownmail.yaml_util.load_yaml", side_effect=OSError("boom")):
            with app.test_client() as client:
                response = client.post("/trust-sender", data={"email": "a@example.com", "redirect": "/search"})
        assert response.status_code == 302

    def test_untrust_sender_writes_config(self, archive, tmp_path):
        """Untrusting a sender should remove it from config.yaml."""
        from ownmail.yaml_util import load_yaml

        config = tmp_path / "config.yaml"
        config.write_text("web:\n  trusted_senders:\n    - a@example.com\n    - b@example.com\n")
        app = create_app(archive, config_path=str(config), trusted_senders=["a@example.com"], verbose=True)
        with app.test_client() as client:
            response = client.post("/untrust-sender", data={"email": "A@Example.com"})
            assert response.get_json() == {"status": "ok"}
        assert "a@example.com" not in app.config["trusted_senders"]
        assert load_yaml(config)["web"]["trusted_senders"] == ["b@example.com"]

    def test_untrust_sender_empty_email_errors(self, archive):
        """An empty email should return an error payload."""
        app = create_app(archive)
        with app.test_client() as client:
            response = client.post("/untrust-sender", data={"email": ""})
            assert response.get_json()["status"] == "error"

    def test_untrust_sender_config_error_is_survivable(self, archive, tmp_path):
        """A config read failure should still report ok."""
        from unittest.mock import patch

        config = tmp_path / "config.yaml"
        config.write_text("web: {}\n")
        app = create_app(archive, config_path=str(config), verbose=True)
        with patch("ownmail.yaml_util.load_yaml", side_effect=OSError("boom")):
            with app.test_client() as client:
                response = client.post("/untrust-sender", data={"email": "a@example.com"})
        assert response.get_json() == {"status": "ok"}


class TestViewTrash:
    """Tests for the /trash listing route."""

    @pytest.fixture
    def archive(self, tmp_path):
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_email_count.return_value = 5
        archive.db.get_trash_count.return_value = 2
        archive.auto_expire_trash.return_value = 0
        return archive

    def test_renders_rows_with_decoded_headers(self, archive):
        """MIME-encoded subject/sender/snippet should be decoded for display."""
        archive.db.get_trashed_emails.return_value = [
            (
                "id1",
                "f1.eml",
                "=?UTF-8?B?7YWM7Iqk7Yq4?=",
                "=?UTF-8?B?7YWM7Iqk7Yq4?= <k@example.com>",
                "Mon, 1 Jan 2024 10:00:00 +0000",
                "=?UTF-8?B?7YWM7Iqk7Yq4?=",
                "2024-01-02",
                "orig.eml",
            )
        ]
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/trash")
            assert response.status_code == 200
            assert "테스트".encode() in response.data
            assert b"=?UTF-8?B?" not in response.data

    def test_missing_subject_and_date(self, archive):
        """A row with no subject or date should render placeholders."""
        archive.db.get_trashed_emails.return_value = [("id2", "f2.eml", "", "", "", "", "2024-01-02", "orig.eml")]
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/trash")
            assert response.status_code == 200
            assert b"(No subject)" in response.data

    def test_unparseable_date_falls_back_to_first_token(self, archive):
        """A date that can't be parsed should degrade to its first token."""
        archive.db.get_trashed_emails.return_value = [
            ("id3", "f3.eml", "Subj", "a@example.com", "20240101 garbage", "snip", "2024-01-02", "orig.eml")
        ]
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/trash")
            assert response.status_code == 200
            assert b"20240101" in response.data


class TestRunServer:
    """Tests for run_server startup, guards and teardown."""

    @pytest.fixture
    def archive(self, tmp_path):
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_email_count.return_value = 1
        archive.db.get_trash_count.return_value = 0
        archive.auto_expire_trash.return_value = 0
        return archive

    @pytest.fixture
    def sanitizer(self):
        """A stand-in HtmlSanitizer that reports itself as available."""
        san = MagicMock()
        san.available = True
        return san

    def _patches(self, sanitizer):
        from unittest.mock import patch

        return (
            patch("ownmail.sanitizer.HtmlSanitizer", return_value=sanitizer),
            patch("flask.Flask.run"),
            patch("webbrowser.open"),
        )

    def test_starts_and_stops_sanitizer(self, archive, sanitizer):
        """The server should start the sanitizer and stop it on exit."""
        from ownmail.web import run_server

        san_patch, run_patch, _ = self._patches(sanitizer)
        with san_patch, run_patch as mock_run:
            run_server(archive, open_browser=False)
        sanitizer.start.assert_called_once()
        sanitizer.stop.assert_called_once()
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["host"] == "127.0.0.1"
        assert mock_run.call_args.kwargs["port"] == 8080

    def test_stops_sanitizer_when_app_run_raises(self, archive, sanitizer):
        """A crash inside app.run must still stop the sanitizer."""
        from ownmail.web import run_server

        san_patch, run_patch, _ = self._patches(sanitizer)
        with san_patch, run_patch as mock_run:
            mock_run.side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                run_server(archive, open_browser=False)
        sanitizer.stop.assert_called_once()

    def test_refuses_to_serve_without_sanitizer(self, archive, sanitizer, capsys):
        """An unavailable sanitizer should abort startup before app.run."""
        from ownmail.web import run_server

        sanitizer.available = False
        san_patch, run_patch, _ = self._patches(sanitizer)
        with san_patch, run_patch as mock_run:
            run_server(archive, open_browser=False)
        mock_run.assert_not_called()
        assert "Refusing to serve without sanitization" in capsys.readouterr().out

    def test_debug_with_public_host_is_refused(self, archive, sanitizer, capsys):
        """--debug on a non-localhost host must not start the server."""
        from ownmail.web import run_server

        san_patch, run_patch, _ = self._patches(sanitizer)
        with san_patch, run_patch as mock_run:
            run_server(archive, host="0.0.0.0", debug=True, open_browser=False)
        mock_run.assert_not_called()
        sanitizer.stop.assert_called_once()
        out = capsys.readouterr().out
        assert "remote code execution" in out

    def test_public_host_warns(self, archive, sanitizer, capsys):
        """Binding to a public host should print a network exposure warning."""
        from ownmail.web import run_server

        san_patch, run_patch, _ = self._patches(sanitizer)
        with san_patch, run_patch:
            run_server(archive, host="0.0.0.0", open_browser=False)
        assert "WARNING: Binding to non-localhost address" in capsys.readouterr().out

    def test_verbose_and_block_images_notices(self, archive, sanitizer, capsys):
        """Verbose, image-blocking and trusted-sender notices should print."""
        from ownmail.web import run_server

        san_patch, run_patch, _ = self._patches(sanitizer)
        with san_patch, run_patch:
            run_server(
                archive,
                verbose=True,
                block_images=True,
                trusted_senders=["a@example.com"],
                open_browser=False,
            )
        out = capsys.readouterr().out
        assert "Verbose logging enabled" in out
        assert "External images blocked by default" in out
        assert "Trusted senders: 1" in out

    def test_opens_browser_when_requested(self, archive, sanitizer):
        """open_browser should schedule a webbrowser.open on the bound host."""
        from unittest.mock import patch

        from ownmail.web import run_server

        san_patch, run_patch, browser_patch = self._patches(sanitizer)
        with san_patch, run_patch, browser_patch as mock_open:
            with patch("threading.Timer") as mock_timer:
                run_server(archive, port=9999, open_browser=True)
                mock_timer.assert_called_once()
                # Invoke the scheduled callback directly rather than waiting.
                mock_timer.call_args.args[1]()
        mock_open.assert_called_once_with("http://127.0.0.1:9999")

    def test_wildcard_host_maps_to_localhost_url(self, archive, sanitizer):
        """A 0.0.0.0 bind should open localhost, not the wildcard address."""
        from unittest.mock import patch

        from ownmail.web import run_server

        san_patch, run_patch, browser_patch = self._patches(sanitizer)
        with san_patch, run_patch, browser_patch as mock_open:
            with patch("threading.Timer") as mock_timer:
                run_server(archive, host="0.0.0.0", port=8080, open_browser=True)
                mock_timer.call_args.args[1]()
        mock_open.assert_called_once_with("http://localhost:8080")

    def test_debug_reloader_parent_does_not_open_browser(self, archive, sanitizer):
        """Under the Werkzeug reloader parent process, no browser should open."""
        import os
        from unittest.mock import patch

        from ownmail.web import run_server

        san_patch, run_patch, _ = self._patches(sanitizer)
        env = {k: v for k, v in os.environ.items() if k != "WERKZEUG_RUN_MAIN"}
        with san_patch, run_patch:
            with patch.dict(os.environ, env, clear=True):
                with patch("threading.Timer") as mock_timer:
                    run_server(archive, debug=True, open_browser=True)
        mock_timer.assert_not_called()


class TestViewEmailRendering:
    """Tests for /email/<id> against real .eml files on disk."""

    @pytest.fixture
    def archive(self, tmp_path):
        """A mock archive backed by a real directory of .eml files."""
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_email_count.return_value = 1
        archive.db.get_trash_count.return_value = 0
        archive.db.get_labels_for_email.return_value = []
        archive.auto_expire_trash.return_value = 0
        return archive

    def _store(self, archive, raw, name="mail.eml", trashed_at=None):
        """Write `raw` to the archive dir and wire up the DB lookup."""
        (archive.archive_dir / name).write_bytes(raw)
        archive.db.get_email_by_id.return_value = ("id1", name, "2024-01-01", "hash", "a@example.com", trashed_at)
        return name

    def test_plain_text_email(self, archive):
        """A simple text email should render its subject, sender and body."""
        self._store(
            archive,
            b"From: Alice <alice@example.com>\r\nTo: bob@example.com\r\n"
            b"Subject: Hello\r\nDate: Mon, 1 Jan 2024 10:00:00 +0000\r\n\r\n"
            b"This is the body text.\r\n",
        )
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/email/id1")
        assert response.status_code == 200
        assert b"Hello" in response.data
        assert b"alice@example.com" in response.data
        assert b"This is the body text." in response.data

    def test_missing_file_is_404(self, archive):
        """A DB row whose file is gone should 404 rather than error."""
        archive.db.get_email_by_id.return_value = ("id1", "gone.eml", "d", "h", "a@example.com", None)
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/email/id1").status_code == 404

    def test_mime_encoded_headers_are_decoded(self, archive):
        """Encoded-word subject and sender should be decoded for display."""
        self._store(
            archive,
            b"From: =?UTF-8?B?7YWM7Iqk7Yq4?= <k@example.com>\r\n"
            b"Subject: =?UTF-8?B?7YWM7Iqk7Yq4?=\r\n"
            b"Date: Mon, 1 Jan 2024 10:00:00 +0000\r\n\r\nbody\r\n",
        )
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/email/id1")
        assert "테스트".encode() in response.data
        assert b"=?UTF-8?B?" not in response.data

    def test_html_body_preferred_over_plain_text(self, archive):
        """When both parts exist, the HTML alternative should win."""
        raw = (
            b"From: a@example.com\r\nSubject: Multi\r\n"
            b"Date: Mon, 1 Jan 2024 10:00:00 +0000\r\n"
            b'MIME-Version: 1.0\r\nContent-Type: multipart/alternative; boundary="b1"\r\n\r\n'
            b"--b1\r\nContent-Type: text/plain\r\n\r\nplain version\r\n"
            b"--b1\r\nContent-Type: text/html\r\n\r\n<p>html version</p>\r\n"
            b"--b1--\r\n"
        )
        self._store(archive, raw)
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/email/id1")
        assert b"html version" in response.data

    def test_attachments_are_listed(self, archive):
        """An attachment part should appear with its name and size."""
        raw = (
            b"From: a@example.com\r\nSubject: With attachment\r\n"
            b"Date: Mon, 1 Jan 2024 10:00:00 +0000\r\n"
            b'MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="b1"\r\n\r\n'
            b"--b1\r\nContent-Type: text/plain\r\n\r\nsee attached\r\n"
            b"--b1\r\nContent-Type: application/pdf\r\n"
            b'Content-Disposition: attachment; filename="report.pdf"\r\n\r\n'
            b"PDFDATA\r\n--b1--\r\n"
        )
        self._store(archive, raw)
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/email/id1")
        assert b"report.pdf" in response.data

    def test_embedded_digest_message_is_rendered(self, archive):
        """A message/rfc822 part should be surfaced as a digest entry."""
        raw = (
            b"From: list@example.com\r\nSubject: Digest\r\n"
            b"Date: Mon, 1 Jan 2024 10:00:00 +0000\r\n"
            b'MIME-Version: 1.0\r\nContent-Type: multipart/digest; boundary="b1"\r\n\r\n'
            b"--b1\r\nContent-Type: message/rfc822\r\n\r\n"
            b"From: inner@example.com\r\nSubject: Inner subject\r\n"
            b"To: list@example.com\r\nReply-To: inner@example.com\r\n"
            b"Date: Mon, 1 Jan 2024 09:00:00 +0000\r\n"
            b"Content-Type: text/plain\r\n\r\ninner body text\r\n"
            b"--b1--\r\n"
        )
        self._store(archive, raw)
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/email/id1")
        assert b"inner@example.com" in response.data
        assert b"Inner subject" in response.data
        assert b"inner body text" in response.data

    def test_labels_are_shown(self, archive):
        """Labels from the database should render on the page."""
        self._store(archive, b"From: a@example.com\r\nSubject: S\r\n\r\nbody\r\n")
        archive.db.get_labels_for_email.return_value = ["Work", "Important"]
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/email/id1")
        assert b"Work" in response.data
        assert b"Important" in response.data

    def test_trashed_email_renders(self, archive):
        """A trashed email should still be viewable."""
        self._store(archive, b"From: a@example.com\r\nSubject: S\r\n\r\nbody\r\n", trashed_at="2024-02-01")
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/email/id1").status_code == 200

    def test_verbose_logs_timings(self, archive, capsys):
        """Verbose mode should print lookup and parse timings."""
        self._store(archive, b"From: a@example.com\r\nSubject: S\r\n\r\nbody\r\n")
        app = create_app(archive, verbose=True)
        with app.test_client() as client:
            client.get("/email/id1")
        out = capsys.readouterr().out
        assert "DB lookup took" in out
        assert "Email parsing took" in out


class TestRawAndDownloadRoutes:
    """Tests for /raw, /download and /attachment."""

    @pytest.fixture
    def archive(self, tmp_path):
        archive = MagicMock()
        archive.archive_dir = tmp_path
        archive.db = MagicMock()
        archive.db.get_email_count.return_value = 1
        archive.db.get_trash_count.return_value = 0
        archive.auto_expire_trash.return_value = 0
        return archive

    ATTACHMENT_EML = (
        b"From: a@example.com\r\nSubject: With attachment\r\n"
        b'MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="b1"\r\n\r\n'
        b"--b1\r\nContent-Type: text/plain\r\n\r\nsee attached\r\n"
        b"--b1\r\nContent-Type: application/pdf\r\n"
        b'Content-Disposition: attachment; filename="report.pdf"\r\n\r\n'
        b"PDFDATA\r\n--b1--\r\n"
    )

    def _store(self, archive, raw, name="mail.eml"):
        (archive.archive_dir / name).write_bytes(raw)
        archive.db.get_email_by_id.return_value = ("id1", name, "2024-01-01", "hash", "a@example.com", None)

    def test_raw_shows_source(self, archive):
        """The raw view should show the file path and message source."""
        self._store(archive, b"From: a@example.com\r\nSubject: Raw test\r\n\r\nbody\r\n")
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/raw/id1")
        assert response.status_code == 200
        assert b"Subject: Raw test" in response.data
        assert b"mail.eml" in response.data

    def test_raw_unknown_id_is_404(self, archive):
        """An unknown email id should 404."""
        archive.db.get_email_by_id.return_value = None
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/raw/nope").status_code == 404

    def test_raw_missing_file_is_404(self, archive):
        """A missing file should 404 rather than raise."""
        archive.db.get_email_by_id.return_value = ("id1", "gone.eml", "d", "h", "a@example.com", None)
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/raw/id1").status_code == 404

    def test_raw_rejects_path_traversal(self, archive, tmp_path):
        """A filename escaping the archive dir must be refused."""
        outside = tmp_path.parent / "outside.eml"
        outside.write_bytes(b"secret")
        archive.db.get_email_by_id.return_value = (
            "id1",
            f"../{outside.name}",
            "d",
            "h",
            "a@example.com",
            None,
        )
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/raw/id1").status_code == 404

    def test_download_returns_eml(self, archive):
        """The download route should return the .eml as an attachment."""
        self._store(archive, b"From: a@example.com\r\nSubject: D\r\n\r\nbody\r\n")
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/download/id1")
        assert response.status_code == 200
        assert b"Subject: D" in response.data
        assert "attachment" in response.headers["Content-Disposition"]

    def test_download_unknown_id_is_404(self, archive):
        """An unknown id should 404."""
        archive.db.get_email_by_id.return_value = None
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/download/nope").status_code == 404

    def test_attachment_download(self, archive):
        """The attachment route should return the decoded payload."""
        self._store(archive, self.ATTACHMENT_EML)
        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/attachment/id1/0")
        assert response.status_code == 200
        assert response.data == b"PDFDATA"
        assert "report.pdf" in response.headers["Content-Disposition"]

    def test_attachment_index_out_of_range_is_404(self, archive):
        """An index past the last attachment should 404."""
        self._store(archive, self.ATTACHMENT_EML)
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/attachment/id1/5").status_code == 404

    def test_attachment_unknown_id_is_404(self, archive):
        """An unknown email id should 404."""
        archive.db.get_email_by_id.return_value = None
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/attachment/nope/0").status_code == 404

    def test_attachment_missing_file_is_404(self, archive):
        """A missing .eml file should 404."""
        archive.db.get_email_by_id.return_value = ("id1", "gone.eml", "d", "h", "a@example.com", None)
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/attachment/id1/0").status_code == 404

    def test_attachment_rejects_path_traversal(self, archive, tmp_path):
        """A filename escaping the archive dir must be refused."""
        outside = tmp_path.parent / "outside2.eml"
        outside.write_bytes(b"secret")
        archive.db.get_email_by_id.return_value = ("id1", f"../{outside.name}", "d", "h", "a@example.com", None)
        app = create_app(archive)
        with app.test_client() as client:
            assert client.get("/attachment/id1/0").status_code == 404


class TestCleanSnippetText:
    """Tests for _clean_snippet_text."""

    def test_strips_leading_mime_headers(self):
        """MIME headers leaked into the body should be removed."""
        from ownmail.web import _clean_snippet_text

        text = "Content-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: 7bit\nReal body here"
        assert _clean_snippet_text(text) == "Real body here"

    def test_strips_html_tags(self):
        """HTML tags should be removed, keeping visible text."""
        from ownmail.web import _clean_snippet_text

        assert _clean_snippet_text("<p>Hello <b>World</b></p>") == "Hello World"

    def test_drops_style_and_script_but_keeps_tail_text(self):
        """Text after a removed element must not be lost."""
        from ownmail.web import _clean_snippet_text

        result = _clean_snippet_text("<div><style>p{color:red}</style>Visible text</div>")
        assert "Visible text" in result
        assert "color:red" not in result

    def test_removes_zero_width_padding(self):
        """Invisible preheader padding should be stripped."""
        from ownmail.web import _clean_snippet_text

        assert _clean_snippet_text("Real​‌‍﻿ text") == "Real text"

    def test_regex_fallback_when_lxml_fails(self):
        """If lxml raises, tags should still be stripped by regex."""
        from unittest.mock import patch

        from ownmail.web import _clean_snippet_text

        with patch("lxml.html.fromstring", side_effect=ValueError("bad")):
            result = _clean_snippet_text("<style>x{}</style><script>y</script><p>Hello</p>")
        assert "Hello" in result
        assert "<p>" not in result

    def test_empty_input(self):
        """Empty text should stay empty."""
        from ownmail.web import _clean_snippet_text

        assert _clean_snippet_text("") == ""


class TestLinkify:
    """Tests for _linkify."""

    def test_urls_become_links(self):
        """A bare URL should be wrapped in an anchor."""
        from ownmail.web import _linkify

        result = _linkify("Visit https://example.com/page today")
        assert '<a href="https://example.com/page"' in result
        assert 'rel="noopener noreferrer"' in result

    def test_emails_become_mailto_links(self):
        """A bare email address should become a mailto link."""
        from ownmail.web import _linkify

        assert '<a href="mailto:alice@example.com"' in _linkify("Contact alice@example.com now")

    @pytest.mark.xfail(strict=True, reason="TASK-13: nested anchor inside href")
    def test_email_inside_url_is_not_double_linked(self):
        """An address already inside a link href must not be re-linked."""
        from ownmail.web import _linkify

        result = _linkify("https://example.com/unsubscribe?email=alice@example.com")
        assert "mailto:" not in result

    def test_html_is_escaped(self):
        """Raw HTML in the text must be escaped, not emitted."""
        from ownmail.web import _linkify

        result = _linkify("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_quoted_lines_are_marked_up(self):
        """Quote levels should be rendered rather than left as raw '>'."""
        from ownmail.web import _linkify

        result = _linkify("> quoted reply\nnormal line")
        assert "quoted reply" in result
        assert "normal line" in result
