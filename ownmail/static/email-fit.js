(function() {
    var viewport = document.getElementById('ownmail-email-viewport');
    var content = document.getElementById('ownmail-email-content');
    var fitButton = document.getElementById('ownmail-fit-message');
    var fitToWidth = viewport.dataset.autoScale === 'true';

    function scaleToFit() {
        // Measure the authored width before applying the reader's zoom.
        var scrollLeft = viewport.scrollLeft;
        content.style.zoom = '';
        content.style.overflow = 'visible';
        viewport.style.minHeight = '';
        viewport.style.overflow = 'clip visible';
        void content.offsetWidth;

        var cw = viewport.clientWidth;
        var sw = viewport.scrollWidth;
        var wide = sw > cw + 1 && cw > 0;
        fitButton.hidden = !wide;
        fitButton.textContent = fitToWidth ? 'Show actual size' : 'Fit to width';

        if (wide && fitToWidth) {
            var scale = cw / sw;
            content.style.zoom = scale;
        } else if (wide) {
            viewport.style.overflow = 'auto hidden';
        }

        // Reserve overflow space without changing sender percentage heights.
        if (viewport.scrollHeight > viewport.clientHeight) {
            var borderHeight = viewport.offsetHeight - viewport.clientHeight;
            viewport.style.minHeight = (viewport.scrollHeight + borderHeight) + 'px';
        }
        if (wide && !fitToWidth) viewport.scrollLeft = scrollLeft;
    }

    fitButton.addEventListener('click', function() {
        fitToWidth = !fitToWidth;
        scaleToFit();
    });
    scaleToFit();
    content.addEventListener('load', scaleToFit, true);
    window.addEventListener('load', scaleToFit);
    window.addEventListener('resize', scaleToFit);
    if (document.fonts) document.fonts.ready.then(scaleToFit);
})();
