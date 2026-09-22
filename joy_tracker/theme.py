"""Explicit colours for every ttk state, including Windows readonly controls."""
from tkinter import ttk

BG = '#10151e'
SURFACE = '#192332'
TEXT = '#edf3fc'
MUTED = '#b0bfd2'
ACCENT = '#7ee2c0'


def apply_theme(root):
    root.option_add('*Font', '{Segoe UI} 10')
    root.option_add('*TCombobox*Listbox.background', SURFACE)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', '#315879')
    root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BG, foreground=TEXT, font=('Segoe UI',10),
                    bordercolor='#304157', lightcolor=BG, darkcolor=BG,
                    troughcolor=BG, selectbackground='#315879', selectforeground='#ffffff')
    style.configure('TFrame', background=BG)
    style.configure('Card.TFrame', background=SURFACE, relief='flat')
    style.configure('Card.TLabel', background=SURFACE, foreground=TEXT)
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Status.TLabel', background=SURFACE, foreground=MUTED, padding=(16,10))
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
                    font=('Segoe UI',10,'bold'), padding=(8,10), relief='flat')
    style.map('Treeview.Heading', background=[('active','#304963')], foreground=[('active',TEXT)])
    style.configure('Vertical.TScrollbar', background='#35485f', arrowcolor=MUTED,
                    troughcolor=BG, borderwidth=0, arrowsize=12)
    style.map('Vertical.TScrollbar', background=[('active','#526e8e')])
