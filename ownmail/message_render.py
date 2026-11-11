"""Render one original MIME message with ownmail's printable reader."""

import email
import html
from email.policy import default as email_policy

from flask import Flask

from ownmail.parser import EmailParser
from ownmail.sanitizer import HtmlSanitizer
from ownmail.web import INLINE_SAFE_TYPES, _extract_body_content, _hide_blocked_images, _message_body, decode_header

_OFFLINE_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"


def render_message_document(
    raw: bytes,
    sanitizer: HtmlSanitizer,
    template,
    *,
    images_blocked: bool = True,
    print_page: bool = False,
    standalone: bool = False,
) -> str:
    """Build the message document shared by Print, PDF export and standalone render."""
    headers = EmailParser.parse_file(content=raw)
    message = email.message_from_bytes(raw, policy=email_policy)
    content = _message_body(message)
    body_html = content["body_html"]
    body_attributes = {}
    needs_padding = True
    if body_html:
        # Print uses the reader's running sanitizer. Offline callers own theirs.
        if not sanitizer.available and not print_page:
            sanitizer.start(install=False)
        if not sanitizer.available:
            raise OSError("HTML sanitizer unavailable; existing dependencies are required")
        for cid, uri in content["cid_images"].items():
            if uri.partition(";")[0].removeprefix("data:") in INLINE_SAFE_TYPES:
                body_html = body_html.replace(f"cid:{cid}", uri)
        original = body_html
        body_html, needs_padding, _ = sanitizer.sanitize(body_html)
        # The sidecar returns escaped input on failure, even if it restarts.
        if body_html == html.escape(original):
            raise OSError("HTML sanitization failed; no document was rendered")
        if images_blocked:
            body_html = _hide_blocked_images(body_html)
        body_html, body_attributes = _extract_body_content(body_html)
    return template.render(
        subject=decode_header(headers["subject"]) or "(No subject)",
        sender=decode_header(headers["sender"]),
        recipients=headers["recipients"],
        date=headers["date_str"],
        body=content["body"],
        body_html=body_html,
        body_attributes=body_attributes,
        needs_padding=needs_padding,
        attachments=content["attachments"],
        images_blocked=images_blocked,
        print_page=print_page,
        standalone_csp=_OFFLINE_CSP if standalone else None,
    )


def render_eml(raw: bytes) -> str:
    """Render raw MIME bytes offline without an archive or a running web app."""
    if not raw.strip():
        raise ValueError("message is empty")
    template = Flask(__name__).jinja_env.get_template("pdf.html")
    sanitizer = HtmlSanitizer()
    try:
        return render_message_document(raw, sanitizer, template, standalone=True)
    finally:
        sanitizer.stop()
