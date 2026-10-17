(function() {
    // Send requests only to this message's labels route.
    var actions = document.getElementById('ownmail-reader-actions');
    var trigger = actions.querySelector('#ownmail-edit-labels');
    var editor = document.getElementById('ownmail-label-editor');
    if (!trigger || !editor) return;
    var url = '/labels/' + encodeURIComponent(actions.dataset.emailId);
    var list = editor.querySelector('#ownmail-label-items');
    var status = editor.querySelector('#ownmail-label-status');
    var input = editor.querySelector('#ownmail-label-input');
    var add = editor.querySelector('#ownmail-label-add');
    var save = editor.querySelector('#ownmail-label-save');
    var close = editor.querySelector('#ownmail-label-close');
    var empty = editor.querySelector('#ownmail-label-empty');
    var history = editor.querySelector('#ownmail-label-history');
    var labels = [];
    var attempt = 0;
    var saving = false;

    function announce(text, error) {
        status.textContent = text;
        status.setAttribute('role', error ? 'alert' : 'status');
    }

    function render() {
        list.replaceChildren();
        labels.forEach(function(label, index) {
            var item = document.createElement('li');
            var name = document.createElement('span');
            name.textContent = label;
            var remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = 'Remove';
            remove.className = 'ownmail-button';
            remove.setAttribute('data-message-action', '');
            remove.setAttribute('aria-label', 'Remove label ' + label);
            remove.addEventListener('click', function() {
                labels.splice(index, 1);
                render();
                announce('Unsaved changes.');
                var next = list.querySelectorAll('button');
                (next[Math.min(index, next.length - 1)] || input).focus();
            });
            item.append(name, remove);
            list.append(item);
        });
        empty.hidden = labels.length !== 0;
        var notes = [];
        if (labels.includes('INBOX') || labels.includes('DRAFT')) {
            notes.push('INBOX and DRAFT are historical labels, hidden in navigation.');
        }
        if (labels.includes('UNREAD')) notes.push('Remove UNREAD before saving; it represents mail-client state.');
        history.textContent = notes.join(' ');
        history.hidden = notes.length === 0;
    }

    trigger.addEventListener('click', async function() {
        var current = ++attempt;
        trigger.closest('details').open = false;
        trigger.setAttribute('aria-expanded', 'true');
        editor.hidden = false;
        input.value = '';
        input.disabled = add.disabled = save.disabled = true;
        list.replaceChildren();
        empty.hidden = true;
        history.hidden = true;
        announce('Loading labels…');
        close.focus();
        try {
            var data = await window.ownmailRequest(url, undefined, true);
            if (current !== attempt) return;
            if (!Array.isArray(data.labels) || !data.labels.every(function(label) { return typeof label === 'string'; })) {
                throw new Error('Could not read the saved labels.');
            }
            labels = data.labels;
            render();
            input.disabled = add.disabled = save.disabled = false;
            announce('');
            input.focus();
        } catch (error) {
            if (current === attempt) {
                announce(error.message + ' Close the editor and try again.', true);
                window.ownmailConnectionError('Could not load labels. Retry to reload the message.');
            }
        }
    });

    function addLabel() {
        var label = input.value;
        if (!label.trim()) {
            announce('Enter a label name.', true);
        } else if (label === 'UNREAD') {
            announce('UNREAD is mail-client state and cannot be saved as a label.', true);
        } else if (labels.includes(label)) {
            announce('That label is already present.');
        } else {
            labels.push(label);
            input.value = '';
            render();
            announce('Unsaved changes.');
        }
        input.focus();
    }
    add.addEventListener('click', addLabel);
    input.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            addLabel();
        }
    });
    close.addEventListener('click', function() {
        if (saving) return;
        ++attempt;
        editor.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        trigger.closest('details').querySelector('summary').focus();
    });
    editor.querySelector('#ownmail-label-form').addEventListener('submit', async function(event) {
        event.preventDefault();
        if (saving || save.disabled) return;
        if (labels.includes('UNREAD')) {
            announce('Remove UNREAD before saving; it represents mail-client state.', true);
            return;
        }
        if (input.value.trim()) {
            announce('Add the entered label before saving, or clear the input.', true);
            input.focus();
            return;
        }
        saving = true;
        announce('Saving labels…');
        var confirmed = await window.ownmailMessageAction({
            url: url,
            request: {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({labels: labels})},
            pending: 'Saving labels…',
            success: 'Labels saved.',
            failure: 'Could not confirm the label save.',
            json: true,
            onSuccess: function(result) {
                if (result.indexed) {
                    window.location.reload();
                } else {
                    announce('Labels saved. Search could not be updated. Save again to retry.', true);
                }
            }
        });
        saving = false;
        if (!confirmed) announce('Could not confirm the label save. Reload the message to check its labels.', true);
    });
})();
