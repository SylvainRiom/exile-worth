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
    from exile_worth.app import App
    from exile_worth.model import Reason, Store
    from exile_worth.vision import Profiles, Scanner

    class Digits:
        def read(self, image):
            return 254, .99

    print('UI smoke: building widgets', flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)
        with (patch('exile_worth.app.Store', lambda: Store(path/'inventory.sqlite')),
              patch('exile_worth.app.Profiles', lambda: Profiles(path))):
            app = App(auto_load=False)
            # Install the fake OCR before any frame can schedule an analysis.
            app.scanner = Scanner(app.profiles, Digits(), app.matcher)
            app.withdraw()
            try:
                app.update_idletasks()
                assert not app.cards.winfo_children(), 'No preview card before anything is read'
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
                # Only record the scheduling: running it here would reorder the
                # analyses this test waits on further down.
                with patch.object(app, 'after_idle') as scheduled:
                    app.calibrate(False)
                assert app.status.get() == 'Reference saved for Exalted Orb.', app.status.get()
                scheduled.assert_called_once_with(app.analyze)
                assert app.profiles.data['slots']['L11']['item'] == 'exalted'
                labels = [str(w.cget('text')) for w in app.capture_button.master.winfo_children()
                          if w.winfo_class() == 'TButton']
                assert 'Analyse' not in labels, labels
                app.refresh_inventory()
                app.league.set('Standard')
                assert app.total.get() == '—'
                app.league.set('Forbidden Rites')
                # Import triggers the reader automatically, with no calibrated slot.
                from tests.test_icons import artwork, render
                from exile_worth.icons import IconMatcher
                from exile_worth.vision import Scanner, SLOTS
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
                def card_texts(index):
                    box = app.cards.winfo_children()[index]
                    found, stack = [], [box]
                    while stack:
                        widget = stack.pop()
                        stack.extend(widget.winfo_children())
                        if widget.winfo_class() == 'TLabel' and widget.cget('text'):
                            found.append(str(widget.cget('text')))
                    return ' | '.join(found)
                assert 'Currencies · tab not identified' in card_texts(0), card_texts(0)
                assert app.store.rows('Forbidden Rites') == [], 'Preview must not save an anonymous tab'
                assert app.read_tree.item('C03')['values'][1] == '254.000'
                from exile_worth.model import Reading
                # A single live observation appears in the table, but cannot
                # become a saved quantity or a valued line before consensus.
                pending = Reading('C03','divine',None,.99,Reason.PENDING)
                app.provisional_readings = [Reading('C03','divine',37,.99,Reason.AUTO)]
                app.show_readings([pending, Reading('C04',None,None,0,Reason.EMPTY)])
                assert '37 (provisional)' in str(app.read_tree.item('C03')['values'][0])
                assert app.read_tree.item('C03')['values'][1] == '—'
                assert not app.read_tree.exists('C04')
                assert app.store.rows('Forbidden Rites') == []
                app.provisional_readings = []
                app.show_readings(app.last_readings)
                print('UI smoke: sortable tables and icons', flush=True)
                app.icon_images = {'divine': artwork(17)}
                app.show_readings([Reading('C03','divine',254), Reading('C01',None,5,.5,Reason.UNKNOWN_ICON),
                                   Reading('C02','divine',31)])
                assert app.read_tree.item('C03')['image'], 'Known item must show its artwork'
                assert not app.read_tree.item('C01')['image'], 'Unknown item must not borrow an icon'
                # No state column: an unknown item is marked, a normal line is not.
                assert app.read_tree['columns'] == ('col.quantity', 'col.value')
                assert app.read_tree.item('C01')['text'].endswith('⚠')
                assert 'attention' in app.read_tree.item('C01')['tags']
                assert 'Corrections' in app.read_notes['C01']
                assert not app.read_tree.item('C03')['text'].endswith('⚠')
                assert 'attention' not in app.read_tree.item('C03')['tags']
                app.sort_by(app.read_tree, 'col.quantity')
                assert app.read_tree.get_children() == ('C01', 'C02', 'C03')
                assert app.read_tree.heading('col.quantity')['text'].endswith('▲')
                app.sort_by(app.read_tree, 'col.quantity')
                assert app.read_tree.get_children() == ('C03', 'C02', 'C01')
                assert app.read_tree.heading('col.quantity')['text'].endswith('▼')
                # A live refresh rebuilds the table; the chosen order must survive it.
                app.show_readings([Reading('C02','divine',31), Reading('C03','divine',254)])
                assert app.read_tree.get_children() == ('C03', 'C02')
                assert app.read_tree.heading('col.value')['text'].startswith('Value')
                assert not app.read_tree.heading('col.value')['text'].endswith(('▲', '▼'))
                app.sort_by(app.read_tree, '#0')
                assert app.read_tree.heading('#0')['text'] == 'Item ▲'
                # Equal names keep their previous order.
                assert app.read_tree.get_children() == ('C03', 'C02')
                # Cell ids key the rows but are never shown to the user.
                assert app.read_tree.item('C03')['text'].strip() == 'Divine Orb'
                assert not any(str(v).startswith('C0') for v in app.read_tree.item('C03')['values'])
                assert not app.read_tree.heading('col.quantity')['text'].endswith(('▲', '▼'))
                assert app.tab_icon('currency') and app.tab_icon('ancient_augments') is app.tab_icon('runes')
                assert app.tab_icon(None) == '' and app.tab_icon('unknown') == ''
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
                from exile_worth.app import ScanResult
                app.messages.put(('live', ScanResult(frame, {'id':'tab2','name':'Second','layout_id':'currency'},
                                                     [Reading('C03','divine',2)], '', 'Forbidden Rites', 'currency')))
                app.drain()
                assert app.selected_tab_id == 'tab1'
                # The preview card names the tab the live readings come from.
                assert 'Second' in card_texts(0), card_texts(0)
                assert 'Live preview · Currencies' in card_texts(0), card_texts(0)
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
                with patch('exile_worth.app.threading.Thread'):
                    app.capture_button.invoke()
                assert app.running and app.capture_state.get() == '● Tracking'
                assert app.capture_action.get() == 'Pause'
                print('UI smoke: live card replaces the preview', flush=True)
                live_tab = {'id':'live1','name':'Main currency','league':'Standard','layout_id':'currency'}
                app.profiles.data['tabs'].append(live_tab)
                app.messages.put(('live', ScanResult(frame, live_tab, [Reading('C03','divine',7)],
                                                     '', 'Standard', 'currency')))
                app.drain()
                assert app.live_tab_id() == 'live1'
                assert len(app.cards.winfo_children()) == 1, 'No preview card while a tab is synced'
                assert 'Main currency' in card_texts(0) and '● Live' in card_texts(0), card_texts(0)
                assert str(app.cards.winfo_children()[0].cget('style')) == 'Live.TFrame'
                app.open_stash('live1')
                assert app.display_readings()[0].quantity == 7
                assert app.detail_title.get().endswith('● Updating live'), app.detail_title.get()
                # Re-confirming a stored cell keeps its confirmed quantity and value.
                # (No price is loaded for Standard here, so only the quantity is checked.)
                app.messages.put(('live', ScanResult(frame, live_tab, [Reading('C03','divine',None,.99,Reason.PENDING)],
                                                     '', 'Standard', 'currency',
                                                     (Reading('C03','divine',9,.99,Reason.AUTO),))))
                app.drain()
                values = app.read_tree.item('C03')['values']
                assert str(values[0]) == '7 → 9 (provisional)', values
                assert 'pending' in app.read_tree.item('C03')['tags']
                assert 'last confirmed' in app.read_notes['C03'], app.read_notes
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
                assert app.live_tab_id() is None
                assert len(app.cards.winfo_children()) == 2, 'A stop brings the preview card back'
                assert '● Live' not in card_texts(1)
                app.place_cards(1200)
                assert app._card_columns == 4 and app.cards.winfo_children()[1].grid_info()['column'] == 1
                app.place_cards(500)
                assert app._card_columns == 1 and app.cards.winfo_children()[1].grid_info()['row'] == 1
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
