"""Independent source caches and one public SPOT calendar."""
import json
import logging
import re
import threading
from datetime import datetime

from qtickets import CATALOG, TZ, fetch_catalog
from yandex_afisha import VENUE_URL, fetch_yandex

SOURCES = {'qtickets': ('Qtickets', CATALOG), 'yandex': ('Яндекс Афиша', VENUE_URL)}
TITLE_NOISE = set('большой сольный концерт концерта в благовещенск благовещенске нк спот споте на тур tour live'.split())


def event_key(event):
    words = re.findall(r'[a-zа-яё0-9]+', event['title'].casefold().replace('ё', 'е'))
    title = ' '.join(word for word in words if word not in TITLE_NOISE)
    day = datetime.fromisoformat(event['starts_at']).astimezone(TZ).date().isoformat()
    return day, title or event['title'].casefold()


def merge_events(batches):
    merged = []
    for source in SOURCES:
        incoming = batches.get(source, [])
        matched_incoming = set()
        for key in {event_key(event) for event in incoming}:
            previous = sorted(datetime.fromisoformat(event['starts_at']) for event in merged if event_key(event) == key)
            candidates = sorted((datetime.fromisoformat(event['starts_at']), index)
                                for index, event in enumerate(incoming) if event_key(event) == key)
            # Ordered matching maximizes paired sessions, then minimizes time
            # differences. A nearest-first match can strand an overlapping show.
            scores = [[(0, 0)] * (len(candidates)+1) for _ in range(len(previous)+1)]
            steps = {}
            for left in range(1, len(previous)+1):
                for right in range(1, len(candidates)+1):
                    choices = [(scores[left-1][right], 'previous'), (scores[left][right-1], 'incoming')]
                    distance = abs((previous[left-1] - candidates[right-1][0]).total_seconds())
                    if distance <= 90*60:
                        count, cost = scores[left-1][right-1]
                        choices.append(((count+1, cost-distance), 'match'))
                    scores[left][right], steps[left, right] = max(choices, key=lambda choice: choice[0])
            left, right = len(previous), len(candidates)
            while left and right:
                step = steps[left, right]
                if step == 'match':
                    matched_incoming.add(candidates[right-1][1])
                    left, right = left-1, right-1
                elif step == 'previous':
                    left -= 1
                else:
                    right -= 1
        merged.extend({**event, 'source': source, 'source_name': SOURCES[source][0]}
                      for index, event in enumerate(incoming) if index not in matched_incoming)
    return sorted(merged, key=lambda event: event['starts_at'])


class Calendar:
    def __init__(self, root):
        self.path = root / 'events-cache.json'
        self.lock = threading.Lock()
        self.errors = {}
        try:
            cached = json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            cached = {}
        self.cached = cached.get('sources', {'qtickets': cached} if 'events' in cached else {})

    def refresh_source(self, source):
        try:
            items = (fetch_catalog if source == 'qtickets' else fetch_yandex)()
            payload = {'events': items, 'updated_at': datetime.now(TZ).isoformat()}
            with self.lock:
                updated = {**self.cached, source: payload}
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'sources': updated}, ensure_ascii=False))
                temporary.replace(self.path)
                self.cached = updated
                self.errors.pop(source, None)
        except Exception as error:
            logging.warning('%s refresh failed: %s', SOURCES[source][0], type(error).__name__)
            with self.lock:
                self.errors[source] = 'Обновление временно недоступно.'

    def refresh(self):
        for source in SOURCES:
            self.refresh_source(source)

    def payload(self):
        with self.lock:
            now = datetime.now(TZ)
            batches, sources = {}, []
            for source, (name, url) in SOURCES.items():
                cached = self.cached.get(source, {})
                batches[source] = [e for e in cached.get('events', [])
                                   if datetime.fromisoformat(e['starts_at']).astimezone(TZ).date() >= now.date()]
                updated = cached.get('updated_at')
                stale = not updated or (now-datetime.fromisoformat(updated)).total_seconds() > 1800 or source in self.errors
                sources.append({'id': source, 'name': name, 'url': url, 'updated_at': updated,
                                'stale': stale, 'notice': self.errors.get(source), 'event_count': len(batches[source])})
            return {'events': merge_events(batches), 'sources': sources,
                    'updated_at': max((s['updated_at'] for s in sources if s['updated_at']), default=None),
                    'stale': any(s['stale'] for s in sources),
                    'notice': ' '.join(f"{s['name']}: {s['notice']}" for s in sources if s['notice']) or None}

    def start(self):
        def run(source):
            while True:
                self.refresh_source(source)
                threading.Event().wait(900)
        for source in SOURCES:
            threading.Thread(target=run, args=(source,), name=f'{source}-refresh', daemon=True).start()
