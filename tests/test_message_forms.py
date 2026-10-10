"""Message forms and links through MIME parsing, sanitization, and browser clicks."""

from email.message import EmailMessage

from tests import test_email_contrast, test_reader_spacing

shell_app = test_email_contrast.shell_app
contrast_browser = test_email_contrast.contrast_browser
spacing_sanitizer = test_reader_spacing.spacing_sanitizer

MESSAGE = """<!doctype html><html><body>
<form method="post" action="/empty-trash"><button id="post-control">Read</button></form>
<form action="/search"><input id="get-field" name="q" value="synthetic">
    <input id="get-control" type="submit" value="Search"></form>
<form id="target" method="post" action="/empty-trash"></form>
<button id="attribute-control" form="target" formaction="/delete-forever" formmethod="post">Open</button>
</body></html>"""


LINKS = """<!doctype html><html><body>
<img id="map-image" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="80" height="40" usemap="#m" alt="Map">
<map name="m"><area href="https://x.invalid/area" shape="rect" coords="0,0,80,40" alt="Area"></map>
<p><a id="anchor-link" href="https://x.invalid/anchor">Anchor</a></p>
</body></html>"""


def reader_response(app, archive, sanitizer, body):
    app.config.update(sanitizer=sanitizer)
    message = EmailMessage()
    message["Subject"] = "Synthetic message"
    message["From"] = "Sender <sender@example.com>"
    message["To"] = "reader@example.com"
    message.set_content("Synthetic plain text alternative")
    message.add_alternative(body, subtype="html")
    (archive.archive_dir / "synthetic.eml").write_bytes(message.as_bytes())
    archive.db.get_email_by_id.return_value = (
        "synthetic",
        "synthetic.eml",
        "2024-01-01",
        "hash",
        "sender@example.com",
        None,
    )
    response = app.test_client().get("/email/synthetic")
    assert response.status_code == 200
    return response


def test_message_submit_controls_send_no_request(shell_app, contrast_browser, spacing_sanitizer):
    app, archive = shell_app
    response = reader_response(app, archive, spacing_sanitizer, MESSAGE)
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        """
        // A form with target=_blank submits in a popup, which page routes do not see.
        const sent = [];
        const popups = [];
        page.context().on('request', request => sent.push(request.method() + ' ' + request.url()));
        page.context().on('page', popup => popups.push(popup));
        await page.context().route('**/*', route => route.abort());
        const start = page.url();
        const actions = [
            ['#post-control', 'click'], ['#get-control', 'click'], ['#attribute-control', 'click'],
            ['#get-field', 'Enter'],
        ];
        for (const [control, action] of actions) {
            const target = page.locator(control);
            await (action === 'click' ? target.click({timeout: 2000}) : target.press(action, {timeout: 2000}));
            // Longer than the delay before the loading overlay appears.
            await page.waitForTimeout(400);
            assert.deepEqual(sent, [], control);
            assert.equal(popups.length, 0, control);
            assert.equal(page.url(), start, control);
            assert.equal(await page.locator('#ownmail-loading-overlay').getAttribute('class'),
                'ownmail-loading-overlay', control);
        }
        """,
        theme="light",
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )


def test_message_links_open_a_new_tab_without_a_referrer(shell_app, contrast_browser, spacing_sanitizer):
    app, archive = shell_app
    response = reader_response(app, archive, spacing_sanitizer, LINKS)
    test_email_contrast.run_contrast_browser(
        app,
        contrast_browser,
        "",
        "",
        """
        const opened = [];
        page.context().on('request', request => {
            if (new URL(request.url()).host === 'x.invalid') opened.push([request.url(), request.headers().referer]);
        });
        await page.context().route('**/*', route => route.abort());
        const start = page.url();
        // The image map's only area covers the whole image.
        for (const control of ['#map-image', '#anchor-link']) {
            const popup = page.context().waitForEvent('page', {timeout: 2000});
            await page.locator(control).click({timeout: 2000});
            await popup;
            assert.equal(page.url(), start, control);
        }
        assert.deepEqual(opened, [['https://x.invalid/area', undefined], ['https://x.invalid/anchor', undefined]]);
        """,
        theme="light",
        rendered_page=response.get_data(as_text=True),
        page_headers={"Content-Security-Policy": response.headers["Content-Security-Policy"]},
    )
