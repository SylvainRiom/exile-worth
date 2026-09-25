import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import numpy as np

from exile_worth import __version__
from exile_worth.report import STASH_AREA, build_report, safe_name, tab_summary


class ReportTests(unittest.TestCase):
    def test_report_holds_logs_crops_summary_and_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'session.log').write_bytes(b'now\n')
            (data / 'session.log.1').write_bytes(b'before\n')
            (data / 'profiles.json').write_text('{}', 'utf-8')
            frame = np.full((1080, 1920, 3), 40, np.uint8)
            frame[:, 1000:] = 255  # Chat and character: outside the stash area.
            path = data / 'report.zip'
            names = build_report(path, data, {'note': 'Abyss stuck', 'league': 'A'},
                                 [('current', frame), ('Abyss', frame), ('Abyss', frame), ('gone', None)],
                                 [('tab1', 'AB02', 'preserved-cranium', 1, '2026-09-25T19:00:00+00:00', 0)])
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(sorted(archive.namelist()), sorted(names))
                self.assertEqual(sorted(names), ['inventory.csv', 'report.json', 'session.log', 'session.log.1',
                                                 'stash-Abyss-2.png', 'stash-Abyss.png', 'stash-current.png'])
                report = json.loads(archive.read('report.json'))
                self.assertEqual((report['note'], report['version']), ('Abyss stuck', __version__))
                image = cv2.imdecode(np.frombuffer(archive.read('stash-current.png'), np.uint8), cv2.IMREAD_COLOR)
                self.assertEqual(image.shape[1::-1], STASH_AREA)
                self.assertLess(image.max(), 255, 'Nothing right of the stash area is kept')
                self.assertIn('preserved-cranium', archive.read('inventory.csv').decode('utf-8'))
                self.assertEqual(archive.read('session.log.1').decode('utf-8'), 'before\n')

    def test_tab_summary_leaves_out_pixels_and_names_are_file_safe(self):
        tab = dict(id='x', name='$$', league='A', layout_id='currency', rect=[1, 2, 3, 4],
                   label=[[[0, 0, 0]]], layout={'L11': []}, auto_registered=True)
        self.assertEqual(set(tab_summary(tab)), {'id', 'name', 'league', 'layout_id', 'rect', 'auto_registered'})
        self.assertEqual(safe_name('$$'), 'tab')
        self.assertEqual(safe_name('Mes orbes / 2'), 'Mes-orbes-2')


if __name__ == '__main__':
    unittest.main()
