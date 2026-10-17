(function() {
    var viewport = document.getElementById('ownmail-email-viewport');
    var frame = document.getElementById('ownmail-email-frame');
    var fitButton = document.getElementById('ownmail-fit-message');
    var fitToWidth = viewport.dataset.autoScale === 'true';
    // The frame cannot inherit custom properties, so the parent copies them.
    var mirrored = ['--ownmail-text', '--ownmail-accent-ink', '--ownmail-font', '--ownmail-message-padding'];
    // Message viewport units keep their reader meaning (see the sanitizer).
    var probe = document.createElement('div');
    probe.setAttribute('aria-hidden', 'true');
    probe.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; visibility: hidden; pointer-events: none;';
    document.body.appendChild(probe);
    var doc = null, content = null, callbacks = [], pending = false, settled = '';
    var sizes = new WeakMap(), faces = new WeakSet();

    function sync() {
        var root = doc.documentElement, style = getComputedStyle(frame);
        mirrored.forEach(function(name) { root.style.setProperty(name, style.getPropertyValue(name)); });
        var box = probe.getBoundingClientRect(), w = box.width / 100, h = box.height / 100;
        root.style.setProperty('--ownmail-vw', w + 'px');
        root.style.setProperty('--ownmail-vh', h + 'px');
        root.style.setProperty('--ownmail-vmin', Math.min(w, h) + 'px');
        root.style.setProperty('--ownmail-vmax', Math.max(w, h) + 'px');
    }

    function layout() {
        if (!doc) return;
        var root = doc.documentElement, scroller = doc.scrollingElement || root;
        var scrollLeft = viewport.scrollLeft;
        // Collapsing the frame below would otherwise clamp the page scroll position.
        viewport.style.minHeight = frame.offsetHeight + 'px';
        sync();
        content.style.zoom = '';
        doc.body.style.width = '';
        root.style.backgroundColor = '';
        frame.style.width = '';
        viewport.style.overflow = '';

        // Fit first: the height read below includes the zoom.
        var cw = scroller.clientWidth, sw = scroller.scrollWidth;
        // Message percentages resolve against the reader column, so a widened
        // frame shows their overflow instead of widening the message with it.
        // The frame's own widths round, and a rounded-up width would clip the message.
        doc.body.style.width = frame.getBoundingClientRect().width + 'px';
        // Any overflow would scroll inside the frame; the button needs a visible amount.
        var wide = sw > cw && cw > 0;
        fitButton.hidden = !(wide && sw > cw + 1);
        fitButton.textContent = fitToWidth ? 'Show actual size' : 'Fit to width';
        // The loop below corrects any overflow left after the zoom.
        if (wide && fitToWidth) content.style.zoom = cw / sw;
        // scrollWidth and scrollHeight round to the nearest pixel, hence the + 1.
        else if (wide) frame.style.width = (sw + 1) + 'px';

        // At zero height, content sized against the frame viewport cannot feed back.
        frame.style.height = '0px';
        var height = Math.ceil(root.getBoundingClientRect().height);
        // Positioned or transformed content overflows the root box.
        if (scroller.scrollHeight > height) height = scroller.scrollHeight + 1;
        frame.style.height = height + 'px';
        for (var pass = 0; pass < 4; pass++) {
            var overflow = scroller.scrollWidth - scroller.clientWidth;
            var overWidth = overflow > 0;
            var overHeight = scroller.scrollHeight > scroller.clientHeight;
            if (!overWidth && !overHeight) break;
            // WebKit keeps zoomed text at a minimum font size, so a smaller zoom
            // cannot fit a long word; only rounding overflow shrinks the zoom.
            if (overWidth && fitToWidth && overflow <= 2) {
                content.style.zoom = (Number(content.style.zoom) || 1) * scroller.clientWidth / (scroller.scrollWidth + 1);
            } else if (overWidth) {
                frame.style.width = (frame.offsetWidth + scroller.scrollWidth - scroller.clientWidth + 1) + 'px';
            }
            if (overHeight) frame.style.height = (scroller.scrollHeight + 1) + 'px';
        }
        if (frame.style.width) {
            // Overflow past the column lies on the root, which continues the
            // message background as a browser canvas continues a body's.
            // The content paints over the root inside the column, so only an
            // opaque color, serialized as rgb(), avoids painting it twice there.
            var background = getComputedStyle(content).backgroundColor;
            if (/^rgb\(/.test(background)) root.style.backgroundColor = background;
            viewport.style.overflow = 'auto hidden';
            viewport.scrollLeft = scrollLeft;
        }
        viewport.style.minHeight = '';
        // Overflow the passes above could not remove must not rerun them forever.
        settled = scroller.scrollWidth + 'x' + scroller.scrollHeight;
    }

    function schedule() {
        if (pending) return;
        pending = true;
        requestAnimationFrame(function() { pending = false; layout(); });
    }

    // Parent listeners on nodes in a frame without scripts never fire in
    // WebKit, so changes inside the frame are observed from here.
    var observer = window.ResizeObserver && new ResizeObserver(function(entries) {
        entries.forEach(function(entry) {
            var rect = entry.contentRect;
            // The layout sets the frame height itself; only its width is input.
            var size = entry.target === frame ? String(rect.width) : rect.width + ':' + rect.height;
            if (sizes.get(entry.target) === size) return;
            sizes.set(entry.target, size);
            schedule();
        });
    });

    // WebKit resolves the frame's fonts.ready while a face is still loading,
    // and its frame load event does not wait for fonts; each face's own
    // promise settles when its font arrives.
    function watchFonts() {
        if (!doc || !doc.fonts) return;
        doc.fonts.forEach(function(face) {
            if (faces.has(face)) return;
            faces.add(face);
            face.loaded.then(schedule, function() {});
        });
    }

    // Animations, transitions and :checked toggles can move positioned or
    // transformed content without resizing any observed box.
    function check() {
        if (document.hidden) return;
        var scroller = doc.scrollingElement || doc.documentElement;
        var over = scroller.scrollHeight > scroller.clientHeight || scroller.scrollWidth > scroller.clientWidth;
        if (over && scroller.scrollWidth + 'x' + scroller.scrollHeight !== settled) schedule();
    }

    function start(frameDocument) {
        doc = frameDocument;
        content = doc.getElementById('ownmail-email-content');
        layout();
        if (observer) {
            observer.observe(frame);
            observer.observe(content);
            Array.from(doc.images).forEach(function(image) { observer.observe(image); });
        }
        // A positioned details element opens without resizing any observed box;
        // the reader's toggle sets its open attribute.
        new MutationObserver(schedule).observe(content, {subtree: true, attributeFilter: ['open']});
        watchFonts();
        setInterval(check, 250);
        var waiting = callbacks;
        callbacks = null;
        waiting.forEach(function(callback) { callback(); });
        // Shown only after the first theme sync, so dark mode has no light flash.
        frame.dataset.ready = '';
    }

    // At script time contentDocument is still the initial about:blank.
    function poll() {
        if (doc) return;
        var current = frame.contentDocument;
        if (current && current.URL === 'about:srcdoc' && current.readyState !== 'loading') start(current);
        else requestAnimationFrame(poll);
    }

    fitButton.addEventListener('click', function() {
        fitToWidth = !fitToWidth;
        layout();
    });
    // Load fires after the frame's images and stylesheet.
    frame.addEventListener('load', function() {
        poll();
        watchFonts();
        layout();
    });
    window.addEventListener('resize', layout);
    window.ownmailMessageFrame = {
        ready: function(callback) {
            if (callbacks) callbacks.push(callback);
            else callback();
        },
        layout: layout
    };
    poll();
})();
