export const themeToggleMarkup = /* html */ `
  <button type="button" class="theme-toggle" aria-label="Dark mode" aria-pressed="false" title="Switch to dark mode">
    <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M16.5 11.6A7 7 0 0 1 8.4 3.5a7 7 0 1 0 8.1 8.1Z"/></svg>
    <span>Dark mode</span><span class="theme-toggle-track" aria-hidden="true"></span>
  </button>`;

const preferenceKey = 'electricity-theme';
const validTheme = value => value === 'dark' || value === 'light';

export function mountTheme(root, signal) {
  const button = root.querySelector('.theme-toggle');
  const page = document.documentElement;
  const previous = page.getAttribute('data-electricity-theme');
  let preference;
  try { preference = localStorage.getItem(preferenceKey); } catch { /* Storage is optional. */ }

  function render() {
    // Start in light mode until the visitor explicitly chooses a theme.
    const theme = validTheme(preference) ? preference : 'light';
    page.setAttribute('data-electricity-theme', theme);
    button.setAttribute('aria-pressed', String(theme === 'dark'));
    button.title = `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`;
  }

  button.addEventListener('click', () => {
    preference = button.getAttribute('aria-pressed') === 'true' ? 'light' : 'dark';
    try { localStorage.setItem(preferenceKey, preference); } catch { /* Keep the toggle usable. */ }
    render();
  }, {signal});
  window.addEventListener('storage', event => {
    if (event.key === preferenceKey || event.key === null) {
      preference = event.newValue;
      render();
    }
  }, {signal});
  signal.addEventListener('abort', () => {
    // Only electricity pages use this theme; restore the surrounding site on exit.
    if (previous === null) page.removeAttribute('data-electricity-theme');
    else page.setAttribute('data-electricity-theme', previous);
  }, {once:true});
  render();
}
