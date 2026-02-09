"""Email parser for extracting searchable content from .eml files."""

import email
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
    def _safe_get_header(msg, header_name: str) -> str:
        """Safely extract a header, handling encoding errors."""
        try:
            val = msg.get(header_name, "") or ""
            return EmailParser._sanitize_header(str(val))
        except Exception:
            # If header parsing fails completely, try raw access
            try:
                val = msg.get(header_name, defects=[]) or ""
                return EmailParser._sanitize_header(str(val))
            except Exception:
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
            if content is not None:
                msg = email.message_from_bytes(content, policy=email_policy)
            elif filepath is not None:
                with open(filepath, "rb") as f:
                    msg = email.message_from_binary_file(f, policy=email_policy)
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
        subject = EmailParser._safe_get_header(msg, "Subject")
        sender = EmailParser._safe_get_header(msg, "From")

        # Combine all recipient fields
        recipients = []
        for header in ["To", "Cc", "Bcc"]:
            val = EmailParser._safe_get_header(msg, header)
            if val:
                recipients.append(val)
        recipients_str = ", ".join(recipients)

        date_str = EmailParser._safe_get_header(msg, "Date")

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
        }
