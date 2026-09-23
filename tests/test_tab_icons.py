import json
import unittest

from PIL import Image

from exile_worth.app import TAB_ICONS
from exile_worth.layouts import LAYOUTS, layout_family


class TabIconTests(unittest.TestCase):
    def test_every_stash_family_has_a_verified_icon(self):
        sources = json.loads((TAB_ICONS / 'sources.json').read_text('utf-8'))
        families = {layout_family(layout_id) for layout_id in LAYOUTS}
        self.assertEqual(families, set(sources))
        for family, entry in sources.items():
            with self.subTest(family=family):
                image = Image.open(TAB_ICONS / f'{family}.png')
                self.assertEqual(list(image.size), entry['size'])
                self.assertEqual(image.mode, 'RGBA')
                self.assertTrue(entry['source'].startswith('https://poe2db.tw/'))
