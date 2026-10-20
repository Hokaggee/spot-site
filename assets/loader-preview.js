(() => {
  const $ = selector => document.querySelector(selector);
  const logo = '<img class="loader-wordmark" src="/assets/лого спот.png" alt="" width="6327" height="1258">';
  const star = '<svg class="assembly-star" viewBox="0 0 50 50" fill="currentColor"><path d="m25 2 6.7 14.1 15.5 2.3L36 29.4l2.6 15.5L25 37.6l-13.6 7.3L14 29.4 2.8 18.4l15.5-2.3Z"/></svg>';
  const names = ['Сборка логотипа', 'Твой проход', 'Первый бит', 'Клубный занавес'];
  const art = [
    `<div class="assembly-logo">${'<span class="logo-piece"></span>'.repeat(4)}</div>${star}`,
    `<div class="admit-ticket"><div class="ticket-body">${logo}<span class="ticket-small">Твоя точка сборки.</span><span class="ticket-stamp">Свой</span></div><div class="ticket-tear"><div class="ticket-barcode"></div><span>ПРОХОДИ</span></div></div>`,
    `<div class="beat-bars">${'<i></i>'.repeat(9)}</div><div class="beat-logo">${logo}</div>`,
    `<div class="curtain-panel curtain-left"></div><div class="curtain-panel curtain-right"></div><div class="curtain-logo">${logo}</div><div class="curtain-line"></div>`
  ];
  for (const thumbnail of document.querySelectorAll('[data-art]')) {
    const number = Number(thumbnail.dataset.art);
    thumbnail.innerHTML = `<div class="loader-art variant-${number}">${art[number-1]}</div>`;
  }
  const dialog = $('#preview-dialog'), overlay = $('#loader-overlay'), frame = $('#preview-frame'), skip = $('#skip');
  let selected = 1, pace = 1, leaveTimer = 0, finishTimer = 0, opener = null;
  function clearPlayback() { clearTimeout(leaveTimer); clearTimeout(finishTimer); }
  function finish() {
    clearPlayback();
    overlay.hidden = true;
    overlay.replaceChildren();
    skip.hidden = true;
    if (document.activeElement === skip) $('#replay').focus({preventScroll:true});
  }
  function play(number, speed = 1) {
    clearPlayback();
    selected = number; pace = speed;
    $('#preview-title').textContent = `${String(number).padStart(2,'0')} · ${names[number-1]}${speed===2?' · медленно':''}`;
    overlay.className = `loader-overlay variant-${number}`;
    overlay.style.setProperty('--pace', String(speed));
    overlay.innerHTML = `<div class="loader-art">${art[number-1]}</div>`;
    overlay.hidden = false; skip.hidden = false;
    if (!dialog.open) {
      opener = document.activeElement;
      dialog.showModal();
      $('#replay').focus({preventScroll:true});
    }
    if (!frame.getAttribute('src')) frame.src = '/?preview=loader';
    // Recreate the art for every play so replay and rapid switching restart cleanly.
    void overlay.offsetWidth;
    overlay.classList.add('playing');
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { finish(); return; }
    leaveTimer = setTimeout(() => overlay.classList.add('is-leaving'), 1650*speed);
    finishTimer = setTimeout(finish, 2050*speed);
  }
  $('#variants').addEventListener('click', event => {
    const button = event.target.closest('button[data-variant]');
    if (button) play(Number(button.dataset.variant), Number(button.dataset.pace || 1));
  });
  frame.addEventListener('load', () => {
    frame.contentDocument?.addEventListener('keydown', event => {
      if (event.key === 'Escape' && dialog.open) {
        event.preventDefault();
        dialog.close();
      }
    });
  });
  $('#replay').addEventListener('click', () => play(selected, pace));
  $('#next').addEventListener('click', () => play(selected%4+1, pace));
  skip.addEventListener('click', finish);
  $('#close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    finish();
    frame.contentDocument?.querySelector('#hero-video')?.pause();
    opener?.focus({preventScroll:true});
  });
})();
