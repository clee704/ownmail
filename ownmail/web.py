"""Web interface for browsing and searching the email archive."""

import base64
import email
import email.header
import html
import os
import re
import time
from datetime import datetime
from email.policy import default as email_policy
from email.utils import parsedate_to_datetime

from flask import Flask, abort, g, redirect, render_template, request, send_file
from zoneinfo import ZoneInfo

from ownmail.archive import EmailArchive
from ownmail.parser import EmailParser

# Regex to find external images in HTML
EXTERNAL_IMAGE_RE = re.compile(
    r'<img\s+([^>]*\s)?src\s*=\s*["\']?(https?://[^"\'>\s]+)["\']?',
    re.IGNORECASE,
)

# Regex to detect external URLs in CSS (background-image, etc.)
CSS_EXTERNAL_URL_RE = re.compile(
    r'url\(\s*["\']?(https?://[^"\')\s]+)["\']?\s*\)',
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


def _get_server_timezone_name() -> str:
    """Return the server's local timezone name (e.g. 'Asia/Seoul')."""
    try:
        # Try to get IANA name from /etc/localtime symlink (macOS / Linux)
        import subprocess
        result = subprocess.run(
            ["readlink", "/etc/localtime"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0 and "zoneinfo/" in result.stdout:
            return result.stdout.strip().split("zoneinfo/")[-1]
    except Exception:
        pass
    # Fallback: use TZ env var or UTC offset
    tz_env = os.environ.get("TZ")
    if tz_env:
        return tz_env
    offset = datetime.now().astimezone().strftime("%z")
    return f"UTC{offset[:3]}:{offset[3:]}"


# Common IANA timezones grouped by region for the settings dropdown
# Flat timezone list sorted by UTC offset, following industry standard.
# Covers all major offsets from UTC-12 to UTC+14 with representative cities.
COMMON_TIMEZONES = [
    "Pacific/Pago_Pago",          # UTC-11:00  Pago Pago
    "Pacific/Honolulu",           # UTC-10:00  Honolulu
    "America/Anchorage",          # UTC-09:00  Anchorage
    "America/Los_Angeles",        # UTC-08:00  Los Angeles
    "America/Vancouver",          # UTC-08:00  Vancouver
    "America/Denver",             # UTC-07:00  Denver
    "America/Phoenix",            # UTC-07:00  Phoenix (no DST)
    "America/Chicago",            # UTC-06:00  Chicago
    "America/Mexico_City",        # UTC-06:00  Mexico City
    "America/New_York",           # UTC-05:00  New York
    "America/Toronto",            # UTC-05:00  Toronto
    "America/Bogota",             # UTC-05:00  Bogota
    "America/Lima",               # UTC-05:00  Lima
    "America/Caracas",            # UTC-04:00  Caracas
    "America/Santiago",           # UTC-04:00  Santiago
    "America/Halifax",            # UTC-04:00  Halifax
    "America/St_Johns",           # UTC-03:30  St. John's
    "America/Sao_Paulo",          # UTC-03:00  São Paulo
    "America/Argentina/Buenos_Aires",  # UTC-03:00  Buenos Aires
    "Atlantic/South_Georgia",     # UTC-02:00  South Georgia
    "Atlantic/Azores",            # UTC-01:00  Azores
    "Atlantic/Cape_Verde",        # UTC-01:00  Cape Verde
    "UTC",                        # UTC+00:00
    "Europe/London",              # UTC+00:00  London
    "Africa/Lagos",               # UTC+01:00  Lagos
    "Europe/Paris",               # UTC+01:00  Paris
    "Europe/Berlin",              # UTC+01:00  Berlin
    "Europe/Amsterdam",           # UTC+01:00  Amsterdam
    "Europe/Rome",                # UTC+01:00  Rome
    "Europe/Madrid",              # UTC+01:00  Madrid
    "Europe/Zurich",              # UTC+01:00  Zurich
    "Europe/Stockholm",           # UTC+01:00  Stockholm
    "Africa/Cairo",               # UTC+02:00  Cairo
    "Africa/Johannesburg",        # UTC+02:00  Johannesburg
    "Europe/Athens",              # UTC+02:00  Athens
    "Europe/Bucharest",           # UTC+02:00  Bucharest
    "Europe/Helsinki",            # UTC+02:00  Helsinki
    "Europe/Kyiv",                # UTC+02:00  Kyiv
    "Asia/Jerusalem",             # UTC+02:00  Jerusalem
    "Europe/Istanbul",            # UTC+03:00  Istanbul
    "Europe/Moscow",              # UTC+03:00  Moscow
    "Asia/Riyadh",                # UTC+03:00  Riyadh
    "Africa/Nairobi",             # UTC+03:00  Nairobi
    "Asia/Baghdad",               # UTC+03:00  Baghdad
    "Asia/Tehran",                # UTC+03:30  Tehran
    "Asia/Dubai",                 # UTC+04:00  Dubai
    "Asia/Baku",                  # UTC+04:00  Baku
    "Asia/Kabul",                 # UTC+04:30  Kabul
    "Asia/Karachi",               # UTC+05:00  Karachi
    "Asia/Tashkent",              # UTC+05:00  Tashkent
    "Asia/Kolkata",               # UTC+05:30  Kolkata
    "Asia/Kathmandu",             # UTC+05:45  Kathmandu
    "Asia/Dhaka",                 # UTC+06:00  Dhaka
    "Asia/Yangon",                # UTC+06:30  Yangon
    "Asia/Bangkok",               # UTC+07:00  Bangkok
    "Asia/Jakarta",               # UTC+07:00  Jakarta
    "Asia/Ho_Chi_Minh",           # UTC+07:00  Ho Chi Minh City
    "Asia/Shanghai",              # UTC+08:00  Shanghai
    "Asia/Hong_Kong",             # UTC+08:00  Hong Kong
    "Asia/Taipei",                # UTC+08:00  Taipei
    "Asia/Singapore",             # UTC+08:00  Singapore
    "Asia/Kuala_Lumpur",          # UTC+08:00  Kuala Lumpur
    "Asia/Manila",                # UTC+08:00  Manila
    "Australia/Perth",            # UTC+08:00  Perth
    "Asia/Seoul",                 # UTC+09:00  Seoul
    "Asia/Tokyo",                 # UTC+09:00  Tokyo
    "Australia/Adelaide",         # UTC+09:30  Adelaide
    "Australia/Sydney",           # UTC+10:00  Sydney
    "Australia/Melbourne",        # UTC+10:00  Melbourne
    "Australia/Brisbane",         # UTC+10:00  Brisbane (no DST)
    "Pacific/Guam",               # UTC+10:00  Guam
    "Pacific/Noumea",             # UTC+11:00  Noumea
    "Pacific/Auckland",           # UTC+12:00  Auckland
    "Pacific/Fiji",               # UTC+12:00  Fiji
    "Pacific/Tongatapu",          # UTC+13:00  Nuku'alofa
    "Pacific/Kiritimati",         # UTC+14:00  Kiritimati
]


def _get_timezone_offset(tz_name: str) -> str:
    """Return the current UTC offset string for a timezone (e.g. '-05:00').

    Returns empty string if the timezone cannot be resolved.
    """
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        offset = now.strftime("%z")  # e.g. "-0500"
        return f"{offset[:3]}:{offset[3:]}"  # e.g. "-05:00"
    except Exception:
        return ""


def _get_timezone_list_with_offsets() -> list:
    """Return COMMON_TIMEZONES as a flat list with UTC offset labels.

    Each zone becomes a dict with 'value' (IANA name) and 'label' (display text).
    Format: (UTC-05:00) America/New_York
    """
    items = []
    for tz_name in COMMON_TIMEZONES:
        offset = _get_timezone_offset(tz_name)
        label = f"(UTC{offset}) {tz_name}" if offset else tz_name
        items.append({"value": tz_name, "label": label})
    return items


def _resolve_timezone(tz_name: str | None) -> ZoneInfo | None:
    """Resolve a timezone name to a ZoneInfo object.

    Returns None if the name is invalid or empty (meaning: use server local).
    """
    if not tz_name:
        return None
    try:
        return ZoneInfo(tz_name)
    except (KeyError, Exception):
        return None


def _to_local_datetime(date_str: str, tz: ZoneInfo | None = None) -> datetime | None:
    """Parse an RFC 2822 date string and convert to the given timezone.

    Args:
        date_str: RFC 2822 date string
        tz: Target timezone (None = server's local timezone)

    Returns None if the date string cannot be parsed.
    """
    if not date_str:
        return None
    try:
        parsed = parsedate_to_datetime(date_str)
        if tz:
            return parsed.astimezone(tz)
        return parsed.astimezone()  # Convert to system local timezone
    except Exception:
        return None


# Default date formats
SEARCH_DATE_FORMAT = "%b %d, %Y"  # e.g. "Jan 27, 2026"
DETAIL_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S"  # e.g. "Tue, 27 Jan 2026 07:16:05"


def _format_date_short(dt: datetime, date_fmt: str | None = None) -> str:
    """Format a datetime as a short date string for search results.

    Uses the configured format if set, otherwise defaults to 'Jan 27, 2026'.
    """
    return dt.strftime(date_fmt or SEARCH_DATE_FORMAT)


def _format_date_long(dt: datetime, date_fmt: str | None = None) -> str:
    """Format a datetime as a full date string for email detail view.

    Uses the configured format if set, otherwise defaults to
    'Tue, 27 Jan 2026 07:16:05' (no timezone).
    """
    return dt.strftime(date_fmt or DETAIL_DATE_FORMAT)


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


def _extract_body_content(html: str) -> str:
    """Extract body content from a full HTML document for direct embedding.

    Strips <html>, <head>, <body> wrappers and extracts just the content
    that goes inside the email container div. Preserves <style> tags
    from <head> so scoped CSS still applies.

    Args:
        html: Full HTML document or fragment

    Returns:
        Body content suitable for direct embedding in a div
    """
    if not html:
        return html

    # Extract <style> tags from anywhere (they may be in <head>)
    styles = []
    style_pattern = re.compile(r'<style[^>]*>[\s\S]*?</style>', re.IGNORECASE)
    for match in style_pattern.finditer(html):
        styles.append(match.group())

    # Try to extract body content
    body_match = re.search(
        r'<body[^>]*>(.*)</body>',
        html,
        re.IGNORECASE | re.DOTALL
    )
    if body_match:
        content = body_match.group(1)
    else:
        # No <body> tag — might be a fragment, use as-is
        # Strip <html> and <head> wrappers if present
        content = re.sub(r'</?html[^>]*>', '', html, flags=re.IGNORECASE)
        content = re.sub(r'<head[^>]*>[\s\S]*?</head>', '', content, flags=re.IGNORECASE)

    # Remove any <style> tags already in content (we'll prepend all styles)
    content_without_styles = style_pattern.sub('', content)

    # Prepend all collected styles
    if styles:
        return '\n'.join(styles) + '\n' + content_without_styles
    return content_without_styles


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
    through, MIME headers embedded in body text, and repetitive padding
    characters.

    Uses lxml for HTML stripping (handles malformed/truncated tags properly).
    """
    if not text:
        return text

    # Strip leading MIME headers embedded in body text
    # Some senders (e.g. USPS) accidentally include MIME headers in the body
    text = re.sub(
        r'^(\s*Content-(?:Type|Transfer-Encoding|Disposition)[^\n]*\n)+\s*',
        '', text, flags=re.IGNORECASE
    )

    # Strip HTML tags using lxml (handles malformed/truncated tags properly)
    if '<' in text:
        try:
            from lxml import html as lxml_html

            tree = lxml_html.fromstring(text)
            # Remove elements that shouldn't contribute text,
            # preserving tail text (text after the closing tag)
            for element in tree.xpath('//style | //script | //head | //noscript'):
                tail = element.tail
                parent = element.getparent()
                if parent is not None:
                    if tail:
                        prev = element.getprevious()
                        if prev is not None:
                            prev.tail = (prev.tail or "") + tail
                        else:
                            parent.text = (parent.text or "") + tail
                    parent.remove(element)
            text = tree.text_content()
        except Exception:
            # Fallback: simple regex if lxml fails
            text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'<[^>]*$', '', text)

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
    # Matches ".class { ... }", "#id { ... }", and element selectors like
    # "body { ... }", "table, td, tr { ... }", "* { ... }", "@media (...) { ... }"
    text = re.sub(r'[.#][\w-]+\s*\{[^}]*\}', '', text)
    text = re.sub(r'(?:^|\s)(?:[a-z][a-z0-9-]*(?:\s*,\s*[a-z][a-z0-9-]*)*|\*)\s*\{[^}]*\}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'@media\s*[^{]*\{[^}]*(?:\{[^}]*\}[^}]*)*\}', '', text)
    # Remove CSS selectors with attribute selectors like a[x-apple-data-detectors=true]
    text = re.sub(r'\w+\[[^\]]+\]\s*\{[^}]*\}', '', text)

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


# Regex patterns for linkifying plain text
URL_RE = re.compile(
    r'(https?://[^\s<>"\')\]]+)',
    re.IGNORECASE
)
EMAIL_RE = re.compile(
    r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
)
# Header patterns for embedded messages
HEADER_RE = re.compile(
    r'^(From|Subject|Date|To|Reply-To|Cc|Bcc):\s*',
    re.IGNORECASE
)
# Quote level pattern (lines starting with >)
QUOTE_RE = re.compile(r'^(&gt;)+')


def _linkify_line(line: str) -> str:
    """Linkify a single line of text (already HTML-escaped)."""
    # Replace URLs with links
    line = URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', line)

    # Replace email addresses with mailto links
    # But not if they're already inside an href (from URL linking)
    def replace_email(match):
        email_addr = match.group(1)
        start = match.start()
        preceding = line[:start]
        last_href = preceding.rfind('href="')
        last_close = max(preceding.rfind('>'), preceding.rfind('"'))
        if last_href > last_close:
            return email_addr
        return f'<a href="mailto:{email_addr}" rel="noopener noreferrer">{email_addr}</a>'

    return EMAIL_RE.sub(replace_email, line)


def _linkify(text: str) -> str:
    """Convert URLs, emails, headers, and quotes in plain text to styled HTML.

    Args:
        text: Plain text content

    Returns:
        HTML with URLs/emails as links, headers styled, quotes colored
    """
    lines = text.split('\n')
    result_lines = []

    colors = ['#58a6c9', '#7ee787', '#f0a855', '#d2a8ff']
    current_depth = 0

    for line in lines:
        escaped = html.escape(line)

        # Check for quote markers (>, >>, etc.)
        quote_match = QUOTE_RE.match(escaped)
        if quote_match:
            depth = quote_match.group(0).count('&gt;')
            rest = escaped[quote_match.end():]
            rest = _linkify_line(rest)

            # Adjust nesting level
            while current_depth < depth:
                color = colors[current_depth % len(colors)]
                result_lines.append(
                    f'<div class="ownmail-quote-level" style="border-left: 2px solid {color}; '
                    f'color: {color}; padding-left: 6px; margin-left: 0;">'
                )
                current_depth += 1

            while current_depth > depth:
                result_lines.append('</div>')
                current_depth -= 1

            # Add the content line
            result_lines.append(f'<div class="ownmail-quote-content">{rest or "&nbsp;"}</div>')
            continue

        # Close all quote levels before non-quote content
        while current_depth > 0:
            result_lines.append('</div>')
            current_depth -= 1

        # Check for header lines (From:, Subject:, etc.)
        header_match = HEADER_RE.match(escaped)
        if header_match:
            label = header_match.group(1)
            rest = escaped[header_match.end():]
            rest = _linkify_line(rest)
            result_lines.append(
                f'<div><span class="ownmail-email-header-label">{label}:</span> {rest}</div>'
            )
            continue

        # Regular line - wrap in div
        result_lines.append(f'<div>{_linkify_line(escaped) or "&nbsp;"}</div>')

    # Close any remaining quote levels
    while current_depth > 0:
        result_lines.append('</div>')
        current_depth -= 1

    return ''.join(result_lines)


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

    Handles both <img src="..."> and CSS url() in inline styles and
    <style> blocks (background-image, list-style-image, etc.).

    Args:
        html: HTML content

    Returns:
        Tuple of (modified HTML, whether external images were found)
    """
    has_img = bool(EXTERNAL_IMAGE_RE.search(html))
    has_css = bool(CSS_EXTERNAL_URL_RE.search(html))
    if not has_img and not has_css:
        return html, False

    blocked_html = html

    # Block <img src="https://...">
    if has_img:
        def replace_src(match):
            prefix = match.group(1) or ""
            url = match.group(2)
            return f'<img {prefix}data-src="{url}" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"'

        blocked_html = EXTERNAL_IMAGE_RE.sub(replace_src, blocked_html)

    # Block CSS url(https://...) -> url() with data-bg attribute on the element
    # For inline styles, replace url() with a transparent placeholder
    if has_css:
        def replace_css_url(match):
            return 'url(data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7)'

        # Replace in inline style="..." attributes, preserving original in data-bg-urls
        def replace_inline_style(match):
            full = match.group(0)
            style_val = match.group(1)
            # Extract all external URLs from this style
            urls = CSS_EXTERNAL_URL_RE.findall(style_val)
            if not urls:
                return full
            new_style = CSS_EXTERNAL_URL_RE.sub(replace_css_url, style_val)
            # Store originals in data attribute for restoration
            url_str = " ".join(urls)
            return f'style="{new_style}" data-bg-urls="{url_str}"'

        blocked_html = re.sub(
            r'style="([^"]*url\s*\([^)]*https?://[^)]*\)[^"]*)"',
            replace_inline_style, blocked_html, flags=re.IGNORECASE
        )

    return blocked_html, True


def parse_email_address(addr: str) -> tuple:
    """Parse email address into (name, email) tuple.

    Args:
        addr: Email address string like "John Doe <john@example.com>" or "john@example.com"
              Handles quoted names with special chars: "옥션<발신전용>" <auction@auction.co.kr>

    Returns:
        Tuple of (name, email) where name may be empty
    """
    if not addr:
        return ("", "")

    addr = addr.strip()

    # Find the last <...> which should contain the email address
    last_open = addr.rfind('<')
    if last_open != -1 and addr.endswith('>'):
        email_addr = addr[last_open + 1:-1].strip()
        name = addr[:last_open].strip()
        # Strip surrounding quotes from name and unescape internal quotes
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1].replace('\\"', '"').strip()
        return (name, email_addr)

    # Try to match just email
    match = re.match(r'^<?([^@\s]+@[^>\s]+)>?$', addr)
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


class _PassthroughSanitizer:
    """No-op sanitizer that returns HTML unchanged. Used in tests."""

    available = True

    def sanitize(self, html: str):
        return html, True, False

    def stop(self):
        pass


def create_app(
    archive: EmailArchive,
    verbose: bool = False,
    block_images: bool = False,
    page_size: int = 20,
    trusted_senders: list = None,
    config_path: str = None,
    date_format: str = None,
    auto_scale: bool = True,
    brand_name: str = "ownmail",
    sanitizer=None,
    display_timezone: str = None,
    detail_date_format: str = None,
) -> Flask:
    """Create the Flask application.

    Args:
        archive: EmailArchive instance
        verbose: Enable request timing logs
        block_images: Block external images by default
        page_size: Number of results per page
        trusted_senders: List of email addresses to always show images from
        config_path: Path to config.yaml for updating trusted senders
        date_format: strftime format for search result dates (default: "%b %d, %Y")
        auto_scale: Scale down wide emails to fit viewport
        brand_name: Custom branding name shown in header
        sanitizer: HTML sanitizer instance (default: passthrough for tests)
        display_timezone: IANA timezone name (default: server local)
        detail_date_format: strftime format for message view dates (default: "%a, %d %b %Y %H:%M:%S")

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
    app.config["date_format"] = date_format  # None = default
    app.config["detail_date_format"] = detail_date_format  # None = default
    app.config["timezone"] = _resolve_timezone(display_timezone)
    app.config["timezone_name"] = display_timezone or ""
    app.config["auto_scale"] = auto_scale
    app.config["brand_name"] = brand_name
    app.config["sanitizer"] = sanitizer or _PassthroughSanitizer()

    @app.context_processor
    def inject_brand():
        return {"brand_name": app.config["brand_name"]}

    # CSRF protection: validate Origin/Referer on POST requests
    @app.before_request
    def csrf_check():
        if request.method == "POST":
            origin = request.headers.get("Origin") or ""
            referer = request.headers.get("Referer") or ""
            # Accept if Origin or Referer starts with our own URL
            # (flask test client sends neither, so allow empty for tests)
            if not origin and not referer:
                return  # Allow (e.g., curl, test client)
            host_url = request.host_url.rstrip("/")
            if origin and origin.rstrip("/") == host_url:
                return
            if referer and referer.startswith(host_url):
                return
            abort(403)

    def get_stats():
        """Get email count stats."""
        return {"total_emails": archive.db.get_email_count()}

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
        stats = get_stats()
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
        per_page = app.config["page_size"]
        stats = get_stats()

        # Check if query is filter-only (no FTS search terms)
        # Remove known filters to see if any search terms remain
        query_without_filters = query
        for pattern in [
            r'\b(?:before|after):\d{4}-?\d{2}-?\d{2}\b',
            r'\b(?:label|tag):(?:"[^"]*"|\S+)\b',
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

        if verbose:
            print(f"[verbose] Searching for: {query} (page {page}, offset {offset}, sort {sort})", flush=True)
            start = time.time()

        # Fetch per_page + 1 to know if there are more results
        try:
            raw_results = archive.search(query, limit=per_page + 1, offset=offset, sort=sort, tz=app.config.get("timezone"))
            search_error = None
        except Exception as e:
            raw_results = []
            search_error = str(e)
            if verbose:
                print(f"[verbose] Search error: {e}", flush=True)

        if verbose and not search_error:
            print(f"[verbose] Search took {time.time()-start:.2f}s, {len(raw_results)} results", flush=True)

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
            sender_name, sender_email_parsed = parse_email_address(sender) if sender else ("", "")
            if not sender_name:
                # Fall back to email or full sender string
                sender_name = sender_email_parsed or sender or ""

            # Format date as short date (converted to configured timezone)
            date_short = ""
            local_dt = _to_local_datetime(date_str, app.config.get("timezone"))
            if local_dt:
                date_short = _format_date_short(local_dt, app.config.get("date_format"))
            elif date_str:
                # Fall back to extracting date part from string
                date_short = date_str.split()[0]

            results.append({
                "email_id": msg_id,
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

    @app.route("/email/<email_id>")
    def view_email(email_id: str):
        stats = get_stats()

        # Get email file path from database
        if verbose:
            print(f"[verbose] Looking up email {email_id}...", flush=True)
            start = time.time()
        email_info = archive.db.get_email_by_id(email_id)
        if verbose:
            print(f"[verbose] DB lookup took {time.time()-start:.2f}s", flush=True)
        if not email_info:
            abort(404)

        filename = email_info[1]  # filename is second column
        filepath = archive.archive_dir / filename

        if not filepath.exists():
            abort(404)

        # Get labels from email_labels table
        labels = archive.db.get_labels_for_email(email_id)

        # Parse email using EmailParser for proper Korean charset handling
        if verbose:
            start = time.time()

        # Use EmailParser for headers (handles Korean charset properly)
        parsed = EmailParser.parse_file(filepath=filepath)
        subject = parsed.get("subject") or "(No subject)"
        sender = parsed.get("sender", "")
        recipients = parsed.get("recipients", "")
        raw_date = parsed.get("date_str", "")
        local_dt = _to_local_datetime(raw_date, app.config.get("timezone"))
        date = _format_date_long(local_dt, app.config.get("detail_date_format")) if local_dt else raw_date

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
        body_parts = []  # Collect text parts from top-level only
        embedded_messages = []  # Collect embedded message/rfc822 for digests
        attachments = []
        cid_images = {}  # Content-ID -> data URI mapping

        if msg.is_multipart():
            # Track depth to skip content nested inside message/rfc822 parts
            # These are embedded messages (like in digests) that shouldn't be
            # concatenated into the main body
            inside_message_rfc822 = 0

            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Handle embedded message/rfc822 parts (digest entries)
                if content_type == "message/rfc822":
                    inside_message_rfc822 += 1
                    # Extract embedded message for digest display
                    try:
                        embedded = part.get_payload(0)
                        if embedded:
                            emb_from = decode_header(embedded.get("From", ""))
                            emb_subject = decode_header(embedded.get("Subject", ""))
                            emb_date = embedded.get("Date", "")
                            emb_to = decode_header(embedded.get("To", ""))
                            emb_reply_to = decode_header(embedded.get("Reply-To", ""))

                            # Get body and attachments of embedded message
                            emb_body = ""
                            for sub in embedded.walk():
                                sub_ct = sub.get_content_type()
                                sub_disp = str(sub.get("Content-Disposition", ""))

                                # Check for attachments inside embedded message
                                if "attachment" in sub_disp or sub.get_filename():
                                    att_filename = _extract_attachment_filename(sub)
                                    payload = sub.get_payload(decode=True)
                                    size = len(payload) if payload else 0
                                    attachments.append({
                                        "filename": att_filename,
                                        "size": _format_size(size),
                                    })
                                elif sub_ct == "text/plain" and not emb_body:
                                    payload = sub.get_payload(decode=True)
                                    if payload:
                                        emb_body = _decode_text_body(payload, sub.get_content_charset())

                            embedded_messages.append({
                                "from": emb_from,
                                "subject": emb_subject,
                                "date": emb_date,
                                "to": emb_to,
                                "reply_to": emb_reply_to,
                                "body": emb_body,
                            })
                    except Exception:
                        pass
                    continue

                # Extract inline images with Content-ID (for cid: references)
                content_id = part.get("Content-ID", "")
                if content_id and content_type.startswith("image/"):
                    # Content-ID is often wrapped in angle brackets
                    cid = content_id.strip("<>")
                    payload = part.get_payload(decode=True)
                    if payload:
                        data_uri = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
                        cid_images[cid] = data_uri

                # Skip content inside embedded messages (already extracted above)
                if inside_message_rfc822 > 0:
                    continue

                if "attachment" in content_disposition:
                    # Extract filename with proper charset handling
                    att_filename = _extract_attachment_filename(part)
                    size = len(part.get_payload(decode=True) or b"")
                    attachments.append({
                        "filename": att_filename,
                        "size": _format_size(size),
                    })
                elif content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        # Collect text/plain parts from main message
                        text = _decode_text_body(payload, part.get_content_charset())
                        if text:
                            body_parts.append(text)
                elif content_type == "text/html" and not body_html:
                    payload = part.get_payload(decode=True)
                    if payload:
                        # Use helper that can extract charset from HTML meta tag
                        body_html = _decode_html_body(payload, part.get_content_charset())

            # Combine all text parts
            if body_parts:
                body = "\n\n".join(body_parts)

            # Append embedded messages (for digest emails)
            if embedded_messages:
                for emb in embedded_messages:
                    separator = "\n" + "-" * 60 + "\n"
                    header_lines = []
                    if emb["from"]:
                        header_lines.append(f"From: {emb['from']}")
                    if emb["subject"]:
                        header_lines.append(f"Subject: {emb['subject']}")
                    if emb["date"]:
                        header_lines.append(f"Date: {emb['date']}")
                    if emb["to"]:
                        header_lines.append(f"To: {emb['to']}")
                    if emb["reply_to"]:
                        header_lines.append(f"Reply-To: {emb['reply_to']}")
                    headers = "\n".join(header_lines)
                    body += separator + headers + "\n\n" + emb["body"]
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

        email_data = {
            "subject": subject,
            "sender": sender,
            "recipients": recipients,
            "date": date,
            "labels": labels,
            "body": body,
            "body_html": body_html,
            "attachments": attachments,
            "cid_images": cid_images,
        }

        # Block external images if configured
        body_html = email_data.get("body_html")
        cid_images = email_data.get("cid_images", {})
        has_external_images = False
        images_blocked = app.config["block_images"]

        # Replace cid: references with inline data URIs
        if body_html and cid_images:
            for cid, data_uri in cid_images.items():
                # cid references can appear as "cid:xxx" in src attributes
                body_html = body_html.replace(f'cid:{cid}', data_uri)

        # Sanitize HTML/CSS using DOMPurify sidecar
        needs_padding = True
        supports_dark = False
        if body_html:
            sanitizer = app.config["sanitizer"]
            if verbose:
                print(f"[verbose] Sanitizing HTML ({len(body_html):,} chars)...", flush=True)
            body_html, needs_padding, supports_dark = sanitizer.sanitize(body_html)

        # Parse sender and recipients for clickable links
        sender_name, sender_email = parse_email_address(email_data["sender"])
        recipients_parsed = parse_recipients(email_data["recipients"])

        # Check if sender is trusted (skip image blocking for trusted senders)
        trusted_senders = app.config.get("trusted_senders", set())
        sender_is_trusted = sender_email and sender_email.lower() in trusted_senders
        if sender_is_trusted:
            images_blocked = False

        # Always detect external images so dropdown menu can show load/block actions
        if body_html and (EXTERNAL_IMAGE_RE.search(body_html) or CSS_EXTERNAL_URL_RE.search(body_html)):
            has_external_images = True

        if body_html and images_blocked and has_external_images:
            body_html, _ = block_external_images(body_html)

        # Extract just the body content for direct embedding
        # (strip <html>, <head>, <body> wrappers since we embed into our page)
        if body_html:
            body_html = _extract_body_content(body_html)

        # Get back URL if user came from search
        back_url = get_back_to_search_url()

        # Linkify plain text body for clickable URLs and emails
        body_linkified = _linkify(email_data["body"]) if email_data["body"] else ""

        return render_template(
            "email.html",
            stats=stats,
            email_id=email_id,
            subject=email_data["subject"],
            sender=email_data["sender"],
            sender_name=sender_name,
            sender_email=sender_email,
            recipients=email_data["recipients"],
            recipients_parsed=recipients_parsed,
            date=email_data["date"],
            labels=email_data["labels"],
            body=body_linkified,
            body_html=body_html,
            attachments=email_data["attachments"],
            images_blocked=images_blocked,
            has_external_images=has_external_images,
            sender_is_trusted=sender_is_trusted,
            needs_padding=needs_padding,
            supports_dark=supports_dark,
            auto_scale=app.config["auto_scale"],
            back_url=back_url,
        )

    @app.route("/raw/<email_id>")
    def view_raw(email_id: str):
        """Show the original .eml file with filepath."""
        email_info = archive.db.get_email_by_id(email_id)
        if not email_info:
            abort(404)

        filename = email_info[1]
        filepath = (archive.archive_dir / filename).resolve()
        if not filepath.is_relative_to(archive.archive_dir.resolve()):
            abort(404)

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
        .ownmail-filepath {{ background: #fff; padding: 10px 15px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 15px; word-break: break-all; font-size: 13px; }}
        .ownmail-filepath-label {{ color: #666; font-size: 11px; margin-bottom: 5px; }}
        .ownmail-content {{ background: #fff; padding: 15px; border: 1px solid #ddd; border-radius: 4px; white-space: pre-wrap; font-size: 12px; line-height: 1.4; overflow-x: auto; word-break: break-all; }}
        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .ownmail-filepath {{ padding: 8px 10px; font-size: 11px; }}
            .ownmail-content {{ padding: 10px; font-size: 11px; }}
        }}
    </style>
</head>
<body>
    <div class="ownmail-filepath">
        <div class="ownmail-filepath-label">File path:</div>
        {escape(str(filepath))}
    </div>
    <div class="ownmail-content">{escape(content)}</div>
</body>
</html>'''

    @app.route("/download/<email_id>")
    def download_eml(email_id: str):
        """Download the original .eml file."""
        email_info = archive.db.get_email_by_id(email_id)
        if not email_info:
            abort(404)

        filename = email_info[1]
        filepath = (archive.archive_dir / filename).resolve()
        if not filepath.is_relative_to(archive.archive_dir.resolve()):
            abort(404)

        if not filepath.exists():
            abort(404)

        # Use the original filename or generate one from email_id
        download_name = filepath.name
        return send_file(filepath, as_attachment=True, download_name=download_name)

    @app.route("/attachment/<email_id>/<int:index>")
    def download_attachment(email_id: str, index: int):
        # Get email file path
        email_info = archive.db.get_email_by_id(email_id)
        if not email_info:
            abort(404)

        filename = email_info[1]
        filepath = (archive.archive_dir / filename).resolve()
        if not filepath.is_relative_to(archive.archive_dir.resolve()):
            abort(404)

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

                    # Send directly from memory
                    import io
                    return send_file(
                        io.BytesIO(att_data),
                        mimetype=content_type,
                        as_attachment=True,
                        download_name=att_filename,
                    )
                attachment_idx += 1

        abort(404)

    @app.route("/settings", methods=["GET"])
    def settings_page():
        """Show settings page with current configuration."""
        config_path = app.config.get("config_path")
        config_data = {}
        if config_path:
            try:
                from ownmail.yaml_util import load_yaml

                config_data = load_yaml(config_path)
            except Exception:
                pass

        web_config = config_data.get("web", {})
        current = {
            "page_size": web_config.get("page_size", 20),
            "block_images": web_config.get("block_images", True),
            "auto_scale": web_config.get("auto_scale", True),
            "date_format": web_config.get("date_format", ""),
            "detail_date_format": web_config.get("detail_date_format", ""),
            "timezone": web_config.get("timezone", ""),
            "brand_name": web_config.get("brand_name", "ownmail"),
            "trusted_senders": web_config.get("trusted_senders", []),
        }
        server_timezone = _get_server_timezone_name()
        server_offset = _get_timezone_offset(server_timezone)
        server_tz_label = f"(UTC{server_offset}) {server_timezone}" if server_offset else server_timezone
        return render_template(
            "settings.html",
            settings=current,
            stats=get_stats(),
            config_path=config_path or "(not set)",
            saved=request.args.get("saved") == "1",
            server_timezone=server_tz_label,
            timezone_list=_get_timezone_list_with_offsets(),
        )

    @app.route("/settings", methods=["POST"])
    def save_settings():
        """Save settings to config.yaml and update in-memory config."""
        from ownmail.yaml_util import load_yaml, save_yaml

        config_path = app.config.get("config_path")
        if not config_path:
            return redirect("/settings")

        try:
            config_data = load_yaml(config_path)
        except Exception:
            config_data = {}

        web_config = config_data.setdefault("web", {})

        # Update settings from form
        try:
            page_size = int(request.form.get("page_size", 20))
            if page_size < 1:
                page_size = 1
            elif page_size > 500:
                page_size = 500
        except (ValueError, TypeError):
            page_size = 20
        web_config["page_size"] = page_size
        app.config["page_size"] = page_size

        block_images = request.form.get("block_images") == "on"
        web_config["block_images"] = block_images
        app.config["block_images"] = block_images

        auto_scale = request.form.get("auto_scale") == "on"
        web_config["auto_scale"] = auto_scale
        app.config["auto_scale"] = auto_scale

        date_format = request.form.get("date_format", "").strip()
        web_config["date_format"] = date_format if date_format else None
        if date_format:
            app.config["date_format"] = date_format
        else:
            app.config["date_format"] = None

        detail_date_format = request.form.get("detail_date_format", "").strip()
        web_config["detail_date_format"] = detail_date_format if detail_date_format else None
        if detail_date_format:
            app.config["detail_date_format"] = detail_date_format
        else:
            app.config["detail_date_format"] = None

        tz_name = request.form.get("timezone", "").strip()
        web_config["timezone"] = tz_name if tz_name else None
        app.config["timezone"] = _resolve_timezone(tz_name)
        app.config["timezone_name"] = tz_name

        brand_name = request.form.get("brand_name", "").strip() or "ownmail"
        web_config["brand_name"] = brand_name
        app.config["brand_name"] = brand_name

        # Trusted senders: textarea, one per line
        trusted_raw = request.form.get("trusted_senders", "")
        trusted_list = [
            s.strip().lower()
            for s in trusted_raw.splitlines()
            if s.strip()
        ]
        web_config["trusted_senders"] = trusted_list
        app.config["trusted_senders"] = set(trusted_list)

        try:
            save_yaml(config_data, config_path)
        except Exception as e:
            if verbose:
                print(f"[verbose] Error saving settings: {e}", flush=True)

        return redirect("/settings?saved=1")

    @app.route("/trust-sender", methods=["POST"])
    def trust_sender():
        """Add a sender to the trusted senders list in config.yaml."""
        sender_email = request.form.get("email", "").strip().lower()
        redirect_to = request.form.get("redirect", "/")
        if not redirect_to.startswith("/"):
            redirect_to = "/"

        if not sender_email:
            return redirect(redirect_to)

        config_path = app.config.get("config_path")
        if not config_path:
            # No config path, just update in-memory
            app.config["trusted_senders"].add(sender_email)
            return redirect(redirect_to)

        try:
            # Read current config
            from ownmail.yaml_util import load_yaml, save_yaml
            config_data = load_yaml(config_path)

            # Add to trusted_senders
            web_config = config_data.setdefault("web", {})
            trusted_list = web_config.setdefault("trusted_senders", [])
            if sender_email not in trusted_list:
                trusted_list.append(sender_email)

                # Write back
                save_yaml(config_data, config_path)

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
                from ownmail.yaml_util import load_yaml, save_yaml
                config_data = load_yaml(config_path)

                # Remove from trusted_senders
                web_config = config_data.get("web", {})
                trusted_list = web_config.get("trusted_senders", [])
                if sender_email in trusted_list:
                    trusted_list.remove(sender_email)

                    # Write back
                    save_yaml(config_data, config_path)

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
    auto_scale: bool = True,
    brand_name: str = "ownmail",
    display_timezone: str = None,
    detail_date_format: str = None,
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
        date_format: strftime format for search result dates (default: "%b %d, %Y")
        auto_scale: Scale down wide emails to fit viewport
        brand_name: Custom branding name shown in header
        display_timezone: IANA timezone name (default: server local)
        detail_date_format: strftime format for message view dates (default: "%a, %d %b %Y %H:%M:%S")
    """
    # Start HTML sanitizer sidecar (DOMPurify via Node.js)
    from ownmail.sanitizer import HtmlSanitizer

    sanitizer = HtmlSanitizer(verbose=verbose)
    sanitizer.start()

    app = create_app(
        archive,
        verbose=verbose,
        block_images=block_images,
        page_size=page_size,
        trusted_senders=trusted_senders,
        config_path=config_path,
        date_format=date_format,
        auto_scale=auto_scale,
        brand_name=brand_name,
        sanitizer=sanitizer,
        display_timezone=display_timezone,
        detail_date_format=detail_date_format,
    )

    print(f"\n🌐 {brand_name} web interface")
    print(f"   Running at: http://{host}:{port}")
    print(f"   Page size: {page_size}")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("\n   ⚠️  WARNING: Binding to non-localhost address!")
        print("   Your email archive will be accessible to anyone on the network.")
        print("   Consider using --host 127.0.0.1 instead.\n")
    if debug and host not in ("127.0.0.1", "localhost", "::1"):
        print("   ERROR: --debug cannot be used with non-localhost --host")
        print("   The Werkzeug debugger allows remote code execution.")
        sanitizer.stop()
        return
    if verbose:
        print("   Verbose logging enabled")
    if block_images:
        print("   External images blocked by default")
    if trusted_senders:
        print(f"   Trusted senders: {len(trusted_senders)}")
    if not sanitizer.available:
        print("\n   ERROR: HTML sanitizer failed to start.")
        print("   Install Node.js and run: cd ownmail/sanitizer && npm install")
        print("   Refusing to serve without sanitization.\n")
        return
    print("   HTML sanitization enabled (DOMPurify)")
    print("   Press Ctrl+C to stop\n")

    try:
        app.run(host=host, port=port, debug=debug)
    finally:
        sanitizer.stop()
