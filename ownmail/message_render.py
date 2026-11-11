"""Render sanitized MIME content for an embedding viewer or OwnMail."""

import email
import html
from email.policy import default as email_policy
from typing import TypedDict

from ownmail.message_content import (
    INLINE_SAFE_TYPES,
    _extract_body_content,
    _has_remote_content,
    _hide_blocked_images,
    _message_body,
    decode_header,
)
from ownmail.parser import EmailParser
from ownmail.sanitizer import HtmlSanitizer

_STANDALONE_CSP = "default-src 'none'; img-src {images}; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"


class RenderedMessage(TypedDict):
    """Message content and metadata for a caller's own document template."""

    subject: str
    sender: str
    recipients: str
    date: str
    body: str
    body_html: str | None
    body_attributes: dict[str, str]
    needs_padding: bool
    attachments: list[dict]
    has_remote_content: bool


def _render_message_content(
    raw: bytes,
    sanitizer: HtmlSanitizer,
    *,
    images_blocked: bool,
    start_sanitizer: bool,
    detect_remote_content: bool,
) -> RenderedMessage:
    headers = EmailParser.parse_file(content=raw)
    message = email.message_from_bytes(raw, policy=email_policy)
    content = _message_body(message)
    body_html = content["body_html"]
    body_attributes = {}
    needs_padding = True
    has_remote_content = False
    if body_html:
        # Print uses the reader's running sanitizer. Offline callers own theirs.
        if not sanitizer.available and start_sanitizer:
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
        has_remote_content = detect_remote_content and bool(body_html) and _has_remote_content(body_html)
        if images_blocked:
            body_html = _hide_blocked_images(body_html)
        body_html, body_attributes = _extract_body_content(body_html)
    return RenderedMessage(
        subject=decode_header(headers["subject"]) or "(No subject)",
        sender=decode_header(headers["sender"]),
        recipients=headers["recipients"],
        date=headers["date_str"],
        body=content["body"],
        body_html=body_html,
        body_attributes=body_attributes,
        needs_padding=needs_padding,
        attachments=content["attachments"],
        has_remote_content=has_remote_content,
    )


def render_eml_content(raw: bytes, *, load_images: bool = False) -> RenderedMessage:
    """Render MIME bytes for a caller that owns the preview page.

    Escape the metadata and plain text when inserting them into HTML. Mount
    sanitized body_html in #ownmail-email-content for the sender's scoped
    styles. The caller controls network requests with its response CSP.
    """
    if not raw.strip():
        raise ValueError("message is empty")
    sanitizer = HtmlSanitizer()
    try:
        return _render_message_content(
            raw,
            sanitizer,
            images_blocked=not load_images,
            start_sanitizer=True,
            detect_remote_content=True,
        )
    finally:
        sanitizer.stop()


def render_message_document(
    raw: bytes,
    sanitizer: HtmlSanitizer,
    template,
    *,
    images_blocked: bool = True,
    print_page: bool = False,
    standalone: bool = False,
    image_toggle_url: str | None = None,
) -> str:
    """Build the message document shared by Print, PDF export and standalone render."""
    content = _render_message_content(
        raw,
        sanitizer,
        images_blocked=images_blocked,
        start_sanitizer=not print_page,
        detect_remote_content=standalone and bool(image_toggle_url),
    )
    image_sources = "data:" if images_blocked else "data: https: http:"
    return template.render(
        **content,
        images_blocked=images_blocked,
        print_page=print_page,
        standalone_csp=_STANDALONE_CSP.format(images=image_sources) if standalone else None,
        image_toggle_url=image_toggle_url if content["has_remote_content"] else None,
    )


def render_eml(raw: bytes, *, load_images: bool = False, image_toggle_url: str | None = None) -> str:
    """Render raw MIME bytes with an optional image policy and local viewer control."""
    from flask import Flask

    if not raw.strip():
        raise ValueError("message is empty")
    if image_toggle_url is not None and not image_toggle_url.startswith("?"):
        raise ValueError("image toggle URL must be a query on the current document")
    template = Flask(__name__).jinja_env.get_template("pdf.html")
    sanitizer = HtmlSanitizer()
    try:
        return render_message_document(
            raw,
            sanitizer,
            template,
            standalone=True,
            images_blocked=not load_images,
            image_toggle_url=image_toggle_url,
        )
    finally:
        sanitizer.stop()
