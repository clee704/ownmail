"""Synthetic body charset regressions shared by display and indexing."""

import email
import json
from email.policy import default
from unittest.mock import MagicMock

import pytest

from ownmail.parser import EmailParser
from ownmail.web import _decode_html_body, _decode_text_body, create_app
from tests import test_email_contrast
from tests.conftest import mock_archive_db

contrast_browser = test_email_contrast.contrast_browser

RECOVERY_CASES = [
    pytest.param("Café �", "utf-8", "utf-8", "", id="literal-replacement-character"),
    pytest.param("Café", "utf-8", "iso-8859-1", "", id="utf8-declared-latin1"),
    pytest.param("한글", "euc-kr", None, "", id="short-undeclared-korean"),
    pytest.param(
        "안녕하세요 반갑습니다",
        "euc-kr",
        None,
        "<html><head><!--" + "a" * 4200 + "--></head><body>",
        id="korean-after-ascii-preamble",
    ),
]

LEGACY_CASES = [
    pytest.param("Café déjà vu", "iso-8859-1", "iso-8859-1", id="declared-latin1"),
    pytest.param("Café", "iso-8859-1", "latin1", id="latin1-alias"),
    pytest.param("Café “update”", "cp1252", "windows-1252", id="declared-windows1252"),
    pytest.param("한글", "euc-kr", "euc-kr", id="declared-korean"),
    # These bytes are also valid UTF-8; declarations other than Latin-1 win.
    pytest.param("Ã©", "cp1252", "windows-1252", id="ambiguous-windows1252"),
]


def body_message(text, encoding, declared, content_type, prefix=""):
    body = text
    if content_type == "text/html":
        body = prefix + f"<p>{text}</p>" + ("</body></html>" if prefix else "")
    elif prefix:
        body = "a" * 4200 + "\n" + text
    declaration = f"; charset={declared}" if declared else ""
    raw = f"Content-Type: {content_type}{declaration}\r\n\r\n".encode() + body.encode(encoding)
    return raw, body


@pytest.mark.parametrize("text,encoding,declared,prefix", RECOVERY_CASES)
@pytest.mark.parametrize("content_type", ["text/plain", "text/html"])
def test_body_recovery_in_display_and_indexing(text, encoding, declared, prefix, content_type):
    raw, body = body_message(text, encoding, declared, content_type, prefix)
    part = email.message_from_bytes(raw, policy=default)
    decoder = _decode_html_body if content_type == "text/html" else _decode_text_body

    assert decoder(part.get_payload(decode=True), declared) == body
    assert EmailParser._safe_get_content(part) == body
    assert EmailParser.parse_file(content=raw)["body"] == (text if content_type == "text/html" else body)


@pytest.mark.parametrize("text,encoding,declared", LEGACY_CASES)
@pytest.mark.parametrize("content_type", ["text/plain", "text/html"])
def test_correct_legacy_declarations_are_preserved(text, encoding, declared, content_type):
    raw, body = body_message(text, encoding, declared, content_type)
    part = email.message_from_bytes(raw, policy=default)
    decoder = _decode_html_body if content_type == "text/html" else _decode_text_body

    assert decoder(part.get_payload(decode=True), declared) == body
    assert EmailParser._safe_get_content(part) == body
    assert EmailParser.parse_file(content=raw)["body"] == text


@pytest.mark.parametrize("encoding", ["utf-8", "iso-8859-1"])
def test_latin1_html_meta_uses_the_same_recovery_rule(encoding):
    body = '<meta charset="latin1"><p>Café</p>'
    raw = b"Content-Type: text/html\r\n\r\n" + body.encode(encoding)
    part = email.message_from_bytes(raw, policy=default)

    assert _decode_html_body(part.get_payload(decode=True), None) == body
    assert EmailParser._safe_get_content(part) == body
    assert EmailParser.parse_file(content=raw)["body"] == "Café"


@pytest.mark.parametrize("text,encoding,declared,prefix", RECOVERY_CASES)
def test_recovered_html_renders_in_browser(tmp_path, contrast_browser, text, encoding, declared, prefix):
    raw, _ = body_message(text, encoding, declared, "text/html", prefix)
    (tmp_path / "synthetic.eml").write_bytes(raw)
    archive = MagicMock()
    archive.archive_dir = tmp_path
    archive.db = mock_archive_db()
    archive.db.get_labels_for_email.return_value = []
    archive.db.get_email_by_id.return_value = (
        "synthetic",
        "synthetic.eml",
        "2024-01-01",
        "hash",
        "sender@example.com",
        None,
    )
    app = create_app(archive)
    with app.test_client() as client:
        response = client.get("/email/synthetic")
    assert response.status_code == 200
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        f"assert.equal(await page.locator('#ownmail-email-content').innerText(), {json.dumps(text)});",
        rendered_page=response.data.decode(),
    )
