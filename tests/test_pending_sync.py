import tempfile
import unittest
from pathlib import Path

from exile_worth.model import Reading, Reason, Store


class PendingSyncTests(unittest.TestCase):
    """A cell being re-confirmed keeps its confirmed row; a failed read flags it."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / 'inventory.sqlite')
        self.store.sync('A', 'tab', [Reading('C01', 'divine', 141)])

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def row(self):
        return self.store.rows('A')[0]

    def test_pending_leaves_the_confirmed_row_untouched(self):
        before = self.row()
        self.assertFalse(self.store.sync('A', 'tab', [Reading('C01', 'divine', None, .99, Reason.PENDING)]))
        self.assertEqual(self.row(), before)
        self.assertEqual(self.row()[5], 0)

    def test_an_unreadable_count_still_flags_the_row(self):
        self.store.sync('A', 'tab', [Reading('C01', 'divine', None, .99, Reason.UNREADABLE_COUNT)])
        self.assertEqual(self.row()[3], 141)
        self.assertEqual(self.row()[5], 1)

    def test_an_unknown_icon_still_flags_the_row(self):
        self.store.sync('A', 'tab', [Reading('C01', None, None, 0, Reason.UNKNOWN_ICON)])
        self.assertEqual(self.row()[5], 1)

    def test_a_confirmed_reading_clears_an_old_flag(self):
        self.store.sync('A', 'tab', [Reading('C01', 'divine', None, .99, Reason.UNREADABLE_COUNT)])
        self.store.sync('A', 'tab', [Reading('C01', 'divine', 141)])
        self.assertEqual(self.row()[5], 0)
