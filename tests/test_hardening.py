"""Four small defects that each had a quiet failure mode.

None of them showed up as a crash: a redirected download, a cache that keeps
serving a stale catalogue, a connection that is never closed, and a function kept
alive only by its own tests.
"""
import itertools
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from joy_tracker import icons as icons_module, model
from joy_tracker.icons import ICON_HOSTS, IconMatcher, fetch_icons
from joy_tracker.vision import Profiles, Scanner


class IconSourceTests(unittest.TestCase):
    """The scheme check passed for an absolute URL to any https host."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self, source):
        with patch.object(icons_module, 'urlopen') as opener:
            images, errors = fetch_icons({'x': {'image': source}}, directory=self.directory)
            return images, errors, opener.call_count

    def test_a_relative_path_still_resolves_on_the_cdn(self):
        self.assertIn('web.poecdn.com', ICON_HOSTS)
        with patch.object(icons_module, 'urlopen') as opener:
            opener.side_effect = OSError('no network in tests')
            _images, errors = fetch_icons({'x': {'image': '/gen/image/abc.png'}},
                                          directory=self.directory)
            self.assertEqual(opener.call_count, 1, 'a CDN path must still be fetched')
            self.assertEqual(errors, ['x'])

    def test_an_absolute_url_to_another_host_is_refused_without_a_request(self):
        images, errors, requests = self.fetch('https://evil.example/x.png')
        self.assertEqual(requests, 0, 'nothing must be downloaded from an outside host')
        self.assertEqual(errors, ['x'])
        self.assertEqual(images, {})

    def test_a_non_https_url_is_still_refused(self):
        _images, errors, requests = self.fetch('http://web.poecdn.com/x.png')
        self.assertEqual(requests, 0)
        self.assertEqual(errors, ['x'])

    def test_credentials_cannot_smuggle_the_host_past_the_check(self):
        """urlparse().hostname ignores user:pass@, unlike a netloc comparison."""
        _images, errors, requests = self.fetch('https://web.poecdn.com@evil.example/x.png')
        self.assertEqual(requests, 0)
        self.assertEqual(errors, ['x'])


class MatcherRevisionTests(unittest.TestCase):
    def test_every_matcher_gets_a_distinct_revision(self):
        first, second = IconMatcher({}), IconMatcher({})
        self.assertNotEqual(first.revision, second.revision)

    def test_a_rebuilt_matcher_invalidates_the_incremental_cache(self):
        """id() can be reused after collection, which would keep a stale catalogue."""
        with tempfile.TemporaryDirectory() as directory:
            class Digits:
                last_approximate = False
                def read(self, image):
                    return None, 0.0

            scanner = Scanner(Profiles(Path(directory)), digits=Digits(), matcher=IconMatcher({}))
            frame = np.zeros((1080, 1920, 3), np.uint8)
            scanner.read_incremental(frame, 'currency', ('league', 'tab'))
            before = scanner.live_config
            scanner.matcher = IconMatcher({})
            scanner.read_incremental(frame, 'currency', ('league', 'tab'))
            self.assertNotEqual(scanner.live_config, before,
                                'a new catalogue must not reuse cached identifications')

    def test_the_revision_is_what_the_cache_key_uses(self):
        matcher = IconMatcher({})
        self.assertIsInstance(matcher.revision, int)
        self.assertNotIn(matcher.revision, (id(matcher),),
                         'the key must not be derived from id()')


class ConnectionLifetimeTests(unittest.TestCase):
    def test_the_profile_lookup_closes_its_connection(self):
        """`with sqlite3.connect(...)` commits but leaves the handle open."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = model.Store(path / 'inventory.sqlite3')
            store.close()
            profiles = Profiles(path)
            opened = []
            real_connect = sqlite3.connect

            def tracking_connect(*args, **kwargs):
                connection = real_connect(*args, **kwargs)
                opened.append(connection)
                return connection

            with patch('joy_tracker.vision.sqlite3.connect', tracking_connect):
                profiles._no_stored_inventory('some-tab')
            self.assertEqual(len(opened), 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].execute('SELECT 1')


class DeadCodeTests(unittest.TestCase):
    def test_value_inventory_is_gone(self):
        """It was superseded by estimate_readings and kept alive by its own tests."""
        self.assertFalse(hasattr(model, 'value_inventory'))


if __name__ == '__main__':
    unittest.main()
