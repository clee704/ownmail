(function() {
    var storageKey = 'ownmail-result-position';
    var list = document.getElementById('ownmail-email-list');
    var backLink = document.getElementById('ownmail-back-to-results');

    function sameTabClick(event) {
        return !event.defaultPrevented && event.button === 0 &&
            !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
    }

    function readPosition() {
        try {
            return JSON.parse(sessionStorage.getItem(storageKey));
        } catch (error) {
            return null;
        }
    }

    function savePosition(position) {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify(position));
        } catch (error) {
            // Navigation still works when browser storage is unavailable.
        }
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
            if (previousLink) previousLink.focus({preventScroll: true});
            window.scrollTo(0, position.scrollY);
        }
        window.addEventListener('pageshow', restorePosition);
        // Unrelated resources can delay pageshow after the rows are ready.
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', restorePosition, {once: true});
        } else {
            restorePosition();
        }
    }

    if (backLink) {
        backLink.addEventListener('click', function(event) {
            if (!sameTabClick(event)) return;
            var position = readPosition();
            var destination = new URL(backLink.href);
            if (position && position.messagePath === location.pathname &&
                position.listUrl === destination.pathname + destination.search) {
                position.restore = true;
                savePosition(position);
            }
            showLoading(event);
        });
    }
})();
