"""Tests for web interface."""

import email
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ownmail.web import (
    LRUCache,
    block_external_images,
    create_app,
    decode_header,
    parse_email_address,
    parse_recipients,
    _extract_snippet,
    _format_size,
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
        """Index route should return 200."""
        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/")
            assert response.status_code == 200
            assert b"ownmail" in response.data

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
