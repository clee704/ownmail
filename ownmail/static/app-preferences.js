function applyListDensity(density) {
    if (!['comfortable', 'standard', 'compact'].includes(density)) density = 'standard';
    document.documentElement.dataset.listDensity = density;
    var control = document.getElementById('ownmail-list-density');
    if (control) control.value = density;
}
function restoreListDensity() {
    var density;
    try { density = localStorage.getItem('ownmail-list-density'); } catch (error) {}
    applyListDensity(density);
}
// Restore before painting and when returning from the browser's page cache.
restoreListDensity();
window.addEventListener('pageshow', restoreListDensity);
window.addEventListener('storage', function(event) {
    if (event.key === 'ownmail-list-density' || event.key === null) restoreListDensity();
});
// Apply the saved theme before the first paint.
(function() {
    var pref = localStorage.getItem('ownmail-theme') || 'auto';
    var dark = pref === 'dark' || (pref === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (dark) document.documentElement.classList.add('ownmail-dark');
})();
