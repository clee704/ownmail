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

from lxml import html as lxml_html

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

    def test_available_property_default(self):
        """Test available property defaults to False."""
        sanitizer = HtmlSanitizer()
        assert sanitizer.available is False

    def test_kill_process_handles_broken_pipe(self):
        """Test _kill_process handles BrokenPipeError on stdin.close."""
        sanitizer = HtmlSanitizer()

        mock_process = MagicMock()
        mock_process.stdin.close.side_effect = BrokenPipeError()
        sanitizer._process = mock_process

        sanitizer._kill_process()
        mock_process.terminate.assert_called_once()
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
                for comment in ("", "/* reset <p> margins */"):
                    with self.subTest(target=target, comment=comment):
                        html = f"<style>{comment} p {{ color: red; }} /*# sourceMappingURL={target} */</style><p>Hi</p>"
                        result, *_ = self.sanitizer.sanitize(html)
                        assert "#ownmail-email-content p" in result

    def test_preserves_html_comment_wrapped_css(self):
        """Legacy outer comment markers do not invalidate the scoped stylesheet."""
        for tag in ("style", "STYLE"):
            for css in (
                "<!--.wrapped { color: red; }-->",
                " \n\t<!--\n.wrapped { color: red; }\n-->\r\n ",
            ):
                with self.subTest(tag=tag, css=css):
                    result, *_ = self.sanitizer.sanitize(f'<{tag}>{css}</{tag}><p class="wrapped">Text</p>')
                    tree = lxml_html.fromstring(result)
                    styles = tree.xpath("//style")
                    assert len(styles) == 1
                    assert "#ownmail-email-content .wrapped" in styles[0].text_content()
                    assert "color: red" in styles[0].text_content()
                    assert tree.xpath("//p")[0].text_content() == "Text"

    def test_preserves_markup_like_css_text(self):
        """Markup in comments and strings must not erase rules or CSS operators."""
        for css in (
            "/* reset <p> margins */",
            '/* <P> <!note> </p> */ .markup::before { content: "<b>text</b>"; }',
            r".markup::before { content: '<em> \\ \' \3c b> <!-- literal -->'; }",
            r'.markup::before { content: "\<em> \3c strong>"; }',
        ):
            with self.subTest(css=css):
                result, *_ = self.sanitizer.sanitize(
                    f"<style>{css} @media (400px < width <= 900px) {{ "
                    '.markup > b { color: red; } }</style><p class="markup"><b>Text</b></p>'
                )
                tree = lxml_html.fromstring(result)
                styles = tree.xpath("//style")
                assert len(styles) == 1
                stylesheet = styles[0].text_content()
                assert "#ownmail-email-content .markup > b" in stylesheet
                assert "400px < width <= 900px" in stylesheet
                assert "color: red" in stylesheet
                if "content:" in css:
                    assert "#ownmail-email-content .markup::before" in stylesheet
                    assert "content:" in stylesheet
                assert tree.xpath("//p/b")[0].text_content() == "Text"

    def test_markup_like_css_cannot_create_html_elements(self):
        """Reparsing CSS strings and comments cannot create scripts or event handlers."""
        for css in (
            r""".probe::before { content: "\3c /StYlE><img id='css-injected' src='x' onerror='alert(1)'><ScRiPt>alert(2)</ScRiPt>"; }""",
            "/* </StYlE-not-an-end-tag><img id='css-injected' src='x' onerror='alert(1)'> */",
        ):
            with self.subTest(css=css):
                result, *_ = self.sanitizer.sanitize(
                    f'<style>{css} .probe {{ color: red; }}</style><p class="probe">Text</p>'
                )
                tree = lxml_html.fromstring(result)
                styles = tree.xpath("//style")
                assert len(styles) == 1
                assert "#ownmail-email-content .probe" in styles[0].text_content()
                assert not tree.xpath("//script | //img | //*[@id='css-injected']")
                assert not any(name.lower().startswith("on") for element in tree.iter() for name in element.attrib)
                assert [element.tag for element in tree.xpath("//body/*")] == ["p"]
                assert tree.xpath("//p")[0].text_content() == "Text"

    def test_filters_declarations_in_markup_like_css(self):
        """Preserving stylesheet text keeps the declaration and import filters active."""
        css = """
            @import url("https://evil.com/spy.css");
            /* reset <p> margins */
            .filtered {
                color: red;
                width: expression(alert(1));
                background: url("javascript:alert(2)");
                behavior: url("https://evil.com/behavior.htc");
                -moz-binding: url("https://evil.com/binding.xml");
            }
        """
        for stylesheet in (css, f"<!--{css}-->"):
            with self.subTest(stylesheet=stylesheet):
                result, *_ = self.sanitizer.sanitize(f'<style>{stylesheet}</style><p class="filtered">Text</p>')
                tree = lxml_html.fromstring(result)
                styles = tree.xpath("//style")
                assert len(styles) == 1
                sanitized_css = styles[0].text_content()
                assert "#ownmail-email-content .filtered" in sanitized_css
                assert "color: red" in sanitized_css
                for forbidden in ("@import", "expression", "javascript:", "behavior", "-moz-binding"):
                    assert forbidden not in sanitized_css

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

    def test_preserves_qualified_body_selectors_after_extraction(self):
        """Matching static body predicates survive extraction without a new wrapper."""
        from ownmail.web import _extract_body_content

        cases = (
            ("body.main", 'class="main"', " .probe"),
            ("body[class=main]", 'class="main"', " > .probe"),
            ("body#message", 'id="message"', " .probe::before"),
            (
                'body.main.news#message[class~="main"][data-kind = "message copy"]',
                'class="main news" id="message" data-kind="message copy"',
                " > .probe + section .probe",
            ),
            ("BODY.main", 'class="main"', " > .probe"),
            ('body[class = "main news"]', 'class="main news"', " .probe"),
            ("body[data-kind]", 'data-kind="message copy"', " .probe"),
        )
        for compound, attributes, suffix in cases:
            for placement in ("head", "body"):
                with self.subTest(compound=compound, placement=placement):
                    style = f"<style>{compound}{suffix} {{ color: red; }}</style>"
                    head_style = style if placement == "head" else ""
                    body_style = style if placement == "body" else ""
                    result, *_ = self.sanitizer.sanitize(
                        f"<html><head>{head_style}</head><body {attributes}>{body_style}"
                        '<p class="probe">Direct</p><section><p class="probe">Nested</p></section></body></html>'
                    )
                    content, container_attributes = _extract_body_content(result)
                    tree = lxml_html.fragment_fromstring(content, create_parent="div")
                    styles = tree.xpath("./style")
                    assert len(styles) == 1
                    # The DIV container cannot match BODY; :not() retains the
                    # compound's specificity without forgiving invalid syntax.
                    expected = f"#ownmail-email-content:not({compound}){suffix}"
                    assert expected + " { color: red; }" in styles[0].text_content()
                    assert container_attributes == {}
                    assert [element.tag for element in tree] == ["style", "p", "section"]
                    assert tree.xpath("./p")[0].text_content() == "Direct"
                    assert tree.xpath("./section/p")[0].text_content() == "Nested"

    def test_qualified_body_selectors_respect_nonmatching_attributes(self):
        """A missing or different body predicate must not become unconditional."""
        for compound in (
            "body.other",
            "body#other",
            "body[class=main]",
            'body.main#message[data-kind="other"]',
            "body[data-missing]",
        ):
            for placement in ("head", "body"):
                with self.subTest(compound=compound, placement=placement):
                    style = f"<style>{compound} .probe {{ color: red; }}</style>"
                    result, *_ = self.sanitizer.sanitize(
                        f"<html><head>{style if placement == 'head' else ''}</head>"
                        '<body class="main news" id="message" data-kind="message copy">'
                        f'{style if placement == "body" else ""}<p class="probe">Text</p></body></html>'
                    )
                    stylesheet = lxml_html.fromstring(result).xpath("//style")[0].text_content()
                    assert stylesheet == f"#ownmail-email-content {compound} .probe {{ color: red; }}"

    def test_qualified_body_selectors_use_sanitized_attributes(self):
        """Removed clobbering IDs and event attributes cannot activate body rules."""
        css = (
            "body.main .probe { color: red; }"
            "body#attributes .probe { color: blue; }"
            "body[id=attributes] .probe { color: green; }"
            "body[onload] .probe { color: yellow; }"
        )
        for placement in ("head", "body"):
            with self.subTest(placement=placement):
                style = f"<style>{css}</style>"
                result, *_ = self.sanitizer.sanitize(
                    f"<html><head>{style if placement == 'head' else ''}</head>"
                    '<body class="main" id="attributes" onload="unsafe()">'
                    f'{style if placement == "body" else ""}<p class="probe">Text</p></body></html>'
                )
                tree = lxml_html.fromstring(result)
                body = tree.xpath("//body")[0]
                assert body.get("id") is None
                assert body.get("onload") is None
                stylesheet = tree.xpath("//style")[0].text_content()
                for compound in ("body#attributes", "body[id=attributes]", "body[onload]"):
                    assert f"#ownmail-email-content {compound} .probe" in stylesheet
                    assert f":not({compound})" not in stylesheet
                assert "#ownmail-email-content:not(body.main) .probe { color: red; }" in stylesheet

    def test_qualified_body_selectors_use_final_inline_style(self):
        """Head/body styles see the same attribute after inline CSS cleanup."""
        for inline, compound, matches in (
            ("font-family: Roboto", 'body[style*="sans-serif"]', True),
            ("width: expression(alert(1))", 'body[style*="expression"]', False),
        ):
            for placement in ("head", "body"):
                with self.subTest(inline=inline, placement=placement):
                    style = f"<style>{compound} .probe {{ color: red; }}</style>"
                    result, *_ = self.sanitizer.sanitize(
                        f"<html><head>{style if placement == 'head' else ''}</head>"
                        f'<body style="{inline}">{style if placement == "body" else ""}'
                        '<p class="probe">Text</p></body></html>'
                    )
                    tree = lxml_html.fromstring(result)
                    final_style = tree.xpath("//body")[0].get("style")
                    assert "expression" not in final_style
                    if matches:
                        assert "sans-serif" in final_style
                    prefix = (
                        f"#ownmail-email-content:not({compound})" if matches else f"#ownmail-email-content {compound}"
                    )
                    assert tree.xpath("//style")[0].text_content() == prefix + " .probe { color: red; }"

    def test_qualified_body_selectors_keep_author_scoped_rules_unchanged(self):
        """Deferred head styles must retain the provenance of already-scoped rules."""
        scoped_rules = (
            "#ownmail-email-content body.main .probe { color: blue; }"
            "body.main #ownmail-email-content .probe { color: green; }"
        )
        for placement in ("head", "body"):
            with self.subTest(placement=placement):
                style = f"<style>body.main .probe {{ color: red; }}{scoped_rules}</style>"
                result, *_ = self.sanitizer.sanitize(
                    f"<html><head>{style if placement == 'head' else ''}</head><body class=main>"
                    f'{style if placement == "body" else ""}<p class="probe">Text</p></body></html>'
                )
                stylesheet = lxml_html.fromstring(result).xpath("//style")[0].text_content()
                assert scoped_rules in stylesheet
                assert "#ownmail-email-content:not(body.main) .probe { color: red; }" in stylesheet

    def test_qualified_body_selectors_keep_unsupported_roots_unchanged(self):
        """Dynamic, escaped and malformed body compounds retain the existing fallback."""
        for selector in (
            "body.main:hover .probe",
            "body.main:has(.probe) .probe",
            r"body.ma\69 n .probe",
            r"b\6f dy.main .probe",
            "body..main .probe",
        ):
            with self.subTest(selector=selector):
                result, *_ = self.sanitizer.sanitize(
                    f"<html><head><style>{selector} {{ color: red; }}</style></head>"
                    '<body class="main"><p class="probe">Text</p></body></html>'
                )
                stylesheet = lxml_html.fromstring(result).xpath("//style")[0].text_content()
                assert stylesheet == f"#ownmail-email-content {selector} {{ color: red; }}"

    def test_qualified_body_selectors_do_not_activate_root_siblings(self):
        """Mapping a matching body must never make a selector reach app siblings."""
        for selector in (
            "body.main + .shell",
            "body.main+.shell",
            "body[class=main] ~ .shell",
            "body#message~.shell",
        ):
            for placement in ("head", "body"):
                with self.subTest(selector=selector, placement=placement):
                    style = f"<style>{selector} {{ color: red; }}</style>"
                    result, *_ = self.sanitizer.sanitize(
                        f"<html><head>{style if placement == 'head' else ''}</head>"
                        '<body class="main" id="message">'
                        f'{style if placement == "body" else ""}<p class="probe">Text</p></body></html>'
                    )
                    stylesheet = lxml_html.fromstring(result).xpath("//style")[0].text_content()
                    assert stylesheet == f"#ownmail-email-content {selector} {{ color: red; }}"

    def test_qualified_body_selectors_do_not_leak_between_requests(self):
        """The long-lived worker must resolve each stylesheet against its own body."""
        for attributes, matches in (
            ('class="main" id="message"', True),
            ("", False),
            ('class="other" id="other"', False),
            ('class="main" id="message"', True),
        ):
            with self.subTest(attributes=attributes):
                result, *_ = self.sanitizer.sanitize(
                    "<html><head><style>body.main#message .probe { color: red; }</style></head>"
                    f'<body {attributes}><p class="probe">Text</p></body></html>'
                )
                stylesheet = lxml_html.fromstring(result).xpath("//style")[0].text_content()
                selector = (
                    "#ownmail-email-content:not(body.main#message) .probe"
                    if matches
                    else "#ownmail-email-content body.main#message .probe"
                )
                assert stylesheet == selector + " { color: red; }"

    def _assert_body_predicate(self, compound, attributes, matches, doctype="<!DOCTYPE html>"):
        """Check a static predicate against actual sanitized head/body styles."""
        from html import escape

        body_attributes = "".join(f' {name}="{escape(value, quote=True)}"' for name, value in attributes.items())
        for placement in ("head", "body"):
            with self.subTest(compound=compound, attributes=attributes, doctype=doctype, placement=placement):
                style = f"<style>{compound} .probe {{ color: red; }}</style>"
                result, *_ = self.sanitizer.sanitize(
                    f"{doctype}<html><head>{style if placement == 'head' else ''}</head>"
                    f"<body{body_attributes}>{style if placement == 'body' else ''}"
                    '<p class="probe">Text</p></body></html>'
                )
                tree = lxml_html.fromstring(result)
                # HTML parsing normalizes carriage returns before predicates run.
                assert dict(tree.xpath("//body")[0].attrib) == {
                    name: value.replace("\r", "\n") for name, value in attributes.items()
                }
                selector = (
                    f"#ownmail-email-content:not({compound})" if matches else f"#ownmail-email-content {compound}"
                )
                assert tree.xpath("//style")[0].text_content() == selector + " .probe { color: red; }"

    def test_body_predicate_absent_attributes_do_not_match_null(self):
        """An absent DOM attribute is not the CSS string or identifier null."""
        for compound in (
            "body.null",
            "body#null",
            "body[missing=null]",
            "body[missing^=n]",
            "body[missing*=u]",
            "body[missing$=ll]",
        ):
            self._assert_body_predicate(compound, {}, False)
        self._assert_body_predicate(
            "body.null#null[data-present=null]", {"class": "null", "id": "null", "data-present": "null"}, True
        )

    def test_body_predicate_attribute_operators_and_empty_operands(self):
        """Each operator needs its own match semantics, including empty needles."""
        attributes = {"data-value": "en-us alpha", "data-empty": ""}
        for predicate, matches in (
            ("[data-value]", True),
            ("[data-missing]", False),
            ('[data-value="en-us alpha"]', True),
            ("[data-value=en-us]", False),
            ("[data-value~=alpha]", True),
            ("[data-value~=lph]", False),
            ('[data-value~="en-us alpha"]', False),
            ("[data-value|=en]", True),
            ("[data-value|=e]", False),
            ("[data-value^=en-]", True),
            ("[data-value^=us]", False),
            ("[data-value$=alpha]", True),
            ("[data-value$=en]", False),
            ("[data-value*=us]", True),
            ("[data-value*=missing]", False),
            ('[data-empty=""]', True),
            ('[data-value=""]', False),
            ('[data-empty|=""]', True),
            ('[data-value|=""]', False),
        ):
            self._assert_body_predicate("body" + predicate, attributes, matches)
        for name in ("data-value", "data-empty"):
            for operator in ("^=", "$=", "*=", "~="):
                self._assert_body_predicate(f'body[{name}{operator}""]', attributes, False)

    def test_body_predicate_tokens_use_ascii_whitespace(self):
        """Class and word predicates split ASCII whitespace, but not NBSP."""
        ascii_tokens = {"class": "first\tmain\nsecond\fthird\rfourth final"}
        self._assert_body_predicate("body.first.main.second.third.fourth.final", ascii_tokens, True)
        self._assert_body_predicate(
            "body[class~=first][class~=main][class~=second][class~=third][class~=fourth][class~=final]",
            ascii_tokens,
            True,
        )
        for compound, matches in (
            ("body.main", False),
            ("body[class~=main]", False),
            ("body.first\N{NO-BREAK SPACE}main", True),
            ('body[class~="first\N{NO-BREAK SPACE}main"]', True),
        ):
            self._assert_body_predicate(compound, {"class": "first\N{NO-BREAK SPACE}main"}, matches)

    def test_body_predicate_case_follows_source_mode_and_ascii_flags(self):
        """Quirks mode affects class/ID selectors; attribute flags fold only ASCII."""
        attributes = {"class": "MAIN Ä", "id": "MESSAGE", "data-case": "ABC Ä", "dir": "RTL"}
        for compound, standards_match, quirks_match in (
            ("body.main", False, True),
            ("body#message", False, True),
            ("body.ä", False, False),
            ('body[class~="main"]', False, False),
            ('body[data-case="abc Ä" i]', True, True),
            ('body[data-case="abc ä" i]', False, False),
            ('body[data-case="ABC Ä" s]', True, True),
            ('body[data-case="abc Ä" s]', False, False),
            ('body[data-case="ABC Ä"]', True, True),
            ('body[data-case="abc Ä"]', False, False),
            ("body[DIR=rtl]", True, True),
            ("body[dir=rtl s]", False, False),
            ("body[dir=RTL s]", True, True),
            ("body[dir=rtl i]", True, True),
        ):
            self._assert_body_predicate(compound, attributes, standards_match)
            self._assert_body_predicate(compound, attributes, quirks_match, doctype="")

    def test_body_predicate_validates_unescaped_identifier_grammar(self):
        """Invalid numeric identifiers cannot become valid through projection."""
        attributes = {
            "class": "123 - --main",
            "id": "123",
            "data-value": "123",
            "data-other": "-1",
            "data-dash": "--value",
        }
        for compound, matches in (
            ("body.123", False),
            ("body#123", False),
            ("body.-", False),
            ("body[data-value=123]", False),
            ("body[data-other=-1]", False),
            ('body[data-value="123"]', True),
            ('body[data-other="-1"]', True),
            ("body.--main", True),
            ("body[data-dash=--value]", True),
        ):
            self._assert_body_predicate(compound, attributes, matches)
        self._assert_body_predicate("body#--message", {"id": "--message"}, True)

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

    def test_authored_canvases_need_no_reader_padding(self):
        """The sender's main canvas supplies its own frame, including scoped CSS."""
        copy = '<p id="copy">Newsletter copy</p>'
        for name, stylesheet, body in (
            (
                "class-styled root",
                ".canvas {background:#eef1f4;margin:0;padding:24px}",
                f'<div class="canvas" id="panel">{copy}</div>',
            ),
            (
                "deeply wrapped table",
                "",
                '<div><div><div><table id="panel" width="100%" bgcolor="#eef1f4"><tbody><tr>'
                f'<td style="padding:24px">{copy}</td></tr></tbody></table></div></div></div>',
            ),
            (
                "principal layout cell",
                "",
                '<table width="100%"><tbody><tr><td id="panel" bgcolor="#eef1f4" style="padding:24px">'
                f"{copy}</td></tr></tbody></table>",
            ),
            (
                "inline root control",
                "",
                f'<div id="panel" style="background:#eef1f4;padding:24px">{copy}</div>',
            ),
            (
                "uppercase hidden preview before canvas",
                "",
                '<div style="display:NONE;background:#eef1f4">Preview</div>'
                f'<div style="background:#eef1f4;visibility:VISIBLE">{copy}</div>',
            ),
        ):
            with self.subTest(name=name):
                result, needs_padding, _ = self.sanitizer.sanitize(f"<style>{stylesheet}</style>{body}")
                tree = lxml_html.fromstring(result)
                assert lxml_html.tostring(tree.xpath("//body")[0], encoding="unicode") == f"<body>{body}</body>"
                if stylesheet:
                    assert tree.xpath("//style")[0].text_content() == (
                        "#ownmail-email-content .canvas {background:#eef1f4;margin:0;padding:24px}"
                    )
                assert needs_padding is False

    def test_simple_copy_with_backgrounds_keeps_reader_padding(self):
        """Decorations, hidden previews and uncertain backgrounds cannot supply a canvas."""
        copy = '<p id="copy">Simple formatted message</p>'
        for name, stylesheet, body in (
            ("simple HTML control", "", copy),
            ("hidden root control", "", '<div style="display:none;background:#eef1f4">Preview</div>' + copy),
            (
                "hidden class control",
                ".preview {display:none;background:#eef1f4}",
                '<div class="preview">Preview</div>' + copy,
            ),
            ("decorative badge", "", '<p><span style="background:#eef1f4">Badge</span></p>' + copy),
            (
                "nested hidden background",
                "",
                '<div><span style="display:none;background:#eef1f4">Preview</span></div>' + copy,
            ),
            (
                "decorative class control",
                ".badge {background:#eef1f4}",
                '<p><span class="badge">Badge</span></p>' + copy,
            ),
            (
                "conflicting class backgrounds",
                ".canvas {background:#eef1f4} .canvas {background:transparent}",
                f'<div class="canvas">{copy}</div>',
            ),
            (
                "conditional class background",
                "@media (min-width:600px) {.canvas {background:#eef1f4}}",
                f'<div class="canvas">{copy}</div>',
            ),
            (
                "escaped property is outside the static proof",
                r".canvas {background:#eef1f4;back\67 round:transparent}",
                f'<div class="canvas">{copy}</div>',
            ),
            ("bgcolor does not paint a div", "", f'<div bgcolor="#eef1f4">{copy}</div>'),
            (
                "text-clipped background is not a canvas",
                "",
                f'<div style="background:#eef1f4;background-clip:text">{copy}</div>',
            ),
            (
                "prefixed text-clipped background is uncertain",
                "",
                f'<div style="background:#eef1f4;-webkit-background-clip:text;color:transparent">{copy}</div>',
            ),
            (
                "masked background is uncertain",
                "",
                f'<div style="background:#eef1f4;mask-image:linear-gradient(transparent,transparent)">{copy}</div>',
            ),
            (
                "zero-sized copy is uncertain",
                "",
                f'<div style="background:#eef1f4;font-size:0;line-height:0">{copy}</div>',
            ),
            (
                "transparent modern color is not a canvas",
                "",
                f'<div style="background:color(srgb 1 1 1 / 0)">{copy}</div>',
            ),
            (
                "zero em height is uncertain",
                "",
                f'<div style="background:#eef1f4;height:0em;overflow:hidden">{copy}</div>',
            ),
            ("hidden content", "", f'<div style="background:#eef1f4;content-visibility:hidden">{copy}</div>'),
            ("closed details", "", f'<details><div style="background:#eef1f4">{copy}</div></details>'),
            ("closed dialog", "", f'<dialog><div style="background:#eef1f4">{copy}</div></dialog>'),
            (
                "colored caption beside an image region",
                "",
                '<div><div><img src="data:image/png;base64," alt="Synthetic"></div>'
                f'<div style="background:#eef1f4">{copy}</div></div>',
            ),
            (
                "colored copy in a competing table cell",
                "",
                '<table><tbody><tr><td><img src="data:image/png;base64," alt="Synthetic"></td>'
                f'<td><div style="background:#eef1f4">{copy}</div></td></tr></tbody></table>',
            ),
            (
                "colored copy beside an empty spacer cell",
                "",
                '<table><tbody><tr><td width="300"></td>'
                f'<td><div><div style="background:#eef1f4">{copy}</div></div></td></tr></tbody></table>',
            ),
            *(
                (
                    f"trailing image outside inline flow: {style}",
                    "",
                    f'<div style="background:#eef1f4">{copy}</div>'
                    f'<img src="data:image/png;base64," style="{style}" alt="Synthetic">',
                )
                for style in ("display:block", "float:right", "position:absolute")
            ),
        ):
            with self.subTest(name=name):
                result, needs_padding, _ = self.sanitizer.sanitize(f"<style>{stylesheet}</style>{body}")
                tree = lxml_html.fromstring(result)
                assert lxml_html.tostring(tree.xpath("//body")[0], encoding="unicode") == f"<body>{body}</body>"
                assert needs_padding is True

    def test_conditional_padding_rules_require_possible_targets(self):
        """Unused responsive rules cannot invalidate an otherwise solid canvas."""
        body = '<div class="canvas" style="background:#eef1f4;padding:24px"><p>Copy</p></div>'
        for selector, expected in (
            (".unused", False),
            (".canvas", True),
            (".unused, .canvas", True),
            (".unused:hover", True),  # Unsupported matching remains uncertain.
        ):
            rule = f"{selector} {{width:100%}}"
            for style in (
                f"<style>@media (max-width:600px) {{{rule}}}</style>",
                f'<style media="(max-width:600px)">{rule}</style>',
            ):
                with self.subTest(selector=selector, style=style):
                    result, needs_padding, _ = self.sanitizer.sanitize(style + body)
                    assert needs_padding is expected
                    tree = lxml_html.fromstring(result)
                    assert lxml_html.tostring(tree.xpath("//body")[0], encoding="unicode") == f"<body>{body}</body>"
                    assert "width:100%" in tree.xpath("//style")[0].text_content()

    def test_padding_selector_repeated_ancestors_finish(self):
        """An absent ancestor must not cause combinatorial matching retries."""
        source = (
            "<style>.missing "
            + " ".join([".x"] * 15)
            + "{background:#eee}</style>"
            + '<div class="x">' * 30
            + "Copy"
            + "</div>" * 30
        )
        result = subprocess.run(
            [shutil.which("node"), str(Path(sanitizer_module._SANITIZER_DIR) / "worker.js")],
            input=json.dumps({"id": 1, "html": source}) + "\n",
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        response = json.loads(result.stdout.splitlines()[-1])
        assert response["error"] is None
        assert response["needsPadding"] is True
        tree = lxml_html.fromstring(response["html"])
        assert len(tree.xpath('//div[@class="x"]')) == 30
        assert tree.xpath("//body")[0].text_content() == "Copy"

    def test_inapplicable_styles_keep_reader_padding(self):
        """Source BODY attributes and non-CSS text cannot paint the reader canvas."""
        body = '<div class="canvas"><p>Copy</p></div>'
        for name, body_attributes, style_attributes, selector, expected_selector in (
            (
                "source body class",
                ' class="sender"',
                "",
                ".sender #ownmail-email-content .canvas",
                ".sender #ownmail-email-content .canvas",
            ),
            ("non-CSS style", "", ' type="text/plain"', ".canvas", "#ownmail-email-content .canvas"),
        ):
            with self.subTest(name=name):
                result, needs_padding, _ = self.sanitizer.sanitize(
                    f"<html><head><style{style_attributes}>{selector} {{background:#eef1f4}}</style></head>"
                    f"<body{body_attributes}>{body}</body></html>"
                )
                assert result == (
                    f"<html><head><style{style_attributes}>{expected_selector} {{background:#eef1f4}}</style></head>"
                    f"<body{body_attributes}>{body}</body></html>"
                )
                assert needs_padding is True

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

    def _worker(self, ready=True, lines=None, stderr="", returncode=None):
        """Build a fake Popen whose stdout replays `lines` after a ready signal."""
        proc = MagicMock()
        proc.stderr = io.StringIO(stderr)
        proc.poll.return_value = returncode
        out = []
        if ready:
            out.append('{"ready": true}\n')
        out.extend(lines or [])
        proc.stdout.readline.side_effect = out + [""] * 10
        return proc

    def _threads(self):
        """Defer each drain until join, or until a test explicitly schedules it."""
        threads = []

        def factory(target, args=(), daemon=False):
            thread = MagicMock()
            thread.run.side_effect = lambda: target(*args)
            thread.join.side_effect = lambda timeout: thread.run()
            threads.append(thread)
            return thread

        return threads, factory

    def _start(self, san, proc, factory):
        with (
            patch.object(san, "is_node_available", return_value=True),
            patch.object(san, "_ensure_deps", return_value=True),
            patch("subprocess.Popen", return_value=proc),
            patch("ownmail.sanitizer.threading.Thread", side_effect=factory),
        ):
            san.start()

    def _fallback(self):
        return (
            "The sanitizer worker did not start. Check that Node.js is a supported LTS release (node --version).\n"
            f"If it is, delete {os.path.join(sanitizer_module._SANITIZER_DIR, 'node_modules')} "
            "and run ownmail serve again to reinstall the sanitizer dependencies."
        )

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
        """No recognizable error preserves the complete generic repair advice."""
        for stderr in ("", "\n/synthetic/worker.js:1\n  throw problem;\nwarning only\n"):
            with self.subTest(stderr=stderr):
                san = HtmlSanitizer()
                proc = self._worker(ready=False, stderr=stderr, returncode=1)
                threads, factory = self._threads()
                self._start(san, proc, factory)
                self.assertFalse(san.available)
                proc.terminate.assert_called_once()
                self.assertEqual(san.error, self._fallback())
                threads[0].join.assert_called_once_with(timeout=1)

    def test_start_with_garbage_ready_line_kills_worker(self):
        """A live invalid worker must not wait for or synchronously read stderr."""
        san = HtmlSanitizer()
        proc = self._worker(ready=False, lines=["not json\n"], returncode=None)
        proc.stderr = MagicMock()
        proc.stderr.readline.side_effect = AssertionError("synchronous stderr read")
        threads, factory = self._threads()
        self._start(san, proc, factory)
        self.assertFalse(san.available)
        self.assertEqual(san.error, self._fallback())
        proc.terminate.assert_called_once()
        proc.stderr.readline.assert_not_called()
        proc.stderr.read.assert_not_called()
        threads[0].join.assert_not_called()

    def test_exited_worker_reports_first_error_after_preamble(self):
        """An exited worker's delayed drain supplies its first actual error."""
        for diagnostic in (
            "Error: Cannot find module 'synthetic-missing-package'",
            "Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'synthetic-missing-package'",
            "SyntaxError: Unexpected token '}'",
        ):
            with self.subTest(diagnostic=diagnostic):
                stderr = f"/synthetic/worker.js:7\n    throw err;\n    ^\n\n{diagnostic}\n"
                stderr += "    at syntheticStackFrame\nError: later failure\n"
                proc = self._worker(ready=False, stderr=stderr, returncode=1)
                san = HtmlSanitizer()
                threads, factory = self._threads()
                self._start(san, proc, factory)
                self.assertEqual(san.error, diagnostic + "\n" + self._fallback())
                self.assertFalse(san.available)
                threads[0].join.assert_called_once_with(timeout=1)
                proc.terminate.assert_called_once()

    def test_exited_worker_with_unfinished_drain_uses_bounded_wait(self):
        """An inherited open pipe must not make startup wait indefinitely."""
        san = HtmlSanitizer()
        proc = self._worker(ready=False, returncode=1)
        thread = MagicMock()  # A timed join returns with the drain still pending.
        thread.is_alive.return_value = True
        self._start(san, proc, MagicMock(return_value=thread))
        thread.join.assert_called_once_with(timeout=1)
        self.assertEqual(san.error, self._fallback())
        proc.terminate.assert_called_once()

    def test_stdout_eof_before_exit_keeps_diagnostic_through_cleanup(self):
        """EOF may arrive before poll sees exit; cleanup can confirm it for the drain."""
        san = HtmlSanitizer()
        proc = self._worker(ready=False, stderr="SyntaxError: startup failed\n")

        def finish_exit(timeout):
            proc.poll.return_value = 1

        proc.wait.side_effect = finish_exit
        threads, factory = self._threads()
        self._start(san, proc, factory)
        self.assertFalse(san.available)
        self.assertEqual(san.error, "SyntaxError: startup failed\n" + self._fallback())
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=3)
        threads[0].join.assert_called_once_with(timeout=1)

    def test_restart_keeps_delayed_old_drain_on_its_own_worker(self):
        """A late old drain cannot steal or contaminate the replacement's error."""
        old = self._worker(stderr="Error: stale worker detail\n")
        new = self._worker(ready=False, stderr="Error: replacement failed\n", returncode=1)
        threads, factory = self._threads()

        def read_replacement_ready():
            threads[0].run()
            return ""

        new.stdout.readline.side_effect = read_replacement_ready
        san = HtmlSanitizer()
        with (
            patch.object(san, "is_node_available", return_value=True),
            patch.object(san, "_ensure_deps", return_value=True) as deps,
            patch("subprocess.Popen", side_effect=[old, new]),
            patch("ownmail.sanitizer.threading.Thread", side_effect=factory),
            patch("ownmail.sanitizer.logger.debug") as debug,
        ):
            san.start()
            self.assertTrue(san.available)
            san._restart()
        self.assertEqual([call.args for call in deps.call_args_list], [(True,), (False,)])
        self.assertEqual(old.stderr.tell(), len(old.stderr.getvalue()))
        self.assertEqual(new.stderr.tell(), len(new.stderr.getvalue()))
        self.assertEqual(san.error, "Error: replacement failed\n" + self._fallback())
        self.assertFalse(san.available)
        debug.assert_called_once_with("[sanitizer] %s", "Error: replacement failed")

    def test_ready_worker_does_not_capture_or_log_runtime_payload(self):
        """Once ready, stderr is drained without retaining message-like content."""
        proc = self._worker(stderr="Error: synthetic private message and credential marker\n")
        san = HtmlSanitizer()
        threads, factory = self._threads()
        with patch("ownmail.sanitizer.logger.debug") as debug:
            self._start(san, proc, factory)
            self.assertTrue(san.available)
            threads[0].run()
        self.assertIsNone(san.error)
        self.assertEqual(proc.stderr.tell(), len(proc.stderr.getvalue()))
        threads[0].join.assert_not_called()
        debug.assert_not_called()

    def test_startup_diagnostic_reads_and_summary_are_bounded(self):
        """Bound allocation, ignore continuation fragments, and keep one summary."""

        class BoundedPipe(io.StringIO):
            def __init__(self, text):
                super().__init__(text)
                self.sizes = []

            def readline(self, size=-1):
                assert 0 < size <= 1024
                self.sizes.append(size)
                return super().readline(size)

        raw = "x" * 1024 + "Error: continuation is not a new error\n"
        raw += "Error: " + "z" * 2000 + " synthetic trailing detail\nError: later failure\n"
        proc = self._worker(ready=False, returncode=1)
        proc.stderr = BoundedPipe(raw)
        san = HtmlSanitizer()
        _, factory = self._threads()
        with patch("ownmail.sanitizer.logger.debug") as debug:
            self._start(san, proc, factory)
        summary = san.error.splitlines()[0]
        self.assertTrue(summary.startswith("Error: z"))
        self.assertLessEqual(len(summary), 512)
        self.assertNotIn("continuation", san.error)
        self.assertNotIn("trailing detail", san.error)
        self.assertNotIn("later failure", san.error)
        self.assertTrue(proc.stderr.sizes)
        self.assertEqual(proc.stderr.tell(), len(raw))
        debug.assert_called_once_with("[sanitizer] %s", summary)

    def test_startup_capture_stops_after_line_budget_but_keeps_draining(self):
        raw = "preamble\n" * 32 + "Error: outside startup diagnostic budget\n"
        proc = self._worker(ready=False, stderr=raw, returncode=1)
        san = HtmlSanitizer()
        _, factory = self._threads()
        with patch("ownmail.sanitizer.logger.debug") as debug:
            self._start(san, proc, factory)
        self.assertEqual(san.error, self._fallback())
        self.assertEqual(proc.stderr.tell(), len(raw))
        debug.assert_not_called()

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
        proc.stdin.close.assert_called_once()
        proc.terminate.assert_called_once()
        self.assertIsNone(san._process)

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
        self.assertIsNone(san._process)

    def test_stop_without_worker_is_a_noop(self):
        """Stopping a sanitizer that never started should not raise."""
        san = HtmlSanitizer()
        san.stop()
        self.assertFalse(san.available)

    def test_drain_stderr_logs_and_survives_close(self):
        """The stderr drain should tolerate the pipe closing mid-read."""
        san = HtmlSanitizer()
        proc = self._worker(ready=False, returncode=1)
        proc.stderr = MagicMock()
        proc.stderr.readline.side_effect = ["  Error: worker\x00 warning  \n", "\n", ValueError("closed")]
        _, factory = self._threads()
        with patch("ownmail.sanitizer.logger.debug") as debug:
            self._start(san, proc, factory)
        self.assertEqual(san.error, "Error: worker warning\n" + self._fallback())
        debug.assert_called_once_with("[sanitizer] %s", "Error: worker warning")


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
        with patch("shutil.which", return_value=None) as which, patch("sys.stdout", new=io.StringIO()) as out:
            self.assertTrue(san._ensure_deps())
        self.assertEqual(out.getvalue(), "")
        which.assert_not_called()
        self.run.assert_not_called()
        self.assertIsNone(san.error)

    def test_changed_manifest_refreshes_existing_directory(self):
        """A raised manifest floor refreshes an existing installation rather than trusting its directory."""
        self._install(**self.CURRENT)
        self.assertTrue(self._ensure()[0])
        self.run.assert_not_called()
        manifest = dict(self.MANIFEST, dependencies=dict(self.MANIFEST["dependencies"], dompurify="^3.4.17"))
        self._write("package.json", manifest)
        self._npm(installs=dict(self.CURRENT, dompurify="3.4.17"))

        self.assertTrue(self._ensure()[0])
        self.run.assert_called_once()
        self.assertEqual(sanitizer_module._installed_version("dompurify"), "3.4.17")

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
                with (
                    patch.object(sanitizer_module.logger, "warning") as warning_log,
                    patch.object(san, "is_node_available", return_value=True),
                    patch("shutil.which", return_value="/usr/bin/npm"),
                    patch("subprocess.Popen") as worker,
                    patch("sys.stdout", new=io.StringIO()) as out,
                ):
                    san.start()
                self.assertFalse(san.available)
                worker.assert_not_called()
                self.assertNotIn("dependencies installed", out.getvalue())
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
        for installed, names in (({}, "dompurify, jsdom, postcss"), (self.STALE, "dompurify")):
            with self.subTest(installed=installed):
                self._reset(**installed)
                san = HtmlSanitizer()
                with (
                    patch.object(san, "is_node_available", return_value=True),
                    patch("shutil.which", return_value=None),
                    patch("subprocess.Popen") as worker,
                ):
                    san.start()
                self.assertFalse(san.available)
                worker.assert_not_called()
                self.assertEqual(
                    san.error,
                    f"npm was not found, so the sanitizer dependencies ({names}) could not be installed.\n"
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
        self._install(**self.CURRENT)
        for contents in (
            None,
            "{",
            "[]",
            "null",
            "{}",
            '{"dependencies": []}',
            '{"dependencies": {}}',
            '{"dependencies": null}',
        ):
            with self.subTest(contents=contents):
                if contents is None:
                    os.remove(os.path.join(self.dir, "package.json"))
                else:
                    self._write("package.json", contents)
                san = HtmlSanitizer()
                with (
                    patch.object(san, "is_node_available", return_value=True),
                    patch("shutil.which", return_value="/usr/bin/npm") as which,
                    patch("subprocess.Popen") as worker,
                ):
                    san.start()
                self.assertFalse(san.available)
                self.assertIn("The sanitizer's package.json could not be read", san.error)
                self.assertIn("Reinstall ownmail", san.error)
                worker.assert_not_called()
                which.assert_not_called()
                self.run.assert_not_called()

        san = HtmlSanitizer()
        with patch("builtins.open", side_effect=PermissionError("unreadable")):
            self.assertFalse(san._ensure_deps())
        self.assertIn("unreadable", san.error)
        self.run.assert_not_called()

    def test_null_requirement_cannot_start_worker(self):
        """An invalid range remains unmet after an attempted refresh and never reaches the worker."""
        self._install(**self.CURRENT)
        self._write(
            "package.json", dict(self.MANIFEST, dependencies=dict(self.MANIFEST["dependencies"], dompurify=None))
        )
        self._npm(installs=self.CURRENT)
        san = HtmlSanitizer()
        with (
            patch.object(san, "is_node_available", return_value=True),
            patch("shutil.which", return_value="/usr/bin/npm"),
            patch("subprocess.Popen") as worker,
        ):
            san.start()
        self.assertFalse(san.available)
        self.assertIn("left dompurify outside the package.json ranges", san.error)
        self.run.assert_called_once()
        worker.assert_not_called()

    def test_unreadable_installed_versions_are_unmet(self):
        """An installed package.json that is missing, invalid or has no string version counts as unmet."""
        target = os.path.join("node_modules", "dompurify", "package.json")
        for contents in ("{", "[]", "{}", '{"version": 3}', '{"version": "3.4.16-beta.1"}'):
            with self.subTest(contents):
                self._write(target, contents)
                self.assertEqual(sanitizer_module._unmet({"dompurify": "^3.4.16"}), ["dompurify"])
        self.assertEqual(sanitizer_module._unmet({"absent": "^1.0.0"}), ["absent"])
        with patch("builtins.open", side_effect=PermissionError("unreadable")):
            self.assertEqual(sanitizer_module._unmet({"dompurify": "^3.4.16"}), ["dompurify"])

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
            ("3.4.16-rc.1", "^3.4.16", False),
            ("4.0.0-rc.1", "^3.4.16", False),
            ("03.4.16", "^3.4.16", False),
            ("3.04.16", "^3.4.16", False),
            ("3.4.016", "^3.4.16", False),
            ("3.٤.16", "^3.4.16", False),
            ("3.4.16+build..2", "^3.4.16", False),
            ("3.4.16", None, False),
            ("3.4.16", "^03.4.16", False),
            ("3.4.16", "^3.04.16", False),
            ("3.4.16", "^3.4.016", False),
            ("3.4.16", "^3.٤.16", False),
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
        result, needs_padding, dark = san.sanitize("<script>alert(1)</script><p>Hello</p>")
        self.assertEqual(result, "&lt;script&gt;alert(1)&lt;/script&gt;&lt;p&gt;Hello&lt;/p&gt;")
        self.assertIs(needs_padding, True)
        self.assertIs(dark, False)

    def test_successful_response_is_returned(self):
        """A matching response should be returned with its flags."""
        san = HtmlSanitizer(verbose=True)
        self._ready(san, ['{"id": 1, "html": "<p>ok</p>", "needsPadding": false, "supportsDarkMode": true}\n'])
        result, needs_padding, dark = san.sanitize("<p>ok</p>")
        self.assertEqual(result, "<p>ok</p>")
        self.assertIs(needs_padding, False)
        self.assertIs(dark, True)

    def test_worker_error_field_escapes_input(self):
        """An error from DOMPurify should fall back to escaped HTML."""
        san = HtmlSanitizer()
        self._ready(san, ['{"id": 1, "error": "jsdom exploded"}\n'])
        result, needs_padding, dark = san.sanitize("<b>hi</b>")
        self.assertEqual(result, "&lt;b&gt;hi&lt;/b&gt;")
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
        self.assertEqual(result, "&lt;b&gt;hi&lt;/b&gt;")

    def test_broken_pipe_triggers_restart(self):
        """A broken stdin pipe should restart the worker and escape output."""
        san = HtmlSanitizer()
        proc = self._ready(san, [])
        proc.stdin.write.side_effect = BrokenPipeError("gone")
        with patch.object(san, "start") as mock_start:
            result, _, _ = san.sanitize("<b>hi</b>")
        mock_start.assert_called_once()
        self.assertEqual(result, "&lt;b&gt;hi&lt;/b&gt;")

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
