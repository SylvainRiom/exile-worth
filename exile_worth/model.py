from __future__ import annotations

import os
import sys
import json
import math
import shutil
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# A packaged build lives next to its executable, which an update replaces.
ROOT = (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
        else Path(__file__).resolve().parent.parent)
LEGACY_DATA = ROOT / 'data'


def data_directory(environ=os.environ, legacy=LEGACY_DATA):
    """User data lives outside the program folder, so installing or updating
    never touches it. `EXILE_DATA_DIR` overrides; off Windows, the old place."""
    if environ.get('EXILE_DATA_DIR'):
        return Path(environ['EXILE_DATA_DIR'])
    if environ.get('LOCALAPPDATA'):
        return Path(environ['LOCALAPPDATA']) / 'ExileWorth'
    return legacy


DATA = data_directory()


# What makes a data folder the user's, as opposed to caches and a log.
# Moved last, the inventory very last: its presence means the move finished.
USER_FILES = ('settings.json', 'profiles.json', 'inventory.sqlite3')


def migrate_legacy_data(target=DATA, legacy=LEGACY_DATA):
    """Copy the pre-install `data/` folder once into the new location.

    Copy, never move: the old folder stays as a backup. Runs only while the
    target holds none of `USER_FILES`, so it never overwrites or merges an
    inventory; a log or cache written there first does not block it.
    The copy lands in a sibling first, then each entry is renamed into place,
    so an interrupted copy leaves nothing that would block the next attempt.
    """
    target, legacy = Path(target), Path(legacy)
    if target.resolve() == legacy.resolve() or not legacy.is_dir():
        return False
    if not any((legacy / name).exists() for name in USER_FILES):
        return False
    if any((target / name).exists() for name in USER_FILES):
        return False
    staging = target.with_name(target.name + '.migrating')
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(legacy, staging)
    target.mkdir(parents=True, exist_ok=True)
    order = {name: rank for rank, name in enumerate(USER_FILES, 1)}
    for entry in sorted(staging.iterdir(), key=lambda entry: order.get(entry.name, 0)):
        destination = target / entry.name
        if destination.is_dir():
            shutil.rmtree(destination)
        elif destination.exists():
            destination.unlink()
        entry.rename(destination)
    staging.rmdir()
    try:
        (legacy / 'MOVED.txt').write_text(
            f'Exile Worth now keeps its data in {target}\n'
            'This folder is the copy made before the move; it is no longer read.\n',
            encoding='utf-8')
    except OSError:
        pass
    return True


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Reason:
    """Stable keys for `Reading.reason`.

    These drive logic (an empty cell clears its stock, a pending one does not),
    so they must stay independent of the display language. `i18n.t('reason.…')`
    turns them into text.
    """
    AUTO = 'auto'
    EMPTY = 'empty'
    EMPTY_CONFIRMED = 'empty_confirmed'
    PENDING = 'pending'
    LOCAL_REF = 'local_ref'
    UNREADABLE_COUNT = 'unreadable_count'
    VARIANT = 'variant'
    UNKNOWN_ICON = 'unknown_icon'
    HIDDEN_ICON = 'hidden_icon'
    MANUAL = 'manual'
    LAST_KNOWN = 'last_known'
    TO_CHECK = 'to_check'


class Event:
    """Stable keys for `valuations.reason`. These are written to SQLite."""
    REFRESH = 'refresh'
    SESSION_START = 'session_start'
    SESSION_END = 'session_end'


# Rows written before the language-independent keys existed. The migration is
# one-way and idempotent; it never touches quantities, UUIDs or price bases.
LEGACY_EVENTS = {
    'Actualisation': Event.REFRESH,
    'Début de session': Event.SESSION_START,
    'Fin de session': Event.SESSION_END,
}


@dataclass
class Reading:
    slot: str
    item: str | None
    quantity: int | None
    confidence: float = 0
    reason: str = ''
    approximate: bool = False
    alternatives: tuple[str, ...] = ()


class Store:
    def __init__(self, path=DATA / 'inventory.sqlite3'):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS slots (
              league TEXT, tab TEXT, slot TEXT, item TEXT, quantity INTEGER,
              confirmed TEXT, uncertain INTEGER, PRIMARY KEY(league, tab, slot));
            CREATE TABLE IF NOT EXISTS history (
              id INTEGER PRIMARY KEY, time TEXT, league TEXT, tab TEXT, snapshot TEXT);
            CREATE TABLE IF NOT EXISTS price_history (
              league TEXT, fetched REAL, primary_currency TEXT, prices TEXT,
              PRIMARY KEY(league, fetched));
            CREATE TABLE IF NOT EXISTS valuations (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, league TEXT NOT NULL,
              signature TEXT NOT NULL, reason TEXT NOT NULL, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS valuations_league ON valuations(league, id);
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(slots)')}
        if 'approximate' not in columns:
            self.db.execute('ALTER TABLE slots ADD COLUMN approximate INTEGER NOT NULL DEFAULT 0')
            self.db.commit()
        if 'empty' not in columns:
            # Before this column a confirmed-empty cell was deleted, which made it
            # indistinguishable from a cell that was never read. Rows deleted then
            # cannot be recovered; they are re-learned on the next scan.
            self.db.execute('ALTER TABLE slots ADD COLUMN empty INTEGER NOT NULL DEFAULT 0')
            self.db.commit()
        self.migrate_event_keys()

    def migrate_event_keys(self):
        """Rewrite French event labels as language-independent keys.

        Only the `reason` column changes: valuation signatures are computed
        without it, so existing points keep their identity and their prices.
        """
        with self.db:
            for legacy, key in LEGACY_EVENTS.items():
                self.db.execute('UPDATE valuations SET reason=? WHERE reason=?', (key, legacy))

    def sync(self, league, tab, readings):
        """Update by slot; unreadable slots retain their last known quantity."""
        changed = False
        stamp = now()
        with self.db:
            for r in readings:
                old = self.db.execute(
                    'SELECT item, quantity, approximate, empty FROM slots WHERE league=? AND tab=? AND slot=?',
                    (league, tab, r.slot)).fetchone()
                if r.reason == Reason.EMPTY:
                    # Confirmed empty is knowledge, not absence of knowledge: keep
                    # the row so the cell stops counting as never read. It holds no
                    # item and no quantity, so it is still never a stored zero.
                    if old is None or not old[3]:
                        changed = True
                    self.db.execute(
                        'INSERT OR REPLACE INTO slots(league,tab,slot,item,quantity,confirmed,uncertain,approximate,empty)'
                        ' VALUES(?,?,?,NULL,NULL,?,0,0,1)', (league, tab, r.slot, stamp))
                    continue
                if r.reason == Reason.PENDING:
                    # A re-confirmation in progress is not a failed reading: the
                    # stored row is still the last confirmed state. Flagging it
                    # would mark every re-read cell "to check" for a second, and
                    # record that in the valuation history.
                    continue
                if r.quantity is None or r.item is None:
                    self.db.execute('UPDATE slots SET uncertain=1 WHERE league=? AND tab=? AND slot=?',
                                    (league, tab, r.slot))
                    continue
                if r.quantity < 0:
                    raise ValueError('Negative quantity')
                changed |= old != (r.item, r.quantity, int(r.approximate), 0)
                self.db.execute('INSERT OR REPLACE INTO slots(league,tab,slot,item,quantity,confirmed,uncertain,approximate,empty)'
                                ' VALUES(?,?,?,?,?,?,0,?,0)',
                                (league, tab, r.slot, r.item, r.quantity, stamp, int(r.approximate)))
            if changed:
                snapshot = self.db.execute('SELECT tab,slot,item,quantity,confirmed,uncertain,approximate'
                                           ' FROM slots WHERE league=? AND empty=0', (league,)).fetchall()
                self.db.execute('INSERT INTO history(time,league,tab,snapshot) VALUES(?,?,?,?)',
                                (stamp, league, tab, json.dumps(snapshot)))
        return changed

    def rows(self, league):
        """Cells holding stock. Six fields, as every caller and snapshot expects.

        Confirmed-empty cells are deliberately excluded: they carry no item and
        no quantity, so including them would turn every consumer into an unread
        cell. `empty_slots()` exposes them, the way `approximate_slots()` does.
        """
        return self.db.execute(
            'SELECT tab,slot,item,quantity,confirmed,uncertain FROM slots'
            ' WHERE league=? AND empty=0 ORDER BY tab,slot', (league,)).fetchall()

    def empty_slots(self, league):
        """Cells confirmed empty: read, and known to hold nothing."""
        return {(tab,slot) for tab,slot in self.db.execute(
            'SELECT tab,slot FROM slots WHERE league=? AND empty=1', (league,))}

    def history(self, league):
        return self.db.execute('SELECT time,tab,snapshot FROM history WHERE league=? ORDER BY id DESC LIMIT 100',
                               (league,)).fetchall()

    def approximate_slots(self, league):
        return {(tab,slot) for tab,slot in self.db.execute(
            'SELECT tab,slot FROM slots WHERE league=? AND approximate=1 AND empty=0', (league,))}

    def save_prices(self, league, market):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO price_history VALUES(?,?,?,?)',
                            (league, market['fetched'], market['primary'], json.dumps(market['prices'])))

    def close(self):
        self.db.close()

    def record_valuation(self, league, market, expected=None, reason=Event.REFRESH, force=False):
        """Freeze inventory and its price basis; never reprice an existing point."""
        rows = self.rows(league)
        if not rows:
            return None
        approximate = self.approximate_slots(league)
        empty = self.empty_slots(league)
        snapshot = [list(row) + [int((row[0], row[1]) in approximate)] for row in rows]
        prices = dict(market.get('prices', {}))
        tabs = {}
        expected = expected or {}
        for tab in sorted(set(expected) | {row[0] for row in rows}):
            entries = [row for row in snapshot if row[0] == tab]
            estimate = estimate_readings([Reading(r[1], r[2], r[3]) for r in entries], prices)
            tabs[tab] = dict(amount=estimate.amount, unpriced=estimate.unpriced,
                             unread=max(0, expected.get(tab, len(entries))-len(entries)
                                        -sum(1 for t,_s in empty if t == tab)),
                             uncertain=sum(bool(r[5]) for r in entries),
                             approximate=sum(bool(r[6]) for r in entries),
                             observed=max((r[4] for r in entries), default=None))
        estimate = estimate_readings([Reading(r[1], r[2], r[3]) for r in snapshot], prices)
        data = dict(rows=snapshot, prices=prices, primary=market.get('primary'),
                    fetched=market.get('fetched'), stale=market.get('stale', False),
                    rate=prices.get('divine'), amount=estimate.amount, tabs=tabs)
        # Observation timestamps alone must not produce hundreds of identical points.
        basis = dict(data, rows=[r[:4]+r[5:] for r in snapshot],
                     tabs={k: {a:b for a,b in v.items() if a != 'observed'} for k,v in tabs.items()})
        signature = hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()
        old = self.db.execute('SELECT signature FROM valuations WHERE league=? ORDER BY id DESC LIMIT 1', (league,)).fetchone()
        if not force and old and old[0] == signature:
            return None
        with self.db:
            cursor = self.db.execute('INSERT INTO valuations(time,league,signature,reason,data) VALUES(?,?,?,?,?)',
                                     (now(), league, signature, reason, json.dumps(data)))
        return cursor.lastrowid

    def valuations(self, league, limit=500):
        rows = self.db.execute('SELECT id,time,reason,data FROM valuations WHERE league=? ORDER BY id DESC LIMIT ?',
                               (league, limit)).fetchall()
        return [dict(id=i, time=stamp, reason=reason, **json.loads(data)) for i,stamp,reason,data in reversed(rows)]

    def active_session(self, league):
        row = self.db.execute("SELECT id,time,reason,data FROM valuations WHERE league=? AND reason IN (?,?) ORDER BY id DESC LIMIT 1", (league, Event.SESSION_START, Event.SESSION_END)).fetchone()
        if row and row[2] == Event.SESSION_START:
            return dict(id=row[0], time=row[1], reason=row[2], **json.loads(row[3]))
        return None

    def last_completed_session(self, league):
        rows = self.db.execute("SELECT id,time,reason,data FROM valuations WHERE league=? AND reason IN (?,?) ORDER BY id DESC LIMIT 2", (league, Event.SESSION_START, Event.SESSION_END)).fetchall()
        if len(rows) == 2 and rows[0][2] == Event.SESSION_END and rows[1][2] == Event.SESSION_START:
            return [dict(id=i, time=stamp, reason=reason, **json.loads(data)) for i,stamp,reason,data in reversed(rows)]
        return None


def line_value(item, quantity, prices, unit='divine'):
    """Price and reference rate must belong to the same league and overview."""
    rate = prices.get(unit)
    if not item or quantity is None or quantity < 0:
        return None
    if rate is None or not math.isfinite(rate) or rate <= 0:
        return None
    if quantity == 0:
        return 0.0
    price = prices.get(item)
    if price is None or not math.isfinite(price) or price < 0:
        return None
    return quantity * price / rate


@dataclass(frozen=True)
class Estimate:
    amount: float | None
    valued: int
    unread: int
    unpriced: int


def estimate_readings(readings, prices, unit='divine'):
    total, valued, unread, unpriced = 0.0, 0, 0, 0
    for reading in readings:
        if reading.reason == Reason.EMPTY and reading.item is None and reading.quantity is None:
            continue
        if not reading.item or reading.quantity is None:
            unread += 1
            continue
        value = line_value(reading.item, reading.quantity, prices, unit)
        if value is None:
            unpriced += 1
        else:
            total += value
            valued += 1
    return Estimate(total if valued else None, valued, unread, unpriced)
