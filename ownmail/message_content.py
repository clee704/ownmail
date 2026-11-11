"""MIME body and sanitized HTML helpers shared by OwnMail readers."""

import base64
import codecs
import email.header
import re
from email.policy import default as email_policy
from html.parser import HTMLParser
from urllib.parse import quote

from ownmail.parser import _decode_body, extract_attachment_filename, is_attachment

# Shown in place of a blocked <img> so it keeps its authored size instead of
# collapsing to its alt text
BLOCKED_IMAGE_PLACEHOLDER = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"

# A URL that leaves the archive's host: an http(s) scheme or a scheme-relative //
REMOTE_URL_RE = re.compile(r"https?:|//", re.IGNORECASE)

# Characters a browser trims from both ends of a URL: controls and space
URL_TRIMMED_CHARACTERS = "".join(chr(code) for code in range(0x21))

# One candidate URL of a srcset. A URL may contain commas, as data: URIs do,
# so a candidate ends at whitespace.
SRCSET_URL_RE = re.compile(r"(?:^|,)[\s,]*([^\s,]\S*)")

# Attributes that load a URL, by element. Any element but <body> may also have
# a background; the reader drops body attributes other than style. The
# sanitizer keeps <link> only for trusted font stylesheets.
URL_ATTRIBUTES = {
    "audio": ("src",),
    "img": ("src", "srcset"),
    "input": ("src",),
    "link": ("href",),
    "source": ("src", "srcset"),
    "track": ("src",),
    "video": ("poster", "src"),
}

# The argument of a CSS url()
CSS_URL_RE = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))""", re.IGNORECASE)

# An @import may name its stylesheet as a bare string
CSS_IMPORT_STRING_RE = re.compile(r"""@import\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)

# The arguments of an image-set(), which also takes images as bare strings.
# Strings elsewhere, such as in selectors and content, load nothing.
CSS_IMAGE_SET_RE = re.compile(r"""image-set\(((?:[^()"']|"[^"]*"|'[^']*'|\([^()]*\))*)\)""", re.IGNORECASE)
CSS_STRING_RE = re.compile(r""""([^"]*)"|'([^']*)'""")

# CSS comments, which load nothing
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# Consume each complete attribute, including non-URL attributes whose values
# can contain image markup. The sanitizer always double-quotes values.
IMAGE_ATTRIBUTE_RE = re.compile(r'(\s+)([^\s/>=]+)(?:="([^"]*)")?')

# Content types served inline, so the browser renders them instead of saving
# them. Everything absent from this set is downloaded.
#
# An inline response shares the archive's origin, and the type it claims comes
# from the email, which anyone who can send mail controls. So this lists only
# formats the browser renders without scripting, and the response is sent with
# the type named here rather than the one the message declared. image/svg+xml
# is left out on purpose: SVG can carry <script>.
INLINE_SAFE_TYPES = frozenset(
    {
        "application/pdf",
        "image/avif",
        "image/bmp",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/plain",
        "audio/mpeg",
        "audio/mp4",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "video/mp4",
        "video/ogg",
        "video/webm",
    }
)

# A charset name may only look like this before it goes in a response header
CHARSET_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")


# Writes an attached message with the header folding it arrived with, and
# the CRLF line endings RFC 5322 requires
ATTACHED_MESSAGE_POLICY = email_policy.clone(refold_source="none", linesep="\r\n")


class _MessageBodyParser(HTMLParser):
    """Extract content from sanitized HTML without interpreting attribute text as tags."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.content: list[str] = []
        self.styles: list[str] = []
        self.body_attributes: dict[str, str] = {}
        self._in_head = False
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self._in_head = True
        elif tag == "body":
            self._in_head = False
            # Whitespace outside the body must not enter preformatted messages.
            self.content.clear()
            style = dict(attrs).get("style")
            if style is not None:
                self.body_attributes = {"style": style}
        elif tag in {"style", "link"}:
            # DOMPurify has already scoped CSS and filtered font stylesheets.
            self.styles.append(self.get_starttag_text())
            self._in_style = tag == "style"
        elif tag != "html":
            # Keep serialized start tags so HTML5 void elements stay intact.
            self.handle_data(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "head":
            self._in_head = False
        elif tag not in {"html", "body"}:
            self.handle_data(f"</{tag}>")
            if tag == "style":
                self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.styles[-1] += data
        elif not self._in_head:
            self.content.append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def _extract_body_content(html: str) -> tuple[str, dict[str, str]]:
    """Extract sanitized message content and body styling for direct embedding.

    Strips <html>, <head>, <body> wrappers and extracts just the content
    that goes inside the email container div. Preserves styles and font links
    in their original order, plus inline styling for the message container.

    Args:
        html: Sanitized HTML document or fragment

    Returns:
        Body content and the container's style attribute
    """
    if not html:
        return html, {}

    parser = _MessageBodyParser()
    parser.feed(html)
    parser.close()
    content = "".join(parser.content)
    if parser.styles:
        content = "\n".join(parser.styles) + "\n" + content
    return content, parser.body_attributes


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
    if hasattr(value, "__str__") and not isinstance(value, str):
        value = str(value)
    if not isinstance(value, str):
        return ""

    # Check if it looks like MIME-encoded
    if "=?" not in value or "?=" not in value:
        return value

    try:
        decoded_parts = email.header.decode_header(value)
        result = []
        for data, charset in decoded_parts:
            if isinstance(data, bytes):
                # Try the declared charset first, then common fallbacks
                charsets_to_try = []
                if charset and charset.upper() != "UNKNOWN":
                    charsets_to_try.append(charset)
                # Add common fallbacks: CJK, Russian, Western European
                charsets_to_try.extend(
                    [
                        "utf-8",
                        "euc-kr",
                        "cp949",
                        "iso-2022-kr",  # Korean
                        "cp1251",
                        "koi8-r",  # Russian
                        "gb2312",
                        "gbk",  # Chinese
                        "shift_jis",
                        "euc-jp",  # Japanese
                        "iso-8859-1",
                        "cp1252",  # Western
                    ]
                )
                decoded = None
                for cs in charsets_to_try:
                    if cs:
                        try:
                            decoded = data.decode(cs)
                            # Validate it doesn't have too many replacement chars
                            if "\ufffd" not in decoded:
                                break
                        except (UnicodeDecodeError, LookupError):
                            continue
                if decoded is None:
                    decoded = data.decode("utf-8", errors="replace")
                result.append(decoded)
            else:
                result.append(data)
        return "".join(result)
    except Exception:
        # If standard decoding fails (malformed base64, etc.), try manual approach
        # Some emails have split multi-byte chars across encoded-words
        try:
            # Find all encoded-words and try to decode them together
            pattern = r"=\?([^?]+)\?([BbQq])\?([^?]*)\?="
            matches = list(re.finditer(pattern, value))

            if not matches:
                return value

            # Collect all base64 parts for same charset
            base64_parts = []
            charset_used = None
            for m in matches:
                charset, encoding, encoded_text = m.groups()
                if encoding.upper() == "B":
                    base64_parts.append(encoded_text)
                    charset_used = charset

            if base64_parts and charset_used:
                # Combine and decode
                combined = "".join(base64_parts)
                # Add padding if needed
                padding = 4 - (len(combined) % 4) if len(combined) % 4 else 0
                combined += "=" * padding
                try:
                    decoded_bytes = base64.b64decode(combined)
                    return decoded_bytes.decode(charset_used, errors="replace")
                except Exception:
                    pass

            return value  # Return original if all else fails
        except Exception:
            return str(value) if value else ""


def _decode_text_body(payload: bytes, header_charset: str | None) -> str:
    """Decode plain text with the charset selection used for indexing."""
    return _decode_body(payload, header_charset)


def _decode_html_body(payload: bytes, header_charset: str | None) -> str:
    """Decode HTML with MIME/meta declarations and the indexing fallback."""
    return _decode_body(payload, header_charset, is_html=True)


def _is_remote_url(url: str) -> bool:
    """Whether a browser would fetch the URL from outside the archive's host."""
    # Browsers drop tabs and newlines from a URL and read a backslash as a slash.
    url = re.sub(r"[\t\n\r]", "", url).strip(URL_TRIMMED_CHARACTERS).replace("\\", "/")
    return REMOTE_URL_RE.match(url) is not None


def _css_has_remote_urls(css: str) -> bool:
    """Whether CSS loads anything from outside the archive's host."""
    css = CSS_COMMENT_RE.sub("", css)
    urls = [match[match.lastindex] for match in CSS_URL_RE.finditer(css)]
    urls.extend(match[match.lastindex] for match in CSS_IMPORT_STRING_RE.finditer(css))
    for image_set in CSS_IMAGE_SET_RE.finditer(css):
        urls.extend(match[match.lastindex] for match in CSS_STRING_RE.finditer(image_set[1]))
    return any(_is_remote_url(url) for url in urls)


def _has_remote_content(html: str) -> bool:
    """Whether sanitized message HTML loads anything from outside the archive's host.

    This decides whether the reader offers to load or block remote content. The
    CSP does the blocking, so a reference this misses stays blocked.
    """
    from lxml import etree
    from lxml import html as lxml_html

    for element in lxml_html.document_fromstring(html).iter(etree.Element):
        urls = [] if element.tag == "body" else [element.get("background", "")]
        for name in URL_ATTRIBUTES.get(element.tag, ()):
            value = element.get(name, "")
            urls.extend(SRCSET_URL_RE.findall(value) if name == "srcset" else [value])
        css = (element.text or "") if element.tag == "style" else element.get("style", "")
        if any(_is_remote_url(url) for url in urls) or _css_has_remote_urls(css):
            return True
    return False


class _ImageSourceParser(HTMLParser):
    """Locate source edits on real image tags while preserving serialized HTML."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=False)
        self.line_offsets = [0] + [match.end() for match in re.finditer("\n", html)]
        self.replacements: list[tuple[int, int, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag not in {"img", "source"}:
            return
        from html import unescape

        def replace(attribute):
            name, value = attribute[2].lower(), unescape(attribute[3] or "")
            if name == "srcset":
                return "" if any(_is_remote_url(url) for url in SRCSET_URL_RE.findall(value)) else attribute[0]
            if name == "src" and tag == "img" and _is_remote_url(value):
                return f'{attribute[1]}src="{BLOCKED_IMAGE_PLACEHOLDER}"'
            return attribute[0]

        original = self.get_starttag_text()
        rewritten = IMAGE_ATTRIBUTE_RE.sub(replace, original)
        if rewritten != original:
            line, column = self.getpos()
            start = self.line_offsets[line - 1] + column
            self.replacements.append((start, start + len(original), rewritten))


def _hide_blocked_images(html: str) -> str:
    """Replace remote <img> sources with a placeholder of the authored size.

    The CSP already stops the requests; this only keeps the layout. Dropping a
    remote srcset makes the browser fall back to the placeholder.
    """
    parser = _ImageSourceParser(html)
    parser.feed(html)
    parser.close()
    parts = []
    previous = 0
    for start, end, replacement in parser.replacements:
        parts.extend((html[previous:start], replacement))
        previous = end
    parts.append(html[previous:])
    return "".join(parts)


def _message_body(msg) -> dict:
    """Extract the reader's MIME body, CID images and attachment descriptions."""
    # Extract body
    body = ""
    body_html = None
    body_parts = []  # Collect text parts from top-level only
    embedded_messages = []  # Collect embedded message/rfc822 for digests
    attachments = [_attachment_entry(part) for part in _attachment_parts(msg)]
    cid_images = {}  # Content-ID -> data URI mapping

    if msg.is_multipart():
        # Parts of embedded message/rfc822 parts (like digest entries),
        # which shouldn't be concatenated into the main body
        embedded_parts = set()

        for part in msg.walk():
            content_type = part.get_content_type()

            # Handle embedded message/rfc822 parts (digest entries)
            if content_type == "message/rfc822":
                embedded_parts.update(part.walk())
                # Extract embedded message for digest display
                try:
                    embedded = part.get_payload(0)
                    if embedded:
                        emb_from = decode_header(embedded.get("From", ""))
                        emb_subject = decode_header(embedded.get("Subject", ""))
                        emb_date = embedded.get("Date", "")
                        emb_to = decode_header(embedded.get("To", ""))
                        emb_reply_to = decode_header(embedded.get("Reply-To", ""))

                        # Get body of embedded message
                        emb_body = ""
                        for sub in embedded.walk():
                            if sub.get_content_type() == "text/plain" and not emb_body and not is_attachment(sub):
                                payload = sub.get_payload(decode=True)
                                if payload:
                                    emb_body = _decode_text_body(payload, sub.get_content_charset())

                        embedded_messages.append(
                            {
                                "from": emb_from,
                                "subject": emb_subject,
                                "date": emb_date,
                                "to": emb_to,
                                "reply_to": emb_reply_to,
                                "body": emb_body,
                            }
                        )
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
            if part in embedded_parts:
                continue

            # Named inline text remains part of the displayed message.
            if part.get_content_disposition() == "attachment":
                continue
            if content_type == "text/plain":
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
    # (we already block remote content for privacy)
    if body_html:
        body = ""

    return {"body": body, "body_html": body_html, "attachments": attachments, "cid_images": cid_images}


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _inline_content_type(part) -> str | None:
    """Return the type to serve this part inline as, or None to download it.

    The returned type always comes from INLINE_SAFE_TYPES rather than from the
    message, so a mislabelled part cannot talk the browser into rendering
    something else.
    """
    content_type = (part.get_content_type() or "").lower()
    if content_type not in INLINE_SAFE_TYPES:
        return None

    if content_type == "text/plain":
        # Keep the declared charset so CJK text reads correctly. It has to look
        # like a charset name before it can go in a header, and codecs has to
        # recognize it; anything else is served as UTF-8. Note the declared
        # spelling is what ships — codecs' canonical name uses underscores
        # ("euc_kr"), which is not a charset any browser knows.
        charset = part.get_content_charset() or ""
        if CHARSET_NAME_RE.fullmatch(charset):
            try:
                codecs.lookup(charset)
            except LookupError:
                charset = ""
        else:
            charset = ""
        return f"text/plain; charset={charset or 'utf-8'}"

    return content_type


def _attachment_parts(msg) -> list:
    """Return the attachment parts in the order detail links number them."""
    return [part for part in msg.walk() if is_attachment(part)]


def _attachment_bytes(part) -> bytes:
    """Return the file content of an attachment part."""
    if part.get_content_type() == "message/rfc822":
        # An attached message has no decoded payload; its file is the
        # message it holds
        return part.get_payload(0).as_bytes(policy=ATTACHED_MESSAGE_POLICY)
    return part.get_payload(decode=True) or b""


def _attachment_entry(part) -> dict:
    """Describe one attachment part for the detail template."""
    filename = extract_attachment_filename(part)
    content_type = (part.get_content_type() or "").lower()
    payload = _attachment_bytes(part)

    # The extension is what people recognize; fall back to the MIME subtype
    # for the attachments that arrive without one.
    _, _, extension = filename.rpartition(".")
    kind = extension.upper() if extension and len(extension) <= 5 else content_type.rpartition("/")[2].upper()

    return {
        "filename": filename,
        # Percent-encoded for the tail of the attachment URL, so a preview tab
        # is titled with the name rather than the part's index.
        "url_name": quote(filename, safe=""),
        "size": _format_size(len(payload) if payload else 0),
        "kind": kind,
        "previewable": _inline_content_type(part) is not None,
    }
