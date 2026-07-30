(function () {
  const root = document.documentElement;
  const stored = localStorage.getItem('bg-theme');
  if (stored) root.setAttribute('data-theme', stored);

  const toggle = document.getElementById('themeToggle');
  if (!toggle) return;

  toggle.addEventListener('click', () => {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const current = root.getAttribute('data-theme') || (prefersDark ? 'dark' : 'light');
    const next = current === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('bg-theme', next);
  });
})();
