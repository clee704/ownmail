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

var originalEmailStyles = new WeakMap();
function applyEmailTheme(siteIsDark) {
    var area = document.querySelector('.ownmail-email-content-area');
    if (!area) return;
    var supportsDark = area.getAttribute('data-supports-dark') === 'true';
    area.classList.toggle('ownmail-email-dark', siteIsDark && supportsDark);

    // Override @media (prefers-color-scheme: dark) blocks in email CSS
    // so they follow the ownmail theme, not the OS preference.
    if (!supportsDark) return;
    var content = document.getElementById('ownmail-email-content');
    if (!content) return;
    var styles = content.querySelectorAll('style');
    for (var i = 0; i < styles.length; i++) {
        var el = styles[i];
        // Save original CSS on first call
        if (!originalEmailStyles.has(el)) originalEmailStyles.set(el, el.textContent);
        var original = originalEmailStyles.get(el);
        if (original.indexOf('prefers-color-scheme') === -1) continue;
        var updated;
        if (siteIsDark) {
            // Dark mode: unwrap @media dark blocks so rules always apply
            updated = original.replace(
                /@media[^{]*prefers-color-scheme\s*:\s*dark[^{]*\{((?:[^{}]*\{[^{}]*\})*[^{}]*)\}/gi,
                '$1'
            );
        } else {
            // Light mode: remove @media dark blocks entirely
            updated = original.replace(
                /@media[^{]*prefers-color-scheme\s*:\s*dark[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/gi,
                ''
            );
        }
        if (el.textContent !== updated) el.textContent = updated;
    }
}
var emailContrast = window.ownmailEmailContrast && window.ownmailEmailContrast(
    document.getElementById('ownmail-email-content'), applyEmailTheme
);
// Called by base.html whenever the app theme changes.
function updateEmailDarkMode(siteIsDark) {
    if (emailContrast) emailContrast.update(siteIsDark);
    else applyEmailTheme(siteIsDark);
}
// Apply on load
(function() {
    var pref = localStorage.getItem('ownmail-theme') || 'auto';
    var dark = pref === 'dark' || (pref === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    updateEmailDarkMode(dark);
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
