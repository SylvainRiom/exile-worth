# Exile Worth — project memory

Handover memo. It describes the state of the code and the decisions taken in
conversation; it does not guarantee any accuracy measured in game.

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
  ships English and French; the language is selected in the toolbar and stored in
  `data/settings.json`. This replaces the earlier "interface and exchanges in
  French" preference, changed by the user on 22 September 2026.
- Give explicit visual feedback on tracking states; never leave a button looking
  inactive without an explanation.

## Environment and commands

Python **3.11**, environment `.venv311`, Tkinter interface, OpenCV/NumPy, MSS
capture, `rapidocr-onnxruntime` OCR, SQLite storage. Python 3.14 was tried early
on, but the RapidOCR version in use does not support it. `.venv` is a leftover;
use `.venv311`.

```powershell
# Normal start, dependencies already installed
.\.venv311\Scripts\python.exe -m joy_tracker

# Install the pinned versions, then start
.\run.ps1

# Unit tests and OCR integration
.\.venv311\Scripts\python.exe -m unittest discover -s tests -v

# Interface test in a hidden window with temporary data
.\.venv311\Scripts\python.exe -m tests.smoke_ui
```

Tested dependencies are pinned in `requirements-lock.txt`; `requirements.txt`
holds the version ranges.

## Code layout

| File | Responsibility |
| --- | --- |
| `joy_tracker/app.py` | Interface, dashboard, cards, preview/detail, workers and capture loop |
| `joy_tracker/capture.py` | Capture of the foreground game client area, DPI handling |
| `joy_tracker/layouts.py` | Geometry of the Currencies, Expedition and Runes profiles, normalised to 1920×1080 |
| `joy_tracker/vision.py` | Saved profiles, tab identification, structure choice, OCR, consensus |
| `joy_tracker/icons.py` | CDN image cache, icon comparison across sizes/offsets |
| `joy_tracker/pricing.py` | Leagues, Currency/Expedition catalogues, price merge and cache |
| `joy_tracker/model.py` | Readings, SQLite, history, valuation computations, stable keys |
| `joy_tracker/i18n.py` | Language selection and the English/French catalogues |
| `tests/` | Storage, OCR, recognition, valuation, simulated capture and interface |

## Language and stable keys — 22 September 2026

- The user asked for an English-first project, keeping French selectable in the
  application settings. English is the default and the source language.
- `joy_tracker/i18n.py` holds `LANGUAGES`, the `CATALOG` for `en` and `fr`, and
  `t(key, **fields)`. A missing key falls back to English, then to the key itself.
  The choice is persisted in `data/settings.json` and read at startup.
- **Translation keys are stable ASCII identifiers and some of them are stored
  values.** `Reading.reason` drives logic (`Reason.EMPTY` clears a stock,
  `Reason.PENDING` does not) and `valuations.reason` is written to SQLite.
  Never translate a key, only its label. `Reason` and `Event` in `model.py` are
  the single source of truth.
- `Store.migrate_event_keys` rewrites the old French labels
  (`Actualisation`, `Début de session`, `Fin de session`) as `refresh`,
  `session_start`, `session_end`. The migration is idempotent and touches only the
  `reason` column: valuation signatures are computed without it, so existing points
  keep their identity and their price basis. Verified on the user's database:
  10 rows migrated, 57 slots and 2 history entries untouched.
- Two other display strings used to double as control values and were removed as
  such: the layout selector now stores a **layout id** (`self.layout_override`,
  `None` meaning automatic) instead of its translated name, and the history view
  stores `mode_key` instead of the translated mode label. Reintroducing a
  comparison against displayed text would break as soon as the language changes.
- `App.retranslate()` relabels the interface in place: the `self._translatable`
  registry filled by `App.tr`, notebook tabs via `page_keys`, tree headings via
  `_trees`, the translated comboboxes, and `HistoryView.retranslate()`.
- Both catalogues must keep the same key set and the same `{placeholders}`;
  a mismatch raises at runtime inside `.format()`.

## Session log — 22 September 2026

- Problem addressed: layout scores, icon runners-up and scanner metrics were all
  computed on every frame and then discarded, and the five `except Exception`
  handlers kept only `str(exc)`. A failure report left nothing to read, which is
  why the diagnosis cycles recorded below were so long.
- `joy_tracker/diagnostics.py` configures a rotating `data/session.log`
  (2 MB × 4) and exposes `log`, `failure(context, exc)` and `ChangeGate`.
  A read-only data directory falls back to a `NullHandler`: logging must never
  prevent the application from starting.
- `INFO` records lifecycle events and every **decision change**; `DEBUG`
  (`JOY_LOG_LEVEL=DEBUG`) adds per-frame metrics and per-cell detail. The live
  loop runs three times a second, so `ChangeGate` suppresses an unchanged
  verdict. Keep it that way: an unconditional line per frame would bury the
  transition that matters.
- `Scanner.detect_layout` now keeps `last_layout_scores` and `last_layout_verdict`
  and states which threshold was missed (`score < .55` or `margin < .12`).
  `Profiles.identify` logs its ranked candidates and the reason for a refusal.
  `Scanner.record_coverage` logs each unidentified cell with the near-miss:
  this is the first real use of `IconMatch.candidate` and `.margin`.
- Verified against the real fixtures: Expedition gives
  `borders accepted expedition (score 1.000, margin 0.733)` then
  `25 identified, 7 empty, 0 unidentified`. Rune artwork against the Expedition
  catalogue gives scores of 0.90–0.93 against a 0.92 threshold with margins of
  0.0008–0.01 against a required 0.015 — enough to tell a threshold problem from
  a missing catalogue entry.
- `tests/test_diagnostics.py` pins the traceback, the numbers behind a verdict,
  the near-miss line, the DEBUG level of frame metrics, the absence of repeats
  and the unusable-directory fallback.
- The accepted-layout test also asserts the margin over the runner-up. That is a
  first step towards the margin harness that is still missing: the suite is still
  otherwise pass/fail and does not show how close a threshold came to failing.
- Last validation: **79 tests passed**, as well as `python -m tests.smoke_ui`.

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
  per cell are required before synchronising.
- Displayed states: paused, tracking, waiting for the game, image moving, live
  preview, stopping. The button becomes `Pause` while running.
- A revisit **replaces** the quantities per cell, it does not add to them.

### Recognition

- Currencies: 37 fixed cells; profiles `L…` and `C…`. The central weapon slot and
  the free grid at the bottom are excluded from the initial profile.
- Expedition: 32 areas `E…`, including two large central cells, measured on the
  user's second screenshot. The assumed source width was 1902×1080.
- `Scanner.detect_layout` compares cell borders first, then icons.
  `App.resolve_layout` uses the manual choice, then the recognised saved profile,
  then automatic detection. No fallback to the last type: an unknown structure
  shows no grid and synchronises no inventory.
- The matcher uses the reference PNGs, their transparency, several sizes and
  offsets. The counter area is masked when identifying the icon.
- Five families share exactly the same asset across the normal, Greater and Perfect
  variants: Transmutation, Augmentation, Regal, Exalted, Chaos. The family is
  recognised visually, the tier is resolved from its position in the three columns
  of the Currencies profile. This is not an OCR reading of the II/III marks.
- Quantity OCR is independent of item identification.
- `K`/`M` and a decimal comma are supported: `24.7K` becomes **about 24,700**, with
  `Reading.approximate=True`. Never present those numbers as exact.

### Dashboard and value

- `My stash` page: total and one card per registered tab; a separate preview card
  represents the current screenshot and is not added to the saved total.
- Card: name, type, value, last reading, partial state and approximate quantities.
- `Detail & reading` page: screenshot, cells, items, quantities, per-line value,
  corrections, inventory and history.
- Per-tab screenshots are kept **in memory** (`tab_frames`), not yet persisted.
  After a restart, the detail view can show the inventory without an image.
- Conversion: sum of `quantity × primaryValue`, divided by the rate of the selected
  currency. Never assume the primary currency is always divine.

## Prices and local data

Reference documentation: https://poe.ninja/docs/api

- Leagues: `/poe2/api/economy/leagues`.
- Prices: `/poe2/api/economy/exchange/current/overview?league=…&type=Currency`,
  and the same path with `type=Expedition`.
- Metadata: **top-level `items`** holds the full catalogue. `core.items` only holds
  the reference currencies.
- Rates: `lines[].primaryValue`; currency: `core.primary`.
- Relative image paths `/gen/image/…` resolve against **`https://web.poecdn.com`**,
  not poe.ninja (which returns 404).
- Responses are cached for an hour, revalidated with ETag, falling back to the cache
  on failure; loaded at startup and refreshed hourly during tracking.
- `stash_market` merges Currency and Expedition without overwriting the Currency
  reference rates; it converts prices when the primary currencies differ.
- A known item can be unpriced or ambiguous. In particular, several Thaumaturgic
  Flux tiers share one image: do not invent their tier or price.
- For distribution to several users, plan for the caching backend recommended by
  poe.ninja; `JOY_PRICE_BASE` and `JOY_CONTACT` exist for that configuration.

The `data/` directory is ignored by Git and holds user data:

- `profiles.json`: tabs, label and structure signatures, local corrections.
- `inventory.sqlite3`: last quantities, inventory and price history.
- `settings.json`: interface language.
- `prices/` and `icons/`: network caches; other PNGs may be diagnostics.

**Preserve existing inventories and UUIDs across changes.** Old profiles without
`layout_id` are interpreted as Currencies. The SQLite `approximate` column is added
by a non-destructive migration. `Store.rows()` keeps its six-field shape;
approximations are reachable through `approximate_slots()`.

## Rules to preserve

- **User request of 20 September 2026, for all future stash tabs**: look up PoE 2
  names and icons on poe.ninja and PoE2DB before leaving whole families as
  "Unrecognised item". The visual catalogue must be independent of the items priced
  in the league. A known name without a rate stays displayed, without an invented
  price. Do not solve this by imposing a cell-by-cell calibration. Keep the verified
  references, their sources and their identifiers in the project for the next
  sessions, not only in the conversation.

- User feedback: Expedition must never receive the Currencies coordinates. Each
  stash type has its own geometry, independently of the tab name. An uncertain
  detection must not reuse the last type: show "Unrecognised type", with no grid and
  no synchronisation. The manual choice must re-run the analysis and take priority
  over an old profile; a different structure must not overwrite that old profile's
  inventory. This rule holds for all future stash tabs.

- An unknown reading is **not zero**: keep the last state and flag it.
- An unknown icon, an unreadable quantity or a missing price must never produce an
  invented price. Show that the estimate is partial.
- Separate inventories and prices per league; never reuse a rate from another league.
- Do not add the preview to a tab that is already registered.
- The total is an **observed stock**, not automatically farming profit.
- A transfer between two tabs may be counted twice for a while, until both have been
  seen again. Show dates and states rather than promising knowledge of tabs that are
  not visible.
- Workers: no access to Tk widgets from a secondary thread; use the `messages` queue
  and `drain`. The type choice is copied into `layout_override` as a layout id.
- Do not confuse tests on synthetic images with validation on real screenshots.
- Never translate a stored key (`Reason`, `Event`); translate only its label.

## Last validation and resumption points

Resumption priorities:

1. Validate a real Expedition capture: coordinates, recognised items, abbreviated
   counters, masks, large cells and unpriced items.
2. Add tests for the Currencies ↔ Expedition switch, selecting a card during
   capture, merged prices, old profiles/SQLite and `K`/`M`.
3. Check the OCR truncation risk: when the K/M suffix is not recognised on the full
   image, the glyph crop must not accept part of the number.
4. Test the three real paths: import/analyse, Start without a registered tab, then
   registration and synchronisation of two tab types.
5. In time: re-association of renamed/moved tabs, robustness of their identity,
   support for other resolutions/scales and other stash types.

The user may launch the application while work is in progress. Avoid leaving calls
to missing methods between two changes; verify the whole path before announcing a
version that is ready to restart.

## Recognition addendum — 20 September 2026

- Observed cause: the poe.ninja Expedition cache held only 18 items, missing
  Verisium, the alloys and the crests in particular. The PoE2DB page consulted shows
  roughly 45–46 items.
- `joy_tracker/item_catalog.json` keeps 45 Expedition visual references verified on
  https://poe2db.tw/us/Economy_Expedition; names, IDs, image URLs and source,
  **no price**. `catalog.py` merges them with the current metadata without changing
  UUIDs, inventories or prices. Shared IDs are preserved.
- The catalogue stays usable when the price endpoints fail. PNGs are cached in
  `data/icons`; downloads share identical URLs and use at most four connections.
  A first offline use with no cached PNG obviously cannot compare images.
- `tools/update_item_catalog.py` regenerates the Expedition references from PoE2DB.
  It excludes navigation links and price columns. For a future stash, extend the
  sources/categories explicitly, check the IDs, icons and the stash-specific
  geometry, then add tests before enabling it. Do not treat the exchange catalogue
  as the exhaustive set of items in the game.
- The matcher also searches ±4 pixel offsets, without lowering the confidence
  thresholds. Identical images remain ambiguous variants.
- `tests/test_catalog.py` covers the merge, network failures, the shared cache,
  identification without a price, and the offsets. Its six real CDN PNGs are
  composited onto **synthetic** cells: this is not a validation of the user's
  Expedition capture. A separate real validation was later added in
  `tests/test_expedition_real.py`.
- Validation of that change: 53 tests passed in 4.1 s; `smoke_ui` passed in 0.70 s.
  Local merged catalogue: 99 items / 79 families, no download error; 45/45 Expedition
  references found again in synthetic compositions against the full catalogue.
  No real in-game rate was claimed.
- Follow-up user feedback: only 2/32 identities on the real thumbnail, so the
  catalogue alone does not solve the problem. Do not announce the problem fixed on
  the basis of synthetic compositions. The frames looked offset. `aligned_slots`
  searches for a common ±20 pixel translation on the borders, with sufficient
  evidence (65 % of the sides and a 20-point improvement). OCR, icons, local
  corrections and the displayed grid all use the realigned coordinates. Old tab
  signatures stay evaluated at their historical coordinates to preserve UUIDs;
  the base coordinates have since been corrected.
- New **Save the image** button: keeps the full pixels without the frames in
  `data/diagnostics/derniere-capture.png`, and the context in the neighbouring JSON.
  After a failure report, read that local file before any new recognition tweak.
  The button exports the visible image (chosen tab or preview), without sending the
  screenshot over the network.

### Validation on the real capture saved at 23:51

- The original is now available in `data/diagnostics/derniere-capture.png`.
  Measured cause: every Expedition column was 14 pixels too far left. Correcting the
  base rectangles took recognition from 2 to 21 items without changing any
  threshold. The older border adjustment was not enough.
- The four sagas have near-identical artwork. The matcher keeps their close
  candidates as an ambiguous family; the fixed cells E03=Medved, E04=Vorana,
  E05=Uhtred, E06=Olroth resolve the ambiguity **only** when every candidate belongs
  to that visually recognised family. Do not name an empty cell from its position
  alone. No change for the Flux tiers.
- The counter 6 of Chilling Flux was read on the full image, then lost after
  cropping. OCR reuses the validated full reading when both crops fail, a glyph was
  found, and no result contradicts that reading.
- Real result: **25/25 occupied stacks identified with their quantities**, including
  Verisium 38.3K ≈ 38,300. The 7 dark cells stay unknown, not zero. This measurement
  concerns that 1920×1080 capture, not every resolution.
- `tests/fixtures/expedition_real/` keeps only the stash area, its metadata and the
  99 competing CDN references. The test runs without network and checks names,
  counters, the absence of a false identity on dark cells, and UUID preservation for
  old and new Expedition profiles.
- `LEGACY_EXPEDITION_SLOTS` preserves the old identification coordinates; new
  profiles record `anchor_rects`. Do not remove that compatibility, and do not
  rewrite existing inventories to fix a geometry.
- Last validation: **57 tests passed in 5.6 s**, `smoke_ui` in **0.53 s**.

### Displaying pending quantities — 21 September 2026

- When the game loses the foreground before three matching observations,
  `Consensus` deliberately keeps a `None` quantity: tracking stays "Waiting for the
  game". The last raw OCR reading is now passed separately to the interface and
  shown as "(provisional)" in the list. It changes neither the total, nor SQLite,
  nor the consensus. Confirmed observations keep going through the existing
  synchronisation path.
- Cells with no counter, no recognised icon and no sufficiently bright artwork are
  marked `Empty cell` with quantity `None`, then omitted from the list. They never
  become a zero or a price. The conservative filter is verified against the seven
  empty cells of the real Expedition capture.

### Automatic tab registration — 21 September 2026

- User request: remove the "register this tab" step. As soon as a stash is seen with
  a known structure and a readable active tab, create its profile automatically,
  then reuse its UUID on later visits.
- On the real capture, the bright lower frame of the active tab indicates SAGA; when
  the side list is open, a small warm arrow to its left confirms the same title.
  `active_tab` uses both cues and refuses a disagreement. Do not simply take one
  visible name among all the tabs.
- `Profiles.observe` keeps the seen label (`visible_name`), the structure, the title
  image, its position and the old anchors. A label already known at another position
  is judged ambiguous, without merging stocks. Old manual profiles keep their UUID
  and their historical reading.
- Import analysis can create the profile, but only tracking with confirmations
  synchronises quantities. When the title or the type is not reliable, keep a preview
  without a persistent inventory.
- The real-capture test checks SAGA with and without the side menu, another active
  tab, a disagreement between arrow and bar, the UUID preserved after a reload, and
  the full `App.live_loop` path without a manual click.

### The `$$` label of the Currencies stash — 21 September 2026

- Report: the selected `$$` tab was not added automatically. Its Currencies grid is
  distinct from the Expedition one and stays correct; the failure came from a title
  made only of symbols. RapidOCR reads neither the small symbol of the top button nor
  the two `$$` signs of the side menu on the reference capture. The old
  `read_tab_text` also rejected results without an alphanumeric character.
- `read_tab_text` now accepts currency symbols recognised by OCR. For this local
  case, `reference_tabs/dollar_top.png` and `dollar_menu.png` keep very small
  references from the real capture. A conservative visual match recognises `$$` when
  OCR fails. When the list is open, the arrow and the side label confirm the top one;
  a disagreement refuses synchronisation. Both the name and the type are required to
  reuse the UUID.
- Live loop test: `$$` menu taken from the real capture, **synthetic** Currencies
  body. That test confirms `currency` detection, a single creation of the `$$`
  profile and UUID preservation. Do not announce a full in-game validation of that
  capture.

### The Runes stash and its five views — 21 September 2026

- The user identified, in the order of the five inner buttons: **Runes**,
  **Kalguuran Runes**, **Soul Cores**, **Idols**, **Ancient Augments**.
- The outer title stays `Runes`: treat the five views as a single registered tab,
  with a distinct state per view. Never erase the quantities of the four hidden views
  when the fifth is re-read, and never count a shared cell twice. An uncertain inner
  view synchronises nothing.
- `Save the image` now creates a dated PNG and JSON on every click, in addition to
  `derniere-capture.png/.json` for compatibility.
- First implementation made from the five chat screenshots: five distinct geometries
  and cell namespaces, a single parent `runes` profile, view detection from the
  borders and a manual fallback selector. Tracking preserves the four hidden views
  when the fifth is read. The poe.ninja categories `Runes`, `SoulCores` and `Idols`
  are loaded in parallel; no distinct public category was found for Ancient Augments.
  Tests on synthetic grids pass, but the coordinates and in-game recognition remain
  unvalidated for lack of original files.
- A cell visually confirmed empty three times now removes its previous stock; an
  unreadable reading keeps the last stock. This rule applies to every stash.
- Validation resumed on 22 September with the real capture saved at 01:05: the
  `runes` grid scores 100 % of borders against 85 % for `kalguuran`. The structural
  separation threshold went from 18 to 12 points; the capture is now detected as
  `runes`. The 70 rectangles follow the cells and the first occupied counters read
  2, 60, 5, 1 and 52. A local fixture keeps the stash area in
  `tests/fixtures/runes_real/stash.png`.
- An old auto-created `Runes` profile had been wrongly registered as `currency`,
  with no stock. `Profiles.observe` can now correct that type while preserving the
  UUID, but only when SQLite holds neither a cell nor history for that profile; a
  profile with stock is never reclassified.
- Last validation: **69 tests passed**, as well as `python -m tests.smoke_ui`.
  That capture validates the first Runes view; the four other geometries still rest
  on the chat screenshots until a real diagnostic capture exists.

### Live refresh blocked by animations — 22 September 2026

- Report: tracking looked active on the `$$` Currencies stash, but SQLite had
  received no new observation since 20 September.
- Cause fixed in `Scanner.read_incremental`: any single-pixel change dropped the
  cell's consensus vote. Stash or icon animations therefore prevented reaching three
  matching readings, even when the item and the OCR quantity stayed identical.
- Consensus now rests on `(item, quantity, approximate, empty)`. An animation does
  restart the reading, but it no longer destroys identical votes. A different
  quantity or identity naturally resets the counter; tab, structure and matcher
  changes and the periodic expiry keep their explicit invalidations.
- Test added with animated pixels between the three observations. Last validation:
  **70 tests passed**, as well as `python -m tests.smoke_ui`.

### Moved tab and the impression of broken prices — 22 September 2026

- On a direct screen capture, `$$` had moved from `x=45` to `x=363` after the bar was
  scrolled/reordered. The Currencies structure, the 32 items and their new counters
  were read correctly (including 109, 1280, 172 chaos, 164 divines), but the profile
  identity was refused because of its position. SQLite marked the old rows uncertain
  without replacing their quantities, which gave the impression that prices had
  stopped working.
- `Profiles.observe` now re-associates a **unique** active label, in the same league
  and with the same structure, to its existing UUID even when its position changes.
  It updates the rectangle, the title image and the anchors. Several profiles sharing
  the same label stay ambiguous and are not merged.
- The user's `$$` profile keeps its UUID and now points at `(363,97,71,27)`.
  Check after restart: 298 prices loaded, primary currency divine, 0 Currencies item
  registered without a price, `$$` card ≈164.41 div, SAGA ≈15.13 div and a total of
  ≈179.54 div. The 16 unpriced items shown concern SAGA, not Currencies.
- Application restarted cleanly with the new code. Last validation: **71 tests
  passed**, as well as `python -m tests.smoke_ui`.

### English-first project and language selector — 22 September 2026

- The user asked for the project to be English-speaking, while keeping French
  selectable in the application settings. See "Language and stable keys" above for
  the architecture and the invariants.
- 139 French interface strings were moved to `joy_tracker/i18n.py` (188 keys per
  language). Code comments and docstrings were already in English.
- Three display strings that doubled as control values were made into stable keys:
  `Reading.reason`, `valuations.reason`, the layout selector and the history mode.
- README.md and AGENTS.md translated. The Git history was rewritten into a single
  English root commit, on a solo repository, with the user's agreement.
- Checks added: `EN`/`FR` catalogues have identical key sets and identical
  `{placeholders}`; every `Reason` and `Event` value has a label.
- Last validation: **71 tests passed**, as well as `python -m tests.smoke_ui`,
  and the SQLite migration verified on the user's real database.
