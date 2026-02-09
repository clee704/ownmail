"""Web interface for browsing and searching the email archive."""

import email
import email.header
import re
import time
from email.policy import default as email_policy

from flask import Flask, abort, g, redirect, render_template_string, request, send_file

from ownmail.archive import EmailArchive
from ownmail.parser import EmailParser

# Regex to find external images in HTML
EXTERNAL_IMAGE_RE = re.compile(
    r'<img\s+([^>]*\s)?src\s*=\s*["\']?(https?://[^"\'>\s]+)["\']?',
    re.IGNORECASE,
)

# Regex to extract charset from HTML meta tag
# Matches: <meta charset="euc-kr"> or <meta http-equiv="Content-Type" content="text/html; charset=euc-kr">
HTML_CHARSET_RE = re.compile(
    r'<meta[^>]+charset\s*=\s*["\']?([a-zA-Z0-9_-]+)',
    re.IGNORECASE,
)

# Charset aliases for Korean encodings
CHARSET_ALIASES = {
    "ks_c_5601-1987": "cp949",
    "euc-kr": "euc-kr",
    "euc_kr": "euc-kr",
}


def decode_header(value) -> str:
    """Decode MIME encoded header (RFC 2047).

    Args:
        value: Header value (can be str, Header object, or None)

    Returns:
        Decoded string
    """
    if not value:
        return ""
    # Handle Header objects by converting to string first
    if hasattr(value, '__str__') and not isinstance(value, str):
        value = str(value)
    if not isinstance(value, str):
        return ""
    try:
        decoded_parts = email.header.decode_header(value)
        result = []
        for data, charset in decoded_parts:
            if isinstance(data, bytes):
                # Try the declared charset first, then common fallbacks
                charsets_to_try = [charset] if charset else []
                charsets_to_try.extend(['utf-8', 'euc-kr', 'cp949', 'iso-2022-kr', 'latin-1'])
                decoded = None
                for cs in charsets_to_try:
                    if cs:
                        try:
                            decoded = data.decode(cs)
                            break
                        except (UnicodeDecodeError, LookupError):
                            continue
                if decoded is None:
                    decoded = data.decode('utf-8', errors='replace')
                result.append(decoded)
            else:
                result.append(data)
        return "".join(result)
    except Exception:
        return str(value) if value else ""


def _extract_snippet(msg: email.message.Message, max_len: int = 150) -> str:
    """Extract a text snippet from email body for preview."""
    try:
        # Try to get plain text part first
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        text = _decode_text_body(payload, part.get_content_charset())
                        # Clean up whitespace
                        text = " ".join(text.split())
                        return text[:max_len] + "..." if len(text) > max_len else text
        else:
            if msg.get_content_type() == "text/plain":
                payload = msg.get_payload(decode=True)
                if payload:
                    text = _decode_text_body(payload, msg.get_content_charset())
                    text = " ".join(text.split())
                    return text[:max_len] + "..." if len(text) > max_len else text
    except Exception:
        pass
    return ""


def _validate_decoded_text(text: str, min_readable_ratio: float = 0.7) -> bool:
    """Check if decoded text looks like valid readable content.

    Args:
        text: Decoded text to validate
        min_readable_ratio: Minimum ratio of readable characters

    Returns:
        True if text appears to be valid readable content
    """
    if not text:
        return False

    # Check for replacement characters (decoding failed)
    if '\ufffd' in text:
        return False

    # Count readable vs unreadable characters
    readable = 0
    total = 0

    for char in text[:1000]:  # Sample first 1000 chars
        code = ord(char)
        total += 1

        # Consider readable:
        # - ASCII printable, whitespace
        # - Latin extended (accented chars)
        # - CJK characters (Chinese, Japanese, Korean)
        # - Common punctuation and symbols
        if (0x20 <= code <= 0x7E or  # ASCII printable
            code in (0x09, 0x0A, 0x0D) or  # tab, newline, CR
            0x80 <= code <= 0xFF or  # Latin extended
            0x4E00 <= code <= 0x9FFF or  # CJK Unified Ideographs
            0xAC00 <= code <= 0xD7AF or  # Hangul Syllables
            0x1100 <= code <= 0x11FF or  # Hangul Jamo
            0x3040 <= code <= 0x309F or  # Hiragana
            0x30A0 <= code <= 0x30FF or  # Katakana
            0x3000 <= code <= 0x303F or  # CJK Punctuation
            0xFF00 <= code <= 0xFFEF):   # Fullwidth forms
            readable += 1

    if total == 0:
        return True

    return (readable / total) >= min_readable_ratio


def _try_decode(payload: bytes, encoding: str) -> str | None:
    """Try to decode payload with given encoding and validate result."""
    try:
        decoded = payload.decode(encoding)
        if _validate_decoded_text(decoded):
            return decoded
    except (UnicodeDecodeError, LookupError):
        pass
    return None


def _decode_text_body(payload: bytes, header_charset: str | None) -> str:
    """Decode plain text body with smart charset detection.

    Args:
        payload: Raw bytes of text content
        header_charset: Charset from Content-Type header (may be None)

    Returns:
        Decoded text string
    """
    # If header specifies charset, try it first with validation
    if header_charset:
        charset = CHARSET_ALIASES.get(header_charset.lower(), header_charset)
        result = _try_decode(payload, charset)
        if result is not None:
            return result
        # Header charset didn't produce valid result - fall through to auto-detection

    # Check if payload has high bytes (non-ASCII) suggesting CJK encoding
    # Sample multiple regions since Korean content may not appear in first 500 bytes
    sample_size = min(len(payload), 4000)
    high_bytes = sum(1 for b in payload[:sample_size] if b >= 0x80)

    if high_bytes > 10:
        # Has significant non-ASCII content - try various encodings
        # and validate the result makes sense
        for encoding in ['utf-8', 'cp949', 'euc-kr', 'gb2312', 'gbk',
                         'big5', 'shift_jis', 'euc-jp']:
            result = _try_decode(payload, encoding)
            if result is not None:
                return result

    # Try common encodings with validation
    for encoding in ['utf-8', 'iso-8859-1', 'cp1252']:
        result = _try_decode(payload, encoding)
        if result is not None:
            return result

    return payload.decode("utf-8", errors="replace")


def _decode_html_body(payload: bytes, header_charset: str | None) -> str:
    """Decode HTML body with charset detection from meta tag fallback.

    Args:
        payload: Raw bytes of HTML content
        header_charset: Charset from Content-Type header (may be None)

    Returns:
        Decoded HTML string
    """
    # If header specifies charset, use it (with alias mapping)
    if header_charset:
        charset = CHARSET_ALIASES.get(header_charset.lower(), header_charset)
        try:
            decoded = payload.decode(charset)
            if _validate_decoded_text(decoded):
                return decoded
        except (LookupError, UnicodeDecodeError):
            pass

    # No header charset - try to detect from HTML meta tag
    # First, do a quick ASCII-safe decode to find the meta tag
    try:
        # Use latin-1 which maps bytes 1:1 to preserve raw bytes for regex
        raw_html = payload.decode("latin-1")
        match = HTML_CHARSET_RE.search(raw_html[:2048])  # Only check first 2KB
        if match:
            meta_charset = match.group(1).lower()
            charset = CHARSET_ALIASES.get(meta_charset, meta_charset)
            try:
                decoded = payload.decode(charset)
                if _validate_decoded_text(decoded):
                    return decoded
            except (LookupError, UnicodeDecodeError):
                pass
    except Exception:
        pass

    # No charset found - try smart detection like plain text
    # Sample multiple regions since Korean content may not appear in first 500 bytes
    sample_size = min(len(payload), 4000)
    high_bytes = sum(1 for b in payload[:sample_size] if b >= 0x80)

    if high_bytes > 10:
        # Has significant non-ASCII content - try various encodings
        for encoding in ['utf-8', 'cp949', 'euc-kr', 'gb2312', 'gbk',
                         'big5', 'shift_jis', 'euc-jp']:
            result = _try_decode(payload, encoding)
            if result is not None:
                return result

    # Try common encodings with validation
    for encoding in ['utf-8', 'iso-8859-1', 'cp1252']:
        result = _try_decode(payload, encoding)
        if result is not None:
            return result

    # Last resort
    return payload.decode("utf-8", errors="replace")


def block_external_images(html: str) -> tuple[str, bool]:
    """Block external images in HTML by replacing src with data-src.

    Args:
        html: HTML content

    Returns:
        Tuple of (modified HTML, whether external images were found)
    """
    has_external = bool(EXTERNAL_IMAGE_RE.search(html))
    if not has_external:
        return html, False

    def replace_src(match):
        prefix = match.group(1) or ""
        url = match.group(2)
        return f'<img {prefix}data-src="{url}" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"'

    blocked_html = EXTERNAL_IMAGE_RE.sub(replace_src, html)
    return blocked_html, True


def parse_email_address(addr: str) -> tuple:
    """Parse email address into (name, email) tuple.

    Args:
        addr: Email address string like "John Doe <john@example.com>" or "john@example.com"

    Returns:
        Tuple of (name, email) where name may be empty
    """
    if not addr:
        return ("", "")

    # Try to match "Name <email>" format
    match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>$', addr.strip())
    if match:
        name = match.group(1).strip()
        email_addr = match.group(2).strip()
        return (name, email_addr)

    # Try to match just email
    match = re.match(r'^<?([^@\s]+@[^>\s]+)>?$', addr.strip())
    if match:
        return ("", match.group(1))

    return ("", "")


def parse_recipients(recipients_str: str) -> list:
    """Parse recipients string into list of parsed addresses.

    Args:
        recipients_str: Comma-separated recipients

    Returns:
        List of dicts with 'name', 'email', 'raw' keys
    """
    if not recipients_str:
        return []

    result = []
    # Split on comma but be careful of commas inside quotes
    parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', recipients_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        name, email_addr = parse_email_address(part)
        result.append({
            "name": name,
            "email": email_addr,
            "raw": part,
        })
    return result


class LRUCache:
    """Simple LRU cache with TTL."""

    def __init__(self, maxsize: int = 100, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl  # seconds
        self.cache = {}  # key -> (value, timestamp)
        self.order = []  # keys in access order

    def get(self, key):
        """Get value from cache, or None if not found/expired."""
        if key not in self.cache:
            return None
        value, timestamp = self.cache[key]
        if time.time() - timestamp > self.ttl:
            # Expired
            del self.cache[key]
            if key in self.order:
                self.order.remove(key)
            return None
        # Move to end (most recently used)
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)
        return value

    def set(self, key, value):
        """Set value in cache."""
        # Remove oldest if at capacity
        while len(self.cache) >= self.maxsize and self.order:
            oldest = self.order.pop(0)
            if oldest in self.cache:
                del self.cache[oldest]
        self.cache[key] = (value, time.time())
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)


def create_app(
    archive: EmailArchive,
    verbose: bool = False,
    block_images: bool = False,
    page_size: int = 20,
    trusted_senders: list = None,
    config_path: str = None,
) -> Flask:
    """Create the Flask application.

    Args:
        archive: EmailArchive instance
        verbose: Enable request timing logs
        block_images: Block external images by default
        page_size: Number of results per page
        trusted_senders: List of email addresses to always show images from
        config_path: Path to config.yaml for updating trusted senders

    Returns:
        Flask application
    """
    app = Flask(__name__)
    app.config["archive"] = archive
    app.config["verbose"] = verbose
    app.config["block_images"] = block_images
    app.config["page_size"] = page_size
    app.config["trusted_senders"] = {s.lower() for s in (trusted_senders or [])}
    app.config["config_path"] = config_path

    # Cache for stats (refreshed every 60 seconds)
    stats_cache = {"value": None, "time": 0}

    # Cache for search results (100 queries, 5 min TTL)
    search_cache = LRUCache(maxsize=100, ttl=300)

    # Cache for parsed emails (50 emails, 10 min TTL)
    email_cache = LRUCache(maxsize=50, ttl=600)

    def get_cached_stats():
        """Get stats with caching to avoid slow DB queries on every request."""
        now = time.time()
        if stats_cache["value"] is None or now - stats_cache["time"] > 60:
            if verbose:
                print("[verbose] Refreshing stats cache...", flush=True)
            start = time.time()
            # Use fast email count instead of slow get_stats
            total = archive.db.get_email_count()
            stats_cache["value"] = {"total_emails": total}
            stats_cache["time"] = now
            if verbose:
                print(f"[verbose] Stats query took {time.time()-start:.2f}s", flush=True)
        return stats_cache["value"]

    if verbose:
        @app.before_request
        def before_request():
            g.start_time = time.time()

        @app.after_request
        def after_request(response):
            if hasattr(g, "start_time"):
                elapsed = time.time() - g.start_time
                print(f"[{request.method}] {request.path} - {elapsed:.2f}s", flush=True)
            return response

    # HTML Templates
    BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}ownmail{% endblock %}</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }
        header h1 { margin: 0; font-size: 1.5em; }
        header h1 a { color: inherit; text-decoration: none; }
        .stats { color: #666; font-size: 0.9em; }
        .sticky-header {
            position: sticky;
            top: 0;
            background: #f5f5f5;
            z-index: 100;
            padding: 15px 20px 5px 20px;
            margin: -10px -20px 0 -20px;
        }
        .search-form {
            display: flex;
            gap: 10px;
            margin-bottom: 8px;
        }
        .search-form input[type="text"] {
            flex: 1;
            padding: 10px 15px;
            font-size: 16px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .search-form button {
            padding: 10px 20px;
            font-size: 16px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        .search-form button:hover { background: #0052a3; }
        .sort-select {
            padding: 10px 15px;
            font-size: 16px;
            border: 1px solid #ddd;
            border-radius: 5px;
            background: white;
            cursor: pointer;
        }
        .email-list { list-style: none; padding: 0; margin: 0; }
        .email-item {
            background: white;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }
        .email-item:hover { border-color: #0066cc; }
        .email-item a { text-decoration: none; color: inherit; display: block; }
        .email-subject { font-weight: 600; margin-bottom: 5px; color: #0066cc; }
        .email-meta { font-size: 0.9em; color: #666; }
        .email-snippet { font-size: 0.9em; color: #888; margin-top: 5px; }
        .email-detail {
            background: white;
            padding: 20px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }
        .email-header { margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
        .email-header h2 { margin: 0 0 10px 0; }
        .email-header-row { margin: 5px 0; }
        .email-header-label { font-weight: 600; display: inline-block; width: 80px; }
        .email-body {
            white-space: pre-wrap;
            font-family: inherit;
            line-height: 1.6;
        }
        .email-body-html {
            width: 100%;
            min-height: 300px;
            border: none;
            background: white;
        }
        .back-link { margin-bottom: 15px; margin-top: 15px; }
        .back-link a { color: #0066cc; text-decoration: none; }
        .back-link a:hover { text-decoration: underline; }
        .no-results { color: #666; text-align: center; padding: 40px; }
        .search-error {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .search-error p { margin: 10px 0 0 0; font-size: 0.9em; }
        .attachments { margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; }
        .attachments h4 { margin: 0 0 10px 0; }
        .attachment-list { list-style: none; padding: 0; }
        .attachment-item { padding: 5px 0; }
        .attachment-item a { color: #0066cc; }
        .labels { margin-top: 10px; }
        .label {
            display: inline-block;
            background: #e0e0e0;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8em;
            margin-right: 5px;
        }
        .clickable-label {
            text-decoration: none;
            color: inherit;
            cursor: pointer;
        }
        .clickable-label:hover {
            background: #c0c0c0;
        }
        .clickable-header {
            color: #0066cc;
            text-decoration: none;
        }
        .clickable-header:hover {
            text-decoration: underline;
        }
        .help { font-size: 0.85em; color: #666; margin-top: 10px; }
        .help a { color: #0066cc; }
        .help-page { max-width: 700px; margin: 0 auto; }
        .help-page h2 { margin-bottom: 20px; }
        .help-page h3 { margin-top: 25px; margin-bottom: 10px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 5px; }
        .help-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
        .help-table td { padding: 8px; border-bottom: 1px solid #eee; }
        .help-table td:first-child { width: 45%; font-family: monospace; background: #f8f8f8; }
        .help-table code { background: transparent; }
        .pagination {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin: 20px 0;
        }
        .pagination.pagination-bottom {
            justify-content: flex-end;
        }
        .pagination a, .pagination span {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            text-decoration: none;
            color: #0066cc;
        }
        .pagination a:hover { background: #e8f0fe; }
        .pagination .current {
            background: #0066cc;
            color: white;
            border-color: #0066cc;
        }
        .pagination .disabled {
            color: #999;
            cursor: default;
        }
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: end;
            padding: 0;
            margin: 10px 0;
        }
        .results-header p { margin: 0; color: #666; }
        .results-header .pagination { margin: 0; }
        .image-banner {
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 10px 15px;
            border-radius: 5px;
            margin-bottom: 15px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            justify-content: space-between;
        }
        .image-banner button {
            background: #0066cc;
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 3px;
            cursor: pointer;
        }
        .image-banner button:hover { background: #0052a3; }
        .image-banner .trust-btn {
            background: #28a745;
        }
        .image-banner .trust-btn:hover { background: #1e7e34; }
        .image-banner .undo-btn {
            background: #ffc107;
            color: #212529;
        }
        .image-banner .undo-btn:hover { background: #e0a800; }
        /* Loading overlay */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        .loading-overlay.show { display: flex; }
        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #ddd;
            border-top-color: #0066cc;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .loading-text {
            margin-top: 15px;
            color: #666;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="loading-overlay" id="loading">
        <div class="spinner"></div>
        <div class="loading-text" id="loading-text">Loading...</div>
    </div>
    <header>
        <h1><a href="/">📧 ownmail</a></h1>
        <div class="stats">{{ stats.total_emails | default(0) }} emails archived</div>
    </header>
    {% block content %}{% endblock %}
    <script>
    function showLoading(text) {
        document.getElementById('loading-text').textContent = text || 'Loading...';
        document.getElementById('loading').classList.add('show');
    }
    function hideLoading() {
        document.getElementById('loading').classList.remove('show');
    }
    // Hide loading on pageshow (handles back button with bfcache)
    window.addEventListener('pageshow', function(event) {
        hideLoading();
    });
    // Show loading on search form submit
    document.addEventListener('DOMContentLoaded', function() {
        var form = document.querySelector('.search-form');
        if (form) {
            form.addEventListener('submit', function() {
                showLoading('Searching...');
            });
        }
        // Show loading on email link clicks (but not for cmd/ctrl+click which opens in new tab)
        document.querySelectorAll('.email-item a').forEach(function(link) {
            link.addEventListener('click', function(e) {
                if (!e.metaKey && !e.ctrlKey) {
                    showLoading('Loading email...');
                }
            });
        });
        // Show loading on pagination clicks (but not for cmd/ctrl+click)
        document.querySelectorAll('.pagination a').forEach(function(link) {
            link.addEventListener('click', function(e) {
                if (!e.metaKey && !e.ctrlKey) {
                    showLoading('Loading...');
                }
            });
        });
    });
    </script>
</body>
</html>
"""

    SEARCH_TEMPLATE = BASE_TEMPLATE.replace(
        "{% block title %}ownmail{% endblock %}",
        "{% block title %}Search - ownmail{% endblock %}"
    ).replace(
        "{% block content %}{% endblock %}",
        """{% block content %}
    <div class="sticky-header">
    <form class="search-form" action="/search" method="get">
        <input type="text" name="q" id="search-input" value="{{ query | default('') }}" placeholder="Search emails..." autofocus>
        <select name="sort" class="sort-select" id="sort-select">
            <option value="relevance" id="relevance-option" {{ 'selected' if sort == 'relevance' else '' }}{% if hide_relevance %} disabled{% endif %}>Relevance</option>
            <option value="date_desc" {{ 'selected' if sort == 'date_desc' else '' }}>Newest first</option>
            <option value="date_asc" {{ 'selected' if sort == 'date_asc' else '' }}>Oldest first</option>
        </select>
        <button type="submit">Search</button>
    </form>
    <script>
    // Enable/disable Relevance option based on search input
    (function() {
        var input = document.getElementById('search-input');
        var relevanceOpt = document.getElementById('relevance-option');
        var sortSelect = document.getElementById('sort-select');

        function updateRelevanceOption() {
            var query = input.value.trim();
            // Remove date/label filters to check for FTS terms
            var withoutFilters = query
                .replace(/\\b(before|after):\\d{4}-?\\d{2}-?\\d{2}\\b/gi, '')
                .replace(/\\b(label|tag):\\S+\\b/gi, '')
                .replace(/\\bAND\\b/gi, '')
                .trim();
            var hasFtsTerms = withoutFilters.length > 0;

            relevanceOpt.disabled = !hasFtsTerms;

            // If relevance is selected but disabled, switch to date_desc
            if (!hasFtsTerms && sortSelect.value === 'relevance') {
                sortSelect.value = 'date_desc';
            }
        }

        input.addEventListener('input', updateRelevanceOption);
        // Run on page load too
        updateRelevanceOption();
    })();
    </script>
    <div class="help">
        Search: <code>from:</code> <code>subject:</code> <code>attachment:</code> <code>before:2024-01-01</code> <code>after:2023-06-15</code> <code>label:INBOX</code>
        &bull; <a href="/help">Syntax help</a>
    </div>
    {% if results %}
        <div class="results-header">
            <p>{% if query %}Showing{% else %}Recent emails:{% endif %} {{ start_idx + 1 }}&ndash;{{ start_idx + results|length }}{% if has_more %}+{% endif %}{% if query %} (took {{ "%.2f"|format(search_time) }}s){% endif %}</p>
            {% if has_prev or has_more %}
            <div class="pagination">
                {% if has_prev %}
                    <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page - 1 }}">&laquo; Previous</a>
                {% endif %}
                <span class="current">Page {{ page }}</span>
                {% if has_more %}
                        <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page + 1 }}">Next &raquo;</a>
                    {% endif %}
                </div>
                {% endif %}
            </div>
    {% endif %}
    </div>

    {% if search_error %}
        <div class="search-error">
            <strong>Search error:</strong> {{ search_error }}
            <p>Try quoting phrases with special characters, e.g., <code>"tpc-ds"</code></p>
        </div>
    {% elif results %}
            <ul class="email-list">
            {% for result in results %}
                <li class="email-item">
                    <a href="/email/{{ result.message_id }}">
                        <div class="email-subject">{{ result.subject or '(No subject)' }}</div>
                        <div class="email-meta">
                            From: {{ result.sender }} &bull; {{ result.date_str }}
                        </div>
                        <div class="email-snippet">{{ result.snippet }}</div>
                    </a>
                </li>
            {% endfor %}
            </ul>
            {% if has_prev or has_more %}
            <div class="pagination pagination-bottom">
                {% if has_prev %}
                    <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page - 1 }}">&laquo; Previous</a>
                {% endif %}
                <span class="current">Page {{ page }}</span>
                {% if has_more %}
                    <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page + 1 }}">Next &raquo;</a>
                {% endif %}
            </div>
            {% endif %}
    {% elif query %}
        <div class="no-results">No results found for "{{ query }}"</div>
    {% endif %}
{% endblock %}"""
    )
    HELP_TEMPLATE = BASE_TEMPLATE.replace(
        "{% block title %}ownmail{% endblock %}",
        "{% block title %}Search Help - ownmail{% endblock %}"
    ).replace(
        "{% block content %}{% endblock %}",
        """{% block content %}
    <div class="back-link"><a href="javascript:history.back()">&larr; Back to search</a></div>
    <div class="help-page">
        <h2>Search Syntax</h2>

        <h3>Field Filters</h3>
        <table class="help-table">
            <tr><td><code>from:user@example.com</code></td><td>Emails from this address</td></tr>
            <tr><td><code>to:user@example.com</code></td><td>Emails to this address</td></tr>
            <tr><td><code>subject:meeting</code></td><td>Emails with "meeting" in subject</td></tr>
            <tr><td><code>attachment:pdf</code></td><td>Emails with PDF attachments</td></tr>
            <tr><td><code>label:INBOX</code></td><td>Emails with specific Gmail label</td></tr>
        </table>

        <h3>Date Filters</h3>
        <table class="help-table">
            <tr><td><code>after:2024-01-15</code></td><td>Emails after this date</td></tr>
            <tr><td><code>before:2024-06-01</code></td><td>Emails before this date</td></tr>
            <tr><td><code>after:2024-01 before:2024-02</code></td><td>Emails in January 2024</td></tr>
        </table>

        <h3>Boolean Operators</h3>
        <table class="help-table">
            <tr><td><code>apple orange</code></td><td>Both words (implicit AND)</td></tr>
            <tr><td><code>apple OR orange</code></td><td>Either word</td></tr>
            <tr><td><code>apple NOT orange</code></td><td>Apple but not orange</td></tr>
            <tr><td><code>-orange</code></td><td>Exclude word (same as NOT)</td></tr>
        </table>

        <h3>Phrases &amp; Grouping</h3>
        <table class="help-table">
            <tr><td><code>"hello world"</code></td><td>Exact phrase</td></tr>
            <tr><td><code>(apple OR orange) juice</code></td><td>Grouping with parentheses</td></tr>
        </table>

        <h3>Prefix Matching</h3>
        <table class="help-table">
            <tr><td><code>meet*</code></td><td>Words starting with "meet" (meeting, meets, etc.)</td></tr>
        </table>

        <h3>Examples</h3>
        <table class="help-table">
            <tr><td><code>from:amazon invoice</code></td><td>Invoices from Amazon</td></tr>
            <tr><td><code>subject:urgent after:2024-01-01</code></td><td>Urgent emails this year</td></tr>
            <tr><td><code>attachment:pdf report OR invoice</code></td><td>PDFs with report or invoice</td></tr>
            <tr><td><code>label:IMPORTANT from:boss@work.com</code></td><td>Important emails from boss</td></tr>
        </table>
    </div>
{% endblock %}"""
    )
    EMAIL_TEMPLATE = BASE_TEMPLATE.replace(
        "{% block title %}ownmail{% endblock %}",
        "{% block title %}{{ subject }} - ownmail{% endblock %}"
    ).replace(
        "{% block content %}{% endblock %}",
        """{% block content %}
    <div class="back-link"><a href="javascript:history.back()">&larr; Back to search</a></div>
    <div class="email-detail">
        <div class="email-header">
            <h2>{{ subject or '(No subject)' }}</h2>
            <div class="email-header-row">
                <span class="email-header-label">From:</span>
                {% if sender_name and sender_email %}
                    {{ sender_name }}
                    &lt;<a href="/search?q=from:{{ sender_email | urlencode }}&sort=date_desc" class="clickable-header" onclick="showLoading()">{{ sender_email }}</a>&gt;
                {% elif sender_email %}
                    <a href="/search?q=from:{{ sender_email | urlencode }}&sort=date_desc" class="clickable-header" onclick="showLoading()">{{ sender_email }}</a>
                {% else %}
                    {{ sender }}
                {% endif %}
            </div>
            <div class="email-header-row">
                <span class="email-header-label">To:</span>
                {% for rcpt in recipients_parsed %}
                    {% if not loop.first %}, {% endif %}
                    {% if rcpt.name and rcpt.email %}
                        {{ rcpt.name }}
                        &lt;<a href="/search?q=to:{{ rcpt.email | urlencode }}&sort=date_desc" class="clickable-header" onclick="showLoading()">{{ rcpt.email }}</a>&gt;
                    {% elif rcpt.email %}
                        <a href="/search?q=to:{{ rcpt.email | urlencode }}&sort=date_desc" class="clickable-header" onclick="showLoading()">{{ rcpt.email }}</a>
                    {% else %}
                        {{ rcpt.raw }}
                    {% endif %}
                {% endfor %}
            </div>
            <div class="email-header-row">
                <span class="email-header-label">Date:</span> {{ date }}
            </div>
            {% if labels %}
            <div class="labels">
                {% for label in labels %}
                <a href="/search?q=label:{{ label | urlencode }}&sort=date_desc" class="label clickable-label" onclick="showLoading()">{{ label }}</a>
                {% endfor %}
            </div>
            {% endif %}
        </div>

        {% if images_blocked and has_external_images %}
        <div class="image-banner" id="image-banner">
            <span id="image-banner-text">🖼️ External images are blocked for security.</span>
            <div style="display: flex; gap: 10px; align-items: center;">
                <button id="load-images-btn" onclick="loadImages()">Load Images</button>
                {% if sender_email %}
                <span id="trust-container">
                    <button class="trust-btn" onclick="trustSender()">Always trust this sender</button>
                </span>
                <span id="trusted-container" style="display: none;">
                    <button class="undo-btn" onclick="untrustSender()">Undo</button>
                </span>
                {% endif %}
            </div>
        </div>
        <script>
        var senderEmail = "{{ sender_email }}";

        function loadImages(skipTextUpdate) {
            var iframe = document.getElementById('email-frame');
            if (iframe) {
                var doc = iframe.contentDocument;
                doc.querySelectorAll('img[data-src]').forEach(function(img) {
                    img.src = img.getAttribute('data-src');
                    img.removeAttribute('data-src');
                });
                // Resize after images load
                setTimeout(function() {
                    iframe.style.height = doc.body.scrollHeight + 20 + 'px';
                }, 500);
            }
            // Hide the load button and update text, but keep trust option visible
            document.getElementById('load-images-btn').style.display = 'none';
            if (!skipTextUpdate) {
                document.getElementById('image-banner-text').textContent = '✓ Images loaded.';
            }
        }

        function trustSender() {
            fetch('/trust-sender', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'email=' + encodeURIComponent(senderEmail)
            }).then(function(response) {
                if (response.ok) {
                    document.getElementById('trust-container').style.display = 'none';
                    document.getElementById('trusted-container').style.display = 'inline';
                    document.getElementById('image-banner-text').textContent = '✓ Images from this sender will always be loaded.';
                    document.getElementById('load-images-btn').style.display = 'none';
                    loadImages(true);
                }
            });
        }

        function untrustSender() {
            fetch('/untrust-sender', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'email=' + encodeURIComponent(senderEmail)
            }).then(function(response) {
                if (response.ok) {
                    document.getElementById('trusted-container').style.display = 'none';
                    document.getElementById('trust-container').style.display = 'inline';
                    document.getElementById('image-banner-text').textContent = '✓ Images loaded.';
                }
            });
        }
        </script>
        {% endif %}

        {% if body_html %}
            <iframe id="email-frame" class="email-body-html" sandbox="allow-same-origin" srcdoc="{{ body_html | e }}"></iframe>
            <script>
            // Auto-resize iframe to fit content
            document.getElementById('email-frame').onload = function() {
                try {
                    this.style.height = this.contentDocument.body.scrollHeight + 20 + 'px';
                } catch(e) {}
            };
            </script>
        {% else %}
            <pre class="email-body">{{ body }}</pre>
        {% endif %}

        {% if attachments %}
        <div class="attachments">
            <h4>Attachments</h4>
            <ul class="attachment-list">
            {% for att in attachments %}
                <li class="attachment-item">
                    <a href="/attachment/{{ message_id }}/{{ loop.index0 }}">📎 {{ att.filename }}</a>
                    ({{ att.size }})
                </li>
            {% endfor %}
            </ul>
        </div>
        {% endif %}

        <div class="email-actions" style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #eee;">
            <a href="/raw/{{ message_id }}" class="btn-secondary" style="display: inline-block; padding: 8px 16px; background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; text-decoration: none; color: #333; font-size: 13px;">📄 View Original (.eml)</a>
        </div>
    </div>
    <div class="back-link"><a href="javascript:history.back()">&larr; Back to search</a></div>
{% endblock %}"""
    )

    @app.route("/")
    def index():
        # Redirect to search page which now shows newest emails by default
        return redirect("/search")

    @app.route("/help")
    def help_page():
        stats = get_cached_stats()
        return render_template_string(HELP_TEMPLATE, stats=stats)

    @app.route("/search")
    def search():
        search_start = time.time()
        query = request.args.get("q", "").strip()
        page = request.args.get("page", 1, type=int)
        sort = request.args.get("sort", "relevance")
        if sort not in ("relevance", "date_desc", "date_asc"):
            sort = "relevance"
        per_page = page_size  # Use configured page_size
        stats = get_cached_stats()

        # Check if query is filter-only (no FTS search terms)
        # Remove known filters to see if any search terms remain
        query_without_filters = query
        for pattern in [
            r'\b(?:before|after):\d{4}-?\d{2}-?\d{2}\b',
            r'\b(?:label|tag):\S+\b',
        ]:
            query_without_filters = re.sub(pattern, '', query_without_filters)
        # Also remove orphaned AND
        query_without_filters = re.sub(r'\bAND\b', '', query_without_filters, flags=re.IGNORECASE)
        # Check if there are actual search terms (including field:value FTS queries)
        has_fts_terms = bool(query_without_filters.strip())

        # If no FTS terms, "relevance" doesn't make sense - use date_desc
        if not has_fts_terms and sort == "relevance":
            sort = "date_desc"

        # If no query at all, show newest emails
        if not query:
            query = ""  # Will trigger filter-only path in database
            has_fts_terms = False
            sort = "date_desc"

        # Server-side pagination: fetch only what we need + 1 to check if more exist
        offset = (page - 1) * per_page
        cache_key = f"{query}:{sort}:{offset}:{per_page}"

        # Check cache first
        cached = search_cache.get(cache_key)
        if cached is not None:
            if verbose:
                print(f"[verbose] Search cache HIT for: {query} (page {page}, sort {sort})", flush=True)
            raw_results = cached
            search_error = None
        else:
            if verbose:
                print(f"[verbose] Searching for: {query} (page {page}, offset {offset}, sort {sort})", flush=True)
                start = time.time()

            # Fetch per_page + 1 to know if there are more results
            try:
                raw_results = archive.search(query, limit=per_page + 1, offset=offset, sort=sort)
                search_error = None
            except Exception as e:
                raw_results = []
                search_error = str(e)
                if verbose:
                    print(f"[verbose] Search error: {e}", flush=True)

            if verbose and not search_error:
                print(f"[verbose] Search took {time.time()-start:.2f}s, {len(raw_results)} results", flush=True)

            # Cache the results (only if successful)
            if not search_error:
                search_cache.set(cache_key, raw_results)

        # Check if there are more results
        has_more = len(raw_results) > per_page
        if has_more:
            raw_results = raw_results[:per_page]

        # Format results - always extract from email file for correct encoding
        results = []
        for msg_id, filename, subject, sender, date_str, snippet in raw_results:
            # Always extract from file to ensure proper Korean/encoding support
            # The parser handles charset detection better than FTS stored values
            if filename:
                filepath = archive.archive_dir / filename
                if filepath.exists():
                    try:
                        # Use our parser which handles Korean charset properly
                        parsed = EmailParser.parse_file(filepath=filepath)
                        subject = parsed.get("subject") or "(No subject)"
                        sender = parsed.get("sender", "")
                        date_str = parsed.get("date_str", "")

                        # Always extract snippet from parsed body for correct encoding
                        # FTS snippet may have garbled Korean text
                        body = parsed.get("body", "")
                        if body:
                            snippet = body[:150] + "..." if len(body) > 150 else body
                    except Exception:
                        # Fall back to FTS values if file parsing fails
                        if not subject:
                            subject = "(Error reading email)"

            results.append({
                "message_id": msg_id,
                "filename": filename,
                "subject": subject,
                "sender": sender,
                "date_str": date_str,
                "snippet": snippet,
            })

        search_time = time.time() - search_start
        return render_template_string(
            SEARCH_TEMPLATE,
            stats=stats,
            query=query,
            results=results,
            page=page,
            sort=sort,
            start_idx=offset,
            has_more=has_more,
            has_prev=page > 1,
            search_time=search_time,
            search_error=search_error,
            hide_relevance=not has_fts_terms,
        )

    @app.route("/email/<message_id>")
    def view_email(message_id: str):
        stats = get_cached_stats()

        # Check email cache first
        cached = email_cache.get(message_id)
        if cached is not None:
            if verbose:
                print(f"[verbose] Email cache HIT for: {message_id}", flush=True)
            email_data = cached
        else:
            # Get email file path from database
            if verbose:
                print(f"[verbose] Looking up email {message_id}...", flush=True)
                start = time.time()
            email_info = archive.db.get_email_by_id(message_id)
            if verbose:
                print(f"[verbose] DB lookup took {time.time()-start:.2f}s", flush=True)
            if not email_info:
                abort(404)

            filename = email_info[1]  # filename is second column
            filepath = archive.archive_dir / filename

            if not filepath.exists():
                abort(404)

            # Parse email using EmailParser for proper Korean charset handling
            if verbose:
                start = time.time()

            # Use EmailParser for headers (handles Korean charset properly)
            parsed = EmailParser.parse_file(filepath=filepath)
            subject = parsed.get("subject") or "(No subject)"
            sender = parsed.get("sender", "")
            recipients = parsed.get("recipients", "")
            date = parsed.get("date_str", "")
            labels_str = parsed.get("labels", "")
            labels = [lbl.strip() for lbl in labels_str.split(",") if lbl.strip()]

            # For body and attachments, we still need to parse the message
            with open(filepath, "rb") as f:
                msg = email.message_from_binary_file(f, policy=email_policy)

            # Extract body
            body = ""
            body_html = None
            attachments = []

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))

                    if "attachment" in content_disposition:
                        # Attachment
                        att_filename = decode_header(part.get_filename() or "") or "attachment"
                        size = len(part.get_payload(decode=True) or b"")
                        attachments.append({
                            "filename": att_filename,
                            "size": _format_size(size),
                        })
                    elif content_type == "text/plain" and not body:
                        payload = part.get_payload(decode=True)
                        if payload:
                            # Use helper that can detect Korean charset
                            body = _decode_text_body(payload, part.get_content_charset())
                    elif content_type == "text/html" and not body_html:
                        payload = part.get_payload(decode=True)
                        if payload:
                            # Use helper that can extract charset from HTML meta tag
                            body_html = _decode_html_body(payload, part.get_content_charset())
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    content_type = msg.get_content_type()
                    header_charset = msg.get_content_charset()
                    if content_type == "text/html":
                        # Use helper that can extract charset from HTML meta tag
                        body_html = _decode_html_body(payload, header_charset)
                    else:
                        # Use helper that can detect Korean charset
                        body = _decode_text_body(payload, header_charset)

            # Prefer HTML over plain text for better formatting
            # (we already block external images for privacy)
            if body_html:
                body = ""

            if verbose:
                print(f"[verbose] Email parsing took {time.time()-start:.2f}s", flush=True)

            # Cache the parsed email data
            email_data = {
                "subject": subject,
                "sender": sender,
                "recipients": recipients,
                "date": date,
                "labels": labels,
                "body": body,
                "body_html": body_html,
                "attachments": attachments,
            }
            email_cache.set(message_id, email_data)

        # Block external images if configured (do this after cache since it depends on config)
        body_html = email_data.get("body_html")
        has_external_images = False
        images_blocked = block_images

        # Parse sender and recipients for clickable links
        sender_name, sender_email = parse_email_address(email_data["sender"])
        recipients_parsed = parse_recipients(email_data["recipients"])

        # Check if sender is trusted (skip image blocking for trusted senders)
        trusted_senders = app.config.get("trusted_senders", set())
        sender_is_trusted = sender_email and sender_email.lower() in trusted_senders
        if sender_is_trusted:
            images_blocked = False

        if body_html and images_blocked:
            body_html, has_external_images = block_external_images(body_html)

        return render_template_string(
            EMAIL_TEMPLATE,
            stats=stats,
            message_id=message_id,
            subject=email_data["subject"],
            sender=email_data["sender"],
            sender_name=sender_name,
            sender_email=sender_email,
            recipients=email_data["recipients"],
            recipients_parsed=recipients_parsed,
            date=email_data["date"],
            labels=email_data["labels"],
            body=email_data["body"],
            body_html=body_html,
            attachments=email_data["attachments"],
            images_blocked=images_blocked,
            has_external_images=has_external_images,
            sender_is_trusted=sender_is_trusted,
        )

    @app.route("/raw/<message_id>")
    def view_raw(message_id: str):
        """Show the original .eml file with filepath."""
        email_info = archive.db.get_email_by_id(message_id)
        if not email_info:
            abort(404)

        filename = email_info[1]
        filepath = archive.archive_dir / filename

        if not filepath.exists():
            abort(404)

        # Read file content
        with open(filepath, "rb") as f:
            content = f.read().decode("utf-8", errors="replace")

        # Render HTML page with filepath and content
        from markupsafe import escape
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Raw Email - {escape(filename)}</title>
    <style>
        body {{ font-family: monospace; margin: 0; padding: 20px; background: #f5f5f5; }}
        .filepath {{ background: #fff; padding: 10px 15px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 15px; word-break: break-all; font-size: 13px; }}
        .filepath-label {{ color: #666; font-size: 11px; margin-bottom: 5px; }}
        .content {{ background: #fff; padding: 15px; border: 1px solid #ddd; border-radius: 4px; white-space: pre-wrap; font-size: 12px; line-height: 1.4; overflow-x: auto; }}
        a {{ color: #0066cc; }}
    </style>
</head>
<body>
    <div style="margin-bottom: 15px;"><a href="/email/{escape(message_id)}">&larr; Back to email</a></div>
    <div class="filepath">
        <div class="filepath-label">File path:</div>
        {escape(str(filepath))}
    </div>
    <div class="content">{escape(content)}</div>
</body>
</html>'''

    @app.route("/attachment/<message_id>/<int:index>")
    def download_attachment(message_id: str, index: int):
        # Get email file path
        email_info = archive.db.get_email_by_id(message_id)
        if not email_info:
            abort(404)

        filename = email_info[1]
        filepath = archive.archive_dir / filename

        if not filepath.exists():
            abort(404)

        # Parse email and find attachment
        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email_policy)

        attachment_idx = 0
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                if attachment_idx == index:
                    # Found the attachment
                    att_filename = decode_header(part.get_filename() or "") or "attachment"
                    att_data = part.get_payload(decode=True)
                    content_type = part.get_content_type()

                    # Create temp file and send
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp.write(att_data)
                        tmp_path = tmp.name

                    return send_file(
                        tmp_path,
                        mimetype=content_type,
                        as_attachment=True,
                        download_name=att_filename,
                    )
                attachment_idx += 1

        abort(404)

    @app.route("/trust-sender", methods=["POST"])
    def trust_sender():
        """Add a sender to the trusted senders list in config.yaml."""
        sender_email = request.form.get("email", "").strip().lower()
        redirect_to = request.form.get("redirect", "/")

        if not sender_email:
            return redirect(redirect_to)

        config_path = app.config.get("config_path")
        if not config_path:
            # No config path, just update in-memory
            app.config["trusted_senders"].add(sender_email)
            return redirect(redirect_to)

        try:
            # Read current config
            with open(config_path) as f:
                import yaml
                config_content = f.read()
                config_data = yaml.safe_load(config_content) or {}

            # Add to trusted_senders
            web_config = config_data.setdefault("web", {})
            trusted_list = web_config.setdefault("trusted_senders", [])
            if sender_email not in trusted_list:
                trusted_list.append(sender_email)

                # Write back
                with open(config_path, "w") as f:
                    yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

                # Update in-memory set
                app.config["trusted_senders"].add(sender_email)

                if verbose:
                    print(f"[verbose] Added trusted sender: {sender_email}", flush=True)
        except Exception as e:
            if verbose:
                print(f"[verbose] Error updating config: {e}", flush=True)

        # Return JSON for AJAX, redirect for form submit
        if request.headers.get("Content-Type") == "application/x-www-form-urlencoded" and not redirect_to:
            return {"status": "ok"}
        if redirect_to == "/":
            return {"status": "ok"}
        return redirect(redirect_to)

    @app.route("/untrust-sender", methods=["POST"])
    def untrust_sender():
        """Remove a sender from the trusted senders list."""
        sender_email = request.form.get("email", "").strip().lower()

        if not sender_email:
            return {"status": "error", "message": "No email provided"}

        # Remove from in-memory set
        app.config["trusted_senders"].discard(sender_email)

        config_path = app.config.get("config_path")
        if config_path:
            try:
                # Read current config
                with open(config_path) as f:
                    import yaml
                    config_data = yaml.safe_load(f) or {}

                # Remove from trusted_senders
                web_config = config_data.get("web", {})
                trusted_list = web_config.get("trusted_senders", [])
                if sender_email in trusted_list:
                    trusted_list.remove(sender_email)

                    # Write back
                    with open(config_path, "w") as f:
                        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

                    if verbose:
                        print(f"[verbose] Removed trusted sender: {sender_email}", flush=True)
            except Exception as e:
                if verbose:
                    print(f"[verbose] Error updating config: {e}", flush=True)

        return {"status": "ok"}

    return app


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def run_server(
    archive: EmailArchive,
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
    verbose: bool = False,
    block_images: bool = False,
    page_size: int = 20,
    trusted_senders: list = None,
    config_path: str = None,
) -> None:
    """Run the web server.

    Args:
        archive: EmailArchive instance
        host: Host to bind to
        port: Port to listen on
        debug: Enable debug mode
        verbose: Enable request timing logs
        block_images: Block external images by default
        page_size: Number of results per page
        trusted_senders: List of email addresses to always show images from
        config_path: Path to config.yaml for updating trusted senders
    """
    app = create_app(
        archive,
        verbose=verbose,
        block_images=block_images,
        page_size=page_size,
        trusted_senders=trusted_senders,
        config_path=config_path,
    )

    print("\n🌐 ownmail web interface")
    print(f"   Running at: http://{host}:{port}")
    print(f"   Page size: {page_size}")
    if verbose:
        print("   Verbose logging enabled")
    if block_images:
        print("   External images blocked by default")
    if trusted_senders:
        print(f"   Trusted senders: {len(trusted_senders)}")
    print("   Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=debug)
