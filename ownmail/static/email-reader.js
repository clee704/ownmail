document.getElementById('ownmail-message-details-toggle').addEventListener('click', function() {
    var expanded = this.getAttribute('aria-expanded') !== 'true';
    this.setAttribute('aria-expanded', String(expanded));
    this.title = expanded ? 'Hide message details' : 'Show message details';
    document.getElementById('ownmail-message-metadata').hidden = !expanded;
});

(function() {
    var toggle = document.getElementById('ownmail-reader-actions').querySelector('#ownmail-active-status-toggle');
    if (!toggle) return;
    var panel = document.getElementById('ownmail-active-status');
    var menu = toggle.closest('details');
    toggle.addEventListener('click', function() {
        panel.hidden = false;
        toggle.setAttribute('aria-expanded', 'true');
        menu.open = false;
        panel.focus();
    });
    function closeStatus() {
        panel.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
        menu.querySelector('summary').focus();
    }
    document.getElementById('ownmail-active-status-close').addEventListener('click', closeStatus);
    panel.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            closeStatus();
        }
    });
})();

var originalEmailMedia = new WeakMap();
// Rewriting style text would let the browser re-parse sender strings as new
// rules. A media rule's condition parses only as a media query list.
// MediaRule is the frame realm's constructor: instanceof fails across realms.
function applyEmailMediaTheme(rules, dark, MediaRule) {
    for (var i = 0; i < rules.length; i++) {
        var rule = rules[i];
        if (rule instanceof MediaRule) {
            if (!originalEmailMedia.has(rule)) originalEmailMedia.set(rule, rule.media.mediaText);
            var original = originalEmailMedia.get(rule);
            // Width is never negative, so these conditions are constant and
            // keep any other condition in the query.
            var updated = original.replace(/\(\s*prefers-color-scheme\s*:\s*dark\s*\)/gi,
                dark ? '(width >= 0px)' : '(width < 0px)');
            if (rule.media.mediaText !== updated) rule.media.mediaText = updated;
        }
        if (rule.cssRules) applyEmailMediaTheme(rule.cssRules, dark, MediaRule);
    }
}
function applyEmailTheme(siteIsDark) {
    var area = document.querySelector('.ownmail-email-content-area');
    if (!area) return;
    var dark = siteIsDark && area.getAttribute('data-supports-dark') === 'true';
    area.classList.toggle('ownmail-email-dark', dark);

    var frame = document.getElementById('ownmail-email-frame');
    var content = frame && frame.contentDocument.getElementById('ownmail-email-content');
    if (!content) return;
    // The frame root's color scheme must match the iframe element's, or the
    // browser paints an opaque backdrop behind the message.
    var root = content.ownerDocument.documentElement;
    root.classList.toggle('ownmail-dark', document.documentElement.classList.contains('ownmail-dark'));
    root.classList.toggle('ownmail-email-dark', dark);
    // Sender dark-mode rules follow the reader canvas, not the OS preference.
    var styles = content.querySelectorAll('style');
    for (var i = 0; i < styles.length; i++) {
        if (styles[i].sheet) applyEmailMediaTheme(styles[i].sheet.cssRules, dark, frame.contentWindow.CSSMediaRule);
    }
    window.ownmailMessageFrame.layout();
}
var emailContrast = null;
// Called by base.html whenever the app theme changes.
function updateEmailDarkMode(siteIsDark) {
    if (emailContrast) emailContrast.update(siteIsDark);
    else applyEmailTheme(siteIsDark);
}
function startEmailTheme(content) {
    emailContrast = window.ownmailEmailContrast && window.ownmailEmailContrast(content, applyEmailTheme);
    var pref = localStorage.getItem('ownmail-theme') || 'auto';
    var dark = pref === 'dark' || (pref === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    updateEmailDarkMode(dark);
}
if (window.ownmailMessageFrame) {
    window.ownmailMessageFrame.ready(function() {
        startEmailTheme(document.getElementById('ownmail-email-frame').contentDocument.getElementById('ownmail-email-content'));
    });
} else {
    startEmailTheme(document.getElementById('ownmail-email-content'));
}

// Neither Chromium nor WebKit passes Space or Shift+Space from a frame to its
// parent, and WebKit never runs parent listeners on nodes in the script-less
// frame, so the key cannot be forwarded. After a plain click in the message,
// focus returns to the viewport once the button is up. Focus stays in the frame
// while it holds a text selection (native copy) or a keyboard-focused link, and
// after Tab moves it there: returning it would make the next Tab enter the frame
// again, so a message without Tab stops would trap keyboard users.
(function() {
    var frame = document.getElementById('ownmail-email-frame');
    if (!frame) return;
    var viewport = document.getElementById('ownmail-email-viewport');
    var pending = false;
    var tabbing = false;
    // Where the frame selection was when Tab moved focus in; a click moves it.
    var tabbed = null;
    function check() {
        pending = false;
        if (document.activeElement !== frame) return;
        var doc = frame.contentDocument;
        // During a press, check every frame so Space works right after mouseup.
        if (frame.matches(':active')) return schedule(true);
        var focused = doc && doc.activeElement;
        var selection = doc && doc.getSelection();
        var held = !doc || !selection.isCollapsed
            || (focused && focused !== doc.body && focused.matches(':focus-visible'))
            || (tabbed && tabbed.node === selection.anchorNode && tabbed.offset === selection.anchorOffset);
        // A selection can stay for minutes; a slow poll still notices the
        // plain click that collapses it, which fires no parent event.
        if (held) schedule(false);
        else viewport.focus({preventScroll: true});
    }
    function schedule(soon) {
        if (pending) return;
        pending = true;
        if (soon) requestAnimationFrame(check);
        else setTimeout(check, 150);
    }
    // Tab moves focus during its keydown, so the blur below fires before the timeout.
    document.addEventListener('keydown', function(event) {
        if (event.key !== 'Tab') return;
        tabbing = true;
        setTimeout(function() { tabbing = false; });
    }, true);
    // The parent window blurs whenever focus moves into the frame.
    window.addEventListener('blur', function() {
        var selection = tabbing && frame.contentDocument && frame.contentDocument.getSelection();
        tabbed = selection ? {node: selection.anchorNode, offset: selection.anchorOffset} : null;
        schedule(true);
    });
})();

function trashEmail(emailId) {
    if (!confirm('Move this email to trash?')) return;
    ownmailMessageAction({
        url: '/trash/' + emailId,
        request: {method: 'POST'},
        pending: 'Moving message to trash…',
        success: 'Message moved to trash.',
        failure: 'Could not move this message to trash.',
        navigate: function() { document.getElementById('ownmail-back-to-results').click(); }
    });
}
function restoreEmail(emailId) {
    ownmailMessageAction({
        url: '/restore/' + emailId,
        request: {method: 'POST'},
        pending: 'Restoring message…',
        success: 'Message restored from trash.',
        failure: 'Could not restore this message.',
        navigate: function() { location.href = location.href; }
    });
}
function deleteForever(emailId) {
    if (!confirm('Permanently delete this email? This cannot be undone.')) return;
    ownmailMessageAction({
        url: '/delete-forever',
        request: {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'ids=' + encodeURIComponent(emailId)},
        pending: 'Deleting message forever…',
        success: 'Message deleted forever.',
        failure: 'Could not delete this message forever.',
        navigate: function() { window.location.href = '/trash'; }
    });
}

// These containers precede and exclude the untrusted message body.
(function() {
    var actions = document.getElementById('ownmail-reader-actions');
    var handlers = {trash: trashEmail, restore: restoreEmail, 'delete-forever': deleteForever};
    actions.querySelectorAll('[data-reader-action]').forEach(function(button) {
        var handler = handlers[button.dataset.readerAction];
        if (handler) button.addEventListener('click', function() { handler(actions.dataset.emailId); });
    });
    var header = document.querySelector('.ownmail-email-detail > .ownmail-email-header');
    header.querySelectorAll('[data-show-loading]').forEach(function(link) {
        link.addEventListener('click', function(event) { showLoading(event); });
    });
})();
