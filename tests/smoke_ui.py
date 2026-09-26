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
    from exile_worth import diagnostics
    from exile_worth.app import App
    from exile_worth.model import Reason, Store
    from exile_worth.vision import Profiles, Scanner

    class Digits:
        def read(self, image):
            return 254, .99

    print('UI smoke: building widgets', flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)
        # The user's own settings (language) must not leak into the test.
        with (patch('exile_worth.app.Store', lambda: Store(path/'inventory.sqlite')),
              patch('exile_worth.app.Profiles', lambda: Profiles(path)),
              patch('exile_worth.settings.DATA', path),
              patch('exile_worth.updater.enabled', lambda: True),
              patch('exile_worth.app.setup_log', lambda: diagnostics.setup(path))):
            app = App(auto_load=False)
            # Install the fake OCR before any frame can schedule an analysis.
            app.scanner = Scanner(app.profiles, Digits(), app.matcher)
            app.withdraw()
            try:
                app.update_idletasks()
                # Only the whole stash before anything is read: no preview entry.
                assert len(app.cards.winfo_children()) == 1, 'No preview card before anything is read'
                assert app.all_view.winfo_manager() and not app.tab_view.winfo_manager()
                assert app.view_title.get() == 'Whole stash'
                # First run: the steps show until closed, and stay closed.
                assert app.guide.winfo_manager(), 'The first-run guide shows'
                app.dismiss_guide()
                assert not app.guide.winfo_manager()
                import json as _json
                assert _json.loads((path/'settings.json').read_text('utf-8'))['guide_done'] is True
                from tkinter import ttk
                style = ttk.Style(app)
                assert style.lookup('TCombobox','fieldbackground',('readonly',)) == '#192332'
                assert style.lookup('TCombobox','foreground',('readonly',)) == '#edf3fc'
                assert style.lookup('TNotebook.Tab','foreground',('selected',)) == '#7ee2c0'
                app.set_frame(np.zeros((1080,1920,3),np.uint8))
                assert app.tab_view.winfo_manager(), 'A new screenshot shows its reading'
                assert not app.fix_controls.winfo_manager(), 'No correction before a line is chosen'
                app.select_slot('L11')
                assert app.fix_controls.winfo_manager()
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
                assert 'Whole stash' in card_texts(0), card_texts(0)
                assert 'Currencies · tab not identified' in card_texts(-1), card_texts(-1)
                assert app.store.rows('Forbidden Rites') == [], 'Preview must not save an anonymous tab'
                assert [str(v) for v in app.read_tree.item('C03')['values'][1:]] == ['1.000', '254.000', '100.0 %']
                from exile_worth.model import Reading
                # A single live observation appears in the table, but cannot
                # become a saved quantity or a valued line before consensus.
                pending = Reading('C03','divine',None,.99,Reason.PENDING)
                app.provisional_readings = [Reading('C03','divine',37,.99,Reason.AUTO)]
                app.show_readings([pending, Reading('C04',None,None,0,Reason.EMPTY)])
                assert '37 (provisional)' in str(app.read_tree.item('C03')['values'][0])
                assert app.read_tree.item('C03')['values'][2] == '—'
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
                assert app.read_tree['columns'] == ('col.quantity', 'col.unit_price', 'col.value', 'col.share')
                assert app.read_tree.item('C01')['text'].endswith('⚠')
                assert 'attention' in app.read_tree.item('C01')['tags']
                assert 'panel' in app.read_notes['C01']
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
                from exile_worth.app import auto_hide
                bar = [w for w in app.read_tree.master.winfo_children() if w.winfo_class() == 'TScrollbar'][0]
                update = auto_hide(bar, app.read_tree)
                update('0.0', '1.0')
                assert not bar.winfo_manager(), 'Nothing to scroll: no scrollbar'
                update('0.0', '0.5')
                assert bar.winfo_manager() == 'pack', 'Overflow: the scrollbar comes back'
                assert bar.master.pack_slaves().index(bar) < bar.master.pack_slaves().index(app.read_tree)
                update('0.0', '1.0')
                assert not bar.winfo_manager()
                print('UI smoke: inventories and history', flush=True)
                app.store.sync('Forbidden Rites','tab1',[Reading('C03','divine',10)])
                app.store.sync('Forbidden Rites','tab2',[Reading('C03','divine',2)])
                app.refresh_inventory()
                assert '12.00 div' in app.total.get(), 'Preview must not be added to saved tabs'
                # The dashboard's item table adds the same item across tabs.
                line = app.items_tree.item('divine')
                assert line['text'].strip() == 'Divine Orb' and line['image'], line
                assert [str(v) for v in line['values'][:4]] == ['12', '1.000', '12.00', '100.0 %'], line['values']
                assert line['values'][4] == 'tab1, tab2', line['values']
                assert app.items_tree.heading('col.value')['text'] == 'Value (div) ▼'
                assert '254.00 div' in app.preview_total.get()
                app.store.sync('Forbidden Rites','tab2',[Reading('C03','divine',2)])
                app.refresh_inventory()
                assert '12.00 div' in app.total.get()
                app.stash_pages.select(app.valuation_view)
                app.update_idletasks()
                assert len(app.store.valuations('Forbidden Rites')) == 1
                app.mark_session()
                assert app.store.active_session('Forbidden Rites')
                assert not app.valuation_view.gains_box.winfo_manager(), 'Nothing to compare yet'
                app.store.sync('Forbidden Rites','tab2',[Reading('C03','divine',3)])
                app.refresh_inventory()
                assert app.valuation_view.gains_box.winfo_manager(), 'An open session shows its gains'
                app.mark_session()
                assert app.store.active_session('Forbidden Rites') is None
                assert '+1.00 div' in app.valuation_view.summary.get()
                table = app.valuation_view.gains
                gains = [[table.set(row, column) for column in ('item', 'before', 'after', 'change', 'value')]
                         for row in table.get_children()]
                assert gains == [['Divine Orb', '12', '13', '+1', '+1.00 div']], gains
                assert app.valuation_view.gains_title.get().startswith('Last session'), app.valuation_view.gains_title.get()
                app.valuation_view.mode.set('Fixed prices of the first displayed point')
                app.valuation_view.choose(app.store.valuations('Forbidden Rites')[-1]['id'])
                app.valuation_view.select()
                assert 'tab2' in app.valuation_view.details.get()
                print('UI smoke: stash list, chart and screenshot', flush=True)
                # Valuations: 12 (10 + 2), then 13 once tab2 holds 3.
                app.profiles.data['tabs'] = [{'id':name,'name':name,'league':'Forbidden Rites','layout_id':'currency'}
                                             for name in ('tab1', 'tab2')]
                app.select_all()
                assert app.all_view.winfo_manager() and not app.tab_view.winfo_manager()
                assert app.view_title.get() == 'Whole stash' and '12' not in app.view_note.get()
                assert app.chart_delta.get() == '+1.00 div (+8 %)', app.chart_delta.get()
                assert app.stash_chart.points, 'The chart draws the stored valuations'
                app.set_period('day')
                assert str(app.period_buttons['day'].cget('style')) == 'PeriodOn.TButton'
                assert str(app.period_buttons['week'].cget('style')) == 'Period.TButton'
                app.open_stash('tab2')
                assert app.tab_view.winfo_manager() and not app.all_view.winfo_manager()
                assert app.chart_delta.get() == '+1.00 div (+50 %)', app.chart_delta.get()
                assert app.view_value.get() == '≈ 3.00 div', app.view_value.get()
                assert '23 % of the stash' in app.view_detail.get(), app.view_detail.get()
                assert not app.canvas.winfo_manager(), 'The screenshot is folded by default'
                app.toggle_capture()
                assert app.canvas.winfo_manager() and app.capture_toggle.cget('text') == '▾ Hide the screenshot'
                app.toggle_capture()
                assert not app.canvas.winfo_manager()
                app.open_stash(None)
                assert app.stash_chart.empty_key == 'chart.none_preview' and not app.stash_chart.points
                app.profiles.data['tabs'] = []
                # Selecting an old card must not redirect incoming live observations.
                app.open_stash('tab1')
                from exile_worth.app import ScanResult
                app.messages.put(('live', ScanResult(frame, {'id':'tab2','name':'Second','layout_id':'currency'},
                                                     [Reading('C03','divine',2)], '', 'Forbidden Rites', 'currency')))
                app.drain()
                assert app.selected_tab_id == 'tab1'
                # The preview card names the tab the live readings come from.
                assert 'Second' in card_texts(-1), card_texts(-1)
                assert 'Live preview · Currencies' in card_texts(-1), card_texts(-1)
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
                assert len(app.cards.winfo_children()) == 2, 'No preview card while a tab is synced'
                assert 'Main currency' in card_texts(1) and '● Live' in card_texts(1), card_texts(1)
                assert str(app.cards.winfo_children()[1].cget('style')) == 'Live.TFrame'
                app.open_stash('live1')
                assert str(app.cards.winfo_children()[1].cget('style')) == 'LiveSelected.TFrame'
                assert app.display_readings()[0].quantity == 7
                assert app.view_title.get() == 'Main currency', app.view_title.get()
                assert app.view_subtitle.get().endswith('● Updating live'), app.view_subtitle.get()
                # Live readings arrive several times a second: the list and the
                # table are updated in place, never rebuilt, so nothing jumps.
                boxes = app.cards.winfo_children()
                labels = boxes[1].winfo_children()
                app.messages.put(('live', ScanResult(frame, live_tab, [Reading('C03','divine',7)],
                                                     '', 'Standard', 'currency')))
                app.drain()
                assert app.cards.winfo_children() == boxes, 'An unchanged reading rebuilt the list'
                app.messages.put(('live', ScanResult(frame, live_tab, [Reading('C03','divine',8)],
                                                     '', 'Standard', 'currency')))
                app.drain()
                assert app.cards.winfo_children() == boxes and boxes[1].winfo_children() == labels
                assert str(app.read_tree.item('C03')['values'][0]) == '8', app.read_tree.item('C03')
                app.messages.put(('live', ScanResult(frame, live_tab, [Reading('C03','divine',7)],
                                                     '', 'Standard', 'currency')))
                app.drain()
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
                assert len(app.cards.winfo_children()) == 3, 'A stop brings the preview card back'
                assert '● Live' not in card_texts(1)
                assert 'Main currency' in card_texts(-1), card_texts(-1)
                assert app.capture_action.get() == 'Start'
                assert not app.capture_button.instate(['disabled'])
                print('UI smoke: problem report', flush=True)
                import json, zipfile
                report = path/'report.zip'
                with (patch('exile_worth.app.simpledialog.askstring', return_value='Abyss stuck'),
                      patch('exile_worth.app.filedialog.asksaveasfilename', return_value=str(report)),
                      patch('exile_worth.app.reveal') as explorer):
                    app.report_problem()
                with zipfile.ZipFile(report) as archive:
                    entries = set(archive.namelist())
                    summary = json.loads(archive.read('report.json'))
                assert {'report.json', 'inventory.csv', 'stash-current.png', 'stash-Main-currency-live1.png'} <= entries, entries
                assert summary['note'] == 'Abyss stuck' and summary['live_tab'] is None, summary
                assert any(tab['id'] == 'live1' for tab in summary['tabs'])
                assert app.status.get().startswith('Report saved'), app.status.get()
                explorer.assert_called_once_with(str(report))
                print('UI smoke: linking a reading to a tab by hand', flush=True)
                from tests.test_stash_real import stash_frame
                app.layout_choice.set('Automatic')
                app.set_frame(stash_frame('delirium'))
                deadline = time.monotonic()+10
                while time.monotonic()<deadline and not (app.last_readings and app.active_layout_id):
                    app.update()
                    time.sleep(.01)
                assert app.active_layout_id == 'delirium', (app.active_layout_id, app.status.get())
                assert app.link_bar.winfo_manager(), 'An unlinked reading offers a link'
                assert app.link_reason.get().startswith('Not linked to a tab'), app.link_reason.get()
                assert list(app.link_box.cget('values')) == ['A new tab…'], app.link_box.cget('values')
                with patch('exile_worth.app.simpledialog.askstring', return_value='34'):
                    app.link_tab()
                linked = next(tab for tab in app.profiles.data['tabs'] if tab['name'] == '34')
                assert linked['layout_id'] == 'delirium' and linked['auto_registered']
                assert app.status.get().startswith('“34” linked'), app.status.get()
                deadline = time.monotonic()+10
                while time.monotonic()<deadline and not app.last_tab:
                    app.update()
                    time.sleep(.01)
                assert app.last_tab and app.last_tab['id'] == linked['id'], 'Read again under its tab'
                assert not app.link_bar.winfo_manager(), 'A linked reading offers no link'
                print('UI smoke: removing a tab', flush=True)
                app.open_stash('live1')
                assert app.remove_button.winfo_manager(), 'A registered tab offers its removal'
                with patch('exile_worth.app.messagebox.askyesno', return_value=False):
                    app.remove_button.invoke()
                assert any(tab['id'] == 'live1' for tab in app.profiles.data['tabs']), 'Cancel keeps the tab'
                with patch('exile_worth.app.messagebox.askyesno', return_value=True) as asked:
                    app.remove_button.invoke()
                assert '1 stored cell' in asked.call_args[0][1], asked.call_args
                assert not any(tab['id'] == 'live1' for tab in app.profiles.data['tabs'])
                assert app.profiles.data['removed']['live1'] == 'Main currency'
                assert not any(row[0] == 'live1' for row in app.store.rows('Standard'))
                assert app.show_all and not app.remove_button.winfo_manager()
                assert app.status.get().startswith('“Main currency” removed'), app.status.get()
                # A scan already in flight must not write the removed tab back.
                app.messages.put(('live', ScanResult(frame, live_tab, [Reading('C03','divine',7)],
                                                     '', 'Standard', 'currency')))
                app.drain()
                assert app.last_tab is None and not app.store.rows('Standard')
                check_update_banner(app, path)
                print('UI smoke OK: widgets, image preview, calibration, prices, league isolation, updates')
            finally:
                print('UI smoke: shutdown', flush=True)
                app.close()
                # Windows cannot delete the folder while the log is open.
                for handler in list(diagnostics.log.handlers):
                    handler.close()
                    diagnostics.log.removeHandler(handler)
                diagnostics._configured = False


def check_update_banner(app, path):
    """The update banner: offered, progress, refusal, skip, language, the setting."""
    import json
    from exile_worth import updater
    from exile_worth.app import UpdateCheck, UpdateFailure, UpdateProgress
    stored = lambda: json.loads((path / 'settings.json').read_text('utf-8'))
    release = updater.Release((9, 9, 9), 'v9.9.9', 'https://github.com/x/ExileWorth-Setup-9.9.9.exe',
                              'ExileWorth-Setup-9.9.9.exe', 1, 'https://github.com/x/sum', updater.RELEASES)
    assert not app.update_bar.winfo_manager(), 'No banner before a newer version is found'
    app.messages.put(('update_check', UpdateCheck(None, True)))
    app.drain()
    assert not app.update_bar.winfo_manager() and 'up to date' in app.status.get(), app.status.get()
    app.messages.put(('update_check', UpdateCheck(release, False)))
    app.drain()
    assert app.update_bar.winfo_manager() and '9.9.9' in app.update_message.get()
    assert isinstance(stored()['update_checked'], float)
    app.messages.put(('update_progress', UpdateProgress(50, 100)))
    app.drain()
    assert app.update_message.get().endswith('50 %'), app.update_message.get()
    app.messages.put(('update_failed', UpdateFailure('checksum', True, 'download')))
    app.drain()
    assert 'checksum' in app.update_message.get() and app.update_install.cget('text') == 'Retry'
    assert app.update_install.instate(['!disabled'])
    app.language_choice.set('Français')
    assert 'somme de contrôle' in app.update_message.get(), app.update_message.get()
    app.language_choice.set('English')
    app.skip_update()
    assert not app.update_bar.winfo_manager() and stored()['update_skip'] == '9.9.9'
    app.messages.put(('update_check', UpdateCheck(release, False)))
    app.drain()
    assert not app.update_bar.winfo_manager(), 'A skipped version is not offered automatically'
    app.messages.put(('update_check', UpdateCheck(release, True)))
    app.drain()
    assert app.update_bar.winfo_manager(), 'A manual check shows it anyway'
    assert app.update_install.cget('text') == 'Update and restart'
    started = []
    with (patch('exile_worth.updater.start_install', lambda *args: started.append(args)),
          patch.object(app, 'after', lambda delay, action: started.append(action))):
        app.messages.put(('update_ready', path / 'ExileWorth-Setup-9.9.9.exe'))
        app.drain()
    assert started[0] == (path / 'ExileWorth-Setup-9.9.9.exe', 'en') and started[1] == app.close
    assert 'restarts' in app.update_message.get()
    app.update_auto.set(False)
    app.update_auto_changed()
    assert stored()['update_auto'] is False and not updater.due(stored())
    app.hide_update_bar()


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
