"""Web interface for browsing and searching the email archive."""

import email
import email.header
import os
import re
import time
from email.policy import default as email_policy

from flask import Flask, abort, g, redirect, render_template, request, send_file

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

# Regex to extract RFC 2231 encoded filename parts
# Handles both: filename*=charset''value and filename*0*=charset''value
RFC2231_FILENAME_RE = re.compile(rb"filename\*(\d*)\*?=([^;\r\n]+)", re.IGNORECASE)


def _extract_attachment_filename(part) -> str:
    """Extract attachment filename with proper charset handling.

    Python's email library can corrupt non-ASCII filenames that aren't
    properly MIME-encoded. This function extracts the raw bytes from
    the part and decodes them properly, handling RFC 2231 encoding.

    Args:
        part: Email MIME part

    Returns:
        Properly decoded filename, or "attachment" if none found
    """
    import base64
    from urllib.parse import unquote_to_bytes

    # Try to get raw bytes from the part
    try:
        raw_part = part.as_bytes()

        # FIRST: Check for RFC2231 + MIME hybrid encoding (filename*N="=?UTF-8?B?...?=")
        # Some email clients incorrectly combine RFC2231 continuation with MIME encoded-words
        # This must be checked first because the quoted values break standard RFC2231 parsing
        rfc2231_mime_re = re.compile(rb'filename\*\d+="([^"]+)"', re.IGNORECASE)
        mime_matches = rfc2231_mime_re.findall(raw_part)
        if mime_matches:
            # Join all parts and clean up
            combined_value = b''.join(mime_matches).replace(b'\r\n ', b' ').replace(b'\r\n', b'').replace(b'\n ', b' ')
            combined_str = combined_value.decode('ascii', errors='ignore')

            # Check if it contains MIME encoded-words
            if '=?' in combined_str and '?=' in combined_str:
                # Extract MIME encoded-words
                mime_word_re = re.compile(r'=\?([^?]+)\?([BbQq])\?([^?]+)\?=')
                mime_parts = mime_word_re.findall(combined_str)
                if mime_parts:
                    decoded_parts = []
                    for charset_name, encoding, encoded_text in mime_parts:
                        try:
                            if encoding.upper() == 'B':
                                # Base64 - fix padding
                                padding = 4 - (len(encoded_text) % 4) if len(encoded_text) % 4 else 0
                                encoded_text += '=' * padding
                                decoded_bytes = base64.b64decode(encoded_text)
                            else:
                                # Quoted-printable
                                import quopri
                                decoded_bytes = quopri.decodestring(encoded_text.encode('ascii'))

                            # Decode with charset
                            cs = charset_name.lower()
                            if cs == 'unknown':
                                cs = 'utf-8'
                            decoded_parts.append(decoded_bytes.decode(cs, errors='replace'))
                        except Exception:
                            continue

                    if decoded_parts:
                        result = ''.join(decoded_parts)
                        if '\ufffd' not in result:
                            return result

        # SECOND: Look for standard RFC 2231 encoded filename
        # Handles both: filename*=charset''value and filename*0*=charset''value
        filename_parts = []

        for match in RFC2231_FILENAME_RE.finditer(raw_part):
            # Part number may be empty (single part) or a number (multi-part)
            part_num_bytes = match.group(1)
            part_num = int(part_num_bytes) if part_num_bytes else 0
            value = match.group(2).strip()

            # Skip if value starts with quote (handled above as hybrid)
            if value.startswith(b'"'):
                continue

            # First part has charset''value format
            if b"''" in value:
                charset_bytes, encoded_value = value.split(b"''", 1)
                charset = charset_bytes.decode('ascii', errors='ignore').lower()
                # unknown-8bit is often EUC-KR for Korean emails
                if charset in ('unknown-8bit', ''):
                    charset = 'euc-kr'
            else:
                # Continuation parts don't have charset prefix
                encoded_value = value
                charset = 'euc-kr'

            # URL-decode the value
            try:
                decoded_bytes = unquote_to_bytes(encoded_value.decode('ascii'))
                filename_parts.append((part_num, decoded_bytes, charset))
            except Exception:
                continue

        if filename_parts:
            # Sort by part number and combine
            filename_parts.sort(key=lambda x: x[0])
            combined = b''.join(p[1] for p in filename_parts)
            charset = filename_parts[0][2]  # Use charset from first part

            # Try the specified charset first, then fallbacks
            for enc in [charset, 'euc-kr', 'cp949', 'utf-8', 'gb2312', 'shift_jis']:
                try:
                    decoded = combined.decode(enc)
                    # Validate it has readable CJK content
                    if any('\uAC00' <= c <= '\uD7AF' or  # Hangul
                           '\u4E00' <= c <= '\u9FFF' or  # CJK
                           '\u3040' <= c <= '\u30FF'     # Japanese
                           for c in decoded):
                        return decoded
                    # If no CJK but decoded without errors, use it
                    if enc in ['utf-8', charset]:
                        return decoded
                except (UnicodeDecodeError, LookupError):
                    continue

        # THIRD: Try to extract raw filename from simple filename="..." header
        # Some old emails have raw non-ASCII bytes without any encoding
        simple_fn_re = re.compile(rb'filename="([^"]+)"', re.IGNORECASE)
        simple_match = simple_fn_re.search(raw_part)
        if simple_match:
            raw_filename = simple_match.group(1)
            # Check if it has high bytes (non-ASCII)
            if any(b >= 0x80 for b in raw_filename):
                # Try various CJK encodings
                for enc in ['euc-kr', 'cp949', 'utf-8', 'gb2312', 'gbk', 'shift_jis', 'cp1251', 'koi8-r']:
                    try:
                        decoded = raw_filename.decode(enc)
                        # Validate - should have CJK/Cyrillic chars
                        if any('\uAC00' <= c <= '\uD7AF' or  # Hangul
                               '\u4E00' <= c <= '\u9FFF' or  # CJK
                               '\u0400' <= c <= '\u04FF' or  # Cyrillic
                               '\u3040' <= c <= '\u30FF'     # Japanese
                               for c in decoded):
                            return decoded
                    except (UnicodeDecodeError, LookupError):
                        continue

    except Exception:
        pass

    # Fall back to standard get_filename() with mojibake fix
    filename = part.get_filename()
    if filename:
        # Check for replacement characters (corruption)
        if '\ufffd' not in filename:
            fixed = _fix_mojibake_filename(filename)
            if fixed:
                return fixed
        # Try decode_header for MIME-encoded filenames
        if '=?' in filename:
            decoded = decode_header(filename)
            if decoded and '\ufffd' not in decoded:
                return decoded
        return filename

    return "attachment"


def _fix_mojibake_filename(filename: str) -> str:
    """Fix mojibake in attachment filenames.

    Some old emails have raw non-ASCII bytes in filenames without proper
    MIME encoding. Python's email library decodes them as latin-1/ASCII,
    producing mojibake. This function detects and fixes such cases.

    Args:
        filename: Potentially mojibake filename

    Returns:
        Properly decoded filename
    """
    if not filename:
        return filename

    # Check if the filename looks like mojibake (high latin-1 chars that
    # could be EUC-KR/CP949 bytes interpreted as latin-1)
    try:
        # Try to encode as latin-1 to get raw bytes
        raw_bytes = filename.encode('latin-1')
    except UnicodeEncodeError:
        # Contains chars outside latin-1, not simple mojibake
        return filename

    # Check if it has high bytes (potential CJK encoding)
    if not any(b >= 0x80 for b in raw_bytes):
        return filename  # All ASCII, no mojibake

    # Try to decode as various CJK encodings
    for encoding in ['euc-kr', 'cp949', 'utf-8', 'gb2312', 'gbk', 'shift_jis']:
        try:
            decoded = raw_bytes.decode(encoding)
            # Validate that result looks like readable text
            # (contains Hangul, CJK, or mostly printable ASCII)
            hangul_cjk = sum(1 for c in decoded
                            if '\uAC00' <= c <= '\uD7AF'  # Hangul
                            or '\u4E00' <= c <= '\u9FFF'  # CJK
                            or '\u3040' <= c <= '\u30FF')  # Japanese
            if hangul_cjk > 0:
                return decoded
        except (UnicodeDecodeError, LookupError):
            continue

    return filename  # Return original if nothing worked


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

    # Check if it looks like MIME-encoded
    if '=?' not in value or '?=' not in value:
        return value

    try:
        decoded_parts = email.header.decode_header(value)
        result = []
        for data, charset in decoded_parts:
            if isinstance(data, bytes):
                # Try the declared charset first, then common fallbacks
                charsets_to_try = []
                if charset and charset.upper() != 'UNKNOWN':
                    charsets_to_try.append(charset)
                # Add common fallbacks: CJK, Russian, Western European
                charsets_to_try.extend([
                    'utf-8', 'euc-kr', 'cp949', 'iso-2022-kr',  # Korean
                    'cp1251', 'koi8-r',  # Russian
                    'gb2312', 'gbk',  # Chinese
                    'shift_jis', 'euc-jp',  # Japanese
                    'iso-8859-1', 'cp1252',  # Western
                ])
                decoded = None
                for cs in charsets_to_try:
                    if cs:
                        try:
                            decoded = data.decode(cs)
                            # Validate it doesn't have too many replacement chars
                            if '\ufffd' not in decoded:
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
        # If standard decoding fails (malformed base64, etc.), try manual approach
        # Some emails have split multi-byte chars across encoded-words
        try:
            import base64
            import re
            # Find all encoded-words and try to decode them together
            pattern = r'=\?([^?]+)\?([BbQq])\?([^?]*)\?='
            matches = list(re.finditer(pattern, value))

            if not matches:
                return value

            # Collect all base64 parts for same charset
            base64_parts = []
            charset_used = None
            for m in matches:
                charset, encoding, encoded_text = m.groups()
                if encoding.upper() == 'B':
                    base64_parts.append(encoded_text)
                    charset_used = charset

            if base64_parts and charset_used:
                # Combine and decode
                combined = ''.join(base64_parts)
                # Add padding if needed
                padding = 4 - (len(combined) % 4) if len(combined) % 4 else 0
                combined += '=' * padding
                try:
                    decoded_bytes = base64.b64decode(combined)
                    return decoded_bytes.decode(charset_used, errors='replace')
                except Exception:
                    pass

            return value  # Return original if all else fails
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
                        # Clean up whitespace and invisible Unicode characters
                        text = _clean_snippet_text(text)
                        return text[:max_len] + "..." if len(text) > max_len else text
        else:
            if msg.get_content_type() == "text/plain":
                payload = msg.get_payload(decode=True)
                if payload:
                    text = _decode_text_body(payload, msg.get_content_charset())
                    text = _clean_snippet_text(text)
                    return text[:max_len] + "..." if len(text) > max_len else text
    except Exception:
        pass
    return ""


def _clean_snippet_text(text: str) -> str:
    """Clean up text for snippet display.

    Removes invisible Unicode characters often used by email marketers
    as preheader padding (ZWNJ, ZWJ, ZWSP, etc.), CSS code that leaked
    through, and repetitive padding characters.
    """
    if not text:
        return text

    # Remove zero-width and invisible characters
    # U+200B Zero Width Space
    # U+200C Zero Width Non-Joiner (ZWNJ) - common in marketing emails
    # U+200D Zero Width Joiner (ZWJ)
    # U+FEFF Byte Order Mark / Zero Width No-Break Space
    # U+00AD Soft Hyphen
    # U+2060 Word Joiner
    invisible_chars = '\u200b\u200c\u200d\ufeff\u00ad\u2060'
    for char in invisible_chars:
        text = text.replace(char, '')

    # Remove CSS-like content (selectors with braces)
    # Matches patterns like ".class { ... }" or "#id { ... }"
    text = re.sub(r'[.#][\w-]+\s*\{[^}]*\}', '', text)

    # Remove repetitive padding patterns (single char repeated with spaces)
    # Matches "ä ä ä ä" or ". . . ." etc.
    text = re.sub(r'(\S)\s+(?:\1\s+){3,}', '', text)

    # Collapse whitespace
    text = " ".join(text.split())
    return text


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
    date_format: str = None,
) -> Flask:
    """Create the Flask application.

    Args:
        archive: EmailArchive instance
        verbose: Enable request timing logs
        block_images: Block external images by default
        page_size: Number of results per page
        trusted_senders: List of email addresses to always show images from
        config_path: Path to config.yaml for updating trusted senders
        date_format: strftime format for dates (default: auto - "Jan 26" or "2025/12/15")

    Returns:
        Flask application
    """
    # Set templates and static directories relative to this module
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["archive"] = archive
    app.config["verbose"] = verbose
    app.config["block_images"] = block_images
    app.config["page_size"] = page_size
    app.config["trusted_senders"] = {s.lower() for s in (trusted_senders or [])}
    app.config["config_path"] = config_path
    app.config["date_format"] = date_format  # None = auto

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

    @app.route("/")
    def index():
        # Redirect to search page which now shows newest emails by default
        return redirect("/search")

    def get_back_to_search_url() -> str | None:
        """Get the URL to go back to search results, if applicable.

        Returns the search URL from the Referer header if the user came from
        a search page, otherwise returns None.
        """
        referer = request.headers.get("Referer", "")
        if not referer:
            return None

        # Parse the referer to check if it's a search page on this host
        from urllib.parse import urlparse
        parsed = urlparse(referer)

        # Check if it's the same host and a search path
        if parsed.path == "/search" or parsed.path.startswith("/search?"):
            # Return just the path and query (relative URL)
            if parsed.query:
                return f"/search?{parsed.query}"
            return "/search"

        return None

    @app.route("/help")
    def help_page():
        stats = get_cached_stats()
        back_url = get_back_to_search_url()
        return render_template("help.html", stats=stats, back_url=back_url)

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

        # Format results - use database values, decode MIME headers as needed
        results = []
        for msg_id, filename, subject, sender, date_str, snippet in raw_results:
            # Use values from database - they're already indexed
            # Only decode MIME-encoded headers if present
            if subject:
                if '=?' in subject:
                    subject = decode_header(subject)
            else:
                subject = "(No subject)"

            if sender and '=?' in sender:
                sender = decode_header(sender)

            if snippet and '=?' in snippet:
                snippet = decode_header(snippet)

            # Clean up snippet text (remove CSS, padding chars, etc.)
            if snippet:
                snippet = _clean_snippet_text(snippet)

            # Extract sender name (without email address)
            sender_name, _ = parse_email_address(sender) if sender else ("", "")
            if not sender_name:
                # Fall back to email address or full sender string
                sender_name = sender.split('<')[0].strip() if sender else ""
                if not sender_name and sender:
                    sender_name = sender

            # Format date as short date
            date_short = ""
            if date_str:
                try:
                    from datetime import datetime
                    from email.utils import parsedate_to_datetime
                    parsed_date = parsedate_to_datetime(date_str)
                    date_fmt = app.config.get("date_format")
                    if date_fmt:
                        # Use configured format
                        date_short = parsed_date.strftime(date_fmt)
                    else:
                        # Auto format: "Jan 26" for this year, "2025/12/15" for other years
                        now = datetime.now(parsed_date.tzinfo) if parsed_date.tzinfo else datetime.now()
                        if parsed_date.year == now.year:
                            date_short = parsed_date.strftime("%b %d")
                        else:
                            date_short = parsed_date.strftime("%Y/%m/%d")
                except Exception:
                    # Fall back to extracting date part from string
                    date_short = date_str.split()[0] if date_str else ""

            results.append({
                "message_id": msg_id,
                "filename": filename,
                "subject": subject,
                "sender": sender,
                "sender_name": sender_name,
                "date_str": date_str,
                "date_short": date_short,
                "snippet": snippet,
            })

        search_time = time.time() - search_start
        return render_template(
            "search.html",
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

            # Ensure MIME-encoded headers are fully decoded
            # Parser may return partially decoded or raw MIME strings
            if subject and '=?' in subject:
                subject = decode_header(subject)
            if sender and '=?' in sender:
                sender = decode_header(sender)

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
                        # Extract filename with proper charset handling
                        att_filename = _extract_attachment_filename(part)
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

        # Make all links in email open in new tab (prevents X-Frame-Options issues)
        # Also inject base styles for consistent rendering
        if body_html:
            # Detect if email has its own styling (inline styles or <style> tags)
            has_own_styles = ('<style' in body_html.lower() or
                             'style=' in body_html.lower())

            if has_own_styles:
                # Email has CSS - keep it light mode (emails assume light background)
                base_styles = '''<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  padding: 0;
  margin: 15px;
  background: #fff;
  color: #333;
}
</style>'''
            else:
                # Plain email without CSS - can apply dark mode safely
                base_styles = '''<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  padding: 0;
  margin: 15px;
}
@media (prefers-color-scheme: dark) {
  body { background: #242424; color: #e0e0e0; }
  a { color: #6cb6ff; }
}
</style>'''
            # Inject <base target="_blank"> to make all links open in new tab
            if '<head>' in body_html.lower():
                # Insert after <head> tag
                body_html = re.sub(
                    r'(<head[^>]*>)',
                    r'\1<base target="_blank">' + base_styles,
                    body_html,
                    count=1,
                    flags=re.IGNORECASE
                )
            elif '<html' in body_html.lower():
                # Insert after <html> tag
                body_html = re.sub(
                    r'(<html[^>]*>)',
                    r'\1<head><base target="_blank">' + base_styles + '</head>',
                    body_html,
                    count=1,
                    flags=re.IGNORECASE
                )
            else:
                # Prepend to body
                body_html = '<base target="_blank">' + base_styles + body_html

        # Get back URL if user came from search
        back_url = get_back_to_search_url()

        return render_template(
            "email.html",
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
            back_url=back_url,
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Raw Email - {escape(filename)}</title>
    <style>
        body {{ font-family: monospace; margin: 0; padding: 20px; background: #f5f5f5; }}
        .filepath {{ background: #fff; padding: 10px 15px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 15px; word-break: break-all; font-size: 13px; }}
        .filepath-label {{ color: #666; font-size: 11px; margin-bottom: 5px; }}
        .content {{ background: #fff; padding: 15px; border: 1px solid #ddd; border-radius: 4px; white-space: pre-wrap; font-size: 12px; line-height: 1.4; overflow-x: auto; word-break: break-all; }}
        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .filepath {{ padding: 8px 10px; font-size: 11px; }}
            .content {{ padding: 10px; font-size: 11px; }}
        }}
    </style>
</head>
<body>
    <div class="filepath">
        <div class="filepath-label">File path:</div>
        {escape(str(filepath))}
    </div>
    <div class="content">{escape(content)}</div>
</body>
</html>'''

    @app.route("/download/<message_id>")
    def download_eml(message_id: str):
        """Download the original .eml file."""
        email_info = archive.db.get_email_by_id(message_id)
        if not email_info:
            abort(404)

        filename = email_info[1]
        filepath = archive.archive_dir / filename

        if not filepath.exists():
            abort(404)

        # Use the original filename or generate one from message_id
        download_name = filepath.name
        return send_file(filepath, as_attachment=True, download_name=download_name)

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
                    # Extract filename with proper charset handling
                    att_filename = _extract_attachment_filename(part)
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
    date_format: str = None,
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
        date_format: strftime format for dates (default: auto)
    """
    app = create_app(
        archive,
        verbose=verbose,
        block_images=block_images,
        page_size=page_size,
        trusted_senders=trusted_senders,
        config_path=config_path,
        date_format=date_format,
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
