"""Message styles work within the Print page's container and preserve the surrounding trusted UI."""

import json
from email.message import EmailMessage

import pytest

from tests import test_email_contrast, test_reader_spacing

shell_app = test_email_contrast.shell_app
spacing_sanitizer = test_reader_spacing.spacing_sanitizer


def run_print_probe(shell_app, browser_node, sanitizer, markup, assertions):
    """Render markup through the sanitizer and the Print route, then run assertions on its trusted text."""
    app, archive = shell_app
    app.config.update(sanitizer=sanitizer, block_images=True)
    message = EmailMessage()
    message["Subject"] = "Synthetic print probe"
    message["From"] = "Synthetic Sender <sender@example.com>"
    message.set_content(markup, subtype="html")
    message.add_attachment(b"synthetic", maintype="application", subtype="octet-stream", filename="synthetic.bin")
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
    response = app.test_client().get("/print/synthetic")
    assert response.status_code == 200
    # The Print page opens the print dialog on load; the probe inspects the page instead.
    page = response.get_data(as_text=True).replace('<script src="/static/message-print.js"></script>', "")
    test_email_contrast.run_contrast_browser(
        app,
        browser_node,
        "",
        "",
        assertions,
        theme="light",
        viewport=(900, 2400),
        rendered_page=page,
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )


# Each piece of trusted text is the topmost element at its centre, on screen and in print layout.
TRUSTED_TEXT_ON_TOP = """
        for (const media of ['screen', 'print']) {
            await page.emulateMedia({media});
            const covered = await page.evaluate(() => {
                const trusted = [...document.querySelectorAll(
                    '.ownmail-pdf-header h1, .ownmail-pdf-header dd, .ownmail-pdf-note, .ownmail-pdf-attachments li')];
                if (trusted.length !== 6) return ['expected 6 trusted elements, found ' + trusted.length];
                return trusted.filter(element => {
                    const box = element.getBoundingClientRect();
                    const top = document.elementFromPoint(box.x + Math.min(box.width / 2, 20), box.y + box.height / 2);
                    return !element.contains(top);
                }).map(element => element.textContent.trim());
            });
            assert.deepEqual(covered, [], media);
        }
"""

COVER = "background:rgb(255, 0, 0);z-index:2147483647"


@pytest.mark.parametrize(
    "markup",
    [
        f'<p>Message copy</p><div style="position:fixed;inset:0;{COVER}">Cover</div>',
        f'<p>Message copy</p><div style="position:absolute;inset:0;height:3000px;{COVER}">Cover</div>',
        f'<p>Message copy</p><div style="position:relative;height:1000px;transform:translateY(-900px);{COVER}">'
        "Cover</div>",
        f'<p>Message copy</p><div style="position:relative;margin-top:-1500px;height:3000px;{COVER}">Cover</div>',
    ],
    ids=["fixed", "absolute", "transform", "negative-margin"],
)
def test_message_content_cannot_cover_trusted_text(shell_app, browser_node, spacing_sanitizer, markup):
    run_print_probe(shell_app, browser_node, spacing_sanitizer, markup, TRUSTED_TEXT_ON_TOP)


@pytest.mark.parametrize(
    "markup",
    [
        '<button id="show-cover" popovertarget="cover">Open</button>'
        f'<div id="cover" popover style="position:fixed;inset:0;width:auto;height:auto;margin:0;{COVER}">Cover</div>',
        '<button id="show-cover" commandfor="cover" command="show-modal">Open</button>'
        '<dialog id="cover" style="position:fixed;inset:0;width:auto;height:auto;max-width:none;max-height:none;'
        f'margin:0;{COVER}">Cover</dialog>',
    ],
    ids=["popover", "dialog"],
)
def test_message_top_layer_cannot_cover_trusted_text(shell_app, browser_node, spacing_sanitizer, markup):
    run_print_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        markup,
        """
        await page.locator('#show-cover').click();
        assert.equal(await page.locator('#cover').evaluate(el => el.matches(':popover-open, :modal')), false);
        """
        + TRUSTED_TEXT_ON_TOP,
    )


def test_message_font_face_cannot_replace_the_print_font(shell_app, browser_node, spacing_sanitizer):
    # Local monospace faces avoid a remote request and differ in width from any UI font. The family names
    # cover the generic keyword pdf.html uses and the UI fonts a template could name instead.
    faces = 'local("Courier New"), local("Courier"), local("Liberation Mono"), local("DejaVu Sans Mono")'
    families = ['"sans-serif"', "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "Roboto", "Helvetica", "Arial"]
    rules = "".join(f"@font-face {{font-family:{family}; src:{faces}}}" for family in families)
    run_print_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        f"<style>{rules}</style><p>Message copy</p>",
        """
        const widths = await page.evaluate(async faces => {
            const sender = document.querySelector('.ownmail-pdf-header dd');
            const style = document.createElement('style');
            style.textContent = `@font-face {font-family: OwnmailProbe; src: ${faces}}`;
            document.head.append(style);
            const reference = document.createElement('span');
            reference.textContent = sender.textContent;
            reference.style.cssText = `font-family: OwnmailProbe; font-size: ${getComputedStyle(sender).fontSize}; white-space: pre`;
            document.body.append(reference);
            const loaded = await document.fonts.load(`16px OwnmailProbe`, sender.textContent);
            await document.fonts.ready;
            const range = document.createRange();
            range.selectNodeContents(sender);
            const result = {loaded: loaded.length, sender: range.getBoundingClientRect().width,
                reference: reference.getBoundingClientRect().width};
            reference.remove();
            style.remove();
            return result;
        }, __FACES__);
        // Without a loaded probe face the comparison below would pass vacuously.
        assert.equal(widths.loaded, 1);
        assert(Math.abs(widths.sender - widths.reference) > 1, JSON.stringify(widths));
        """.replace("__FACES__", repr(faces)),
    )


@pytest.mark.parametrize(
    "css",
    [
        "@scope (.card) { img { width:37px; } }",
        "@scope (.card) { @media (min-width:1px) { img { width:37px; } } }",
        "@media (min-width:1px) { @scope (.card) { @supports (display:block) { "
        "@scope (.inner) { img { width:37px; } } } } }",
    ],
    ids=["scope", "grouped-rule", "nested-scope"],
)
def test_scoped_message_rules_apply_on_print_page(shell_app, browser_node, spacing_sanitizer, css):
    image = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    run_print_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        f"<style>{css}</style>"
        f'<div class="card"><div class="inner"><img id="scope-image" src="{image}" width="7" height="5"></div></div>'
        f'<img id="outside-card" src="{image}" width="7" height="5">',
        """
        for (const media of ['screen', 'print']) {
            await page.emulateMedia({media});
            assert.equal(await page.locator('#scope-image').evaluate(el => getComputedStyle(el).width), '37px', media);
            assert.equal(await page.locator('#outside-card').evaluate(el => getComputedStyle(el).width), '7px', media);
        }
        """,
    )


@pytest.mark.parametrize(
    "selector", [":scope + .scope-sibling", ":scope ~ .scope-sibling", "& + .scope-sibling", "& ~ .scope-sibling"]
)
def test_scoped_sibling_selectors_preserve_print_ui(shell_app, browser_node, spacing_sanitizer, selector):
    run_print_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        "<style>@scope (body, .ownmail-pdf-header, .ownmail-pdf-attachments) {"
        ":scope { --scope-root: active; } #inside-scope { width:37px; } "
        f"{selector} {{ opacity:0.2 !important; }}"
        '}</style><div id="inside-scope">Message copy</div>',
        """
        const selector = __SELECTOR__;
        const stylesheet = await page.locator('#ownmail-email-content style').textContent();
        assert(stylesheet.includes(`${selector} { opacity:0.2 !important; }`), stylesheet);
        await page.evaluate(() => {
            const container = document.getElementById('ownmail-email-content');
            for (let i = 0; i < 2; i++) {
                const sibling = document.createElement('div');
                sibling.className = 'scope-sibling';
                sibling.textContent = 'Trusted sibling ' + i;
                container.parentElement.append(sibling);
            }
        });
        for (const media of ['screen', 'print']) {
            await page.emulateMedia({media});
            assert.equal(await page.locator('#inside-scope').evaluate(el => getComputedStyle(el).width), '37px', media);
            assert.equal(await page.locator('#ownmail-email-content').evaluate(el =>
                getComputedStyle(el).getPropertyValue('--scope-root').trim()), 'active', media);
            const outside = await page.locator('.scope-sibling, .ownmail-pdf-header, .ownmail-pdf-attachments')
                .evaluateAll(elements => elements.map(el => ({opacity: getComputedStyle(el).opacity,
                    scope: getComputedStyle(el).getPropertyValue('--scope-root').trim()})));
            assert.deepEqual(outside, Array.from({length: 4}, () => ({opacity: '1', scope: ''})), media);
        }
        """.replace("__SELECTOR__", json.dumps(selector)),
    )
