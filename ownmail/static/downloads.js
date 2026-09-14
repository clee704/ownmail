(function() {
    var form = document.getElementById('ownmail-download-form');
    var start = document.getElementById('ownmail-download-now');
    var interval = document.getElementById('ownmail-download-interval');
    var save = document.getElementById('ownmail-download-save');
    var status = document.getElementById('ownmail-download-status');
    var message = document.getElementById('ownmail-download-message');
    var progress = document.getElementById('ownmail-download-progress');
    var counts = document.getElementById('ownmail-download-counts');
    var saved = document.getElementById('ownmail-download-saved');
    var error = document.getElementById('ownmail-download-error');
    var snapshot = JSON.parse(document.getElementById('ownmail-download-initial').textContent);
    var pending = false;
    var awaitingStatus = false;
    var scheduleDirty = false;
    var actionError = '';
    var pollError = '';
    var pollController;
    var pollTimer;

    function showDate(id, value) {
        var element = document.getElementById(id);
        var date = value && new Date(value);
        element.textContent = date && !isNaN(date.getTime()) ? date.toLocaleString() : '—';
    }

    function render() {
        start.disabled = pending || awaitingStatus || !snapshot.available || snapshot.running;
        start.textContent = snapshot.running ? 'Downloading…' : 'Download now';
        interval.disabled = pending || awaitingStatus || !snapshot.available;
        save.disabled = pending || awaitingStatus || !snapshot.available;
        if (!scheduleDirty) interval.value = String(snapshot.interval_minutes);
        var currentInterval = Array.from(interval.options).find(function(option) {
            return option.value === String(snapshot.interval_minutes);
        });
        document.getElementById('ownmail-download-current').textContent =
            'Current schedule: ' + (currentInterval ? currentInterval.textContent : 'Off') + '.';
        var messages = {
            idle: 'Ready to download.',
            running: 'Download in progress.',
            succeeded: 'Download finished.',
            failed: 'Download failed.',
            busy: 'Another download is already running.'
        };
        var text = snapshot.available ? messages[snapshot.state] :
            'Downloads are unavailable.';
        if (snapshot.running) {
            var phases = {
                starting: 'Starting download…',
                authenticating: snapshot.source ? 'Signing in to ' + snapshot.source + '…' : 'Signing in…',
                checking: snapshot.source ? 'Checking ' + snapshot.source + ' for new mail…' : 'Checking for new mail…',
                downloading: snapshot.source ? 'Downloading from ' + snapshot.source + '…' : 'Downloading…',
                finished: 'Finishing download…'
            };
            text = phases[snapshot.phase] || text;
        } else if (snapshot.failure_reason) {
            text = snapshot.failure_reason;
        } else if (snapshot.state === 'succeeded' && snapshot.has_progress && snapshot.downloaded === 0) {
            text = 'No new mail.';
        }
        if (message.textContent !== text) message.textContent = text;
        var totals = snapshot.has_progress ? snapshot.downloaded + ' downloaded · ' +
            snapshot.skipped + ' skipped · ' + snapshot.errors + ' failed' : '';
        if (counts.textContent !== totals) counts.textContent = totals;
        progress.hidden = !snapshot.has_progress;
        status.dataset.state = snapshot.state;
        showDate('ownmail-download-started', snapshot.started_at);
        showDate('ownmail-download-finished', snapshot.finished_at);
        showDate('ownmail-download-next', snapshot.next_run);
        var failure = actionError || pollError;
        if (error.textContent !== failure) error.textContent = failure;
        error.hidden = !failure;
    }

    function schedulePoll() {
        clearTimeout(pollTimer);
        if (!document.hidden) pollTimer = setTimeout(refresh, 3000);
    }

    async function refresh() {
        clearTimeout(pollTimer);
        if (document.hidden || pending || pollController) return;
        var controller = new AbortController();
        pollController = controller;
        var timeout = setTimeout(function() { controller.abort(); }, 15000);
        try {
            var response = await fetch('/downloads', {cache: 'no-store', signal: controller.signal});
            if (!response.ok) throw new Error('HTTP ' + response.status);
            var data = await response.json();
            if (pollController !== controller) return;
            snapshot = data;
            if (awaitingStatus) actionError = '';
            awaitingStatus = false;
            pollError = '';
        } catch (failure) {
            if (pollController !== controller) return;
            pollError = 'Cannot refresh download status. Retrying automatically…';
        } finally {
            clearTimeout(timeout);
            if (pollController === controller) {
                pollController = null;
                render();
                schedulePoll();
            }
        }
    }

    async function submit(url, body, isSchedule) {
        if (pending) return;
        pending = true;
        clearTimeout(pollTimer);
        if (pollController) {
            pollController.abort();
            pollController = null;
        }
        actionError = '';
        saved.hidden = true;
        render();
        var controller = new AbortController();
        var timeout = setTimeout(function() { controller.abort(); }, 15000);
        try {
            var response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
                signal: controller.signal
            });
            var data = await response.json();
            if (typeof data.available === 'boolean') snapshot = data;
            if (!response.ok && !(response.status === 409 && !isSchedule)) {
                actionError = data.error || (isSchedule ? 'Could not save the download schedule.' :
                    typeof data.available === 'boolean' ? '' : 'Could not start the download.');
            } else if (isSchedule) {
                scheduleDirty = false;
                saved.textContent = 'Download schedule saved.';
                saved.hidden = false;
            }
        } catch (failure) {
            awaitingStatus = true;
            actionError = isSchedule ? 'Could not confirm whether the schedule was saved. Checking its status…' :
                'Could not confirm whether the download started. Checking its status…';
        } finally {
            clearTimeout(timeout);
            pending = false;
            render();
            refresh();
        }
    }

    start.addEventListener('click', function() {
        if (!start.disabled) submit('/downloads', {}, false);
    });
    interval.addEventListener('change', function() {
        scheduleDirty = interval.value !== String(snapshot.interval_minutes);
        saved.hidden = true;
    });
    form.addEventListener('submit', function(event) {
        event.preventDefault();
        if (!save.disabled) submit('/downloads/schedule', {interval_minutes: Number(interval.value)}, true);
    });
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) clearTimeout(pollTimer);
        else refresh();
    });
    window.addEventListener('focus', refresh);
    window.addEventListener('pageshow', refresh);
    render();
    refresh();
})();
