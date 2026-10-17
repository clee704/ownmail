// The Print page opens the dialog once images have loaded, so they print.
// The page stays open afterwards, so a cancelled dialog can be retried.
window.addEventListener('load', function() { window.print(); });
