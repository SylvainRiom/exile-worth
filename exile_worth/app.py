from __future__ import annotations

import csv
import json
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

import cv2
import numpy as np
from PIL import Image, ImageTk

from .capture import capture_game
from . import __version__, i18n, settings, updater
from .diagnostics import ChangeGate, failure, log, setup as setup_log
from .report import build_report, reveal, tab_summary
from .i18n import t
from .model import (DATA, Reading, Reason, Event, Store, estimate_readings, line_value, point_value,
                    stock_change)
from .pricing import Ninja
from .icons import IconMatcher, fetch_icons
from .vision import Profiles, Scanner, normalize
from .layouts import (ALL_SLOTS, LAYOUTS, UNKNOWN_LAYOUT, RUNE_PAGES, expected_slot_count,
                      has_views, layout_family, layout_for_tab, layout_name, aligned_slots)
from .history_ui import HistoryView, LineChart
from . import theme
from .theme import apply_theme, dark_title_bar
from .tables import sorted_rows


@dataclass(frozen=True)
class UpdateCheck:
    release: updater.Release | None
    manual: bool


@dataclass(frozen=True)
class UpdateProgress:
    done: int
    total: int


@dataclass(frozen=True)
class UpdateFailure:
    key: str
    manual: bool
    stage: str


# In-game stash tab icons by layout family, verified on PoE2DB; see sources.json.
TAB_ICONS = Path(__file__).with_name('assets') / 'tab_icons'
# The application's own icon, drawn by tools/make_app_icon.py.
APP_ICON = Path(__file__).with_name('assets') / 'app.ico'
# The stash chart's periods, in seconds; None keeps the whole league.
PERIODS = {'day': 86400, 'week': 7*86400, 'league': None}


@dataclass(frozen=True)
class ScanResult:
    """One analysis or live reading handed from a worker thread to the UI.

    Workers must not touch Tk widgets, so every reading crosses the queue. This
    used to be a tuple of six or seven items whose length the consumer probed
    (`payload[6] if len(payload) > 6`), which silently decided behaviour.
    """
    frame: object
    tab: dict | None
    readings: list
    reason: str
    league: str
    layout_id: str | None
    provisional: tuple = ()


def auto_hide(scroll, neighbour):
    """A `yscrollcommand` that shows the scrollbar only when there is something to scroll.

    `neighbour` is the scrolled widget, packed on the left; the bar comes back
    on its right.
    """
    def update(first, last):
        scroll.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            if scroll.winfo_manager():
                scroll.pack_forget()
        elif not scroll.winfo_manager():
            scroll.pack(side='right', fill='y', before=neighbour)
    return update


SIDE_WIDTH = 320


class Tooltip:
    """A hint under a widget while the pointer rests on it.

    `text` is called on each show, so the hint follows the language and the
    data; an empty text shows nothing.
    """

    def __init__(self, widget, text):
        self.widget, self.text, self.window = widget, text, None
        widget.bind('<Enter>', self.show, add='+')
        widget.bind('<Leave>', self.hide, add='+')

    def show(self, _event=None):
        text = self.text()
        if not text or self.window is not None:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        tk.Label(self.window, text=text, background='#223247', foreground='#edf3fc', justify='left',
                 font=('Segoe UI', 9), padx=8, pady=4).pack()
        self.window.geometry(f'+{self.widget.winfo_rootx()}+'
                             f'{self.widget.winfo_rooty()+self.widget.winfo_height()+4}')

    def hide(self, _event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None


def warn_mark(thumb):
    """`thumb` with an amber dot in its lower right corner, ringed in the table's colour."""
    from PIL import ImageDraw
    thumb = thumb.copy()
    draw = ImageDraw.Draw(thumb)
    draw.ellipse((17, 17, 27, 27), fill=theme.WARN, outline=theme.SURFACE, width=2)
    return thumb


def fit_text(font, text, width):
    """`text` cut with an ellipsis to fit `width` pixels in `font`."""
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + '…') > width:
        text = text[:-1]
    return text.rstrip(' ·') + '…'


class App(tk.Tk):
    def __init__(self, auto_load=True):
        super().__init__()
        try:
            # `default` also covers every dialog and Toplevel of the app.
            self.iconbitmap(default=str(APP_ICON))
        except tk.TclError:
            pass
        setup_log()
        i18n.load_language()
        log.info('--- session start --- language=%s', i18n.language())
        self.title(t('app.title'))
        self.geometry('1380x920')
        self.minsize(1080, 780)
        self.configure(bg='#10151e')
        self.store = Store()
        self.profiles = Profiles()
        self.ninja = Ninja(os.getenv('EXILE_PRICE_BASE', 'https://poe.ninja'),
                           os.getenv('EXILE_CONTACT', 'local-prototype'))
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
        # Why the last reading was attached to no tab (ScanResult.reason).
        self.last_reason = ''
        # True when the last scan was a live one synchronised into `last_tab`.
        self.last_scan_synced = False
        self.active_layout_id = None
        self.selected_tab_id = None
        self.tab_frames = {}
        # Reference artwork by item id, and the table thumbnails made from it.
        # PhotoImages are built on the Tk thread only, and kept referenced here
        # or Tk would drop them.
        self.icon_images = {}
        self._thumbs = {}
        self._tab_icons = {}
        self.language_choice = tk.StringVar(value=i18n.language_name())
        self.layout_choice = tk.StringVar(value=t('layout.auto'))
        # None means automatic detection; otherwise a layout id, never its label.
        self.layout_override = None
        self.layout_choice.trace_add('write', self.layout_changed)
        # The stash page shows either the whole stash or one entry of its
        # list: a registered tab, or the live preview (selected_tab_id None).
        self.show_all = True
        self.capture_open = False
        self.chart_period = 'week'
        self._valuations = []
        self.view_title = tk.StringVar(value=t('side.all'))
        self.view_subtitle = tk.StringVar()
        self.view_value = tk.StringVar(value='—')
        self.view_detail = tk.StringVar()
        self.view_note = tk.StringVar()
        self.chart_title = tk.StringVar(value=t('chart.title_all'))
        self.chart_delta = tk.StringVar()
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
        # Updates: only a packaged build checks (see updater.enabled).
        self.updates_enabled = updater.enabled()
        self.update_auto = tk.BooleanVar(value=settings.read().get('update_auto', True) is not False)
        # The first-run guide, until the player closes it or a tab registers.
        self.guide_done = settings.read().get('guide_done') is True
        self.update_release = None
        self.update_busy = False
        self.update_message = tk.StringVar()
        self._update_text = ('', {})
        self.build_ui()
        dark_title_bar(self)
        self.refresh_capture_state()
        self.refresh_inventory()
        self.league.trace_add('write', self.league_changed)
        self.after(100, self.drain)
        self.after(60000, self.refresh_prices_when_due)
        if auto_load:
            self.after(300, self.load_prices)
            if self.updates_enabled:
                self.after(5000, self.check_updates)
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
        # What each table shows, by row id (`fill_tree`).
        self._tree_rows = {}
        # Per table: (column, descending). Reapplied after every refresh.
        self._sort = {}
        header = ttk.Frame(self, padding=16)
        header.pack(fill='x')
        self.header = header
        self.tr(ttk.Label(header, text='', font=('Segoe UI', 20, 'bold')), 'app.brand').pack(side='left')
        self.tr(ttk.Label(header, text='', foreground='#a9b8ca'), 'app.tagline').pack(side='left')
        ttk.Label(header, text=f'v{__version__}', style='Muted.TLabel').pack(side='left', padx=(10, 0))
        # The two pages, chosen here like the chart's periods; the notebook
        # below draws no tabs of its own (`Pages.TNotebook`).
        self.page_buttons = []
        for index, key in enumerate(('page.stash', 'page.history')):
            button = self.tr(ttk.Button(header, text='', style='Nav.TButton',
                                        command=lambda index=index: self.stash_pages.select(index)), key)
            button.pack(side='left', padx=(28 if index == 0 else 4, 0))
            self.page_buttons.append(button)
        # Settings touched once a league (language, updates) sit in a menu;
        # the tracking state stands beside the button that changes it.
        self.settings_button = ttk.Menubutton(header, style='TMenubutton')
        self.tr(self.settings_button, 'bar.settings')
        self.settings_menu = self.make_menu(self.settings_button)
        self.settings_button.configure(menu=self.settings_menu)
        self.settings_button.pack(side='right', padx=(10, 0))
        self.capture_button = ttk.Button(header, textvariable=self.capture_action,
                                         command=self.toggle_live, width=14, style='Accent.TButton')
        self.capture_button.pack(side='right')
        self.capture_badge = tk.Label(header, textvariable=self.capture_state,
                                      font=('Segoe UI', 11, 'bold'), padx=14, pady=7)
        self.capture_badge.pack(side='right', padx=(0, 6))
        self.language_choice.trace_add('write', self.language_changed)
        self.build_update_bar()
        bar = ttk.Frame(self, padding=(16, 0, 16, 10))
        bar.pack(fill='x')
        self.tr(ttk.Label(bar, text=''), 'bar.league').pack(side='left', padx=(0, 6))
        self.league_box = ttk.Combobox(bar, textvariable=self.league, width=23)
        self.league_box.pack(side='left')
        prices_button = ttk.Button(bar, text='↻', width=3, command=self.load_prices)
        prices_button.pack(side='left', padx=(6, 0))
        Tooltip(prices_button, lambda: t('bar.load_prices'))
        ttk.Label(bar, textvariable=self.price_status).pack(side='left', padx=6)
        ttk.Combobox(bar, textvariable=self.unit, values=['divine', 'exalted', 'chaos'],
                     state='readonly', width=9).pack(side='right')
        self.unit.trace_add('write', lambda *_: self.refresh_inventory())
        more = ttk.Menubutton(bar, style='TMenubutton')
        self.tr(more, 'bar.more')
        self.more_menu = self.make_menu(more)
        more.configure(menu=self.more_menu)
        more.pack(side='right', padx=(0, 10))
        # No manual "Analyse": every event that changes the answer (a new
        # screenshot, a layout choice, the catalogue, a correction) re-reads.
        for key, action in [('bar.capture', self.delayed_capture), ('bar.import', self.import_image)]:
            self.tr(ttk.Button(bar, text='', command=action), key).pack(side='right', padx=(0, 6))
        self.fill_menus()
        # One line at the bottom for what just happened, beside the footer.
        footer = ttk.Frame(self, style='Status.TFrame')
        footer.pack(side='bottom', fill='x')
        self.tr(ttk.Label(footer, text='', style='Status.TLabel'), 'app.footer').pack(side='right')
        ttk.Label(footer, textvariable=self.status, style='Status.TLabel').pack(side='left', fill='x')
        self.stash_pages = ttk.Notebook(self, style='Pages.TNotebook')
        self.stash_pages.pack(fill='both', expand=True, padx=16, pady=(4,12))
        self.stash_pages.bind('<<NotebookTabChanged>>', self.page_changed)
        dashboard = self.dashboard = ttk.Frame(self.stash_pages, padding=(0,10,0,0))
        self.stash_pages.add(dashboard, text=t('page.stash'))
        self.valuation_view = HistoryView(self.stash_pages, self.mark_session, self.item_name)
        self.stash_pages.add(self.valuation_view, text=t('page.history'))
        self.page_keys = [(self.stash_pages, dashboard, 'page.stash'),
                          (self.stash_pages, self.valuation_view, 'page.history')]
        # One page: the stash list on the left, what the chosen entry holds on
        # the right. "Whole stash" shows the total and every item; a tab shows
        # its own cells, their corrections and its screenshot.
        side = ttk.Frame(dashboard, width=SIDE_WIDTH)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        self.cards_canvas = tk.Canvas(side, bg='#10151e', highlightthickness=0)
        cards_scroll = ttk.Scrollbar(side, orient='vertical', command=self.cards_canvas.yview)
        self.cards_canvas.configure(yscrollcommand=auto_hide(cards_scroll, self.cards_canvas))
        self.cards_canvas.pack(side='left', fill='both', expand=True)
        self.cards = ttk.Frame(self.cards_canvas)
        self.cards.columnconfigure(0, weight=1)
        cards_window = self.cards_canvas.create_window((0,0), window=self.cards, anchor='nw')
        self.cards.bind('<Configure>', lambda event: self.cards_canvas.configure(
            scrollregion=self.cards_canvas.bbox('all')))
        self.cards_canvas.bind('<Configure>', lambda event: self.cards_canvas.itemconfigure(
            cards_window, width=event.width))
        self._card_boxes = []
        self._card_lines = None
        # The wheel scrolls the list wherever the pointer is over it; `all`
        # bindings run after a widget's own ones.
        self.bind_all('<MouseWheel>', self.wheel_cards, add='+')
        main = ttk.Frame(dashboard, padding=(18,0,0,0))
        main.pack(side='left', fill='both', expand=True)
        # Packed above the header while it is wanted (`refresh_guide`).
        self.guide = ttk.Frame(main, style='Panel.TFrame', padding=14)
        self.tr(ttk.Label(self.guide, text='', style='Panel.TLabel', font=(theme.HEADINGS, 11)),
                'guide.title').pack(anchor='w')
        for key in ('guide.window', 'guide.stash', 'guide.start', 'guide.link'):
            self.tr(ttk.Label(self.guide, text='', style='Panel.TLabel', wraplength=900, justify='left'),
                    key).pack(anchor='w', pady=(4, 0))
        self.tr(ttk.Button(self.guide, text='', command=self.dismiss_guide), 'guide.close').pack(anchor='e', pady=(8, 0))
        head = self.view_head = ttk.Frame(main)
        head.pack(fill='x')
        # The name, then its value right under it, then what it is and what
        # the estimate misses: the eye no longer crosses the page for the total.
        names = ttk.Frame(head)
        names.pack(fill='x')
        ttk.Label(names, textvariable=self.view_title, font=(theme.HEADINGS,16)).pack(side='left')
        # Packed only while a registered tab is shown (`refresh_view`).
        self.remove_button = self.tr(ttk.Button(names, text='', style='Period.TButton',
                                                command=lambda: self.remove_tab(self.shown_tab_id())),
                                     'tab.remove')
        ttk.Label(head, textvariable=self.view_value, font=(theme.NUMBERS,26,'bold'),
                  foreground=theme.VALUE).pack(anchor='w')
        facts = ttk.Frame(head)
        facts.pack(fill='x')
        self.view_subtitle_label = ttk.Label(facts, textvariable=self.view_subtitle, foreground=theme.SUBTLE)
        self.view_subtitle_label.pack(side='left')
        ttk.Label(facts, textvariable=self.view_detail, foreground=theme.SUBTLE,
                  wraplength=900, justify='left').pack(side='left', padx=(16,0))
        self.view_note_label = ttk.Label(main, textvariable=self.view_note, foreground='#a9b8ca')
        self.view_note_label.pack(anchor='w')
        # Shown under the note while a reading is attached to no tab
        # (`refresh_link`): why, and the player's way to say which tab it is.
        self.link_bar = ttk.Frame(main)
        self.link_reason = tk.StringVar()
        ttk.Label(self.link_bar, textvariable=self.link_reason, foreground='#ffcf70',
                  wraplength=900, justify='left').pack(anchor='w')
        link_row = ttk.Frame(self.link_bar)
        link_row.pack(anchor='w', pady=(4, 0))
        self.tr(ttk.Label(link_row, text=''), 'link.choose').pack(side='left')
        self.link_choice = tk.StringVar()
        self.link_box = ttk.Combobox(link_row, textvariable=self.link_choice, state='readonly', width=30)
        self.link_box.pack(side='left', padx=6)
        self.tr(ttk.Button(link_row, text='', command=self.link_tab), 'link.button').pack(side='left')
        self._link_options = {}
        # The value of the chosen entry over time, from the stored valuations.
        chart_bar = ttk.Frame(main)
        chart_bar.pack(fill='x', pady=(10,4))
        ttk.Label(chart_bar, textvariable=self.chart_title, foreground='#a9b8ca').pack(side='left')
        self.chart_delta_label = ttk.Label(chart_bar, textvariable=self.chart_delta, font=(theme.NUMBERS,11,'bold'))
        self.chart_delta_label.pack(side='left', padx=10)
        self.period_buttons = {}
        for key in reversed(PERIODS):
            button = self.tr(ttk.Button(chart_bar, text='', style='Period.TButton',
                                        command=lambda key=key: self.set_period(key)), 'chart.period_'+key)
            button.pack(side='right', padx=(4,0))
            self.period_buttons[key] = button
        chart = tk.Canvas(main, height=130, background='#17202d', highlightthickness=0)
        chart.pack(fill='x')
        self.stash_chart = LineChart(chart, 130, 'chart.empty', self.chart_time)
        body = ttk.Frame(main)
        body.pack(fill='both', expand=True, pady=(12,0))
        # Whole stash: every item in one table, most valuable first.
        self.all_view = ttk.Frame(body)
        self.tr(ttk.Label(self.all_view, text='', foreground='#a9b8ca'), 'dash.items_title').pack(anchor='w', pady=(0,6))
        self.items_tree = self.make_tree(self.all_view, ('col.quantity','col.unit_price','col.value','col.share','col.tabs'),
                                         (90, 100, 110, 70, 260), item_column=280)
        self._sort[self.items_tree] = ('col.value', True)
        for name in self.headings(self.items_tree):
            self.set_heading(self.items_tree, name)
        # One tab: its cells, a panel explaining and correcting the chosen
        # line, and the screenshot on demand.
        self.tab_view = ttk.Frame(body)
        # The stash type belongs to the reading shown here, not to the toolbar.
        recognition = ttk.Frame(self.tab_view)
        recognition.pack(fill='x', pady=(0,6))
        self.layout_box = ttk.Combobox(recognition, textvariable=self.layout_choice, state='readonly',
                                       width=20, values=self.layout_values())
        self.layout_box.pack(side='right')
        self.tr(ttk.Label(recognition, text='', style='Muted.TLabel'), 'layout.label').pack(side='right', padx=(12,6))
        ttk.Label(recognition, textvariable=self.recognition_status, style='Muted.TLabel',
                  wraplength=760).pack(side='left', fill='x', expand=True)
        columns = ttk.Frame(self.tab_view)
        columns.pack(fill='both', expand=True)
        right = ttk.Frame(columns, width=340)
        right.pack(side='right', fill='y', padx=(14,0))
        right.pack_propagate(False)
        table = ttk.Frame(columns)
        table.pack(side='left', fill='both', expand=True)
        # Cell ids (L11, E22…) stay internal: rows are keyed by them, never shown.
        # No state column: a normal line carries no mark, a line being confirmed
        # is grey, one that needs attention is amber with a ⚠, and the selected
        # line's explanation appears in the panel beside the table.
        self.read_tree = self.make_tree(table, ('col.quantity','col.unit_price','col.value','col.share'),
                                        (130, 90, 90, 70), item_column=260)
        self.read_tree.tag_configure('pending', foreground='#8a97a8')
        # The amber is on the thumbnail's corner (`item_icon`), not on the
        # whole line: half a tab in amber made the colour mean nothing.
        self.read_tree.tag_configure('attention', foreground='#f2e3c0')
        self.read_tree.bind('<<TreeviewSelect>>', self.select_tree)
        panel = ttk.Frame(right, style='Panel.TFrame', padding=14)
        panel.pack(fill='x')
        self.read_notes = {}
        self.read_note = tk.StringVar(value=t('note.legend'))
        self.read_note_label = ttk.Label(panel, textvariable=self.read_note, style='Panel.TLabel', wraplength=300)
        self.read_note_label.pack(fill='x')
        # The correction controls show once a line or a cell is chosen.
        self.fix_controls = ttk.Frame(panel, style='Panel.TFrame')
        ttk.Label(self.fix_controls, textvariable=self.slot_status, style='Panel.TLabel',
                  foreground='#a9b8ca', wraplength=300).pack(fill='x', pady=(10,4))
        self.item_box = ttk.Combobox(self.fix_controls, textvariable=self.item_choice, state='readonly')
        self.item_box.pack(fill='x', pady=4)
        row = ttk.Frame(self.fix_controls, style='Panel.TFrame')
        row.pack(fill='x')
        self.tr(ttk.Button(row, text='', command=lambda: self.calibrate(False)), 'fix.correct_icon').pack(side='left')
        self.tr(ttk.Button(row, text='', command=lambda: self.calibrate(True)), 'fix.learn_empty').pack(side='left', padx=4)
        self.tr(ttk.Button(self.fix_controls, text='', command=self.correct), 'fix.correct_quantity').pack(fill='x', pady=(6,0))
        self.capture_toggle = ttk.Button(right, text=t('capture.show'), command=self.toggle_capture)
        self.capture_toggle.pack(anchor='w', pady=(12,6))
        # Packed only while the screenshot is shown (`toggle_capture`).
        self.canvas = tk.Canvas(right, width=320, height=380, bg='#080c12', highlightthickness=0)
        self.preview_scale = 320/645
        self.canvas.bind('<Configure>', lambda event: self.draw())
        self.canvas.bind('<ButtonPress-1>', self.mouse_down)
        self.canvas.bind('<B1-Motion>', self.mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.mouse_up)

    def page_changed(self, _event=None):
        """Light the header button of the page on show."""
        shown = self.stash_pages.index('current')
        for index, button in enumerate(self.page_buttons):
            button.configure(style='NavOn.TButton' if index == shown else 'Nav.TButton')

    def make_menu(self, parent):
        return tk.Menu(parent, tearoff=0, background='#192332', foreground='#edf3fc',
                       activebackground='#315879', activeforeground='#ffffff',
                       selectcolor='#7ee2c0', borderwidth=0)

    def fill_menus(self):
        """The toolbar menus' entries, rebuilt in place on a language change."""
        self.more_menu.delete(0, 'end')
        for key, action in [('bar.export_csv', self.export_csv), ('bar.save_image', self.save_diagnostic),
                            ('bar.report', self.report_problem)]:
            self.more_menu.add_command(label=t(key), command=action)
        menu = self.settings_menu
        menu.delete(0, 'end')
        languages = self.make_menu(menu)
        for name in i18n.LANGUAGES.values():
            languages.add_radiobutton(label=name, variable=self.language_choice, value=name)
        menu.add_cascade(label=t('bar.language'), menu=languages)
        if self.updates_enabled:
            menu.add_separator()
            menu.add_checkbutton(label=t('bar.update_auto'), variable=self.update_auto,
                                 command=self.update_auto_changed)
            menu.add_command(label=t('bar.update_check'), command=lambda: self.check_updates(manual=True))

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
            for name in self.headings(tree):
                self.set_heading(tree, name)
        # Comboboxes with translated entries keep the choice, not its old text.
        self.layout_box.configure(values=self.layout_values())
        self.fill_menus()
        self.layout_choice.set(layout_name(self.layout_override) if self.layout_override else t('layout.auto'))
        self.valuation_view.retranslate()
        self.capture_toggle.configure(text=t('capture.hide' if self.capture_open else 'capture.show'))
        key, fields = self._update_text
        self.show_update_text(key, **fields)
        self.refresh_capture_state()
        self.refresh_inventory()
        self.draw()
        self.status.set(t('status.language_changed', language=i18n.language_name()))

    def make_tree(self, parent, columns, widths, item_column=None):
        """A sortable table; `item_column` (a width) adds the item column.

        The item column is the tree column (#0): the artwork and the name share
        one cell, which a regular Treeview column cannot hold.
        """
        box = ttk.Frame(parent)
        box.pack(fill='both', expand=True)
        tree = ttk.Treeview(box, columns=columns, show='tree headings' if item_column else 'headings', height=10)
        tree.heading_texts = {}
        tree.item_heading = 'col.item' if item_column else None
        if item_column:
            tree.column('#0', width=item_column, minwidth=120, anchor='w')
            self.set_heading(tree, '#0')
        for name, width in zip(columns, widths):
            # Numbers line up on their last digit, heading included. The list
            # of tabs is centred: left-aligned, it touched the share beside it.
            anchor = 'center' if name == 'col.tabs' else 'e'
            tree.column(name, width=width, minwidth=40, anchor=anchor)
            tree.heading(name, anchor=anchor)
            self.set_heading(tree, name)
        tree.tag_configure('even', background='#192332')
        tree.tag_configure('odd', background='#1e2b3d')
        scroll = ttk.Scrollbar(box, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=auto_hide(scroll, tree))
        tree.pack(side='left', fill='both', expand=True)
        self._trees.append((tree, columns))
        return tree

    def set_heading(self, tree, name, text=None):
        """Label a column, with an arrow on the one the table is sorted by.

        `text` overrides the translated label (the value column names its unit);
        it is remembered so a later click keeps it.
        """
        if text is not None:
            tree.heading_texts[name] = text
        label = tree.heading_texts.get(name, t(tree.item_heading if name == '#0' else name))
        column, descending = self._sort.get(tree, (None, False))
        if column == name:
            label += ' ▼' if descending else ' ▲'
        tree.heading(name, text=label, command=lambda: self.sort_by(tree, name))

    def sort_by(self, tree, name):
        """First click sorts ascending, the next one flips the direction."""
        column, descending = self._sort.get(tree, (None, False))
        self._sort[tree] = (name, not descending if column == name else False)
        for other in self.headings(tree):
            self.set_heading(tree, other)
        self.apply_sort(tree)

    @staticmethod
    def headings(tree):
        """Every sortable column, the item (tree) column included."""
        return (['#0'] if tree.item_heading else []) + list(tree['columns'])

    def fill_tree(self, tree, rows):
        """Show `rows` ((iid, options) pairs) without rebuilding the table.

        Deleting every row and inserting it again on each live reading sent
        the table back to its top and made it flicker while nothing changed.
        Only the rows that changed are touched; an unchanged table is left alone.
        """
        rows = dict(rows)
        if self._tree_rows.get(tree) == rows:
            return
        shown = self._tree_rows.get(tree, {})
        gone = [iid for iid in tree.get_children() if iid not in rows]
        if gone:
            tree.delete(*gone)
        for iid, options in rows.items():
            if not tree.exists(iid):
                tree.insert('', 'end', iid=iid, **options)
            elif shown.get(iid) != options:
                tree.item(iid, **options)
        self._tree_rows[tree] = rows
        self.apply_sort(tree)

    def apply_sort(self, tree):
        """Reorder rows by the chosen column; unsorted tables keep insertion order."""
        column, descending = self._sort.get(tree, (None, False))
        rows = tree.get_children()
        if column is not None:
            rows = sorted_rows([(row, tree.item(row, 'text') if column == '#0' else tree.set(row, column))
                                for row in rows], descending)
            for index, row in enumerate(rows):
                tree.move(row, '', index)
        # Stripes follow the displayed order, not the insertion order; the other
        # tags (a line being confirmed, one needing attention) are kept.
        for index, row in enumerate(rows):
            marks = [tag for tag in tree.item(row, 'tags') if tag not in ('odd', 'even')]
            tree.item(row, tags=(*marks, 'odd' if index % 2 else 'even'))

    def item_icon(self, item, alternatives=(), warn=False):
        """A small thumbnail of an item's artwork, or '' when none is known.

        An unresolved family whose candidates share one image (the Flux tiers)
        still shows that image: it helps locate the line without naming a tier.
        `warn` adds an amber dot in the corner; a line needing attention with
        no known artwork shows the dot alone.
        """
        candidates = [item] if item else list(alternatives)
        known = [c for c in candidates if c in self.icon_images]
        key = known[0] if known else None
        if key and any(self.icon_images[c] is not self.icon_images[key] for c in known):
            key = None
        if key is None and not warn:
            return ''
        if (key, warn) not in self._thumbs:
            thumb = Image.new('RGBA', (28, 28))
            if key:
                image = self.icon_images[key]
                rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA if image.shape[2] == 4 else cv2.COLOR_BGR2RGBA)
                thumb = Image.fromarray(rgba).resize((28, 28), Image.LANCZOS)
            if warn:
                thumb = warn_mark(thumb)
            self._thumbs[(key, warn)] = ImageTk.PhotoImage(thumb, master=self)
        return self._thumbs[(key, warn)]


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
                market['icons'] = images
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
        self.last_scan_synced = False
        self.selected_tab_id = None
        self.show_all = True
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
        self.last_reason = ''
        self.last_scan_synced = False
        # A new screenshot is shown at once: its reading, its corrections.
        self.selected_tab_id = None
        self.show_all = False
        self.last_readings = []
        self.reading_league = None
        self.show_readings([])
        self.refresh_inventory()
        self.status.set(t('status.frame_loaded'))
        self.draw()
        self.after_idle(self.analyze)

    def draw(self):
        # The screenshot is folded away by default; nothing to draw then.
        if not self.capture_open:
            return
        frame = self.tab_frames.get(self.selected_tab_id) if self.selected_tab_id else self.frame
        if frame is None:
            self.canvas.delete('all')
            self.canvas.create_text(max(self.canvas.winfo_width(), 2)//2, max(self.canvas.winfo_height(), 2)//2,
                                    text=t('detail.canvas_no_image'), fill='#a9b8ca',
                                    font=('Segoe UI',12), justify='center')
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
            self.show_note(selection[0])
            # A refresh restores the selection; that is not a new choice.
            if selection[0] != self.selected_slot:
                self.select_slot(selection[0])

    def select_slot(self, slot):
        self.selected_slot = slot
        entry = self.profiles.data['slots'].get(slot, {})
        # The line shown, which is a stored cell when a saved tab is open.
        detected = next((r.item for r in self.display_readings() if r.slot == slot and r.item), entry.get('item'))
        # Corrections apply to the screenshot being read, never to a stored tab.
        self.slot_status.set(t('fix.slot_selected', name=self.item_name(detected)) if self.showing_live()
                             else t('fix.need_preview'))
        for label, item in getattr(self, 'choices', {}).items():
            if item == detected:
                self.item_choice.set(label)
        self.show_fix(True)
        # A cell clicked on the screenshot selects its line too.
        if self.read_tree.exists(slot) and self.read_tree.selection() != (slot,):
            self.read_tree.selection_set(slot)
        self.draw()

    def show_fix(self, shown):
        """The correction controls, beside the table once a line is chosen."""
        if shown and not self.fix_controls.winfo_manager():
            self.fix_controls.pack(fill='x')
        elif not shown and self.fix_controls.winfo_manager():
            self.fix_controls.pack_forget()

    def toggle_capture(self):
        """Show or fold the screenshot with its cells; folded by default."""
        self.capture_open = not self.capture_open
        self.capture_toggle.configure(text=t('capture.hide' if self.capture_open else 'capture.show'))
        if self.capture_open:
            self.canvas.pack(fill='both', expand=True)
            self.draw()
        else:
            self.canvas.pack_forget()

    def set_period(self, key):
        self.chart_period = key
        self.refresh_chart()

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
        self.status.set(t('fix.saved_empty') if empty else t('fix.saved', name=self.item_name(item)))
        self.draw()
        # Show the correction's effect at once instead of waiting for a new image.
        self.after_idle(self.analyze)

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
                if tab is None and layout_id and tab_ocr and self.may_register():
                    tab, reason = self.profiles.observe(frame, league, layout_id, tab_ocr)
                readings = self.scanner.read(frame, layout_id) if layout_id else []
                self.messages.put(('analysis', ScanResult(frame, tab, readings, reason, league, layout_id)))
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
            family = layout_family(layout_for_tab(tab).id)
            if has_views(family):
                # An unrecognised view stays unrecognised. A structure the
                # borders confidently place in another family is returned, so
                # a profile registered with the wrong type before that type
                # existed can be corrected (only while it holds no stock).
                return detected
            return detected or layout_for_tab(tab).id
        return self.scanner.detect_layout(frame)

    def may_register(self):
        """Only a structure confirmed by its borders, the selector or the user registers a tab.

        The icon fallback counts recognised items per grid; on a tab whose
        structure was unknown (Ritual before its geometry existed) it named Runes
        from 5 matches against 3, and the tab was saved with the wrong type.
        """
        return bool(self.layout_override) or getattr(self.scanner, 'last_layout_basis', None) in ('borders', 'selector')

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

    def report_problem(self):
        """Write a local zip for whoever helps the player: nothing is sent."""
        note = simpledialog.askstring(t('report.title'), t('report.prompt'), parent=self)
        if note is None:
            return
        desktop = Path.home() / 'Desktop'
        path = filedialog.asksaveasfilename(
            parent=self, title=t('report.title'), defaultextension='.zip', filetypes=[('Zip', '*.zip')],
            initialdir=str(desktop if desktop.exists() else Path.home()),
            initialfile=f"exile-worth-report-{datetime.now():%Y%m%d-%H%M}.zip")
        if not path:
            return
        league = self.league.get().strip()
        names = {tab['id']: tab['name'] for tab in self.profiles.data['tabs']}
        # The screenshot being read, then the last one of every tab seen
        # this session: the stash the player is reporting is among them.
        # Named after the tab and its id's start, which report.json lists.
        frames = [('current', self.frame)] + [(f"{names.get(tab_id, 'removed')}-{tab_id[:6]}", frame)
                                              for tab_id, frame in self.tab_frames.items()]
        summary = dict(
            note=note.strip(), league=league, language=i18n.language(), status=self.status.get(),
            running=self.running, activity=self.capture_activity,
            layout_override=self.layout_override, active_layout=self.active_layout_id,
            layout_basis=getattr(self.scanner, 'last_layout_basis', None),
            layout_verdict=getattr(self.scanner, 'last_layout_verdict', ''),
            last_tab=self.last_tab['id'] if self.last_tab else None, live_tab=self.live_tab_id(),
            shown_tab=self.shown_tab_id(),
            tabs=[tab_summary(tab) for tab in self.profiles.data['tabs']],
            removed=self.profiles.data.get('removed', {}),
            readings=[vars(reading) for reading in self.last_readings],
            empty_cells=sorted(self.store.empty_slots(league)),
            prices=dict(league=self.market_league, primary=self.market.get('primary'),
                        fetched=self.market.get('fetched'), stale=self.market.get('stale')))
        # Written before the log is archived, so the report marks its own place.
        log.info('problem report: %s | note: %s', path, note.strip() or '-')
        try:
            build_report(path, self.profiles.directory, summary, frames, self.store.rows(league))
        except (OSError, ValueError, cv2.error) as exc:
            failure('report_problem', exc)
            self.status.set(t('report.failed', error=exc))
            return
        self.status.set(t('report.saved', path=path))
        reveal(path)

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
                        has_views(layout_for_tab(tab).id)):
                    return LAYOUTS.get(self.active_layout_id, layout_for_tab(tab))
                return layout_for_tab(tab)
        return LAYOUTS.get(self.active_layout_id, UNKNOWN_LAYOUT)

    def live_tab_id(self):
        """The registered tab the live loop is synchronising right now, if any.

        Its card replaces the preview card: the preview only exists for
        readings that no card holds (unidentified tab, imported screenshot).
        """
        if (self.running and self.last_scan_synced and self.last_tab
                and self.reading_league == self.league.get().strip()):
            return self.last_tab['id']
        return None

    def showing_live(self):
        """True when the detail page shows the live readings, not a stored tab."""
        return not self.selected_tab_id or self.selected_tab_id == self.live_tab_id()

    def display_readings(self):
        if self.showing_live():
            return self.last_readings if self.reading_league == self.league.get().strip() else []
        league = self.league.get().strip()
        approximate = self.store.approximate_slots(league)
        return [Reading(slot,item,quantity,1,Reason.TO_CHECK if uncertain else Reason.LAST_KNOWN,
                        (tab,slot) in approximate)
                for tab,slot,item,quantity,stamp,uncertain in self.store.rows(league)
                if tab == self.selected_tab_id]

    def open_stash(self, tab_id):
        """Show one entry of the stash list: a registered tab, or the live preview (None)."""
        self.show_all = False
        self.selected_tab_id = tab_id
        self.selected_slot = None
        self.stash_pages.select(self.dashboard)
        self.refresh_inventory()
        self.draw()

    def select_all(self):
        """Show the whole stash: its total and every item."""
        self.show_all = True
        self.selected_slot = None
        self.refresh_inventory()

    def shown_tab_id(self):
        """The registered tab whose contents the page shows, if any.

        The live preview entry becomes the live tab once tracking synchronises
        one: that tab's entry is then the live view.
        """
        if self.show_all:
            return None
        return self.selected_tab_id or self.live_tab_id()

    def wheel_cards(self, event):
        """Scroll the stash list when the pointer is over it and it overflows."""
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not str(widget).startswith(str(self.cards_canvas)):
            return
        if self.cards_canvas.yview() == (0.0, 1.0):
            return
        self.cards_canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    @staticmethod
    def card_time(stamp):
        """A stored UTC stamp as local time; the date only when it is not today."""
        moment = datetime.fromisoformat(stamp).astimezone()
        return moment.strftime('%H:%M' if moment.date() == datetime.now().date() else '%d/%m %H:%M')

    def tab_summary(self, tab, rows, prices, unit):
        """A registered tab's stored cells, their estimate and what is missing."""
        league = self.league.get().strip()
        entries = [r for r in rows if r[0] == tab['id']]
        estimate = estimate_readings([Reading(r[1], r[2], r[3]) for r in entries], prices, unit)
        # Read and known to be empty is not unread: without this a fully
        # scanned tab would claim to be partial forever.
        confirmed_empty = sum(1 for tab_id, _slot in self.store.empty_slots(league) if tab_id == tab['id'])
        unread = max(0, expected_slot_count(tab)-len(entries)-confirmed_empty)
        uncertain = sum(bool(r[5]) for r in entries)
        missing = []
        if unread or uncertain:
            missing.append(t('dash.card_to_check', count=unread+uncertain))
        if estimate.unpriced:
            missing.append(t('dash.card_unpriced', count=estimate.unpriced))
        approximate = self.store.approximate_slots(league)
        if any((r[0], r[1]) in approximate for r in entries):
            missing.append(t('dash.card_abbreviated'))
        return entries, estimate, missing

    def refresh_cards(self, rows, prices, unit, total):
        """The stash list: the whole stash, one line per tab, then the preview.

        `total` is the whole stash's amount text and what it misses. The live
        loop refreshes several times a second: an unchanged list is left
        alone, and a list with the same lines is updated in place. Rebuilding
        it every time made the lines jump while their values did not change.
        """
        symbol = 'div' if unit=='divine' else unit
        shown = self.shown_tab_id()
        # One line: (identity, title, amount, facts, missing, layout id, live,
        # selected). The identity ('all', a tab id, 'preview') decides its
        # click action; `missing` becomes the amber count and its hint.
        lines = []
        league = self.league.get().strip()
        tabs = [t for t in self.profiles.data['tabs'] if t['league']==league]
        amount, missing = total
        lines.append(('all', t('side.all'), amount, [t('side.all_facts', tabs=len(tabs))], missing,
                      None, False, self.show_all))
        live = self.live_tab_id()
        for tab in tabs:
            entries, estimate, missing = self.tab_summary(tab, rows, prices, unit)
            amount = f'≈ {estimate.amount:,.2f} {symbol}' if estimate.amount is not None else '—'
            # A Runes tab being read names the view on screen, not the family.
            layout_id = (self.active_layout_id if tab['id'] == live and self.active_layout_id
                         else layout_for_tab(tab).id)
            facts = [layout_name(layout_id),
                     self.card_time(max(r[4] for r in entries)) if entries else t('dash.card_never')]
            lines.append((tab['id'], tab['name'], amount, facts, missing, layout_id,
                          tab['id'] == live, tab['id'] == shown))
        # The preview holds readings no tab holds: an unidentified tab or an
        # imported screenshot. It is never added to the total, and there is
        # none before anything is read (start-up, league change).
        preview_readings = self.last_readings if self.reading_league==league else []
        if live is None and preview_readings:
            preview = estimate_readings(preview_readings,prices,unit)
            amount = f'≈ {preview.amount:,.2f} {symbol}' if preview.amount is not None else '—'
            title, subtitle = self.preview_names()
            missing = []
            if preview.unread:
                missing.append(t('dash.card_to_check', count=preview.unread))
            if preview.unpriced:
                missing.append(t('dash.card_unpriced', count=preview.unpriced))
            lines.append(('preview', title, amount, [subtitle, t('dash.card_screenshot')], missing,
                          self.active_layout_id, False, not self.show_all and shown is None))
        lines = [(identity, title, amount, tuple(facts), tuple(missing), layout_id, live, selected)
                 for identity, title, amount, facts, missing, layout_id, live, selected in lines]
        if lines == self._card_lines:
            return
        # The same lines with the same icons are updated in place; any other
        # change (a tab added or removed, an icon appearing) rebuilds the list.
        shape = [(line[0], self.tab_icon(line[5]) is not None) for line in lines]
        if shape != [(card.identity, card.icon is not None) for card in self._card_boxes]:
            for child in self.cards.winfo_children():
                child.destroy()
            self._card_boxes = [self.make_card(identity, has_icon) for identity, has_icon in shape]
            for row, card in enumerate(self._card_boxes):
                card.box.grid(row=row, column=0, sticky='ew', pady=2)
        for card, line in zip(self._card_boxes, lines):
            self.fill_card(card, *line[1:])
        self._card_lines = lines

    def card_action(self, identity):
        if identity == 'all':
            return self.select_all
        return lambda: self.open_stash(None if identity == 'preview' else identity)

    def make_card(self, identity, has_icon):
        """One list line's widgets; `fill_card` sets their text and colours."""
        box = ttk.Frame(self.cards,padding=(12,8),style='Card.TFrame',cursor='hand2')
        box.columnconfigure(1,weight=1)
        card = SimpleNamespace(identity=identity, box=box, icon=None)
        if has_icon:
            card.icon = ttk.Label(box,style='Card.TLabel')
            card.icon.grid(row=0,column=0,rowspan=2,sticky='w',padx=(0,10))
        # Each row in its own frame, so the value and the amber count do not
        # share a column's width. One line each, cut to the list's width:
        # wrapping made lines of two and three rows, and a fixed wrap
        # clipped words ("15 to checl").
        card.rows = [ttk.Frame(box,style='Card.TFrame') for _row in range(2)]
        for row, frame in enumerate(card.rows):
            frame.grid(row=row,column=1,sticky='ew')
        card.title = ttk.Label(card.rows[0],font=(theme.HEADINGS,11),foreground='#e7edf6',style='Card.TLabel')
        card.title.pack(side='left')
        card.amount = ttk.Label(card.rows[0],font=(theme.NUMBERS,11,'bold'),foreground=theme.VALUE,style='Card.TLabel')
        card.amount.pack(side='right',padx=(8,0))
        card.facts = ttk.Label(card.rows[1],font=('Segoe UI',9),style='Card.TLabel')
        card.facts.pack(side='left')
        card.warn = ttk.Label(card.rows[1],style='CardWarn.TLabel')
        card.warn.pack(side='right',padx=(8,0))
        card.hint = ''
        Tooltip(card.warn, lambda: card.hint)
        action = self.card_action(identity)
        for widget in [box, *card.rows, card.title, card.amount, card.facts, card.warn] + ([card.icon] if card.icon else []):
            # Clicking may rebuild the list and destroy the clicked widget:
            # run it after the click's own bindings have finished.
            widget.bind('<Button-1>',lambda event: self.after_idle(action))
            if identity not in ('all', 'preview'):
                widget.bind('<Button-3>',lambda event: self.tab_menu(event, identity))
        return card

    def fill_card(self, card, title, amount, facts, missing, layout_id, live, selected):
        """Two lines: icon, name and value; then the type and time, with an
        amber count of what the estimate misses (in words under the pointer)."""
        kind = ('LiveSelected' if selected else 'Live') if live else ('Selected' if selected else 'Card')
        if live:
            facts = (t('dash.card_live'),) + facts
        for frame in (card.box, *card.rows):
            frame.configure(style=f'{kind}.TFrame')
        for label in (card.title, card.amount, card.facts):
            label.configure(style=f'{kind}.TLabel')
        # Every entry of `missing` but "abbreviated" starts with its count.
        counts = [int(part.split()[0]) for part in missing if part.split()[0].isdigit()]
        warn = f'⚠ {sum(counts)}' if counts else ('≈' if missing else '')
        card.hint = '\n'.join(missing)
        card.warn.configure(text=warn, style=f'{kind}Warn.TLabel')
        # The list has a fixed width; room is what the icon, the paddings,
        # a possible scrollbar and the other label of the row leave.
        room = SIDE_WIDTH - 24 - 16 - (37 if card.icon is not None else 0)
        heading, small, numbers = self.card_fonts()
        card.title.configure(text=fit_text(heading, title, room - numbers.measure(amount) - 8))
        card.amount.configure(text=amount)
        card.facts.configure(text=fit_text(small, ' · '.join(facts), room - small.measure(warn) - 12),
                             foreground='#7ee2c0' if live else '#a9b8ca')
        if card.icon is not None:
            card.icon.configure(image=self.tab_icon(layout_id), style=f'{kind}.TLabel')

    def card_fonts(self):
        if not hasattr(self, '_card_fonts'):
            self._card_fonts = (tkfont.Font(self, family=theme.HEADINGS, size=11),
                                tkfont.Font(self, family='Segoe UI', size=9),
                                tkfont.Font(self, family=theme.NUMBERS, size=11, weight='bold'))
        return self._card_fonts

    def tab_menu(self, event, tab_id):
        tab = next((p for p in self.profiles.data['tabs'] if p['id'] == tab_id), None)
        if tab is None:
            return
        menu = tk.Menu(self, tearoff=0)
        # Through after_idle, like a click: removing rebuilds the list.
        menu.add_command(label=t('tab.remove_menu', name=tab['name']),
                         command=lambda: self.after_idle(lambda: self.remove_tab(tab['id'])))
        menu.tk_popup(event.x_root, event.y_root)

    def remove_tab(self, tab_id):
        """Forget a registered tab and its stored cells, after confirmation.

        The game is not touched: when tracking sees the tab again it registers
        it under a new id and reads every cell from scratch. History and past
        valuations stay; a `TAB_REMOVED` point explains the drop.
        """
        tab = next((p for p in self.profiles.data['tabs'] if p['id'] == tab_id), None)
        if tab is None:
            return
        league = tab['league']
        count = (sum(1 for row in self.store.rows(league) if row[0] == tab_id)
                 + sum(1 for other, _slot in self.store.empty_slots(league) if other == tab_id))
        if not messagebox.askyesno(t('tab.remove_title'), t('tab.remove_confirm', name=tab['name'], count=count),
                                   icon='warning', parent=self):
            return
        self.profiles.remove(tab_id)
        cells = self.store.forget_tab(league, tab_id)
        self.tab_frames.pop(tab_id, None)
        if self.last_tab and self.last_tab['id'] == tab_id:
            # Its readings stay on screen as a preview until it registers again.
            self.last_tab = None
            self.last_scan_synced = False
        if self.selected_tab_id == tab_id:
            self.selected_tab_id = None
            self.show_all = True
        self.selected_slot = None
        log.info('tab removed: %s (%s) league=%s cells=%d', tab['name'], tab_id, league, cells)
        if league == self.league.get().strip():
            self.record_valuation(Event.TAB_REMOVED, force=True)
        self.refresh_inventory()
        self.status.set(t('tab.removed', name=tab['name']))

    def refresh_guide(self):
        """Show the first-run steps until closed, a tab registers or something is read."""
        wanted = not self.guide_done and not self.profiles.data['tabs'] and not self.last_readings
        if wanted and not self.guide.winfo_manager():
            self.guide.pack(fill='x', pady=(0, 12), before=self.view_head)
        elif not wanted and self.guide.winfo_manager():
            self.guide.pack_forget()

    def dismiss_guide(self):
        self.guide_done = True
        settings.write(guide_done=True)
        self.refresh_guide()

    def link_reason_text(self):
        """Why the reading on screen is attached to no tab, in the player's words."""
        if self.active_layout_id is None:
            return t('link.no_layout')
        reason = self.last_reason or t('link.unknown')
        if getattr(self.scanner, 'last_layout_basis', None) == 'icons' and not self.layout_override:
            reason += ' ' + t('link.icons_only')
        return t('link.why', reason=reason)

    def refresh_link(self):
        """Offer to link the preview to a tab while it holds a reading no tab holds."""
        league = self.league.get().strip()
        preview = (not self.show_all and self.shown_tab_id() is None and self.last_tab is None
                   and self.frame is not None and self.reading_league == league and bool(self.last_readings))
        if not preview:
            if self.link_bar.winfo_manager():
                self.link_bar.pack_forget()
            return
        self.link_reason.set(self.link_reason_text())
        family = layout_family(self.active_layout_id) if self.active_layout_id else None
        options = {tab['name']: tab['id'] for tab in self.profiles.data['tabs']
                   if family and tab['league'] == league and layout_family(layout_for_tab(tab).id) == family}
        if family:
            options[t('link.new')] = None
        if options != self._link_options:
            self._link_options = options
            self.link_box.configure(values=list(options))
            if self.link_choice.get() not in options:
                self.link_choice.set(next(iter(options), ''))
        self.link_box.configure(state='readonly' if options else 'disabled')
        if not self.link_bar.winfo_manager():
            self.link_bar.pack(anchor='w', fill='x', pady=(6, 0), after=self.view_note_label)

    def link_tab(self):
        """Attach the reading on screen to the tab the player names, or to a new one."""
        league, layout_id, frame = self.league.get().strip(), self.active_layout_id, self.frame
        if layout_id is None or frame is None:
            self.status.set(t('link.no_layout'))
            return
        choice = self.link_choice.get()
        if choice not in self._link_options:
            self.status.set(t('link.pick'))
            return
        tab_id = self._link_options[choice]
        try:
            if tab_id is None:
                name = simpledialog.askstring(t('link.new_title'), t('link.new_prompt'), parent=self)
                if not name or not name.strip():
                    return
                tab = self.profiles.register_selected(name, league, frame, layout_id)
            else:
                tab = self.profiles.relink(tab_id, frame, layout_id)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self._link_options = {}
        self.status.set(t('link.done', name=tab['name']))
        if not self.running and not self.busy:
            # An imported screenshot is read again, now under its tab.
            self.after_idle(self.analyze)
        self.refresh_inventory()

    def preview_names(self):
        """The preview's title and subtitle.

        It names the tab being read, so the user can tell which tab the live
        readings are feeding; an unidentified tab says so.
        """
        layout = layout_name(self.active_layout_id or 'unknown')
        return ((self.last_tab['name'], t('detail.live_preview_of', layout=layout)) if self.last_tab
                else (t('dash.preview_card'), t('dash.preview_unidentified', layout=layout)))

    def refresh_view(self, rows, prices, unit):
        """The header and body of the chosen entry: whole stash, a tab, or the preview."""
        symbol = 'div' if unit == 'divine' else unit
        wanted, other = (self.all_view, self.tab_view) if self.show_all else (self.tab_view, self.all_view)
        if other.winfo_manager():
            other.pack_forget()
        if not wanted.winfo_manager():
            wanted.pack(fill='both', expand=True)
        live = self.live_tab_id()
        shown = self.shown_tab_id()
        tab = next((p for p in self.profiles.data['tabs'] if p['id'] == shown), None)
        subtitle_colour = '#a9b8ca'
        if tab and not self.show_all:
            if not self.remove_button.winfo_manager():
                self.remove_button.pack(side='right')
        elif self.remove_button.winfo_manager():
            self.remove_button.pack_forget()
        if self.show_all:
            self.view_title.set(t('side.all'))
            self.view_subtitle.set(self.total_title.get())
            self.view_value.set(self.total.get())
            self.view_detail.set(self.total_detail.get())
            self.view_note.set(self.preview_total.get())
        elif tab:
            entries, estimate, missing = self.tab_summary(tab, rows, prices, unit)
            stash = estimate_readings([Reading(r[1], r[2], r[3]) for r in rows], prices, unit).amount
            self.view_title.set(tab['name'])
            when = (t('dash.live_badge') if shown == live else
                    t('view.read_at', time=self.card_time(max(r[4] for r in entries))) if entries
                    else t('dash.card_never'))
            self.view_subtitle.set(f'{layout_name(self.display_layout().id)} · {when}')
            if shown == live:
                subtitle_colour = '#7ee2c0'
            self.view_value.set(f'≈ {estimate.amount:,.2f} {symbol}' if estimate.amount is not None else '—')
            share = ([t('view.share', share=f'{100*estimate.amount/stash:.0f} %')]
                     if estimate.amount is not None and stash else [])
            self.view_detail.set(' · '.join(share + missing))
            self.view_note.set('')
        else:
            league = self.league.get().strip()
            readings = self.last_readings if self.reading_league == league else []
            preview = estimate_readings(readings, prices, unit)
            title, subtitle = self.preview_names()
            self.view_title.set(title)
            self.view_subtitle.set(subtitle)
            self.view_value.set(f'≈ {preview.amount:,.2f} {symbol}' if preview.amount is not None else '—')
            missing = []
            if preview.unread:
                missing.append(t('dash.card_to_check', count=preview.unread))
            if preview.unpriced:
                missing.append(t('dash.card_unpriced', count=preview.unpriced))
            self.view_detail.set(' · '.join(missing))
            self.view_note.set(t('view.preview_note') + ('' if self.last_tab else ' ' + t('dash.auto_add_hint')))
        self.refresh_link()
        self.view_subtitle_label.configure(foreground=subtitle_colour)
        self.refresh_chart()

    @staticmethod
    def chart_time(moment):
        return moment.astimezone().strftime('%d/%m %H:%M')

    def refresh_chart(self):
        """The chosen entry's value over the chosen period, from stored valuations.

        A point keeps the prices it was valued with, so the curve moves with
        the stock and with the market alike; the history page separates them.
        """
        unit = self.unit.get()
        symbol = 'div' if unit == 'divine' else unit
        for key, button in self.period_buttons.items():
            button.configure(style='PeriodOn.TButton' if key == self.chart_period else 'Period.TButton')
        shown = self.shown_tab_id()
        self.chart_title.set(t('chart.title_all' if self.show_all else 'chart.title_tab'))
        self.chart_delta.set('')
        if not self.show_all and shown is None:
            self.stash_chart.empty_key = 'chart.none_preview'
            self.stash_chart.show([], [], symbol)
            return
        self.stash_chart.empty_key = 'chart.empty'
        span = PERIODS[self.chart_period]
        now = datetime.now(timezone.utc)
        points = [point for point in self._valuations
                  if not span or (now-datetime.fromisoformat(point['time'])).total_seconds() <= span]
        times = [datetime.fromisoformat(point['time']) for point in points]
        values = [point_value(point, unit, None if self.show_all else [shown]) for point in points]
        if not self.show_all:
            # A tab absent from a point has no value there, not a zero.
            values = [None if point.get('tabs', {}).get(shown, {}).get('amount') is None else value
                      for point, value in zip(points, values)]
        valid = [v for v in values if v is not None]
        if len(valid) < 2:
            self.stash_chart.show([], [], symbol)
            return
        self.stash_chart.show(times, values, symbol)
        # The curve shows every point, tabs being registered included; the
        # change compares like with like (`stock_change`).
        since = ''
        if self.show_all:
            change = stock_change(points, unit)
            if change is None:
                return
            start, before, after = change
            if start is not points[values.index(valid[0])]:
                since = ' ' + t('chart.since', time=self.chart_time(datetime.fromisoformat(start['time'])))
        else:
            before, after = valid[0], valid[-1]
        change = after-before
        text = f"{'+' if change >= 0 else '−'}{abs(change):,.2f} {symbol}"
        if before > 0:
            text += f" ({'+' if change >= 0 else '−'}{100*abs(change)/before:.0f} %)"
        text += since
        self.chart_delta.set(text)
        self.chart_delta_label.configure(foreground=theme.GAIN if change >= 0 else theme.LOSS)

    def refresh_items(self, rows, approximate, prices, unit):
        """One line per item across every tab: quantity, unit price, value, share.

        `rows` has the shape of `Store.rows()`; the preview passes its readings
        with no tab. Unpriced items stay listed with no value, never a zero.
        """
        symbol = 'div' if unit == 'divine' else unit
        self.set_heading(self.items_tree, 'col.unit_price', t('col.unit_price', unit=symbol))
        self.set_heading(self.items_tree, 'col.value', t('col.value_unit', unit=symbol))
        names = {tab['id']: tab['name'] for tab in self.profiles.data['tabs']}
        items = {}
        for tab, slot, item, quantity, _stamp, _uncertain in rows:
            entry = items.setdefault(item, dict(quantity=0, approximate=False, tabs=set()))
            entry['quantity'] += quantity
            entry['approximate'] |= (tab, slot) in approximate
            if tab is not None:
                entry['tabs'].add(names.get(tab, tab))
        values = {item: line_value(item, entry['quantity'], prices, unit) for item, entry in items.items()}
        total = sum(value for value in values.values() if value is not None)
        shown = []
        for item, entry in items.items():
            value, each = values[item], line_value(item, 1, prices, unit)
            shown.append((item, dict(image=self.item_icon(item), text=' '+self.item_name(item),
                                     values=(('≈ ' if entry['approximate'] else '')+f"{entry['quantity']:,}",
                                             '—' if each is None else f'{each:,.3f}',
                                             '—' if value is None else f'{value:,.2f}',
                                             '—' if value is None or not total else f'{100*value/total:.1f} %',
                                             ', '.join(sorted(entry['tabs']))))))
        self.fill_tree(self.items_tree, shown)

    def tab_icon(self, layout_id):
        """The in-game icon of a stash type, or '' for an unrecognised layout.

        Keyed by family, so the five Runes views share the Augment tab icon.
        """
        family = layout_family(layout_id) if layout_id else None
        if family not in self._tab_icons:
            file = TAB_ICONS / f'{family}.png'
            self._tab_icons[family] = (ImageTk.PhotoImage(Image.open(file), master=self)
                                       if family and file.exists() else '')
        return self._tab_icons[family]

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
        gate = ChangeGate()
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
                registrable = tab is None and layout_id and tab_ocr and self.may_register()
                if tab is None and layout_id and tab_ocr and registrable:
                    tab, reason = self.profiles.observe(frame, league, layout_id, tab_ocr)
                if tab is None and layout_id:
                    basis = getattr(self.scanner, 'last_layout_basis', None)
                    verdict = (f'{layout_id} by {basis}: {reason or "no reason"}' +
                               ('' if registrable else ' | cannot register: layout not confirmed by borders or selector, or no title OCR'))
                    if gate.passes('attach', verdict):
                        log.info('reading not attached to a tab: %s', verdict)
                if layout_id is None:
                    self.scanner.reset_incremental()
                    activity('preview', t('status.unknown_layout'))
                    if last_signature != ('unknown',):
                        self.messages.put(('live', ScanResult(frame, None, [], '', league, None)))
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
                    self.messages.put(('live', ScanResult(frame, tab, readings, reason, league,
                                                          layout_id, tuple(provisional))))
                    last_signature = signature
        except Exception as exc:
            failure('live_loop', exc)
            self.messages.put(('error', str(exc)))
        finally:
            log.info('tracking stopped after %d scans', scans)
            self.messages.put(('stopped', None))

    def show_readings(self, readings):
        self.read_notes = {}
        readings = [r for r in readings if r.reason != Reason.EMPTY]
        provisional = {r.slot:r for r in self.provisional_readings} if self.showing_live() else {}
        unit = self.unit.get()
        prices = self.market['prices'] if self.league.get().strip() == self.market_league else {}
        symbol = 'div' if unit == 'divine' else unit
        self.set_heading(self.read_tree, 'col.unit_price', t('col.unit_price', unit=symbol))
        self.set_heading(self.read_tree, 'col.value', t('col.value_unit', unit=symbol))
        identified = sum(bool(r.item) for r in readings)
        ambiguous = sum(bool(r.alternatives) and not r.item for r in readings)
        self.recognition_status.set(
            t('detail.recognition', identified=identified, total=len(readings), ambiguous=ambiguous)
            if readings else t('detail.recognition_none'))
        # On the tab being synchronised, a cell that is re-confirming or unreadable
        # right now still has its last confirmed quantity in storage. Show that
        # quantity and its value rather than a blank, as long as the same item is
        # recognised; the new observation stays marked provisional beside it.
        live = self.live_tab_id() if self.showing_live() else None
        league = self.league.get().strip()
        confirmed = ({slot: (item, quantity) for tab, slot, item, quantity, _stamp, _uncertain
                      in self.store.rows(league) if tab == live} if live else {})
        abbreviated = self.store.approximate_slots(league) if live else set()
        lines = []
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
            known = confirmed.get(r.slot)
            fallback = bool(r.quantity is None and r.item and known and known[0] == r.item)
            if fallback:
                stored = known[1]
                value = line_value(r.item, stored, prices, unit)
                quantity_text = ('≈ ' if (live, r.slot) in abbreviated else '')+f'{stored:,}'
                if pending and (candidate.quantity != stored or candidate.approximate != ((live, r.slot) in abbreviated)):
                    quantity_text += ' → '+('≈ ' if candidate.approximate else '')+f'{candidate.quantity:,}'+t('reading.provisional')
            # What the line needs from the user: nothing, patience, or attention.
            attention = r.reason in (Reason.UNREADABLE_COUNT, Reason.UNKNOWN_ICON, Reason.VARIANT,
                                     Reason.HIDDEN_ICON, Reason.TO_CHECK)
            waiting = r.reason == Reason.PENDING
            notes = [t('note.last_confirmed') if fallback and waiting else
                     t('note.'+r.reason) if waiting or attention or r.reason in (Reason.MANUAL, Reason.LOCAL_REF)
                     else t('note.fine')]
            if fallback and attention:
                notes.append(t('note.last_confirmed'))
            if shown_approximate or (fallback and (live, r.slot) in abbreviated):
                notes.append(t('note.abbreviated'))
            self.read_notes[r.slot] = ' '.join(notes)
            lines.append((r, index, attention, waiting, quantity_text, value))
        # A line's share of what this tab's valued lines add up to.
        total = sum(line[5] for line in lines if line[5] is not None)
        shown = []
        for r, index, attention, waiting, quantity_text, value in lines:
            each = line_value(r.item, 1, prices, unit)
            # Stripes are left to apply_sort, which follows the displayed order.
            shown.append((r.slot, dict(image=self.item_icon(r.item, r.alternatives, warn=attention),
                                       text=' '+self.reading_name(r)+('  ⚠' if attention else ''),
                                       tags=('attention',) if attention else ('pending',) if waiting else (),
                                       values=(quantity_text, '—' if each is None else f'{each:,.3f}',
                                               '—' if value is None else f'{value:.3f}',
                                               '—' if value is None or not total else f'{100*value/total:.1f} %'))))
        self.fill_tree(self.read_tree, shown)
        # The table is rebuilt on every live reading; keep the chosen line.
        if self.selected_slot and self.read_tree.exists(self.selected_slot):
            self.read_tree.selection_set(self.selected_slot)
            self.show_note(self.selected_slot)
        else:
            self.show_note(None)

    def show_note(self, slot):
        """The selected line's explanation, amber when it needs attention."""
        attention = slot is not None and 'attention' in self.read_tree.item(slot, 'tags')
        self.read_note.set(self.read_notes.get(slot, '') if slot else t('note.legend'))
        self.read_note_label.configure(foreground='#ffcf70' if attention else '#b0bfd2')
        # A cell chosen on the screenshot keeps its controls without a line.
        self.show_fix(bool(slot or self.selected_slot))

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
        expected = sum(expected_slot_count(profile) for profile in self.profiles.data['tabs']
                       if profile['league'] == league)
        amount = stored.amount if rows else preview.amount
        estimate = stored if rows else preview
        missing = estimate.unpriced
        empty_slots = self.store.empty_slots(league)
        unread = max(0, expected-len(rows)-len(empty_slots)) if rows else estimate.unread
        partial = bool(missing or unread or uncertain)
        self.total.set((f'≈ {amount:,.2f} {symbol}' + (t('dash.total_partial') if partial else '')) if amount is not None else '—')
        if rows:
            tabs = len({row[0] for row in rows})
            self.total_title.set(t('dash.tracked', tabs=tabs))
            self.total_detail.set(t('dash.tracked_detail', unread=unread, missing=missing, uncertain=uncertain))
            preview_text = f'≈ {preview.amount:,.2f} {symbol}' if preview.amount is not None else '—'
            self.preview_total.set(t('dash.preview_line', amount=preview_text)
                                   if readings and self.live_tab_id() is None else '')
        else:
            self.total_title.set(t('dash.displayed_title'))
            self.total_detail.set(t('dash.displayed_detail', valued=estimate.valued, unread=unread, missing=missing)
                                  if readings else t('dash.total_placeholder'))
            self.preview_total.set(t('dash.auto_add_hint') if readings and not self.last_tab else '')
        approximate_slots = self.store.approximate_slots(league)
        if (approximate_slots if rows else any(r.approximate for r in readings)):
            self.total_detail.set(self.total_detail.get()+t('dash.abbreviated_suffix'))
        self.show_readings(self.display_readings())
        self.refresh_items(rows if rows else [(None, r.slot, r.item, r.quantity, '', 0) for r in readings
                                              if r.item and r.quantity is not None],
                           approximate_slots if rows else {(None, r.slot) for r in readings if r.approximate},
                           prices, unit)
        self.record_valuation()
        names = {tab_id: t('history.removed_tab', name=name)
                 for tab_id, name in self.profiles.data.get('removed', {}).items()}
        names.update({tab['id']: tab['name'] for tab in self.profiles.data['tabs']})
        latest = self.store.db.execute('SELECT MAX(id) FROM valuations WHERE league=?', (league,)).fetchone()[0]
        history_key = (league, latest, tuple(names.items()))
        if getattr(self, '_history_key', None) != history_key:
            self._history_key = history_key
            self._valuations = self.store.valuations(league)
            self.valuation_view.refresh(self._valuations, names, self.store.active_session(league),
                                        self.store.last_completed_session(league))
        overview = []
        if unread or uncertain:
            overview.append(t('dash.card_to_check', count=unread+uncertain))
        if missing:
            overview.append(t('dash.card_unpriced', count=missing))
        self.refresh_cards(rows, prices, unit,
                           (f'≈ {amount:,.2f} {symbol}' if amount is not None else '—', overview))
        self.refresh_view(rows, prices, unit)
        self.refresh_guide()
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
        expected = {tab['id']: expected_slot_count(tab)
                    for tab in self.profiles.data['tabs'] if tab['league'] == league}
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
                    if 'icons' in market:
                        self.icon_images, self._thumbs = market['icons'], {}
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
                elif kind == 'update_check':
                    self.update_checked(payload)
                elif kind == 'update_progress':
                    percent = int(100 * payload.done / payload.total) if payload.total else 0
                    self.show_update_text('update.downloading', version=self.update_release.label,
                                          percent=percent)
                elif kind == 'update_ready':
                    self.install_update(payload)
                elif kind == 'update_failed':
                    self.update_failed(payload)
                elif kind in ('analysis', 'live'):
                    scan = payload
                    tab, readings, league = scan.tab, scan.readings, scan.league
                    if league != self.league.get().strip():
                        continue
                    if tab and tab['id'] in self.profiles.data.get('removed', {}):
                        # Removed while this scan was in flight: syncing it would
                        # write rows back under an id no tab holds.
                        tab = None
                    self.frame, self.last_tab, self.last_readings = scan.frame, tab, readings
                    self.last_reason = scan.reason
                    self.last_scan_synced = kind == 'live' and tab is not None
                    self.provisional_readings = list(scan.provisional) if kind == 'live' else []
                    self.reading_league = league
                    self.active_layout_id = scan.layout_id
                    if tab:
                        self.tab_frames[tab['id']] = scan.frame.copy()
                    # The header follows through refresh_inventory below.
                    self.show_readings(self.display_readings())
                    self.draw()
                    if kind == 'live' and tab:
                        self.store.sync(league, tab['id'], readings)
                        self.refresh_inventory()
                        occupied = [r for r in readings if r.reason != Reason.EMPTY]
                        known = sum(r.item is not None and r.quantity is not None for r in occupied)
                        detail = (t('status.synced_partial', name=tab['name'], known=known, total=len(occupied))
                                  if known < len(occupied) else t('status.synced', name=tab['name']))
                        self.status.set(f'{scan.reason} {detail}' if scan.reason else detail)
                    else:
                        self.refresh_inventory()
                        occupied = [r for r in readings if r.reason != Reason.EMPTY]
                        known = sum(r.item is not None and r.quantity is not None for r in occupied)
                        suffix = (scan.reason or (t('status.tab_to_recognise') if not tab
                                                  else t('status.ready_for_tracking')))
                        self.status.set(t('status.identified', known=known, total=len(occupied), suffix=suffix)
                                        if scan.layout_id else t('status.unknown_layout_short'))
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
                    self.refresh_inventory()
                    self.refresh_capture_state()
                    self.league_box.configure(state='normal')
                    if self.stop_event.is_set():
                        self.status.set(t('status.paused'))
        except queue.Empty:
            pass
        self.after(100, self.drain)

    # --- Updates -------------------------------------------------------------

    def build_update_bar(self):
        """The banner offering a new version; packed only while there is one."""
        bar = self.update_bar = ttk.Frame(self, padding=(16, 8), style='Update.TFrame')
        ttk.Label(bar, textvariable=self.update_message, style='Update.TLabel').pack(side='left')
        self.update_buttons = []
        for key, action in [('update.skip', self.skip_update), ('update.later', self.hide_update_bar),
                            ('update.notes', self.open_release_notes)]:
            button = self.tr(ttk.Button(bar, text='', command=action), key)
            button.pack(side='right', padx=(6, 0))
            self.update_buttons.append(button)
        self.update_install = self.tr(ttk.Button(bar, text='', command=self.download_update,
                                                 style='Accent.TButton'), 'update.install')
        self.update_install.pack(side='right', padx=(6, 0))

    def show_update_text(self, key, **fields):
        self._update_text = (key, fields)
        self.update_message.set(t(key, **fields) if key else '')

    def show_update_bar(self):
        if not self.update_bar.winfo_manager():
            self.update_bar.pack(fill='x', after=self.header)

    def hide_update_bar(self):
        if not self.update_busy:
            self.update_bar.pack_forget()

    def update_auto_changed(self):
        settings.write(update_auto=bool(self.update_auto.get()))
        log.info('automatic update check %s', 'on' if self.update_auto.get() else 'off')

    def check_updates(self, manual=False):
        """The daily check runs in a worker; its answer comes back through `drain`."""
        if self.update_busy or not (manual or updater.due(settings.read())):
            return
        self.update_busy = True
        if manual:
            self.status.set(t('update.checking'))

        def work():
            updater.clean(DATA / 'updates')
            try:
                self.messages.put(('update_check', UpdateCheck(updater.newer_release(), manual)))
            except Exception as error:
                log.info('update check failed: %s', error)
                self.messages.put(('update_failed', UpdateFailure('check', manual, 'check')))
        threading.Thread(target=work, daemon=True).start()

    def update_checked(self, check):
        self.update_busy = False
        settings.write(update_checked=time.time())
        release = check.release
        if release is None:
            log.info('update check: %s is the latest version', __version__)
            if check.manual:
                self.status.set(t('update.up_to_date', current=__version__))
            return
        log.info('update check: %s available (running %s)', release.label, __version__)
        if not check.manual and settings.read().get('update_skip') == release.label:
            return
        self.update_release = release
        self.update_install.configure(text=t('update.install'))
        self.show_update_text('update.available', version=release.label, current=__version__)
        self.set_update_buttons(True)
        self.show_update_bar()

    def set_update_buttons(self, enabled):
        state = ['!disabled'] if enabled else ['disabled']
        for button in [self.update_install, *self.update_buttons]:
            button.state(state)

    def open_release_notes(self):
        if self.update_release and updater.permitted(self.update_release.page_url):
            webbrowser.open(self.update_release.page_url)

    def skip_update(self):
        if self.update_release and not self.update_busy:
            settings.write(update_skip=self.update_release.label)
            self.status.set(t('update.skipped', version=self.update_release.label))
            self.update_bar.pack_forget()

    def download_update(self):
        release = self.update_release
        if release is None or self.update_busy:
            return
        self.update_busy = True
        self.set_update_buttons(False)
        self.show_update_text('update.downloading', version=release.label, percent=0)
        log.info('update: downloading %s', release.installer_url)
        shown = [-1]

        def progress(done, total):
            percent = int(100 * done / total) if total else 0
            if percent != shown[0]:
                shown[0] = percent
                self.messages.put(('update_progress', UpdateProgress(done, total)))

        def work():
            try:
                path = updater.download(release, DATA / 'updates', progress)
            except updater.UpdateError as error:
                log.warning('update download refused: %s', error)
                self.messages.put(('update_failed', UpdateFailure(error.key, True, 'download')))
            except Exception as error:
                log.warning('update download failed: %s', error)
                self.messages.put(('update_failed', UpdateFailure('download', True, 'download')))
            else:
                self.messages.put(('update_ready', path))
        threading.Thread(target=work, daemon=True).start()

    def install_update(self, installer):
        release = self.update_release
        self.show_update_text('update.installing', version=release.label)
        try:
            updater.start_install(installer, i18n.language())
        except OSError as error:
            log.warning('update: installer did not start: %s', error)
            self.update_failed(UpdateFailure('install', True, 'install'))
            return
        log.info('update: installer %s started, closing', installer.name)
        # The installer also waits for this process through the Restart Manager.
        self.after(500, self.close)

    def update_failed(self, failure):
        self.update_busy = False
        if failure.stage == 'check':
            if failure.manual:
                self.status.set(t('update.error.check'))
            return
        self.show_update_text(f'update.error.{failure.key}')
        self.update_install.configure(text=t('update.retry'))
        self.set_update_buttons(True)
        self.show_update_bar()

    def close(self):
        self.stop_event.set()
        self.store.close()
        self.destroy()
