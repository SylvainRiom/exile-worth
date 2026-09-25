# Exile Worth — project memory

What is true of the code now, and the rules that must survive the next change.
Everything is written in the present tense: if a statement here is no longer
true, fix it rather than adding a note beside it.

The dated record of how each decision was reached lives in
[`docs/journal.md`](docs/journal.md). When a rule below looks arbitrary, its
entry there says which measured failure produced it.

## Goal and user preferences

- Windows application that watches **Path of Exile 2** stash tabs and estimates
  their overall value in **divines**, with poe.ninja prices and quantity history.
- Near-continuous reading while the stash is visible: tab changes, but also
  additions and removals within the same tab.
- Keep the scope to items that are visually identifiable and quantifiable.
  Do not estimate gear from its icon alone.
- Recognise the **type** of a tab from its structure, independently of its name.
  The name is customisable and distinguishes individual inventories.
- Automatic recognition of icons and of the white numbers in the top-left corner.
  The user refused a mandatory cell-by-cell calibration: manual corrections must
  remain a fallback.
- **Presentation chosen explicitly (23 September 2026): the stash list on the
  left, the chosen entry on the right**, with `Whole stash` first: its total
  and every item, a small value chart, and each tab's own value and cells one
  click away. No separate detail page. This replaced the earlier choice of one
  card per tab with a detail page, which the user found redundant.
- **The project is English-first** (code, docs, commits, interface). The interface
  ships English and French; the language is selected in the toolbar.
- **Commits carry no AI attribution.** No `Co-Authored-By` trailer, no generated-by
  line, in commit messages or pull request descriptions.
- Give explicit visual feedback on tracking states; never leave a button looking
  inactive without an explanation.

## Environment and commands

Python **3.11**, environment `.venv311`, Tkinter interface, OpenCV/NumPy, MSS
capture, `rapidocr-onnxruntime` OCR, SQLite storage. Python 3.14 was tried early
on, but the RapidOCR version in use does not support it. `.venv` is a leftover;
use `.venv311`.

```powershell
# Normal start, dependencies already installed
.\.venv311\Scripts\python.exe -m exile_worth

# Install the pinned versions, then start
.\run.ps1

# Unit tests and OCR integration
.\.venv311\Scripts\python.exe -m unittest discover -s tests -v

# Interface test in a hidden window with temporary data and default settings
.\.venv311\Scripts\python.exe -m tests.smoke_ui

# Headroom of every recognition decision (see "Before touching a threshold")
.\.venv311\Scripts\python.exe -m tests.margins

# Installer: tests, PyInstaller build, packaged self-test, Inno Setup
.\packaging\build.ps1            # -SkipTests to skip the unit tests
```

Building the installer needs Inno Setup 6 (`winget install JRSoftware.InnoSetup`)
and the build tools pinned in `requirements-build.txt`, which `build.ps1` installs.

Tested dependencies are pinned in `requirements-lock.txt`; `requirements.txt`
holds the version ranges.

## Code layout

| File | Responsibility |
| --- | --- |
| `exile_worth/app.py` | Interface, stash list and contents, chart, corrections, workers and capture loop |
| `exile_worth/capture.py` | Capture of the foreground game client area, DPI handling |
| `exile_worth/layouts.py` | Stash geometry, edge maps, alignment, expected cell counts |
| `exile_worth/vision.py` | Saved profiles, tab identification, structure choice, OCR, consensus |
| `exile_worth/icons.py` | CDN image cache, icon comparison across sizes/offsets |
| `exile_worth/pricing.py` | Leagues, Currency/Expedition catalogues, price merge and cache |
| `exile_worth/model.py` | Readings, SQLite, history, valuation computations, stable keys |
| `exile_worth/history_ui.py` | History page, and `LineChart` shared with the stash chart |
| `exile_worth/i18n.py` | Language selection and the English/French catalogues |
| `exile_worth/diagnostics.py` | Session log: decision verdicts, near-misses, tracebacks |
| `exile_worth/tables.py` | Sort order of displayed table cells |
| `exile_worth/settings.py` | `settings.json`: small preferences merged key by key |
| `exile_worth/updater.py` | Release check on GitHub, verified download, installer launch |
| `exile_worth/report.py` | "Report a problem": a local zip of the log, stash crops and context |
| `exile_worth/selftest.py` | `--self-test`: a packaged build loads its OCR, data files and Tk |
| `packaging/` | PyInstaller spec, Inno Setup script, `build.ps1` |
| `.github/workflows/release.yml` | A `v*` tag builds the installer and publishes the release |
| `exile_worth/assets/tab_icons/` | In-game stash tab icons per layout family, with `sources.json` |
| `tests/margins.py` | Headroom of every recognition decision, against a baseline |
| `tests/` | Storage, OCR, recognition, valuation, simulated capture and interface |

## Rules to preserve

These are the ones that have been broken before. Each has an entry in the journal.

**Recognition**

- An unknown reading is **not zero**: keep the last state and flag it.
- An unknown icon, an unreadable quantity or a missing price must never produce an
  invented price. Show that the estimate is partial.
- A `PENDING` reading (a re-confirmation in progress) leaves the stored row
  untouched. Only a failed reading — unreadable count, unknown or hidden icon —
  flags it `uncertain` ("to check"), which also counts in the valuation history.
- A cell **confirmed empty three times** clears its stock. It is then stored as read
  and holding nothing (`empty=1`, no item, no quantity), never as a zero.
- Each stash type has its own geometry, independently of the tab name. Expedition
  must never receive the Currencies coordinates.
- An uncertain detection must **not** reuse the last type: show "Unrecognised type",
  with no grid and no synchronisation. The manual choice re-runs the analysis and
  takes priority over an old profile; a different structure must not overwrite that
  old profile's inventory.
- Position resolves only a family already confirmed from its artwork (the five
  currency tiers, the four sagas). It can never name an empty cell.
- Do not confuse tests on synthetic images with validation on real screenshots.

**Data**

- Preserve existing inventories and UUIDs across changes. Migrations are additive.
- User data lives in `%LOCALAPPDATA%\ExileWorth` (`model.DATA`; `EXILE_DATA_DIR`
  overrides), never next to the code, which an installer or update replaces.
  `migrate_legacy_data` copies an old `data/` folder there once, at start-up,
  only while the target holds none of `USER_FILES`; it never merges into or
  overwrites an inventory, and the old folder stays as a backup. Nothing but
  `__main__` may create user files before it runs.
- `Store.rows()` keeps its six fields **and its meaning**: cells holding stock.
  Confirmed-empty cells are reached through `empty_slots()`, approximations through
  `approximate_slots()`. Putting either into `rows()` turns every consumer —
  valuation, CSV, inventory tree, history — into treating them as unread.
- Separate inventories and prices per league; never reuse a rate from another league.
- Do not add the preview to a tab that is already registered.
- The total is an **observed stock**, not automatically farming profit. A transfer
  between two tabs may be counted twice until both have been seen again.
- Never translate a stored key (`Reason`, `Event`); translate only its label.

**Catalogue** (user request of 20 September 2026, for all future stash tabs)

- Look up PoE 2 names and icons on poe.ninja and PoE2DB before leaving whole
  families as "Unrecognised item". The visual catalogue must be independent of the
  items priced in the league. A known name without a rate stays displayed, without
  an invented price. Do not solve this by imposing a cell-by-cell calibration.
  Keep verified references, their sources and their identifiers in the project.

**Threads**

- No access to Tk widgets from a secondary thread; everything crosses the
  `messages` queue and `drain`. Worker results travel as `ScanResult`, never as a
  tuple whose length the consumer probes.

## Architecture invariants

**Language.** `i18n.py` holds `LANGUAGES`, the `CATALOG` for `en` and `fr`, and
`t(key, **fields)`. A missing key falls back to English, then to the key itself.
The choice is persisted in `settings.json` in the data folder. Both catalogues must keep the
same key set and the same `{placeholders}`; a mismatch raises inside `.format()`
in one language only. `App.retranslate()` relabels in place.

**Stable keys.** Translation keys are ASCII identifiers, and some are stored
values. `Reading.reason` drives logic (`Reason.EMPTY` clears a stock,
`Reason.PENDING` does not) and `valuations.reason` is written to SQLite. `Reason`
and `Event` in `model.py` are the single source of truth. Three display strings
used to double as control values and must not go back: the layout selector stores
a **layout id** (`layout_override`, `None` meaning automatic), the history view
stores `mode_key`, and events are `Event.*`.

**Geometry.** `layouts.edge_maps(frame)` builds the gradient maps once over
`REGION = (800, 700)`, which contains every stash grid with room for the ±20 px
alignment search. `Scanner.aligned()` memoises the fit per frame and per layout,
keyed on the **frame object** compared with `is` — never `id()`, which is reused
after collection. `expected_slot_count(tab)` is the single answer to how many
cells a tab covers; a Runes tab spans all five views.

**Caches.** Any cache keyed on an object identity holds the object, or uses an
explicit revision counter (`IconMatcher.revision`). `id()` is never a cache key.

**Network.** Icon downloads are pinned to `ICON_HOSTS` with
`urlparse().hostname`, which also rejects `https://web.poecdn.com@elsewhere/`.
Updates are pinned the same way to `UPDATE_HOSTS`, **including every redirect**
(`PinnedRedirects`): a GitHub download link redirects to its asset storage.
No screenshot or inventory ever leaves the machine by itself: a problem report
is a local zip the player sends, never an upload.

**Releases.** `exile_worth.__version__` is the only version number: the tag
(`v` + it, checked by the workflow), the executable's file version and the
update check all read it. The installer's `AppId` in `packaging/installer.iss`
must never change, or an update installs a second copy beside the first.
An installer is run only after its SHA-256 matches the `.sha256` published
beside it; a release lacking either asset is not offered.

## Current behaviour

### Installation and updates

- `ExileWorth-Setup-<version>.exe` installs per user in
  `%LOCALAPPDATA%\Programs\ExileWorth`, with no administrator rights. It is a
  PyInstaller one-folder build (about 225 MB installed, 70 MB to download);
  one-file was avoided because it unpacks on every start. The installer
  replaces `_internal` whole, so no stale library survives an update, and
  uninstalling leaves the user data.
- The application icon (`assets/app.ico`, 16–256 px) is original artwork drawn by
  `tools/make_app_icon.py`: a golden orb in one cell of a 2×2 stash grid, in the
  dashboard's colours; below 32 px the orb alone. It is **not** the game's
  Divine Orb, which is GGG's artwork and would ship in a public executable.
  The exe, the installer, the window (`iconbitmap(default=…)`) and the taskbar
  use it; `set_app_id` gives the window its own taskbar entry from source too.
- The build is unsigned: Windows SmartScreen warns on the first install. The
  updater's own download carries no web mark, so updates do not warn.
- Only a packaged build checks (`updater.enabled`; `EXILE_UPDATE_CHECK=1` forces
  it from source, `0` turns it off). Five seconds after start, at most once a
  day, a worker asks `releases/latest`; a 404 (no release yet) means up to date.
  A failed automatic check is silent (logged); a manual one ("Check now") says so.
- A newer version shows a banner under the header: update and restart, what's
  new, later, skip this version. A skipped version is not offered again
  automatically, but "Check now" still shows it. The toolbar checkbox turns the
  daily check off (`update_auto` in `settings.json`).
- "Update" downloads to `updates/` in the data folder with its progress in the
  banner, verifies the hash, starts the installer detached with
  `/SILENT /CLOSEAPPLICATIONS /RELAUNCH=1 /LANG=…` and closes the app; the
  installer reuses the previous folder and `RELAUNCH` starts the new version.
  Any refusal (hash, size, redirect host, download, launch) leaves the banner
  with its reason and a Retry button; nothing is run.

### Capture and synchronisation

- Import a screenshot, or capture the game after a five-second delay.
- There is no manual "Analyse" button. The screenshot is re-read automatically
  after an import or capture, a layout choice, the arrival of the catalogue, and
  a correction. Estimation is possible without a registered tab.
- `Start` also works without a registered tab: live preview, without creating a
  persistent anonymous inventory.
- Capture only reads the foreground window whose title contains `Path of Exile`.
  It sends neither clicks nor keys to the game. Prefer borderless windowed mode;
  alt-tabbing away from the game suspends readings.
- Loop with a 0.33 s wait, image stabilisation, then OCR. Three matching readings
  per cell are required before synchronising. Consensus rests on
  `(item, quantity, approximate, empty)`, so an animation restarts a reading but
  does not destroy identical votes.
- A revisit **replaces** the quantities per cell, it does not add to them.
- A tab is registered automatically once its structure is known and its active
  title readable. "Known" means confirmed by the **borders, the view selector or
  the user** (`may_register`, from `Scanner.last_layout_basis`): the icon
  fallback may show a preview but never registers, since it once saved the
  user's Ritual tab as Runes from 5 matches against 3. A unique active label in the same league with the same structure
  keeps its UUID even when its position changes.
- **The tab bar scrolls**: a tab's position depends on where the player came
  from (Delirium, registered at x=181, was later selected at x=466).
  `Profiles.identify` therefore compares an auto-registered or view-family
  tab's stored label **where the selected tab is now** (`label_score`, ±4 px,
  width within 6 px), never at its registration position. Requiring that
  position left every tab but the pinned currency one synchronised once and
  then stuck in the preview, resting on OCR of its title alone. A manually
  drawn tab keeps its drawn rect.
- The selected tab is found at y=121, where lit tabs reach the bar's lower edge.
  Coloured tabs are all lit there, so `pick_selected_run` chooses the one whose
  colour matches the line under the bar (`TAB_COLOUR_MAX` 0.4: measured 0.13
  selected against 0.75 for the nearest other); reaching down into that line
  breaks a tie between two tabs of the same colour. Without a readable line, the
  rightmost lit tab is kept, as before.
- The side menu's row confirms the title. Its small tab icon may be read as a
  letter (`B BREACH`); `without_menu_icon` drops one leading character only when
  the rest is exactly the tab's title. A lit row (dark text on bright green)
  can defeat OCR: a second, `high_contrast` read may only **confirm** the tab's
  title, never replace it. OCR sometimes reads a word's start twice (`De` over
  `Delirium`); `read_tab_text` drops that overlapping echo.

### Recognition

- Currencies: 37 fixed cells (`L…`, `C…`). The central weapon slot and the free
  bottom grid are excluded. Expedition: 32 areas `E…`. Runes: one profile over five
  view geometries with separate cell namespaces, so a hidden view keeps its stock.
  For a tab of a view family, `resolve_layout` returns what the borders detect,
  even in another family: an unrecognised view stays unrecognised, and a profile
  saved with the wrong type is corrected by `Profiles.observe`, keeping its UUID,
  only while it holds no stock; with stock, a separate profile is created.
  Breach works the same way: its Catalysts view (`breach`, 29 cells `B…`: two
  small and one large at the top, then normal and refined catalysts on rows of 6
  and 7) is measured. Its Wombgifts view is **deliberately not supported** (user
  decision, 23 September 2026: tedious, little value): it shows as an
  unrecognised type and synchronises nothing. Do not add it as a to-do.
- Four single-view tabs measured on real captures: Abyss (21 cells `AB…`),
  Delirium (32 `DE…`), Essences (87 `ES…`) and Ritual (33 `RI…`, one wide).
- **Dedicated cells.** These tabs accept one item per cell. `SLOT_ITEMS` names it
  for Delirium and Essences (the game's order: each Essences row is one essence
  in Lesser/normal/Greater/Perfect columns; Delirium mirrors normal and Ancient
  emotions). When near-identical artwork leaves the matcher ambiguous
  (`IconMatch.contenders`, every item within the margin), the cell's own item
  is taken if it is among them; a clearly different match is **refused, never
  renamed**. `SLOT_FAMILIES` does the same with a set: the Abyss diamond holds
  Abyss bones only. Never restrict a whole tab to one poe.ninja category: the
  Abyss tab's bottom row holds abyssal omens, which poe.ninja files as Ritual.
- A stash type with several views is a **view family** (`VIEW_FAMILIES` in
  `layouts.py`). The first view's id is the family's id and the stored
  `layout_id` of its tabs; `has_views` replaces any check on a family name, and
  `expected_slot_count` sums every view of the family.
- `Scanner.detect_layout` compares cell borders first, then icons. On a frame
  whose best grid is a Runes view, the **view selector decides** instead: the
  button of the visible view carries an amber underline (y 176..182, 64 px pitch
  from x=175), measured by `selector_underlines`. `lit_rune_view` requires the
  lit button at 45 or more and 20 ahead of every other; hover lights less, and
  two lit buttons fall back to the borders. The selected grid must still score
  0.55, beat every non-Runes stash by 0.12, and not trail another Runes grid by
  0.12 — a selector contradicting a clearly better grid is refused.
  `App.resolve_layout` uses the manual choice, then the recognised saved profile,
  then automatic detection.
- The matcher uses the reference PNGs, their transparency, several sizes and
  offsets. The counter area is masked when identifying the icon.
- A **dark cell with no readable counter is empty**, even when an icon matches:
  sparse dark artwork (Carved Mischief) matches the ghosts that Breach draws in
  empty cells at 0.92 and above. On every real capture, filled cells have a
  95th-percentile brightness of 79 or more, empty ghosts 64 or less.
- A cell showing **no counter at all** (`Scanner.last_counter_seen`: none read
  and no white glyph found) is empty below `GHOST_P95_MAX` (78) and
  `GHOST_BRIGHT_MAX` (4.2 % bright pixels), which catches the brighter ghosts
  of dedicated tabs (`AB01`, `AB05`, `AB09`, `DE13`, `DE23`, Breach `B02`) that
  used to stay "to check" forever. Every filled cell shows a counter, even at
  1. Measured on the ground truth (`ghost.*` in the harness): ghosts 73 and
  3.7 % at most, filled cells 84 and 4.7 % at least. A counter found but
  unreadable never takes this path.
- The counter crop follows white glyphs whose top is within 10 px of the cell
  top. The `5` and `1` on catalysts start at 9 px, their pale top bar or serif
  falling under the white threshold; at 8 px they were never read.
- Counter glyphs are **pure white**: a component whose mean saturation exceeds
  `COUNTER_SATURATION_MAX` (6) is artwork. Digits measure 0.0–0.1, essence
  crystals and Ritual emblems 12.9 and more; without it essence counters read
  `444` for 44 and `27` for 2.
- A K/M or decimal mark counts as evidence only at `MARK_CONFIDENCE_MIN` (0.5) or
  above: `6M` at 0.38 on an omen was artwork, genuine marks read 0.70–0.80.
- A mark (or an approximate count) read on the **full strip** counts only when
  the strip's white pixels alone read a mark too. A real `38.3K` is white like
  its digits; Omen of Gambling's gold bag beside `37` read `37M` at 0.58.
- The counter strip is 18 px (`COUNTER_HEIGHT`), although glyphs reach row
  18–19: a taller strip reaches the artwork and broke seven counts on the real
  captures. A counter the strip **found but could not read** gets a second read
  at 20 px (`Scanner.read_counter`); that is what reads a `4` whose foot the
  short strip cuts (it read `1`). Never a retry for a cell with no counter.
- Five families share one asset across normal/Greater/Perfect: Transmutation,
  Augmentation, Regal, Exalted, Chaos. The family is recognised visually, the tier
  from its column. This is not OCR of the II/III marks.
- Quantity OCR is independent of item identification. `K`/`M` and a decimal comma
  are supported: `24.7K` becomes **about 24,700**, with `approximate=True`. Never
  present those as exact.
- A K/M suffix or a decimal mark seen by **any** of the three reads (full
  counter, raw crop, white crop), even below the 0.90 confidence bar, forbids an
  exact result: the cell is then unreadable rather than `247` for `24.7K`. A crop
  that reads the suffix itself keeps `approximate=True`.
- `LEGACY_EXPEDITION_SLOTS` preserves the identification coordinates of profiles
  registered before the 14 px correction. Do not remove that compatibility, and do
  not rewrite existing inventories to fix a geometry.

### Stash page and value

- `My stash` is one page: **the stash list on the left, the chosen entry's
  contents on the right**. There is no separate detail page. The list starts
  with `Whole stash`, selected at start-up and after a league change, then one
  line per registered tab, then the preview. Clicking a line shows it
  (`select_all`, `open_stash`); clicks run through `after_idle` because a
  click may rebuild the list and destroy the clicked widget.
- **Live refreshes never rebuild what did not change.** The live loop
  refreshes several times a second; rebuilding the list and the tables each
  time made them jump and scrolled the tables back to the top while no value
  changed. `refresh_cards` leaves an unchanged list alone, updates lines in
  place (`fill_card`) and rebuilds only when a line or an icon appears or goes.
  `fill_tree` does the same for the item and reading tables, row by row, so
  their scroll position and selection hold.
- `Whole stash` shows the total with what it misses, then **every item of the
  stash in one table** (`refresh_items`): one line per item across all tabs,
  with total quantity, unit price, value, share of the valued total and the
  tabs holding it, most valuable first. It reads the same source as the total
  (stored rows, or the preview readings when no tab is stored). An unpriced
  item stays listed with `—`, never a zero.
- A tab shows **only its own value and cells**: name, type, last read time or
  the live badge, its value and its share of the stash, then the reading table
  (quantity, unit price, value, share of the tab). Beside the table, a panel
  explains the selected line and holds the corrections, which appear once a
  line or a cell is chosen (`show_fix`). The screenshot with its cells is
  folded under that panel (`toggle_capture`) and drawn only while shown.
- While tracking synchronises a registered tab (`live_tab_id()`), **that tab's
  line is the live view**: green background, `● Live`, and its contents show
  the live readings including provisional ones. The selection never jumps to
  it by itself; the preview entry, if chosen, becomes the live tab
  (`shown_tab_id`). The preview line exists only for readings no tab holds —
  an unidentified tab or an imported screenshot, which is analysed but never
  synchronised — and it is never added to the saved total. With nothing read
  yet there is no preview line. A new screenshot selects the preview.
- A **small chart** between the header and the table draws the chosen entry's
  value over 24 h, 7 days (default) or the league, from the stored valuations
  (`refresh_chart`): the stash total, or the tab's `tabs[id].amount`. Each
  point keeps its own prices, converted to the selected currency with that
  point's rates, so the curve moves with the stock and with the market; the
  history page separates the two. The preview has no chart. `LineChart` in
  `history_ui.py` draws it and the history page's chart, with a readout under
  the pointer.
- List lines are compact: two lines (icon, name, value; then type, last read
  time in local time, what is missing). The mouse wheel scrolls the list
  wherever the pointer is over it (`wheel_cards`, bound on `all`).
- Scrollbars (list and tables) appear only when there is something to scroll
  (`auto_hide` as the `yscrollcommand`).
- The reading table has **no state column**. A normal line carries no mark; a
  line being confirmed (`PENDING`) is grey; one needing attention (unreadable
  count, unknown or hidden icon, uncertain tier, to check) is amber with a ⚠
  after its name. Selecting a line shows its explanation in the panel
  (`note.*` keys, player wording); the selection survives the live refreshes.
  `Reason` keys still drive the logic; only their display changed.
- On the live tab, a cell that is re-confirming (`Reason.PENDING`) or whose count
  is unreadable right now shows its **last confirmed** stored quantity and value,
  explained as such in its note, as long as the same item is recognised. A
  different provisional count shows beside it as `141 → 145 (provisional)`; the
  value stays that of the confirmed quantity until consensus.
- Corrections apply to the screenshot being read (the preview or the live tab),
  never to a stored tab; the panel says so on a stored tab.
- The item and reading tables sort on a heading click (again to reverse, arrow
  on the active column). Rows change on every live reading, so the order is
  a state `apply_sort` reapplies after each refresh, never a one-off move.
  Numbers sort by value (`≈ 24,700`, `12 (provisional)`), text in natural
  order (C2 before C10), and `—` stays last in both directions.
- **Cell ids (`L11`, `E22`, `R05`…) are never shown to the user**: they key the
  reading rows (`iid`) and the corrections, and stay in the CSV export. The
  correction panel names the selected item instead.
- The item and reading tables show the item artwork and name together in
  the tree column (`#0`, sortable like the others),
  from `icon_images` (the images `fetch_icons` returned with the last prices).
  An unknown item shows none; an unresolved family whose candidates share one
  image (Flux tiers) shows that image without naming a tier. Thumbnails are
  `PhotoImage`s built on the Tk thread and kept in `_thumbs`.
- Each tab line shows the in-game icon of its stash type before its title, keyed
  by layout family (the five Runes views share the Augment tab icon); the preview
  follows the detected layout and shows none when it is unrecognised. The
  icons are 27 px PNGs **shipped with the project**, verified on PoE2DB, not
  fetched at runtime: PoE2DB's CDN refuses requests without its own referer, and
  its host is not in `ICON_HOSTS`. A new stash family needs its icon added there;
  `tests/test_tab_icons.py` fails until it is.
- Per-tab screenshots are kept **in memory** (`tab_frames`), not persisted.
- A registered tab can be **removed** (`remove_tab`): the button under its
  title, or a right-click on its list line, after a confirmation. It drops the
  profile (`Profiles.remove`, which replaces the list since the live loop
  iterates it) and its cells (`Store.forget_tab`), and records a
  `TAB_REMOVED` valuation. History and past valuations stay; the name is kept
  under `removed` in `profiles.json` so they still name the tab. Nothing is
  sent to the game: seen again, the tab registers under a new UUID and is read
  from scratch. A scan in flight for a removed id is shown as a preview, never
  synchronised, or it would write rows back under a dead id.
- Conversion: sum of `quantity × primaryValue`, divided by the rate of the selected
  currency. Never assume the primary currency is always divine.

## Prices and local data

Reference documentation: https://poe.ninja/docs/api

- Leagues: `/poe2/api/economy/leagues`. Prices:
  `/poe2/api/economy/exchange/current/overview?league=…&type=Currency`, and the
  same path with `type=Expedition`, `Verisium`, `Breach`, `Abyss`, `Delirium`,
  `Essences`, `Ritual`, `Runes`, `SoulCores`, `Idols`.
  An Expedition tab needs two of them: `Expedition` holds the sagas, fluxes and
  logbooks, `Verisium` the alloys, crests, Verisium and Starlit Ores.
- Metadata: **top-level `items`** holds the full catalogue; `core.items` only the
  reference currencies. Rates: `lines[].primaryValue`; currency: `core.primary`.
- Relative image paths `/gen/image/…` resolve against **`https://web.poecdn.com`**,
  not poe.ninja (which returns 404).
- Responses are cached for an hour, revalidated with ETag, falling back to the
  cache on failure; refreshed hourly during tracking.
- `stash_market` merges the categories without overwriting the Currency reference
  rates, and converts when the primary currencies differ.
- A known item can be unpriced or ambiguous. Several Thaumaturgic Flux tiers share
  one image: do not invent their tier or price.
- `exile_worth/item_catalog.json` keeps 214 visual references verified on
  PoE2DB — Expedition, Breach, Abyss, Delirium, Essences, Ritual — names, IDs,
  image URLs, source, **no price**. PoE2DB lists fewer essences (56) than
  poe.ninja (76); recognition uses the market's full list. It stays
  usable when the price endpoints fail. `tools/update_item_catalog.py`
  regenerates it from the categories in its `SOURCES`; a reference the source
  stops listing is kept, so an item still in a stash stays identifiable.
- For distribution to several users, plan for the caching backend recommended by
  poe.ninja; `EXILE_PRICE_BASE` and `EXILE_CONTACT` exist for that.

User data lives in `%LOCALAPPDATA%\ExileWorth` in every mode, source or
packaged, so a later install finds the same inventory: `profiles.json` (tabs,
label and structure signatures, local corrections), `inventory.sqlite3`
(quantities, history, valuations), `settings.json` (language), `session.log`,
`diagnostics/` (saved images) and the `prices/` and `icons/` network caches.
`EXILE_DATA_DIR` points it elsewhere; off Windows it falls back to `data/`.
The repository's `data/` directory, ignored by Git, is the pre-move location:
it is copied once and then carries a `MOVED.txt`, and is no longer read.

## Expected state

Run these first; anything that does not match means something changed before you
arrived, not that the numbers below are stale.

```
python -m unittest discover -s tests   ->  218 tests, OK
python -m tests.smoke_ui               ->  OK, under a second
python -m tests.margins                ->  79 decisions, none FAILS, 14 TIGHT
```

The fourteen TIGHT decisions are expected: icon scores and icon margins of the
real captures (Expedition, Breach, Abyss, Delirium, Essences, Ritual), the
Runes border separation, and the two bright-pixel bounds of the ghost filter
(`ghost.bright_max`, `ghost.filled_bright_min`, half a point each side; see
"Known fragilities").
`tests/test_margins.py` already fails if any of them erodes, so a green suite
means the headroom is intact — you do not need to read the table to know that.

The TIGHT flag is calibrated for 0–1 scores (`headroom < .05`), so it does not
carry on counts. `dollar_tab.arrow_rows` is narrow — 4 against a required 2 —
without being flagged. Read the fragilities list, not just the flags; the
baseline test is the real guard either way.

## Diagnosing a failure

A player's problem starts with **Report a problem** (toolbar, `report.py`). It
asks what went wrong, then writes one zip where the player chooses and shows
it in Explorer; nothing is sent. It holds `report.json` (version, league,
tabs without their pixel signatures, removed tabs, the live and shown tabs,
the layout with the basis and verdict that chose it, the current readings,
confirmed-empty cells, the price basis, the player's note), `inventory.csv`
(the league's stored cells), `session.log` and its rotations, and
`stash-*.png`: the screenshot being read and the last one of every tab seen
this session, named after the tab and its id's first six characters. Images
are cropped to `STASH_AREA` (860×765), which holds everything the recogniser
reads and leaves out the chat and the character; the crops fit
`tests/fixtures` as they are.

Two tools exist because a screenshot alone never explained a refusal.

**`session.log`** in the data folder (rotating, local). `INFO` records lifecycle events and
every *decision change* — the live loop runs three times a second, so an
unchanged verdict is suppressed and a line means something really changed. It
carries the numbers behind each verdict, the near-miss on every refused cell
(`best=… score=… margin=…`), why a live reading stays in the preview
(`reading not attached to a tab`), the title `observe` read and how many tabs
it matched (`tab title:`), and full tracebacks. `EXILE_LOG_LEVEL=DEBUG` adds
per-frame metrics and per-cell detail. After a failure report, read it together
with the PNG from **Save the image**: the PNG shows what was seen, the log says
why it was refused.

**`python -m tests.margins`** reports the headroom of every recognition decision
against its threshold, recorded in `tests/margin_baseline.json`.
`tests/test_margins.py` fails on shrinking headroom, a **relaxed threshold** or a
changed count. It covers the Expedition stash, the five Runes views and their
selector, the Breach Catalysts view and its tab colour, Abyss, Delirium,
Essences and Ritual, and the `$$` tab
selection and label.

The two `dollar_tab.symbol_*` scores are near-tautological: the templates in
`reference_tabs/` were cut from that very capture, so ~1.0 means the matcher
still recognises its own source, not that `$$` is robust in general. They guard
against preprocessing changes, nothing more.

### Before touching a threshold

Run the harness, make the change, run it again, compare. Refresh the baseline
(`--update`) deliberately, never to turn a red test green. Lowering a threshold
*raises* measured headroom, so it hides itself; that is why thresholds are pinned
in the baseline and compared separately, and why that test must not be removed.

## Known fragilities

- **Runes separates from Kalguuran by 0.03 on borders alone** (0.15 measured
  against a required 0.12). The view selector now decides between Runes views
  with a lead of 40 against a required 20, so this headroom only matters when the
  selector is unlit or ambiguous (hover, two lit buttons). A 120 px overlay on
  the grid is enough to make the borders refuse the Runes view; the selector
  still names it. Do not lower the separation threshold: it remains the
  fallback. It also still blocks a cross-frame layout cache and a confirm-only
  detection shortcut, both of which could keep a stale page after a view change.
  On borders alone the risk runs **one way**: a Runes capture scores 0.850 on
  the Kalguuran grid, a Kalguuran capture only 0.586 on the Runes grid.
- **The sidebar arrow clears its floor by 2** (`dollar_tab.arrow_rows`, 4 measured
  against a required 2). It is the narrowest absolute margin outside the Runes
  border separation, and it decides whether the side menu can confirm the active tab.
- **The selector geometry is fixed.** Its position is measured at 1920×1080
  only, like the grids. Hover was reported by the user as a much less sharp
  underline but has not been captured; the lead requirement is what protects
  against it.
- **Breach is half validated.** One real capture of the Catalysts view, holding
  12 normal catalysts and splinters: refined catalysts are drawn differently
  (tilted glyph, grey base) but none was on the capture, so their recognition is
  unverified.
- **Icon margins are thin on the new tabs**: Delirium clears the 0.015 margin by
  0.0009 (DE04), Essences by 0.004, Ritual by 0.005, Abyss by 0.007. On
  dedicated cells a margin that fails falls back on the cell's item, so Delirium
  and Essences keep their answer; Ritual and Abyss have no such fallback.
- **Ritual emblems** sit over the first cell of some groups. The colour filter
  removes them from the counters; `RI25` is read through the 20 px retry.
- **The ghost filter's bright-pixel bound is narrow**: 4.2 % between ghosts at
  3.7 % (`B02`) and filled cells at 4.7 % (`AB10`). It applies only to a cell
  showing no counter, and the 95th-percentile bound (5 and 6 of headroom) must
  hold too. Several Runes ghosts sit at 2.3–2.7 %, but the Runes captures have
  no ground truth, so whether they now read as empty is unmeasured.
- **Essences against Currencies is unverified on a real Currency capture**: on
  the Essences capture the Currency grid scores 0.486 (0.51 behind), but no real
  Currency capture exists to measure the reverse.
- **One resolution is validated**: 1920×1080. Other resolutions and interface
  scales are unverified, and a non-16:9 capture is refused outright.
- **Renamed or moved tabs**: re-association is handled for a unique label with the
  same structure, but a rename is still unvalidated. Duplicate labels stay
  ambiguous and are never merged.
- Rows deleted by the pre-`empty` behaviour are not recoverable; those cells are
  re-learned on the next scan.

## Resumption points

1. Breach: a capture of the Catalysts view holding refined catalysts.
2. Ground truth for a Runes capture, to measure its ghosts against the ghost
   filter as the dedicated tabs were.
3. A real Currency capture, to measure Essences against Currencies both ways.
4. In time: other resolutions and scales, other stash types, persisting
   `tab_frames`.
5. Code signing (for example Azure Trusted Signing), to remove the SmartScreen
   warning on first install.

The user may launch the application while work is in progress. Avoid leaving calls
to missing methods between two changes; verify the whole path before announcing a
version that is ready to restart.
