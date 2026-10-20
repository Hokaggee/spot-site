(() => {
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  if (reduced.matches || new URLSearchParams(location.search).get('preview') === 'loader') return;
  let finished = false, exitTimer = 0, finishTimer = 0, safetyTimer = 0;
  let content = [];
  function finish() {
    if (finished) return;
    finished = true;
    clearTimeout(exitTimer); clearTimeout(finishTimer); clearTimeout(safetyTimer);
    root.classList.remove('entry-pending', 'entry-running', 'entry-fading');
    const overlay = document.getElementById('entry-loader');
    overlay?.setAttribute('aria-hidden', 'true');
    for (const node of content) node.inert = false;
    document.removeEventListener('keydown', onKey);
    reduced.removeEventListener('change', onMotion);
  }
  function onKey(event) { if (event.key === 'Escape') finish(); }
  function onMotion() { if (reduced.matches) finish(); }
  // Set the safety exit before showing anything; application/API/video failures
  // must never leave the site covered or its content inert.
  safetyTimer = setTimeout(finish, 4500);
  root.classList.add('entry-pending');
  addEventListener('pagehide', finish, {once:true});
  document.addEventListener('keydown', onKey);
  reduced.addEventListener('change', onMotion);
  document.addEventListener('DOMContentLoaded', () => {
    if (finished) return;
    const overlay = document.getElementById('entry-loader');
    if (!overlay) { finish(); return; }
    overlay.setAttribute('aria-hidden', 'false');
    content = [...document.querySelectorAll('main, body>footer, .skip-link')];
    for (const node of content) node.inert = true;
    function start() {
      if (finished) return;
      root.classList.add('entry-running');
      exitTimer = setTimeout(() => root.classList.add('entry-fading'), 1650);
      finishTimer = setTimeout(finish, 2050);
    }
    const logo = overlay.querySelector('img');
    Promise.race([logo.decode().catch(() => {}), new Promise(resolve => setTimeout(resolve, 450))]).then(start);
  }, {once:true});
})();
