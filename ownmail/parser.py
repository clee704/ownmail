"""Email parser for extracting searchable content from .eml files."""

import email
import email.utils
import re
from email.policy import default as email_policy
from pathlib import Path


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
    def _safe_get_content(part) -> str:
        """Safely extract content from a message part."""
        try:
            payload = part.get_content()
            if isinstance(payload, str):
                return payload
            elif isinstance(payload, bytes):
                # Try common encodings
                for encoding in ['utf-8', 'euc-kr', 'cp949', 'iso-8859-1']:
                    try:
                        return payload.decode(encoding)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return payload.decode('utf-8', errors='replace')
        except Exception:
            # Last resort: try get_payload
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode('utf-8', errors='replace')
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

        date_str = EmailParser._safe_get_header(msg, "Date")
        # Try to parse and normalize the date to avoid garbled weekday names
        try:
            parsed_date = email.utils.parsedate_to_datetime(date_str)
            date_str = parsed_date.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass  # Keep original if parsing fails

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
