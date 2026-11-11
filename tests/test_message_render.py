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
    assert not output.err
    assert file.read_bytes() == original
    config.assert_not_called()


def test_render_standalone_html_keeps_receipt_table_and_blocks_remote_resources(real_sanitizer, monkeypatch):
    message = _message(
        "<table><tr><td>Purchased item</td><td>USD 9.99</td></tr></table>"
        '<img src="https://example.invalid/pixel.gif" onerror="window.bad=1">'
        "<script>window.bad=2</script>",
        "html",
    )
    monkeypatch.setattr(message_render, "HtmlSanitizer", lambda: real_sanitizer)
    rendered = message_render.render_eml(message.as_bytes())
    assert "<td>Purchased item</td>" in rendered and "<td>USD 9.99</td>" in rendered
    assert 'http-equiv="Content-Security-Policy"' in rendered
    assert "img-src data:" in rendered and "default-src &#39;none&#39;" in rendered
    assert 'src="https://example.invalid/pixel.gif"' not in rendered
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


def test_render_rejects_empty_message():
    with pytest.raises(ValueError, match="message is empty"):
        message_render.render_eml(b"\r\n")
