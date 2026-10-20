import unittest
from qtickets import parse_catalog


def card(place='СПОТ', url='https://blagoveshensk.qtickets.events/123-test', day='2026-10-25'):
    return f'''<li class="item"><section><a href="{url}">
    <div class="img jpg" style="background-image: url('https://cdn.qtickets.tech/thumbs/poster.webp')">
    <div class="price for-desktop">от 1 390 руб.</div></div>
    <h2>Ночь &amp; музыка</h2><div class="type">Вечеринка</div>
    <time datetime="{day}T20:00:00+09:00"><span class="place-name">{place}&nbsp;</span></time>
    </a></section></li>'''


class QticketsTests(unittest.TestCase):
    def test_filters_venue_parses_date_price_and_link(self):
        events, more = parse_catalog(card()+card('Дизель')+card('НК Спот', day='2026-10-30'))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]['title'], 'Ночь & музыка')
        self.assertEqual(events[0]['starts_at'], '2026-10-25T20:00:00+09:00')
        self.assertEqual(events[0]['price'], 'от 1 390 ₽')
        self.assertTrue(events[0]['url'].startswith('https://blagoveshensk.qtickets.events/'))
        self.assertFalse(more)

    def test_pagination_and_external_links(self):
        events, more = parse_catalog(card(url='javascript:alert(1)')+'<a id="next_page" href="/?page=2">Ещё</a>')
        self.assertEqual(events, [])
        self.assertTrue(more)

    def test_invalid_remote_document_is_not_an_empty_success(self):
        with self.assertRaises(ValueError):
            parse_catalog('<html><h1>Service unavailable</h1></html>')
        events, _ = parse_catalog(card('Дизель'))
        self.assertEqual(events, [])

    def test_uses_largest_published_poster_instead_of_catalogue_thumbnail(self):
        thumbnail = 'https://cdn.qtickets.tech/thumbs/616235_360_0_0_0_auto_90_small.webp'
        large = 'https://cdn.qtickets.tech/thumbs/616235_1080_0_0_0_restricted_90_large.webp'
        medium = 'https://cdn.qtickets.tech/thumbs/616235_720_0_0_0_restricted_90_medium.webp'
        document = card().replace(
            "background-image: url('https://cdn.qtickets.tech/thumbs/poster.webp')",
            f"background-image: url('{thumbnail}'); background-image: image-set("
            f'url(&quot;{large}&quot;) 3x, url(&quot;{medium}&quot;) 2x, '
            f'url(&quot;{thumbnail}&quot;) 1x)')
        events, _ = parse_catalog(document)
        self.assertEqual(events[0]['poster'], large)

    def test_ignores_untrusted_or_unrelated_high_resolution_images(self):
        thumbnail = 'https://cdn.qtickets.tech/thumbs/616235_360_0_0_0_auto_90_small.webp'
        document = card().replace(
            "background-image: url('https://cdn.qtickets.tech/thumbs/poster.webp')",
            f"background-image: url('{thumbnail}'); background-image: image-set("
            'url(&quot;https://evil.test/thumbs/616235_2000_large.webp&quot;) 3x, '
            'url(&quot;https://cdn.qtickets.tech/thumbs/999999_2000_unrelated.webp&quot;) 4x)')
        events, _ = parse_catalog(document)
        self.assertEqual(events[0]['poster'], thumbnail)


if __name__ == '__main__':
    unittest.main()
