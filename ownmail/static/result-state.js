(function() {
    var storageKey = 'ownmail-result-position';
    var list = document.getElementById('ownmail-email-list');
    var backLink = document.getElementById('ownmail-back-to-results');

    function sameTabClick(event) {
        return !event.defaultPrevented && event.button === 0 &&
            !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
    }

    function readPosition(key) {
        try {
            return JSON.parse(sessionStorage.getItem(key || storageKey));
        } catch (error) {
            return null;
        }
    }

    function savePosition(position, key) {
        try {
            sessionStorage.setItem(key || storageKey, JSON.stringify(position));
        } catch (error) {
            // Navigation still works when browser storage is unavailable.
        }
    }

    // One session-only reader checkpoint: identity/version and offset, never mail.
    var readerKey = 'ownmail-reading-position';
    var reader = document.getElementById('ownmail-reader-actions');
    var readerUrl = location.pathname + location.search;
    var saved = readPosition(readerKey);
    if (document.getElementById('ownmail-reader-unavailable') && saved && saved.url === readerUrl) {
        try { sessionStorage.removeItem(readerKey); } catch (error) {}
    }
    if (reader && reader.dataset.readerVersion) {
        var version = reader.dataset.readerVersion;
        var moved = false;
        var restored = false;
        ['wheel', 'touchstart', 'pointerdown', 'keydown'].forEach(function(type) {
            window.addEventListener(type, function() { moved = true; }, {passive: true});
        });
        function saveReadingPosition() {
            savePosition({url: readerUrl, version: version, scrollY: window.scrollY}, readerKey);
        }
        window.addEventListener('pagehide', saveReadingPosition);
        document.addEventListener('visibilitychange', function() {
            if (document.visibilityState === 'hidden') saveReadingPosition();
        });
        window.addEventListener('pageshow', function(event) {
            if (restored || event.persisted) return;
            restored = true;
            var navigation = window.performance.getEntriesByType && window.performance.getEntriesByType('navigation')[0];
            if (!saved || saved.url !== readerUrl || saved.version !== version ||
                    !Number.isFinite(saved.scrollY) || saved.scrollY < 0 || location.hash ||
                    navigation && navigation.type === 'back_forward') return;
            // Run after the reader's load-time fit. Native restoration and user
            // movement win; never jump a reader that already has a position.
            window.requestAnimationFrame(function() {
                window.requestAnimationFrame(function() {
                    if (!moved && window.scrollY === 0) window.scrollTo(0, saved.scrollY);
                });
            });
        });
    }

    if (list) {
        list.addEventListener('click', function(event) {
            var link = event.target.closest('.ownmail-email-row-link');
            if (!link || !sameTabClick(event)) return;
            savePosition({
                listUrl: location.pathname + location.search,
                messagePath: new URL(link.href).pathname,
                scrollY: window.scrollY,
                restore: false
            });
            showLoading(event);
        });
        function restorePosition() {
            var position = readPosition();
            if (!position || position.listUrl !== location.pathname + location.search) return;
            try {
                sessionStorage.removeItem(storageKey);
            } catch (error) {
                return;
            }
            if (!position.restore) return;
            var links = list.querySelectorAll('.ownmail-email-row-link');
            var previousLink = Array.from(links).find(function(link) {
                return new URL(link.href).pathname === position.messagePath;
            });
            if (previousLink && position.restoreFocus) previousLink.focus({preventScroll: true});
            window.scrollTo(0, position.scrollY);
        }
        window.addEventListener('pageshow', restorePosition);
        restorePosition();
    }

    if (backLink) {
        backLink.addEventListener('click', function(event) {
            if (!sameTabClick(event)) return;
            var position = readPosition();
            var destination = new URL(backLink.href);
            if (position && position.messagePath === location.pathname &&
                position.listUrl === destination.pathname + destination.search) {
                position.restore = true;
                position.restoreFocus = event.detail === 0;
                savePosition(position);
            }
            showLoading(event);
        });
    }
})();
