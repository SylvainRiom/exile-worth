"""Historical values always use their stored price basis, in divines."""
import csv
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, ttk

from .i18n import t
from .model import Reading, estimate_readings, item_changes

MODE_KEYS = ('history.mode_current', 'history.mode_fixed')


def fixed_value(point, prices):
    return estimate_readings([Reading(r[1], r[2], r[3]) for r in point['rows']], prices).amount


def quality(point, prices=None):
    tabs = point['tabs'].values()
    unread = sum(entry['unread'] + entry['uncertain'] for entry in tabs)
    unpriced = sum(entry['unpriced'] for entry in tabs)
    if prices is not None:
        unpriced = estimate_readings([Reading(r[1],r[2],r[3]) for r in point['rows']], prices).unpriced
    approximate = sum(entry['approximate'] for entry in tabs)
    return t('history.quality', unread=unread, unpriced=unpriced, approximate=approximate) + \
        (t('history.quality_stale') if point['stale'] else '')


class LineChart:
    """A value over time on a Tk canvas, with a readout under the pointer.

    The history page and the stash page's small chart share it. A `None` value
    breaks the line: the point had no price basis.
    """
    def __init__(self, canvas, height, empty_key, stamp_text, on_click=None):
        self.canvas, self.height, self.empty_key = canvas, height, empty_key
        self.stamp_text, self.on_click = stamp_text, on_click
        self.times, self.values, self.unit, self.points = [], [], 'div', []
        canvas.bind('<Configure>', lambda event: self.draw())
        canvas.bind('<Motion>', self.hover)
        canvas.bind('<Leave>', lambda event: canvas.delete('hover'))

    def show(self, times, values, unit):
        self.times, self.values, self.unit = list(times), list(values), unit
        self.draw()

    def draw(self):
        canvas = self.canvas
        canvas.delete('all')
        self.points = []
        valid = [v for v in self.values if v is not None]
        if not valid:
            canvas.create_text(20, self.height//2, anchor='w', fill='#a9b8ca', text=t(self.empty_key))
            return
        width, height = max(canvas.winfo_width(), 300), self.height
        low, high = min(valid), max(valid)
        span = high-low or max(abs(high)*.1, 1)
        stamps = [moment.timestamp() for moment in self.times]
        duration = stamps[-1]-stamps[0]
        previous = None
        for index, value in enumerate(self.values):
            if value is None:
                previous = None
                continue
            x = 85+(width-115)*((stamps[index]-stamps[0])/duration if duration else index/max(len(self.values)-1, 1))
            y = height-28-(height-46)*(value-low)/span
            if previous:
                canvas.create_line(*previous, x, y, fill='#83f0b6', width=2)
            dot = canvas.create_oval(x-3, y-3, x+3, y+3, fill='#83f0b6', outline='')
            if self.on_click:
                canvas.tag_bind(dot, '<Button-1>', lambda event, i=index: self.on_click(i))
            self.points.append((x, y, index))
            previous = (x, y)
        for y, label in [(12, f'{high:,.2f} {self.unit}'), (height-28, f'{low:,.2f} {self.unit}')]:
            canvas.create_text(5, y, anchor='w', fill='#a9b8ca', text=label)
        canvas.create_text(85, height-9, anchor='w', fill='#a9b8ca', text=self.stamp_text(self.times[0]))
        canvas.create_text(width-12, height-9, anchor='e', fill='#a9b8ca', text=self.stamp_text(self.times[-1]))

    def hover(self, event):
        """A dashed guide on the nearest point, with its value and time."""
        canvas = self.canvas
        canvas.delete('hover')
        if not self.points:
            return
        x, y, index = min(self.points, key=lambda point: abs(point[0]-event.x))
        canvas.create_line(x, 6, x, self.height-28, fill='#a9b8ca', dash=(3, 3), tags='hover')
        canvas.create_oval(x-5, y-5, x+5, y+5, fill='#83f0b6', outline='#17202d', width=2, tags='hover')
        text = f'≈ {self.values[index]:,.2f} {self.unit} · {self.stamp_text(self.times[index])}'
        right = x > max(canvas.winfo_width(), 300)-260
        label = canvas.create_text(x-10 if right else x+10, 14, anchor='ne' if right else 'nw',
                                   fill='#edf3fc', text=text, tags='hover')
        box = canvas.bbox(label)
        canvas.tag_lower(canvas.create_rectangle(box[0]-6, box[1]-4, box[2]+6, box[3]+4,
                                                 fill='#25344a', outline='', tags='hover'), label)


class HistoryView(ttk.Frame):
    def __init__(self, parent, mark_session, item_name=lambda item: item):
        super().__init__(parent, padding=16)
        self.points = []
        self.names = {}
        self.item_name = item_name
        self.session_note = None
        # The two points a session's gains compare: its start, then its end or
        # the latest point while it is open (`refresh`).
        self.session_span = None
        # The selected mode is held as a key: comparing display text would break
        # as soon as the language changes.
        self.mode_key = MODE_KEYS[0]
        self.mode = tk.StringVar(value=t(self.mode_key))
        self.summary = tk.StringVar(value=t('history.empty'))
        self.details = tk.StringVar()
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        self.mode_box = ttk.Combobox(bar, textvariable=self.mode, state='readonly', width=33,
                                     values=[t(key) for key in MODE_KEYS])
        self.mode_box.pack(side='left')
        self.session_button = ttk.Button(bar, text=t('history.session_start'), command=mark_session)
        self.session_button.pack(side='left', padx=8)
        self.export_button = ttk.Button(bar, text=t('history.export'), command=self.export)
        self.export_button.pack(side='right')
        self.note = ttk.Label(self, text=t('history.note'), foreground='#a9b8ca')
        self.note.pack(anchor='w', pady=8)
        ttk.Label(self, textvariable=self.summary, wraplength=1100).pack(anchor='w')
        self.chart = tk.Canvas(self, height=210, background='#17202d', highlightthickness=0)
        self.chart.pack(fill='x', pady=10)
        self.line = LineChart(self.chart, 210, 'history.chart_empty', self.local_time,
                              on_click=lambda index: self.choose(self.points[index]['id']))
        self.mode.trace_add('write', self.mode_changed)
        self.tree = ttk.Treeview(self, columns=('date', 'reason', 'value', 'quality'), show='headings', height=7)
        self.columns = [('date','history.col_date',170), ('reason','history.col_event',140),
                        ('value','history.col_value',130), ('quality','history.col_quality',460)]
        for key, title, width in self.columns:
            self.tree.heading(key, text=t(title))
            self.tree.column(key, width=width)
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        # What the session gained and lost, item by item (`item_changes`).
        self.gains_box = ttk.Frame(self)
        self.gains_title = tk.StringVar()
        ttk.Label(self.gains_box, textvariable=self.gains_title, foreground='#a9b8ca').pack(anchor='w', pady=(8, 4))
        self.gains = ttk.Treeview(self.gains_box, columns=('item', 'before', 'after', 'change', 'value'),
                                  show='headings', height=6)
        self.gains_columns = [('item', 'gains.col_item', 300), ('before', 'gains.col_before', 110),
                              ('after', 'gains.col_after', 110), ('change', 'gains.col_change', 110),
                              ('value', 'gains.col_value', 140)]
        for key, title, width in self.gains_columns:
            self.gains.heading(key, text=t(title))
            self.gains.column(key, width=width, anchor='w' if key == 'item' else 'e')
        self.gains.tag_configure('gain', foreground='#83f0b6')
        self.gains.tag_configure('loss', foreground='#ff9b8a')
        self.gains.pack(fill='x')
        self.details_label = ttk.Label(self, textvariable=self.details, wraplength=1100, foreground='#a9b8ca')
        self.details_label.pack(anchor='w', pady=8)

    def mode_changed(self, *_):
        shown = self.mode.get()
        self.mode_key = next((key for key in MODE_KEYS if t(key) == shown), MODE_KEYS[0])
        self.render()

    def historical(self):
        return self.mode_key == MODE_KEYS[0]

    def retranslate(self):
        """Relabel every static widget after a language change."""
        self.mode_box.configure(values=[t(key) for key in MODE_KEYS])
        self.mode.set(t(self.mode_key))
        self.export_button.configure(text=t('history.export'))
        self.note.configure(text=t('history.note'))
        for key, title, _ in self.columns:
            self.tree.heading(key, text=t(title))
        for key, title, _ in self.gains_columns:
            self.gains.heading(key, text=t(title))
        self.render()

    def refresh(self, points, names, session, completed=None):
        self.points, self.names = points, names
        self.session_button.configure(text=t('history.session_end') if session else t('history.session_start'))
        self.session_note = None
        self.session_span = None
        if session:
            self.session_note = t('history.session_open', time=self.local_time(session['time']))
            if points and points[-1]['id'] != session['id']:
                self.session_span = (session, points[-1], 'gains.title_open')
        elif completed:
            start, end = completed
            if start:
                self.session_span = (start, end, 'gains.title_done')
            if start:
                initial, final = start['amount'], end['amount']
                fixed = fixed_value(end, start['prices'])
                if all(v is not None for v in (initial, final, fixed)):
                    self.session_note = t('history.session_delta', historical=final-initial, fixed=fixed-initial)
        self.render()

    @staticmethod
    def local_time(stamp):
        """A stored UTC stamp (ISO text or datetime) in local time."""
        moment = datetime.fromisoformat(stamp) if isinstance(stamp, str) else stamp
        return moment.astimezone().strftime('%d/%m/%Y %H:%M:%S')

    def values(self):
        if not self.points:
            return []
        if self.historical():
            return [p['amount'] for p in self.points]
        return [fixed_value(p, self.points[0]['prices']) for p in self.points]

    def render(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for point, value in reversed(list(zip(self.points, self.values()))):
            prices = None if self.historical() else self.points[0]['prices']
            self.tree.insert('', 'end', iid=str(point['id']), values=(self.local_time(point['time']),
                             t('event.'+point['reason']), '—' if value is None else f'≈ {value:,.2f}',
                             quality(point, prices)))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self.summary.set(t('history.summary', count=len(self.points)) if self.points
                         else t('history.empty_hint'))
        if self.session_note:
            self.summary.set(self.session_note)
        self.details.set(t('history.select_hint'))
        self.render_gains()
        self.draw()

    def render_gains(self):
        """The session's gains, shown only while there is a session to compare."""
        self.gains.delete(*self.gains.get_children())
        if self.session_span is None:
            self.gains_box.pack_forget()
            return
        start, end, title = self.session_span
        changes = item_changes(start, end)
        known = [value for *_, value in changes if value is not None]
        self.gains_title.set(t(title, start=self.local_time(start['time']), end=self.local_time(end['time']),
                               total=sum(known), count=len(changes)))
        for item, before, after, change, value in changes:
            self.gains.insert('', 'end', values=(
                self.item_name(item), f'{before:,}', f'{after:,}', f'{change:+,}',
                '—' if value is None else f'{value:+,.2f} div'), tags=('gain' if change > 0 else 'loss',))
        if not changes:
            self.gains.insert('', 'end', values=(t('gains.none'), '', '', '', ''))
        if not self.gains_box.winfo_manager():
            self.gains_box.pack(fill='x', before=self.details_label)

    def draw(self):
        self.line.show([datetime.fromisoformat(p['time']) for p in self.points], self.values(), 'div')

    def choose(self, identity):
        self.tree.selection_set(str(identity))
        self.tree.see(str(identity))

    def select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        point = next(p for p in self.points if str(p['id'])==selected[0])
        price_date = (datetime.fromtimestamp(point['fetched']).strftime('%d/%m/%Y %H:%M')
                      if point['fetched'] else t('history.prices_unavailable'))
        parts = [t('history.detail_header', date=price_date, rate=point['rate'], primary=point['primary'])]
        for tab, data in point['tabs'].items():
            amount = '—' if data['amount'] is None else f'≈ {data["amount"]:.2f} div'
            observed = self.local_time(data['observed']) if data['observed'] else t('history.never_read')
            parts.append(t('history.detail_tab', name=self.names.get(tab,tab), amount=amount, observed=observed))
        self.details.set('\n'.join(parts))

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='exile-worth-valuations.csv')
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            writer.writerow(['date_utc','event','historical_value_div','displayed_value_div','mode','state','prices_timestamp'])
            for point,value in zip(self.points,self.values()):
                prices = None if self.historical() else self.points[0]['prices']
                writer.writerow([point['time'],point['reason'],point['amount'],value,
                                 self.mode_key,quality(point, prices),point['fetched']])
