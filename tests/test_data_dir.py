import tempfile
import unittest
from pathlib import Path

from exile_worth.model import Store, Reading, data_directory, migrate_legacy_data


class DataDirectoryTests(unittest.TestCase):
    def test_override_then_local_app_data_then_legacy(self):
        legacy = Path('legacy')
        self.assertEqual(data_directory({'EXILE_DATA_DIR': 'x', 'LOCALAPPDATA': 'y'}, legacy), Path('x'))
        self.assertEqual(data_directory({'LOCALAPPDATA': 'y'}, legacy), Path('y') / 'ExileWorth')
        self.assertEqual(data_directory({}, legacy), legacy)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.legacy, self.target = root / 'repo' / 'data', root / 'local' / 'ExileWorth'
        self.legacy.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def fill_legacy(self):
        store = Store(self.legacy / 'inventory.sqlite3')
        store.sync('League', 'uuid-1', [Reading('L11', 'exalted', 12)])
        store.close()
        (self.legacy / 'profiles.json').write_text('{"tabs": {"uuid-1": {}}}', 'utf-8')
        (self.legacy / 'icons').mkdir()
        (self.legacy / 'icons' / 'a.png').write_bytes(b'png')

    def test_copies_inventory_and_keeps_the_original(self):
        self.fill_legacy()
        self.assertTrue(migrate_legacy_data(self.target, self.legacy))
        store = Store(self.target / 'inventory.sqlite3')
        self.assertEqual(store.rows('League')[0][3], 12)
        store.close()
        self.assertEqual((self.target / 'profiles.json').read_text('utf-8'), '{"tabs": {"uuid-1": {}}}')
        self.assertTrue((self.target / 'icons' / 'a.png').exists())
        self.assertTrue((self.legacy / 'inventory.sqlite3').exists(), 'The old folder stays as a backup')
        self.assertTrue((self.legacy / 'MOVED.txt').exists())
        self.assertFalse(self.target.with_name('ExileWorth.migrating').exists())

    def test_never_overwrites_an_existing_target(self):
        self.fill_legacy()
        self.target.mkdir(parents=True)
        (self.target / 'profiles.json').write_text('{"new": 1}', 'utf-8')
        self.assertFalse(migrate_legacy_data(self.target, self.legacy))
        self.assertEqual((self.target / 'profiles.json').read_text('utf-8'), '{"new": 1}')
        self.assertFalse((self.target / 'inventory.sqlite3').exists())

    def test_a_log_or_cache_written_first_does_not_block(self):
        self.fill_legacy()
        (self.target / 'icons').mkdir(parents=True)
        (self.target / 'icons' / 'b.png').write_bytes(b'png')
        (self.target / 'session.log').write_text('started', 'utf-8')
        self.assertTrue(migrate_legacy_data(self.target, self.legacy))
        self.assertTrue((self.target / 'inventory.sqlite3').exists())
        self.assertTrue((self.target / 'icons' / 'a.png').exists())

    def test_a_folder_of_caches_only_is_not_migrated(self):
        (self.legacy / 'prices').mkdir()
        (self.legacy / 'session.log').write_text('old', 'utf-8')
        self.assertFalse(migrate_legacy_data(self.target, self.legacy))
        self.assertFalse(self.target.exists())

    def test_runs_once(self):
        self.fill_legacy()
        self.assertTrue(migrate_legacy_data(self.target, self.legacy))
        self.assertFalse(migrate_legacy_data(self.target, self.legacy))

    def test_nothing_to_migrate(self):
        self.assertFalse(migrate_legacy_data(self.target, self.legacy))
        self.assertFalse(self.target.exists())
        self.assertFalse(migrate_legacy_data(self.target, self.target.parent / 'missing'))

    def test_same_folder_is_left_alone(self):
        self.fill_legacy()
        self.assertFalse(migrate_legacy_data(self.legacy, self.legacy))
        self.assertFalse((self.legacy / 'MOVED.txt').exists())

    def test_stale_staging_from_an_interrupted_copy_is_replaced(self):
        self.fill_legacy()
        staging = self.target.with_name('ExileWorth.migrating')
        staging.mkdir(parents=True)
        (staging / 'partial').write_text('half', 'utf-8')
        self.assertTrue(migrate_legacy_data(self.target, self.legacy))
        self.assertFalse((self.target / 'partial').exists())


if __name__ == '__main__':
    unittest.main()
