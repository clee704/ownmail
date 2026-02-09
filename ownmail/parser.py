"""Email parser for extracting searchable content from .eml files."""

import email
import email.utils
import re
from email.policy import default as email_policy
from pathlib import Path

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
        # - ASCII printable (0x20-0x7E)
        # - Common whitespace (tab, newline, carriage return)
        # - Latin extended (0x80-0xFF) - accented chars
        # - CJK characters (Chinese, Japanese, Korean)
        #   - CJK Unified Ideographs: U+4E00-U+9FFF
        #   - Hangul Syllables: U+AC00-U+D7AF
        #   - Hangul Jamo: U+1100-U+11FF
        #   - Hiragana: U+3040-U+309F
        #   - Katakana: U+30A0-U+30FF
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
        result = re.sub(r'\s+', ' ', result)
        return result.strip()

    @staticmethod
    def _extract_raw_header(content: bytes, header_name: str, charset: str = None) -> str:
        """Extract a header directly from raw email bytes.

        This is used when the email library corrupts non-ASCII headers.
        """
        header_prefix = f"{header_name}:".encode('ascii')
        header_prefix_lower = header_prefix.lower()

        lines = content.split(b'\r\n')
        if len(lines) == 1:
            lines = content.split(b'\n')

        value_lines = []
        in_header = False

        for line in lines:
            if line == b'':
                break  # End of headers

            if line.lower().startswith(header_prefix_lower):
                in_header = True
                value_lines.append(line[len(header_prefix):].strip())
            elif in_header and line.startswith((b' ', b'\t')):
                # Continuation line
                value_lines.append(line.strip())
            elif in_header:
                break  # Next header

        if not value_lines:
            return ""

        raw_value = b' '.join(value_lines)

        # Try to decode with various charsets
        charsets = ['utf-8', 'cp949', 'euc-kr', 'iso-8859-1']
        if charset:
            # Map charset aliases and prioritize
            charset_map = {
                'ks_c_5601-1987': 'cp949',
                'ks_c_5601': 'cp949',
                'ks_c_5601_1987': 'cp949',
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
                if '\ufffd' not in decoded:
                    return decoded
            except (UnicodeDecodeError, LookupError):
                continue

        return raw_value.decode('utf-8', errors='replace')

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

        # If already a clean string without encoding issues, return it
        if isinstance(raw_value, str):
            # Check if it looks like it has encoding issues (replacement chars)
            if '\ufffd' not in raw_value and '�' not in raw_value:
                return raw_value

        try:
            # Try RFC 2047 decoding first
            if isinstance(raw_value, str) and ('=?' in raw_value and '?=' in raw_value):
                parts = decode_header(raw_value)
                decoded_parts = []
                for content, charset in parts:
                    if isinstance(content, bytes):
                        # Map charset aliases
                        charset_map = {
                            'ks_c_5601-1987': 'cp949',
                            'ks_c_5601': 'cp949',
                            'euc-kr': 'cp949',
                        }
                        enc = charset_map.get(charset.lower(), charset) if charset else 'utf-8'
                        try:
                            decoded_parts.append(content.decode(enc, errors='replace'))
                        except (LookupError, UnicodeDecodeError):
                            decoded_parts.append(content.decode('utf-8', errors='replace'))
                    else:
                        decoded_parts.append(str(content))
                return ''.join(decoded_parts)
        except Exception:
            pass

        # Try direct decoding with common charsets
        if isinstance(raw_value, bytes):
            for enc in ['utf-8', 'cp949', 'euc-kr', 'iso-8859-1']:
                try:
                    return raw_value.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return raw_value.decode('utf-8', errors='replace')

        # For strings with encoding issues, try re-encoding and decoding
        if isinstance(raw_value, str) and ('\ufffd' in raw_value or '�' in raw_value):
            # Try to recover by encoding to latin-1 and decoding as Korean
            try:
                raw_bytes = raw_value.encode('latin-1', errors='replace')
                for enc in ['cp949', 'euc-kr', 'utf-8']:
                    try:
                        decoded = raw_bytes.decode(enc)
                        if '\ufffd' not in decoded:
                            return decoded
                    except (UnicodeDecodeError, LookupError):
                        continue
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

            # Check for replacement characters BEFORE any processing
            # If the raw value has encoding corruption, extract directly from bytes
            if raw_content and isinstance(val, str) and '\ufffd' in val:
                raw_decoded = EmailParser._extract_raw_header(
                    raw_content, header_name, fallback_charset
                )
                if raw_decoded and '\ufffd' not in raw_decoded:
                    return EmailParser._sanitize_header(raw_decoded)

            decoded = EmailParser._decode_header_value(val, fallback_charset)
            result = EmailParser._sanitize_header(decoded)

            return result
        except Exception:
            # If header parsing fails completely, try raw extraction
            if raw_content:
                try:
                    raw_decoded = EmailParser._extract_raw_header(
                        raw_content, header_name, fallback_charset
                    )
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
        cleaned = re.sub(r'^[^\x00-\x7F]+,?\s*', '', date_str)

        # Try parsing the cleaned version
        try:
            parsed_date = email.utils.parsedate_to_datetime(cleaned)
            return parsed_date.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass

        # Try parsing numeric month format: "DD M YY(YY) H:MM:SS +Z(ZZZ)"
        # Handles: 2 or 4 digit year, 1-4 digit timezone
        match = re.match(
            r'(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([+-]?\d{1,4})?',
            cleaned
        )
        if match:
            day, month, year, hour, minute, second = [int(x) for x in match.groups()[:6]]
            tz_str = match.group(7) or "+0000"

            # Expand 2-digit year to 4-digit
            if year < 100:
                year = 2000 + year if year < 50 else 1900 + year

            # Normalize timezone ("+9" -> "+0900", "+530" -> "+0530", "+0900" stays)
            tz_str = tz_str.lstrip('+')
            if tz_str.startswith('-'):
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
                from datetime import timezone, timedelta
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
                # Check header charset first
                header_charset = part.get_content_charset()
                if header_charset:
                    charset = CHARSET_ALIASES.get(header_charset.lower(), header_charset)
                    try:
                        return payload.decode(charset, errors='replace')
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
                            try:
                                return payload.decode(charset, errors='replace')
                            except (LookupError, UnicodeDecodeError):
                                pass
                    except Exception:
                        pass

                # No charset specified - try smart detection
                # Check if payload has high bytes (non-ASCII) suggesting CJK encoding
                high_bytes = sum(1 for b in payload[:500] if b >= 0x80)

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

                # Last resort - decode with replacement
                return payload.decode('utf-8', errors='replace')

            # Fallback to get_content() for non-bytes
            payload = part.get_content()
            if isinstance(payload, str):
                return payload
        except Exception:
            pass
        return ""

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
                                filename = part.get_filename()
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
                                # Strip HTML tags for indexing
                                text = re.sub(r'<[^>]+>', ' ', text)
                                text = re.sub(r'\s+', ' ', text)
                                body_parts.append(text)
                    except Exception:
                        continue
            else:
                text = EmailParser._safe_get_content(msg)
                if text:
                    if msg.get_content_type() == "text/html":
                        text = re.sub(r'<[^>]+>', ' ', text)
                        text = re.sub(r'\s+', ' ', text)
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
            "labels": EmailParser._safe_get_header(msg, "X-Gmail-Labels"),
        }
