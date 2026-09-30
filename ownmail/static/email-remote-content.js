var readerActions = document.getElementById('ownmail-reader-actions');
var senderEmail = readerActions.dataset.sender;

// The response's CSP decides what the browser may request from other
// hosts, so loading or blocking remote content reloads the message.
// Bind only app controls. Message HTML may retain arbitrary data attributes.
[readerActions, document.getElementById('ownmail-image-banner')].forEach(function(container) {
    if (!container) return;
    container.querySelectorAll('[data-reader-action="trust"]').forEach(function(button) {
        button.addEventListener('click', trustSender);
    });
    container.querySelectorAll('[data-reader-action="untrust"]').forEach(function(button) {
        button.addEventListener('click', untrustSender);
    });
    container.querySelectorAll('[data-images-url]').forEach(function(button) {
        button.addEventListener('click', function() {
            showLoading();
            location.replace(button.getAttribute('data-images-url'));
        });
    });
});

function trustSender() {
    ownmailMessageAction({
        url: '/trust-sender',
        request: {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'email=' + encodeURIComponent(senderEmail)},
        pending: 'Trusting sender…',
        success: 'Sender trusted.',
        failure: 'Could not trust this sender.',
        navigate: function() { location.replace(readerActions.dataset.reloadUrl); }
    });
}

function untrustSender() {
    ownmailMessageAction({
        url: '/untrust-sender',
        request: {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'email=' + encodeURIComponent(senderEmail)},
        pending: 'Removing trusted sender…',
        success: 'Sender removed from trusted senders.',
        failure: 'Could not remove this trusted sender.',
        onSuccess: function() {
            document.getElementById('menu-trust-sender').style.display = '';
            document.getElementById('menu-untrust-sender').style.display = 'none';
        }
    });
}
