(function() {
    var feedback = document.getElementById('ownmail-action-feedback');
    var message = document.getElementById('ownmail-action-message');
    var dismiss = document.getElementById('ownmail-action-dismiss');
    var pending = false;
    var noticeKey = 'ownmail-action-notice';
    var dismissTimer;

    function announce(text, state) {
        clearTimeout(dismissTimer);
        feedback.dataset.state = state;
        feedback.setAttribute('role', state === 'error' ? 'alert' : 'status');
        feedback.setAttribute('aria-live', state === 'error' ? 'assertive' : 'polite');
        message.textContent = text;
        dismiss.hidden = state === 'pending';
        feedback.hidden = false;
        if (state === 'success') {
            dismissTimer = setTimeout(function() { feedback.hidden = true; }, 4000);
        }
    }
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

    window.ownmailMessageAction = async function(action) {
        if (pending) return false;
        pending = true;
        var controls = Array.from(document.querySelectorAll('[data-message-action], .ownmail-email-checkbox input, #ownmail-select-all'));
        var previous = controls.map(function(control) { return control.disabled; });
        controls.forEach(function(control) { control.disabled = true; });
        announce(action.pending, 'pending');
        try {
            var response = await fetch(action.url, action.request);
            if (!response.ok) throw new Error('HTTP ' + response.status);
            announce(action.success, 'success');
            if (action.navigate) {
                try {
                    sessionStorage.setItem(noticeKey, JSON.stringify({message: action.success, created: Date.now()}));
                } catch (error) {}
                action.navigate();
            } else if (action.onSuccess) {
                await action.onSuccess(response);
            }
            return true;
        } catch (error) {
            announce(action.failure + ' Try the action again.', 'error');
            return false;
        } finally {
            pending = false;
            controls.forEach(function(control, index) { control.disabled = previous[index]; });
            if (typeof hideLoading === 'function') hideLoading();
        }
    };
})();
