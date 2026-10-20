import copy
import json
import tempfile
import unittest
from io import BytesIO
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from yandex_afisha import VENUE_URL, parse_venue, parse_confirmed_transfer
from events import Calendar, merge_events
import yandex_afisha


FIXTURE = Path(__file__).parent / 'fixtures' / 'yandex-spot.html'


def event(title='Yasmi', day='2099-10-25', hour='19:00', url='https://example.test/event'):
    return {'title': title, 'starts_at': f'{day}T{hour}:00+09:00', 'url': url,
            'venue': 'СПОТ', 'poster': '', 'price': 'от 2000 ₽', 'category': 'Концерт'}


class YandexTests(unittest.TestCase):
    def test_confirmed_transfer_loads_fortuna_despite_stale_venue_and_uses_actual_local_schedule(self):
        document = (FIXTURE.parent/'yandex-fortuna-transfer.html').read_text()
        items = parse_confirmed_transfer(document, 'https://afisha.yandex.ru/blagoveshchensk/concert/fortuna-812-tour', 'fortuna')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Fortuna 812')
        self.assertEqual(items[0]['venue'], 'СПОТ')
        self.assertEqual(items[0]['starts_at'], '2026-10-24T20:00:00+09:00')
        self.assertTrue(items[0]['poster'].endswith('/orig'))

    def test_transferred_event_does_not_take_an_unrelated_schedule(self):
        document = (FIXTURE.parent/'yandex-fortuna-transfer.html').read_text()
        key = json.dumps('eventScheduleInfo({"id":"unrelated"})')
        unrelated = '<script>'+key+':'+json.dumps({'regularity':{'singleShowtime':'2026-11-10T13:00:00'}})+'</script>'
        items = parse_confirmed_transfer(unrelated+document, 'https://afisha.yandex.ru/blagoveshchensk/concert/fortuna-812-tour', 'fortuna')
        self.assertEqual(items[0]['starts_at'], '2026-10-24T20:00:00+09:00')

    def test_dns_failure_uses_public_dns_without_pinning_an_address(self):
        response = BytesIO(json.dumps({'Answer':[{'type':1,'data':'127.0.0.1'},
                                                 {'type':1,'data':'213.180.193.71'}]}).encode())
        with patch.object(yandex_afisha, '_lookup', None), patch('yandex_afisha.socket.gethostbyname', side_effect=OSError('DNS')), patch('yandex_afisha.urlopen', return_value=response):
            self.assertEqual(yandex_afisha.resolve_host('afisha.yandex.ru'), '213.180.193.71')

    def test_real_venue_structured_data_retains_local_dates_originals_and_ticket_links(self):
        items = parse_venue(FIXTURE.read_text())
        self.assertEqual(len(items), 4)
        kitana = next(e for e in items if e['title'] == 'Kitana')
        self.assertEqual(kitana['starts_at'], '2026-11-15T20:00:00+09:00')
        self.assertEqual(kitana['url'], 'https://afisha.yandex.ru/blagoveshchensk/concert/kitana-tour')
        self.assertTrue(kitana['poster'].endswith('/orig'))
        self.assertEqual(kitana['price'], 'от 2000 ₽')

    def test_missing_or_wrong_venue_is_not_a_successful_empty_calendar(self):
        for document in ['<html>captcha</html>', FIXTURE.read_text().replace('spot-blagoveshchensk', 'another-venue')]:
            with self.assertRaises(ValueError):
                parse_venue(document)
        self.assertEqual(parse_venue('<script type="application/ld+json">'+json.dumps({
            '@type':'Place', 'url':VENUE_URL, 'event':[]})+'</script>'), [])

    def test_unreadable_event_dates_fail_instead_of_erasing_the_source_cache(self):
        document = json.loads(FIXTURE.read_text().split('>', 1)[1].split('</script>')[0])
        for item in document['event']:
            item['startDate'] = 'unavailable'
        with self.assertRaises(ValueError):
            parse_venue('<script type="application/ld+json">'+json.dumps(document)+'</script>')
        for item in document['event']:
            item['eventStatus'] = 'https://schema.org/EventCancelled'
        self.assertEqual(parse_venue('<script type="application/ld+json">'+json.dumps(document)+'</script>'), [])

    def test_unrelated_venue_and_unsafe_ticket_urls_are_rejected(self):
        document = json.loads(FIXTURE.read_text().split('>', 1)[1].split('</script>')[0])
        document['event'][0]['name'] = 'Fortuna 812'
        document['event'][0]['location']['url'] = 'https://afisha.yandex.ru/blagoveshchensk/concert/places/jigger-pony'
        document['event'][1]['url'] = 'https://afisha.yandex.ru.evil.test/ticket'
        document['event'][2]['image'] = 'https://evil.test/photo.jpg'
        items = parse_venue('<script type="application/ld+json">'+json.dumps(document)+'</script>')
        self.assertEqual(len(items), 2)
        self.assertNotIn('Fortuna 812', [item['title'] for item in items])
        self.assertEqual(next(e for e in items if e['title'] == 'uglystephan')['poster'], '')


class CombinedCalendarTests(unittest.TestCase):
    def test_same_artist_same_day_is_one_card_despite_source_title_and_time_differences(self):
        qt = event('Большой сольный концерт YASMI в Благовещенске', hour='20:00', url='https://blagoveshensk.qtickets.events/1')
        ya = event('Yasmi', url='https://afisha.yandex.ru/blagoveshchensk/concert/yasmi')
        result = merge_events({'qtickets':[qt], 'yandex':[ya, event('Kitana'), event('Yasmi', day='2099-10-26')]})
        self.assertEqual(len(result), 3)
        retained = next(e for e in result if e['source'] == 'qtickets')
        self.assertEqual(retained['starts_at'], qt['starts_at'])
        self.assertEqual(next(e for e in result if e['title'] == 'Kitana')['source'], 'yandex')

    def test_different_programmes_on_the_same_day_are_not_merged(self):
        self.assertEqual(len(merge_events({'qtickets':[event('KISS PARTY 1')], 'yandex':[event('KISS PARTY 2')]})), 2)

    def test_distinct_sessions_survive_and_cross_source_matching_is_one_to_one(self):
        earlier, later = event(hour='18:00'), event(hour='21:00')
        earlier['url'], later['url'] = 'https://qt.test/early', 'https://qt.test/late'
        self.assertEqual(len(merge_events({'qtickets':[earlier, later]})), 2)
        self.assertEqual(len(merge_events({'qtickets':[earlier], 'yandex':[earlier, later]})), 2)
        self.assertEqual(len(merge_events({'qtickets':[earlier, later], 'yandex':[
            event(hour='18:00'), event(hour='19:30'), event(hour='21:00')]})), 3)
        result = merge_events({'qtickets':[earlier, later], 'yandex':[
            event(hour='18:00'), event(hour='19:30'), event(hour='21:00')]})
        self.assertEqual(next(e for e in result if e['source'] == 'yandex')['starts_at'], event(hour='19:30')['starts_at'])

    def test_overlapping_cross_source_times_match_all_corresponding_sessions(self):
        result = merge_events({'qtickets':[event(hour='18:00'), event(hour='19:30')],
                               'yandex':[event(hour='19:00'), event(hour='20:30')]})
        self.assertEqual(len(result), 2)

    def test_legacy_cache_migrates_and_source_outage_preserves_its_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'events-cache.json').write_text(json.dumps({'events':[event()], 'updated_at':datetime.now().astimezone().isoformat()}))
            calendar = Calendar(root)
            self.assertEqual(len(calendar.payload()['events']), 1)
            with patch('events.fetch_yandex', return_value=[event('Kitana')]):
                calendar.refresh_source('yandex')
            before = copy.deepcopy(calendar.payload())
            with patch('events.fetch_yandex', side_effect=OSError('offline')):
                calendar.refresh_source('yandex')
            after = calendar.payload()
            self.assertEqual(after['events'], before['events'])
            source = next(s for s in after['sources'] if s['id'] == 'yandex')
            self.assertTrue(source['stale'])
            self.assertEqual(source['updated_at'], next(s for s in before['sources'] if s['id'] == 'yandex')['updated_at'])
            self.assertEqual(len(Calendar(root).payload()['events']), 2)

    def test_one_failed_source_does_not_stop_the_other_and_empty_success_clears_old_events(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar = Calendar(Path(directory))
            with patch('events.fetch_catalog', side_effect=OSError('offline')), patch('events.fetch_yandex', return_value=[event('Kitana')]):
                calendar.refresh()
            self.assertEqual([e['title'] for e in calendar.payload()['events']], ['Kitana'])
            with patch('events.fetch_yandex', return_value=[]):
                calendar.refresh_source('yandex')
            self.assertEqual(calendar.payload()['events'], [])
