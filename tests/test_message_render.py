import io
import sys
from email import policy
from email.message import EmailMessage
from unittest.mock import Mock

import pytest

from ownmail import cli, message_render
from tests import test_pdf_export

real_sanitizer = test_pdf_export.real_sanitizer


def _message(body, subtype="plain"):
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = "Sender <sender@example.invalid>"
    message["Subject"] = "Purchase <Example>"
    message.set_content(body, subtype=subtype)
    return message


@pytest.mark.parametrize("from_stdin", [True, False])
def test_render_command_uses_only_the_selected_bytes(tmp_path, monkeypatch, capsysbinary, from_stdin):
    original = _message("Paid <USD> 9.99").as_bytes()
    file = tmp_path / "receipt.eml"
    file.write_bytes(original)
    args = ["ownmail", "render"]
    if from_stdin:
        args.extend(["--load-images", "--image-toggle-url", "?images=block"])
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(original)))
    else:
        args.append(str(file))
    monkeypatch.setattr(sys, "argv", args)
    config = Mock(side_effect=AssertionError("read archive configuration"))
    monkeypatch.setattr(cli, "load_config", config)

    cli.main()

    output = capsysbinary.readouterr()
    assert b"Purchase &lt;Example&gt;" in output.out
    assert b"Paid &lt;USD&gt; 9.99" in output.out
    assert b"Content-Security-Policy" in output.out
    image_policy = b"img-src data: https: http:;" if from_stdin else b"img-src data:;"
    assert image_policy in output.out
    assert b"Block images" not in output.out
    assert not output.err
    assert file.read_bytes() == original
    config.assert_not_called()


@pytest.mark.parametrize("load_images", [False, True])
def test_render_standalone_html_applies_the_viewers_image_choice(real_sanitizer, monkeypatch, load_images):
    message = _message(
        "<table><tr><td>Purchased item</td><td>USD 9.99</td></tr></table>"
        '<img src="https://example.invalid/pixel.gif" onerror="window.bad=1" referrerpolicy="unsafe-url">'
        "<script>window.bad=2</script>",
        "html",
    )
    monkeypatch.setattr(message_render, "HtmlSanitizer", lambda: real_sanitizer)
    next_mode = "block" if load_images else "load"
    rendered = message_render.render_eml(
        message.as_bytes(),
        load_images=load_images,
        image_toggle_url=f"?id=example&images={next_mode}",
    )
    assert "<td>Purchased item</td>" in rendered and "<td>USD 9.99</td>" in rendered
    assert 'http-equiv="Content-Security-Policy"' in rendered
    assert "default-src &#39;none&#39;" in rendered
    assert "style-src &#39;unsafe-inline&#39;" in rendered
    image_policy = "img-src data: https: http:;" if load_images else "img-src data:;"
    assert image_policy in rendered
    assert ('src="https://example.invalid/pixel.gif"' in rendered) is load_images
    assert f'href="?id=example&amp;images={next_mode}"' in rendered
    assert ("Block images" if load_images else "Load images") in rendered
    assert "referrerpolicy=" not in rendered
    assert "window.bad" not in rendered and "message-print.js" not in rendered


def test_render_command_reports_sanitizer_failure(tmp_path, monkeypatch, capsysbinary):
    file = tmp_path / "receipt.eml"
    file.write_bytes(_message("<p>Receipt</p>", "html").as_bytes())
    sanitizer = Mock(available=False)
    monkeypatch.setattr(message_render, "HtmlSanitizer", lambda: sanitizer)
    monkeypatch.setattr(sys, "argv", ["ownmail", "render", str(file)])

    with pytest.raises(SystemExit) as caught:
        cli.main()

    assert caught.value.code == 1
    output = capsysbinary.readouterr()
    assert not output.out
    assert b"HTML sanitizer unavailable" in output.err
    sanitizer.start.assert_called_once_with(install=False)
    sanitizer.stop.assert_called_once()


def test_render_eml_content_returns_plain_message_without_document():
    message = _message("Paid <USD> 9.99")
    result = message_render.render_eml_content(message.as_bytes())
    assert result["subject"] == "Purchase <Example>"
    assert "Paid <USD> 9.99" in result["body"]
    assert result["body_html"] is None
    assert not result["has_remote_content"]


@pytest.mark.parametrize("load_images", [False, True])
def test_render_eml_content_returns_only_scoped_email_html(real_sanitizer, monkeypatch, load_images):
    message = _message(
        "<html><head><style>p { color: green }</style></head>"
        '<body style="color: black"><p>Receipt</p><img src="https://example.invalid/remote.png">'
        "<script>window.bad=1</script></body></html>",
        "html",
    )
    monkeypatch.setattr(message_render, "HtmlSanitizer", lambda: real_sanitizer)
    result = message_render.render_eml_content(message.as_bytes(), load_images=load_images)
    assert result["has_remote_content"]
    assert "color: black" in result["body_attributes"]["style"]
    assert "#ownmail-email-content p" in result["body_html"]
    assert ("https://example.invalid/remote.png" in result["body_html"]) is load_images
    assert "window.bad" not in result["body_html"]
    assert "<html" not in result["body_html"]


def test_render_rejects_empty_message():
    with pytest.raises(ValueError, match="message is empty"):
        message_render.render_eml(b"\r\n")


def test_render_rejects_nonlocal_image_control():
    with pytest.raises(ValueError, match="must be a query"):
        message_render.render_eml(
            _message("Receipt").as_bytes(),
            image_toggle_url="https://example.invalid/?images=load",
        )
