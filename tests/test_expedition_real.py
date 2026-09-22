"""Regression on the user's actual 1920x1080 capture, cropped to the stash."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from unittest.mock import patch

from exile_worth.model import Reason
from exile_worth.icons import IconMatcher
from exile_worth.layouts import LEGACY_EXPEDITION_SLOTS
from exile_worth.vision import Profiles, Scanner, active_tab


class RealExpeditionTests(unittest.TestCase):
    def test_active_highlight_registers_once_and_arrow_confirms_title(self):
        from rapidocr_onnxruntime import RapidOCR
        stash = np.zeros((1080,1920,3),np.uint8)
        fixture = Path(__file__).parent/'fixtures/expedition_real'
        stash[:765,:645] = cv2.imread(str(fixture/'stash.png'))
        expanded = stash.copy()
        expanded[340:383,666:855] = cv2.imread(str(fixture/'selection.png'))
        ocr = RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
        self.assertEqual(active_tab(expanded,ocr)[0], 'SAGA')
        self.assertEqual(active_tab(stash,ocr)[0], 'SAGA')
        with tempfile.TemporaryDirectory() as temporary:
            profiles = Profiles(Path(temporary))
            first, _ = profiles.observe(stash,'A','expedition',ocr)
            again, _ = profiles.observe(stash,'A','expedition',ocr)
            self.assertEqual(first['id'],again['id'])
            self.assertEqual(len(profiles.data['tabs']),1)
            self.assertEqual(profiles.identify(stash,'A')[0]['id'],first['id'])
            moved = stash.copy()
            moved[121,500:591] = moved[126,500:591]
            moved[121,100:188] = stash[121,500:588]
            self.assertEqual(active_tab(moved,ocr)[0], 'Gems')
            self.assertIsNone(profiles.identify(moved,'A')[0])
            conflicting = moved.copy()
            conflicting[340:383,666:855] = expanded[340:383,666:855]
            self.assertIsNone(active_tab(conflicting,ocr))
            self.assertIsNone(profiles.observe(conflicting,'A','expedition',ocr)[0])
            second, _ = profiles.observe(moved,'A','expedition',ocr)
            self.assertNotEqual(first['id'],second['id'])
            self.assertEqual(len(profiles.data['tabs']),2)
            blank = stash.copy()
            blank[121,40:594] = 0
            self.assertIsNone(active_tab(blank,ocr))
            self.assertIsNone(profiles.observe(blank,'A','expedition',ocr)[0])

    def test_symbol_only_currency_tab_is_registered_and_reused(self):
        from rapidocr_onnxruntime import RapidOCR
        frame = np.zeros((1080,1920,3),np.uint8)
        fixture = Path(__file__).parent/'fixtures/expedition_real/stash.png'
        frame[:765,:645] = cv2.imread(str(fixture))
        frame[121,500:591] = frame[126,500:591]  # SAGA is no longer selected.
        menu = Path(__file__).parent/'fixtures/tab_labels/dollar_selected_menu.png'
        frame[182:225,666:855] = cv2.imread(str(menu))
        ocr = RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
        self.assertEqual(active_tab(frame,ocr)[0], '$$')
        with tempfile.TemporaryDirectory() as temporary:
            profiles = Profiles(Path(temporary))
            tab,reason = profiles.observe(frame,'A','currency',ocr)
            self.assertEqual((tab['name'],tab['layout_id']),('$$','currency'))
            self.assertEqual(profiles.observe(frame,'A','currency',ocr)[0]['id'],tab['id'])
            self.assertEqual(Profiles(Path(temporary)).identify(frame,'A')[0]['id'],tab['id'])

    def test_unique_tab_keeps_uuid_after_horizontal_reordering(self):
        frame = np.zeros((1080,1920,3),np.uint8)
        old_rect, new_rect = (45,97,71,27), (363,97,71,27)
        frame[old_rect[1]:old_rect[1]+old_rect[3],old_rect[0]:old_rect[0]+old_rect[2]] = 80
        frame[new_rect[1]:new_rect[1]+new_rect[3],new_rect[0]:new_rect[0]+new_rect[2]] = 120
        with tempfile.TemporaryDirectory() as temporary:
            profiles = Profiles(Path(temporary))
            with patch('exile_worth.vision.active_tab', return_value=('$$', old_rect)):
                first, _ = profiles.observe(frame,'A','currency',object())
            with patch('exile_worth.vision.active_tab', return_value=('$$', new_rect)):
                moved, reason = profiles.observe(frame,'A','currency',object())
            self.assertEqual(moved['id'],first['id'])
            self.assertEqual(moved['rect'],new_rect)
            self.assertIn('new position',reason)
            self.assertEqual(len(profiles.data['tabs']),1)

    def test_real_items_counts_and_empty_slots(self):
        directory = Path(__file__).parent/'fixtures'/'expedition_real'
        frame = np.zeros((1080,1920,3),np.uint8)
        frame[:765,:645] = cv2.imread(str(directory/'stash.png'))
        images = {file.stem:cv2.imread(str(file),cv2.IMREAD_UNCHANGED)
                  for file in (directory/'icons').glob('*.png')}
        expected = {
            'E01':('expedition-logbook',10), 'E03':('medveds-saga',9),
            'E04':('voranas-saga',8), 'E05':('uhtreds-saga',4), 'E06':('olroths-saga',2),
            'E09':('verisium',38300), 'E10':('exceptional-verisium',225),
            'E12':('medveds-crest-of-the-circle',2), 'E13':('voranas-crest-of-the-scythe',1),
            'E15':('olroths-crest-of-the-sun',6), 'E16':('runic-alloy',2),
            'E17':('adaptive-alloy',1), 'E18':('protective-alloy',3),
            'E19':('expansive-alloy',1), 'E20':('swift-alloy',6),
            'E21':('cyclonic-alloy',8), 'E22':('prismatic-alloy',15),
            'E23':('mystic-alloy',2), 'E24':('sovereign-alloy',4),
            'E26':('transcendent-alloy',2), 'E28':('the-runefathers-alloy',1),
            'E29':('blazing-flux',11), 'E30':('chilling-flux',6),
            'E31':('crackling-flux',11), 'E32':('void-flux',3),
        }
        with tempfile.TemporaryDirectory() as temporary:
            scanner = Scanner(Profiles(Path(temporary)), matcher=IconMatcher(images))
            self.assertEqual(scanner.detect_layout(frame), 'expedition')
            readings = scanner.read(frame, 'expedition')
        for reading in readings:
            with self.subTest(slot=reading.slot):
                if reading.slot in expected:
                    self.assertEqual((reading.item,reading.quantity),expected[reading.slot])
                    self.assertEqual(reading.approximate, reading.slot == 'E09')
                else:
                    self.assertIsNone(reading.item)
                    self.assertIsNone(reading.quantity)
                    self.assertFalse(reading.alternatives)
                    self.assertEqual(reading.reason, Reason.EMPTY)

    def test_old_expedition_profile_keeps_its_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            profiles = Profiles(Path(temporary))
            frame = np.random.default_rng(32).integers(0,255,(1080,1920,3),dtype=np.uint8)
            tab = profiles.register('SAGA', 'A', (500,96,80,25), frame, 'expedition')
            identity = tab['id']
            self.assertEqual(profiles.identify(frame,'A')[0]['id'],identity)
            tab.pop('anchor_rects')
            tab['layout'] = {slot:frame[y-3:y,x-3:x+w+3].tolist()
                             for slot,(x,y,w,h) in LEGACY_EXPEDITION_SLOTS.items()}
            profiles.save()
            reloaded = Profiles(Path(temporary))
            self.assertEqual(reloaded.identify(frame,'A')[0]['id'],identity)
