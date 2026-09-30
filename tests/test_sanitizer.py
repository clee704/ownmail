"""Tests for the HTML sanitizer (DOMPurify sidecar)."""

import io
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import ownmail.sanitizer as sanitizer_module
from ownmail.download_lock import ProcessLock
from ownmail.sanitizer import HtmlSanitizer, _caret_floor, _satisfies


def node_available():
    """Check if Node.js is available for integration tests."""
    return shutil.which("node") is not None


class TestHtmlSanitizerUnit(unittest.TestCase):
    """Unit tests for HtmlSanitizer (mocked subprocess)."""

    def test_is_node_available_found(self):
        """Test is_node_available returns True when node exists."""
        with patch("shutil.which", return_value="/usr/local/bin/node"):
            assert HtmlSanitizer.is_node_available() is True

    def test_is_node_available_not_found(self):
        """Test is_node_available returns False when node missing."""
        with patch("shutil.which", return_value=None):
            assert HtmlSanitizer.is_node_available() is False

    def test_sanitize_without_node_returns_escaped(self):
        """Test sanitize() returns escaped HTML when not available."""
        import html as html_module

        sanitizer = HtmlSanitizer()
        html = "<script>alert(1)</script><p>Hello</p>"
        result, needs_padding, supports_dark = sanitizer.sanitize(html)
        assert result == html_module.escape(html)
        assert needs_padding is True
        assert supports_dark is False

    def test_stop_without_start(self):
        """Test stop() is safe to call without start()."""
        sanitizer = HtmlSanitizer()
        sanitizer.stop()  # Should not raise

    def test_available_property_default(self):
        """Test available property defaults to False."""
        sanitizer = HtmlSanitizer()
        assert sanitizer.available is False

    def test_sanitize_with_mocked_process(self):
        """Test sanitize() with a mocked running process."""
        import io
        import json

        sanitizer = HtmlSanitizer()
        sanitizer._available = True

        response = (
            json.dumps(
                {
                    "id": 1,
                    "html": "<p>Clean</p>",
                    "needsPadding": False,
                    "supportsDarkMode": True,
                }
            )
            + "\n"
        )

        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = io.StringIO(response)
        sanitizer._process = mock_process

        result_html, needs_padding, supports_dark = sanitizer.sanitize("<p>Clean</p>")
        assert result_html == "<p>Clean</p>"
        assert needs_padding is False
        assert supports_dark is True

    def test_sanitize_process_died(self):
        """Test sanitize() handles dead process gracefully."""
        import html as html_module
        import io

        sanitizer = HtmlSanitizer()
        sanitizer._available = True

        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = io.StringIO("")  # EOF = process died

        sanitizer._process = mock_process

        with patch.object(sanitizer, "_restart"):
            result, needs_padding, _ = sanitizer.sanitize("<p>Test</p>")

        assert result == html_module.escape("<p>Test</p>")

    def test_sanitize_broken_pipe(self):
        """Test sanitize() handles BrokenPipeError."""
        import html as html_module

        sanitizer = HtmlSanitizer()
        sanitizer._available = True

        mock_process = MagicMock()
        mock_process.stdin.write.side_effect = BrokenPipeError("broken")
        sanitizer._process = mock_process

        with patch.object(sanitizer, "_restart"):
            result, needs_padding, _ = sanitizer.sanitize("<p>Test</p>")

        assert result == html_module.escape("<p>Test</p>")

    def test_sanitize_dompurify_error(self):
        """Test sanitize() handles DOMPurify errors from worker."""
        import html as html_module
        import io
        import json

        sanitizer = HtmlSanitizer()
        sanitizer._available = True

        response = json.dumps({"id": 1, "error": "parse failed"}) + "\n"

        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = io.StringIO(response)
        sanitizer._process = mock_process

        result, needs_padding, _ = sanitizer.sanitize("<p>Test</p>")
        assert result == html_module.escape("<p>Test</p>")

    def test_kill_process(self):
        """Test _kill_process terminates the process."""
        sanitizer = HtmlSanitizer()

        mock_process = MagicMock()
        sanitizer._process = mock_process

        sanitizer._kill_process()

        mock_process.stdin.close.assert_called_once()
        mock_process.terminate.assert_called_once()
        assert sanitizer._process is None

    def test_kill_process_handles_broken_pipe(self):
        """Test _kill_process handles BrokenPipeError on stdin.close."""
        sanitizer = HtmlSanitizer()

        mock_process = MagicMock()
        mock_process.stdin.close.side_effect = BrokenPipeError()
        sanitizer._process = mock_process

        sanitizer._kill_process()
        mock_process.terminate.assert_called_once()
        assert sanitizer._process is None

    def test_kill_process_handles_timeout(self):
        """Test _kill_process uses kill() after wait timeout."""
        sanitizer = HtmlSanitizer()

        mock_process = MagicMock()
        # First wait(timeout=3) times out, second wait(timeout=1) succeeds
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired("node", 3),
            None,
        ]
        sanitizer._process = mock_process

        sanitizer._kill_process()
        mock_process.kill.assert_called_once()
        assert sanitizer._process is None

    def test_restart_calls_stop_and_start(self):
        """Test _restart kills and restarts the process without installing dependencies."""
        sanitizer = HtmlSanitizer()
        sanitizer._available = True

        with patch.object(sanitizer, "_kill_process") as mock_kill, patch.object(sanitizer, "start") as mock_start:
            sanitizer._restart()

        mock_kill.assert_called_once()
        assert sanitizer._available is False
        mock_start.assert_called_once_with(install=False)


@unittest.skipUnless(node_available(), "Node.js not available")
class TestHtmlSanitizerIntegration(unittest.TestCase):
    """Integration tests that run the actual Node.js sidecar."""

    @classmethod
    def setUpClass(cls):
        """Start the sanitizer once for all integration tests."""
        cls.sanitizer = HtmlSanitizer(timeout=10.0)
        cls.sanitizer.start()
        if not cls.sanitizer.available:
            raise unittest.SkipTest(f"Sanitizer failed to start: {cls.sanitizer.error}")

    @classmethod
    def tearDownClass(cls):
        """Stop the sanitizer after all integration tests."""
        cls.sanitizer.stop()

    def test_strips_script_tags(self):
        """Test that <script> tags are removed."""
        html = "<p>Hello</p><script>alert('xss')</script>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "<script>" not in result
        assert "alert" not in result
        assert "Hello" in result

    def test_strips_event_handlers(self):
        """Test that on* event attributes are removed."""
        html = '<p onclick="alert(1)" onmouseover="steal()">Text</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "onclick" not in result
        assert "onmouseover" not in result
        assert "Text" in result

    def test_keeps_safe_html(self):
        """Test that safe HTML is preserved."""
        html = "<h1>Title</h1><p>Paragraph with <strong>bold</strong> and <em>italic</em></p>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "<h1>Title</h1>" in result
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_keeps_data_uris(self):
        """Test that data: URIs for images are preserved (CID replacements)."""
        html = '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==" alt="inline">'
        result, *_ = self.sanitizer.sanitize(html)
        assert "data:image/png;base64" in result
        assert 'alt="inline"' in result

    def test_keeps_links(self):
        """Test that links are preserved with target=_blank."""
        html = '<a href="https://example.com">Link</a>'
        result, *_ = self.sanitizer.sanitize(html)
        assert 'href="https://example.com"' in result
        assert "Link" in result

    def test_strips_iframe(self):
        """Test that <iframe> tags are removed."""
        html = '<p>Text</p><iframe src="https://evil.com"></iframe>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "<iframe" not in result
        assert "Text" in result

    def test_strips_object_embed(self):
        """Test that <object> and <embed> tags are removed."""
        html = '<object data="evil.swf"></object><embed src="evil.swf"><p>Safe</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "<object" not in result
        assert "<embed" not in result
        assert "Safe" in result

    def test_allows_form_elements(self):
        """Test that form elements are preserved (matching Gmail behavior)."""
        html = '<form action="https://example.com"><input type="text" name="title"><button>Submit</button></form><p>Safe</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "<form" in result
        assert "<input" in result
        assert "<button" in result
        assert 'target="_blank"' in result
        assert "Safe" in result

    def test_strips_meta_refresh(self):
        """Test that <meta http-equiv=refresh> is removed."""
        html = (
            '<html><head><meta http-equiv="refresh" content="0;url=https://evil.com"></head><body>Content</body></html>'
        )
        result, *_ = self.sanitizer.sanitize(html)
        assert "http-equiv" not in result
        assert "Content" in result

    def test_strips_css_import(self):
        """Test that @import rules are removed from CSS."""
        html = '<style>@import url("https://evil.com/spy.css"); p { color: red; }</style><p>Text</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "@import" not in result or "removed" in result.lower()
        assert "color: red" in result or "color:red" in result
        assert "Text" in result

    def test_preserves_css_external_url(self):
        """Test that external url() references are preserved (blocking handled server-side)."""
        html = '<style>body { background: url("https://example.com/image.gif"); }</style><p>Text</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "example.com" in result
        assert "Text" in result

    def test_ignores_css_source_map_comments(self):
        """A sourceMappingURL comment can neither read a local file nor drop the stylesheet."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.map")
            with open(path, "w") as f:
                f.write("not a source map")
            # Loading either target as a source map fails the CSS parse, which drops the rule.
            for target in (path, "data:application/json,not%20a%20source%20map"):
                with self.subTest(target=target):
                    html = f"<style>p {{ color: red; }} /*# sourceMappingURL={target} */</style><p>Hi</p>"
                    result, *_ = self.sanitizer.sanitize(html)
                    assert "#ownmail-email-content p" in result

    def test_strips_css_javascript_url(self):
        """Test that javascript: url() references are removed."""
        html = '<div style="background: url(javascript:alert(1))">Text</div>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "javascript:" not in result
        assert "Text" in result

    def test_strips_css_expression(self):
        """Test that CSS expression() is removed."""
        html = '<div style="width: expression(document.body.clientWidth)">Text</div>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "expression" not in result or "removed" in result.lower()
        assert "Text" in result

    def test_keeps_inline_styles(self):
        """Test that safe inline CSS is preserved."""
        html = '<p style="color: blue; font-size: 14px;">Styled</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "color:" in result or "color: blue" in result
        assert "Styled" in result

    def test_preserves_table_structure(self):
        """Test that HTML email tables are preserved."""
        html = '<table><tr><td style="padding: 10px;">Cell</td></tr></table>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "<table>" in result or "<table" in result
        assert "<td" in result
        assert "Cell" in result

    def test_keeps_data_attributes(self):
        """Test that data-* attributes are preserved."""
        html = '<div data-note="kept">Content</div>'
        result, *_ = self.sanitizer.sanitize(html)
        assert 'data-note="kept"' in result

    def test_preserves_bgcolor(self):
        """Test that bgcolor attribute is preserved (common in email HTML)."""
        html = '<table bgcolor="#ffffff"><tr><td>Content</td></tr></table>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "bgcolor" in result

    def test_strips_javascript_uri(self):
        """Test that javascript: URIs are removed from links."""
        html = '<a href="javascript:alert(1)">Click</a>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "javascript:" not in result

    def test_multiple_sanitize_calls(self):
        """Test that multiple sequential calls work correctly."""
        html1 = "<p>First</p><script>bad()</script>"
        html2 = "<p>Second</p><script>bad()</script>"
        r1, *_ = self.sanitizer.sanitize(html1)
        r2, *_ = self.sanitizer.sanitize(html2)
        assert "First" in r1 and "<script>" not in r1
        assert "Second" in r2 and "<script>" not in r2

    def test_empty_html(self):
        """Test sanitizing empty HTML."""
        result, *_ = self.sanitizer.sanitize("")
        assert isinstance(result, str)

    def test_large_html(self):
        """Test sanitizing a large HTML string."""
        html = "<p>" + "x" * 100000 + "</p>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "x" in result
        assert len(result) > 100000

    def test_preserves_whole_document(self):
        """Test that full HTML document structure is preserved."""
        html = "<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "<html>" in result or "<html" in result
        assert "<body>" in result or "<body" in result
        assert "Hello" in result

    def test_scopes_css_selectors(self):
        """Test that CSS selectors are scoped under #ownmail-email-content."""
        html = "<style>.header { color: red; } p { margin: 0; }</style><p>Text</p>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "#ownmail-email-content .header" in result
        assert "#ownmail-email-content p" in result
        assert "Text" in result

    def test_scopes_body_selector_to_email_content(self):
        """Test that body {} becomes #ownmail-email-content {}."""
        html = "<html><head><style>body { font-size: 14px; }</style></head><body><p>Hi</p></body></html>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "#ownmail-email-content" in result
        assert "font-size" in result

    def test_scopes_css_in_media_query(self):
        """Test that selectors inside @media are also scoped."""
        html = '<style>@media (max-width: 600px) { .col { width: 100%; } }</style><div class="col">X</div>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "@media" in result
        assert "#ownmail-email-content .col" in result

    def test_preserves_font_face(self):
        """Font face descriptors retain the single family required by CSS."""
        html = '<style>@font-face { font-family: MyFont; src: local("MyFont"); } p { color: red; }</style><p>Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "@font-face" in result
        assert "font-family: MyFont;" in result
        assert "@#ownmail-email-content" not in result
        assert "#ownmail-email-content p" in result

    def test_preserves_dark_mode_media(self):
        """Test that @media (prefers-color-scheme: dark) blocks are preserved."""
        html = "<style>p { color: #333; } @media (prefers-color-scheme: dark) { p { color: #fff; } }</style><p>Hi</p>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "color: #333" in result or "color:#333" in result
        assert "prefers-color-scheme" in result

    def test_dark_mode_detected_from_css(self):
        """Test emails with dark mode CSS are detected as supporting dark mode."""
        html = "<style>p { color: #333; } @media (prefers-color-scheme: dark) { p { color: #fff; } }</style><p>Hi</p>"
        _, _, supports_dark = self.sanitizer.sanitize(html)
        assert supports_dark is True

    def test_dark_mode_detected_from_dark_background(self):
        """Test emails with dark inline backgrounds are detected as supporting dark mode."""
        html = '<div style="background-color: #1a1a2e; color: #fff;"><p>Dark email</p></div>'
        _, _, supports_dark = self.sanitizer.sanitize(html)
        assert supports_dark is True

    def test_dark_mode_detected_from_bgcolor(self):
        """Test emails with dark bgcolor attribute are detected as supporting dark mode."""
        html = '<table bgcolor="#222222"><tr><td>Dark</td></tr></table>'
        _, _, supports_dark = self.sanitizer.sanitize(html)
        assert supports_dark is True

    def test_light_email_no_dark_support(self):
        """Test plain emails without dark mode are not flagged as dark-capable."""
        html = "<p>Hello world</p>"
        _, _, supports_dark = self.sanitizer.sanitize(html)
        assert supports_dark is False

    def test_light_background_no_dark_support(self):
        """Test emails with light backgrounds are not flagged as dark-capable."""
        html = '<div style="background-color: #ffffff;"><p>Light</p></div>'
        _, _, supports_dark = self.sanitizer.sanitize(html)
        assert supports_dark is False

    def test_allows_google_fonts_import(self):
        """Test that @import from Google Fonts is preserved."""
        html = '<style>@import url("https://fonts.googleapis.com/css2?family=Roboto"); p { font-family: Roboto; }</style><p>Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "@import" in result
        assert "fonts.googleapis.com" in result
        assert "font-family" in result

    def test_strips_untrusted_import(self):
        """Test that @import from untrusted domain is removed."""
        html = '<style>@import url("https://evil.com/spy.css"); p { color: red; }</style><p>Text</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "evil.com" not in result
        assert "Text" in result

    def test_allows_google_fonts_font_face_url(self):
        """Test that @font-face with Google Fonts url() is preserved."""
        html = '<style>@font-face { font-family: Roboto; src: url("https://fonts.gstatic.com/s/roboto/v30/font.woff2"); }</style><p>Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "@font-face" in result
        assert "fonts.gstatic.com" in result

    def test_preserves_untrusted_font_face_url(self):
        """Test that @font-face with any url() is preserved (not a security risk)."""
        html = '<style>@font-face { font-family: Custom; src: url("https://example.com/font.woff2"); }</style><p>Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "example.com" in result

    def test_allows_trusted_font_link_tag(self):
        """Test that <link rel=stylesheet> from Google Fonts is preserved."""
        html = '<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto"></head><body><p>Hi</p></body></html>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "fonts.googleapis.com" in result
        assert "<link" in result

    def test_strips_untrusted_link_tag(self):
        """Test that <link rel=stylesheet> from untrusted domain is removed."""
        html = '<html><head><link rel="stylesheet" href="https://evil.com/spy.css"></head><body><p>Hi</p></body></html>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "evil.com" not in result
        assert "<link" not in result

    def test_strips_non_stylesheet_link_tag(self):
        """Test that <link rel=prefetch> to trusted domain is still removed."""
        html = '<html><head><link rel="prefetch" href="https://fonts.googleapis.com/css?family=Roboto"></head><body><p>Hi</p></body></html>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "<link" not in result

    def test_appends_sans_serif_fallback_inline(self):
        """Test that font-family without generic fallback gets sans-serif appended (inline style)."""
        html = '<p style="font-family: Roboto">Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "sans-serif" in result

    def test_keeps_existing_generic_fallback_inline(self):
        """Test that font-family already ending with generic is not modified."""
        html = '<p style="font-family: Arial, sans-serif">Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        # Should not have double sans-serif
        assert result.count("sans-serif") == 1

    def test_appends_sans_serif_fallback_style_block(self):
        """Test that font-family in <style> block gets sans-serif fallback."""
        html = "<style>td { font-family: Roboto; }</style><td>Hi</td>"
        result, *_ = self.sanitizer.sanitize(html)
        assert "sans-serif" in result

    def test_preserves_css_wide_font_keywords(self):
        """Inheritance and reset values must remain valid CSS values."""
        for prop in ("font-family", "font"):
            for keyword in ("inherit", "initial", "unset", "revert", "revert-layer"):
                for priority in ("", " !important"):
                    with self.subTest(prop=prop, keyword=keyword, priority=priority):
                        declaration = f"{prop}: {keyword}{priority};"
                        html = f'<style>p {{ {declaration} }}</style><p style="{declaration}">Hi</p>'
                        result, *_ = self.sanitizer.sanitize(html)
                        assert result.count(declaration) == 2

    def test_font_fallback_precedes_inline_priority(self):
        """Append a missing fallback before the declaration's priority."""
        for family, expected in (("Roboto", "Roboto, sans-serif"), ("Arial, sans-serif", "Arial, sans-serif")):
            for priority in (" !important", " ! IMPORTANT"):
                with self.subTest(family=family, priority=priority):
                    html = f'<p style="font-family: {family}{priority};">Hi</p>'
                    result, *_ = self.sanitizer.sanitize(html)
                    assert f"font-family: {expected}{priority};" in result


class TestSanitizerLifecycle(unittest.TestCase):
    """Tests for start/stop/restart with the Node worker mocked out."""

    def _worker(self, ready=True, lines=None):
        """Build a fake Popen whose stdout replays `lines` after a ready signal."""
        proc = MagicMock()
        proc.stderr = iter(())
        out = []
        if ready:
            out.append('{"ready": true}\n')
        out.extend(lines or [])
        proc.stdout.readline.side_effect = out + [""] * 10
        return proc

    def test_start_without_node_stays_unavailable(self):
        """With no node on PATH, start() should degrade rather than raise."""
        san = HtmlSanitizer()
        with patch.object(HtmlSanitizer, "is_node_available", return_value=False):
            san.start()
        self.assertFalse(san.available)
        self.assertIn("Node.js was not found", san.error)

    def test_start_aborts_when_deps_unavailable(self):
        """A failed dependency install should leave the sanitizer unavailable."""
        for install in (True, False):
            with self.subTest(install=install):
                san = HtmlSanitizer()
                with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
                    with patch.object(san, "_ensure_deps", return_value=False) as mock_deps:
                        with patch("subprocess.Popen") as mock_popen:
                            san.start(install=install)
                self.assertFalse(san.available)
                mock_deps.assert_called_once_with(install)
                mock_popen.assert_not_called()

    def test_start_marks_available_on_ready_signal(self):
        """A worker that signals ready should mark the sanitizer available and clear an earlier error."""
        san = HtmlSanitizer(verbose=True)
        san._error = "earlier failure"
        with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
            with patch.object(san, "_ensure_deps", return_value=True):
                with patch("subprocess.Popen", return_value=self._worker()):
                    san.start()
        self.assertTrue(san.available)
        self.assertIsNone(san.error)

    def test_start_without_ready_signal_kills_worker(self):
        """A worker that never signals ready should be terminated."""
        san = HtmlSanitizer()
        proc = self._worker(ready=False)
        with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
            with patch.object(san, "_ensure_deps", return_value=True):
                with patch("subprocess.Popen", return_value=proc):
                    san.start()
        self.assertFalse(san.available)
        proc.terminate.assert_called_once()
        self.assertIn("The sanitizer worker did not start", san.error)
        self.assertIn(os.path.join(sanitizer_module._SANITIZER_DIR, "node_modules"), san.error)

    def test_start_with_garbage_ready_line_kills_worker(self):
        """Non-JSON on the ready line should be treated as a failed start."""
        san = HtmlSanitizer()
        proc = MagicMock()
        proc.stderr = iter(())
        proc.stdout.readline.return_value = "not json\n"
        with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
            with patch.object(san, "_ensure_deps", return_value=True):
                with patch("subprocess.Popen", return_value=proc):
                    san.start()
        self.assertFalse(san.available)
        self.assertIn("The sanitizer worker did not start", san.error)

    def test_start_handles_missing_node_binary(self):
        """A FileNotFoundError from Popen should degrade gracefully."""
        san = HtmlSanitizer()
        with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
            with patch.object(san, "_ensure_deps", return_value=True):
                with patch("subprocess.Popen", side_effect=FileNotFoundError):
                    san.start()
        self.assertFalse(san.available)
        self.assertIn("Node.js was not found", san.error)

    def test_start_handles_unexpected_error(self):
        """Any other spawn failure should degrade gracefully."""
        san = HtmlSanitizer()
        with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
            with patch.object(san, "_ensure_deps", return_value=True):
                with patch("subprocess.Popen", side_effect=OSError("no fork")):
                    san.start()
        self.assertFalse(san.available)
        self.assertEqual(san.error, "The sanitizer worker could not start (no fork).")

    def test_stop_terminates_worker(self):
        """stop() should terminate the process and clear availability."""
        san = HtmlSanitizer()
        proc = self._worker()
        with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
            with patch.object(san, "_ensure_deps", return_value=True):
                with patch("subprocess.Popen", return_value=proc):
                    san.start()
        san.stop()
        self.assertFalse(san.available)
        proc.terminate.assert_called_once()

    def test_kill_escalates_to_sigkill_on_timeout(self):
        """A worker that ignores terminate should be killed."""
        san = HtmlSanitizer()
        proc = self._worker()
        proc.wait.side_effect = [subprocess.TimeoutExpired("node", 3), None]
        with patch.object(HtmlSanitizer, "is_node_available", return_value=True):
            with patch.object(san, "_ensure_deps", return_value=True):
                with patch("subprocess.Popen", return_value=proc):
                    san.start()
        san.stop()
        proc.kill.assert_called_once()

    def test_stop_without_worker_is_a_noop(self):
        """Stopping a sanitizer that never started should not raise."""
        san = HtmlSanitizer()
        san.stop()
        self.assertFalse(san.available)

    def test_drain_stderr_logs_and_survives_close(self):
        """The stderr drain should tolerate the pipe closing mid-read."""
        san = HtmlSanitizer()
        proc = MagicMock()

        def lines():
            yield "  worker warning  "
            yield ""
            raise ValueError("closed")

        proc.stderr = lines()
        san._process = proc
        san._drain_stderr()  # must not raise


class TestSanitizerDeps(unittest.TestCase):
    """Tests for _ensure_deps over a temporary sanitizer directory, with npm faked."""

    MANIFEST = {
        "private": True,
        "devDependencies": {"playwright": "1.58.0"},
        "dependencies": {"dompurify": "^3.4.16", "jsdom": "^26.0.0", "postcss": "^8.5.28"},
    }
    CURRENT = {"dompurify": "3.4.16", "jsdom": "26.1.0", "postcss": "8.5.28"}
    STALE = dict(CURRENT, dompurify="3.3.1")
    NETWORK_ARGS = ["--fetch-timeout=30000", "--fetch-retries=1", "--fetch-retry-mintimeout=2000"]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="sanitizer dir ")
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.node_modules = os.path.join(self.dir, "node_modules")
        self.marker = os.path.join(self.node_modules, sanitizer_module._INSTALL_MARKER)
        for target, value in (
            ("ownmail.sanitizer._SANITIZER_DIR", self.dir),
            # A test that forgets to fake npm fails instead of installing anything.
            ("ownmail.sanitizer.subprocess.run", MagicMock(side_effect=AssertionError("npm ran"))),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.run = sanitizer_module.subprocess.run
        self._write("package.json", self.MANIFEST)

    def _write(self, path, data):
        path = os.path.join(self.dir, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def _install(self, **versions):
        for name, version in versions.items():
            self._write(os.path.join("node_modules", name, "package.json"), {"name": name, "version": version})

    def _reset(self, **versions):
        shutil.rmtree(self.node_modules, ignore_errors=True)
        self._install(**versions)

    def _npm(self, returncode=0, stderr="", installs=None, scope="--omit=dev"):
        """Make npm install `installs` and exit with `returncode`, checking the marker it runs under."""

        def run(args, **kwargs):
            with open(self.marker, encoding="utf-8") as f:
                self.assertEqual(f.read(), scope, "npm must run under a marker that records its scope")
            self._install(**(installs or {}))
            return subprocess.CompletedProcess(args, returncode, "", stderr)

        self.run.side_effect = run

    def _ensure(self, san=None, npm="/usr/bin/npm", **kwargs):
        """Run _ensure_deps with `npm` on PATH, returning its result and printed output."""
        san = san or HtmlSanitizer()
        with patch("shutil.which", return_value=npm), patch("sys.stdout", new=io.StringIO()) as out:
            return san._ensure_deps(**kwargs), out.getvalue()

    def test_satisfied_install_needs_no_npm(self):
        """Installed versions within every range start without npm, even when npm is missing."""
        self._install(dompurify="3.9.0", jsdom="26.0.0", postcss="8.5.28+build.1")
        san = HtmlSanitizer()
        self.assertEqual(self._ensure(san, npm=None), (True, ""))
        self.run.assert_not_called()
        self.assertIsNone(san.error)

    def test_unmet_dependencies_are_installed(self):
        """Missing or out-of-range dependencies are installed, keeping a development tree's test dependencies."""
        cases = [
            ("first install", {}, "--omit=dev", "Installing HTML sanitizer dependencies from npm (one-time setup)"),
            ("stale", self.STALE, "--omit=dev", "Updating HTML sanitizer dependencies (dompurify) from npm"),
            ("missing", {"jsdom": "26.1.0"}, "--omit=dev", "Updating HTML sanitizer dependencies (dompurify, postcss)"),
            ("development tree", dict(self.STALE, playwright="1.58.0"), "--include=dev", "(dompurify) from npm"),
        ]
        for label, installed, scope, progress in cases:
            with self.subTest(label):
                self._reset(**installed)
                self._npm(installs=self.CURRENT, scope=scope)
                ready, out = self._ensure()
                self.assertTrue(ready)
                self.run.assert_called_once_with(
                    ["/usr/bin/npm", "install", scope, "--no-fund", "--no-audit", "--no-update-notifier"]
                    + self.NETWORK_ARGS,
                    cwd=self.dir,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                self.run.reset_mock()
                self.assertIn(progress, out)
                self.assertIn("✓ HTML sanitizer dependencies installed", out)
                self.assertFalse(os.path.exists(self.marker))

    def test_unfinished_install_is_redone(self):
        """A marker left by an interrupted install clears node_modules, keeping the marker, and installs again."""
        # The scope comes from the marker when it recorded one, else from the tree.
        for label, recorded, installed in (
            ("recorded scope", "--include=dev", self.CURRENT),
            ("unreadable scope", "", dict(self.CURRENT, playwright="1.58.0")),
        ):
            with self.subTest(label):
                self._reset(**installed)
                retired = os.path.join(self.node_modules, ".dompurify-6OOHNhdF")
                os.makedirs(retired)
                self._write(os.path.join("node_modules", ".package-lock.json"), "{}")
                self._write(os.path.join("node_modules", sanitizer_module._INSTALL_MARKER), recorded)
                self._npm(installs=self.CURRENT, scope="--include=dev")
                ready, out = self._ensure()
                self.assertTrue(ready)
                self.assertEqual(sorted(os.listdir(self.node_modules)), sorted(self.CURRENT))
                self.assertIn("--include=dev", self.run.call_args[0][0])
                self.assertIn("Reinstalling HTML sanitizer dependencies after an unfinished install", out)
                self.assertFalse(os.path.exists(self.marker))

    def test_marker_counts_until_npm_completes_an_install(self):
        """An install npm completes after the marker, such as the manual command, resolves it."""
        self._install(**self.CURRENT)
        open(self.marker, "w").close()
        lockfile = os.path.join(self.node_modules, ".package-lock.json")
        open(lockfile, "w").close()
        started = os.stat(self.marker).st_mtime_ns
        for label, offset, unfinished in (("completed later", 1, False), ("same time", 0, True), ("earlier", -1, True)):
            with self.subTest(label):
                os.utime(lockfile, ns=(started + offset * 10**9, started + offset * 10**9))
                self.assertIs(sanitizer_module._unfinished(self.node_modules), unfinished)
        os.remove(lockfile)
        self.assertTrue(sanitizer_module._unfinished(self.node_modules))
        os.utime(self.marker, ns=(started - 10**9, started - 10**9))
        open(lockfile, "w").close()
        self.assertEqual(self._ensure(npm=None), (True, ""))
        self.run.assert_not_called()

    def test_install_failures_are_reported(self):
        """Each failed install leaves the sanitizer stopped with a reason, a remedy and a manual command.

        A tree npm rolled back is kept. One it may have left half-written is
        cleared down to the marker, so the next start installs with the same scope.
        """
        internet = "Check the internet connection"
        crashed = "Check the internet connection and the npm output above"
        npm_error = "Fix the npm error shown above"
        warning = "npm warn deprecated inflight@1.0.6: This module is not supported\n"
        timeout = subprocess.TimeoutExpired("npm", 300)
        network = ["ECONNREFUSED", "ECONNRESET", "ENOTFOUND", "EAI_AGAIN", "EAI_FAIL", "EHOSTUNREACH"]
        network += ["ENETDOWN", "ENETUNREACH", "ETIMEDOUT", "ECONNABORTED", "EIDLETIMEOUT"]
        cases = [
            *[
                (code, (1, f"{warning}npm error code {code}"), f"npm install failed with {code}", internet, "kept")
                for code in network
            ],
            ("permissions", (1, "npm ERR! code EACCES"), "npm install failed with EACCES", npm_error, "kept"),
            (
                "crash",
                (1, "npm error Exit handler never called!"),
                "npm install exited with code 1",
                crashed,
                "removed",
            ),
            ("signal", (-9, ""), "npm install was stopped by signal 9", crashed, "removed"),
            (
                "still unmet",
                (0, ""),
                "npm install finished but left dompurify outside the package.json ranges",
                "Check the npm configuration",
                "kept",
            ),
            ("timeout", timeout, "npm install did not finish within 300 seconds", internet, "removed"),
            (
                "npm cannot run",
                OSError("Exec format error"),
                "npm could not run (Exec format error)",
                "Check the npm installation",
                "kept",
            ),
        ]
        for label, outcome, reason, hint, tree in cases:
            with self.subTest(label):
                self._reset(**self.STALE)
                if isinstance(outcome, Exception):
                    self.run.side_effect = outcome
                else:
                    self._npm(*outcome)
                san = HtmlSanitizer()
                with patch.object(sanitizer_module.logger, "warning") as warning_log:
                    ready, out = self._ensure(san)
                self.assertFalse(ready)
                self.assertNotIn("dependencies installed", out)
                cause, remedy, command = san.error.splitlines()
                self.assertEqual(cause, f"The sanitizer dependencies (dompurify) could not be installed: {reason}.")
                self.assertEqual(remedy, f"{hint}, then run ownmail serve again, or install them with:")
                self.assertEqual(shlex.split(command), ["npm", "--prefix", self.dir, "install", "--omit=dev"])
                if tree == "kept":
                    self.assertFalse(os.path.exists(self.marker))
                    self.assertEqual(sanitizer_module._installed_version("dompurify"), "3.3.1")
                else:
                    self.assertEqual(os.listdir(self.node_modules), [sanitizer_module._INSTALL_MARKER])
                    with open(self.marker, encoding="utf-8") as f:
                        self.assertEqual(f.read(), "--omit=dev")
                # npm's own output is logged whenever it fails.
                if isinstance(outcome, tuple) and outcome[0]:
                    self.assertIn(outcome[1], warning_log.call_args.args)
                else:
                    warning_log.assert_not_called()

    def test_development_tree_failure_suggests_its_scope(self):
        """The manual command keeps a development tree's test dependencies."""
        self._reset(**dict(self.STALE, playwright="1.58.0"))
        self._npm(1, "npm error code ENOTFOUND", scope="--include=dev")
        san = HtmlSanitizer()
        with patch.object(sanitizer_module.logger, "warning"):
            self.assertFalse(self._ensure(san)[0])
        self.assertEqual(
            shlex.split(san.error.splitlines()[-1]), ["npm", "--prefix", self.dir, "install", "--include=dev"]
        )

    def test_unremovable_half_written_install_keeps_marker(self):
        """If a half-written install cannot be cleared, its marker stays so the next start clears it."""
        self._reset(**self.STALE)
        self.run.side_effect = subprocess.TimeoutExpired("npm", 300)
        san = HtmlSanitizer()
        with patch("ownmail.sanitizer._clear", side_effect=OSError("busy")):
            self.assertFalse(self._ensure(san)[0])
        self.assertTrue(os.path.exists(self.marker))
        self.assertIn("did not finish within 300 seconds", san.error)

    def test_install_that_cannot_start_is_reported(self):
        """An unwritable node_modules is reported without running npm."""
        self._write("node_modules", "not a directory")
        san = HtmlSanitizer()
        self.assertFalse(self._ensure(san)[0])
        cause, remedy, _ = san.error.splitlines()
        self.assertIn("could not be installed: the install could not start (", cause)
        self.assertTrue(remedy.startswith(f"Check that {self.dir} is writable, then run ownmail serve again"))
        self.run.assert_not_called()

    def test_missing_npm_is_reported(self):
        """Without npm, unmet dependencies are named and nothing runs."""
        san = HtmlSanitizer()
        self.assertFalse(self._ensure(san, npm=None)[0])
        self.assertEqual(
            san.error,
            "npm was not found, so the sanitizer dependencies (dompurify, jsdom, postcss) could not be installed.\n"
            "Install Node.js with npm from https://nodejs.org, then run ownmail serve again.",
        )
        self.run.assert_not_called()

    def test_concurrent_install_is_reported(self):
        """While another process holds the install lock, nothing is installed or removed."""
        self._install(**self.STALE)
        san = HtmlSanitizer()
        with ProcessLock(Path(self.dir, ".install.lock")):
            self.assertFalse(self._ensure(san)[0])
        self.assertEqual(
            san.error,
            "Another ownmail process is installing the sanitizer dependencies.\n"
            "Wait for it to finish, then run ownmail serve again.",
        )
        self.run.assert_not_called()
        self.assertEqual(sanitizer_module._installed_version("dompurify"), "3.3.1")

    def test_install_finished_by_another_process_is_used(self):
        """If another process finishes the install before the lock is taken, npm does not run again."""
        self._install(**self.STALE)
        test = self

        class FinishedElsewhere(ProcessLock):
            def __enter__(self):
                test._install(**test.CURRENT)
                return super().__enter__()

        with patch("ownmail.sanitizer.ProcessLock", FinishedElsewhere):
            self.assertEqual(self._ensure(), (True, ""))
        self.run.assert_not_called()

    def test_unwritable_lock_is_reported(self):
        """A lock file that cannot be created is reported as an unwritable sanitizer directory."""
        self._install(**self.STALE)
        os.makedirs(os.path.join(self.dir, ".install.lock"))
        san = HtmlSanitizer()
        self.assertFalse(self._ensure(san)[0])
        self.assertTrue(san.error.startswith("The sanitizer dependencies (dompurify) could not be installed ("))
        self.assertTrue(san.error.endswith(f"Check that {self.dir} is writable, then run ownmail serve again."))
        self.run.assert_not_called()

    def test_restart_never_installs(self):
        """With install False, unmet or unfinished dependencies are reported rather than installed."""
        for label in ("stale", "unfinished"):
            with self.subTest(label):
                self._reset(**(self.STALE if label == "stale" else self.CURRENT))
                if label == "unfinished":
                    open(self.marker, "w").close()
                san = HtmlSanitizer()
                self.assertFalse(self._ensure(san, install=False)[0])
                self.assertIn("changed while ownmail serve was running", san.error)
                self.run.assert_not_called()

    def test_unremovable_unfinished_install_is_reported(self):
        """If an unfinished install cannot be removed, the error says which directory to delete."""
        self._install(**self.CURRENT)
        open(self.marker, "w").close()
        san = HtmlSanitizer()
        with patch("shutil.rmtree", side_effect=OSError("busy")):
            self.assertFalse(self._ensure(san)[0])
        self.assertEqual(
            san.error,
            "The sanitizer dependencies (dompurify, jsdom, postcss) could not be installed: "
            "an unfinished install could not be removed (busy).\n"
            f"Delete {self.node_modules}, then run ownmail serve again.",
        )
        self.assertTrue(os.path.exists(self.marker))
        self.run.assert_not_called()

    def test_unreadable_package_json_is_reported(self):
        """A broken shipped package.json stops the sanitizer instead of raising."""
        self._write("package.json", "{")
        san = HtmlSanitizer()
        self.assertFalse(san._ensure_deps())
        self.assertIn("The sanitizer's package.json could not be read", san.error)

    def test_unreadable_installed_versions_are_unmet(self):
        """An installed package.json that is missing, invalid or has no string version counts as unmet."""
        target = os.path.join("node_modules", "dompurify", "package.json")
        for contents in ("{", "[]", "{}", '{"version": 3}', '{"version": "3.4.16-beta.1"}'):
            with self.subTest(contents):
                self._write(target, contents)
                self.assertEqual(sanitizer_module._unmet({"dompurify": "^3.4.16"}), ["dompurify"])
        self.assertEqual(sanitizer_module._unmet({"absent": "^1.0.0"}), ["absent"])

    def test_windows_command_uses_windows_quoting(self):
        """The manual command quotes the path for cmd.exe on Windows."""
        san = HtmlSanitizer()
        with patch("ownmail.sanitizer.os.name", "nt"):
            san._install_failed(
                "dompurify", "npm install failed with EPERM", "Fix the npm error shown above", "--omit=dev"
            )
        expected = subprocess.list2cmdline(["npm", "--prefix", self.dir, "install", "--omit=dev"])
        self.assertEqual(san.error.splitlines()[-1], f"  {expected}")
        self.assertIn(f'"{self.dir}"', expected)

    def test_version_ranges(self):
        """Caret ranges keep the major version and never match a prerelease."""
        cases = [
            ("3.4.16", "^3.4.16", True),
            ("3.10.0", "^3.4.16", True),
            ("3.4.16+build.7", "^3.4.16", True),
            ("3.4.15", "^3.4.16", False),
            ("3.3.99", "^3.4.16", False),
            ("4.0.0", "^3.4.16", False),
            ("3.5.0-rc.1", "^3.4.16", False),
            ("26.1.0", "^26.0.0", True),
            (None, "^3.4.16", False),
            (3, "^3.4.16", False),
            # Ranges the check does not understand count as unmet, so npm decides.
            ("0.2.5", "^0.2.3", False),
            ("3.4.16", "~3.4.16", False),
            ("3.4.16", "3.4.16", False),
            ("3.4.16", ">=3.4.16", False),
            ("3.4.16", "^3.4.16 || ^4.0.0", False),
            ("3.4.16", "^3.4.16 - 3.9", False),
        ]
        for version, spec, expected in cases:
            with self.subTest(version=version, spec=spec):
                self.assertIs(_satisfies(version, spec), expected)

    def test_shipped_package_json_is_checkable(self):
        """The shipped package.json uses only what the dependency check understands."""
        with open(os.path.join(os.path.dirname(sanitizer_module.__file__), "package.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        # The check reads only dependencies; a field such as overrides would go unchecked.
        self.assertLessEqual(set(manifest), {"private", "dependencies", "devDependencies"})
        for name, spec in manifest["dependencies"].items():
            with self.subTest(name):
                self.assertIsNotNone(_caret_floor(spec), f"{name}: {spec} is not a ^X.Y.Z range with X >= 1")


class TestSanitizeErrorHandling(unittest.TestCase):
    """Tests for sanitize()'s failure paths, with the worker mocked."""

    def _ready(self, san, readline_side_effect):
        """Put `san` into an available state with a scripted stdout."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = readline_side_effect
        san._process = proc
        san._available = True
        return proc

    def test_unavailable_sanitizer_escapes_input(self):
        """With no worker, HTML must be escaped rather than passed through."""
        san = HtmlSanitizer()
        result, needs_padding, dark = san.sanitize("<script>alert(1)</script>")
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertTrue(needs_padding)
        self.assertFalse(dark)

    def test_successful_response_is_returned(self):
        """A matching response should be returned with its flags."""
        san = HtmlSanitizer(verbose=True)
        self._ready(san, ['{"id": 1, "html": "<p>ok</p>", "needsPadding": false, "supportsDarkMode": true}\n'])
        self.assertEqual(san.sanitize("<p>ok</p>"), ("<p>ok</p>", False, True))

    def test_worker_error_field_escapes_input(self):
        """An error from DOMPurify should fall back to escaped HTML."""
        san = HtmlSanitizer()
        self._ready(san, ['{"id": 1, "error": "jsdom exploded"}\n'])
        result, needs_padding, dark = san.sanitize("<b>hi</b>")
        self.assertIn("&lt;b&gt;", result)
        self.assertTrue(needs_padding)

    def test_invalid_json_lines_are_skipped(self):
        """Garbage lines should be ignored until a valid response arrives."""
        san = HtmlSanitizer()
        self._ready(san, ["not json\n", '{"id": 1, "html": "<p>ok</p>"}\n'])
        self.assertEqual(san.sanitize("<p>ok</p>")[0], "<p>ok</p>")

    def test_mismatched_ids_are_skipped(self):
        """A response for a different request should be ignored."""
        san = HtmlSanitizer()
        self._ready(san, ['{"id": 99, "html": "stale"}\n', '{"id": 1, "html": "<p>ok</p>"}\n'])
        self.assertEqual(san.sanitize("<p>ok</p>")[0], "<p>ok</p>")

    def test_dead_worker_triggers_restart(self):
        """An EOF on stdout means the worker died; it should be restarted."""
        san = HtmlSanitizer()
        self._ready(san, [""])
        with patch.object(san, "start") as mock_start:
            result, needs_padding, dark = san.sanitize("<b>hi</b>")
        mock_start.assert_called_once()
        self.assertIn("&lt;b&gt;", result)

    def test_broken_pipe_triggers_restart(self):
        """A broken stdin pipe should restart the worker and escape output."""
        san = HtmlSanitizer()
        proc = self._ready(san, [])
        proc.stdin.write.side_effect = BrokenPipeError("gone")
        with patch.object(san, "start") as mock_start:
            result, _, _ = san.sanitize("<b>hi</b>")
        mock_start.assert_called_once()
        self.assertIn("&lt;b&gt;", result)

    def test_timeout_triggers_restart(self):
        """A worker that never answers should time out and be restarted."""
        san = HtmlSanitizer()
        san._timeout = 0
        self._ready(san, ['{"id": 1, "html": "too late"}\n'])
        with patch.object(san, "start") as mock_start:
            result, _, _ = san.sanitize("<b>hi</b>")
        mock_start.assert_called_once()
        self.assertIn("&lt;b&gt;", result)

    def test_restart_failure_is_survivable(self):
        """If restarting also fails, sanitize should still return escaped HTML and log why."""

        def fail_start(install):
            san._error = "The sanitizer dependencies changed while ownmail serve was running."

        for failure in (OSError("no fork"), fail_start):
            with self.subTest(failure=failure):
                san = HtmlSanitizer()
                self._ready(san, [""])
                with patch.object(san, "start", side_effect=failure):
                    with self.assertLogs("ownmail.sanitizer", "WARNING") as logs:
                        result, _, _ = san.sanitize("<b>hi</b>")
                self.assertIn("&lt;b&gt;", result)
                self.assertFalse(san.available)
                self.assertIn(f"Failed to restart HTML sanitizer: {san.error}", logs.output[-1])
