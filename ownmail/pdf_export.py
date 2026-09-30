"""Optional, offline PDF export using already installed Playwright/Chromium."""

import email
import html
import os
import shutil
import signal
import subprocess
from email.policy import default as email_policy
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile

from flask import Flask

from ownmail.export import _export_rows, _publish_file, _read_source
from ownmail.parser import EmailParser
from ownmail.sanitizer import HtmlSanitizer
from ownmail.web import INLINE_SAFE_TYPES, _extract_body_content, _hide_blocked_images, _message_body, decode_header

_RENDERER = Path(__file__).with_name("pdf_renderer.js")
_RENDER_SECONDS = 60


def _run_renderer(node: str, *args: str, timeout: float) -> None:
    """Run the optional renderer, bounding failure and cancellation cleanup."""
    # A descendant may inherit diagnostics after its leader exits. A regular
    # temporary file never makes completion depend on those descriptors closing.
    with TemporaryFile() as diagnostics:
        process = subprocess.Popen(
            [node, str(_RENDERER), *args],
            stdout=subprocess.DEVNULL,
            stderr=diagnostics,
            start_new_session=os.name == "posix",
        )
        try:
            process.wait(timeout=timeout)
        except BaseException as error:
            if os.name == "posix":

                def signal_group(sig):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        pass

                # Playwright's first SIGTERM closes its browser gracefully; a
                # second forces its own detached browser group closed. Always
                # kill remaining members of our group, even if the leader exited.
                signal_group(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    signal_group(signal.SIGTERM)
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
                finally:
                    signal_group(signal.SIGKILL)
            else:
                # Windows has no POSIX process groups. taskkill targets only the
                # still-running renderer PID and its descendant tree.
                if process.poll() is None:
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                    process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            if isinstance(error, subprocess.TimeoutExpired):
                raise OSError("PDF renderer timed out") from error
            raise
        if process.returncode:
            diagnostics.seek(0, os.SEEK_END)
            diagnostics.seek(max(0, diagnostics.tell() - 4000))
            reason = (
                diagnostics.read().decode("utf-8", errors="replace").strip()[-1000:] or f"exit {process.returncode}"
            )
            raise OSError(f"PDF renderer unavailable or failed: {reason}")


def _document(raw: bytes, sanitizer: HtmlSanitizer, template) -> str:
    """Build the printable reader presentation without app routes or controls."""
    headers = EmailParser.parse_file(content=raw)
    message = email.message_from_bytes(raw, policy=email_policy)
    content = _message_body(message)
    body_html = content["body_html"]
    body_attributes = {}
    needs_padding = True
    if body_html:
        if not sanitizer.available:
            sanitizer.start(install=False)
            if not sanitizer.available:
                raise OSError("PDF HTML sanitizer unavailable; existing dependencies are required")
        for cid, uri in content["cid_images"].items():
            if uri.partition(";")[0].removeprefix("data:") in INLINE_SAFE_TYPES:
                body_html = body_html.replace(f"cid:{cid}", uri)
        original = body_html
        body_html, needs_padding, _ = sanitizer.sanitize(body_html)
        # The sidecar's documented failure result is escaped input, including
        # a failed request followed by a successful worker restart.
        if body_html == html.escape(original):
            raise OSError("HTML sanitization failed; no PDF export was written")
        body_html, body_attributes = _extract_body_content(_hide_blocked_images(body_html))
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
    )


def export_pdf(archive, output: Path, query: str = "") -> tuple[int, list[tuple[str, str]]]:
    """Export matching archived messages as numbered PDFs in a new directory.

    Requires existing Node, Playwright, Chromium and sanitizer installations;
    never installs or downloads them. Source-read failures are skipped. Fatal
    rendering/output failures or Ctrl-C remove this invocation's incomplete output.
    """
    rows = _export_rows(archive, output, query)
    node = shutil.which("node")
    if not node:
        raise OSError("PDF renderer unavailable: Node.js is not installed")
    _run_renderer(node, "--check", timeout=15)
    root = archive.archive_dir.resolve()
    template = Flask(__name__).jinja_env.get_template("pdf.html")
    exported = 0
    skipped = []
    sanitizer = HtmlSanitizer()
    try:
        with TemporaryDirectory(prefix=".ownmail-export-", dir=output.parent) as directory:
            temporary = Path(directory)
            for email_id, filename, *_ in rows:
                try:
                    raw = _read_source(root, filename)
                except (OSError, RuntimeError) as error:
                    skipped.append((email_id, str(error)))
                    continue
                document = _document(raw, sanitizer, template)
                exported += 1
                (temporary / f"{exported:06d}.html").write_text(document, encoding="utf-8")
            if exported:
                _run_renderer(node, str(temporary), str(exported), timeout=_RENDER_SECONDS * (exported + 1))
            files = [temporary / f"{index:06d}.pdf" for index in range(1, exported + 1)]
            for path in files:
                with path.open("rb") as source:
                    if source.read(5) != b"%PDF-":
                        raise OSError("PDF renderer returned an invalid document")
            # mkdir is exclusive, including against an output appearing mid-export.
            output.mkdir()
            published = []
            try:
                for path in files:
                    destination = output / path.name
                    _publish_file(path, destination)
                    published.append(destination)
            except BaseException:
                for path in published:
                    path.unlink()
                # Do not recursively remove unrelated files another writer added.
                try:
                    output.rmdir()
                except OSError:
                    pass
                raise
    finally:
        sanitizer.stop()
    return exported, skipped
