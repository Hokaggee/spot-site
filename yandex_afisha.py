"""Public JSON-LD published by the SPOT venue on Yandex Afisha."""
import http.client
import ipaddress
import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, quote
from urllib.request import urlopen

from qtickets import TZ, text

VENUE_URL = 'https://afisha.yandex.ru/blagoveshchensk/concert/places/spot-blagoveshchensk'
SOURCE_CONFIG = Path(__file__).with_name('event-sources.json')
_resolver = ThreadPoolExecutor(max_workers=1, thread_name_prefix='afisha-dns')
_lookup = None


def resolve_host(host):
    # Bound system DNS separately: socket connection timeouts do not bound DNS.
    # Reuse a pending lookup so a broken resolver cannot accumulate workers.
    global _lookup
    if _lookup is None or _lookup.done():
        _lookup = _resolver.submit(socket.gethostbyname, host)
    try:
        return _lookup.result(timeout=2)
    except (OSError, TimeoutError):
        with urlopen(f'https://dns.google/resolve?name={quote(host)}&type=A', timeout=6) as response:
            payload = json.loads(response.read(65536))
        for answer in payload.get('Answer', []):
            if answer.get('type') == 1 and ipaddress.ip_address(answer['data']).is_global:
                return answer['data']
        raise OSError('Yandex Afisha DNS unavailable')


def fetch_document(url, address):
    host = 'afisha.yandex.ru'
    connection = http.client.HTTPSConnection(host, timeout=18)
    # Connect to the resolved IP, keeping the original hostname for TLS/SNI
    # and certificate verification. No pinned IP or disabled TLS verification.
    connection._create_connection = lambda target, timeout, source_address: socket.create_connection(
        (address, target[1]), timeout, source_address)
    try:
        connection.request('GET', urlparse(url).path, headers={
            'Host': host, 'User-Agent': 'SPOT-venue-calendar/1.0', 'Accept': 'text/html', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status != 200:
            raise OSError(f'Yandex Afisha HTTP {response.status}')
        document = response.read(4*1024*1024+1)
        if len(document) > 4*1024*1024:
            raise ValueError('Yandex Afisha document too large')
        return document.decode('utf-8')
    finally:
        connection.close()


def fetch_yandex():
    address = resolve_host('afisha.yandex.ru')
    results = parse_venue(fetch_document(VENUE_URL, address))
    transfers = json.loads(SOURCE_CONFIG.read_text()).get('yandex_confirmed_transfers', []) if SOURCE_CONFIG.exists() else []
    for transfer in transfers:
        url = transfer['url']
        if not ticket_url(url):
            raise ValueError('Invalid transfer URL')
        if datetime.now(TZ).date().isoformat() > transfer['valid_until']:
            continue
        if any(item['url'] == url for item in results):
            continue
        results.extend(parse_confirmed_transfer(fetch_document(url, address), url, transfer['event_id']))
    return results


def ticket_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (parsed.scheme == 'https' and parsed.netloc == 'afisha.yandex.ru'
            and parsed.path.startswith('/blagoveshchensk/') and '/places/' not in parsed.path)


def image_url(value):
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str)), '')
    if not isinstance(value, str):
        return ''
    parsed = urlparse(value)
    return value if (parsed.scheme == 'https' and parsed.netloc in (
        'avatars.mds.yandex.net', 'avatars.mds.yandex.ru') and parsed.path.startswith('/get-afishanew/')) else ''


def structured_records(document):
    records = []
    for attributes, raw in re.findall(r'<script\b([^>]*)>(.*?)</script>', document, re.S | re.I):
        if not re.search(r'type\s*=\s*["\']application/ld\+json["\']', attributes, re.I):
            continue
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        records.extend(payload if isinstance(payload, list) else [payload])
    places = []
    for record in records:
        if isinstance(record, dict):
            places.extend(record.get('@graph', []) if '@graph' in record else [record])
    return places


def parse_confirmed_transfer(document, url, event_id):
    item = next((record for record in structured_records(document) if isinstance(record, dict)
                 and record.get('@type') in ('Event', 'MusicEvent') and record.get('url') == url), None)
    if item is None:
        raise ValueError('Transferred event missing from Yandex page')
    schedule = None
    for match in re.finditer(r'("eventScheduleInfo\((?:\\.|[^"\\])*\)")\s*:\s*', document):
        key = json.loads(match.group(1))
        arguments = json.loads(key[len('eventScheduleInfo('):-1])
        if arguments.get('id') == event_id:
            schedule = json.JSONDecoder().raw_decode(document[match.end():])[0]
            break
    if schedule is None:
        raise ValueError('Transferred event local schedule missing')
    starts = schedule.get('regularity', {}).get('singleShowtime')
    if not starts:
        raise ValueError('Transferred event local showtime missing')
    # Venue override is explicitly confirmed by the owner, never inferred
    # from a city recommendation. Other metadata still comes from Yandex.
    item = {**item, 'location': {'url': VENUE_URL}, 'startDate': starts}
    envelope = {'@type': 'Place', 'url': VENUE_URL, 'event': [item]}
    return parse_venue('<script type="application/ld+json">'+json.dumps(envelope)+'</script>')


def parse_venue(document):
    venue = next((p for p in structured_records(document) if isinstance(p, dict) and p.get('@type') == 'Place'
                  and p.get('url', '').rstrip('/') == VENUE_URL and isinstance(p.get('event'), list)), None)
    if venue is None:
        raise ValueError('Yandex Afisha SPOT structured data missing')
    results, cancelled = [], 0
    for item in venue['event']:
        if not isinstance(item, dict) or item.get('@type') not in (
                'Event', 'MusicEvent', 'Festival', 'DanceEvent', 'TheaterEvent', 'ComedyEvent', 'SportsEvent', 'ExhibitionEvent'):
            continue
        if str(item.get('eventStatus', '')).endswith('EventCancelled'):
            cancelled += 1
            continue
        location = item.get('location') or {}
        if not isinstance(location, dict) or location.get('url', '').rstrip('/') != VENUE_URL:
            continue
        title, url = text(str(item.get('name', ''))), item.get('url', '')
        if not title or not ticket_url(url):
            continue
        try:
            starts = datetime.fromisoformat(item['startDate'])
            starts = starts.replace(tzinfo=TZ) if starts.tzinfo is None else starts.astimezone(TZ)
        except (KeyError, TypeError, ValueError):
            continue
        offers = item.get('offers') or {}
        if isinstance(offers, list):
            offers = next((offer for offer in offers if isinstance(offer, dict)), {})
        price = str(offers.get('price', offers.get('lowPrice', ''))) if isinstance(offers, dict) else ''
        price = f'от {price} ₽' if re.fullmatch(r'\d+(?:\.\d+)?', price) else ''
        category = {'concert':'Концерт', 'party':'Вечеринка', 'theatre':'Спектакль', 'sport':'Спорт'}.get(
            urlparse(url).path.split('/')[2], 'Мероприятие')
        results.append({'title': title, 'starts_at': starts.isoformat(), 'venue': 'СПОТ', 'url': url,
                        'poster': image_url(item.get('image', '')), 'price': price, 'category': category})
    if venue['event'] and not results and cancelled != len(venue['event']):
        raise ValueError('Yandex Afisha event records could not be parsed')
    return results
