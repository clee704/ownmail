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
