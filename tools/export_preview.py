"""Export only the public website and published albums for GitHub Pages.

The Python server, admin credentials, sessions and draft albums never enter
the exported directory. Run from the checkout with Python 3.11+.
"""
import argparse
import json
import re
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from events import Calendar


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def export(destination, data_root):
    destination.mkdir(parents=True, exist_ok=True)
    # Explicit allowlist: do not copy arbitrary files from the checkout/data root.
    for name in ('index.html', 'styles.css', 'fonts.css', 'app.js', 'legal.html', 'legal.css'):
        shutil.copy2(ROOT / name, destination / name)
    assets = {
        'spot-logo.jpg', 'лого спот.png', 'red-portrait.jpg', 'spot-reel.mp4',
        'entry-loader.css', 'entry-loader.js', 'golos-LICENSE.txt', 'oswald-LICENSE.txt',
        *(f'golos-{weight}.ttf' for weight in (400, 500, 600, 700)),
        'oswald-600.ttf', 'oswald-700.ttf',
    }
    (destination / 'assets').mkdir(exist_ok=True)
    for name in assets:
        shutil.copy2(ROOT / 'assets' / name, destination / 'assets' / name)

    # Keep the full local app unchanged. This adapter supplies the same public
    # JSON contract from files and works at a project subpath (/spot-site/).
    adapter = '''(() => {
  const base = new URL('./', document.currentScript.src);
  const fetchNative = window.fetch.bind(window);
  window.fetch = (input, options) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      const path = input === '/api/events' ? 'events.json'
        : input === '/api/albums' ? 'albums.json'
        : /^\\/api\\/albums\\/[a-f0-9]{24}$/.test(input)
          ? `albums/${input.split('/').pop()}.json` : null;
      if (path) return fetchNative(new URL(`data/${path}`, base), options);
    }
    return fetchNative(input, options);
  };
  document.addEventListener('DOMContentLoaded', () => {
    const archive = document.getElementById('download-album');
    const update = () => {
      const path = archive.getAttribute('href');
      const match = /^\\/api\\/albums\\/([a-f0-9]{24})\\/archive$/.exec(path || '');
      if (match) {
        archive.href = new URL(`downloads/${match[1]}.zip`, base).href;
        archive.download = 'album.zip';
      }
    };
    new MutationObserver(update).observe(archive, {attributes: true, attributeFilter: ['href']});
  }, {once: true});
})();
'''
    (destination / 'preview-adapter.js').write_text(adapter, encoding='utf-8')
    index = (destination / 'index.html').read_text(encoding='utf-8')
    index = index.replace('<script src="app.js" defer>', '<script src="preview-adapter.js"></script>\n  <script src="app.js" defer>')
    (destination / 'index.html').write_text(index, encoding='utf-8')
    (destination / '.nojekyll').touch()
    events = Calendar(data_root).payload()
    poster_index = ROOT / 'assets/posters/index.json'
    if poster_index.exists():
        mapping = json.loads(poster_index.read_text(encoding='utf-8'))
        (destination / 'assets/posters').mkdir(exist_ok=True)
        for event in events['events']:
            name = mapping.get(event.get('poster'))
            if name and re.fullmatch(r'[a-f0-9]{64}\.(jpg|png|webp)', name):
                shutil.copy2(poster_index.parent / name, destination / 'assets/posters' / name)
                event['poster'] = f'./assets/posters/{name}'
    dump(destination / 'data/events.json', events)

    db = sqlite3.connect(f'{(data_root / "spot.sqlite3").as_uri()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    albums = []
    try:
        for row in db.execute('SELECT id,title,date,cover_id FROM albums WHERE published=1 ORDER BY date DESC,created DESC'):
            album = dict(row)
            photos = []
            for photo in db.execute('SELECT id,filename,ext FROM photos WHERE album_id=? ORDER BY created,id', (row['id'],)):
                photo = dict(photo)
                # Database IDs/extensions must never become arbitrary filesystem paths.
                if not re.fullmatch('[a-f0-9]{32}', photo['id']) or photo['ext'] not in ('jpg', 'png', 'webp'):
                    raise ValueError('Unexpected photo metadata')
                folder = Path('photos') / photo['id']
                (destination / folder).mkdir(parents=True, exist_ok=True)
                for variant, extension in [('original', photo['ext']), ('preview', 'jpg'), ('thumb', 'jpg')]:
                    name = f'{variant}.{extension}'
                    shutil.copy2(data_root / folder / name, destination / folder / name)
                photo.update(thumb_url=f'./{folder}/thumb.jpg', url=f'./{folder}/preview.jpg',
                             download_url=f'./{folder}/original.{photo["ext"]}')
                photos.append(photo)
            album.update(photo_count=len(photos), cover_url=f'./photos/{row["cover_id"]}/thumb.jpg')
            albums.append(album)
            dump(destination / f'data/albums/{row["id"]}.json', {**album, 'photos': photos})
            (destination / 'downloads').mkdir(exist_ok=True)
            with zipfile.ZipFile(destination / f'downloads/{row["id"]}.zip', 'w', compression=zipfile.ZIP_STORED) as archive:
                for number, photo in enumerate(photos, 1):
                    archive.write(destination / photo['download_url'][2:],
                                  arcname=f'{number:03d}_{Path(photo["filename"]).name}')
    finally:
        db.close()
    dump(destination / 'data/albums.json', {'albums': albums})
    print(f'Exported {len(albums)} published albums, {sum(a["photo_count"] for a in albums)} photos to {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'public-preview')
    parser.add_argument('--data', type=Path, default=ROOT / '.spot-data')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Output must be empty: use a fresh directory to prevent publishing old files.')
    export(output, args.data.resolve())
