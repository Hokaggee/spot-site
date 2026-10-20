"""Cache original public posters for a reliable GitHub Pages preview."""
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from events import Calendar

folder = ROOT / 'assets/posters'
folder.mkdir(exist_ok=True)
allowed = {'cdn.qtickets.tech', 'avatars.mds.yandex.net', 'avatars.mds.yandex.ru'}


def cache(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in allowed:
        raise ValueError('Unexpected poster origin')
    temporary = folder / f'{hashlib.sha256(url.encode()).hexdigest()}.tmp'
    try:
        subprocess.run(['curl', '--fail', '--silent', '--show-error', '--connect-timeout', '10',
                        '--max-time', '30', '--max-filesize', '20000000', '--output', str(temporary), url], check=True)
        with Image.open(temporary) as image:
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}[image.format]
            image.verify()
        path = temporary.with_suffix(f'.{extension}')
        temporary.replace(path)
        return url, path.name
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    urls = sorted({event['poster'] for event in Calendar(ROOT / '.spot-data').payload()['events'] if event.get('poster')})
    with ThreadPoolExecutor(max_workers=3) as pool:
        mapping = dict(pool.map(cache, urls))
    (folder / 'index.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Cached {len(mapping)} original posters without resizing or recompression.')
