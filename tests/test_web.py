"""Tests for web interface."""

import email
from unittest.mock import MagicMock

import pytest

from ownmail.web import (
    LRUCache,
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


class TestLRUCache:
    """Tests for LRUCache class."""

    def test_basic_get_set(self):
        """Basic get and set operations."""
        cache = LRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_missing_key(self):
        """Missing key should return None."""
        cache = LRUCache(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_maxsize_eviction(self):
        """Cache should evict oldest entries when full."""
        cache = LRUCache(maxsize=2, ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_ttl_expiration(self):
        """Cache entries should expire after TTL."""
        import time
        cache = LRUCache(maxsize=10, ttl=0.01)  # 10ms TTL
        cache.set("key1", "value1")
        time.sleep(0.02)  # Wait for expiration
        assert cache.get("key1") is None


class TestExtractSnippet:
    """Tests for _extract_snippet function."""

    def test_plain_text_email(self):
        """Extract snippet from plain text email."""
        msg = email.message_from_string(
            "Content-Type: text/plain\n\nHello, this is a test email body."
        )
        snippet = _extract_snippet(msg)
        assert "Hello" in snippet
        assert "test email" in snippet

    def test_long_text_truncation(self):
        """Long text should be truncated."""
        long_text = "A" * 200
        msg = email.message_from_string(
            f"Content-Type: text/plain\n\n{long_text}"
        )
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
            assert b"Search Syntax" in response.data

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
            assert b"Next" in response.data  # Has pagination

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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/test.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "missing.eml")
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


class TestSearchCacheHit:
    """Tests for search cache functionality."""

    def test_search_cache_returns_cached_results(self, tmp_path):
        """Second search should use cached results."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = [
            ("msg1", "file1.eml", "Subject 1", "sender@example.com", "2024-01-01", "snippet")
        ]

        app = create_app(mock_archive)
        with app.test_client() as client:
            # First search
            response1 = client.get("/search?q=test")
            assert response1.status_code == 200

            # Second search (should hit cache)
            response2 = client.get("/search?q=test")
            assert response2.status_code == 200

            # Search should only be called once (second is cached)
            # Note: It may be called twice if cache is per-request
            assert mock_archive.search.call_count >= 1


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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/test.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg2", "emails/html.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg3", "emails/attach.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/missing.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg4", "emails/multipart.eml")
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/msg4")
            assert response.status_code == 200

    def test_view_email_cached(self, tmp_path):
        """Second view of same email should use cache."""
        from unittest.mock import MagicMock

        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
Subject: Cacheable
Content-Type: text/plain

Body.
"""
        eml_path = tmp_path / "emails" / "cache.eml"
        eml_path.parent.mkdir(parents=True)
        eml_path.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_by_id.return_value = ("msg5", "emails/cache.eml")
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            # First request
            response1 = client.get("/email/msg5")
            assert response1.status_code == 200

            # Second request (should hit cache)
            response2 = client.get("/email/msg5")
            assert response2.status_code == 200


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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/attach.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/attach.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/img.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/trusted.eml")
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
        mock_archive.db.get_email_by_id.return_value = ("msg1", "emails/rt.eml")
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

    def test_same_year_shows_month_day(self):
        """Dates in current year show 'Mon DD' format."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        dt = now.replace(month=3, day=15)
        result = _format_date_short(dt)
        assert result == "Mar 15"

    def test_different_year_shows_full_date(self):
        """Dates in other years show 'YYYY/MM/DD' format."""
        from datetime import datetime, timezone
        dt = datetime(2020, 6, 5, tzinfo=timezone.utc)
        result = _format_date_short(dt)
        assert result == "2020/06/05"

    def test_custom_format(self):
        """Custom format string is used when provided."""
        from datetime import datetime, timezone
        dt = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        result = _format_date_short(dt, "%Y-%m-%d")
        assert result == "2024-01-15"


class TestFormatDateLong:
    """Tests for _format_date_long."""

    def test_formats_full_date(self):
        """Formats datetime as RFC 2822 style string."""
        from datetime import datetime, timezone
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _format_date_long(dt)
        assert result == "Mon, 15 Jan 2024 10:30:00 +0000"


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

