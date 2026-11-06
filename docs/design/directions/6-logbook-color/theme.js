// Light/dark theme. Order: ?theme= (used by the comparison page) > saved choice > OS setting.
// Runs in <head> before paint so there is no flash. The switch is instant: no transition on a daily screen.
(function () {
  var KEY = 'ons-theme', root = document.documentElement;
  var q = new URLSearchParams(location.search).get('theme');
  var saved = null; try { saved = localStorage.getItem(KEY); } catch (e) {}
  var os = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  root.dataset.theme = q === 'dark' || q === 'light' ? q : saved || os;

  function label(btn) {
    var dark = root.dataset.theme === 'dark';
    btn.setAttribute('aria-pressed', dark);
    btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
    btn.title = dark ? 'Light theme (T)' : 'Dark theme (T)';
  }
  function flip() {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(KEY, root.dataset.theme); } catch (e) {}
    document.querySelectorAll('[data-theme-toggle]').forEach(label);
  }
  addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-theme-toggle]').forEach(function (b) { label(b); b.addEventListener('click', flip); });
    addEventListener('keydown', function (e) {
      if (e.key !== 't' || e.metaKey || e.ctrlKey || e.altKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) return;
      flip();
    });
  });
})();
