from __future__ import annotations

import csv
import json
import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from .capture import capture_game
from . import i18n
from .diagnostics import failure, log, setup as setup_log
from .i18n import t
from .model import DATA, Reading, Reason, Event, Store, estimate_readings, line_value
from .pricing import Ninja
from .icons import IconMatcher, fetch_icons
from .vision import Profiles, Scanner, normalize
from .layouts import (ALL_SLOTS, LAYOUTS, UNKNOWN_LAYOUT, RUNE_PAGES, layout_family,
                      layout_for_tab, layout_name, aligned_slots)
from .history_ui import HistoryView
from .theme import apply_theme


class App(tk.Tk):
    def __init__(self, auto_load=True):
        super().__init__()
        setup_log()
        i18n.load_language()
        log.info('--- session start --- language=%s', i18n.language())
        self.title(t('app.title'))
        self.geometry('1380x920')
        self.minsize(1080, 780)
        self.configure(bg='#10151e')
        self.store = Store()
        self.profiles = Profiles()
        self.ninja = Ninja(os.getenv('JOY_PRICE_BASE', 'https://poe.ninja'),
                           os.getenv('JOY_CONTACT', 'local-prototype'))
        self.frame = None
        self.scanner = None
        self.matcher = IconMatcher({})
        self.market = {'items': {}, 'prices': {}, 'primary': '?'}
        self.market_league = None
        self.messages = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.capture_activity = ''
        self.busy = False
        self.network_busy = False
        self.next_price_check = time.monotonic() + 3600
        self.selected_slot = None
        self.selecting = False
        self.selection = None
        self.drag_start = None
        self.last_readings = []
        self.provisional_readings = []
        self.last_tab = None
        self.active_layout_id = None
        self.selected_tab_id = None
        self.tab_frames = {}
        self.language_choice = tk.StringVar(value=i18n.language_name())
        self.layout_choice = tk.StringVar(value=t('layout.auto'))
        # None means automatic detection; otherwise a layout id, never its label.
        self.layout_override = None
        self.layout_choice.trace_add('write', self.layout_changed)
        self.detail_title = tk.StringVar(value=t('detail.default_title'))
        self.reading_league = None
        self.league = tk.StringVar(value='Forbidden Rites')
        self.unit = tk.StringVar(value='divine')
        self.status = tk.StringVar(value=t('status.intro'))
        self.total = tk.StringVar(value='—')
        self.total_title = tk.StringVar(value=t('dash.total_title'))
        self.total_detail = tk.StringVar(value=t('dash.total_placeholder'))
        self.preview_total = tk.StringVar(value='')
        self.price_status = tk.StringVar(value=t('status.prices_not_loaded'))
        self.slot_status = tk.StringVar(value=t('fix.slot_placeholder'))
        self.recognition_status = tk.StringVar(value=t('detail.recognition_placeholder'))
        self.item_choice = tk.StringVar()
        self.capture_state = tk.StringVar(value=t('state.paused'))
        self.capture_action = tk.StringVar(value=t('bar.start'))
        self.build_ui()
        self.refresh_capture_state()
        self.refresh_inventory()
        self.league.trace_add('write', self.league_changed)
        self.after(100, self.drain)
        self.after(60000, self.refresh_prices_when_due)
        if auto_load:
            self.after(300, self.load_prices)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def tr(self, widget, key, **fields):
        """Register a static widget so a language change can relabel it."""
        self._translatable.append((widget, key, fields))
        widget.configure(text=t(key, **fields))
        return widget

    def build_ui(self):
        apply_theme(self)
        self._translatable = []
        self._trees = []
        header = ttk.Frame(self, padding=16)
        header.pack(fill='x')
        self.tr(ttk.Label(header, text='', font=('Segoe UI', 20, 'bold')), 'app.brand').pack(side='left')
        self.tr(ttk.Label(header, text='', foreground='#a9b8ca'), 'app.tagline').pack(side='left')
        self.capture_badge = tk.Label(header, textvariable=self.capture_state,
                                      font=('Segoe UI', 11, 'bold'), padx=14, pady=7)
        self.capture_badge.pack(side='right')
        bar = ttk.Frame(self, padding=(16, 0, 16, 8))
        bar.pack(fill='x')
        self.tr(ttk.Label(bar, text=''), 'bar.league').pack(side='left', padx=(0, 6))
        self.league_box = ttk.Combobox(bar, textvariable=self.league, width=23)
        self.league_box.pack(side='left')
        self.tr(ttk.Button(bar, text='', command=self.load_prices), 'bar.load_prices').pack(side='left', padx=6)
        ttk.Label(bar, textvariable=self.price_status).pack(side='left', padx=6)
        ttk.Combobox(bar, textvariable=self.unit, values=['divine', 'exalted', 'chaos'],
                     state='readonly', width=9).pack(side='right')
        self.unit.trace_add('write', lambda *_: self.refresh_inventory())
        self.language_box = ttk.Combobox(bar, textvariable=self.language_choice, state='readonly',
                                         width=11, values=list(i18n.LANGUAGES.values()))
        self.language_box.pack(side='right', padx=(0, 10))
        self.tr(ttk.Label(bar, text=''), 'bar.language').pack(side='right', padx=(12, 6))
        self.language_choice.trace_add('write', self.language_changed)
        controls = ttk.Frame(self, padding=(16, 0, 16, 8))
        controls.pack(fill='x')
        for key, action in [('bar.import', self.import_image), ('bar.capture', self.delayed_capture),
                            ('bar.analyze', self.analyze)]:
            self.tr(ttk.Button(controls, text='', command=action), key).pack(side='left', padx=(0, 6))
        self.capture_button = ttk.Button(controls, textvariable=self.capture_action,
                                         command=self.toggle_live, width=18, style='Accent.TButton')
        self.capture_button.pack(side='left', padx=(0, 6))
        self.tr(ttk.Button(controls, text='', command=self.export_csv), 'bar.export_csv').pack(side='left')
        self.tr(ttk.Button(controls, text='', command=self.save_diagnostic), 'bar.save_image').pack(side='left', padx=6)
        self.layout_box = ttk.Combobox(controls, textvariable=self.layout_choice, state='readonly',
                                       width=20, values=self.layout_values())
        self.layout_box.pack(side='right')
        ttk.Label(self, textvariable=self.status, wraplength=1240, style='Status.TLabel').pack(fill='x')
        self.stash_pages = ttk.Notebook(self)
        self.stash_pages.pack(fill='both', expand=True, padx=16, pady=(4,12))
        dashboard = ttk.Frame(self.stash_pages, padding=16)
        self.detail_page = ttk.Frame(self.stash_pages)
        self.stash_pages.add(dashboard, text=t('page.stash'))
        self.stash_pages.add(self.detail_page, text=t('page.detail'))
        self.valuation_view = HistoryView(self.stash_pages, self.mark_session)
        self.stash_pages.add(self.valuation_view, text=t('page.history'))
        self.page_keys = [(self.stash_pages, dashboard, 'page.stash'),
                          (self.stash_pages, self.detail_page, 'page.detail'),
                          (self.stash_pages, self.valuation_view, 'page.history')]
        ttk.Label(dashboard, textvariable=self.total_title, font=('Segoe UI',14)).pack(anchor='w')
        ttk.Label(dashboard, textvariable=self.total, font=('Segoe UI',30,'bold')).pack(anchor='w', pady=5)
        ttk.Label(dashboard, textvariable=self.total_detail, foreground='#a9b8ca', wraplength=1080).pack(anchor='w')
        self.tr(ttk.Label(dashboard, text='', foreground='#a9b8ca'), 'dash.cards_hint').pack(anchor='w', pady=(4,16))
        cards_box = ttk.Frame(dashboard)
        cards_box.pack(fill='both',expand=True)
        self.cards_canvas = tk.Canvas(cards_box,bg='#10151e',highlightthickness=0)
        cards_scroll = ttk.Scrollbar(cards_box,orient='vertical',command=self.cards_canvas.yview)
        cards_scroll.pack(side='right',fill='y')
        self.cards_canvas.configure(yscrollcommand=cards_scroll.set)
        self.cards_canvas.pack(side='left',fill='both',expand=True)
        self.cards = ttk.Frame(self.cards_canvas)
        cards_window = self.cards_canvas.create_window((0,0),window=self.cards,anchor='nw')
        self.cards.bind('<Configure>',lambda event:self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox('all')))
        self.cards_canvas.bind('<Configure>',lambda event:self.cards_canvas.itemconfigure(cards_window,width=event.width))
        for column in range(3):
            self.cards.columnconfigure(column,weight=1,uniform='cards')
        body = ttk.Frame(self.detail_page, padding=(16, 0))
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body)
        left.pack(side='left', fill='y')
        self.canvas = tk.Canvas(left, width=440, height=522, bg='#080c12', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.preview_scale = 440/645
        self.canvas.bind('<Configure>', lambda event: self.draw())
        self.canvas.create_text(258, 260, text=t('detail.canvas_empty'),
                                fill='#a9b8ca', font=('Segoe UI', 14), justify='center')
        self.canvas.bind('<ButtonPress-1>', self.mouse_down)
        self.canvas.bind('<B1-Motion>', self.mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.mouse_up)
        right = ttk.Frame(body, padding=(14, 0, 0, 0))
        right.pack(side='left', fill='both', expand=True)
        ttk.Label(right,textvariable=self.detail_title,font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(right, textvariable=self.total_title, foreground='#a9b8ca').pack(anchor='w')
        ttk.Label(right, textvariable=self.total, font=('Segoe UI', 24, 'bold')).pack(anchor='w')
        ttk.Label(right, textvariable=self.total_detail,
                  wraplength=540, foreground='#a9b8ca').pack(anchor='w')
        ttk.Label(right, textvariable=self.preview_total, wraplength=540).pack(anchor='w', pady=(4, 10))
        notebook = ttk.Notebook(right)
        notebook.pack(fill='both', expand=True)
        detection = ttk.Frame(notebook)
        inventory = ttk.Frame(notebook)
        history = ttk.Frame(notebook)
        corrections = ttk.Frame(notebook, padding=14)
        notebook.add(detection, text=t('tab.detection'))
        notebook.add(inventory, text=t('tab.inventory'))
        notebook.add(history, text=t('tab.history'))
        notebook.add(corrections, text=t('tab.corrections'))
        self.page_keys += [(notebook, detection, 'tab.detection'), (notebook, inventory, 'tab.inventory'),
                           (notebook, history, 'tab.history'), (notebook, corrections, 'tab.corrections')]
        ttk.Label(detection, textvariable=self.recognition_status, style='Muted.TLabel',
                  wraplength=650, padding=(10,10)).pack(fill='x')
        self.read_tree = self.make_tree(detection, ('col.cell','col.item','col.quantity','col.value','col.state'),
                                        (48, 210, 75, 85, 180))
        self.read_tree.bind('<<TreeviewSelect>>', self.select_tree)
        ttk.Label(corrections, textvariable=self.slot_status, wraplength=530).pack(fill='x', pady=5)
        self.item_box = ttk.Combobox(corrections, textvariable=self.item_choice, state='readonly')
        self.item_box.pack(fill='x', pady=4)
        row = ttk.Frame(corrections)
        row.pack(fill='x')
        self.tr(ttk.Button(row, text='', command=lambda: self.calibrate(False)), 'fix.correct_icon').pack(side='left')
        self.tr(ttk.Button(row, text='', command=lambda: self.calibrate(True)), 'fix.learn_empty').pack(side='left', padx=4)
        self.tr(ttk.Button(corrections, text='', command=self.correct), 'fix.correct_quantity').pack(fill='x', pady=6)
        self.tr(ttk.Label(corrections, text='', wraplength=530, foreground='#a9b8ca'), 'fix.hint').pack(fill='x', pady=6)
        self.inventory_tree = self.make_tree(inventory, ('col.tab','col.item','col.quantity','col.last_read'),
                                             (100, 145, 55, 150))
        self.history_tree = self.make_tree(history, ('col.date','col.tab','col.saved_cells'), (160, 150, 140))
        self.tr(ttk.Label(self, text='', foreground='#a9b8ca', padding=12), 'app.footer').pack(anchor='w')

    def layout_values(self):
        return [t('layout.auto')] + [layout_name(key) for key in LAYOUTS]

    def language_changed(self, *_):
        code = i18n.code_for_name(self.language_choice.get())
        if code == i18n.language():
            return
        i18n.set_language(code)
        log.info('language changed to %s', code)
        self.retranslate()

    def retranslate(self):
        """Relabel the whole interface in place after a language change."""
        self.title(t('app.title'))
        for widget, key, fields in self._translatable:
            widget.configure(text=t(key, **fields))
        for notebook, page, key in self.page_keys:
            notebook.tab(page, text=t(key))
        for tree, columns in self._trees:
            for name in columns:
                tree.heading(name, text=t(name))
        # Comboboxes with translated entries keep the choice, not its old text.
        self.layout_box.configure(values=self.layout_values())
        self.layout_choice.set(layout_name(self.layout_override) if self.layout_override else t('layout.auto'))
        self.valuation_view.retranslate()
        if self.selected_tab_id is None and self.frame is None:
            self.canvas.delete('all')
            self.canvas.create_text(258, 260, text=t('detail.canvas_empty'),
                                    fill='#a9b8ca', font=('Segoe UI', 14), justify='center')
        self.refresh_capture_state()
        self.refresh_inventory()
        self.draw()
        self.status.set(t('status.language_changed', language=i18n.language_name()))

    def make_tree(self, parent, columns, widths):
        box = ttk.Frame(parent)
        box.pack(fill='both', expand=True)
        tree = ttk.Treeview(box, columns=columns, show='headings', height=10)
        for name, width in zip(columns, widths):
            tree.heading(name, text=t(name))
            tree.column(name, width=width, minwidth=40)
        tree.tag_configure('even', background='#192332')
        tree.tag_configure('odd', background='#1e2b3d')
        scroll = ttk.Scrollbar(box, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)
        self._trees.append((tree, columns))
        return tree


    def load_prices(self):
        if self.busy or self.network_busy:
            self.status.set(t('status.busy'))
            return
        league = self.league.get().strip()
        if not league:
            return
        self.network_busy = True
        self.next_price_check = time.monotonic() + 3600
        self.price_status.set(t('status.loading_prices'))
        def work():
            try:
                try:
                    leagues = self.ninja.leagues()
                except (OSError, ValueError, KeyError):
                    leagues = [{'id': league}]
                market = self.ninja.stash_market(league)
                images, errors = fetch_icons(market['items'], progress=lambda done,total:
                                            self.messages.put(('status', t('status.loading_icons', done=done, total=total))))
                market['matcher'] = IconMatcher(images)
                market['icon_errors'] = errors
                self.messages.put(('prices', (league, leagues, market)))
            except Exception as exc:
                failure('load_prices', exc)
                self.messages.put(('price_error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def refresh_prices_when_due(self):
        if self.running and time.monotonic() >= self.next_price_check:
            self.load_prices()
        self.after(60000, self.refresh_prices_when_due)

    def league_changed(self, *_):
        self.last_tab = None
        self.selected_tab_id = None
        self.last_readings = []
        self.provisional_readings = []
        self.reading_league = None
        self.show_readings([])
        self.refresh_inventory()

    def import_image(self):
        if self.running or self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp')])
        if path:
            try:
                image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError(t('error.unreadable_image'))
                self.set_frame(image)
            except Exception as exc:
                failure('import_image', exc)
                messagebox.showerror(t('error.title_capture'), str(exc))

    def delayed_capture(self):
        if self.running or self.busy:
            return
        self.busy = True
        def tick(remaining):
            if remaining:
                self.status.set(t('status.capture_countdown', remaining=remaining))
                self.after(1000, lambda: tick(remaining - 1))
            else:
                try:
                    frame = capture_game()
                    if frame is None:
                        raise ValueError(t('error.foreground'))
                    self.set_frame(frame)
                except Exception as exc:
                    failure('delayed_capture', exc)
                    self.status.set(str(exc))
                finally:
                    self.busy = False
        tick(5)

    def set_frame(self, image):
        self.frame = normalize(image)
        self.active_layout_id = None
        self.last_tab = None
        self.selected_tab_id = None
        self.last_readings = []
        self.reading_league = None
        self.show_readings([])
        self.refresh_inventory()
        self.status.set(t('status.frame_loaded'))
        self.draw()
        self.after_idle(self.analyze)

    def draw(self):
        frame = self.tab_frames.get(self.selected_tab_id) if self.selected_tab_id else self.frame
        if frame is None:
            self.canvas.delete('all')
            self.canvas.create_text(258,260,text=t('detail.canvas_no_image'),
                                    fill='#a9b8ca',font=('Segoe UI',13),justify='center')
            return
        self.preview_scale = min(max(self.canvas.winfo_width(), 2)/645, max(self.canvas.winfo_height(), 2)/765)
        preview = cv2.cvtColor(frame[:765, :645], cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(preview).resize((round(645*self.preview_scale),round(765*self.preview_scale))))
        self.canvas.delete('all')
        self.canvas.create_image(0,0, image=self.photo, anchor='nw')
        statuses = {r.slot:r for r in self.display_readings()}
        for slot,(x,y,w,h) in self.display_slots().items():
            r = statuses.get(slot)
            color = '#60dba8' if r and r.item and r.quantity is not None else '#e9b863' if r else '#718095'
            self.canvas.create_rectangle(x*self.preview_scale,y*self.preview_scale,(x+w)*self.preview_scale,(y+h)*self.preview_scale,
                                         outline='#ffffff' if slot == self.selected_slot else color,
                                         width=2 if slot == self.selected_slot else 1)

    def begin_tab(self):
        if self.active_layout_id is None:
            self.status.set(t('status.unknown_layout'))
            return
        if self.frame is not None and not self.running and not self.busy:
            self.open_stash(None)
            self.selecting = True
            self.status.set(t('status.unknown_layout'))

    def mouse_down(self, event):
        if self.selecting:
            self.drag_start = (event.x, event.y)
        else:
            for slot,(x,y,w,h) in self.display_slots().items():
                if x <= event.x/self.preview_scale <= x+w and y <= event.y/self.preview_scale <= y+h:
                    self.select_slot(slot)
                    break

    def mouse_drag(self, event):
        if self.selecting and self.drag_start:
            self.canvas.delete('selection')
            self.canvas.create_rectangle(*self.drag_start, event.x,event.y, outline='#ffffff', tags='selection')

    def mouse_up(self, event):
        if not self.selecting or not self.drag_start:
            return
        sx,sy = self.drag_start
        x1,x2 = sorted((max(0,min(sx,645*self.preview_scale)),max(0,min(event.x,645*self.preview_scale))))
        y1,y2 = sorted((max(0,min(sy,765*self.preview_scale)),max(0,min(event.y,765*self.preview_scale))))
        rect = tuple(int(v/self.preview_scale) for v in (x1,y1,x2-x1,y2-y1))
        self.selecting = False
        self.drag_start = None
        if rect[1] < 88 or rect[1]+rect[3] > 128:
            self.status.set(t('profile.need_name'))
            return
        name = simpledialog.askstring(t('error.title_tab'), t('profile.need_name'))
        if name:
            try:
                tab = self.profiles.register(name.strip(), self.league.get().strip(), rect, self.frame, self.active_layout_id)
                self.tab_frames[tab['id']] = self.frame.copy()
                self.refresh_inventory()
                self.status.set(t('profile.auto_added', name=name))
            except ValueError as exc:
                messagebox.showerror(t('error.title_tab'), str(exc))

    def select_tree(self, _event):
        selection = self.read_tree.selection()
        if selection:
            self.select_slot(selection[0])

    def select_slot(self, slot):
        self.selected_slot = slot
        self.slot_status.set(t('fix.slot_selected', slot=slot))
        entry = self.profiles.data['slots'].get(slot, {})
        detected = next((r.item for r in self.last_readings if r.slot == slot and r.item), entry.get('item'))
        for label, item in getattr(self, 'choices', {}).items():
            if item == detected:
                self.item_choice.set(label)
        self.draw()

    def calibrate(self, empty):
        if self.selected_tab_id:
            self.status.set(t('fix.need_preview'))
            return
        if self.running or self.busy or self.frame is None or not self.selected_slot:
            self.status.set(t('fix.need_pause'))
            return
        item = getattr(self, 'choices', {}).get(self.item_choice.get())
        if not item:
            self.status.set(t('fix.need_item'))
            return
        self.profiles.calibrate(self.selected_slot, item, self.frame, empty)
        self.status.set(t('fix.saved', slot=self.selected_slot,
                         kind=t('fix.kind_empty') if empty else t('fix.kind_icon')))
        self.draw()

    def analyze(self):
        if self.running or self.busy or self.frame is None:
            return
        if self.network_busy:
            self.status.set(t('status.waiting_catalog'))
            return
        self.busy = True
        frame, league = self.frame.copy(), self.league.get().strip()
        self.status.set(t('status.analysing'))
        def work():
            try:
                self.scanner = self.scanner or Scanner(self.profiles, matcher=self.matcher)
                tab, reason = self.profiles.identify(frame, league)
                layout_id = self.resolve_layout(frame, tab)
                if tab and (layout_id is None or layout_family(layout_id) != layout_family(layout_for_tab(tab).id)):
                    tab = None
                tab_ocr = getattr(getattr(self.scanner, 'digits', None), 'ocr', None)
                if tab is None and layout_id and tab_ocr:
                    tab, reason = self.profiles.observe(frame, league, layout_id, tab_ocr)
                readings = self.scanner.read(frame, layout_id) if layout_id else []
                self.messages.put(('analysis', (frame,tab,readings,reason,league,layout_id)))
            except Exception as exc:
                failure('analyze', exc)
                self.messages.put(('error', str(exc)))
            finally:
                self.messages.put(('done', None))
        threading.Thread(target=work, daemon=True).start()

    def resolve_layout(self, frame, tab):
        if self.layout_override:
            return self.layout_override
        if tab:
            detected = self.scanner.detect_layout(frame, borders_only=True)
            if layout_family(layout_for_tab(tab).id) == 'runes':
                return detected if layout_family(detected) == 'runes' else None
            return detected or layout_for_tab(tab).id
        return self.scanner.detect_layout(frame)

    def layout_changed(self, *_):
        shown = self.layout_choice.get()
        self.layout_override = next((key for key in LAYOUTS if layout_name(key) == shown), None)
        if self.frame is not None and not self.running and not self.busy:
            self.after_idle(self.analyze)

    def save_diagnostic(self):
        frame = self.frame if self.frame is not None else self.tab_frames.get(self.selected_tab_id)
        if frame is None:
            self.status.set(t('status.no_image'))
            return
        try:
            directory = self.profiles.directory / 'diagnostics'
            directory.mkdir(parents=True, exist_ok=True)
            # Keep each diagnostic: multi-page stash tabs need one image per view.
            path = directory / f"capture-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png"
            ok, encoded = cv2.imencode('.png', frame)
            if not ok:
                raise ValueError(t('error.encode'))
            encoded.tofile(str(path))
            metadata = json.dumps({
                'layout': self.display_layout().id,
                'slots': self.display_slots(),
                'items': self.market['items'],
                'readings': [vars(reading) for reading in self.display_readings()],
            }, ensure_ascii=False, indent=2)
            path.with_suffix('.json').write_text(metadata, encoding='utf-8')
            latest = directory / 'derniere-capture.png'
            encoded.tofile(str(latest))
            latest.with_suffix('.json').write_text(metadata, encoding='utf-8')
            self.status.set(t('status.image_saved', path=path))
        except (OSError, ValueError, cv2.error) as exc:
            failure('save_diagnostic', exc)
            self.status.set(t('status.save_failed', error=exc))

    def display_slots(self):
        layout = self.display_layout()
        frame = self.tab_frames.get(self.selected_tab_id) if self.selected_tab_id else self.frame
        if frame is None or layout.id not in LAYOUTS:
            return layout.slots
        return aligned_slots(frame, layout.id)

    def display_layout(self):
        if self.selected_tab_id:
            tab = next((t for t in self.profiles.data['tabs'] if t['id']==self.selected_tab_id),None)
            if tab:
                if (self.last_tab and self.last_tab['id'] == tab['id'] and
                        layout_family(layout_for_tab(tab).id) == 'runes'):
                    return LAYOUTS.get(self.active_layout_id, layout_for_tab(tab))
                return layout_for_tab(tab)
        return LAYOUTS.get(self.active_layout_id, UNKNOWN_LAYOUT)

    def display_readings(self):
        if not self.selected_tab_id:
            return self.last_readings if self.reading_league == self.league.get().strip() else []
        league = self.league.get().strip()
        approximate = self.store.approximate_slots(league)
        return [Reading(slot,item,quantity,1,Reason.TO_CHECK if uncertain else Reason.LAST_KNOWN,
                        (tab,slot) in approximate)
                for tab,slot,item,quantity,stamp,uncertain in self.store.rows(league)
                if tab == self.selected_tab_id]

    def open_stash(self, tab_id):
        self.selected_tab_id = tab_id
        self.selected_slot = None
        tab = next((t for t in self.profiles.data['tabs'] if t['id']==tab_id),None)
        self.detail_title.set(f'{tab["name"]} · {layout_name(layout_for_tab(tab).id)}'
                              if tab else t('detail.live_preview'))
        self.show_readings(self.display_readings())
        self.draw()
        self.stash_pages.select(self.detail_page)

    def refresh_cards(self, rows, prices, unit):
        for child in self.cards.winfo_children():
            child.destroy()
        symbol = 'div' if unit=='divine' else unit
        def card(index,tab_id,title,subtitle,amount,detail):
            box = ttk.Frame(self.cards,padding=20,style='Card.TFrame')
            box.grid(row=index//3,column=index%3,sticky='nsew',padx=6,pady=6)
            for text,font,colour in [(title,('Segoe UI',15,'bold'),'#e7edf6'),
                                     (subtitle,('Segoe UI',10),'#a9b8ca'),
                                     (amount,('Segoe UI',23,'bold'),'#83f0b6'),
                                     (detail,('Segoe UI',10),'#a9b8ca')]:
                label = ttk.Label(box,text=text,font=font,foreground=colour,wraplength=315,style='Card.TLabel')
                label.pack(anchor='w',pady=4)
                label.bind('<Button-1>',lambda event,selected=tab_id:self.open_stash(selected))
            ttk.Button(box,text=t('dash.see_detail'),command=lambda:self.open_stash(tab_id)).pack(anchor='w',pady=(8,0))
            box.bind('<Button-1>',lambda event:self.open_stash(tab_id))
        preview = estimate_readings(self.last_readings if self.reading_league==self.league.get().strip() else [],prices,unit)
        amount = f'≈ {preview.amount:,.2f} {symbol}' if preview.amount is not None else '—'
        card(0,None,t('dash.preview_card'),layout_name(self.active_layout_id or 'unknown'),amount,
             t('dash.preview_detail', unread=preview.unread, unpriced=preview.unpriced))
        tabs = [t for t in self.profiles.data['tabs'] if t['league']==self.league.get().strip()]
        approximate = self.store.approximate_slots(self.league.get().strip())
        for index,tab in enumerate(tabs,1):
            entries = [r for r in rows if r[0]==tab['id']]
            estimate = estimate_readings([Reading(r[1],r[2],r[3]) for r in entries],prices,unit)
            amount = f'≈ {estimate.amount:,.2f} {symbol}' if estimate.amount is not None else '—'
            expected_slots = (sum(len(LAYOUTS[key].slots) for key in RUNE_PAGES)
                              if layout_family(layout_for_tab(tab).id) == 'runes'
                              else len(layout_for_tab(tab).slots))
            unread = max(0, expected_slots-len(entries))
            uncertain = sum(bool(r[5]) for r in entries)
            detail = (t('dash.never_synced') if not entries else
                      t('dash.last_read', stamp=max(r[4] for r in entries).replace('T',' ')))
            if unread or uncertain or estimate.unpriced:
                detail += t('dash.partial', count=unread+uncertain, unpriced=estimate.unpriced)
            if any((r[0],r[1]) in approximate for r in entries):
                detail += t('dash.abbreviated')
            card(index,tab['id'],tab['name'],layout_name(layout_for_tab(tab).id),amount,detail)

    def refresh_capture_state(self):
        if self.running and self.stop_event.is_set():
            label, action, foreground, background = t('state.stopping'), t('state.stopping_action'), '#ffda8a', '#49391f'
            self.capture_button.state(['disabled'])
        elif self.running:
            label, action, foreground, background = t('state.tracking'), t('bar.pause'), '#83f0b6', '#163d2b'
            if self.capture_activity == 'waiting':
                label, foreground, background = t('state.waiting'), '#ffda8a', '#49391f'
            elif self.capture_activity == 'preview':
                label = t('state.preview')
            elif self.capture_activity == 'unstable':
                label, foreground, background = t('state.unstable'), '#ffda8a', '#49391f'
            self.capture_button.state(['!disabled'])
        else:
            label, action, foreground, background = t('state.paused'), t('bar.start'), '#c1cddd', '#283449'
            self.capture_button.state(['!disabled'])
        self.capture_state.set(label)
        self.capture_action.set(action)
        self.capture_badge.configure(foreground=foreground, background=background)

    def toggle_live(self):
        if self.running:
            self.stop_event.set()
            self.refresh_capture_state()
            self.status.set(t('status.stopping'))
            return
        if self.busy or self.network_busy:
            self.status.set(t('status.wait_before_start'))
            return
        league = self.league.get().strip()
        self.stop_event.clear()
        self.running = True
        self.capture_activity = ''
        self.refresh_capture_state()
        self.league_box.configure(state='disabled')
        self.status.set(t('status.started'))
        log.info('tracking started: league=%s override=%s', league, self.layout_override or 'auto')
        threading.Thread(target=self.live_loop, args=(league,), daemon=True).start()

    def live_loop(self, league):
        last_signature = None
        scans = 0
        last_activity = None
        def activity(state, detail):
            nonlocal last_activity
            if (state,detail) != last_activity:
                self.messages.put(('activity', (state,detail)))
                last_activity = (state,detail)
        try:
            self.scanner = self.scanner or Scanner(self.profiles, matcher=self.matcher)
            self.scanner.reset_incremental()
            while not self.stop_event.wait(.33):
                image = capture_game()
                if image is None:
                    activity('waiting', t('status.waiting_game'))
                    self.scanner.reset_incremental()
                    scans = 0
                    last_signature = None
                    continue
                frame = normalize(image)
                tab, reason = self.profiles.identify(frame, league)
                layout_id = self.resolve_layout(frame, tab)
                if tab and (layout_id is None or layout_family(layout_id) != layout_family(layout_for_tab(tab).id)):
                    tab = None
                tab_ocr = getattr(getattr(self.scanner, 'digits', None), 'ocr', None)
                if tab is None and layout_id and tab_ocr:
                    tab, reason = self.profiles.observe(frame, league, layout_id, tab_ocr)
                if layout_id is None:
                    self.scanner.reset_incremental()
                    activity('preview', t('status.unknown_layout'))
                    if last_signature != ('unknown',):
                        self.messages.put(('live', (frame,None,[],'',league,None)))
                        last_signature = ('unknown',)
                    continue
                identity = tab['id'] if tab else 'preview:'+layout_id
                readings = self.scanner.read_incremental(frame, layout_id, (league, identity))
                if self.stop_event.is_set():
                    break
                activity('active' if tab else 'preview',
                         t('status.tab_recognised', name=tab['name']) if tab else t('status.preview_only'))
                scans += 1
                provisional = getattr(self.scanner, 'preview_readings', [])
                signature = (tab['id'] if tab else None, layout_id,
                             tuple((r.slot,r.item,r.quantity,r.reason,r.approximate,r.alternatives) for r in readings),
                             tuple((r.slot,r.item,r.quantity,r.approximate) for r in provisional))
                if signature != last_signature or scans % 12 == 0:
                    self.messages.put(('live', (frame,tab,readings,reason,league,layout_id,provisional)))
                    last_signature = signature
        except Exception as exc:
            failure('live_loop', exc)
            self.messages.put(('error', str(exc)))
        finally:
            log.info('tracking stopped after %d scans', scans)
            self.messages.put(('stopped', None))

    def show_readings(self, readings):
        self.read_tree.delete(*self.read_tree.get_children())
        readings = [r for r in readings if r.reason != Reason.EMPTY]
        provisional = {r.slot:r for r in self.provisional_readings} if not self.selected_tab_id else {}
        unit = self.unit.get()
        prices = self.market['prices'] if self.league.get().strip() == self.market_league else {}
        self.read_tree.heading('col.value', text=t('col.value_unit', unit='div' if unit == 'divine' else unit))
        identified = sum(bool(r.item) for r in readings)
        ambiguous = sum(bool(r.alternatives) and not r.item for r in readings)
        self.recognition_status.set(
            t('detail.recognition', identified=identified, total=len(readings), ambiguous=ambiguous)
            if readings else t('detail.recognition_none'))
        for index,r in enumerate(readings):
            value = line_value(r.item, r.quantity, prices, unit)
            candidate = provisional.get(r.slot)
            pending = (r.reason == Reason.PENDING and r.quantity is None and candidate is not None
                       and candidate.item == r.item and candidate.quantity is not None)
            shown_quantity = candidate.quantity if pending else r.quantity
            shown_approximate = candidate.approximate if pending else r.approximate
            quantity_text = ('—' if shown_quantity is None else
                             ('≈ ' if shown_approximate else '')+f'{shown_quantity:,}'+
                             (t('reading.provisional') if pending else ''))
            self.read_tree.insert('', 'end', iid=r.slot, tags=('odd' if index%2 else 'even',), values=(r.slot,self.reading_name(r),
                                  quantity_text,
                                  '—' if value is None else f'{value:.3f}',t('reason.'+r.reason)+
                                  (t('reading.provisional_suffix') if pending else
                                   t('reading.abbreviated_suffix') if r.approximate else '')))

    def item_name(self, item):
        return self.market['items'].get(item, {}).get('name', item or t('item.unknown'))

    def reading_name(self, reading):
        if reading.item:
            return self.item_name(reading.item)
        if reading.alternatives:
            names = [self.item_name(item) for item in reading.alternatives]
            bases = {name.split(' (')[0] for name in names}
            if len(bases) == 1:
                return t('item.unknown_variant', name=next(iter(bases)))
            return ' / '.join(names)
        return t('item.unknown')

    def refresh_inventory(self):
        league = self.league.get().strip()
        rows = self.store.rows(league)
        prices = self.market['prices'] if league == self.market_league else {}
        unit = self.unit.get()
        symbol = 'div' if unit == 'divine' else unit
        readings = self.last_readings if self.reading_league == league else []
        preview = estimate_readings(readings, prices, unit)
        stored = estimate_readings([Reading(slot,item,quantity) for tab,slot,item,quantity,stamp,stale in rows], prices, unit)
        uncertain = sum(bool(row[5]) for row in rows)
        expected = sum((sum(len(LAYOUTS[key].slots) for key in RUNE_PAGES)
                        if layout_family(layout_for_tab(t).id) == 'runes'
                        else len(layout_for_tab(t).slots))
                       for t in self.profiles.data['tabs'] if t['league']==league)
        amount = stored.amount if rows else preview.amount
        estimate = stored if rows else preview
        missing = estimate.unpriced
        unread = max(0, expected-len(rows)) if rows else estimate.unread
        partial = bool(missing or unread or uncertain)
        self.total.set((f'≈ {amount:,.2f} {symbol}' + (' · partiel' if partial else '')) if amount is not None else '—')
        if rows:
            tabs = len({row[0] for row in rows})
            self.total_title.set(t('dash.tracked', tabs=tabs))
            self.total_detail.set(t('dash.tracked_detail', unread=unread, missing=missing, uncertain=uncertain))
            preview_text = f'≈ {preview.amount:,.2f} {symbol}' if preview.amount is not None else '—'
            self.preview_total.set(t('dash.preview_line', amount=preview_text) if readings else '')
        else:
            self.total_title.set(t('dash.displayed_title'))
            self.total_detail.set(t('dash.displayed_detail', valued=estimate.valued, unread=unread, missing=missing)
                                  if readings else t('dash.total_placeholder'))
            self.preview_total.set(t('dash.auto_add_hint') if readings and not self.last_tab else '')
        approximate_slots = self.store.approximate_slots(league)
        if (approximate_slots if rows else any(r.approximate for r in readings)):
            self.total_detail.set(self.total_detail.get()+t('dash.abbreviated_suffix'))
        self.show_readings(self.display_readings())
        self.refresh_cards(rows,prices,unit)
        self.inventory_tree.delete(*self.inventory_tree.get_children())
        names = {t['id']:t['name'] for t in self.profiles.data['tabs']}
        for tab,slot,item,quantity,stamp,stale in rows:
            self.inventory_tree.insert('', 'end', values=(names.get(tab,tab), self.item_name(item),
                                       f'≈ {quantity:,}' if (tab,slot) in approximate_slots else quantity,
                                       stamp[11:19]+' UTC'+(' · '+t('reason.to_check') if stale else '')))
        self.history_tree.delete(*self.history_tree.get_children())
        for stamp,tab,snapshot in self.store.history(league):
            self.history_tree.insert('', 'end', values=(stamp,names.get(tab,tab),len(json.loads(snapshot))))
        self.record_valuation()
        latest = self.store.db.execute('SELECT MAX(id) FROM valuations WHERE league=?', (league,)).fetchone()[0]
        history_key = (league, latest, tuple(names.items()))
        if getattr(self, '_history_key', None) != history_key:
            self._history_key = history_key
            self.valuation_view.refresh(self.store.valuations(league), names, self.store.active_session(league),
                                        self.store.last_completed_session(league))
        if self.market_league == league:
            stamp = datetime.fromtimestamp(self.market['fetched']).strftime('%d/%m %H:%M')
            age = t('status.prices_expired') if time.time()-self.market['fetched'] > 7200 or self.market['stale'] else ''
            self.price_status.set(t('status.prices_summary', stamp=stamp, age=age, missing=missing, uncertain=uncertain))
        else:
            self.price_status.set(t('status.prices_load_league'))

    def record_valuation(self, reason=Event.REFRESH, force=False):
        league = self.league.get().strip()
        if self.market_league != league:
            return None
        market = self.market
        expected = {tab['id']: (sum(len(LAYOUTS[key].slots) for key in RUNE_PAGES)
                                if layout_family(layout_for_tab(tab).id) == 'runes'
                                else len(layout_for_tab(tab).slots))
                    for tab in self.profiles.data['tabs'] if tab['league']==league}
        return self.store.record_valuation(league, market, expected, reason, force)

    def mark_session(self):
        league = self.league.get().strip()
        if not self.store.rows(league):
            self.status.set(t('status.session_needs_rows'))
            return
        if self.market_league != league:
            self.status.set(t('status.session_needs_prices'))
            return
        reason = Event.SESSION_END if self.store.active_session(league) else Event.SESSION_START
        self.record_valuation(reason, force=True)
        self.refresh_inventory()
        self.status.set(t('status.session_marked', reason=t('event.'+reason)))

    def correct(self):
        if self.selected_tab_id:
            self.status.set(t('fix.need_preview_quantity'))
            return
        if self.running or self.busy or not self.last_tab or not self.selected_slot or self.last_tab['league'] != self.league.get().strip():
            self.status.set(t('fix.need_tab'))
            return
        ref = self.profiles.data['slots'].get(self.selected_slot, {})
        item = next((r.item for r in self.last_readings if r.slot == self.selected_slot and r.item), ref.get('item'))
        if not item:
            return
        quantity = simpledialog.askinteger(t('fix.dialog_title'), t('fix.dialog_prompt'), minvalue=0, maxvalue=999999)
        if quantity is not None:
            self.store.sync(self.league.get().strip(), self.last_tab['id'],
                            [Reading(self.selected_slot,item,quantity,1,Reason.MANUAL)])
            self.last_readings = [Reading(r.slot,item,quantity,1,Reason.MANUAL) if r.slot == self.selected_slot else r
                                  for r in self.last_readings]
            self.refresh_inventory()

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='exile-worth-inventory.csv')
        if path:
            with open(path,'w',newline='',encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                writer.writerow(['tab_id','slot','item_id','quantity','confirmed_utc','uncertain','approximate'])
                approximate = self.store.approximate_slots(self.league.get().strip())
                writer.writerows([*r,int((r[0],r[1]) in approximate)] for r in self.store.rows(self.league.get().strip()))
            self.status.set(t('status.exported'))

    def drain(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == 'prices':
                    league, leagues, market = payload
                    self.network_busy = False
                    self.market = market
                    self.matcher = market.get('matcher', self.matcher)
                    if self.scanner:
                        self.scanner.matcher = self.matcher
                    self.market_league = league
                    self.store.save_prices(league, market)
                    if self.league.get().strip() != league:
                        self.league.set(league)
                    self.league_box.configure(values=[v['id'] for v in leagues])
                    self.choices = {f"{item['name']} [{key}]":key for key,item in sorted(market['items'].items(), key=lambda p:p[1]['name'])}
                    self.item_box.configure(values=list(self.choices))
                    stamp = datetime.fromtimestamp(market['fetched']).strftime('%d/%m %H:%M')
                    self.price_status.set(t('status.prices_received', stamp=stamp)+
                                          (t('status.prices_stale_suffix') if market['stale'] else ''))
                    self.refresh_inventory()
                    log.info('prices loaded: league=%s items=%d families=%d unavailable=%s',
                             league, len(market['items']), len(self.matcher.groups),
                             market.get('unavailable_categories') or 'none')
                    errors = market.get('icon_errors', [])
                    self.status.set(t('status.catalog_loaded', families=len(self.matcher.groups))+
                                    (t('status.icons_missing', count=len(errors)) if errors else ''))
                    if market.get('unavailable_categories'):
                        categories = ', '.join(market['unavailable_categories'])
                        self.status.set(self.status.get()+t('status.categories_missing', categories=categories))
                    if self.frame is not None and not self.running:
                        self.after_idle(self.analyze)
                elif kind in ('analysis', 'live'):
                    frame,tab,readings,reason,league = payload[:5]
                    layout_id = payload[5] if len(payload) > 5 else (layout_for_tab(tab).id if tab else
                                ('expedition' if readings and readings[0].slot.startswith('E') else 'currency' if readings else None))
                    if league != self.league.get().strip():
                        continue
                    self.frame, self.last_tab, self.last_readings = frame, tab, readings
                    self.provisional_readings = payload[6] if kind == 'live' and len(payload) > 6 else []
                    self.reading_league = league
                    self.active_layout_id = layout_id
                    if tab:
                        self.tab_frames[tab['id']] = frame.copy()
                    if not self.selected_tab_id:
                        self.detail_title.set(t('detail.live_preview_of', layout=layout_name(self.active_layout_id or 'unknown')))
                    self.show_readings(self.display_readings())
                    self.draw()
                    if kind == 'live' and tab:
                        self.store.sync(league, tab['id'], readings)
                        self.refresh_inventory()
                        known = sum(r.item is not None and r.quantity is not None for r in readings)
                        detail = (t('status.synced_partial', name=tab['name'], known=known, total=len(readings))
                                  if known < len(readings) else t('status.synced', name=tab['name']))
                        self.status.set(f'{reason} {detail}' if reason else detail)
                    else:
                        self.refresh_inventory()
                        known = sum(r.item is not None and r.quantity is not None for r in readings)
                        suffix = (reason or t('status.tab_to_recognise')) if not tab else (reason or t('status.ready_for_tracking'))
                        self.status.set(t('status.identified', known=known, total=len(readings), suffix=suffix)
                                        if layout_id else t('status.unknown_layout_short'))
                elif kind in ('error', 'price_error'):
                    self.status.set(str(payload))
                    if kind == 'price_error':
                        self.network_busy = False
                        self.price_status.set(t('status.prices_unavailable'))
                elif kind == 'status':
                    self.status.set(payload)
                elif kind == 'activity':
                    if self.running and not self.stop_event.is_set():
                        self.capture_activity, detail = payload
                        self.refresh_capture_state()
                        self.status.set(detail)
                elif kind == 'done':
                    self.busy = False
                elif kind == 'stopped':
                    self.running = False
                    self.capture_activity = ''
                    self.refresh_capture_state()
                    self.league_box.configure(state='normal')
                    if self.stop_event.is_set():
                        self.status.set(t('status.paused'))
        except queue.Empty:
            pass
        self.after(100, self.drain)

    def close(self):
        self.stop_event.set()
        self.store.close()
        self.destroy()
