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
// Apply the saved theme before paint and update browser chrome on resume.
function isDarkMode() {
    var pref;
    try { pref = localStorage.getItem('ownmail-theme'); } catch (error) {}
    if (!['light', 'dark'].includes(pref)) pref = 'auto';
    return pref === 'dark' || (pref === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
}
function applyTheme() {
    var dark = isDarkMode();
    document.documentElement.classList.toggle('ownmail-dark', dark);
    document.head.querySelector('meta[name="theme-color"]').content = dark ? '#202124' : '#ffffff';
    if (typeof updateEmailDarkMode === 'function') updateEmailDarkMode(dark);
}
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
window.addEventListener('pageshow', applyTheme);
window.addEventListener('storage', function(event) {
    if (event.key === 'ownmail-theme' || event.key === null) applyTheme();
});
applyTheme();
