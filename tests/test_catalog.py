import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from exile_worth.catalog import reference_items, with_reference_items
from exile_worth.icons import IconMatcher, fetch_icons
from exile_worth.layouts import EXPEDITION_SLOTS
from exile_worth.model import estimate_readings
from exile_worth.pricing import Ninja
from exile_worth.vision import Profiles, Scanner
from tests.test_icons import render
from tools.update_item_catalog import CatalogueParser


class CatalogueTests(unittest.TestCase):
    def test_reference_identification_does_not_create_prices_or_replace_current_metadata(self):
        market = dict(items={'verisium': {'id': 'verisium', 'name': 'Current name'}},
                      prices={'divine': 1}, primary='divine', fetched=1, stale=False)
        merged = with_reference_items(market)
        self.assertEqual(merged['items']['verisium']['name'], 'Current name')
        self.assertTrue(merged['items']['verisium']['image'].startswith('https://'))
        self.assertIn('adaptive-alloy', merged['items'])
        self.assertEqual(merged['prices'], {'divine': 1})
        self.assertNotIn('adaptive-alloy', market['items'])

    def test_reference_catalogue_survives_unavailable_economy_and_has_no_foreign_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Ninja(cache=Path(directory))
            with patch.object(client, 'overview', side_effect=OSError('offline')):
                market = client.stash_market('A')
            self.assertIn('verisium', market['items'])
            self.assertEqual(market['prices'], {})
            self.assertEqual(market['unavailable_categories'],
                             ['Currency', 'Expedition', 'Verisium', 'Breach', 'Runes', 'SoulCores', 'Idols'])

    def test_expedition_tab_is_priced_from_both_overviews(self):
        """Alloys, crests and Verisium live in the `Verisium` overview, not `Expedition`."""
        overviews = {
            'Currency': dict(items={'divine': {'name': 'Divine Orb'}}, prices={'divine': 1},
                             primary='divine', fetched=1, stale=False),
            'Expedition': dict(items={'uhtreds-saga': {'name': "Uhtred's Saga"}},
                               prices={'uhtreds-saga': 1.76}, primary='divine', fetched=1, stale=False),
            'Verisium': dict(items={'sovereign-alloy': {'name': 'Sovereign Alloy'},
                                    'voranas-crest-of-the-scythe': {'name': "Vorana's Crest of the Scythe"}},
                             prices={'sovereign-alloy': .31, 'voranas-crest-of-the-scythe': .0017},
                             primary='divine', fetched=1, stale=False),
        }
        def overview(_league, category):
            if category in overviews:
                return overviews[category]
            raise OSError('not needed here')
        with tempfile.TemporaryDirectory() as directory:
            client = Ninja(cache=Path(directory))
            with patch.object(client, 'overview', side_effect=overview):
                market = client.stash_market('A')
        self.assertEqual(market['prices']['sovereign-alloy'], .31)
        self.assertEqual(market['prices']['voranas-crest-of-the-scythe'], .0017)
        self.assertEqual(market['prices']['uhtreds-saga'], 1.76)
        self.assertNotIn('Verisium', market['unavailable_categories'])

    def test_currency_prices_survive_missing_expedition(self):
        currency = dict(items={}, prices={'divine': 1}, primary='divine', fetched=1, stale=False)
        with tempfile.TemporaryDirectory() as directory:
            client = Ninja(cache=Path(directory))
            def overview(_league, category):
                if category == 'Currency':
                    return currency
                raise OSError('offline')
            with patch.object(client, 'overview', side_effect=overview):
                market = client.stash_market('A')
        self.assertEqual(market['prices'], currency['prices'])
        self.assertIn('aldurs-saga', market['items'])

    def test_rune_soul_core_and_idol_prices_join_currency_market(self):
        currency = dict(items={'divine': {'id': 'divine'}}, prices={'divine': 1},
                        primary='divine', fetched=1, stale=False)
        categories = {'Runes': 'rune', 'SoulCores': 'soul-core', 'Idols': 'idol'}
        def overview(_league, category):
            if category == 'Currency':
                return currency
            if category in categories:
                item = categories[category]
                return dict(items={item: {'id': item}}, prices={item: 2},
                            primary='divine', fetched=1, stale=False)
            raise OSError('offline')
        with tempfile.TemporaryDirectory() as directory:
            client = Ninja(cache=Path(directory))
            with patch.object(client, 'overview', side_effect=overview):
                market = client.stash_market('A')
        self.assertEqual(market['prices']['rune'], 2)
        self.assertEqual(market['prices']['soul-core'], 2)
        self.assertEqual(market['prices']['idol'], 2)
        self.assertEqual(market['unavailable_categories'], ['Expedition', 'Verisium', 'Breach'])

    def test_scraper_excludes_navigation_prices_and_price_currencies(self):
        parser = CatalogueParser('https://poe2db.tw/us/Economy_Expedition', 'Expedition')
        icon = '<img src="https://web.poecdn.com/test.png">'
        parser.feed(f'<a href="Economy_Currency">{icon}Currency</a><table><tr><td>'
                    f'<a href="Economy_verisium">{icon}Verisium</a></td>'
                    f'<td>999<a href="Economy_divine">{icon}Divine Orb</a></td></tr></table>')
        self.assertEqual(list(parser.items), ['verisium'])
        self.assertEqual(parser.items['verisium']['name'], 'Verisium')
        self.assertNotIn('price', parser.items['verisium'])

    def test_shared_icons_use_one_download_and_then_cache(self):
        fixture = Path(__file__).parent / 'fixtures/expedition/verisium.png'
        items = {key: {'image': 'https://web.poecdn.com/test.png'} for key in ('a', 'b')}
        with tempfile.TemporaryDirectory() as directory:
            with patch('exile_worth.icons.urlopen') as request:
                request.return_value.__enter__.return_value.read.return_value = fixture.read_bytes()
                images, errors = fetch_icons(items, directory)
                self.assertEqual(request.call_count, 1)
            with patch('exile_worth.icons.urlopen', side_effect=AssertionError('Network on cache hit')):
                cached, errors = fetch_icons(items, directory)
        self.assertEqual(list(images), ['a', 'b'])
        self.assertEqual(list(cached), ['a', 'b'])
        self.assertFalse(errors)


class ExpeditionArtworkTests(unittest.TestCase):
    """Real CDN artwork composited into synthetic cells, not game screenshots."""
    @classmethod
    def setUpClass(cls):
        cls.images = {file.stem: cv2.imread(str(file), cv2.IMREAD_UNCHANGED)
                      for file in (Path(__file__).parent / 'fixtures/expedition').glob('*.png')}
        cls.images['thaumaturgic-flux-13'] = cls.images['thaumaturgic-flux-20']
        cls.matcher = IconMatcher(cls.images)

    def test_real_reference_icons_identified_with_different_counters(self):
        for key, icon in self.images.items():
            for size, counter in ((44, '45.6K'), (48, '2'), (51, '225')):
                with self.subTest(item=key, size=size):
                    match = self.matcher.match_many([render(icon, size, counter)])[0]
                    self.assertIn(key, match.alternatives)
                    if key.startswith('thaumaturgic'):
                        self.assertIsNone(match.item)

    def test_dark_empty_silhouettes_never_become_inventory(self):
        for icon in self.images.values():
            dark = (render(icon).astype(float)*.2).astype(np.uint8)
            self.assertFalse(self.matcher.match_many([dark])[0].alternatives)

    def test_off_centre_artwork_keeps_its_identity(self):
        for key, icon in self.images.items():
            for dx,dy in ((4,3), (-4,-3), (2,-2)):
                with self.subTest(item=key, offset=(dx,dy)):
                    cell = cv2.warpAffine(render(icon, 48), np.float32([[1,0,dx],[0,1,dy]]),
                                          (52,51), borderValue=(14,9,5))
                    self.assertIn(key, self.matcher.match_many([cell])[0].alternatives)

    def test_expedition_scan_names_unpriced_item_without_calibration(self):
        class Digits:
            last_approximate = True
            def read(self, image):
                return 45600, .99

        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), Digits(), self.matcher)
            frame = np.zeros((1080, 1920, 3), np.uint8)
            x,y,w,h = EXPEDITION_SLOTS['E09']
            frame[y:y+h, x:x+w] = cv2.resize(render(self.images['verisium'], 48, '45.6K'), (w,h))
            reading = scanner.read(frame, 'expedition', ['E09'])[0]
        self.assertEqual(reading.item, 'verisium')
        self.assertEqual(reading.quantity, 45600)
        self.assertTrue(reading.approximate)
        self.assertEqual(estimate_readings([reading], {'divine': 1}, 'divine').unpriced, 1)
