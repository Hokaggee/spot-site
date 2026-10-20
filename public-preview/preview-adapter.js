(() => {
  const base = new URL('./', document.currentScript.src);
  const fetchNative = window.fetch.bind(window);
  window.fetch = (input, options) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      const path = input === '/api/events' ? 'events.json'
        : input === '/api/albums' ? 'albums.json'
        : /^\/api\/albums\/[a-f0-9]{24}$/.test(input)
          ? `albums/${input.split('/').pop()}.json` : null;
      if (path) return fetchNative(new URL(`data/${path}`, base), options);
    }
    return fetchNative(input, options);
  };
  document.addEventListener('DOMContentLoaded', () => {
    const archive = document.getElementById('download-album');
    const update = () => {
      const path = archive.getAttribute('href');
      const match = /^\/api\/albums\/([a-f0-9]{24})\/archive$/.exec(path || '');
      if (match) {
        archive.href = new URL(`downloads/${match[1]}.zip`, base).href;
        archive.download = 'album.zip';
      }
    };
    new MutationObserver(update).observe(archive, {attributes: true, attributeFilter: ['href']});
  }, {once: true});
})();
