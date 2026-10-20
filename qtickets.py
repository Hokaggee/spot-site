"""Read the public Qtickets venue catalogue over HTTP; retain the last success."""
import html
import re
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CATALOG = 'https://blagoveshensk.qtickets.events/'
TZ = ZoneInfo('Asia/Yakutsk')


def text(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', value)).split())


def safe_url(value, images=False):
    parsed = urlparse(html.unescape(value))
    allowed = ('cdn.qtickets.tech',) if images else ('blagoveshensk.qtickets.events',)
    return parsed.scheme == 'https' and parsed.hostname in allowed and not parsed.username


def catalog_poster(card):
    card = html.unescape(card)
    match = re.search(r'background-image:\s*url\(["\']?([^\)"\']+)', card, re.I)
    poster = match.group(1) if match else ''
    if not safe_url(poster, images=True):
        return ''
    identity = re.search(r'/thumbs/(\d+)_(\d+)_', urlparse(poster).path)
    if not identity:
        return poster
    width = int(identity.group(2))
    # Qtickets publishes signed 1x/2x/3x URLs. Use the largest actual URL,
    # preserving the poster identity instead of guessing a CDN signature.
    for candidate in re.findall(r'url\(["\']?([^\)"\']+)', card, re.I):
        if not safe_url(candidate, images=True):
            continue
        variant = re.search(r'/thumbs/(\d+)_(\d+)_', urlparse(candidate).path)
        if variant and variant.group(1) == identity.group(1) and int(variant.group(2)) > width:
            poster, width = candidate, int(variant.group(2))
    return poster


def parse_catalog(document):
    cards = re.findall(r'<li\b[^>]*class=["\'][^"\']*\bitem\b[^"\']*["\'][^>]*>(.*?)</li>', document, re.S | re.I)
    if not cards and not re.search(r'Нет мероприятий|Мероприятий не найдено|Ничего не найдено', document, re.I):
        raise ValueError('Qtickets catalogue markup is missing')
    results = []
    for card in cards:
        def match(pattern):
            found = re.search(pattern, card, re.S | re.I)
            return found.group(1) if found else ''
        venue = text(match(r'class=["\']place-name["\'][^>]*>(.*?)</span>'))
        if not re.fullmatch(r'(?:нк\s+)?спот', venue, re.I):
            continue
        url = html.unescape(match(r'<a\b[^>]*href=["\']([^"\']+)'))
        starts = match(r'<time\b[^>]*datetime=["\']([^"\']+)')
        title = text(match(r'<h2[^>]*>(.*?)</h2>'))
        poster = catalog_poster(card)
        price = text(match(r'class=["\']price\s+for-desktop["\'][^>]*>(.*?)</div>'))
        category = text(match(r'class=["\']type["\'][^>]*>(.*?)</div>'))
        try:
            datetime.fromisoformat(starts)
        except ValueError:
            continue
        if not safe_url(url) or not title:
            continue
        results.append({'title': title, 'starts_at': starts, 'venue': venue, 'url': url,
                        'poster': poster if safe_url(poster, images=True) else '',
                        'price': re.sub(r'руб\.?', '₽', price), 'category': category})
    more = bool(re.search(r'id=["\']next_page["\']', document))
    return results, more


def fetch_catalog():
    events = {}
    for page in range(1, 21):
        request = Request(f'{CATALOG}?page={page}', headers={'User-Agent': 'SPOT-venue-calendar/1.0', 'Accept': 'text/html'})
        with urlopen(request, timeout=18) as response:
            if urlparse(response.url).hostname != 'blagoveshensk.qtickets.events':
                raise ValueError('Unexpected Qtickets redirect')
            document = response.read(4*1024*1024).decode('utf-8')
        batch, more = parse_catalog(document)
        for event in batch:
            events[event['url']] = event
        if not more:
            return sorted(events.values(), key=lambda e: e['starts_at'])
    raise ValueError('Qtickets catalogue exceeded 20 pages; previous cache retained')

