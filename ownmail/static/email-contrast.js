(function () {
    'use strict';

    var MAX_ELEMENTS = 2500;
    var MAX_TEXT_NODES = 1500;
    var PAINT = ['color', 'backgroundColor', 'backgroundImage', 'borderTopColor',
        'borderRightColor', 'borderBottomColor', 'borderLeftColor', 'outlineColor',
        'boxShadow', 'textShadow', 'textDecorationColor', 'textDecorationLine', 'fill', 'stroke',
        'opacity', 'visibility', 'filter', 'backdropFilter', 'maskImage', 'clip', 'clipPath',
        'mixBlendMode', 'transform', 'animationName', 'transitionDuration', 'webkitTextFillColor',
        'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing', 'lineHeight'];

    function rgb(value) {
        var match = /^rgba?\(\s*([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)$/.exec(value);
        if (!match) return null;
        return [Number(match[1]), Number(match[2]), Number(match[3]), match[4] === undefined ? 1 : Number(match[4])];
    }

    function contrast(first, second) {
        function luminance(color) {
            var channels = color.slice(0, 3).map(function (value) {
                value /= 255;
                return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
            });
            return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
        }
        var a = luminance(first), b = luminance(second);
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    }

    function box(rect) { return [rect.x, rect.y, rect.width, rect.height]; }
    function sameBox(a, b) { return a.every(function (value, i) { return Math.abs(value - b[i]) <= 0.5; }); }
    function contains(outer, inner) {
        return inner.left >= outer.left - 0.5 && inner.right <= outer.right + 0.5 &&
            inner.top >= outer.top - 0.5 && inner.bottom <= outer.bottom + 0.5;
    }
    function overlaps(a, b) {
        return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    }

    window.ownmailEmailContrast = function (content, applyTheme) {
        if (!content) return null;
        var dark = false;
        var timer = null;
        var repairs = new Map();
        var resources = /url\s*\(|image-set\s*\(|@import\b|@font-face\b|\\/i;
        var originalHasResources = Array.from(content.querySelectorAll('style')).some(function (el) {
            return resources.test(el.textContent);
        });

        function reset() {
            repairs.forEach(function (wrapper, node) {
                if (node.parentNode === wrapper && wrapper.parentNode) wrapper.replaceWith(node);
            });
            repairs.clear();
        }

        function collect() {
            var elements = [content];
            var walker = document.createTreeWalker(content, NodeFilter.SHOW_ELEMENT);
            var node;
            while ((node = walker.nextNode())) {
                if (elements.length >= MAX_ELEMENTS) return null;
                elements.push(node);
            }
            var texts = [];
            walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
            while ((node = walker.nextNode())) {
                if (texts.length >= MAX_TEXT_NODES) return null;
                if (!/^(STYLE|SCRIPT|TITLE)$/.test(node.parentElement.tagName) && /[\p{L}\p{N}]/u.test(node.data)) texts.push(node);
            }
            return { elements: elements, texts: texts };
        }

        function canProbe(elements) {
            // Probing a different stylesheet can fetch otherwise unused assets.
            return !originalHasResources && !elements.some(function (el) {
                return el.tagName === 'LINK' || el.getAttribute('loading') === 'lazy' ||
                    resources.test(el.getAttribute('style') || '') ||
                    (el.tagName === 'STYLE' && resources.test(el.textContent));
            });
        }

        function measure(items) {
            var cache = new Map(), rows = new Map(), paint = new Map();
            function info(el) {
                if (!cache.has(el)) {
                    var style = getComputedStyle(el);
                    var pseudo = ['::before', '::after'].some(function (which) {
                        var s = getComputedStyle(el, which);
                        return s.display !== 'none' && s.content !== 'none' && s.content !== 'normal' && s.content !== '';
                    });
                    cache.set(el, { style: style, rect: el.getBoundingClientRect(), pseudo: pseudo });
                }
                return cache.get(el);
            }
            var obstacles = [], hasColumns = false;
            items.elements.forEach(function (el) {
                var data = info(el), s = data.style;
                if (/^table-column/.test(s.display)) hasColumns = true;
                paint.set(el, { values: PAINT.map(function (name) { return s[name]; }), box: box(data.rect) });
                if (s.display !== 'none' && s.visibility === 'visible' && Number(s.opacity) > 0 &&
                    (data.pseudo || s.backgroundImage !== 'none' || s.boxShadow !== 'none' ||
                        (rgb(s.backgroundColor) || [0, 0, 0, 1])[3] > 0 ||
                        /^(absolute|fixed|sticky)$/.test(s.position) || /^(IMG|SVG|VIDEO|CANVAS)$/.test(el.tagName))) {
                    obstacles.push(el);
                }
            });
            items.texts.forEach(function (node) {
                var el = node.parentElement;
                if (!content.contains(el) || el.closest('[hidden], [aria-hidden="true"], [aria-disabled="true"], [disabled]')) return;
                var s = info(el).style, foreground = rgb(s.color);
                if (!foreground || foreground[3] !== 1 || parseFloat(s.fontSize) < 4 ||
                    s.textShadow !== 'none' || parseFloat(s.webkitTextStrokeWidth || '0') > 0 ||
                    (s.webkitTextFillColor && s.webkitTextFillColor !== s.color)) return;
                var range = document.createRange();
                range.selectNodeContents(node);
                var rect = range.getBoundingClientRect();
                if (rect.width < 1 || rect.height < 2 || rect.right <= 0 || rect.bottom <= 0) return;
                var background = null, surface = null, ancestor = el, depth = 0;
                while (ancestor) {
                    if (++depth > 50) return;
                    var data = info(ancestor), style = data.style;
                    if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) !== 1 ||
                        style.filter !== 'none' || (style.backdropFilter && style.backdropFilter !== 'none') ||
                        style.mixBlendMode !== 'normal' || style.transform !== 'none' || style.clipPath !== 'none' ||
                        style.boxShadow !== 'none' || (style.maskImage && style.maskImage !== 'none') ||
                        style.clip !== 'auto' || style.animationName !== 'none' ||
                        style.transitionDuration.split(',').some(function (v) { return parseFloat(v) > 0; }) ||
                        data.pseudo || /^(absolute|fixed|sticky)$/.test(style.position)) return;
                    if ((/hidden|clip|scroll|auto/.test(style.overflowY) &&
                        (rect.top < data.rect.top - 0.5 || rect.bottom > data.rect.bottom + 0.5)) ||
                        (/hidden|clip|scroll|auto/.test(style.overflowX) &&
                        (rect.left < data.rect.left - 0.5 || rect.right > data.rect.right + 0.5))) return;
                    if (!background) {
                        // Column layers are outside the ancestor chain; transparent layout tables are not.
                        if ((hasColumns && /^(table|inline-table)$/.test(style.display)) || style.backgroundImage !== 'none' ||
                            style.backgroundBlendMode !== 'normal' || style.backgroundClip !== 'border-box') return;
                        var candidate = rgb(style.backgroundColor);
                        if (!candidate || (candidate[3] > 0 && candidate[3] !== 1)) return;
                        if (candidate[3] === 1) { background = candidate; surface = ancestor; }
                    }
                    ancestor = ancestor.parentElement;
                }
                if (!background || !contains(info(surface).rect, rect)) return;
                if (obstacles.some(function (other) {
                    return !other.contains(el) && overlaps(info(other).rect, rect);
                })) return;
                rows.set(node, { color: s.color, background: background.join(','), surface: surface,
                    contrast: contrast(foreground, background), box: box(rect) });
            });
            return { rows: rows, paint: paint };
        }

        function run() {
            reset();
            applyTheme(dark);
            if (!dark || !content.classList.contains('ownmail-email-content-html')) return;
            var items = collect();
            if (!items || !canProbe(items.elements)) return;
            var native = measure(items);
            if (!Array.from(native.rows.values()).some(function (row) { return row.contrast <= 1.5; })) return;
            var base;
            try {
                applyTheme(false);
                base = measure(items);
            } finally {
                // Both measurements finish in the same task, before the next paint.
                applyTheme(true);
            }
            var candidates = new Map();
            native.rows.forEach(function (row, node) {
                var original = base.rows.get(node);
                if (original && original.contrast >= 4.5 && row.contrast <= 1.5 && original.color !== row.color &&
                    original.background === row.background && original.surface === row.surface && sameBox(original.box, row.box)) {
                    candidates.set(node, original);
                }
            });
            candidates.forEach(function (original, node) {
                // A parent color override would also change links and currentColor decoration.
                var wrapper = document.createElement('span');
                wrapper.style.cssText = 'all: unset !important; color: ' + original.color + ' !important;';
                node.replaceWith(wrapper);
                wrapper.appendChild(node);
                repairs.set(node, wrapper);
            });
            if (!repairs.size) return;
            var after = measure(items);
            var safe = true;
            native.paint.forEach(function (before, el) {
                var current = after.paint.get(el);
                if (!sameBox(before.box, current.box) || before.values.some(function (value, i) { return value !== current.values[i]; })) safe = false;
            });
            native.rows.forEach(function (before, node) {
                var current = after.rows.get(node), original = candidates.get(node);
                if (!current || !sameBox(before.box, current.box) || before.background !== current.background ||
                    (original ? current.color !== original.color || current.contrast < 4.5 : before.color !== current.color)) safe = false;
            });
            // Sender selectors may react to inserted spans; keep the original if they do.
            if (!safe) reset();
        }

        function refresh() {
            if (!dark) return;
            clearTimeout(timer);
            timer = setTimeout(function () { timer = null; run(); }, 80);
        }
        function imageChanged(event) {
            // Rewriting a style element also fires load; it must not restart the probe.
            if (event.target.tagName === 'IMG') refresh();
        }
        content.addEventListener('load', imageChanged, true);
        content.addEventListener('error', imageChanged, true);
        content.addEventListener('ownmail-images-changed', refresh);
        window.addEventListener('resize', refresh);
        if (document.fonts) document.fonts.ready.then(refresh);
        if (window.ResizeObserver) {
            var lastSize = '';
            new ResizeObserver(function (entries) {
                var rect = entries[0].contentRect, size = rect.width + ':' + rect.height;
                if (size !== lastSize) { lastSize = size; refresh(); }
            }).observe(content);
        }
        return { update: function (isDark) {
            clearTimeout(timer);
            dark = isDark;
            run();
        } };
    };
})();
