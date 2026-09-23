import itertools
import queue
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from exile_worth.app import App
from exile_worth.model import Reason, Reading
from exile_worth.vision import Scanner, Profiles
from tests.test_incremental import Digits, Matcher


class LimitedLoop:
    def __init__(self, steps=10):
        self.steps = steps

    def wait(self, _seconds):
        self.steps -= 1
        return self.steps <= 0

    def is_set(self):
        return self.steps <= 0


class LiveLoopTests(unittest.TestCase):
    def test_real_capture_auto_registers_once_during_live_tracking(self):
        import cv2
        from rapidocr_onnxruntime import RapidOCR

        class OCRDigits:
            def __init__(self):
                self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
            def read(self, image):
                return 10, .99

        frame = np.zeros((1080,1920,3),np.uint8)
        fixture = Path(__file__).parent/'fixtures/expedition_real/stash.png'
        frame[:765,:645] = cv2.imread(str(fixture))
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            scanner = Scanner(profiles, OCRDigits(), Matcher())
            app = SimpleNamespace(stop_event=LimitedLoop(5), messages=queue.Queue(), scanner=scanner,
                                  profiles=profiles, layout_override=None)
            app.resolve_layout = lambda image,tab: App.resolve_layout(app,image,tab)
            app.may_register = lambda: App.may_register(app)
            with patch('exile_worth.app.capture_game',return_value=frame):
                App.live_loop(app,'A')
            messages = list(app.messages.queue)
            self.assertFalse(any(kind=='error' for kind,_ in messages),messages)
            self.assertEqual(len(profiles.data['tabs']),1)
            tab = profiles.data['tabs'][0]
            self.assertEqual((tab['name'],tab['layout_id']),('SAGA','expedition'))
            self.assertTrue(all(payload.tab['id']==tab['id'] for kind,payload in messages if kind=='live'))
            reloaded = Profiles(Path(directory))
            self.assertEqual(reloaded.identify(frame,'A')[0]['id'],tab['id'])

    def test_symbol_currency_tab_auto_registers_in_live_loop(self):
        import cv2
        from rapidocr_onnxruntime import RapidOCR
        from exile_worth.layouts import LAYOUTS

        class OCRDigits:
            def __init__(self):
                self.ocr = RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
            def read(self,image):
                return 10,.99

        frame = np.zeros((1080,1920,3),np.uint8)
        fixture = Path(__file__).parent/'fixtures'
        frame[:765,:645] = cv2.imread(str(fixture/'expedition_real/stash.png'))
        frame[121,500:591] = frame[126,500:591]
        frame[182:225,666:855] = cv2.imread(str(fixture/'tab_labels/dollar_selected_menu.png'))
        frame[140:765,:645] = 0
        for x,y,w,h in LAYOUTS['currency'].slots.values():
            cv2.rectangle(frame,(x,y),(x+w,y+h),(90,110,140),2)
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            scanner = Scanner(profiles, OCRDigits(), Matcher())
            app = SimpleNamespace(stop_event=LimitedLoop(5),messages=queue.Queue(),scanner=scanner,
                                  profiles=profiles,layout_override=None)
            app.resolve_layout = lambda image,tab: App.resolve_layout(app,image,tab)
            app.may_register = lambda: App.may_register(app)
            with patch('exile_worth.app.capture_game',return_value=frame):
                App.live_loop(app,'A')
            messages = list(app.messages.queue)
            self.assertFalse(any(kind=='error' for kind,_ in messages),messages)
            self.assertEqual(len(profiles.data['tabs']),1)
            tab = profiles.data['tabs'][0]
            self.assertEqual((tab['name'],tab['layout_id']),('$$','currency'))
            self.assertTrue(all(payload.tab['id']==tab['id'] for kind,payload in messages if kind=='live'))

    def test_real_resolver_and_incremental_scanner_switch_structures(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            currency = np.full((1080,1920,3),12,np.uint8)
            expedition = np.full_like(currency,80)
            a = profiles.register('Currency','A',(140,96,65,27),currency,'currency')
            b = profiles.register('Expedition','A',(140,96,65,27),expedition,'expedition')
            scanner = Scanner(profiles, Digits(), Matcher())
            app = SimpleNamespace(stop_event=LimitedLoop(13), messages=queue.Queue(), scanner=scanner,
                                  profiles=profiles, layout_override=None, active_layout_id='currency')
            app.resolve_layout = lambda frame,tab: App.resolve_layout(app,frame,tab)
            app.may_register = lambda: App.may_register(app)
            ticks = itertools.count()
            frames = [currency]*5+[expedition]*7
            with (patch('exile_worth.app.capture_game',side_effect=frames),
                  patch('exile_worth.app.time.monotonic',side_effect=lambda:next(ticks))):
                App.live_loop(app,'A')
            messages = list(app.messages.queue)
            self.assertFalse(any(kind=='error' for kind,_ in messages), messages)
            live = [payload for kind,payload in messages if kind=='live']
            for tab,quantity in [(a,12),(b,80)]:
                values = [payload.readings for payload in live if payload.tab['id']==tab['id']]
                self.assertTrue(values)
                self.assertIsNone(values[0][0].quantity)
                self.assertEqual(values[-1][0].quantity,quantity)

    def run_loop(self, image, tab=None):
        app = SimpleNamespace(
            stop_event=LimitedLoop(), messages=queue.Queue(),
            scanner=SimpleNamespace(reset_incremental=lambda:None,
                                    read_incremental=lambda frame,layout_id,identity: [Reading('C03','divine',12,.99,Reason.AUTO)]),
            resolve_layout=lambda frame,tab:'currency',
            profiles=SimpleNamespace(identify=lambda frame, league:(tab,'Onglet inconnu')))
        ticks = itertools.count()
        with (patch('exile_worth.app.capture_game', return_value=image),
              patch('exile_worth.app.time.monotonic', side_effect=lambda:next(ticks))):
            App.live_loop(app, 'Standard')
        messages = []
        while not app.messages.empty():
            messages.append(app.messages.get_nowait())
        self.assertFalse(any(kind=='error' for kind,_ in messages),messages)
        self.assertEqual(messages[-1][0],'stopped')
        return messages

    def test_no_registered_tab_still_produces_confirmed_live_preview(self):
        messages = self.run_loop(np.zeros((1080,1920,3),np.uint8))
        previews = [payload for kind,payload in messages if kind=='live']
        self.assertTrue(previews)
        self.assertTrue(all(payload.tab is None for payload in previews))
        self.assertEqual(previews[-1].readings[0].quantity,12)
        self.assertIn('preview',[payload[0] for kind,payload in messages if kind=='activity'])

    def test_missing_foreground_game_reports_waiting_without_reading(self):
        messages = self.run_loop(None)
        self.assertEqual([payload[0] for kind,payload in messages if kind=='activity'],['waiting'])
        self.assertFalse(any(kind=='live' for kind,_ in messages))

    def test_known_tab_keeps_identity_for_saved_inventory(self):
        tab = {'id':'tab-1','name':'Currencies'}
        messages = self.run_loop(np.zeros((1080,1920,3),np.uint8),tab)
        readings = [payload for kind,payload in messages if kind=='live']
        self.assertEqual(readings[-1].tab['id'],'tab-1')
        self.assertEqual(readings[-1].readings[0].quantity,12)
