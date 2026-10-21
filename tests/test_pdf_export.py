"""Optional local PDF export: source fidelity, isolation and failure cleanup."""

import html
import os
import re
import sys
from email.message import EmailMessage
from pathlib import Path

import pytest
from flask import Flask
from lxml import html as lxml_html

from ownmail import pdf_export
from ownmail.sanitizer import HtmlSanitizer
from tests import test_export

archive = test_export.archive
store = test_export.store
mixed_archive = test_export.mixed_archive


@pytest.fixture
def fake_renderer(monkeypatch):
    """Replace only Chromium; retain real query, MIME and publication behavior."""
    documents = []

    def run(node, *args, timeout):
        if args == ("--check",):
            return
        directory, count = Path(args[0]), int(args[1])
        for index in range(1, count + 1):
            document = directory / f"{index:06d}.html"
            documents.append(document.read_text())
            document.with_suffix(".pdf").write_bytes(b"%PDF-1.7\nsynthetic renderer placeholder\n%%EOF\n")

    monkeypatch.setattr(pdf_export.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(pdf_export, "_run_renderer", run)
    return documents


def test_pdf_selection_has_no_limit_and_preserves_source(archive, store, fake_renderer, tmp_path):
    for index in range(53):
        store(f"keep-{index:02}", date=f"2024-01-{index % 28 + 1:02}T12:00:00+00:00")
    store("exclude")
    before = test_export.snapshot(archive)
    output = tmp_path / "pdfs"
    count, skipped = pdf_export.export_pdf(archive, output, "subject:keep")
    assert (count, skipped) == (53, [])
    assert sorted(path.name for path in output.iterdir()) == [f"{index:06d}.pdf" for index in range(1, 54)]
    assert len(fake_renderer) == 53
    assert "keep-00" in fake_renderer[0]
    assert all("exclude" not in text for text in fake_renderer)
    assert test_export.snapshot(archive) == before
    test_export.assert_no_temporary_exports(output)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("is:archived", {"Message owned", "Message dual"}),
        ("is:active", {"Message dual"}),
        ("-has:attachment -is:active", {"Message owned"}),
    ],
)
def test_pdf_selection_reuses_ownership_semantics(mixed_archive, fake_renderer, tmp_path, query, expected):
    archive, _ = mixed_archive
    before = test_export.snapshot(archive)
    count, skipped = pdf_export.export_pdf(archive, tmp_path / "pdfs", query)
    assert count == len(expected)
    assert not skipped
    assert {lxml_html.fromstring(document).xpath("//h1")[0].text_content() for document in fake_renderer} == expected
    assert test_export.snapshot(archive) == before


def test_empty_selection_makes_empty_directory_without_starting_browser(archive, fake_renderer, tmp_path):
    output = tmp_path / "empty"
    assert pdf_export.export_pdf(archive, output) == (0, [])
    assert list(output.iterdir()) == []
    assert fake_renderer == []


def test_source_failures_skip_only_bad_messages(archive, store, fake_renderer, tmp_path):
    store("good")
    missing = store("missing")
    missing.unlink()
    unsafe = store("unsafe")
    unsafe.unlink()
    outside = tmp_path / "outside.eml"
    outside.write_text("Subject: Do not read\n\nPRIVATE CANARY")
    unsafe.symlink_to(outside)
    output = tmp_path / "pdfs"
    count, skipped = pdf_export.export_pdf(archive, output)
    assert count == 1
    assert {identifier for identifier, _ in skipped} == {"missing", "unsafe"}
    assert len(list(output.iterdir())) == 1
    assert "PRIVATE CANARY" not in fake_renderer[0]
    assert outside.read_text().endswith("PRIVATE CANARY")


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_pdf_refuses_existing_destinations(archive, fake_renderer, tmp_path, kind):
    output = tmp_path / "existing"
    if kind == "directory":
        output.mkdir()
    elif kind == "symlink":
        output.symlink_to(tmp_path / "missing")
    else:
        output.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        pdf_export.export_pdf(archive, output)
    assert os.path.lexists(output)
    assert fake_renderer == []


def test_invalid_query_does_not_probe_renderer(archive, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_export, "_run_renderer", lambda *_a, **_k: pytest.fail("Invalid query reached renderer"))
    with pytest.raises(ValueError, match="Invalid search"):
        pdf_export.export_pdf(archive, tmp_path / "pdfs", "after:not-a-date")
    assert not (tmp_path / "pdfs").exists()


def test_missing_node_fails_before_output(archive, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_export.shutil, "which", lambda _: None)
    with pytest.raises(OSError, match="Node.js"):
        pdf_export.export_pdf(archive, tmp_path / "pdfs")
    assert list(tmp_path.iterdir()) == [archive.archive_dir]


@pytest.mark.parametrize("phase", ["check", "render", "publish"])
@pytest.mark.parametrize("failure", [OSError("synthetic failure"), KeyboardInterrupt()])
def test_failure_or_interrupt_cleans_for_retry(archive, store, fake_renderer, tmp_path, monkeypatch, phase, failure):
    store("one")
    store("two")
    output = tmp_path / "retry"
    original = pdf_export._run_renderer
    with monkeypatch.context() as patch:
        if phase == "publish":
            real_publish = pdf_export._publish_file

            def publish(source, destination):
                if destination.name == "000002.pdf":
                    raise failure
                real_publish(source, destination)

            patch.setattr(pdf_export, "_publish_file", publish)
        else:

            def run(node, *args, **kwargs):
                if (args == ("--check",)) == (phase == "check"):
                    raise failure
                original(node, *args, **kwargs)

            patch.setattr(pdf_export, "_run_renderer", run)
        with pytest.raises(type(failure)):
            pdf_export.export_pdf(archive, output)
    assert not output.exists()
    test_export.assert_no_temporary_exports(output)
    assert pdf_export.export_pdf(archive, output) == (2, [])


def test_directory_created_during_render_is_preserved(archive, store, fake_renderer, tmp_path, monkeypatch):
    store("one")
    output = tmp_path / "raced"
    original = pdf_export._run_renderer

    def render(*args, **kwargs):
        original(*args, **kwargs)
        if args[1] != "--check":
            output.mkdir()
            (output / "other.txt").write_text("another writer")

    monkeypatch.setattr(pdf_export, "_run_renderer", render)
    with pytest.raises(FileExistsError):
        pdf_export.export_pdf(archive, output)
    assert (output / "other.txt").read_text() == "another writer"
    test_export.assert_no_temporary_exports(output)


def test_invalid_renderer_output_never_publishes(archive, store, fake_renderer, tmp_path, monkeypatch):
    store("one")
    original = pdf_export._run_renderer

    def render(node, *args, **kwargs):
        original(node, *args, **kwargs)
        if args != ("--check",):
            (Path(args[0]) / "000001.pdf").write_bytes(b"not a PDF")

    monkeypatch.setattr(pdf_export, "_run_renderer", render)
    with pytest.raises(OSError, match="invalid document"):
        pdf_export.export_pdf(archive, tmp_path / "pdfs")
    assert not (tmp_path / "pdfs").exists()


@pytest.mark.parametrize("available", [False, True])
def test_failed_html_sanitization_is_not_presented_as_success(
    archive, store, fake_renderer, tmp_path, monkeypatch, available
):
    message = EmailMessage()
    message.set_content("<p>Keep readable</p>", subtype="html")
    store("html", raw=message.as_bytes())

    class BrokenSanitizer:
        def __init__(self):
            self.available = available

        def start(self, *, install):
            assert install is False

        def sanitize(self, raw):
            return html.escape(raw), True, False

        def stop(self):
            pass

    monkeypatch.setattr(pdf_export, "HtmlSanitizer", BrokenSanitizer)
    with pytest.raises(OSError, match="sanitiz"):
        pdf_export.export_pdf(archive, tmp_path / "pdfs")
    assert not (tmp_path / "pdfs").exists()
    assert fake_renderer == []


def test_plain_pdf_needs_no_sanitizer_process(archive, store, fake_renderer, tmp_path, monkeypatch):
    store("plain")
    monkeypatch.setattr(HtmlSanitizer, "start", lambda *_a, **_k: pytest.fail("Plain text does not need HTML sidecar"))
    assert pdf_export.export_pdf(archive, tmp_path / "pdfs") == (1, [])


@pytest.fixture
def real_sanitizer():
    sanitizer = HtmlSanitizer()
    sanitizer.start(install=False)
    if not sanitizer.available:
        pytest.skip("Existing sanitizer dependencies are unavailable")
    try:
        yield sanitizer
    finally:
        sanitizer.stop()


def test_printable_message_keeps_headers_html_cid_and_separates_attachments(real_sanitizer):
    message = EmailMessage()
    message["Subject"] = "영수증 café <script>not executable</script>"
    message["From"] = "Sender <sender@example.test>"
    message["To"] = "reader@example.test"
    message["Cc"] = "copy@example.test"
    message.set_content("Plain alternative")
    message.add_alternative(
        '<style>p {color: red}</style><p>HTML body</p><img src="cid:logo">'
        '<script>fetch("https://example.test")</script><img src="https://example.test/pixel">',
        subtype="html",
    )
    message.get_payload()[-1].add_related(b"synthetic image", maintype="image", subtype="png", cid="<logo>")
    message.add_attachment("ATTACHMENT BODY MUST NOT BECOME MESSAGE TEXT", subtype="plain", filename="첨부.txt")
    template = Flask(pdf_export.__name__).jinja_env.get_template("pdf.html")
    document = pdf_export._document(message.as_bytes(), real_sanitizer, template)
    dom = lxml_html.fromstring(document)
    assert not dom.xpath("//script")
    assert "영수증 café <script>not executable</script>" in dom.text_content()
    assert "HTML body" in dom.text_content()
    assert "Plain alternative" not in dom.text_content()
    assert "ATTACHMENT BODY MUST NOT BECOME MESSAGE TEXT" not in dom.text_content()
    assert "첨부.txt" in dom.text_content()
    assert "copy@example.test" in dom.text_content()
    assert "attachment files are not embedded" in dom.text_content()
    assert dom.xpath('//img[starts-with(@src,"data:image/png;base64,")]')
    assert "#ownmail-email-content p" in document
    assert not dom.xpath('//img[starts-with(@src,"https://")]')


def test_renderer_nonzero_error_is_clear(tmp_path, monkeypatch):
    runner = tmp_path / "fail.py"
    runner.write_text("import sys\nsys.stderr.write('synthetic renderer missing')\nsys.exit(2)\n")
    monkeypatch.setattr(pdf_export, "_RENDERER", runner)
    with pytest.raises(OSError, match="synthetic renderer missing"):
        pdf_export._run_renderer(sys.executable, "--check", timeout=5)


@pytest.mark.parametrize(
    "failure",
    [
        "[pid=123][err] FATAL:zygote_host_impl_linux.cc: No usable sandbox!",
        "browserType.launch: Chromium sandboxing failed!",
        "Failed to move to new namespace: PID namespaces supported, Network namespace supported, but failed: errno = Operation not permitted",
        "Running as root without --no-sandbox is not supported. See https://crbug.com/638180.",
    ],
)
def test_renderer_sandbox_failure_survives_long_crash_log(tmp_path, monkeypatch, failure):
    runner = tmp_path / "fail.py"
    diagnostics = failure + "\n" + "[err] register dump\n" * 1000
    runner.write_text(f"import sys\nsys.stderr.write({diagnostics!r})\nsys.exit(1)\n")
    monkeypatch.setattr(pdf_export, "_RENDERER", runner)

    with pytest.raises(OSError, match="could not start the Chromium sandbox") as error:
        pdf_export._run_renderer(sys.executable, timeout=5)

    message = str(error.value)
    assert "non-root user" in message
    assert "unprivileged user namespaces" in message
    assert "AppArmor profile for the Chromium executable" in message
    assert "README: PDF export on Linux" in message
    assert "sandbox remains enabled" in message
    assert "register dump" not in message


def test_renderer_timeout_terminates_its_process(tmp_path, monkeypatch):
    runner = tmp_path / "hang.py"
    marker = tmp_path / "pid"
    runner.write_text(
        "import os,time\nfrom pathlib import Path\nPath(__file__).with_name('pid').write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    monkeypatch.setattr(pdf_export, "_RENDERER", runner)
    with pytest.raises(OSError, match="timed out"):
        pdf_export._run_renderer(sys.executable, timeout=0.5)
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)


@pytest.fixture
def pdf_browser_node():
    import shutil

    node = shutil.which("node")
    try:
        if not node:
            raise OSError("Node.js is unavailable")
        pdf_export._run_renderer(node, "--check", timeout=15)
    except OSError as error:
        if os.environ.get("OWNMAIL_REQUIRE_BROWSER_TESTS") == "1":
            pytest.fail(str(error))
        pytest.skip(str(error))
    return node


def test_actual_pdfs_are_readable_and_block_untrusted_resources(archive, store, tmp_path, pdf_browser_node):
    import base64
    import shutil
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    requests = []

    class Tracker(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"REMOTE CANARY")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Tracker)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    secret = tmp_path / "local-secret.html"
    secret.write_text("LOCAL FILE CANARY MUST NEVER APPEAR")
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII="
    )
    plain = EmailMessage()
    plain["Subject"] = "Plain 영수증 café"
    plain["From"] = "Sender <sender@example.test>"
    plain["To"] = "reader@example.test"
    plain.set_content("Plain readable München.\nLast plain line.")
    store("plain", raw=plain.as_bytes(), date="2024-01-01T00:00:00+00:00")
    rich = EmailMessage()
    rich["Subject"] = "HTML 영수증 café"
    rich["From"] = "Sender <sender@example.test>"
    rich["To"] = "reader@example.test"
    rich.add_alternative(
        f'<meta http-equiv="refresh" content="0;url={origin}/navigate">'
        f'<script>fetch("{origin}/script");navigator.serviceWorker.register("{origin}/worker");'
        'document.body.textContent="SCRIPT RAN";</script>'
        f'<iframe src="{secret.as_uri()}"></iframe><object data="{secret.as_uri()}"></object>'
        f'<style>@import "{origin}/import";@font-face{{font-family:Tracker;src:url({origin}/font)}}'
        f"p{{background-image:url({origin}/background);font-family:Tracker,sans-serif}}</style>"
        f'<img src="{origin}/image" onerror="location.href=\'{origin}/event\'">'
        f'<img src="{secret.as_uri()}"><img src="cid:logo" width="32" height="32">'
        # Word's page setup, a margin box and fixed content would otherwise change or repeat on printed pages.
        "<style>@page WordSection1 {size:8.5in 11in; margin:1in} div.WordSection1 {page:WordSection1}"
        '@page {@top-center {content:"MARGIN CANARY"}}</style>'
        '<div class="WordSection1"><div style="position:fixed;top:0;right:0">FIXED CANARY</div>'
        '<table style="width:1100px"><tr><td>LEFT EDGE</td><td style="text-align:right">RIGHT EDGE</td></tr></table>'
        + "".join(f"<p>Readable HTML München 영수증 paragraph {index}</p>" for index in range(100))
        + "<p>LAST HTML PARAGRAPH</p></div>",
        subtype="html",
    )
    rich.get_payload()[-1].add_related(image, maintype="image", subtype="png", cid="<logo>")
    rich.add_attachment("ATTACHMENT PRIVATE CONTENT", subtype="plain", filename="첨부.txt")
    store("rich", raw=rich.as_bytes(), date="2024-01-02T00:00:00+00:00")
    before = test_export.snapshot(archive)
    output = tmp_path / "actual-pdfs"
    try:
        assert pdf_export.export_pdf(archive, output) == (2, [])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert requests == []
    assert test_export.snapshot(archive) == before
    pdfs = sorted(output.glob("*.pdf"))
    assert len(pdfs) == 2
    for document in pdfs:
        data = document.read_bytes()
        assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
        assert b"/Type /Page" in data and b"/Font" in data
    assert b"/Subtype /Image" in pdfs[1].read_bytes()
    # Every page of both documents has export's one page size.
    boxes = [re.findall(rb"/MediaBox \[[^]]*\]", path.read_bytes()) for path in pdfs]
    assert len(boxes[1]) > 1 and len(set(boxes[0] + boxes[1])) == 1
    # Optional independent local observer; no PDF package/product dependency.
    extractor = shutil.which("pdftotext")
    if extractor:
        texts = [
            " ".join(
                subprocess.run(
                    [extractor, "-layout", str(path), "-"], capture_output=True, text=True, check=True, timeout=15
                ).stdout.split()
            )
            for path in pdfs
        ]
        assert "Plain 영수증 café" in texts[0]
        assert "Plain readable München." in texts[0] and "Last plain line." in texts[0]
        for value in [
            "HTML 영수증 café",
            "sender@example.test",
            "reader@example.test",
            "LEFT EDGE",
            "RIGHT EDGE",
            "LAST HTML PARAGRAPH",
            "첨부.txt",
            "not embedded",
        ]:
            assert value in texts[1]
        for value in [
            "SCRIPT RAN",
            "REMOTE CANARY",
            "LOCAL FILE CANARY",
            "ATTACHMENT PRIVATE CONTENT",
            "MARGIN CANARY",
        ]:
            assert value not in texts[1]
        assert texts[1].count("FIXED CANARY") == 1
        first_page = subprocess.run(
            [extractor, "-f", "1", "-l", "1", str(pdfs[1]), "-"], capture_output=True, text=True, check=True, timeout=15
        ).stdout
        first_page = " ".join(first_page.split())
        assert "HTML 영수증 café" in first_page and "paragraph 0" in first_page
        assert [int(value) for value in re.findall(r"Readable HTML München 영수증 paragraph (\d+)", texts[1])] == list(
            range(100)
        )
    test_export.assert_no_temporary_exports(output)


@pytest.mark.parametrize(
    "slow_close",
    [False, pytest.param(True, marks=pytest.mark.skipif(os.name != "posix", reason="POSIX shell wrapper"))],
)
def test_actual_renderer_does_not_execute_unsanitized_page_scripts(tmp_path, pdf_browser_node, monkeypatch, slow_close):
    import shutil
    import subprocess
    import time

    if slow_close:
        # The browser outlives its close deadline after writing the PDF, as under
        # heavy load: the wrapper keeps running after Chromium exits.
        browser = (
            os.environ.get("OWNMAIL_BROWSER_EXECUTABLE")
            or subprocess.run(
                [pdf_browser_node, "-e", "console.log(require('playwright').chromium.executablePath())"],
                cwd=pdf_export._RENDERER.with_name("sanitizer"),
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            ).stdout.strip()
        )
        wrapper = tmp_path / "slow-close-browser"
        # Record the PID first: under load Chromium itself can overrun the
        # deadline, and the wrapper is killed before reaching its sleep. The
        # closed marker times the slow close independently of render speed.
        wrapper.write_text(
            f'#!/bin/sh\necho $$ > "{tmp_path}/wrapper.pid"\n"{browser}" "$@"\n'
            f'touch "{tmp_path}/closed"\nexec sleep 60\n'
        )
        wrapper.chmod(0o755)
        monkeypatch.setenv("OWNMAIL_BROWSER_EXECUTABLE", str(wrapper))
    # Exercise the browser boundary even if a future sanitizer accidentally keeps
    # a script. This is trusted synthetic runner input, never raw production mail.
    document = tmp_path / "000001.html"
    document.write_text(
        '<!doctype html><p>SAFE BODY</p><script>document.querySelector("p").textContent="SCRIPT RAN";</script>'
    )
    pdf_export._run_renderer(pdf_browser_node, str(tmp_path), "1", timeout=60)
    finished = time.time()
    result = tmp_path / "000001.pdf"
    assert result.read_bytes().startswith(b"%PDF-")
    extractor = shutil.which("pdftotext")
    if extractor:
        text = subprocess.run(
            [extractor, str(result), "-"], capture_output=True, text=True, check=True, timeout=15
        ).stdout
        assert "SAFE BODY" in text and "SCRIPT RAN" not in text
    if slow_close:
        # The renderer stops waiting 5s after close starts; Playwright alone
        # would wait 30s before force-killing the browser.
        closed = tmp_path / "closed"
        if closed.exists():
            assert finished - closed.stat().st_mtime < 15, "Renderer waited for the slow close"
        wrapper_pid = int((tmp_path / "wrapper.pid").read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(wrapper_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            pytest.fail("Browser left closing outlived the renderer")


def test_missing_browser_fails_without_installation_or_output(archive, store, tmp_path, monkeypatch):
    store("one")
    before = test_export.snapshot(archive)
    monkeypatch.setenv("OWNMAIL_BROWSER_EXECUTABLE", str(tmp_path / "missing-chromium"))
    output = tmp_path / "missing-renderer"
    with pytest.raises(OSError, match="renderer unavailable"):
        pdf_export.export_pdf(archive, output)
    assert not output.exists()
    assert test_export.snapshot(archive) == before
    test_export.assert_no_temporary_exports(output)


@pytest.mark.skipif(os.name != "posix", reason="Synthetic POSIX Ctrl-C process regression")
def test_actual_ctrl_c_stops_renderer_child(tmp_path):
    import signal
    import subprocess
    import time

    child = tmp_path / "child.py"
    child.write_text(
        "import os,time\nfrom pathlib import Path\nPath(__file__).with_name('child.pid').write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    caller = tmp_path / "caller.py"
    caller.write_text(
        "import sys\nfrom pathlib import Path\nfrom ownmail import pdf_export\n"
        "pdf_export._RENDERER=Path(__file__).with_name('child.py')\n"
        "try:\n    pdf_export._run_renderer(sys.executable, timeout=20)\n"
        "except KeyboardInterrupt:\n    sys.exit(42)\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1])
    with subprocess.Popen(
        [sys.executable, str(caller)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as process:
        try:
            deadline = time.monotonic() + 5
            while not (tmp_path / "child.pid").exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert (tmp_path / "child.pid").exists()
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=8)
            assert process.returncode == 42, (stdout, stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    with pytest.raises(ProcessLookupError):
        os.kill(int((tmp_path / "child.pid").read_text()), 0)


@pytest.mark.skipif(os.name != "posix", reason="Owned POSIX process-group regression")
@pytest.mark.parametrize(
    ("inherit_descriptors", "interrupt", "stubborn_leader"),
    [(True, False, False), (False, False, False), (True, True, False), (False, True, False), (True, False, True)],
    ids=[
        "timeout-inherited-output",
        "timeout-closed-output",
        "ctrl-c-inherited-output",
        "ctrl-c-closed-output",
        "stubborn-leader",
    ],
)
def test_stubborn_renderer_descendant_is_stopped_with_bounded_cleanup(
    tmp_path, inherit_descriptors, interrupt, stubborn_leader
):
    import signal
    import subprocess
    import time

    child = tmp_path / "stubborn.py"
    child.write_text(
        "import os,signal,time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "Path(__file__).with_name('descendant.pid').write_text(str(os.getpid()))\n"
        "time.sleep(40)\n"
    )
    renderer = tmp_path / "renderer.py"
    redirect = "" if inherit_descriptors else ", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL"
    renderer.write_text(
        "import os,signal,subprocess,sys,time\nfrom pathlib import Path\n"
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if stubborn_leader else "")
        + "Path(__file__).with_name('renderer.pid').write_text(str(os.getpid()))\n"
        f"subprocess.Popen([sys.executable,str(Path(__file__).with_name('stubborn.py'))]{redirect})\n"
        "time.sleep(40)\n"
    )
    caller = tmp_path / "caller.py"
    caller.write_text(
        "import sys\nfrom pathlib import Path\nfrom ownmail import pdf_export\n"
        "pdf_export._RENDERER=Path(__file__).with_name('renderer.py')\n"
        "pdf_export._TERM_GRACE_SECONDS=(0.3, 0.1)\n"
        f"try:\n    pdf_export._run_renderer(sys.executable, timeout={20 if interrupt else 1})\n"
        "except KeyboardInterrupt:\n    sys.exit(42)\n"
        "except OSError as error:\n    print(error)\n"
    )
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1]), PYTHONDONTWRITEBYTECODE="1")
    process = subprocess.Popen([sys.executable, str(caller)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        if interrupt:
            deadline = time.monotonic() + 5
            while not (tmp_path / "descendant.pid").exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert (tmp_path / "descendant.pid").exists()
            process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=6)
        assert process.returncode == (42 if interrupt else 0), (stdout, stderr)
        if not interrupt:
            assert b"timed out" in stdout
        descendant = int((tmp_path / "descendant.pid").read_text())

        # Allow the OS to reap the now-orphaned descendant. A Linux zombie is
        # already stopped; minimal container init processes may leave it unreaped.
        def running():
            try:
                os.kill(descendant, 0)
            except ProcessLookupError:
                return False
            stat = Path(f"/proc/{descendant}/stat")
            try:
                return stat.read_text().rpartition(") ")[2].split()[0] != "Z"
            except FileNotFoundError:
                return True

        deadline = time.monotonic() + 2
        while running() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not running(), "Cleanup returned while its SIGTERM-resistant descendant survived"
    finally:
        marker = tmp_path / "renderer.pid"
        if marker.exists():
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)
