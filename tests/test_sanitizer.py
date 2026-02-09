"""Tests for the HTML sanitizer (DOMPurify sidecar)."""

import shutil
import unittest
from unittest.mock import MagicMock, patch

from ownmail.sanitizer import HtmlSanitizer


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

    def test_start_without_node(self):
        """Test start() gracefully handles missing Node.js."""
        sanitizer = HtmlSanitizer()
        with patch.object(HtmlSanitizer, "is_node_available", return_value=False):
            sanitizer.start()
        assert sanitizer.available is False

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

    @patch("ownmail.sanitizer.subprocess.run")
    @patch("ownmail.sanitizer.os.path.isdir", return_value=False)
    @patch("shutil.which")
    def test_ensure_deps_runs_npm_install(self, mock_which, mock_isdir, mock_run):
        """Test _ensure_deps runs npm install when node_modules missing."""
        mock_which.side_effect = lambda cmd: "/usr/bin/npm" if cmd == "npm" else None
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        sanitizer = HtmlSanitizer()
        result = sanitizer._ensure_deps()

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "install" in call_args[0][0]

    @patch("ownmail.sanitizer.os.path.isdir", return_value=True)
    def test_ensure_deps_skips_if_exists(self, mock_isdir):
        """Test _ensure_deps skips npm install when node_modules exists."""
        sanitizer = HtmlSanitizer()
        result = sanitizer._ensure_deps()
        assert result is True

    @patch("ownmail.sanitizer.os.path.isdir", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_ensure_deps_no_npm(self, mock_which, mock_isdir):
        """Test _ensure_deps returns False when npm not found."""
        sanitizer = HtmlSanitizer()
        result = sanitizer._ensure_deps()
        assert result is False


@unittest.skipUnless(node_available(), "Node.js not available")
class TestHtmlSanitizerIntegration(unittest.TestCase):
    """Integration tests that run the actual Node.js sidecar."""

    @classmethod
    def setUpClass(cls):
        """Start the sanitizer once for all integration tests."""
        cls.sanitizer = HtmlSanitizer(timeout=10.0)
        cls.sanitizer.start()
        if not cls.sanitizer.available:
            raise unittest.SkipTest("Sanitizer failed to start")

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
        html = '<html><head><meta http-equiv="refresh" content="0;url=https://evil.com"></head><body>Content</body></html>'
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

    def test_keeps_data_src_attribute(self):
        """Test that data-src attribute is preserved (used by image blocking)."""
        html = '<img data-src="https://example.com/img.jpg" src="data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==">'
        result, *_ = self.sanitizer.sanitize(html)
        assert "data-src" in result

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
        html = '<style>.header { color: red; } p { margin: 0; }</style><p>Text</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "#ownmail-email-content .header" in result
        assert "#ownmail-email-content p" in result
        assert "Text" in result

    def test_scopes_body_selector_to_email_content(self):
        """Test that body {} becomes #ownmail-email-content {}."""
        html = '<html><head><style>body { font-size: 14px; }</style></head><body><p>Hi</p></body></html>'
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
        """Test that @font-face blocks are not scoped."""
        html = '<style>@font-face { font-family: MyFont; src: local("MyFont"); } p { color: red; }</style><p>Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "@font-face" in result
        assert "@#ownmail-email-content" not in result
        assert "#ownmail-email-content p" in result

    def test_preserves_dark_mode_media(self):
        """Test that @media (prefers-color-scheme: dark) blocks are preserved."""
        html = '<style>p { color: #333; } @media (prefers-color-scheme: dark) { p { color: #fff; } }</style><p>Hi</p>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "color: #333" in result or "color:#333" in result
        assert "prefers-color-scheme" in result

    def test_dark_mode_detected_from_css(self):
        """Test emails with dark mode CSS are detected as supporting dark mode."""
        html = '<style>p { color: #333; } @media (prefers-color-scheme: dark) { p { color: #fff; } }</style><p>Hi</p>'
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
        html = '<p>Hello world</p>'
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
        html = '<style>td { font-family: Roboto; }</style><td>Hi</td>'
        result, *_ = self.sanitizer.sanitize(html)
        assert "sans-serif" in result
