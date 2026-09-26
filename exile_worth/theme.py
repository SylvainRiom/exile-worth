"""Explicit colours for every ttk state, including Windows readonly controls."""
import ctypes
import sys
from tkinter import font as tkfont, ttk

BG = '#10151e'
SURFACE = '#192332'
TEXT = '#edf3fc'
MUTED = '#b0bfd2'
ACCENT = '#7ee2c0'
LIVE = '#173229'
UPDATE = '#1d3350'
SELECTED = '#2a3b54'
LIVE_SELECTED = '#1f4a38'
# Each colour says one thing: gold is value, green is live or a rise, red a
# fall, amber something the player should look at. Green once meant all five.
VALUE = '#e9c46a'
GAIN = '#83f0b6'
LOSS = '#ff9b8a'
WARN = '#ffcf70'
SUBTLE = '#a9b8ca'
# Numbers are set in Bahnschrift (shipped with Windows): its digits share one
# width, so amounts line up and do not jitter as they change. `apply_theme`
# falls back to Segoe UI where it is missing.
NUMBERS = 'Bahnschrift'
HEADINGS = 'Segoe UI Semibold'


def dark_title_bar(window):
    """Ask Windows 10/11 for a dark title bar; elsewhere, nothing happens."""
    if sys.platform != 'win32':
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        on = ctypes.c_int(1)
        # 20 is DWMWA_USE_IMMERSIVE_DARK_MODE; builds before 20H1 used 19.
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(on),
                                                          ctypes.sizeof(on)) == 0:
                break
    except (AttributeError, OSError):
        pass


def apply_theme(root):
    root.option_add('*Font', '{Segoe UI} 10')
    root.option_add('*TCombobox*Listbox.background', SURFACE)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', '#315879')
    root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
    global NUMBERS, HEADINGS
    families = set(tkfont.families(root))
    NUMBERS = NUMBERS if NUMBERS in families else 'Segoe UI'
    HEADINGS = HEADINGS if HEADINGS in families else 'Segoe UI'
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BG, foreground=TEXT, font=('Segoe UI',10),
                    bordercolor='#304157', lightcolor=BG, darkcolor=BG,
                    troughcolor=BG, selectbackground='#315879', selectforeground='#ffffff')
    style.configure('TFrame', background=BG)
    style.configure('Card.TFrame', background=SURFACE, relief='flat')
    style.configure('Card.TLabel', background=SURFACE, foreground=TEXT)
    # The two pages are chosen from the header, not from notebook tabs.
    style.layout('Pages.TNotebook.Tab', [])
    style.configure('Pages.TNotebook', background=BG, borderwidth=0, tabmargins=0)
    style.configure('Nav.TButton', background=BG, foreground=MUTED, padding=(14,6), font=(HEADINGS,11))
    style.configure('NavOn.TButton', background=SELECTED, foreground=TEXT, padding=(14,6), font=(HEADINGS,11))
    style.map('Nav.TButton', background=[('active','#233247')], foreground=[('active',TEXT)])
    style.map('NavOn.TButton', background=[('active',SELECTED)])
    # The card of the tab the live loop is synchronising.
    style.configure('Live.TFrame', background=LIVE, relief='flat')
    style.configure('Live.TLabel', background=LIVE, foreground=TEXT)
    # The entry of the stash list whose contents are shown on the right.
    style.configure('Selected.TFrame', background=SELECTED, relief='flat')
    style.configure('Selected.TLabel', background=SELECTED, foreground=TEXT)
    style.configure('LiveSelected.TFrame', background=LIVE_SELECTED, relief='flat')
    style.configure('LiveSelected.TLabel', background=LIVE_SELECTED, foreground=TEXT)
    # A side panel, and the chart's period buttons (the chosen one is lit).
    style.configure('Panel.TFrame', background=SURFACE)
    style.configure('Panel.TLabel', background=SURFACE, foreground=TEXT)
    style.configure('Period.TButton', background=BG, foreground=MUTED, padding=(10,4))
    style.configure('PeriodOn.TButton', background='#2a3b54', foreground=TEXT, padding=(10,4))
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('TCheckbutton', background=BG, foreground=TEXT, indicatorbackground=SURFACE,
                    indicatorforeground=ACCENT, focusthickness=0)
    style.map('TCheckbutton', background=[('active',BG)], foreground=[('disabled','#91a0b4')],
              indicatorbackground=[('pressed','#304963'),('active','#26384e')])
    # The banner offering a new version.
    style.configure('Update.TFrame', background=UPDATE)
    style.configure('Update.TLabel', background=UPDATE, foreground=TEXT, font=('Segoe UI',10,'bold'))
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Status.TLabel', background=SURFACE, foreground=MUTED, padding=(16,6))
    style.configure('Status.TFrame', background=SURFACE)
    # The toolbar's menus look like its buttons.
    style.configure('TMenubutton', background='#233247', foreground=TEXT, padding=(12,8),
                    borderwidth=0, relief='flat', arrowcolor=MUTED)
    style.map('TMenubutton', background=[('pressed','#375777'),('active','#304963')],
              foreground=[('active','#ffffff')])
    # The amber count on a stash list line.
    for kind, background in (('Card', SURFACE), ('Live', LIVE), ('Selected', SELECTED),
                             ('LiveSelected', LIVE_SELECTED)):
        style.configure(f'{kind}Warn.TLabel', background=background, foreground='#ffcf70',
                        font=('Segoe UI',9,'bold'))
    style.configure('TButton', background='#233247', foreground=TEXT, padding=(12,8),
                    borderwidth=0, relief='flat', focusthickness=0)
    style.map('TButton', background=[('disabled','#1c2736'),('pressed','#375777'),('active','#304963')],
              foreground=[('disabled','#91a0b4'),('active','#ffffff')])
    style.configure('Accent.TButton', background=ACCENT, foreground='#10251f', font=('Segoe UI',10,'bold'))
    style.map('Accent.TButton', background=[('disabled','#334e48'),('pressed','#54bb99'),('active','#a2f0d6')],
              foreground=[('disabled','#bfcec9'),('!disabled','#10251f')])
    style.configure('TCombobox', fieldbackground=SURFACE, background='#26384e',
                    foreground=TEXT, arrowcolor=TEXT, padding=7, borderwidth=1)
    style.map('TCombobox', fieldbackground=[('disabled','#202a38'),('readonly',SURFACE)],
              foreground=[('disabled','#a4b2c4'),('readonly',TEXT)],
              selectbackground=[('readonly',SURFACE)], selectforeground=[('readonly',TEXT)],
              background=[('active','#354c66'),('readonly','#26384e')])
    style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0,8,0,0))
    style.configure('TNotebook.Tab', background=BG, foreground=MUTED, padding=(18,10), borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected',SURFACE),('active','#233247')],
              foreground=[('selected',ACCENT),('active',TEXT)])
    style.configure('Treeview', background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    rowheight=34, borderwidth=0, relief='flat')
    style.map('Treeview', background=[('selected','#315879')], foreground=[('selected','#ffffff')])
    style.configure('Treeview.Heading', background='#223247', foreground=MUTED,
                    font=(HEADINGS,10), padding=(8,10), relief='flat')
    style.map('Treeview.Heading', background=[('active','#304963')], foreground=[('active',TEXT)])
    # Thin scrollbars with no arrows: a thumb on the page's own background.
    style.layout('Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
        ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
    style.configure('Vertical.TScrollbar', background='#2c3b50', troughcolor=BG, borderwidth=0,
                    arrowsize=8, gripcount=0, lightcolor='#2c3b50', darkcolor='#2c3b50', bordercolor=BG)
    style.map('Vertical.TScrollbar', background=[('active','#46607f')])
