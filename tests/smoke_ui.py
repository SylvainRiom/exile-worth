"""Run explicitly: python -m tests.smoke_ui (creates a hidden Tk window)."""
import tempfile
import time
import faulthandler
import os
import threading
from pathlib import Path
from unittest.mock import patch

def main():
    import numpy as np
    from joy_tracker.app import App
    from joy_tracker.model import Reason, Store
    from joy_tracker.vision import Profiles, Scanner

    class Digits:
        def read(self, image):
            return 254, .99

    print('UI smoke: building widgets', flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)
        with (patch('joy_tracker.app.Store', lambda: Store(path/'inventory.sqlite')),
              patch('joy_tracker.app.Profiles', lambda: Profiles(path))):
            app = App(auto_load=False)
            # Install the fake OCR before any frame can schedule an analysis.
            app.scanner = Scanner(app.profiles, Digits(), app.matcher)
            app.withdraw()
            try:
                app.update_idletasks()
                from tkinter import ttk
                style = ttk.Style(app)
                assert style.lookup('TCombobox','fieldbackground',('readonly',)) == '#192332'
                assert style.lookup('TCombobox','foreground',('readonly',)) == '#edf3fc'
                assert style.lookup('TNotebook.Tab','foreground',('selected',)) == '#7ee2c0'
                app.set_frame(np.zeros((1080,1920,3),np.uint8))
                app.select_slot('L11')
                market = dict(items={'exalted':{'name':'Exalted Orb'},'divine':{'name':'Divine Orb'}},
                              prices={'exalted':.01,'divine':1},primary='divine',
                              fetched=time.time(),stale=False)
                app.messages.put(('prices',('Forbidden Rites',[{'id':'Forbidden Rites'}],market)))
                app.drain()
                app.item_choice.set('Exalted Orb [exalted]')
                app.calibrate(False)
                assert app.profiles.data['slots']['L11']['item'] == 'exalted'
                app.refresh_inventory()
                app.league.set('Standard')
                assert app.total.get() == '—'
                app.league.set('Forbidden Rites')
                # Import triggers the reader automatically, with no calibrated slot.
                from tests.test_icons import artwork, render
                from joy_tracker.icons import IconMatcher
                from joy_tracker.vision import Scanner, SLOTS
                print('UI smoke: automatic reading', flush=True)
                app.profiles.data['slots'] = {}
                app.matcher = IconMatcher({'divine':artwork(17)})
                app.scanner = Scanner(app.profiles, Digits(), app.matcher)
                # A lone icon on a black background does not establish stash geometry.
                app.layout_choice.set('Currencies')
                frame = np.zeros((1080,1920,3),np.uint8)
                x,y,w,h = SLOTS['C03']
                frame[y:y+h,x:x+w] = render(artwork(17))
                app.set_frame(frame)
                app.save_diagnostic()
                import cv2
                first_capture = sorted((path/'diagnostics').glob('capture-*.png'))
                assert len(first_capture) == 1
                saved = cv2.imread(str(first_capture[0]))
                assert np.array_equal(saved, frame), 'Diagnostic must preserve original pixels'
                app.save_diagnostic()
                assert len(list((path/'diagnostics').glob('capture-*.png'))) == 2, 'Saving another view must preserve the first'
                deadline = time.monotonic()+5
                while time.monotonic()<deadline and not app.last_readings:
                    app.update()
                    time.sleep(.01)
                assert app.last_readings, 'No automatic reading after 5 seconds'
                reading = next(r for r in app.last_readings if r.slot == 'C03')
                assert reading.item == 'divine' and reading.quantity == 254
                assert '254.00 div' in app.total.get(), app.total.get()
                assert 'displayed tab' in app.total_title.get()
                assert app.store.rows('Forbidden Rites') == [], 'Preview must not save an anonymous tab'
                assert app.read_tree.item('C03')['values'][3] == '254.000'
                from joy_tracker.model import Reading
                # A single live observation appears in the table, but cannot
                # become a saved quantity or a valued line before consensus.
                pending = Reading('C03','divine',None,.99,Reason.PENDING)
                app.provisional_readings = [Reading('C03','divine',37,.99,Reason.AUTO)]
                app.show_readings([pending, Reading('C04',None,None,0,Reason.EMPTY)])
                assert '37 (provisional)' in str(app.read_tree.item('C03')['values'][2])
                assert app.read_tree.item('C03')['values'][3] == '—'
                assert not app.read_tree.exists('C04')
                assert app.store.rows('Forbidden Rites') == []
                app.provisional_readings = []
                app.show_readings(app.last_readings)
                print('UI smoke: inventories and history', flush=True)
                app.store.sync('Forbidden Rites','tab1',[Reading('C03','divine',10)])
                app.store.sync('Forbidden Rites','tab2',[Reading('C03','divine',2)])
                app.refresh_inventory()
                assert '12.00 div' in app.total.get(), 'Preview must not be added to saved tabs'
                assert '254.00 div' in app.preview_total.get()
                app.store.sync('Forbidden Rites','tab2',[Reading('C03','divine',2)])
                app.refresh_inventory()
                assert '12.00 div' in app.total.get()
                app.stash_pages.select(app.valuation_view)
                app.update_idletasks()
                assert len(app.store.valuations('Forbidden Rites')) == 1
                app.mark_session()
                assert app.store.active_session('Forbidden Rites')
                app.store.sync('Forbidden Rites','tab2',[Reading('C03','divine',3)])
                app.refresh_inventory()
                app.mark_session()
                assert app.store.active_session('Forbidden Rites') is None
                assert '+1.00 div' in app.valuation_view.summary.get()
                app.valuation_view.mode.set('Fixed prices of the first displayed point')
                app.valuation_view.choose(app.store.valuations('Forbidden Rites')[-1]['id'])
                app.valuation_view.select()
                assert 'tab2' in app.valuation_view.details.get()
                # Selecting an old card must not redirect incoming live observations.
                app.open_stash('tab1')
                from joy_tracker.app import ScanResult
                app.messages.put(('live', ScanResult(frame, {'id':'tab2','name':'Second','layout_id':'currency'},
                                                     [Reading('C03','divine',2)], '', 'Forbidden Rites', 'currency')))
                app.drain()
                assert app.selected_tab_id == 'tab1'
                assert app.display_readings()[0].quantity == 10
                assert next(r for r in app.store.rows('Forbidden Rites') if r[0]=='tab2')[3] == 2
                app.unit.set('exalted')
                assert '1,200.00 exalted' in app.total.get()
                app.league.set('Standard')
                assert app.total.get() == '—' and app.preview_total.get() == ''
                assert app.capture_action.get() == 'Start'
                assert app.capture_state.get() == '● Paused'
                print('UI smoke: tracking start and stop', flush=True)
                assert not app.profiles.data['tabs'], 'Starting must also work before registering a tab'
                with patch('joy_tracker.app.threading.Thread'):
                    app.capture_button.invoke()
                assert app.running and app.capture_state.get() == '● Tracking'
                assert app.capture_action.get() == 'Pause'
                app.messages.put(('activity', ('waiting', 'Back to the game.')))
                app.drain()
                assert app.capture_state.get() == '● Waiting for the game'
                assert app.capture_action.get() == 'Pause'
                app.capture_button.invoke()
                assert app.capture_state.get() == '● Stopping'
                assert app.capture_button.instate(['disabled'])
                app.messages.put(('stopped', None))
                app.drain()
                assert not app.running and app.capture_state.get() == '● Paused'
                assert app.capture_action.get() == 'Start'
                assert not app.capture_button.instate(['disabled'])
                print('UI smoke OK: widgets, image preview, calibration, prices, league isolation')
            finally:
                print('UI smoke: shutdown', flush=True)
                app.close()


def run_bounded(timeout=15):
    """Bound even blocked Tk calls; the watchdog never touches Tk widgets."""
    finished = threading.Event()
    started = time.monotonic()

    def watchdog():
        if not finished.wait(timeout):
            print(f'UI smoke ECHEC : delai total de {timeout}s depasse.', flush=True)
            faulthandler.dump_traceback(all_threads=True)
            os._exit(1)

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        main()
    finally:
        finished.set()
        print(f'UI smoke: duration {time.monotonic()-started:.2f}s', flush=True)


if __name__ == '__main__':
    run_bounded()
