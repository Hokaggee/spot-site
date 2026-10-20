(() => {
  const $ = selector => document.querySelector(selector);
  const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Yakutsk' });
  const eventFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Yakutsk' });
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const photoCount = count => `${count} ${count % 10 === 1 && count % 100 !== 11 ? 'фотография' : count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 12 || count % 100 > 14) ? 'фотографии' : 'фотографий'}`;
  async function request(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) { let message = 'Не удалось загрузить данные. Попробуйте ещё раз.'; try { message = (await response.json()).error || message; } catch {} throw new Error(message); }
    return response.json();
  }
  function image(src, alt, className) {
    const img = el('img', className); img.src = src; img.alt = alt; img.loading = 'lazy'; img.decoding = 'async'; return img;
  }

  const video = $('#hero-video');
  const pauseButton = $('.video-toggle');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let manualPause = false, heroVisible = true, explicitPlay = false;
  function syncVideo() {
    const paused = manualPause || (reduced.matches && !explicitPlay) || document.hidden || !heroVisible;
    if (paused) video.pause(); else video.play().catch(() => {});
    pauseButton.setAttribute('aria-pressed', String(paused));
    pauseButton.setAttribute('aria-label', paused ? 'Воспроизвести видео' : 'Приостановить видео');
    pauseButton.firstElementChild.textContent = paused ? '▷' : 'Ⅱ';
  }
  pauseButton.addEventListener('click', () => {
    manualPause = !video.paused;
    if (!manualPause) explicitPlay = true;
    syncVideo();
  });
  video.addEventListener('loadeddata', syncVideo, { once: true });
  reduced.addEventListener('change', () => { explicitPlay = false; syncVideo(); });
  document.addEventListener('visibilitychange', syncVideo);
  if ('IntersectionObserver' in window) new IntersectionObserver(([entry]) => { heroVisible = entry.isIntersecting; syncVideo(); }).observe($('.hero'));
  syncVideo();

  const eventGrid = $('#events-grid');
  let eventLayoutFrame = 0;
  function layoutEvents() {
    if (eventLayoutFrame) return;
    eventLayoutFrame = requestAnimationFrame(() => {
      eventLayoutFrame = 0;
      const desktop = matchMedia('(min-width: 601px)').matches;
      const cards = [...eventGrid.children];
      const spans = cards.map(card => desktop ? String(Math.ceil(card.getBoundingClientRect().height + 24)) : '');
      cards.forEach((card, index) => {
        const value = spans[index] ? `span ${spans[index]}` : '';
        if (card.style.gridRowEnd !== value) card.style.gridRowEnd = value;
      });
    });
  }
  const eventResize = 'ResizeObserver' in window ? new ResizeObserver(layoutEvents) : null;
  addEventListener('resize', layoutEvents);
  document.fonts.ready.then(layoutEvents);

  let calendarAttempts = 0;
  async function loadEvents() {
    const grid = $('#events-grid'), status = $('#events-status');
    try {
      const payload = await request('/api/events');
      eventResize?.disconnect();
      grid.replaceChildren();
      for (const event of payload.events) {
        const seller = event.source_name || (new URL(event.url).hostname === 'afisha.yandex.ru' ? 'Яндекс Афиша' : 'Qtickets');
        const card = el('article', 'event');
        if (event.poster) card.append(image(event.poster, `Афиша: ${event.title}`, 'event-poster'));
        const info = el('div', 'event-info'), meta = el('div', 'event-meta');
        meta.append(el('span', 'event-date', eventFormat.format(new Date(event.starts_at))), el('span', 'event-category', event.category));
        const bottom = el('div', 'event-bottom'), link = el('a', 'button primary', 'Купить билет ↗');
        link.href = event.url; link.target = '_blank'; link.rel = 'noreferrer'; link.setAttribute('aria-label', `Купить билет: ${event.title} — ${seller}`);
        const price = el('div', 'event-price-line');
        price.append(el('span', 'event-price', event.price || 'Цена при покупке'), el('span', 'event-source', `Билеты: ${seller}`));
        bottom.append(price, link);
        info.append(meta, el('h3', null, event.title), bottom); card.append(info); grid.append(card);
        eventResize?.observe(card);
        card.querySelector('img')?.addEventListener('load', layoutEvents, {once: true});
      }
      eventResize?.observe(grid);
      layoutEvents();
      const updated = value => new Intl.DateTimeFormat('ru-RU', {day:'numeric',month:'long',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Yakutsk'}).format(new Date(value));
      if (payload.sources?.length) {
        status.textContent = payload.sources.map(source => `${source.name}: ${source.updated_at ? `обновлено ${updated(source.updated_at)}` : 'ожидаем мероприятия'}${source.stale && (source.updated_at || source.notice) ? ' · обновление временно недоступно' : ''}`).join(' · ');
      } else if (payload.updated_at) {
        status.textContent = `Афиша · обновлена ${updated(payload.updated_at)}${payload.stale ? ' · обновление временно недоступно' : ''}`;
      } else {
        status.textContent = 'Загружаем мероприятия. Афиши продавцов доступны по ссылкам ниже.';
      }
      if ((!payload.updated_at || payload.sources?.some(source => !source.updated_at)) && calendarAttempts < 8) {
        const delay = Math.min(1500 * 2 ** calendarAttempts++, 15000);
        setTimeout(loadEvents, delay);
      }
      if (!payload.events.length && payload.updated_at) status.textContent += ' Новых мероприятий пока нет.';
    } catch { status.textContent = 'Сейчас не удалось загрузить афишу. Откройте Qtickets или Яндекс Афишу по ссылкам ниже.'; }
    finally { grid.setAttribute('aria-busy', 'false'); }
  }
  async function loadAlbums() {
    const grid = $('#albums-grid'), status = $('#albums-status');
    try {
      const { albums } = await request('/api/albums');
      grid.replaceChildren();
      for (const album of albums) {
        const button = el('button', 'album-card'); button.type = 'button'; button.setAttribute('aria-label', `Открыть альбом «${album.title}», ${photoCount(album.photo_count)}`);
        const cover = el('div', 'album-cover'); cover.append(image(album.cover_url, '', null), el('span', 'album-open', '↗'));
        cover.lastChild.setAttribute('aria-hidden', 'true');
        button.append(cover, el('h3', null, album.title), el('p', null, `${dateFormat.format(new Date(album.date+'T12:00:00+09:00'))} · ${photoCount(album.photo_count)}`));
        button.addEventListener('click', () => openAlbum(album)); grid.append(button);
      }
      status.textContent = albums.length ? '' : 'Первые фотоальбомы появятся здесь после публикации. Возвращайся за своими кадрами.';
    } catch { status.textContent = 'Не получилось загрузить фотоальбомы. Обновите страницу чуть позже.'; }
    finally { grid.setAttribute('aria-busy', 'false'); }
  }

  const dialog = $('#album-dialog'), viewer = $('#photo-viewer'), photoGrid = $('#photo-grid');
  let currentAlbum = null, currentIndex = 0, opener = null, controller = null;
  async function openAlbum(summary) {
    opener = document.activeElement;
    currentAlbum = null;
    controller?.abort(); controller = new AbortController();
    $('#album-title').textContent = summary.title;
    $('#album-meta').textContent = `${dateFormat.format(new Date(summary.date+'T12:00:00+09:00'))} · ${photoCount(summary.photo_count)}`;
    $('#album-error').textContent = 'Загружаем фотографии…';
    $('#download-album').href = `/api/albums/${summary.id}/archive`;
    photoGrid.replaceChildren(); showGrid();
    dialog.showModal(); document.body.classList.add('dialog-open');
    try {
      const album = await request(`/api/albums/${summary.id}`, {signal: controller.signal});
      if (!dialog.open) return;
      currentAlbum = album;
      $('#album-error').textContent = '';
      album.photos.forEach((photo, index) => {
        const tile = el('button', 'photo-tile'); tile.type = 'button'; tile.setAttribute('aria-label', `Открыть фотографию ${index+1} из ${album.photos.length}`);
        tile.append(image(photo.thumb_url, `Фотография ${index+1} с вечеринки ${album.title}`));
        tile.addEventListener('click', () => showPhoto(index)); photoGrid.append(tile);
      });
    } catch (error) { if (error.name !== 'AbortError') $('#album-error').textContent = error.message; }
  }
  function showPhoto(index) {
    if (!currentAlbum?.photos.length) return;
    currentIndex = (index+currentAlbum.photos.length) % currentAlbum.photos.length;
    const photo = currentAlbum.photos[currentIndex];
    $('#full-photo').src = photo.url;
    $('#full-photo').alt = `Фотография ${currentIndex+1} с вечеринки ${currentAlbum.title}`;
    $('#photo-counter').textContent = `${currentIndex+1} / ${currentAlbum.photos.length}`;
    $('#photo-filename').textContent = photo.filename;
    $('#download-photo').href = photo.download_url;
    $('#download-photo').download = photo.filename;
    $('.album-toolbar').hidden = true; photoGrid.hidden = true; $('#album-error').hidden = true; viewer.hidden = false;
    $('#previous-photo').hidden = $('#next-photo').hidden = currentAlbum.photos.length < 2;
    $('#back-to-album').focus();
  }
  function showGrid() {
    viewer.hidden = true; photoGrid.hidden = false; $('.album-toolbar').hidden = false; $('#album-error').hidden = false;
    photoGrid.children[currentIndex]?.focus();
  }
  $('#back-to-album').addEventListener('click', showGrid);
  $('#previous-photo').addEventListener('click', () => showPhoto(currentIndex-1));
  $('#next-photo').addEventListener('click', () => showPhoto(currentIndex+1));
  for (const button of document.querySelectorAll('.close-dialog')) button.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) {const rect=dialog.getBoundingClientRect(); if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom) dialog.close();} });
  dialog.addEventListener('close', () => { controller?.abort(); document.body.classList.remove('dialog-open'); $('#full-photo').removeAttribute('src'); opener?.focus(); });
  dialog.addEventListener('keydown', event => { if (viewer.hidden) return; if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); showPhoto(currentIndex+(event.key==='ArrowRight'?1:-1)); } });
  let touchStart = null;
  $('.viewer-stage').addEventListener('touchstart', event => {touchStart = event.touches.length===1 ? {x:event.touches[0].clientX,y:event.touches[0].clientY} : null;}, {passive:true});
  $('.viewer-stage').addEventListener('touchend', event => {if(!touchStart||!event.changedTouches.length)return;const dx=event.changedTouches[0].clientX-touchStart.x,dy=event.changedTouches[0].clientY-touchStart.y;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.5)showPhoto(currentIndex+(dx<0?1:-1));touchStart=null;}, {passive:true});
  loadEvents(); loadAlbums();
})();
