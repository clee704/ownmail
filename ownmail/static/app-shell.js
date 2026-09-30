(function() {
    var input = document.getElementById('search-input');
    var clear = document.getElementById('ownmail-search-clear');
    clear.addEventListener('mousedown', function(event) {
        // Keep the mobile keyboard open while clearing the field.
        event.preventDefault();
    });
    clear.addEventListener('click', function() {
        input.value = '';
        input.focus({preventScroll: true});
        input.dispatchEvent(new Event('input', {bubbles: true}));
    });
})();
applyTheme();

var sidebar = document.getElementById('ownmail-sidebar');
var sidebarToggle = document.getElementById('ownmail-sidebar-toggle');
sidebarToggle.addEventListener('click', toggleSidebar);
document.getElementById('ownmail-nav-backdrop').addEventListener('click', closeMobileNavigation);
sidebar.querySelectorAll('a[href]').forEach(function(link) {
    link.addEventListener('click', showLoading);
});
var navigationBreakpoint = window.matchMedia('(max-width: 900px)');
function syncNavigation() {
    var mobile = navigationBreakpoint.matches;
    var open = mobile && document.body.classList.contains('ownmail-nav-open');
    var collapsed = !mobile && localStorage.getItem('ownmail-sidebar') === 'collapsed';
    sidebar.classList.toggle('collapsed', collapsed);
    document.body.classList.toggle('ownmail-sidebar-collapsed', collapsed);
    sidebar.inert = mobile && !open;
    if (mobile && !open) sidebar.setAttribute('aria-hidden', 'true');
    else sidebar.removeAttribute('aria-hidden');
    document.getElementById('ownmail-nav-backdrop').hidden = !open;
    document.getElementById('ownmail-main').inert = open;
    document.querySelector('.ownmail-header-search').inert = open;
    sidebarToggle.setAttribute('aria-expanded', String(mobile ? open : !collapsed));
    var label = mobile ? (open ? 'Close navigation' : 'Open navigation') : (collapsed ? 'Expand navigation' : 'Collapse navigation');
    sidebarToggle.setAttribute('aria-label', label);
    sidebarToggle.title = label;
}
function closeMobileNavigation() {
    document.body.classList.remove('ownmail-nav-open');
    syncNavigation();
    sidebarToggle.focus();
}
function toggleSidebar() {
    if (navigationBreakpoint.matches) {
        var open = document.body.classList.toggle('ownmail-nav-open');
        syncNavigation();
        if (open) (sidebar.querySelector('[aria-current="page"]') || sidebar.querySelector('a')).focus();
    } else {
        localStorage.setItem('ownmail-sidebar', sidebar.classList.contains('collapsed') ? 'expanded' : 'collapsed');
        syncNavigation();
    }
}
navigationBreakpoint.addEventListener('change', function() {
    var focusWasInSidebar = sidebar.contains(document.activeElement);
    document.body.classList.remove('ownmail-nav-open');
    syncNavigation();
    if (navigationBreakpoint.matches && focusWasInSidebar) {
        (document.getElementById('ownmail-back-to-results') || sidebarToggle).focus({preventScroll: true});
    }
});
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape' && document.body.classList.contains('ownmail-nav-open')) {
        event.preventDefault();
        closeMobileNavigation();
    }
    if (event.key === 'Tab' && navigationBreakpoint.matches && document.body.classList.contains('ownmail-nav-open')) {
        var links = Array.from(sidebar.querySelectorAll('a'));
        var first = sidebarToggle;
        var last = links[links.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }
});
syncNavigation();
document.addEventListener('click', function(event) {
    document.querySelectorAll('.ownmail-email-menu[open]').forEach(function(menu) {
        if (!menu.contains(event.target) || event.target.closest('button, a')) {
            menu.open = false;
            if (menu.contains(event.target)) menu.querySelector('summary').focus();
        }
    });
});
document.addEventListener('keydown', function(event) {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('.ownmail-email-menu[open]').forEach(function(menu) {
        menu.open = false;
        menu.querySelector('summary').focus();
    });
});
var loadingTimer = null;
var loadingDeadline = null;
var loadingUrl = null;
var loadingRow = null;
var loadingOverlay = document.getElementById('ownmail-loading-overlay');
var loadingStatus = document.getElementById('ownmail-loading-status');
function showLoading(event) {
    if (event && (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
            (event.button !== undefined && event.button !== 0))) {
        return;
    }
    var link = event && event.target && event.target.closest && event.target.closest('.ownmail-email-row-link');
    var row = link ? link.closest('.ownmail-email-row') : null;
    var retryUrl = location.href;
    var target = event && event.target && event.target.closest && event.target.closest('a[href], form');
    if (target) {
        var destination = new URL(target.tagName === 'FORM' ? target.action : target.href, location.href);
        if (destination.origin === location.origin) {
            if (target.tagName !== 'FORM') retryUrl = destination.href;
            else if (target.method.toLowerCase() === 'get') {
                destination.search = new URLSearchParams(new FormData(target)).toString();
                retryUrl = destination.href;
            }
        }
    }
    if (retryUrl === loadingUrl && row === loadingRow && (loadingTimer !== null ||
            (row ? row.classList.contains('ownmail-loading') : loadingOverlay.classList.contains('ownmail-active')))) return;
    hideLoading();
    loadingRow = row;
    loadingUrl = retryUrl;
    loadingDeadline = setTimeout(function() {
        window.stop();
        hideLoading();
        window.ownmailConnectionError('Could not open this page. Check the server connection and retry.', retryUrl);
    }, 30000);
    // Keep native navigation immediate; fast responses need no feedback.
    loadingTimer = setTimeout(function() {
        loadingTimer = null;
        if (loadingRow) {
            loadingRow.classList.add('ownmail-loading');
            loadingStatus.textContent = 'Opening message';
        } else {
            loadingOverlay.classList.add('ownmail-active');
        }
    }, 200);
}
function hideLoading() {
    clearTimeout(loadingDeadline);
    loadingDeadline = null;
    loadingUrl = null;
    clearTimeout(loadingTimer);
    loadingTimer = null;
    if (loadingRow) loadingRow.classList.remove('ownmail-loading');
    loadingRow = null;
    loadingStatus.textContent = '';
    loadingOverlay.classList.remove('ownmail-active');
}
window.addEventListener('pagehide', hideLoading);
window.addEventListener('pageshow', hideLoading);
window.addEventListener('load', hideLoading);
document.addEventListener('keydown', function(event) {
    if (event.key !== 'Escape' || event.defaultPrevented) return;
    if (loadingRow) window.stop();
    hideLoading();
});
document.addEventListener('click', function(event) {
    if (!loadingRow || event.defaultPrevented || event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    var link = event.target.closest('a[href]');
    if (!link || loadingRow.contains(link) && link.classList.contains('ownmail-email-row-link') ||
            link.hasAttribute('download') || link.target && link.target !== '_self') return;
    var destination = new URL(link.href);
    if (destination.protocol !== 'http:' && destination.protocol !== 'https:') return;
    // In-page links and separate controls do not replace the pending page.
    if (destination.origin === location.origin && destination.pathname === location.pathname &&
            destination.search === location.search && destination.hash) return;
    hideLoading();
});
// Show loading on form submit (skip if onsubmit handler cancelled it)
document.querySelectorAll('form').forEach(function(form) {
    form.addEventListener('submit', function(e) {
        if (!e.defaultPrevented) showLoading(e);
    });
});
// Show loading on pagination click
document.querySelectorAll('.ownmail-pagination a').forEach(function(link) {
    link.addEventListener('click', function(e) {
        showLoading(e);
    });
});
