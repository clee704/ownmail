"""Email parser for extracting searchable content from .eml files."""

import base64
import email
import email.utils
import html
import re
from email.policy import default as email_policy
from pathlib import Path

from lxml import html as lxml_html

# Regex to extract charset from HTML meta tag
HTML_CHARSET_RE = re.compile(
    r'<meta[^>]+charset\s*=\s*["\']?([a-zA-Z0-9_-]+)',
    re.IGNORECASE,
)

# Charset aliases for various encodings
CHARSET_ALIASES = {
    "ks_c_5601-1987": "cp949",
    "ks_c_5601": "cp949",
    "euc-kr": "euc-kr",
    "euc_kr": "euc-kr",
    "gb2312": "gb2312",
    "gbk": "gbk",
    "big5": "big5",
    "shift_jis": "shift_jis",
    "euc-jp": "euc-jp",
}

# Encoding groups for smart detection
# Maps byte range patterns to likely encodings
ENCODING_FAMILIES = [
    # (name, encodings_to_try, validation_func)
    ("cjk", ["utf-8", "cp949", "euc-kr", "gb2312", "gbk", "big5", "shift_jis", "euc-jp"], None),
]

# Pre-compiled regex patterns for performance
WHITESPACE_RE = re.compile(r"\s+")
NON_ASCII_DATE_PREFIX_RE = re.compile(r"^[^\x00-\x7F]+,?\s*")
NUMERIC_DATE_RE = re.compile(r"(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([+-]?\d{1,4})?")
STYLE_TAG_RE = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
SCRIPT_TAG_RE = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")

# Charset mapping for known aliases (used in charset detection)
CHARSET_MAP = {
    "ks_c_5601-1987": "cp949",
    "ks_c_5601": "cp949",
    "ks_c_5601_1987": "cp949",
    "euc-kr": "cp949",  # Treat EUC-KR as CP949 (superset)
}

# Default encoding fallback chain for CJK and Cyrillic support
DEFAULT_ENCODING_CHAIN = [
    "utf-8",
    "cp949",
    "euc-kr",
    "gb2312",
    "shift_jis",
    "cp1251",
    "koi8-r",  # Russian/Cyrillic
    "iso-8859-1",
]


def _detect_charset(raw_bytes: bytes, declared_charset: str = None) -> str:
    """Detect the best charset to decode raw bytes.

    Encapsulates the fallback chain logic for charset detection.

    Args:
        raw_bytes: Raw bytes to decode
        declared_charset: Charset declared in headers (may be wrong)

    Returns:
        Best charset string to use for decoding
    """
    # Normalize and map declared charset
    if declared_charset:
        declared_lower = declared_charset.lower()
        # Handle unknown/invalid charset declarations
        if declared_lower in ("unknown", "unknown-8bit"):
            declared_charset = None
        else:
            declared_charset = CHARSET_MAP.get(declared_lower, declared_charset)

    # Build encoding chain with declared charset first if provided
    encodings_to_try = []
    if declared_charset:
        encodings_to_try.append(declared_charset)
    encodings_to_try.extend(enc for enc in DEFAULT_ENCODING_CHAIN if enc not in encodings_to_try)

    # Try each encoding, return first that decodes cleanly
    for enc in encodings_to_try:
        try:
            decoded = raw_bytes.decode(enc)
            # Check for replacement characters (decoding failed)
            if "\ufffd" not in decoded:
                return enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback to UTF-8 with replacement
    return "utf-8"


def _decode_grouped_rfc2047_parts(parts: list, fallback_charset: str = None) -> str:
    """Decode RFC 2047 encoded-word parts, handling split multi-byte characters.

    Groups adjacent same-charset encoded-words to handle malformed emails
    that split multi-byte characters across encoded-words.

    Args:
        parts: List of (content, charset) tuples from email.header.decode_header()
        fallback_charset: Charset to try if declared charset fails

    Returns:
        Decoded string
    """
    if not parts:
        return ""

    # Group adjacent same-charset encoded-words to handle split multi-byte chars
    grouped_parts = []
    for content, charset in parts:
        # Normalize charset for comparison
        norm_charset = charset.lower() if charset else None

        if (
            grouped_parts
            and isinstance(content, bytes)
            and isinstance(grouped_parts[-1][0], bytes)
            and grouped_parts[-1][1] == norm_charset
        ):
            # Same charset as previous, concatenate bytes
            grouped_parts[-1] = (grouped_parts[-1][0] + content, norm_charset)
        else:
            grouped_parts.append((content, norm_charset))

    # Decode each grouped part
    decoded_parts = []
    for content, charset in grouped_parts:
        if isinstance(content, bytes):
            # Determine best charset
            declared_enc = CHARSET_MAP.get(charset, charset) if charset else None

            # Handle 'unknown' charset
            if declared_enc and declared_enc.lower() in ("unknown", "unknown-8bit"):
                declared_enc = None

            # Build encoding chain
            encodings_to_try = []
            if declared_enc:
                encodings_to_try.append(declared_enc)
            if fallback_charset and fallback_charset not in encodings_to_try:
                encodings_to_try.append(fallback_charset)
            encodings_to_try.extend(enc for enc in DEFAULT_ENCODING_CHAIN if enc not in encodings_to_try)

            decoded = None
            for enc in encodings_to_try:
                try:
                    decoded = content.decode(enc)
                    if "\ufffd" not in decoded:
                        break
                    decoded = None
                except (LookupError, UnicodeDecodeError):
                    continue

            if decoded is None:
                decoded = content.decode("utf-8", errors="replace")
            decoded_parts.append(decoded)
        else:
            decoded_parts.append(str(content))

    return "".join(decoded_parts)


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
    if "\ufffd" in text:
        return False

    # Count readable vs unreadable characters
    readable = 0
    total = 0

    for char in text[:1000]:  # Sample first 1000 chars
        code = ord(char)
        total += 1

        # Consider readable:
        # - ASCII printable (0x20-0x7E)
        # - Common whitespace (tab, newline, carriage return)
        # - Latin extended (0x80-0xFF) - accented chars
        # - Zero-width characters (U+200B-U+200D, U+FEFF) - used in emails
        # - CJK characters (Chinese, Japanese, Korean)
        #   - CJK Unified Ideographs: U+4E00-U+9FFF
        #   - Hangul Syllables: U+AC00-U+D7AF
        #   - Hangul Jamo: U+1100-U+11FF
        #   - Hiragana: U+3040-U+309F
        #   - Katakana: U+30A0-U+30FF
        # - Common punctuation and symbols

        if (
            0x20 <= code <= 0x7E  # ASCII printable
            or code in (0x09, 0x0A, 0x0D)  # tab, newline, CR
            or 0x80 <= code <= 0xFF  # Latin extended
            or 0x200B <= code <= 0x200D  # Zero-width space/non-joiner/joiner
            or code == 0xFEFF  # BOM / zero-width no-break space
            or code == 0x00AD  # Soft hyphen
            or code == 0x2060  # Word joiner
            or 0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
            or 0xAC00 <= code <= 0xD7AF  # Hangul Syllables
            or 0x1100 <= code <= 0x11FF  # Hangul Jamo
            or 0x3040 <= code <= 0x309F  # Hiragana
            or 0x30A0 <= code <= 0x30FF  # Katakana
            or 0x3000 <= code <= 0x303F  # CJK Punctuation
            or 0xFF00 <= code <= 0xFFEF
        ):  # Fullwidth forms
            readable += 1

    if total == 0:
        return True  # Empty is fine

    return (readable / total) >= min_readable_ratio


def _try_decode(payload: bytes, encoding: str) -> str | None:
    """Try to decode payload with given encoding and validate result.

    Returns decoded text if successful and valid, None otherwise.
    """
    try:
        decoded = payload.decode(encoding)
        if _validate_decoded_text(decoded):
            return decoded
    except (UnicodeDecodeError, LookupError):
        pass
    return None


class EmailParser:
    """Parse .eml files for indexing. Handles malformed emails gracefully."""

    @staticmethod
    def _sanitize_header(value: str) -> str:
        """Remove CR/LF and other problematic chars from header values."""
        if not value:
            return ""
        # Replace CR/LF with space, collapse multiple spaces
        result = value.replace("\r", " ").replace("\n", " ")
        result = WHITESPACE_RE.sub(" ", result)
        return result.strip()

    @staticmethod
    def _extract_raw_header(content: bytes, header_name: str, charset: str = None) -> str:
        """Extract a header directly from raw email bytes.

        This is used when the email library corrupts non-ASCII headers.
        """
        header_prefix = f"{header_name}:".encode("ascii")
        header_prefix_lower = header_prefix.lower()

        lines = content.split(b"\r\n")
        if len(lines) == 1:
            lines = content.split(b"\n")

        value_lines = []
        in_header = False

        for line in lines:
            if line == b"":
                break  # End of headers

            if line.lower().startswith(header_prefix_lower):
                in_header = True
                value_lines.append(line[len(header_prefix) :].strip())
            elif in_header and line.startswith((b" ", b"\t")):
                # Continuation line
                value_lines.append(line.strip())
            elif in_header:
                break  # Next header

        if not value_lines:
            return ""

        raw_value = b" ".join(value_lines)

        # Try to decode with various charsets
        charsets = ["utf-8", "cp949", "euc-kr", "iso-8859-1"]
        if charset:
            # Map well-known charset aliases
            charset_map = {
                "ks_c_5601-1987": "cp949",
                "ks_c_5601": "cp949",
                "ks_c_5601_1987": "cp949",
            }
            mapped = charset_map.get(charset.lower(), charset)
            if mapped not in charsets:
                charsets.insert(0, mapped)
            else:
                charsets.remove(mapped)
                charsets.insert(0, mapped)

        for enc in charsets:
            try:
                decoded = raw_value.decode(enc)
                # Check if it decoded cleanly (no replacement chars)
                if "\ufffd" not in decoded:
                    return decoded
            except (UnicodeDecodeError, LookupError):
                continue

        return raw_value.decode("utf-8", errors="replace")

    @staticmethod
    def _decode_header_value(raw_value, fallback_charset: str = None) -> str:
        """Decode a header value, handling various encodings.

        Args:
            raw_value: The raw header value (str or bytes)
            fallback_charset: Charset to try if standard decoding fails
        """
        from email.header import decode_header

        if not raw_value:
            return ""

        # Check for RFC 2047 encoded strings first - they always need decoding
        if isinstance(raw_value, str) and ("=?" in raw_value and "?=" in raw_value):
            try:
                parts = decode_header(raw_value)
                return _decode_grouped_rfc2047_parts(parts, fallback_charset)
            except Exception:
                pass

        # If already a clean string without encoding issues, return it
        if isinstance(raw_value, str):
            # Check if it looks like it has encoding issues (replacement chars)
            has_issues = "\ufffd" in raw_value or "�" in raw_value
            if not has_issues:
                return raw_value

        # Try direct decoding with common charsets
        if isinstance(raw_value, bytes):
            best_charset = _detect_charset(raw_value, fallback_charset)
            try:
                return raw_value.decode(best_charset)
            except (UnicodeDecodeError, LookupError):
                return raw_value.decode("utf-8", errors="replace")

        # For strings with encoding issues, try re-encoding and decoding
        if isinstance(raw_value, str) and ("\ufffd" in raw_value or "�" in raw_value):
            # Try to recover by encoding to latin-1 and decoding as Korean
            try:
                raw_bytes = raw_value.encode("latin-1", errors="replace")
                best_charset = _detect_charset(raw_bytes, fallback_charset)
                try:
                    decoded = raw_bytes.decode(best_charset)
                    if "\ufffd" not in decoded:
                        return decoded
                except (UnicodeDecodeError, LookupError):
                    pass
            except Exception:
                pass

        return str(raw_value) if raw_value else ""

    @staticmethod
    def _safe_get_header(
        msg,
        header_name: str,
        fallback_charset: str = None,
        raw_content: bytes = None,
    ) -> str:
        """Safely extract a header, handling encoding errors.

        Args:
            msg: Parsed email message
            header_name: Name of header to extract
            fallback_charset: Charset to try for decoding
            raw_content: Raw email bytes for fallback extraction
        """
        try:
            val = msg.get(header_name, "") or ""

            # Convert header objects to string
            val_str = str(val) if val else ""

            # Check for replacement characters
            has_issues = "\ufffd" in val_str

            # If the raw value has encoding corruption, try extracting directly from bytes first
            # This handles cases where the email library corrupts split multi-byte chars
            if raw_content and has_issues:
                raw_decoded = EmailParser._extract_raw_header(raw_content, header_name, fallback_charset)
                if raw_decoded and "\ufffd" not in raw_decoded:
                    # If raw extraction returned RFC 2047 encoded string, decode it
                    if "=?" in raw_decoded and "?=" in raw_decoded:
                        raw_decoded = EmailParser._decode_header_value(raw_decoded, fallback_charset)
                    if "\ufffd" not in raw_decoded:
                        return EmailParser._sanitize_header(raw_decoded)

            decoded = EmailParser._decode_header_value(val, fallback_charset)
            result = EmailParser._sanitize_header(decoded)

            return result
        except Exception:
            # If header parsing fails completely, try raw extraction
            if raw_content:
                try:
                    raw_decoded = EmailParser._extract_raw_header(raw_content, header_name, fallback_charset)
                    if raw_decoded:
                        return EmailParser._sanitize_header(raw_decoded)
                except Exception:
                    pass
            return ""

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Normalize a date string to a standard format.

        Handles:
        - Korean/garbled weekday names
        - Numeric month format (DD M YYYY instead of DD Mon YYYY)
        """
        if not date_str:
            return ""

        from datetime import datetime

        # Try standard parsing first
        try:
            parsed_date = email.utils.parsedate_to_datetime(date_str)
            return parsed_date.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass

        # Remove non-ASCII prefix (Korean/garbled weekday)
        cleaned = NON_ASCII_DATE_PREFIX_RE.sub("", date_str)

        # Try parsing the cleaned version
        try:
            parsed_date = email.utils.parsedate_to_datetime(cleaned)
            return parsed_date.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass

        # Try parsing numeric month format: "DD M YY(YY) H:MM:SS +Z(ZZZ)"
        # Handles: 2 or 4 digit year, 1-4 digit timezone
        match = NUMERIC_DATE_RE.match(cleaned)
        if match:
            day, month, year, hour, minute, second = [int(x) for x in match.groups()[:6]]
            tz_str = match.group(7) or "+0000"

            # Expand 2-digit year to 4-digit
            if year < 100:
                year = 2000 + year if year < 50 else 1900 + year

            # Normalize timezone ("+9" -> "+0900", "+530" -> "+0530", "+0900" stays)
            tz_str = tz_str.lstrip("+")
            if tz_str.startswith("-"):
                tz_sign = -1
                tz_str = tz_str[1:]
            else:
                tz_sign = 1

            # Handle short timezone formats:
            # 1-2 digits = hours only (9 -> 0900, 12 -> 1200)
            # 3-4 digits = HHMM format (530 -> 0530, 0900 -> 0900)
            if len(tz_str) <= 2:
                tz_hours = int(tz_str)
                tz_mins = 0
            else:
                tz_str = tz_str.zfill(4)
                tz_hours = int(tz_str[:2])
                tz_mins = int(tz_str[2:4])

            try:
                from datetime import timedelta, timezone

                tz = timezone(timedelta(hours=tz_sign * tz_hours, minutes=tz_sign * tz_mins))
                dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
                return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
            except Exception:
                pass

        # Return original if all parsing fails
        return date_str

    @staticmethod
    def _extract_date_from_received(msg) -> str:
        """Extract date from Received header when Date header is missing."""
        try:
            # Get the first (most recent) Received header
            received = msg.get("Received", "")
            if not received:
                return ""

            # Received header format: ... ; <date>
            if ";" in received:
                date_part = received.split(";")[-1].strip()
                # Try to parse it
                try:
                    parsed = email.utils.parsedate_to_datetime(date_part)
                    return parsed.strftime("%a, %d %b %Y %H:%M:%S %z")
                except Exception:
                    pass
            return ""
        except Exception:
            return ""

    @staticmethod
    def _safe_get_content(part) -> str:
        """Safely extract content from a message part."""
        try:
            # First, try to get raw bytes and decode with proper charset
            payload = part.get_payload(decode=True)
            if payload and isinstance(payload, bytes):
                # Check header charset first, but validate the result
                header_charset = part.get_content_charset()
                if header_charset:
                    charset = CHARSET_ALIASES.get(header_charset.lower(), header_charset)
                    try:
                        decoded = payload.decode(charset)
                        # Validate result - if it has replacement chars, charset was wrong
                        if _validate_decoded_text(decoded):
                            return EmailParser._strip_embedded_mime_headers(decoded)
                        # Header charset produced garbage - fall through to auto-detection
                    except (LookupError, UnicodeDecodeError):
                        pass

                # For HTML, try to extract charset from meta tag
                content_type = part.get_content_type()
                if content_type == "text/html":
                    try:
                        # Use latin-1 to preserve raw bytes for regex search
                        raw_html = payload.decode("latin-1")
                        match = HTML_CHARSET_RE.search(raw_html[:2048])
                        if match:
                            meta_charset = match.group(1).lower()
                            charset = CHARSET_ALIASES.get(meta_charset, meta_charset)
                            result = _try_decode(payload, charset)
                            if result is not None:
                                return result
                    except Exception:
                        pass

                # No charset specified or it was wrong - try smart detection
                # Sample more bytes since CJK content may not appear until later
                sample_size = min(len(payload), 4000)
                high_bytes = sum(1 for b in payload[:sample_size] if b >= 0x80)

                if high_bytes > 10:
                    # Has significant non-ASCII content - try various encodings
                    # and validate the result makes sense
                    for encoding in ["utf-8", "cp949", "euc-kr", "gb2312", "gbk", "big5", "shift_jis", "euc-jp"]:
                        result = _try_decode(payload, encoding)
                        if result is not None:
                            return EmailParser._strip_embedded_mime_headers(result)

                # Try common encodings with validation
                for encoding in ["utf-8", "iso-8859-1", "cp1252"]:
                    result = _try_decode(payload, encoding)
                    if result is not None:
                        return EmailParser._strip_embedded_mime_headers(result)

                # Last resort - decode with replacement
                return EmailParser._strip_embedded_mime_headers(payload.decode("utf-8", errors="replace"))

            # Fallback to get_content() for non-bytes
            payload = part.get_content()
            if isinstance(payload, str):
                return EmailParser._strip_embedded_mime_headers(payload)
        except Exception:
            pass
        return ""

    @staticmethod
    def _strip_embedded_mime_headers(text: str) -> str:
        """Strip MIME headers accidentally embedded in body text.

        Some email senders (e.g. USPS Informed Delivery) include MIME headers
        like 'Content-Type: text/plain; charset=UTF-8' as part of the body
        content. This strips them from the beginning of the text.
        """
        return re.sub(
            r"^(\s*Content-(?:Type|Transfer-Encoding|Disposition)[^\n]*\n)+\s*", "", text, flags=re.IGNORECASE
        )

    @staticmethod
    def _strip_html(html_content: str) -> str:
        """Strip HTML tags and extract text content.

        Uses lxml to properly parse HTML and extract only visible text,
        correctly handling style/script blocks and malformed HTML.
        """
        try:
            # Parse HTML with lxml (handles malformed HTML well)
            tree = lxml_html.fromstring(html_content)

            # Remove elements that shouldn't contribute text
            for element in tree.xpath("//style | //script | //head | //noscript"):
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)

            # Extract text content
            text = tree.text_content()

            # Normalize whitespace
            return " ".join(text.split())
        except Exception:
            # Fallback to simple regex if lxml fails
            text = STYLE_TAG_RE.sub(" ", html_content)
            text = SCRIPT_TAG_RE.sub(" ", text)
            text = HTML_TAG_RE.sub(" ", text)
            text = html.unescape(text)
            return " ".join(text.split())

    @staticmethod
    def parse_file(filepath: Path = None, content: bytes = None) -> dict:
        """Parse an .eml file and extract searchable content.

        Args:
            filepath: Path to .eml file (reads from disk)
            content: Raw email bytes (avoids disk read if already loaded)

        Returns:
            Dictionary with keys: subject, sender, recipients, date_str, body, attachments
        """
        try:
            raw_content = None
            if content is not None:
                raw_content = content
                msg = email.message_from_bytes(content, policy=email_policy)
            elif filepath is not None:
                with open(filepath, "rb") as f:
                    raw_content = f.read()
                msg = email.message_from_bytes(raw_content, policy=email_policy)
            else:
                raise ValueError("Must provide filepath or content")
        except Exception as e:
            # If even parsing fails, return minimal info
            return {
                "subject": "",
                "sender": "",
                "recipients": "",
                "date_str": "",
                "body": f"[Parse error: {e}]",
                "attachments": "",
            }

        # Extract headers safely
        # Try to get charset from Content-Type for fallback decoding
        content_charset = None
        try:
            content_charset = msg.get_content_charset()
        except Exception:
            pass

        subject = EmailParser._safe_get_header(msg, "Subject", content_charset, raw_content)
        sender = EmailParser._safe_get_header(msg, "From", content_charset, raw_content)

        # Combine all recipient fields
        recipients = []
        for header in ["To", "Cc", "Bcc"]:
            val = EmailParser._safe_get_header(msg, header, content_charset, raw_content)
            if val:
                recipients.append(val)
        recipients_str = ", ".join(recipients)

        date_str = EmailParser._safe_get_header(msg, "Date", raw_content=raw_content)

        # If no Date header, try to extract from Received header
        if not date_str:
            date_str = EmailParser._extract_date_from_received(msg)

        # Try to parse and normalize the date to avoid garbled weekday names
        date_str = EmailParser._normalize_date(date_str)

        # Extract body text
        body_parts = []
        attachments = []

        try:
            if msg.is_multipart():
                for part in msg.walk():
                    try:
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition", ""))

                        # Get attachment filenames
                        if "attachment" in content_disposition:
                            try:
                                # Not get_filename(): it returns None for the
                                # malformed parameters this recovers by hand
                                filename = extract_attachment_filename(part)
                                if filename:
                                    attachments.append(EmailParser._sanitize_header(filename))
                            except Exception:
                                pass

                        # Extract text content
                        if content_type == "text/plain":
                            text = EmailParser._safe_get_content(part)
                            if text:
                                body_parts.append(text)
                        elif content_type == "text/html" and not body_parts:
                            # Only use HTML if no plain text
                            text = EmailParser._safe_get_content(part)
                            if text:
                                # Strip HTML for indexing
                                text = EmailParser._strip_html(text)
                                body_parts.append(text)
                    except Exception:
                        continue
            else:
                text = EmailParser._safe_get_content(msg)
                if text:
                    if msg.get_content_type() == "text/html":
                        text = EmailParser._strip_html(text)
                    body_parts.append(text)
        except Exception:
            pass

        return {
            "subject": subject,
            "sender": sender,
            "recipients": recipients_str,
            "date_str": date_str,
            "body": "\n".join(body_parts),
            "attachments": ", ".join(attachments),
        }


# Joins a folded header back onto one line, per RFC 5322 unfolding
HEADER_UNFOLD_RE = re.compile(rb"\r?\n[ \t]+")

# Extracts RFC 2231 encoded filename parts
# Handles both: filename*=charset''value and filename*0*=charset''value
RFC2231_FILENAME_RE = re.compile(rb"filename\*(\d*)\*?=([^;\r\n]+)", re.IGNORECASE)

# Matches a plain filename= parameter, quoted or bare
SIMPLE_FILENAME_RE = re.compile(rb'filename=[ \t]*(?:"([^"]*)"|([^;\r\n]+))', re.IGNORECASE)


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
        raw_bytes = filename.encode("latin-1")
    except UnicodeEncodeError:
        # Contains chars outside latin-1, not simple mojibake
        return filename

    # Check if it has high bytes (potential CJK encoding)
    if not any(b >= 0x80 for b in raw_bytes):
        return filename  # All ASCII, no mojibake

    # Try to decode as various CJK encodings
    for encoding in ["euc-kr", "cp949", "utf-8", "gb2312", "gbk", "shift_jis"]:
        try:
            decoded = raw_bytes.decode(encoding)
            # Validate that result looks like readable text
            # (contains Hangul, CJK, or mostly printable ASCII)
            hangul_cjk = sum(
                1
                for c in decoded
                if "\uac00" <= c <= "\ud7af"  # Hangul
                or "\u4e00" <= c <= "\u9fff"  # CJK
                or "\u3040" <= c <= "\u30ff"
            )  # Japanese
            if hangul_cjk > 0:
                return decoded
        except (UnicodeDecodeError, LookupError):
            continue

    return filename  # Return original if nothing worked


def _raw_content_disposition(part) -> bytes:
    """Return the part's Content-Disposition exactly as it arrived.

    Not as_bytes(): when a parameter is malformed enough that the policy
    rejects it, the generator rebuilds the header from the parsed value and
    the original text is gone — and whether it does that turns on incidental
    details like whether the header was folded. raw_items() hands back the
    unparsed value every time, and never walks the payload.
    """
    values = [str(value) for name, value in part.raw_items() if name.lower() == "content-disposition"]
    # Header values arrive as str with any non-ASCII bytes carried in
    # surrogates; surrogateescape puts the original bytes back.
    raw = "\n".join(values).encode("utf-8", "surrogateescape")
    return HEADER_UNFOLD_RE.sub(b" ", raw)


def extract_attachment_filename(part) -> str:
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

    try:
        raw_part = _raw_content_disposition(part)

        # FIRST: Check for RFC2231 + MIME hybrid encoding (filename*N="=?UTF-8?B?...?=")
        # Some email clients incorrectly combine RFC2231 continuation with MIME encoded-words
        # This must be checked first because the quoted values break standard RFC2231 parsing
        rfc2231_mime_re = re.compile(rb'filename\*\d+="([^"]+)"', re.IGNORECASE)
        mime_matches = rfc2231_mime_re.findall(raw_part)
        if mime_matches:
            # Join all parts and clean up
            combined_value = b"".join(mime_matches).replace(b"\r\n ", b" ").replace(b"\r\n", b"").replace(b"\n ", b" ")
            combined_str = combined_value.decode("ascii", errors="ignore")

            # Check if it contains MIME encoded-words
            if "=?" in combined_str and "?=" in combined_str:
                # Extract MIME encoded-words
                mime_word_re = re.compile(r"=\?([^?]+)\?([BbQq])\?([^?]+)\?=")
                mime_parts = mime_word_re.findall(combined_str)
                if mime_parts:
                    decoded_parts = []
                    for charset_name, encoding, encoded_text in mime_parts:
                        try:
                            if encoding.upper() == "B":
                                # Base64 - fix padding
                                padding = 4 - (len(encoded_text) % 4) if len(encoded_text) % 4 else 0
                                encoded_text += "=" * padding
                                decoded_bytes = base64.b64decode(encoded_text)
                            else:
                                # Quoted-printable
                                import quopri

                                decoded_bytes = quopri.decodestring(encoded_text.encode("ascii"))

                            # Decode with charset
                            cs = charset_name.lower()
                            if cs == "unknown":
                                cs = "utf-8"
                            decoded_parts.append(decoded_bytes.decode(cs, errors="replace"))
                        except Exception:
                            continue

                    if decoded_parts:
                        result = "".join(decoded_parts)
                        if "\ufffd" not in result:
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
                charset = charset_bytes.decode("ascii", errors="ignore").lower()
                # unknown-8bit is often EUC-KR for Korean emails
                if charset in ("unknown-8bit", ""):
                    charset = "euc-kr"
            else:
                # Continuation parts don't have charset prefix
                encoded_value = value
                charset = "euc-kr"

            # URL-decode the value
            try:
                decoded_bytes = unquote_to_bytes(encoded_value.decode("ascii"))
                filename_parts.append((part_num, decoded_bytes, charset))
            except Exception:
                continue

        if filename_parts:
            # Sort by part number and combine
            filename_parts.sort(key=lambda x: x[0])
            combined = b"".join(p[1] for p in filename_parts)
            charset = filename_parts[0][2]  # Use charset from first part

            # Try the specified charset first, then fallbacks
            for enc in [charset, "euc-kr", "cp949", "utf-8", "gb2312", "shift_jis"]:
                try:
                    decoded = combined.decode(enc)
                    # Validate it has readable CJK content
                    if any(
                        "\uac00" <= c <= "\ud7af"  # Hangul
                        or "\u4e00" <= c <= "\u9fff"  # CJK
                        or "\u3040" <= c <= "\u30ff"  # Japanese
                        for c in decoded
                    ):
                        return decoded
                    # If no CJK but decoded without errors, use it
                    if enc in ["utf-8", charset]:
                        return decoded
                except (UnicodeDecodeError, LookupError):
                    continue

        # THIRD: Read the plain filename= parameter out of the raw header.
        # Two things land here: raw non-ASCII bytes with no encoding declared
        # at all, and RFC 2047 encoded-words used as the parameter value. The
        # latter is illegal but common in the wild, and an unquoted one is
        # rejected wholesale by the strict policy — get_filename() returns
        # None for it, so this is the only place it can be recovered.
        simple_match = SIMPLE_FILENAME_RE.search(raw_part)
        if simple_match:
            raw_filename = (simple_match.group(1) or simple_match.group(2)).strip()

            if b"=?" in raw_filename and b"?=" in raw_filename:
                decoded = EmailParser._decode_header_value(raw_filename.decode("ascii", errors="replace"))
                if decoded and "\ufffd" not in decoded:
                    return decoded

            # Check if it has high bytes (non-ASCII)
            if any(b >= 0x80 for b in raw_filename):
                # Try various CJK encodings
                for enc in ["euc-kr", "cp949", "utf-8", "gb2312", "gbk", "shift_jis", "cp1251", "koi8-r"]:
                    try:
                        decoded = raw_filename.decode(enc)
                        # Validate - should have CJK/Cyrillic chars
                        if any(
                            "\uac00" <= c <= "\ud7af"  # Hangul
                            or "\u4e00" <= c <= "\u9fff"  # CJK
                            or "\u0400" <= c <= "\u04ff"  # Cyrillic
                            or "\u3040" <= c <= "\u30ff"  # Japanese
                            for c in decoded
                        ):
                            return decoded
                    except (UnicodeDecodeError, LookupError):
                        continue

    except Exception:
        pass

    # Fall back to standard get_filename() with mojibake fix
    filename = part.get_filename()
    if filename:
        # MIME-encoded filenames first: Python doesn't decode RFC 2047
        # encoded-words in parameter values, and an encoded-word says what its
        # charset is — the mojibake fix below only guesses.
        if "=?" in filename:
            decoded = EmailParser._decode_header_value(filename)
            if decoded and "\ufffd" not in decoded:
                return decoded
        # Check for replacement characters (corruption)
        if "\ufffd" not in filename:
            fixed = _fix_mojibake_filename(filename)
            if fixed:
                return fixed
        return filename

    return "attachment"
