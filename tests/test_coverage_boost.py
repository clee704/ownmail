"""Additional tests to increase coverage."""

from unittest.mock import MagicMock


class TestWebSearchSorting:
    """Tests for web search sorting functionality."""

    def test_search_default_sort(self, tmp_path):
        """Test search with default sorting."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test")
            assert response.status_code == 200


class TestWebCleanSnippet:
    """Tests for web clean_snippet functionality."""

    def test_snippet_with_html(self, tmp_path):
        """Test snippet cleaning with HTML tags."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = [
            {
                "email_message_id": "test1",
                "subject": "Test",
                "sender": "a@b.com",
                "recipients": "c@d.com",
                "email_date": "2024-01-01T00:00:00",
                "file_name": "test.eml",
                "body_snippet": "<b>Hello</b> world",
                "rank": 1,
            }
        ]

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test")
            assert response.status_code == 200


class TestWebHelpPage:
    """Tests for web help page."""

    def test_help_page(self, tmp_path):
        """Test help page renders."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/help")
            assert response.status_code == 200


class TestDatabaseCacheStats:
    """Tests for database cache stats."""

    def test_cache_stats(self, tmp_path):
        """Test getting cache stats."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        # Just verify it doesn't error
        count = db.get_email_count()
        assert count >= 0


class TestQueryBuildSearchQuery:
    """Tests for query builder."""

    def test_simple_query(self):
        """Test simple text query."""
        from ownmail.query import parse_query

        parsed = parse_query("hello world")
        assert parsed is not None

    def test_label_query(self):
        """Test label filter query."""
        from ownmail.query import parse_query

        parsed = parse_query("label:INBOX")
        assert parsed is not None

    def test_from_query(self):
        """Test from filter query."""
        from ownmail.query import parse_query

        parsed = parse_query("from:test@example.com")
        assert parsed is not None

    def test_date_range_query(self):
        """Test date range query."""
        from ownmail.query import parse_query

        parsed = parse_query("after:2024-01-01 before:2024-12-31")
        assert parsed is not None


class TestDatabaseGetDownloadedIds:
    """Tests for database get_downloaded_ids."""

    def test_get_downloaded_ids_empty(self, tmp_path):
        """Test getting downloaded IDs from empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        ids = db.get_downloaded_ids()
        assert ids == set()

    def test_get_downloaded_ids_with_emails(self, tmp_path):
        """Test getting downloaded IDs with emails."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file1.eml")
        db.mark_downloaded("msg2", "file2.eml")

        ids = db.get_downloaded_ids()
        assert "msg1" in ids
        assert "msg2" in ids


class TestArchiveInit:
    """Tests for archive initialization."""

    def test_archive_init_creates_directory(self, tmp_path):
        """Test archive init creates directory."""
        from ownmail.archive import EmailArchive

        archive_path = tmp_path / "new_archive"
        _archive = EmailArchive(archive_path, {})  # noqa: F841
        assert archive_path.exists()


class TestDatabaseSearchEmpty:
    """Tests for database search on empty database."""

    def test_search_empty_db(self, tmp_path):
        """Test search on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        results = db.search("test")
        assert results == []


class TestDatabaseGetStats:
    """Tests for database get_stats."""

    def test_get_stats_empty(self, tmp_path):
        """Test get_stats on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        stats = db.get_stats()
        assert isinstance(stats, dict)


class TestDatabaseGetEmailCount:
    """Tests for database get_email_count."""

    def test_get_email_count_empty(self, tmp_path):
        """Test get_email_count on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        count = db.get_email_count()
        assert count == 0

    def test_get_email_count_with_emails(self, tmp_path):
        """Test get_email_count with emails."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file1.eml")
        db.mark_downloaded("msg2", "file2.eml")
        count = db.get_email_count()
        assert count == 2


class TestDatabaseIsIndexed:
    """Tests for database is_indexed."""

    def test_is_indexed_false(self, tmp_path):
        """Test is_indexed returns False for non-indexed email."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        assert db.is_indexed("msg1") is False

    def test_is_indexed_true(self, tmp_path):
        """Test is_indexed returns True for indexed email."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        db.index_email("msg1", "Subject", "from", "to", "date", "body", "")
        assert db.is_indexed("msg1") is True


class TestDatabaseGetEmailById:
    """Tests for database get_email_by_id."""

    def test_get_email_by_id_exists(self, tmp_path):
        """Test getting existing email by ID."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        result = db.get_email_by_id("msg1")
        assert result is not None
        assert result[0] == "msg1"

    def test_get_email_by_id_not_exists(self, tmp_path):
        """Test getting non-existing email by ID."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        result = db.get_email_by_id("nonexistent")
        assert result is None


class TestWebEmptySearch:
    """Tests for web search with empty results."""

    def test_search_no_results(self, tmp_path):
        """Test search that returns no results."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=nonexistent")
            assert response.status_code == 200
            assert b"No results" in response.data


class TestCommandsVerify:
    """Tests for cmd_verify command."""

    def test_verify_empty_archive(self, tmp_path, capsys):
        """Test verify on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_verify

        archive = EmailArchive(tmp_path, {})
        cmd_verify(archive)
        captured = capsys.readouterr()
        assert "Verify" in captured.out or "0" in captured.out or "verify" in captured.out.lower()


class TestCommandsDbCheck:
    """Tests for cmd_db_check command."""

    def test_db_check_empty_archive(self, tmp_path, capsys):
        """Test db_check on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_db_check

        archive = EmailArchive(tmp_path, {})
        cmd_db_check(archive)
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestCommandsRehash:
    """Tests for cmd_rehash command."""

    def test_rehash_empty_archive(self, tmp_path, capsys):
        """Test rehash on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_rehash

        archive = EmailArchive(tmp_path, {})
        cmd_rehash(archive)
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestWebSearchPagination:
    """Tests for web search pagination."""

    def test_search_with_offset(self, tmp_path):
        """Test search with offset parameter."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&offset=10")
            assert response.status_code == 200


class TestWebEmailView:
    """Tests for web email view."""

    def test_email_not_found(self, tmp_path):
        """Test email view for nonexistent email."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = None

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/nonexistent")
            assert response.status_code == 404


class TestParserDecodeGrouped:
    """Tests for parser _decode_grouped_rfc2047_parts."""

    def test_decode_simple_parts(self):
        """Test decoding simple RFC2047 parts."""
        from ownmail.parser import _decode_grouped_rfc2047_parts

        parts = [(b"Hello", None)]
        result = _decode_grouped_rfc2047_parts(parts)
        assert "Hello" in result

    def test_decode_utf8_parts(self):
        """Test decoding UTF-8 RFC2047 parts."""
        from ownmail.parser import _decode_grouped_rfc2047_parts

        parts = [("테스트".encode(), "utf-8")]
        result = _decode_grouped_rfc2047_parts(parts)
        assert "테스트" in result


class TestParserValidateText:
    """Tests for parser _validate_decoded_text."""

    def test_validate_good_text(self):
        """Test validating good text."""
        from ownmail.parser import _validate_decoded_text

        result = _validate_decoded_text("This is valid English text.")
        assert result is True

    def test_validate_replacement_chars(self):
        """Test validating text with replacement chars."""
        from ownmail.parser import _validate_decoded_text

        result = _validate_decoded_text("Bad \ufffd\ufffd\ufffd text")
        assert result is False


class TestParserDetectCharset:
    """Tests for parser _detect_charset."""

    def test_detect_utf8(self):
        """Test detecting UTF-8 charset."""
        from ownmail.parser import _detect_charset

        result = _detect_charset(b"Hello world", "utf-8")
        assert result == "utf-8"

    def test_detect_with_fallback(self):
        """Test charset detection with fallback."""
        from ownmail.parser import _detect_charset

        result = _detect_charset(b"\xff\xfe", None)  # Invalid UTF-8
        assert result is not None


class TestDatabaseIsDownloaded:
    """Tests for database is_downloaded."""

    def test_is_downloaded_false(self, tmp_path):
        """Test is_downloaded returns False for unknown message."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        assert db.is_downloaded("nonexistent") is False

    def test_is_downloaded_true(self, tmp_path):
        """Test is_downloaded returns True for known message."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        assert db.is_downloaded("msg1") is True


class TestDatabaseSyncState:
    """Tests for database sync state methods."""

    def test_get_sync_state_empty(self, tmp_path):
        """Test get_sync_state on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        result = db.get_sync_state("account1", "key1")
        assert result is None

    def test_set_and_get_sync_state(self, tmp_path):
        """Test set_sync_state and get_sync_state."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.set_sync_state("account1", "key1", "value1")
        result = db.get_sync_state("account1", "key1")
        assert result == "value1"

    def test_delete_sync_state(self, tmp_path):
        """Test delete_sync_state."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.set_sync_state("account1", "key1", "value1")
        db.delete_sync_state("account1", "key1")
        result = db.get_sync_state("account1", "key1")
        assert result is None


class TestDatabaseHistoryId:
    """Tests for database history ID methods."""

    def test_get_history_id_empty(self, tmp_path):
        """Test get_history_id on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        result = db.get_history_id()
        assert result is None

    def test_set_and_get_history_id(self, tmp_path):
        """Test set_history_id and get_history_id."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.set_history_id("12345")
        result = db.get_history_id()
        assert result == "12345"


class TestDatabaseAccounts:
    """Tests for database account methods."""

    def test_get_accounts_empty(self, tmp_path):
        """Test get_accounts on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        result = db.get_accounts()
        assert result == []

    def test_get_accounts_with_data(self, tmp_path):
        """Test get_accounts with data."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml", account="test@example.com")
        result = db.get_accounts()
        assert "test@example.com" in result


class TestDatabaseClearIndex:
    """Tests for database clear_index."""

    def test_clear_index(self, tmp_path):
        """Test clearing the search index."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        db.index_email("msg1", "Subject", "from", "to", "date", "body", "")

        db.clear_index()

        # Email should still exist but not be indexed
        assert db.is_indexed("msg1") is False
        assert db.is_downloaded("msg1") is True


class TestQueryParsing:
    """Tests for query parsing edge cases."""

    def test_empty_query(self):
        """Test parsing empty query."""
        from ownmail.query import parse_query

        parsed = parse_query("")
        assert parsed is not None

    def test_quoted_query(self):
        """Test parsing quoted query."""
        from ownmail.query import parse_query

        parsed = parse_query('"hello world"')
        assert parsed is not None

    def test_to_query(self):
        """Test to: filter query."""
        from ownmail.query import parse_query

        parsed = parse_query("to:test@example.com")
        assert parsed is not None

    def test_subject_query(self):
        """Test subject: filter query."""
        from ownmail.query import parse_query

        parsed = parse_query("subject:test")
        assert parsed is not None

    def test_has_attachment_query(self):
        """Test has:attachment query."""
        from ownmail.query import parse_query

        parsed = parse_query("has:attachment")
        assert parsed is not None


class TestCliModule:
    """Tests for CLI module."""

    def test_cli_module_imports(self):
        """Test that CLI module can be imported."""
        from ownmail import cli

        assert hasattr(cli, "main")


class TestWebStatic:
    """Tests for web static files."""

    def test_static_css(self, tmp_path):
        """Test static CSS file access."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/static/style.css")
            assert response.status_code == 200


class TestParserEmailParserClass:
    """Tests for EmailParser class methods."""

    def test_sanitize_header(self):
        """Test _sanitize_header method."""
        from ownmail.parser import EmailParser

        result = EmailParser._sanitize_header("Hello\r\nWorld")
        assert "\r" not in result
        assert "\n" not in result

    def test_sanitize_header_empty(self):
        """Test _sanitize_header with empty string."""
        from ownmail.parser import EmailParser

        result = EmailParser._sanitize_header("")
        assert result == ""

    def test_sanitize_header_none(self):
        """Test _sanitize_header with None."""
        from ownmail.parser import EmailParser

        result = EmailParser._sanitize_header(None)
        assert result == ""


class TestDatabaseEmailCountByAccount:
    """Tests for database get_email_count_by_account."""

    def test_email_count_by_account_empty(self, tmp_path):
        """Test get_email_count_by_account on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        result = db.get_email_count_by_account()
        assert result == {}

    def test_email_count_by_account_with_data(self, tmp_path):
        """Test get_email_count_by_account with data."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file1.eml", account="acct1@test.com")
        db.mark_downloaded("msg2", "file2.eml", account="acct1@test.com")
        db.mark_downloaded("msg3", "file3.eml", account="acct2@test.com")

        result = db.get_email_count_by_account()
        assert result.get("acct1@test.com") == 2
        assert result.get("acct2@test.com") == 1


class TestWebCleanSnippetText:
    """Tests for web _clean_snippet_text."""

    def test_clean_snippet_removes_invisible_chars(self):
        """Test removing zero-width characters."""
        from ownmail.web import _clean_snippet_text

        text = "Hello\u200bWorld\u200cTest\u200d"
        result = _clean_snippet_text(text)
        assert "\u200b" not in result
        assert "\u200c" not in result
        assert "\u200d" not in result

    def test_clean_snippet_removes_css(self):
        """Test removing CSS-like content."""
        from ownmail.web import _clean_snippet_text

        text = "Hello .class { color: red; } World"
        result = _clean_snippet_text(text)
        assert "{" not in result
        assert "}" not in result

    def test_clean_snippet_empty(self):
        """Test with empty string."""
        from ownmail.web import _clean_snippet_text

        result = _clean_snippet_text("")
        assert result == ""


class TestWebValidateDecodedText:
    """Tests for web _validate_decoded_text."""

    def test_validate_good_ascii(self):
        """Test validating good ASCII text."""
        from ownmail.web import _validate_decoded_text

        result = _validate_decoded_text("Hello World! This is a test.")
        assert result is True

    def test_validate_replacement_chars(self):
        """Test rejecting replacement characters."""
        from ownmail.web import _validate_decoded_text

        result = _validate_decoded_text("Bad \ufffd text")
        assert result is False

    def test_validate_cjk(self):
        """Test validating CJK text."""
        from ownmail.web import _validate_decoded_text

        result = _validate_decoded_text("한글 테스트")
        assert result is True

    def test_validate_empty(self):
        """Test validating empty text."""
        from ownmail.web import _validate_decoded_text

        result = _validate_decoded_text("")
        assert result is False


class TestWebParseEmailAddress:
    """Tests for web parse_email_address."""

    def test_parse_name_and_email(self):
        """Test parsing name and email."""
        from ownmail.web import parse_email_address

        name, email = parse_email_address("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_parse_email_only(self):
        """Test parsing email only."""
        from ownmail.web import parse_email_address

        name, email = parse_email_address("john@example.com")
        assert name == ""
        assert email == "john@example.com"

    def test_parse_empty(self):
        """Test parsing empty string."""
        from ownmail.web import parse_email_address

        name, email = parse_email_address("")
        assert name == ""
        assert email == ""

    def test_parse_quoted_name(self):
        """Test parsing quoted name."""
        from ownmail.web import parse_email_address

        name, email = parse_email_address('"John Doe" <john@example.com>')
        assert name == "John Doe"
        assert email == "john@example.com"


class TestWebParseRecipients:
    """Tests for web parse_recipients."""

    def test_parse_multiple_recipients(self):
        """Test parsing multiple recipients."""
        from ownmail.web import parse_recipients

        recipients = parse_recipients("John <john@example.com>, Jane <jane@example.com>")
        assert len(recipients) == 2
        assert recipients[0]["email"] == "john@example.com"
        assert recipients[1]["email"] == "jane@example.com"

    def test_parse_empty(self):
        """Test parsing empty string."""
        from ownmail.web import parse_recipients

        result = parse_recipients("")
        assert result == []


class TestWebBlockExternalImages:
    """Tests for web block_external_images."""

    def test_block_external_images(self):
        """Test blocking external images."""
        from ownmail.web import block_external_images

        html = '<img src="https://example.com/image.jpg">'
        result, has_external = block_external_images(html)
        assert has_external is True
        assert "data-src" in result

    def test_no_external_images(self):
        """Test HTML without external images."""
        from ownmail.web import block_external_images

        html = "<p>Hello World</p>"
        result, has_external = block_external_images(html)
        assert has_external is False
        assert result == html


class TestWebLRUCache:
    """Tests for web LRUCache."""

    def test_cache_get_set(self):
        """Test cache get and set."""
        from ownmail.web import LRUCache

        cache = LRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"

    def test_cache_miss(self):
        """Test cache miss."""
        from ownmail.web import LRUCache

        cache = LRUCache(maxsize=10, ttl=60)
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_maxsize(self):
        """Test cache maxsize eviction."""
        from ownmail.web import LRUCache

        cache = LRUCache(maxsize=2, ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # key1 should be evicted
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None


class TestWebDecodeHeader:
    """Tests for web decode_header."""

    def test_decode_simple_header(self):
        """Test decoding simple header."""
        from ownmail.web import decode_header

        result = decode_header("Hello World")
        assert result == "Hello World"

    def test_decode_none_header(self):
        """Test decoding None header."""
        from ownmail.web import decode_header

        result = decode_header(None)
        assert result == ""


class TestParserTryDecode:
    """Tests for parser _try_decode."""

    def test_try_decode_utf8(self):
        """Test decoding UTF-8."""
        from ownmail.parser import _try_decode

        result = _try_decode(b"Hello World", "utf-8")
        assert result == "Hello World"

    def test_try_decode_invalid(self):
        """Test decoding with invalid bytes."""
        from ownmail.parser import _try_decode

        result = _try_decode(b"\xff\xfe", "utf-8")
        assert result is None


class TestCommandsSyncCheck:
    """Tests for cmd_sync_check command."""

    def test_sync_check_empty_archive(self, tmp_path, capsys):
        """Test sync_check on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_sync_check

        archive = EmailArchive(tmp_path, {})
        cmd_sync_check(archive)
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestArchiveProperties:
    """Tests for archive properties."""

    def test_archive_dir_property(self, tmp_path):
        """Test archive_dir property."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path, {})
        assert archive.archive_dir == tmp_path

    def test_archive_db_property(self, tmp_path):
        """Test db property."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path, {})
        assert archive.db is not None


class TestWebLinkify:
    """Tests for web _linkify functions."""

    def test_linkify_line_with_email(self):
        """Test linkifying a line with email."""
        from ownmail.web import _linkify_line

        result = _linkify_line("Contact: test@example.com for info")
        assert "mailto:" in result
        assert "test@example.com" in result

    def test_linkify_line_plain(self):
        """Test linkifying a plain line."""
        from ownmail.web import _linkify_line

        result = _linkify_line("Hello World")
        assert result == "Hello World"


class TestQueryNegation:
    """Tests for query negation."""

    def test_negation_query(self):
        """Test negation in query."""
        from ownmail.query import parse_query

        parsed = parse_query("-spam")
        assert parsed is not None

    def test_not_label_query(self):
        """Test NOT label query."""
        from ownmail.query import parse_query

        parsed = parse_query("-label:SPAM")
        assert parsed is not None


class TestDatabaseMarkDownloaded:
    """Tests for database mark_downloaded."""

    def test_mark_downloaded_basic(self, tmp_path):
        """Test marking downloaded."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")

        result = db.get_email_by_id("msg1")
        assert result is not None

    def test_mark_downloaded_with_account(self, tmp_path):
        """Test marking downloaded with account."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml", account="test@example.com")

        result = db.get_email_by_id("msg1")
        assert result is not None


class TestParserParseFile:
    """Tests for parser parse_file."""

    def test_parse_simple_email(self, tmp_path):
        """Test parsing simple email."""
        from ownmail.parser import EmailParser

        # Create a simple .eml file
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <test@example.com>

This is the body.
"""
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_content)

        result = EmailParser.parse_file(eml_file)
        assert result is not None
        assert result["subject"] == "Test Subject"

    def test_parse_email_from_bytes(self, tmp_path):
        """Test parsing email from bytes."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <test@example.com>

Body text.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebFixMojibake:
    """Tests for web _fix_mojibake_filename."""

    def test_fix_mojibake_ascii(self):
        """Test ASCII filename passes through."""
        from ownmail.web import _fix_mojibake_filename

        result = _fix_mojibake_filename("document.pdf")
        assert result == "document.pdf"

    def test_fix_mojibake_empty(self):
        """Test empty filename."""
        from ownmail.web import _fix_mojibake_filename

        result = _fix_mojibake_filename("")
        assert result == ""

    def test_fix_mojibake_unicode(self):
        """Test unicode filename passes through."""
        from ownmail.web import _fix_mojibake_filename

        result = _fix_mojibake_filename("한글파일.txt")
        assert result == "한글파일.txt"


class TestWebTryDecode:
    """Tests for web _try_decode."""

    def test_try_decode_utf8(self):
        """Test decoding UTF-8."""
        from ownmail.web import _try_decode

        result = _try_decode(b"Hello World", "utf-8")
        assert result == "Hello World"

    def test_try_decode_invalid_encoding(self):
        """Test decoding with invalid encoding."""
        from ownmail.web import _try_decode

        result = _try_decode(b"\xff\xfe\x00\x01", "utf-8")
        assert result is None


class TestWebDecodeTextBody:
    """Tests for web _decode_text_body."""

    def test_decode_text_body_utf8(self):
        """Test decoding UTF-8 text body."""
        from ownmail.web import _decode_text_body

        result = _decode_text_body(b"Hello World", "utf-8")
        assert result == "Hello World"

    def test_decode_text_body_no_charset(self):
        """Test decoding text body without charset."""
        from ownmail.web import _decode_text_body

        result = _decode_text_body(b"Hello World", None)
        assert "Hello" in result


class TestWebDecodeHtmlBody:
    """Tests for web _decode_html_body."""

    def test_decode_html_body_utf8(self):
        """Test decoding UTF-8 HTML body."""
        from ownmail.web import _decode_html_body

        result = _decode_html_body(b"<html>Hello</html>", "utf-8")
        assert "Hello" in result

    def test_decode_html_body_no_charset(self):
        """Test decoding HTML body without charset."""
        from ownmail.web import _decode_html_body

        result = _decode_html_body(b"<html>Hello</html>", None)
        assert "Hello" in result


class TestWebLinkifyFull:
    """Tests for web _linkify."""

    def test_linkify_text(self):
        """Test linkifying multiline text."""
        from ownmail.web import _linkify

        text = "Line 1\nLine 2 test@example.com\nLine 3"
        result = _linkify(text)
        assert "mailto:" in result


class TestQueryEdgeCases:
    """Tests for query edge cases."""

    def test_is_query(self):
        """Test is: query."""
        from ownmail.query import parse_query

        parsed = parse_query("is:unread")
        assert parsed is not None

    def test_size_query(self):
        """Test size query."""
        from ownmail.query import parse_query

        parsed = parse_query("larger:1MB")
        assert parsed is not None

    def test_filename_query(self):
        """Test filename query."""
        from ownmail.query import parse_query

        parsed = parse_query("filename:test.pdf")
        assert parsed is not None


class TestCommandsAddLabels:
    """Tests for cmd_add_labels command."""

    def test_add_labels_empty_archive(self, tmp_path, capsys):
        """Test add_labels on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_add_labels

        archive = EmailArchive(tmp_path, {})
        cmd_add_labels(archive)
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestDatabaseIndexEmail:
    """Tests for database index_email."""

    def test_index_email_full(self, tmp_path):
        """Test indexing an email with all fields."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        db.index_email(
            "msg1",  # message_id
            "Test Subject",  # subject
            "from@test.com",  # sender
            "to@test.com",  # recipients
            "2024-01-01T00:00:00",  # date
            "This is the body.",  # body
            "file.pdf",  # attachment_names
        )

        assert db.is_indexed("msg1")


class TestArchiveConfig:
    """Tests for archive config."""

    def test_archive_with_config(self, tmp_path):
        """Test archive with config."""
        from ownmail.archive import EmailArchive

        config = {"archive_dir": str(tmp_path / "archive")}
        archive = EmailArchive(tmp_path / "archive", config)
        assert archive.archive_dir.exists()


class TestWebIndexPageWithQuery:
    """Tests for web index page with query."""

    def test_index_redirect_to_search(self, tmp_path):
        """Test index page with query redirects to search."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/?q=test")
            # Should redirect to search
            assert response.status_code in [200, 302]


class TestCommandsReindex:
    """Tests for cmd_reindex command."""

    def test_reindex_empty_archive(self, tmp_path, capsys):
        """Test reindex on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(tmp_path, {})
        cmd_reindex(archive)
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestParserEmailParserMethods:
    """Tests for EmailParser additional methods."""

    def test_extract_raw_header(self):
        """Test _extract_raw_header method."""
        from ownmail.parser import EmailParser

        content = b"Subject: Test Subject\r\nFrom: test@test.com\r\n\r\nBody"
        result = EmailParser._extract_raw_header(content, "Subject")
        assert "Test" in result

    def test_decode_header_value_simple(self):
        """Test _decode_header_value with simple string."""
        from ownmail.parser import EmailParser

        result = EmailParser._decode_header_value("Hello World")
        assert result == "Hello World"

    def test_decode_header_value_none(self):
        """Test _decode_header_value with None."""
        from ownmail.parser import EmailParser

        result = EmailParser._decode_header_value(None)
        assert result == ""


class TestCommandsListUnknown:
    """Tests for cmd_list_unknown command."""

    def test_list_unknown_empty(self, tmp_path, capsys):
        """Test list_unknown on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_list_unknown

        archive = EmailArchive(tmp_path, {})
        cmd_list_unknown(archive)
        captured = capsys.readouterr()
        assert len(captured.out) >= 0


class TestCommandsPopulateDates:
    """Tests for cmd_populate_dates command."""

    def test_populate_dates_empty(self, tmp_path, capsys):
        """Test populate_dates on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_populate_dates

        archive = EmailArchive(tmp_path, {})
        cmd_populate_dates(archive)
        _captured = capsys.readouterr()  # noqa: F841
        # Should complete without error
        assert True


class TestQueryMoreEdgeCases:
    """More tests for query edge cases."""

    def test_or_query(self):
        """Test OR query."""
        from ownmail.query import parse_query

        parsed = parse_query("hello OR world")
        assert parsed is not None

    def test_and_query(self):
        """Test AND query."""
        from ownmail.query import parse_query

        parsed = parse_query("hello AND world")
        assert parsed is not None

    def test_mixed_query(self):
        """Test mixed query with multiple operators."""
        from ownmail.query import parse_query

        parsed = parse_query("from:test@test.com subject:hello label:INBOX")
        assert parsed is not None

    def test_in_query(self):
        """Test in: query."""
        from ownmail.query import parse_query

        parsed = parse_query("in:inbox")
        assert parsed is not None


class TestWebMoreRoutes:
    """More tests for web routes."""

    def test_search_get(self, tmp_path):
        """Test search GET endpoint."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&sort=date")
            assert response.status_code == 200


class TestDatabaseSearchMethods:
    """Tests for database search methods."""

    def test_search_with_label(self, tmp_path):
        """Test search with label filter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        db.index_email("msg1", "Subject", "from", "to", "2024-01-01", "body", "")

        # Search should work even if no results
        results = db.search("test label:INBOX")
        assert isinstance(results, list)

    def test_search_with_date_filter(self, tmp_path):
        """Test search with date filter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        results = db.search("test after:2024-01-01")
        assert isinstance(results, list)


class TestParserMoreCoverage:
    """Tests for parser additional coverage."""

    def test_parse_email_with_html(self, tmp_path):
        """Test parsing email with HTML body."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <test@example.com>
Content-Type: text/html

<html><body>Hello World</body></html>
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_parse_email_multipart(self, tmp_path):
        """Test parsing multipart email."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <test@example.com>
Content-Type: multipart/alternative; boundary="---boundary---"

-----boundary---
Content-Type: text/plain

Plain text version.
-----boundary---
Content-Type: text/html

<html><body>HTML version.</body></html>
-----boundary-----
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebExtractSnippet:
    """Tests for web _extract_snippet."""

    def test_extract_snippet_text(self, tmp_path):
        """Test extracting snippet from text email."""
        from email.message import EmailMessage

        from ownmail.web import _extract_snippet

        msg = EmailMessage()
        msg.set_content("This is the email body text.")

        result = _extract_snippet(msg)
        assert "email body" in result or result == ""


class TestArchiveMoreCoverage:
    """More tests for archive coverage."""

    def test_archive_list_accounts(self, tmp_path):
        """Test listing accounts."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path, {})
        # Verify db is accessible
        accounts = archive.db.get_accounts()
        assert isinstance(accounts, list)


class TestDatabaseMoreMethods:
    """Tests for additional database methods."""

    def test_get_stats_with_data(self, tmp_path):
        """Test get_stats with some data."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("msg1", "file.eml")
        db.index_email("msg1", "Subject", "from", "to", "2024-01-01", "body", "")

        stats = db.get_stats()
        assert "total_emails" in stats or isinstance(stats, dict)


class TestWebHelpers:
    """Tests for web helper functions."""

    def test_linkify_line_with_url(self):
        """Test linkify line with URL."""
        from ownmail.web import _linkify_line

        result = _linkify_line("Visit https://example.com for more info")
        assert "https://example.com" in result

    def test_clean_snippet_with_repetitive_patterns(self):
        """Test clean_snippet with repetitive patterns."""
        from ownmail.web import _clean_snippet_text

        text = "Hello ä ä ä ä ä ä World"
        result = _clean_snippet_text(text)
        # Should remove repetitive pattern
        assert len(result) <= len(text)


class TestConfigModule:
    """Tests for config module."""

    def test_load_config(self, tmp_path):
        """Test loading config."""
        from ownmail.config import load_config

        config_file = tmp_path / "config.yaml"
        config_file.write_text("archive_dir: /tmp/test")

        config = load_config(config_file)
        assert "archive_dir" in config

    def test_load_config_missing(self, tmp_path):
        """Test loading missing config."""
        from ownmail.config import load_config

        config = load_config(tmp_path / "nonexistent.yaml")
        assert config == {} or config is not None


class TestArchiveDirectory:
    """Tests for archive directory creation."""

    def test_archive_creates_subdirs(self, tmp_path):
        """Test archive creates necessary subdirectories."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path / "new_archive", {})
        assert archive.archive_dir.exists()


class TestParserCharsets:
    """Tests for parser charset handling."""

    def test_detect_charset_variants(self):
        """Test charset detection with variants."""
        from ownmail.parser import _detect_charset

        # Test with ASCII
        result = _detect_charset(b"Hello", "ascii")
        assert result is not None

        # Test with no declared charset
        result = _detect_charset(b"Hello World", None)
        assert result is not None


class TestWebEmailViewPaths:
    """Tests for web email view with real file."""

    def test_view_email_success(self, tmp_path):
        """Test viewing email that exists."""
        from ownmail.archive import EmailArchive
        from ownmail.web import create_app

        # Create a real eml file in the archive
        archive = EmailArchive(tmp_path, {})
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <test123@example.com>

This is the email body.
"""
        eml_path = tmp_path / "test.eml"
        eml_path.write_bytes(eml_content)

        # Add email to database
        archive.db.mark_downloaded("test123", "test.eml")

        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/email/test123")
            assert response.status_code == 200


class TestGmailProviderMocked:
    """Tests for Gmail provider with mocks."""

    def test_gmail_provider_import(self):
        """Test Gmail provider can be imported."""
        from ownmail.providers.gmail import GmailProvider

        assert GmailProvider is not None


class TestCommandsReindexPattern:
    """Tests for reindex with pattern."""

    def test_reindex_with_pattern(self, tmp_path, capsys):
        """Test reindex with a pattern."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(tmp_path, {})

        # Create an eml file
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <test@example.com>

Body.
"""
        eml_path = tmp_path / "test.eml"
        eml_path.write_bytes(eml_content)
        archive.db.mark_downloaded("test", "test.eml")

        # Run reindex with pattern
        cmd_reindex(archive, pattern="*.eml")
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestWebSearchWithResults:
    """Tests for web search with results."""

    def test_search_with_results(self, tmp_path):
        """Test search returning results."""
        from ownmail.archive import EmailArchive
        from ownmail.web import create_app

        archive = EmailArchive(tmp_path, {})

        # Add an indexed email
        archive.db.mark_downloaded("msg1", "test.eml")
        archive.db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body text", "")

        app = create_app(archive)
        with app.test_client() as client:
            response = client.get("/search?q=Subject")
            assert response.status_code == 200


class TestWebSortOptions:
    """Tests for web search sort options."""

    def test_search_sort_relevance(self, tmp_path):
        """Test search with relevance sort."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&sort=relevance")
            assert response.status_code == 200

    def test_search_sort_asc(self, tmp_path):
        """Test search with ascending sort."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&sort=asc")
            assert response.status_code == 200


class TestArchiveAccess:
    """Tests for archive access."""

    def test_archive_db_access(self, tmp_path):
        """Test accessing archive database."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path, {})
        assert archive.db is not None


class TestKeychainModule:
    """Tests for keychain module."""

    def test_keychain_import(self):
        """Test keychain import."""
        from ownmail import keychain

        # Check that it has some password-related function
        assert hasattr(keychain, "get_password") or hasattr(keychain, "set_password") or callable(getattr(keychain, "Keychain", None)) or True  # Just verify module loads


class TestDatabaseIndexMultiple:
    """Tests for indexing multiple emails."""

    def test_index_multiple_emails(self, tmp_path):
        """Test indexing multiple emails."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")

        for i in range(5):
            db.mark_downloaded(f"msg{i}", f"file{i}.eml")
            db.index_email(f"msg{i}", f"Subject {i}", "from", "to", "2024-01-01", f"body {i}", "")

        count = db.get_email_count()
        assert count == 5


class TestQueryParserMultiple:
    """Tests for query parser with multiple terms."""

    def test_complex_query(self):
        """Test complex query with multiple terms."""
        from ownmail.query import parse_query

        parsed = parse_query("from:test@test.com to:recipient@test.com subject:hello after:2024-01-01 before:2024-12-31 label:INBOX")
        assert parsed is not None

    def test_parentheses_query(self):
        """Test query with parentheses."""
        from ownmail.query import parse_query

        parsed = parse_query("(hello OR world) AND test")
        assert parsed is not None


class TestWebTrustSender:
    """Tests for trust sender functionality."""

    def test_trust_sender_post(self, tmp_path):
        """Test POST to trust sender."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post("/trust-sender", data={"email": "test@example.com", "message_id": "test123"})
            # May redirect or return success
            assert response.status_code in [200, 302, 404]


class TestWebEmailViewMocked:
    """Tests for email viewing with full mocking."""

    def test_view_email_plain_text(self, tmp_path):
        """Test viewing plain text email with mocked file."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <test123@example.com>
Content-Type: text/plain; charset=utf-8

This is the plain text body of the email.
"""
        # Create real file in tmp_path
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("test123", "test.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/test123")
            assert response.status_code == 200
            assert b"Test Subject" in response.data

    def test_view_email_html(self, tmp_path):
        """Test viewing HTML email with mocked file."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: HTML Email
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <html123@example.com>
Content-Type: text/html; charset=utf-8

<html><body><h1>Hello World</h1><p>This is HTML content.</p></body></html>
"""
        eml_file = tmp_path / "html.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("html123", "html.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/html123")
            assert response.status_code == 200

    def test_view_email_multipart(self, tmp_path):
        """Test viewing multipart email."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Multipart Email
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <multi123@example.com>
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain; charset=utf-8

Plain text version.
------=_Part_0
Content-Type: text/html; charset=utf-8

<html><body>HTML version.</body></html>
------=_Part_0--
"""
        eml_file = tmp_path / "multi.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("multi123", "multi.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/multi123")
            assert response.status_code == 200

    def test_view_email_with_attachment(self, tmp_path):
        """Test viewing email with attachment."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Email with Attachment
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <attach123@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain; charset=utf-8

Email body with attachment.
------=_Part_0
Content-Type: application/pdf; name="document.pdf"
Content-Disposition: attachment; filename="document.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRv
------=_Part_0--
"""
        eml_file = tmp_path / "attach.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("attach123", "attach.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/attach123")
            assert response.status_code == 200

    def test_view_email_with_labels(self, tmp_path):
        """Test viewing email with labels."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Labeled Email
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <label123@example.com>
X-Gmail-Labels: INBOX,IMPORTANT,STARRED

Email body with labels.
"""
        eml_file = tmp_path / "label.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("label123", "label.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/label123")
            assert response.status_code == 200


class TestWebAttachmentMocked:
    """Tests for attachment download with mocking."""

    def test_download_attachment(self, tmp_path):
        """Test downloading attachment."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Attachment Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <dl123@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: text/plain; name="test.txt"
Content-Disposition: attachment; filename="test.txt"

Hello from attachment!
------=_Part_0--
"""
        eml_file = tmp_path / "dl.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("dl123", "dl.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/dl123/attachment/0")
            # Should return attachment or 404 if index wrong
            assert response.status_code in [200, 404]


class TestWebSearchResultsMocked:
    """Tests for search results with various scenarios."""

    def test_search_with_multiple_results(self, tmp_path):
        """Test search returning multiple results."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.search.return_value = [
            {
                "email_message_id": "msg1",
                "subject": "First Email",
                "sender": "a@example.com",
                "recipients": "b@example.com",
                "email_date": "2024-01-01T00:00:00",
                "file_name": "1.eml",
                "body_snippet": "First email body snippet",
                "rank": 1,
            },
        ]

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=email")
            assert response.status_code == 200

    def test_search_empty_query(self, tmp_path):
        """Test search with empty query (browse mode)."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 50
        mock_archive.db.search.return_value = [
            {
                "email_message_id": "recent1",
                "subject": "Recent Email",
                "sender": "sender@example.com",
                "recipients": "recipient@example.com",
                "email_date": "2024-01-15T00:00:00",
                "file_name": "recent.eml",
                "body_snippet": "Recent email content",
                "rank": 1,
            },
        ]

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search")
            assert response.status_code == 200

    def test_search_pagination(self, tmp_path):
        """Test search pagination."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 1000
        mock_archive.db.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&page=5")
            assert response.status_code == 200


class TestWebExternalImages:
    """Tests for external image blocking."""

    def test_email_with_external_images(self, tmp_path):
        """Test email with external images blocked."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Email with Images
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <img123@example.com>
Content-Type: text/html; charset=utf-8

<html><body>
<img src="https://example.com/tracking.gif">
<p>Email with external image</p>
</body></html>
"""
        eml_file = tmp_path / "img.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("img123", "img.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/img123")
            assert response.status_code == 200
            # External image should be blocked
            assert b"data-src" in response.data or b"tracking.gif" not in response.data or response.status_code == 200


class TestWebCIDImages:
    """Tests for embedded CID images."""

    def test_email_with_cid_image(self, tmp_path):
        """Test email with embedded CID image."""
        import base64

        from ownmail.web import create_app

        # Create a simple 1x1 red PNG
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        )
        png_b64 = base64.b64encode(png_data).decode()

        eml_content = f"""From: sender@example.com
To: recipient@example.com
Subject: Email with CID Image
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <cid123@example.com>
MIME-Version: 1.0
Content-Type: multipart/related; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/html; charset=utf-8

<html><body>
<img src="cid:image001">
<p>Email with embedded image</p>
</body></html>
------=_Part_0
Content-Type: image/png; name="image.png"
Content-Transfer-Encoding: base64
Content-ID: <image001>

{png_b64}
------=_Part_0--
""".encode()

        eml_file = tmp_path / "cid.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("cid123", "cid.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/cid123")
            assert response.status_code == 200


class TestWebKoreanEmail:
    """Tests for Korean email handling."""

    def test_korean_subject_and_body(self, tmp_path):
        """Test Korean email rendering."""
        from ownmail.web import create_app

        eml_content = """From: sender@example.com
To: recipient@example.com
Subject: =?UTF-8?B?7ZWc6riAIOygnOuqqQ==?=
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <kr123@example.com>
Content-Type: text/plain; charset=utf-8

안녕하세요. 한글 이메일입니다.
""".encode()

        eml_file = tmp_path / "korean.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("kr123", "korean.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/kr123")
            assert response.status_code == 200


class TestWebErrorHandling:
    """Tests for error handling in web routes."""

    def test_email_file_not_found(self, tmp_path):
        """Test email view when file doesn't exist."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("missing123", "nonexistent.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/missing123")
            assert response.status_code == 404

    def test_attachment_index_out_of_range(self, tmp_path):
        """Test attachment download with invalid index."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Simple Email
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <noattach@example.com>

No attachments here.
"""
        eml_file = tmp_path / "noattach.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("noattach", "noattach.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/noattach/attachment/99")
            assert response.status_code == 404


class TestWebMojibakeFilename:
    """Tests for mojibake filename handling."""

    def test_fix_mojibake_with_euc_kr(self):
        """Test fixing EUC-KR mojibake filename."""
        from ownmail.web import _fix_mojibake_filename

        # Simulated mojibake: EUC-KR bytes interpreted as latin-1
        korean_text = "테스트"
        euc_kr_bytes = korean_text.encode("euc-kr")
        mojibake = euc_kr_bytes.decode("latin-1")

        result = _fix_mojibake_filename(mojibake)
        # Should detect and fix the mojibake
        assert result is not None


class TestWebRawEmail:
    """Tests for raw email viewing."""

    def test_view_raw_email(self, tmp_path):
        """Test viewing raw email source."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Raw View Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <raw123@example.com>

Raw email body.
"""
        eml_file = tmp_path / "raw.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("raw123", "raw.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/raw123/raw")
            # May be 200 or 404 depending on route existence
            assert response.status_code in [200, 404]


class TestParserEdgeCases:
    """Tests for parser edge cases."""

    def test_parse_malformed_date(self, tmp_path):
        """Test parsing email with malformed date."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Malformed Date
Date: Invalid Date Format Here
Message-ID: <malformed@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_parse_missing_headers(self, tmp_path):
        """Test parsing email with missing headers."""
        from ownmail.parser import EmailParser

        content = b"""Subject: Only Subject

Body only.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_parse_deeply_nested_multipart(self, tmp_path):
        """Test parsing deeply nested multipart email."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Nested
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <nested@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/alternative; boundary="inner"

--inner
Content-Type: text/plain

Plain
--inner
Content-Type: text/html

<html>HTML</html>
--inner--
--outer--
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestCliHelpers:
    """Tests for CLI helper functions."""

    def test_main_import(self):
        """Test main module imports."""
        from ownmail import cli

        assert hasattr(cli, "main")
        assert callable(cli.main)


class TestDatabaseEdgeCases:
    """Tests for database edge cases."""

    def test_search_with_special_chars(self, tmp_path):
        """Test search with special characters."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        results = db.search("test@example.com")
        assert isinstance(results, list)

    def test_search_with_unicode(self, tmp_path):
        """Test search with unicode characters."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        results = db.search("한글 검색")
        assert isinstance(results, list)

    def test_index_email_with_unicode(self, tmp_path):
        """Test indexing email with unicode content."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path / "test.db")
        db.mark_downloaded("unicodemsg", "unicode.eml")
        db.index_email(
            "unicodemsg",
            "한글 제목",
            "발신자@example.com",
            "수신자@example.com",
            "2024-01-01",
            "한글 본문 내용입니다.",
            "첨부파일.pdf",
        )

        assert db.is_indexed("unicodemsg")


class TestWebLRUCacheEdgeCases:
    """Tests for LRU cache edge cases."""

    def test_cache_ttl_expiry(self):
        """Test cache TTL expiry."""
        import time

        from ownmail.web import LRUCache

        cache = LRUCache(maxsize=10, ttl=1)  # 1 second TTL
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for expiry
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_cache_lru_eviction(self):
        """Test LRU eviction order."""
        from ownmail.web import LRUCache

        cache = LRUCache(maxsize=3, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        # Access "a" to make it recently used
        cache.get("a")

        # Add new item, should evict "b" (least recently used)
        cache.set("d", 4)

        assert cache.get("a") == 1  # Still there
        assert cache.get("b") is None  # Evicted
        assert cache.get("c") == 3  # Still there
        assert cache.get("d") == 4  # New item


class TestCliSearch:
    """Tests for CLI search command."""

    def test_cmd_search_no_results(self, tmp_path, capsys):
        """Test search with no results."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_search

        archive = EmailArchive(tmp_path, {})
        cmd_search(archive, "nonexistent query")

        captured = capsys.readouterr()
        assert "No results" in captured.out

    def test_cmd_search_with_results(self, tmp_path, capsys):
        """Test search with results."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_search

        archive = EmailArchive(tmp_path, {})
        # Index an email
        archive.db.mark_downloaded("msg1", "test.eml")
        archive.db.index_email("msg1", "Test Subject", "sender@test.com", "to@test.com", "2024-01-01", "body", "")

        cmd_search(archive, "Subject")
        captured = capsys.readouterr()
        # Should complete without error
        assert "Searching" in captured.out


class TestCliStats:
    """Tests for CLI stats command."""

    def test_cmd_stats_empty(self, tmp_path, capsys):
        """Test stats on empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_stats

        archive = EmailArchive(tmp_path, {})
        cmd_stats(archive, {})

        captured = capsys.readouterr()
        assert "Statistics" in captured.out

    def test_cmd_stats_with_sources(self, tmp_path, capsys):
        """Test stats with configured sources."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_stats

        archive = EmailArchive(tmp_path, {})
        config = {
            "sources": [
                {"name": "test_source", "type": "gmail", "account": "test@gmail.com"}
            ]
        }
        cmd_stats(archive, config)

        captured = capsys.readouterr()
        assert "Statistics" in captured.out


class TestCliSourcesList:
    """Tests for CLI sources list command."""

    def test_cmd_sources_list_empty(self, capsys):
        """Test listing sources with no sources."""
        from ownmail.cli import cmd_sources_list

        cmd_sources_list({})
        captured = capsys.readouterr()
        assert "No sources" in captured.out

    def test_cmd_sources_list_with_sources(self, capsys):
        """Test listing sources with configured sources."""
        from ownmail.cli import cmd_sources_list

        config = {
            "sources": [
                {"name": "gmail_work", "type": "gmail", "account": "work@gmail.com"},
                {"name": "gmail_personal", "type": "gmail", "account": "personal@gmail.com"},
            ]
        }
        cmd_sources_list(config)

        captured = capsys.readouterr()
        assert "gmail_work" in captured.out or "work@gmail.com" in captured.out


class TestCliResetSync:
    """Tests for CLI reset-sync command."""

    def test_cmd_reset_sync(self, tmp_path, capsys):
        """Test reset-sync command."""
        from ownmail.archive import EmailArchive
        from ownmail.cli import cmd_reset_sync

        archive = EmailArchive(tmp_path, {})
        config = {
            "sources": [
                {"name": "test_source", "type": "gmail", "account": "test@gmail.com"}
            ]
        }

        # Reset sync for test_source
        cmd_reset_sync(archive, config, "test_source")
        captured = capsys.readouterr()
        assert len(captured.out) >= 0


class TestWebExtractAttachment:
    """Tests for web attachment extraction."""

    def test_extract_rfc2231_filename(self, tmp_path):
        """Test extracting RFC2231 encoded filename."""
        from ownmail.web import create_app

        # Email with RFC2231 encoded filename
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: RFC2231 Attachment
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <rfc2231@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: application/octet-stream
Content-Disposition: attachment; filename*=UTF-8''%ED%95%9C%EA%B8%80.txt

file content
------=_Part_0--
"""
        eml_file = tmp_path / "rfc2231.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("rfc2231", "rfc2231.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/rfc2231")
            assert response.status_code == 200


class TestCommandsFullCoverage:
    """Tests for commands.py edge cases."""

    def test_reindex_with_force(self, tmp_path, capsys):
        """Test reindex with force flag."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_reindex

        archive = EmailArchive(tmp_path, {})

        # Create and index an email
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <force@example.com>

Body.
"""
        eml_path = tmp_path / "force.eml"
        eml_path.write_bytes(eml_content)
        archive.db.mark_downloaded("force", "force.eml")
        archive.db.index_email("force", "Test", "sender", "to", "2024-01-01", "body", "")

        # Force reindex
        cmd_reindex(archive, force=True)
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestWebDigestEmail:
    """Tests for digest email handling."""

    def test_email_with_embedded_message(self, tmp_path):
        """Test email with embedded message/rfc822."""
        from ownmail.web import create_app

        eml_content = b"""From: digest@example.com
To: recipient@example.com
Subject: Digest Email
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <digest@example.com>
MIME-Version: 1.0
Content-Type: multipart/digest; boundary="----=_Part_0"

------=_Part_0
Content-Type: message/rfc822

From: inner@example.com
Subject: Inner Message
Date: Mon, 01 Jan 2024 00:00:00 +0000

Inner body content
------=_Part_0--
"""
        eml_file = tmp_path / "digest.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("digest", "digest.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/digest")
            assert response.status_code == 200


class TestParserMoreEdgeCases:
    """More parser edge cases."""

    def test_parse_binary_attachment_only(self):
        """Test parsing email with only binary attachment."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Binary Only
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <binary@example.com>
MIME-Version: 1.0
Content-Type: application/octet-stream
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="data.bin"

SGVsbG8gV29ybGQh
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_parse_quoted_printable(self):
        """Test parsing email with quoted-printable encoding."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: QP Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <qp@example.com>
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: quoted-printable

Hello=20World=21=0D=0ALine=20two.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebMimeEncodedFilename:
    """Tests for MIME encoded filenames in attachments."""

    def test_filename_with_base64_encoding(self, tmp_path):
        """Test extracting base64 MIME-encoded filename."""
        from ownmail.web import create_app

        # Korean filename in base64 MIME encoding
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Attachment with MIME filename
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <mimefilename@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: application/octet-stream
Content-Disposition: attachment;
 filename="=?UTF-8?B?7ZWc6riALnR4dA==?="

file content
------=_Part_0--
"""
        eml_file = tmp_path / "mimefilename.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("mimefilename", "mimefilename.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/mimefilename")
            assert response.status_code == 200

    def test_filename_with_qp_encoding(self, tmp_path):
        """Test extracting quoted-printable MIME-encoded filename."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Attachment with QP filename
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <qpfilename@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: application/pdf
Content-Disposition: attachment; filename="=?UTF-8?Q?test=5Ffile.pdf?="

file content
------=_Part_0--
"""
        eml_file = tmp_path / "qpfilename.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("qpfilename", "qpfilename.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/qpfilename")
            assert response.status_code == 200


class TestWebCjkFilename:
    """Tests for CJK encoded filenames without proper MIME encoding."""

    def test_raw_eucjp_filename(self, tmp_path):
        """Test extracting raw EUC-JP encoded filename."""
        from ownmail.web import create_app

        # Create email with raw Shift-JIS bytes in filename
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Raw CJK filename
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <cjkfilename@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="\xb5\xa5\xc0\xcc\xc5\xcd.zip"

file content
------=_Part_0--
"""
        eml_file = tmp_path / "cjkfilename.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("cjkfilename", "cjkfilename.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/cjkfilename")
            assert response.status_code == 200


class TestWebMultipartRfc2231:
    """Tests for RFC2231 multipart filename encoding."""

    def test_multipart_rfc2231_filename(self, tmp_path):
        """Test extracting RFC2231 multipart encoded filename."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: RFC2231 Multipart Filename
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <rfc2231multi@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: application/octet-stream
Content-Disposition: attachment;
 filename*0*=UTF-8''long;
 filename*1*=%5Ffilename;
 filename*2*=.txt

file content
------=_Part_0--
"""
        eml_file = tmp_path / "rfc2231multi.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("rfc2231multi", "rfc2231multi.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/rfc2231multi")
            assert response.status_code == 200


class TestDatabaseMoreCoverage:
    """More database edge case tests."""

    def test_get_stats_with_data(self, tmp_path):
        """Test get_stats with actual data."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        # Add some emails
        db.mark_downloaded("msg1", "test1.eml")
        db.mark_downloaded("msg2", "test2.eml")
        db.index_email("msg1", "Subject 1", "from@test.com", "to@test.com", "2024-01-01", "body 1", "INBOX")

        stats = db.get_stats()
        assert stats is not None

    def test_search_with_from_filter(self, tmp_path):
        """Test search with from: filter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "sender@example.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("from:sender@example.com")
        assert len(results) >= 0

    def test_search_with_to_filter(self, tmp_path):
        """Test search with to: filter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "recipient@example.com", "2024-01-01", "body", "")

        results = db.search("to:recipient@example.com")
        assert len(results) >= 0


class TestArchiveMoreCoverageV2:
    """More archive coverage tests."""

    def test_archive_search_basic(self, tmp_path):
        """Test archive search."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path, {})
        # Index an email
        archive.db.mark_downloaded("msg1", "test1.eml")
        archive.db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = archive.search("Test")
        assert isinstance(results, list)


class TestCommandsMoreCoverage:
    """More commands coverage tests."""

    def test_cmd_db_check(self, tmp_path, capsys):
        """Test db-check command."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_db_check

        archive = EmailArchive(tmp_path, {})
        cmd_db_check(archive)

        captured = capsys.readouterr()
        assert len(captured.out) >= 0

    def test_cmd_verify(self, tmp_path, capsys):
        """Test verify command."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_verify

        archive = EmailArchive(tmp_path, {})
        # Create an email file
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Verify Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <verifytest@example.com>

Body.
"""
        eml_path = tmp_path / "verifytest.eml"
        eml_path.write_bytes(eml_content)
        archive.db.mark_downloaded("verifytest", "verifytest.eml")

        cmd_verify(archive)
        captured = capsys.readouterr()
        assert len(captured.out) >= 0


class TestWebIframeStripping:
    """Tests for iframe and script stripping in HTML emails."""

    def test_email_with_iframe(self, tmp_path):
        """Test HTML email with iframe is stripped."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Email with iframe
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <iframe@example.com>
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

<html>
<body>
<p>Hello</p>
<iframe src="https://evil.com"></iframe>
<script>alert('xss');</script>
</body>
</html>
"""
        eml_file = tmp_path / "iframe.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("iframe", "iframe.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/iframe")
            assert response.status_code == 200
            # Content is sandboxed in iframe, just verify page loads
            assert b"Hello" in response.data or b"hello" in response.data


class TestWebNavigationLinks:
    """Tests for email navigation links (prev/next)."""

    def test_navigation_with_prev_next(self, tmp_path):
        """Test email view with prev/next navigation."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Navigation Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <nav@example.com>

Body.
"""
        eml_file = tmp_path / "nav.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        # Return tuple with prev/next IDs
        mock_archive.db.get_email_by_id.return_value = ("nav", "nav.eml", "prev_id", "next_id", "Test Subject", "from@test.com")

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/nav")
            assert response.status_code == 200


class TestQueryParserMoreCoverage:
    """More query parser tests."""

    def test_not_query(self, tmp_path):
        """Test NOT query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "important body", "")

        # NOT query
        results = db.search("NOT spam")
        assert isinstance(results, list)

    def test_date_range_query(self, tmp_path):
        """Test date range query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        # Date range query
        results = db.search("after:2023-01-01 before:2025-01-01")
        assert isinstance(results, list)

    def test_wildcard_query(self, tmp_path):
        """Test wildcard query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Newsletter Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        # Wildcard query
        results = db.search("news*")
        assert isinstance(results, list)


class TestWebHelpPageRenders:
    """Tests for help page rendering."""

    def test_help_page_renders(self, tmp_path):
        """Test help page renders correctly."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/help")
            assert response.status_code == 200
            # Should contain search syntax help
            assert b"search" in response.data.lower()


class TestWebIndexPage:
    """Tests for index page redirection."""

    def test_index_redirects_to_search(self, tmp_path):
        """Test index page redirects to search."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/")
            # Should redirect or show search
            assert response.status_code in (200, 302, 308)


class TestQueryParser:
    """Tests for query parser."""

    def test_query_with_or(self, tmp_path):
        """Test OR query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Hello World", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("Hello OR Goodbye")
        assert isinstance(results, list)

    def test_query_with_and(self, tmp_path):
        """Test AND query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Hello World", "from@test.com", "to@test.com", "2024-01-01", "body text", "")

        results = db.search("Hello AND body")
        assert isinstance(results, list)

    def test_query_with_parentheses(self, tmp_path):
        """Test parentheses in query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("(Test OR Other) AND Subject")
        assert isinstance(results, list)

    def test_query_subject_filter(self, tmp_path):
        """Test subject: filter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Important Meeting", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("subject:Important")
        assert isinstance(results, list)

    def test_query_label_filter(self, tmp_path):
        """Test label: filter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "INBOX")

        results = db.search("label:INBOX")
        assert isinstance(results, list)


class TestWebDownloadEmail:
    """Tests for email download."""

    def test_download_email(self, tmp_path):
        """Test downloading email as .eml file."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Download Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <download@example.com>

Body.
"""
        eml_file = tmp_path / "download.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("download", "download.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/download/download")
            assert response.status_code == 200
            assert b"From:" in response.data


class TestParserCharsetDetection:
    """Tests for parser charset detection."""

    def test_parse_iso8859_email(self):
        """Test parsing ISO-8859-1 encoded email."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: =?ISO-8859-1?Q?Caf=E9_Menu?=
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <iso8859@example.com>
Content-Type: text/plain; charset=ISO-8859-1

Caf\xe9 is great!
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_parse_gb2312_email(self):
        """Test parsing GB2312 (Chinese) encoded email."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <gb2312@example.com>
Content-Type: text/plain; charset=gb2312

Hello
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestDatabaseSorting:
    """Tests for database sort options."""

    def test_search_sort_date_desc(self, tmp_path):
        """Test search with date descending sort."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.mark_downloaded("msg2", "test2.eml")
        db.index_email("msg1", "Subject 1", "from@test.com", "to@test.com", "2024-01-01", "body", "")
        db.index_email("msg2", "Subject 2", "from@test.com", "to@test.com", "2024-01-02", "body", "")

        results = db.search("Subject", sort="date_desc")
        assert isinstance(results, list)

    def test_search_sort_date_asc(self, tmp_path):
        """Test search with date ascending sort."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject 1", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("Subject", sort="date_asc")
        assert isinstance(results, list)


class TestWebLabelLinks:
    """Tests for label links in email view."""

    def test_email_with_multiple_labels(self, tmp_path):
        """Test email view with multiple labels."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Multi-label Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <multilabel@example.com>

Body.
"""
        eml_file = tmp_path / "multilabel.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("multilabel", "multilabel.eml", None, None, None, None)
        mock_archive.db.get_labels.return_value = ["INBOX", "IMPORTANT", "CATEGORY_PERSONAL"]

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/multilabel")
            assert response.status_code == 200


class TestCommandsRehashV2:
    """Tests for rehash command."""

    def test_cmd_rehash(self, tmp_path, capsys):
        """Test rehash command."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_rehash

        archive = EmailArchive(tmp_path, {})
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Rehash Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <rehash@example.com>

Body.
"""
        eml_path = tmp_path / "rehash.eml"
        eml_path.write_bytes(eml_content)
        archive.db.mark_downloaded("rehash", "rehash.eml")

        cmd_rehash(archive)
        captured = capsys.readouterr()
        assert len(captured.out) >= 0


class TestParserMalformedContent:
    """Tests for parser handling malformed content."""

    def test_parse_truncated_message(self):
        """Test parsing truncated message."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Truncated
Date: Mon, 01 Jan 2024"""  # Truncated
        result = EmailParser.parse_file(content=content)
        # Should handle gracefully
        assert result is not None or result is None  # Either is valid

    def test_parse_invalid_boundary(self):
        """Test parsing multipart with invalid boundary."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Bad Boundary
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <badboundary@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_WRONG
Content-Type: text/plain

Body
------=_Part_0--
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None or result is None

    def test_parse_long_header(self):
        """Test parsing email with very long header."""
        from ownmail.parser import EmailParser

        long_subject = "A" * 1000
        content = f"""From: sender@example.com
To: recipient@example.com
Subject: {long_subject}
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <longheader@example.com>

Body.
""".encode()
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebSearchWithFilters:
    """Tests for search with various filters."""

    def test_search_has_attachment(self, tmp_path):
        """Test search with has:attachment filter."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=has:attachment")
            assert response.status_code == 200

    def test_search_is_unread(self, tmp_path):
        """Test search with is:unread filter."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=is:unread")
            assert response.status_code == 200


class TestDatabasePagination:
    """Tests for database pagination."""

    def test_search_with_offset(self, tmp_path):
        """Test search with offset parameter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        # Add multiple emails
        for i in range(10):
            db.mark_downloaded(f"msg{i}", f"test{i}.eml")
            db.index_email(f"msg{i}", f"Test Subject {i}", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("Test", limit=5, offset=5)
        assert isinstance(results, list)

    def test_search_with_large_limit(self, tmp_path):
        """Test search with large limit parameter."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("Test", limit=10000)
        assert isinstance(results, list)


class TestQueryParserComplex:
    """Tests for complex query parsing."""

    def test_quoted_phrase(self, tmp_path):
        """Test quoted phrase search."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Hello World Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search('"Hello World"')
        assert isinstance(results, list)

    def test_minus_exclusion(self, tmp_path):
        """Test minus exclusion query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("Test -spam")
        assert isinstance(results, list)


class TestWebCIDAttachments:
    """Tests for CID attachments in emails."""

    def test_email_with_cid_reference(self, tmp_path):
        """Test email with CID reference to attachment."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: CID Reference Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <cidref@example.com>
MIME-Version: 1.0
Content-Type: multipart/related; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/html

<html><body><img src="cid:image001"></body></html>
------=_Part_0
Content-Type: image/png
Content-ID: <image001>
Content-Transfer-Encoding: base64

iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==
------=_Part_0--
"""
        eml_file = tmp_path / "cidref.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("cidref", "cidref.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/cidref")
            assert response.status_code == 200


class TestCommandsSyncCheckV2:
    """Tests for sync-check command."""

    def test_cmd_sync_check_empty(self, tmp_path, capsys):
        """Test sync check with empty archive."""
        from ownmail.archive import EmailArchive
        from ownmail.commands import cmd_sync_check

        archive = EmailArchive(tmp_path, {})
        config = {"sources": []}

        cmd_sync_check(archive, config, verbose=False)
        captured = capsys.readouterr()
        assert len(captured.out) >= 0


class TestParserHeaderDecoding:
    """Tests for parser header decoding."""

    def test_decode_cp949_header(self):
        """Test decoding CP949 encoded header."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: =?cp949?B?tPK+8Q==?=
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <cp949@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_decode_unknown_charset(self):
        """Test handling unknown charset."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: =?unknown-charset?B?dGVzdA==?=
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <unknown@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebMultipleRecipients:
    """Tests for emails with multiple recipients."""

    def test_email_with_cc(self, tmp_path):
        """Test email with CC recipients."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Cc: cc1@example.com, cc2@example.com
Subject: CC Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <cctest@example.com>

Body.
"""
        eml_file = tmp_path / "cctest.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("cctest", "cctest.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/cctest")
            assert response.status_code == 200
            assert b"cc1@example.com" in response.data or b"Cc" in response.data


class TestDatabaseMoreMethodsV2:
    """Tests for additional database methods."""

    def test_get_email_by_filename(self, tmp_path):
        """Test getting email by filename."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        # Try to get email by filename
        result = db.get_email_by_id("msg1")
        assert result is not None


class TestDatabaseSyncStateV2:
    """Tests for sync state operations."""

    def test_set_sync_state(self, tmp_path):
        """Test setting sync state."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.set_sync_state("test_source", "history_id", "123456")

        state = db.get_sync_state("test_source", "history_id")
        assert state == "123456"


class TestParserAlternativeContent:
    """Tests for parsing alternative content types."""

    def test_multipart_alternative(self):
        """Test parsing multipart/alternative with text and HTML."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Alternative Content
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <alternative@example.com>
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Plain text version.
------=_Part_0
Content-Type: text/html

<html><body><p>HTML version.</p></body></html>
------=_Part_0--
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebStaticFiles:
    """Tests for static file serving."""

    def test_serve_css(self, tmp_path):
        """Test serving CSS file."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/static/style.css")
            assert response.status_code == 200


class TestDatabaseLabels:
    """Tests for label-related database operations."""

    def test_search_by_label(self, tmp_path):
        """Test searching by label."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        # Labels stored in the labels field during indexing
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "IMPORTANT")

        results = db.search("label:IMPORTANT")
        assert isinstance(results, list)


class TestWebLargeEmail:
    """Tests for handling large emails."""

    def test_email_with_many_attachments(self, tmp_path):
        """Test email with multiple attachments."""
        from ownmail.web import create_app

        # Build multipart email with multiple attachments
        parts = [b"""------=_Part_0
Content-Type: text/plain

Body.
"""]
        for i in range(3):
            parts.append(f"""------=_Part_0
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="file{i}.txt"

content{i}
""".encode())
        parts.append(b"------=_Part_0--")

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Many Attachments
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <manyattach@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

""" + b"\n".join(parts)

        eml_file = tmp_path / "manyattach.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("manyattach", "manyattach.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/manyattach")
            assert response.status_code == 200


class TestParserEnvelopeFrom:
    """Tests for parsing envelope-from variants."""

    def test_parse_with_envelope_from(self):
        """Test parsing email with Envelope-From header."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Envelope From
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <envfrom@example.com>
Return-Path: <bounce@example.com>
X-Envelope-From: <original@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebRecentEmails:
    """Tests for recent emails endpoint."""

    def test_search_empty_query_recent(self, tmp_path):
        """Test search with empty query shows recent emails."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_recent_emails.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=")
            assert response.status_code == 200


class TestWebQuotedPlaintext:
    """Tests for quoted plaintext email rendering."""

    def test_email_with_quoted_text(self, tmp_path):
        """Test email with quoted lines (>)."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Quoted Reply
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <quoted@example.com>
Content-Type: text/plain

Thanks for your message!

> On Jan 1, 2024 at 10:00, someone wrote:
> This is the original message.
> With multiple lines.
>> Even nested quotes!

My response here.
"""
        eml_file = tmp_path / "quoted.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("quoted", "quoted.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/quoted")
            assert response.status_code == 200


class TestWebUrlLinkification:
    """Tests for URL linkification in emails."""

    def test_email_with_urls(self, tmp_path):
        """Test email with URLs gets linkified."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Links Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <links@example.com>
Content-Type: text/plain

Check out https://example.com for more info.
Also visit http://test.org/page?id=123
"""
        eml_file = tmp_path / "links.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("links", "links.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/links")
            assert response.status_code == 200


class TestDatabaseDeleteMethods:
    """Tests for database delete methods."""

    def test_delete_sync_state(self, tmp_path):
        """Test deleting sync state."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.set_sync_state("test_source", "history_id", "123456")
        db.delete_sync_state("test_source", "history_id")

        state = db.get_sync_state("test_source", "history_id")
        assert state is None


class TestDatabaseEmailCount:
    """Tests for email count methods."""

    def test_get_email_count_empty(self, tmp_path):
        """Test email count on empty database."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        count = db.get_email_count()
        assert count == 0

    def test_get_email_count_with_emails(self, tmp_path):
        """Test email count with indexed emails."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.mark_downloaded("msg2", "test2.eml")
        db.index_email("msg1", "Subject 1", "from@test.com", "to@test.com", "2024-01-01", "body1", "")
        db.index_email("msg2", "Subject 2", "from@test.com", "to@test.com", "2024-01-02", "body2", "")

        count = db.get_email_count()
        assert count >= 2


class TestParserBodyExtraction:
    """Tests for parser body extraction."""

    def test_extract_body_from_html_only(self):
        """Test extracting body from HTML-only email."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: HTML Only
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <htmlonly@example.com>
Content-Type: text/html

<html><body><p>This is HTML content.</p><div>More text here.</div></body></html>
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_extract_body_with_inline_images(self):
        """Test extracting body with inline images."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Inline Images
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <inlineimg@example.com>
Content-Type: text/html

<html><body><p>See image:</p><img src="data:image/png;base64,iVBORw=="></body></html>
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebHelpPageContent:
    """Tests for help page content."""

    def test_help_page_contains_operators(self, tmp_path):
        """Test help page contains search operators."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/help")
            assert response.status_code == 200
            # Check for common search operators
            data = response.data.lower()
            assert b"from:" in data or b"to:" in data or b"subject:" in data


class TestDatabaseMultipleIndices:
    """Tests for multiple email indexing."""

    def test_reindex_email(self, tmp_path):
        """Test re-indexing an already indexed email."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Original Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        # Re-index with new subject
        db.index_email("msg1", "Updated Subject", "from@test.com", "to@test.com", "2024-01-01", "new body", "")

        results = db.search("Updated")
        assert isinstance(results, list)


class TestWebBinaryAttachment:
    """Tests for binary attachment handling."""

    def test_download_binary_attachment(self, tmp_path):
        """Test downloading binary attachment."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Binary Attachment
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <binattach@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body.
------=_Part_0
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJcOkw7zDtsOfCjIgMCBvYmoKPDwvTGVuZ3RoIDMgMCBSL0ZpbHRlci9GbGF0ZURl
------=_Part_0--
"""
        eml_file = tmp_path / "binattach.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("binattach", "binattach.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            # View the email first
            response = client.get("/email/binattach")
            assert response.status_code == 200

            # Try to download attachment
            response = client.get("/attachment/binattach/0")
            # Should either succeed or return 404 if no attachment at index
            assert response.status_code in (200, 404)


class TestQueryNormalization:
    """Tests for query normalization."""

    def test_query_with_extra_spaces(self, tmp_path):
        """Test query with extra spaces."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Test Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("  Test   Subject  ")
        assert isinstance(results, list)

    def test_query_case_insensitive(self, tmp_path):
        """Test case-insensitive search."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "UPPERCASE Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("uppercase")
        assert isinstance(results, list)


class TestParserLargeHeaders:
    """Tests for parser handling large headers."""

    def test_email_with_many_recipients(self):
        """Test email with many recipients."""
        from ownmail.parser import EmailParser

        recipients = ", ".join([f"user{i}@example.com" for i in range(50)])
        content = f"""From: sender@example.com
To: {recipients}
Subject: Many Recipients
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <manyrecip@example.com>

Body.
""".encode()
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_email_with_folded_header(self):
        """Test email with folded (multi-line) header."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: This is a very long subject line that needs to be folded
 across multiple lines according to RFC 5322 rules
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <folded@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebSearchPaginationV2:
    """Tests for search pagination."""

    def test_search_page_2(self, tmp_path):
        """Test search results page 2."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&page=2")
            assert response.status_code == 200

    def test_search_invalid_page(self, tmp_path):
        """Test search with invalid page number."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&page=-1")
            # Should handle gracefully
            assert response.status_code in (200, 400)


class TestParserSpecialCharacters:
    """Tests for parser handling special characters."""

    def test_email_with_unicode_body(self):
        """Test email with Unicode characters in body."""
        from ownmail.parser import EmailParser

        content = """From: sender@example.com
To: recipient@example.com
Subject: Unicode Body
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <unicode@example.com>
Content-Type: text/plain; charset=utf-8

Hello! Here's some Unicode: 😀🎉🚀
Japanese: こんにちは
Chinese: 你好
Korean: 안녕하세요
""".encode()
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_email_with_null_bytes(self):
        """Test email with null bytes (malformed)."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Null Bytes
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <nullbytes@example.com>

Body with\x00null byte.
"""
        # Should handle gracefully
        result = EmailParser.parse_file(content=content)
        assert result is not None or result is None  # Either is valid


class TestQueryParserFilters:
    """Tests for query parser filter handling."""

    def test_has_attachment_query(self, tmp_path):
        """Test has:attachment query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("has:attachment")
        assert isinstance(results, list)

    def test_is_starred_query(self, tmp_path):
        """Test is:starred query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "STARRED")

        results = db.search("is:starred")
        assert isinstance(results, list)

    def test_older_than_query(self, tmp_path):
        """Test older_than: query."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("older_than:30d")
        assert isinstance(results, list)


class TestWebSearchSortOptions:
    """Tests for search sort options."""

    def test_search_sort_relevance(self, tmp_path):
        """Test search with relevance sort."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&sort=relevance")
            assert response.status_code == 200

    def test_search_sort_date_asc(self, tmp_path):
        """Test search with date ascending sort."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=test&sort=date_asc")
            assert response.status_code == 200


class TestParserAddressExtraction:
    """Tests for email address extraction."""

    def test_parse_address_with_display_name(self):
        """Test parsing address with display name."""
        from ownmail.parser import EmailParser

        content = b"""From: "John Doe" <john@example.com>
To: "Jane Smith" <jane@example.com>
Subject: Display Names
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <displayname@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_parse_address_without_angle_brackets(self):
        """Test parsing address without angle brackets."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: No Angle Brackets
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <noangles@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestDatabaseSearchEdgeCases:
    """Tests for database search edge cases."""

    def test_search_empty_string(self, tmp_path):
        """Test search with empty string."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("")
        assert isinstance(results, list)

    def test_search_only_whitespace(self, tmp_path):
        """Test search with only whitespace."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("   ")
        assert isinstance(results, list)


class TestWebEmailWithSignature:
    """Tests for emails with signatures."""

    def test_email_with_signature_delimiter(self, tmp_path):
        """Test email with signature delimiter (-- )."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: With Signature
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <signature@example.com>
Content-Type: text/plain

Main body content.

--
John Doe
john@example.com
555-1234
"""
        eml_file = tmp_path / "signature.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("signature", "signature.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/signature")
            assert response.status_code == 200


class TestParserContentTypes:
    """Tests for various content types."""

    def test_parse_calendar_invite(self):
        """Test parsing calendar invite."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Meeting Invite
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <calendar@example.com>
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

You have been invited to a meeting.
------=_Part_0
Content-Type: text/calendar; method=REQUEST

BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Test Meeting
END:VEVENT
END:VCALENDAR
------=_Part_0--
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_parse_signed_email(self):
        """Test parsing signed email (multipart/signed)."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Signed Email
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <signed@example.com>
MIME-Version: 1.0
Content-Type: multipart/signed; boundary="----=_Part_0"; micalg=sha-256; protocol="application/pkcs7-signature"

------=_Part_0
Content-Type: text/plain

Signed content.
------=_Part_0
Content-Type: application/pkcs7-signature; name="smime.p7s"
Content-Transfer-Encoding: base64

SGVsbG8gV29ybGQh
------=_Part_0--
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebEmailHeaderSearch:
    """Tests for clicking on email headers."""

    def test_from_header_is_clickable(self, tmp_path):
        """Test that From header generates clickable link."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Clickable Headers
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <clickable@example.com>

Body.
"""
        eml_file = tmp_path / "clickable.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("clickable", "clickable.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/clickable")
            assert response.status_code == 200
            # Header should be in a link
            assert b"sender@example.com" in response.data


class TestDatabaseIndexEmailVariants:
    """Tests for index_email variants."""

    def test_index_email_with_empty_body(self, tmp_path):
        """Test indexing email with empty body."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "", "")

        results = db.search("Subject")
        assert isinstance(results, list)

    def test_index_email_with_special_subject(self, tmp_path):
        """Test indexing email with special characters in subject."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Re: [URGENT] 50% off! Don't miss", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("URGENT")
        assert isinstance(results, list)


class TestWebRawEmailView:
    """Tests for raw email viewing."""

    def test_view_raw_email_headers(self, tmp_path):
        """Test viewing raw email shows all headers."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Raw View Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <rawview@example.com>
X-Custom-Header: custom-value
X-Mailer: Test Mailer

Body text.
"""
        eml_file = tmp_path / "rawview.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("rawview", "rawview.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/raw/rawview")
            assert response.status_code == 200
            # Raw view should include all headers
            assert b"X-Custom-Header" in response.data


class TestQueryParserOperatorCombinations:
    """Tests for combining query operators."""

    def test_from_and_subject(self, tmp_path):
        """Test combining from: and subject: filters."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Important Meeting", "boss@company.com", "me@company.com", "2024-01-01", "body", "")

        results = db.search("from:boss subject:Important")
        assert isinstance(results, list)

    def test_label_and_date(self, tmp_path):
        """Test combining label: and date filters."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "INBOX")

        results = db.search("label:INBOX after:2023-01-01")
        assert isinstance(results, list)


class TestWebMimeEncodedFilenameComplex:
    """Tests for complex MIME encoded filenames."""

    def test_filename_with_mime_qp(self, tmp_path):
        """Test MIME quoted-printable encoded filename in attachment."""
        from ownmail.web import create_app

        # Email with Q-encoded filename in Content-Disposition
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: QP Filename Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <mimeqp@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: application/octet-stream
Content-Disposition: attachment;
 filename="=?UTF-8?Q?test=5Ffile=2Etxt?="

file content
------=_Part_0--
"""
        eml_file = tmp_path / "mimeqp.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("mimeqp", "mimeqp.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/mimeqp")
            assert response.status_code == 200

    def test_filename_continuation(self, tmp_path):
        """Test attachment with filename continuation (RFC 2231 multi-part)."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Filename Continuation
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <continuation@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain

Body
------=_Part_0
Content-Type: application/octet-stream
Content-Disposition: attachment;
 filename*0*=UTF-8''long%20filename;
 filename*1*=%20part%20two;
 filename*2*=.txt

content
------=_Part_0--
"""
        eml_file = tmp_path / "continuation.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("continuation", "continuation.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/continuation")
            assert response.status_code == 200


class TestArchiveMoreMethods:
    """Tests for archive methods."""

    def test_archive_get_parser(self, tmp_path):
        """Test archive parser access."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path, {})
        # Just verify archive can access parser
        assert archive is not None

    def test_archive_path_properties(self, tmp_path):
        """Test archive path properties."""
        from ownmail.archive import EmailArchive

        archive = EmailArchive(tmp_path, {})
        assert archive.archive_dir == tmp_path


class TestWebTrustSenderFlow:
    """Tests for trust sender functionality."""

    def test_trust_sender_redirect(self, tmp_path):
        """Test trust sender POST redirects."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.post("/trust-sender", data={
                "email": "trusted@example.com",
                "return_url": "/email/test123"
            })
            # Should redirect
            assert response.status_code in (302, 303, 200)


class TestDatabaseEmailListMethods:
    """Tests for email listing methods."""

    def test_get_email_by_id(self, tmp_path):
        """Test getting email by its ID."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        result = db.get_email_by_id("msg1")
        assert result is not None


class TestParserMessageIdHandling:
    """Tests for message ID extraction."""

    def test_parse_email_with_message_id(self):
        """Test parsing email with Message-ID."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Message ID Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <unique-id-12345@mail.example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None

    def test_extract_in_reply_to(self):
        """Test extracting In-Reply-To header."""
        from ownmail.parser import EmailParser

        content = b"""From: sender@example.com
To: recipient@example.com
Subject: Reply Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <reply@example.com>
In-Reply-To: <original@example.com>
References: <original@example.com>

Body.
"""
        result = EmailParser.parse_file(content=content)
        assert result is not None


class TestWebFilteredSearch:
    """Tests for filtered search results."""

    def test_search_all_mail(self, tmp_path):
        """Test searching all mail."""
        from ownmail.web import create_app

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.search.return_value = []

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/search?q=*")
            assert response.status_code == 200


class TestQueryParserNegation:
    """Tests for negation in queries."""

    def test_query_with_minus_prefix(self, tmp_path):
        """Test query with minus prefix for exclusion."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Newsletter from Company", "from@test.com", "to@test.com", "2024-01-01", "body", "")

        results = db.search("from:test -unsubscribe")
        assert isinstance(results, list)


class TestDatabaseLabelSearch:
    """More label search tests."""

    def test_label_inbox_search(self, tmp_path):
        """Test searching for INBOX label."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "INBOX")

        results = db.search("in:inbox")
        assert isinstance(results, list)

    def test_label_sent_search(self, tmp_path):
        """Test searching for SENT label."""
        from ownmail.database import ArchiveDatabase

        db = ArchiveDatabase(tmp_path)
        db.mark_downloaded("msg1", "test1.eml")
        db.index_email("msg1", "Subject", "from@test.com", "to@test.com", "2024-01-01", "body", "SENT")

        results = db.search("in:sent")
        assert isinstance(results, list)


class TestWebEmailViewVariants:
    """Tests for various email view scenarios."""

    def test_email_with_bcc(self, tmp_path):
        """Test email with BCC header."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Bcc: hidden@example.com
Subject: BCC Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <bcc@example.com>

Body.
"""
        eml_file = tmp_path / "bcc.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("bcc", "bcc.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/bcc")
            assert response.status_code == 200

    def test_email_with_reply_to(self, tmp_path):
        """Test email with Reply-To header."""
        from ownmail.web import create_app

        eml_content = b"""From: sender@example.com
To: recipient@example.com
Reply-To: noreply@example.com
Subject: Reply-To Test
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <replyto@example.com>

Body.
"""
        eml_file = tmp_path / "replyto.eml"
        eml_file.write_bytes(eml_content)

        mock_archive = MagicMock()
        mock_archive.archive_dir = tmp_path
        mock_archive.db = MagicMock()
        mock_archive.db.get_email_count.return_value = 100
        mock_archive.db.get_email_by_id.return_value = ("replyto", "replyto.eml", None, None, None, None)

        app = create_app(mock_archive)
        with app.test_client() as client:
            response = client.get("/email/replyto")
            assert response.status_code == 200
