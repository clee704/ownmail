"""Message CSS and markup that act through global names or the top layer stay in the frame."""

from email.message import EmailMessage

from tests import test_email_contrast, test_reader_spacing

shell_app = test_email_contrast.shell_app
spacing_sanitizer = test_reader_spacing.spacing_sanitizer


def run_probe(shell_app, browser_node, sanitizer, markup, assertions):
    """Render markup through the sanitizer and the reader route, then run assertions on app UI."""
    app, archive = shell_app
    app.config.update(sanitizer=sanitizer, block_images=True, auto_scale=False)
    message = EmailMessage()
    message["Subject"] = "Synthetic isolation probe"
    message["From"] = "Synthetic Sender <sender@example.com>"
    message.set_content(markup, subtype="html")
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = ("synthetic", "synthetic.eml", None, None, None, None)
    response = app.test_client().get("/email/synthetic")
    assert response.status_code == 200
    test_email_contrast.run_contrast_browser(
        app,
        browser_node,
        "",
        "",
        assertions,
        theme="light",
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )


# A reader control stays the topmost element at its centre and still responds.
CONTROL_WORKS = """
        const control = page.locator('#ownmail-message-details-toggle');
        const box = await control.boundingBox();
        assert.equal(await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('#ownmail-message-details-toggle')?.id,
            [box.x + box.width / 2, box.y + box.height / 2]), 'ownmail-message-details-toggle');
        await control.click({timeout: 2000});
        assert.equal(await control.getAttribute('aria-expanded'), 'true');
"""


def test_message_property_registration_cannot_recolor_app_text(shell_app, browser_node, spacing_sanitizer):
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        "<style>@property --ownmail-text {syntax:'<color>'; inherits:false; initial-value:rgb(255, 0, 0)}</style>"
        "<p>Message copy</p>",
        """
        const [subject, expected] = await page.evaluate(() => {
            const reference = document.createElement('span');
            reference.style.color = getComputedStyle(document.documentElement).getPropertyValue('--ownmail-text');
            document.body.append(reference);
            const colors = [getComputedStyle(document.querySelector('.ownmail-reader-subject')).color, getComputedStyle(reference).color];
            reference.remove();
            return colors;
        });
        assert.notEqual(subject, 'rgb(255, 0, 0)');
        assert.equal(subject, expected);
        """,
    )


def test_message_keyframes_cannot_replace_the_loading_spinner(shell_app, browser_node, spacing_sanitizer):
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        "<style>@keyframes ownmail-spin {from {opacity:0} to {opacity:0}}</style><p>Message copy</p>",
        """
        const keyframes = await page.evaluate(() => {
            document.getElementById('ownmail-loading-overlay').classList.add('ownmail-active');
            const animations = document.querySelector('.ownmail-loading-spinner').getAnimations();
            return animations.map(animation => animation.effect.getKeyframes().map(frame => frame.transform || frame.opacity));
        });
        assert.equal(keyframes.length, 1);
        assert.match(keyframes[0].at(-1), /rotate\\(360deg\\)/);
        """,
    )


def test_message_font_face_cannot_replace_the_app_font(shell_app, browser_node, spacing_sanitizer):
    # Local monospace faces avoid a remote request and differ in width from any UI font.
    # Direct embedding let this replace the app font in Chromium; WebKit resolves
    # -apple-system as the system font keyword, so only Chromium showed the effect.
    faces = 'local("Courier New"), local("Courier"), local("Liberation Mono"), local("DejaVu Sans Mono")'
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        f"<style>@font-face {{font-family:-apple-system; src:{faces}}}</style><p>Message copy</p>",
        """
        const widths = await page.evaluate(async faces => {
            const sender = document.querySelector('.ownmail-reader-sender');
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


def test_fixed_message_content_cannot_cover_reader_controls(shell_app, browser_node, spacing_sanitizer):
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        '<div style="position:fixed;inset:0;z-index:2147483647;background:rgb(255, 0, 0)">Cover</div>'
        "<p>Message copy</p>",
        CONTROL_WORKS,
    )


def test_message_popover_cannot_cover_reader_controls(shell_app, browser_node, spacing_sanitizer):
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        '<button id="show-cover" popovertarget="cover">Open</button>'
        '<div id="cover" popover style="position:fixed;inset:0;width:auto;height:auto;margin:0;'
        'background:rgb(255, 0, 0)">Cover</div>',
        """
        await message().locator('#show-cover').click();
        assert(await message().locator('#cover').evaluate(el => el.matches(':popover-open')));
        """
        + CONTROL_WORKS,
    )


def test_message_modal_dialog_cannot_cover_reader_controls(shell_app, browser_node, spacing_sanitizer):
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        '<button id="show-cover" commandfor="cover" command="show-modal">Open</button>'
        '<dialog id="cover" style="position:fixed;inset:0;width:auto;height:auto;max-width:none;max-height:none;'
        'margin:0;background:rgb(255, 0, 0)">Cover</dialog>',
        """
        await message().locator('#show-cover').click();
        assert(await message().locator('#cover').evaluate(el => el.open && el.matches(':modal')));
        """
        + CONTROL_WORKS,
    )


def test_message_images_cannot_shadow_frame_document_properties(shell_app, browser_node, spacing_sanitizer):
    # Reader scripts read fonts and scrollingElement from the frame document;
    # a shadowed fonts kept the message hidden.
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        '<img name="fonts" alt=""><img name="scrollingElement" alt=""><p>Message copy</p>',
        """
        await page.waitForSelector('#ownmail-email-frame[data-ready]', {state: 'attached', timeout: 3000});
        assert.equal(await page.evaluate(() => {
            const doc = document.getElementById('ownmail-email-frame').contentDocument;
            return [typeof doc.fonts.ready?.then, doc.scrollingElement === doc.documentElement].join();
        }), 'function,true');
        """,
    )


def test_message_property_registration_keeps_viewport_initial_values(shell_app, browser_node, spacing_sanitizer):
    run_probe(
        shell_app,
        browser_node,
        spacing_sanitizer,
        "<style>@property --probe {syntax:'<length>'; inherits:false; initial-value:10vh}</style>"
        '<div id="probe" style="height:var(--probe)"></div><p>Message copy</p>',
        """
        const [height, viewport] = await page.evaluate(() => {
            const frame = document.getElementById('ownmail-email-frame');
            return [frame.contentDocument.getElementById('probe').getBoundingClientRect().height,
                frame.contentDocument.documentElement.clientHeight];
        });
        assert(height > 0 && Math.abs(height - viewport / 10) <= 0.5, JSON.stringify([height, viewport]));
        """,
    )
