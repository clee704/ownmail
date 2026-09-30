(function() {
    var feedback = document.getElementById('ownmail-action-feedback');
    var message = document.getElementById('ownmail-action-message');
    var retry = document.getElementById('ownmail-action-retry');
    var dismiss = document.getElementById('ownmail-action-dismiss');
    var pending = false;
    var noticeKey = 'ownmail-action-notice';
    var dismissTimer;

    function announce(text, state, retryUrl) {
        clearTimeout(dismissTimer);
        feedback.dataset.state = state;
        feedback.setAttribute('role', state === 'error' ? 'alert' : 'status');
        feedback.setAttribute('aria-live', state === 'error' ? 'assertive' : 'polite');
        message.textContent = text;
        dismiss.hidden = state === 'pending';
        retry.hidden = !retryUrl;
        if (retryUrl) retry.href = retryUrl;
        feedback.hidden = false;
        if (state === 'success') {
            dismissTimer = setTimeout(function() { feedback.hidden = true; }, 4000);
        }
    }
    retry.addEventListener('click', function(event) {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        feedback.hidden = true;
        if (typeof showLoading === 'function') showLoading(event);
        if (retry.pathname === location.pathname && retry.search === location.search) {
            // A same-document fragment link would not contact the server.
            event.preventDefault();
            location.reload();
        }
    });
    dismiss.addEventListener('click', function() {
        clearTimeout(dismissTimer);
        feedback.hidden = true;
    });

    // Carry confirmed feedback through the action's existing redirect or reload.
    try {
        var notice = JSON.parse(sessionStorage.getItem(noticeKey) || 'null');
        sessionStorage.removeItem(noticeKey);
        if (notice && typeof notice.message === 'string' && Date.now() - notice.created < 60000) {
            announce(notice.message, 'success');
        }
    } catch (error) {}

    // Retry is an explicit GET, never an automatic repeat of a mutation.
    window.ownmailConnectionError = function(text, url) {
        announce(text, 'error', url || location.href);
    };

    // Bound the entire response, including JSON decoding. A late response cannot
    // announce success after the deadline, even when abort is slow to settle.
    window.ownmailRequest = async function(url, options, json) {
        var controller = new AbortController();
        var timer;
        try {
            return await Promise.race([
                (async function() {
                    var response = await fetch(url, Object.assign({}, options, {signal: controller.signal}));
                    var data = json ? await response.json() : response;
                    if (!response.ok) throw new Error(json && data && data.error || 'HTTP ' + response.status);
                    return data;
                })(),
                new Promise(function(resolve, reject) {
                    timer = setTimeout(function() {
                        controller.abort();
                        reject(new Error('The server did not respond in time.'));
                    }, 30000);
                })
            ]);
        } finally {
            clearTimeout(timer);
        }
    };

    window.ownmailMessageAction = async function(action) {
        if (pending) return false;
        pending = true;
        var controls = Array.from(document.querySelectorAll('[data-message-action], .ownmail-email-checkbox input, #ownmail-select-all'));
        var previous = controls.map(function(control) { return control.disabled; });
        controls.forEach(function(control) { control.disabled = true; });
        announce(action.pending, 'pending');
        try {
            var response = await window.ownmailRequest(action.url, action.request, action.json);
            if (action.onSuccess) await action.onSuccess(response);
            announce(action.success, 'success');
            if (action.navigate) {
                try {
                    sessionStorage.setItem(noticeKey, JSON.stringify({message: action.success, created: Date.now()}));
                } catch (error) {}
                action.navigate();
            }
            return true;
        } catch (error) {
            window.ownmailConnectionError(action.failure + ' Reload to check the current state. Try the action again.');
            return false;
        } finally {
            pending = false;
            controls.forEach(function(control, index) { control.disabled = previous[index]; });
        }
    };
})();
