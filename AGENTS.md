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
- **Presentation chosen explicitly: a dashboard with one card per tab**, not a
  side list. Global total on top, detail reachable by clicking.
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

# Interface test in a hidden window with temporary data
.\.venv311\Scripts\python.exe -m tests.smoke_ui

# Headroom of every recognition decision (see "Before touching a threshold")
.\.venv311\Scripts\python.exe -m tests.margins
```

Tested dependencies are pinned in `requirements-lock.txt`; `requirements.txt`
holds the version ranges.

## Code layout

| File | Responsibility |
| --- | --- |
| `exile_worth/app.py` | Interface, dashboard, cards, preview/detail, workers and capture loop |
| `exile_worth/capture.py` | Capture of the foreground game client area, DPI handling |
| `exile_worth/layouts.py` | Stash geometry, edge maps, alignment, expected cell counts |
| `exile_worth/vision.py` | Saved profiles, tab identification, structure choice, OCR, consensus |
| `exile_worth/icons.py` | CDN image cache, icon comparison across sizes/offsets |
| `exile_worth/pricing.py` | Leagues, Currency/Expedition catalogues, price merge and cache |
| `exile_worth/model.py` | Readings, SQLite, history, valuation computations, stable keys |
| `exile_worth/i18n.py` | Language selection and the English/French catalogues |
| `exile_worth/diagnostics.py` | Session log: decision verdicts, near-misses, tracebacks |
| `tests/margins.py` | Headroom of every recognition decision, against a baseline |
| `tests/` | Storage, OCR, recognition, valuation, simulated capture and interface |

## Rules to preserve

These are the ones that have been broken before. Each has an entry in the journal.

**Recognition**

- An unknown reading is **not zero**: keep the last state and flag it.
- An unknown icon, an unreadable quantity or a missing price must never produce an
  invented price. Show that the estimate is partial.
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
The choice is persisted in `data/settings.json`. Both catalogues must keep the
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
No screenshot or inventory ever leaves the machine.

## Current behaviour

### Capture and synchronisation

- Import a screenshot, or capture the game after a five-second delay.
- Automatic analysis after import. Estimation is possible without a registered tab.
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
  title readable. A unique active label in the same league with the same structure
  keeps its UUID even when its position changes.

### Recognition

- Currencies: 37 fixed cells (`L…`, `C…`). The central weapon slot and the free
  bottom grid are excluded. Expedition: 32 areas `E…`. Runes: one profile over five
  view geometries with separate cell namespaces, so a hidden view keeps its stock.
- `Scanner.detect_layout` compares cell borders first, then icons.
  `App.resolve_layout` uses the manual choice, then the recognised saved profile,
  then automatic detection.
- The matcher uses the reference PNGs, their transparency, several sizes and
  offsets. The counter area is masked when identifying the icon.
- Five families share one asset across normal/Greater/Perfect: Transmutation,
  Augmentation, Regal, Exalted, Chaos. The family is recognised visually, the tier
  from its column. This is not OCR of the II/III marks.
- Quantity OCR is independent of item identification. `K`/`M` and a decimal comma
  are supported: `24.7K` becomes **about 24,700**, with `approximate=True`. Never
  present those as exact.
- `LEGACY_EXPEDITION_SLOTS` preserves the identification coordinates of profiles
  registered before the 14 px correction. Do not remove that compatibility, and do
  not rewrite existing inventories to fix a geometry.

### Dashboard and value

- `My stash`: total and one card per registered tab; a separate preview card
  represents the current screenshot and is not added to the saved total.
- `Detail & reading`: screenshot, cells, items, quantities, per-line value,
  corrections, inventory and history.
- Per-tab screenshots are kept **in memory** (`tab_frames`), not persisted.
- Conversion: sum of `quantity × primaryValue`, divided by the rate of the selected
  currency. Never assume the primary currency is always divine.

## Prices and local data

Reference documentation: https://poe.ninja/docs/api

- Leagues: `/poe2/api/economy/leagues`. Prices:
  `/poe2/api/economy/exchange/current/overview?league=…&type=Currency`, and the
  same path with `type=Expedition`, `Runes`, `SoulCores`, `Idols`.
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
- `exile_worth/item_catalog.json` keeps 45 Expedition visual references verified on
  PoE2DB — names, IDs, image URLs, source, **no price**. It stays usable when the
  price endpoints fail. `tools/update_item_catalog.py` regenerates it.
- For distribution to several users, plan for the caching backend recommended by
  poe.ninja; `EXILE_PRICE_BASE` and `EXILE_CONTACT` exist for that.

The `data/` directory is ignored by Git and holds user data: `profiles.json`
(tabs, label and structure signatures, local corrections), `inventory.sqlite3`
(quantities, history, valuations), `settings.json` (language), `session.log`,
and the `prices/` and `icons/` network caches.

## Diagnosing a failure

Two tools exist because a screenshot alone never explained a refusal.

**`data/session.log`** (rotating, local). `INFO` records lifecycle events and
every *decision change* — the live loop runs three times a second, so an
unchanged verdict is suppressed and a line means something really changed. It
carries the numbers behind each verdict, the near-miss on every refused cell
(`best=… score=… margin=…`), and full tracebacks. `EXILE_LOG_LEVEL=DEBUG` adds
per-frame metrics and per-cell detail. After a failure report, read it together
with the PNG from **Save the image**: the PNG shows what was seen, the log says
why it was refused.

**`python -m tests.margins`** reports the headroom of every recognition decision
against its threshold, recorded in `tests/margin_baseline.json`.
`tests/test_margins.py` fails on shrinking headroom, a **relaxed threshold** or a
changed count. It covers the Expedition stash, the Runes stash, and the `$$` tab
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

- **Runes separates from Kalguuran by 0.03** (0.15 measured against a required
  0.12) — the smallest structural headroom in the project, and the reason the
  separation threshold must not be lowered again. It also blocks two
  optimisations: a cross-frame layout cache and a confirm-only detection shortcut,
  both of which could keep a stale page after a view change.
- **The sidebar arrow clears its floor by 2** (`dollar_tab.arrow_rows`, 4 measured
  against a required 2). It is the narrowest absolute margin outside the Runes
  separation, and it decides whether the side menu can confirm the active tab.
- **Four of the five Runes geometries rest on chat screenshots**, not on real
  captures. Only the first view is validated. Do not tune them on synthetic grids.
- **One resolution is validated**: 1920×1080. Other resolutions and interface
  scales are unverified, and a non-16:9 capture is refused outright.
- **Renamed or moved tabs**: re-association is handled for a unique label with the
  same structure, but a rename is still unvalidated. Duplicate labels stay
  ambiguous and are never merged.
- Rows deleted by the pre-`empty` behaviour are not recoverable; those cells are
  re-learned on the next scan.

## Resumption points

1. Capture the four unvalidated Runes views with **Save the image**, then verify
   their coordinates and selection indicator against real files.
2. Decide the Runes/Kalguuran separation: accept 0.03 knowingly, or find a more
   robust discriminant.
3. Check the OCR truncation risk: when the K/M suffix is not recognised on the full
   image, the glyph crop must not accept part of the number.
4. In time: other resolutions and scales, other stash types, persisting
   `tab_frames`.

The user may launch the application while work is in progress. Avoid leaving calls
to missing methods between two changes; verify the whole path before announcing a
version that is ready to restart.
