"""The catalogues must stay in step, because a drift only breaks one language.

A key present in English and missing in French falls back silently, so the bug
looks like an untranslated string. A `{placeholder}` that differs between the two
is worse: `.format()` raises, but only for the language that has the wrong name,
so the English-speaking author never sees it.
"""
import re
import unittest

from exile_worth import i18n
from exile_worth.i18n import CATALOG, DEFAULT, LANGUAGES
from exile_worth.model import Event, Reason

PLACEHOLDER = re.compile(r'\{(\w+)')


def placeholders(text):
    return set(PLACEHOLDER.findall(text))


class CatalogueTests(unittest.TestCase):
    def test_every_declared_language_has_a_catalogue(self):
        self.assertEqual(set(LANGUAGES), set(CATALOG))
        self.assertIn(DEFAULT, CATALOG)

    def test_all_catalogues_share_the_same_keys(self):
        reference = set(CATALOG[DEFAULT])
        for code, catalogue in CATALOG.items():
            with self.subTest(code):
                missing = reference - set(catalogue)
                extra = set(catalogue) - reference
                self.assertFalse(missing, f'{code} is missing {sorted(missing)}')
                self.assertFalse(extra, f'{code} has keys {sorted(extra)} that {DEFAULT} lacks')

    def test_placeholders_match_across_languages(self):
        """A mismatch raises inside .format(), in one language only."""
        for key, text in CATALOG[DEFAULT].items():
            expected = placeholders(text)
            for code, catalogue in CATALOG.items():
                with self.subTest(f'{code}.{key}'):
                    self.assertEqual(placeholders(catalogue[key]), expected,
                                     f'{code}.{key} does not take the same fields')

    def test_no_entry_is_empty(self):
        for code, catalogue in CATALOG.items():
            for key, text in catalogue.items():
                with self.subTest(f'{code}.{key}'):
                    self.assertTrue(text.strip(), f'{code}.{key} is blank')


class StoredKeyTests(unittest.TestCase):
    """`Reason` and `Event` values are written to SQLite and compared in logic."""

    def values(self, holder):
        return [v for k, v in vars(holder).items() if not k.startswith('_')]

    def test_every_reason_and_event_has_a_label_in_every_language(self):
        for holder, prefix in ((Reason, 'reason.'), (Event, 'event.')):
            for value in self.values(holder):
                for code, catalogue in CATALOG.items():
                    with self.subTest(f'{code}.{prefix}{value}'):
                        self.assertIn(prefix + value, catalogue)

    def test_stored_keys_are_ascii_and_stable_looking(self):
        """A key that is a translated word would break on the next language switch."""
        for holder in (Reason, Event):
            for value in self.values(holder):
                with self.subTest(value):
                    self.assertRegex(value, r'^[a-z][a-z0-9_]*$')

    def test_keys_are_distinct(self):
        for holder in (Reason, Event):
            values = self.values(holder)
            self.assertEqual(len(values), len(set(values)))


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.previous = i18n.language()

    def tearDown(self):
        i18n._current = self.previous

    def test_translation_follows_the_selected_language(self):
        i18n._current = 'en'
        english = i18n.t('reason.empty')
        i18n._current = 'fr'
        self.assertNotEqual(i18n.t('reason.empty'), english)

    def test_an_unknown_key_returns_itself_rather_than_raising(self):
        self.assertEqual(i18n.t('no.such.key'), 'no.such.key')

    def test_a_missing_translation_falls_back_to_english(self):
        i18n._current = 'fr'
        try:
            CATALOG['fr'].pop('reason.empty')
            self.assertEqual(i18n.t('reason.empty'), CATALOG['en']['reason.empty'])
        finally:
            CATALOG['fr']['reason.empty'] = 'Case vide'

    def test_fields_are_substituted(self):
        i18n._current = 'en'
        self.assertIn('SAGA', i18n.t('status.synced', name='SAGA'))

    def test_every_key_formats_with_its_own_placeholders(self):
        """Catches a stray brace that would raise only when that string is shown."""
        for code, catalogue in CATALOG.items():
            i18n._current = code
            for key, text in catalogue.items():
                with self.subTest(f'{code}.{key}'):
                    fields = {name: 1 for name in placeholders(text)}
                    i18n.t(key, **fields)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.previous = i18n.language()

    def tearDown(self):
        i18n._current = self.previous

    def test_language_round_trips_through_the_settings_file(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            i18n.set_language('fr', directory)
            self.assertTrue((Path(directory) / 'settings.json').exists())
            i18n._current = 'en'
            self.assertEqual(i18n.load_language(directory), 'fr')

    def test_a_damaged_settings_file_falls_back_to_the_default(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'settings.json').write_text('{ not json', encoding='utf-8')
            self.assertEqual(i18n.load_language(directory), DEFAULT)

    def test_an_unknown_stored_language_falls_back(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'settings.json').write_text(
                json.dumps({'language': 'klingon'}), encoding='utf-8')
            self.assertEqual(i18n.load_language(directory), DEFAULT)

    def test_setting_an_unknown_language_is_refused(self):
        with self.assertRaises(ValueError):
            i18n.set_language('klingon')


if __name__ == '__main__':
    unittest.main()
