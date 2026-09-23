# Exile Worth — work journal

Dated record of what was reported, what was measured, what was changed and what
stayed unvalidated. `AGENTS.md` holds the durable state and the rules; this file
holds how they were arrived at.

Read it when a decision looks arbitrary: the reason is almost always a measured
failure recorded below. Entries are append-only and in chronological order; do
not rewrite an entry to match later behaviour, add a new one.

## Recognition addendum — 20 September 2026

- Observed cause: the poe.ninja Expedition cache held only 18 items, missing
  Verisium, the alloys and the crests in particular. The PoE2DB page consulted shows
  roughly 45–46 items.
- `exile_worth/item_catalog.json` keeps 45 Expedition visual references verified on
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


## Validation on the real capture saved at 23:51

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


## Displaying pending quantities — 21 September 2026

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


## Automatic tab registration — 21 September 2026

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


## The `$$` label of the Currencies stash — 21 September 2026

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


## The Runes stash and its five views — 21 September 2026

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


## Live refresh blocked by animations — 22 September 2026

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


## Moved tab and the impression of broken prices — 22 September 2026

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


## English-first project and language selector — 22 September 2026

- The user asked for the project to be English-speaking, while keeping French
  selectable in the application settings. See "Language and stable keys" above for
  the architecture and the invariants.
- 139 French interface strings were moved to `exile_worth/i18n.py` (188 keys per
  language). Code comments and docstrings were already in English.
- Three display strings that doubled as control values were made into stable keys:
  `Reading.reason`, `valuations.reason`, the layout selector and the history mode.
- README.md and AGENTS.md translated. The Git history was rewritten into a single
  English root commit, on a solo repository, with the user's agreement.
- Checks added: `EN`/`FR` catalogues have identical key sets and identical
  `{placeholders}`; every `Reason` and `Event` value has a label.
- Last validation: **71 tests passed**, as well as `python -m tests.smoke_ui`,
  and the SQLite migration verified on the user's real database.


## Language and stable keys — 22 September 2026

- The user asked for an English-first project, keeping French selectable in the
  application settings. English is the default and the source language.
- `exile_worth/i18n.py` holds `LANGUAGES`, the `CATALOG` for `en` and `fr`, and
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
- `exile_worth/diagnostics.py` configures a rotating `data/session.log`
  (2 MB × 4) and exposes `log`, `failure(context, exc)` and `ChangeGate`.
  A read-only data directory falls back to a `NullHandler`: logging must never
  prevent the application from starting.
- `INFO` records lifecycle events and every **decision change**; `DEBUG`
  (`EXILE_LOG_LEVEL=DEBUG`) adds per-frame metrics and per-cell detail. The live
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


## Margin harness — 22 September 2026

- Problem addressed: the suite was binary. When `test_rune_pages` passed, nothing
  said whether it passed by 0.30 or by 0.005. The structural separation threshold
  had already been lowered from 18 to 12 points for Runes with no measurement of
  what it cost Expedition.
- `tests/margins.py` measures each decision against its threshold and reports
  `headroom`, the distance to the point where the decision would flip.
  `python -m tests.margins` prints the table, `--update` rewrites the baseline.
- **Measured state, the numbers that matter:**
  `runes_real.border_margin` = 0.1500 against a required 0.1200, so **0.03 of
  headroom — the most fragile decision in the project**. Expedition is comfortable
  (0.6133). The tight icon decisions are `expedition_real.icon_score_min` 0.0141
  and `icon_margin_min` 0.0105.
- `tests/test_margins.py` guards three distinct regressions:
  shrinking headroom, a **relaxed threshold**, and a changed count.
- The threshold guard exists because of a hole found while building this:
  lowering a threshold *raises* measured headroom, so the original design stayed
  silent on exactly the historical mistake it was meant to catch. Thresholds are
  therefore pinned in the baseline and compared separately. Do not remove that
  test; without it the harness is blind in the direction that matters most.
- Cells resolved by fixed-slot position (the four sagas) are excluded from the
  icon-margin measurement: `ICON_MARGIN_MIN` never governed them, so including
  them reported a false failure.
- Verified by injecting real regressions: lowering the separation to .06 is caught
  as two relaxed thresholds; shifting the Expedition geometry by 6 px is caught
  three ways (identified 25 → 21, `icon_margin_min` 0.0105 → 0.0063,
  `icon_score_min` 0.0141 → 0.0119).
- **Before changing any recognition threshold**, run the harness, make the change,
  run it again and compare. Refresh the baseline deliberately, never to make a red
  test go green.
- Last validation: **86 tests passed**, as well as `python -m tests.smoke_ui`.


## Confirmed-empty cells — 22 September 2026

- Problem addressed: `Store.sync` deleted a cell confirmed empty, which made it
  indistinguishable from a cell that had never been read. The dashboard computed
  `unread = expected - len(rows)`, so a fully scanned tab claimed to be partial
  forever. On the real Expedition capture, 25 occupied cells out of 32 meant the
  card reported "Partial - 7 to check" permanently, even though those 7 were
  confirmed empty three times each. That destroyed the meaning of the partial
  signal the rest of the interface relies on.
- A non-destructive `empty` column was added to `slots`. A confirmed-empty cell is
  now stored with `item=NULL, quantity=NULL, empty=1` and a confirmation stamp:
  knowledge that the cell holds nothing, still never a stored zero.
- **`Store.rows()` keeps its six fields and its meaning**: cells holding stock.
  Empty rows are excluded there and exposed by `empty_slots()`, the same shape as
  `approximate_slots()`. Including them in `rows()` would have turned every
  consumer — valuation, CSV, inventory tree, history snapshots — into treating
  them as unread, which is the bug in reverse.
- The three `unread` computations in `app.py` (cards, grand total, valuation
  points) now subtract the confirmed-empty cells, and the live status line
  excludes them from its denominator.
- Rows deleted by the old behaviour cannot be recovered; they are re-learned on
  the next scan. The user's database therefore still shows 57 stock rows and 0
  empty until each tab is scanned once more.
- Verified on the real Expedition capture with the real OCR: 25 stock + 7 empty =
  32 expected, 0 unread, no partial marker, 0 stored zeros, 0 empty rows carrying
  an item.
- `tests/test_empty_cells.py` pins the invariants: empty is never a zero, stock
  reappearing clears the mark, an unreadable reading keeps a recorded emptiness,
  a repeated empty reading is not a change (otherwise every scan would append a
  history snapshot), league/tab isolation, and the legacy-database migration.
- Last validation: **98 tests passed**, as well as `python -m tests.smoke_ui`.


## Live-loop geometry cost — 22 September 2026

- Problem addressed: `resolve_layout` calls `detect_layout` on every iteration of
  the 0.33 s loop, measured at 58.5 ms, and `read_incremental` then re-fitted the
  same alignment. The whole geometry path cost 62.9 ms per frame, 19 % of the
  budget, to re-derive a layout that only changes when the tab changes.
- Profiling, not guessing, found the cost was mostly waste:
  `aligned_slots` rebuilt identical edge maps once per layout (18.4 ms of the
  32.3 ms it spent), and `detect_layout` built its own maps over the full
  1920x1080 frame (11.3 ms) although every cell fits in 700x800.
- `layouts.edge_maps(frame)` now builds those maps once over `REGION = (800, 700)`;
  `aligned_slots(frame, layout_id, edges=None)` accepts them. `Scanner.aligned()`
  memoises the fit per frame and per layout, so detection and reading share it.
- The cache is keyed on the **frame object**, compared with `is`. Keeping the
  object (never its `id()`, which can be reused after collection) makes identity a
  sound test. A copy of the same pixels is a different frame and is re-fitted.
- Result: 62.9 ms -> 30 ms per frame, 19.1 % -> 9.1 % of the loop budget.
- **Behaviour is unchanged and that was verified, not assumed**: the margin
  harness reports the same values to four decimals, and a test compares readings
  with a warm and a cold cache.
- What was deliberately *not* done: a cross-frame cache that keeps the previous
  verdict. Confirming only the current layout would be roughly seven times cheaper
  again, but Runes and Kalguuran overlap enough that the current layout could keep
  scoring above the floor after the page changed, and the rule is explicit that an
  uncertain detection must never reuse the last type. Validating that shortcut
  needs a real capture of a second rune page, which does not exist yet. Do not add
  it on synthetic grids.
- `tests/test_geometry_cache.py` pins both halves: the saving (one fit per layout
  per frame, reading reuses detection's) and the invalidation (a new frame, or an
  equal-but-distinct one, is always re-fitted). It also asserts that every layout
  fits inside the window with room for the alignment search.
- Last validation: **105 tests passed**, as well as `python -m tests.smoke_ui`.


## Structural debt in app.py — 22 September 2026

- `expected_slot_count` existed as **three identical inline copies** in `app.py`:
  the dashboard card, the grand total and the valuation point each recomputed
  "sum the five Runes views, otherwise this layout's cells". The next multi-view
  stash would have made them diverge, and a disagreement there shows up as a wrong
  "partial" badge rather than as a crash. It now lives once in
  `layouts.expected_slot_count(tab)`, next to the geometry it reads.
- The worker-to-UI message for an analysis or a live reading was a tuple of six or
  seven items whose length the consumer probed:
  `layout_id = payload[5] if len(payload) > 5 else …` and
  `provisional = payload[6] if kind == 'live' and len(payload) > 6 else []`.
  A producer adding a field in the wrong position changed behaviour silently.
  It is now the frozen `ScanResult` dataclass in `app.py`, with named fields and
  `provisional` defaulting to empty.
- The `payload[5]` fallback guessed the layout from the first slot's name prefix
  (`'expedition' if readings[0].slot.startswith('E')`). All three producers had
  been sending `layout_id` for a while, so that branch was dead **and** would have
  guessed wrong for the Runes views. Removed.
- `tests/test_structure.py` pins both: every Runes view yields the same
  expectation, a legacy profile without `layout_id` counts as Currencies, an
  unknown id falls back without raising, the three former call sites agree by
  construction, and `ScanResult` is immutable with an explicit `None` layout
  rather than an absent tuple element.
- Behaviour unchanged: the margin harness is identical and `smoke_ui` passes.
- Last validation: **115 tests passed**, as well as `python -m tests.smoke_ui`.


## Four quiet defects — 22 September 2026

- None of these showed as a crash, which is why they survived a full review.
- `icons.py` pinned the artwork host in a comment but checked only the scheme.
  `urljoin()` returns an absolute URL untouched, so a catalogue entry could point
  the downloader at any https host. The host is now checked against `ICON_HOSTS`
  with `urlparse().hostname`, which also rejects
  `https://web.poecdn.com@elsewhere/`, a form a `netloc` comparison would have
  let through. A refusal is logged and counted as a missing icon, as before.
- `vision.py` keyed the incremental cache on `id(self.matcher)`. `id()` is reused
  after collection, so a rebuilt catalogue could land on the same value and keep
  serving identifications made with the old one. `IconMatcher` now carries a
  monotonic `revision`. A matcher object holds ~80 MB of template arrays, so a
  counter was chosen over keeping the object alive.
- `Profiles._no_stored_inventory` used `with sqlite3.connect(...)`, which commits
  but never closes. It now uses `closing()`.
- `model.value_inventory` was superseded by `estimate_readings` and kept alive
  only by its own two tests. Those covered league isolation and the reporting of
  unpriced items, so they were **ported** to `estimate_readings`, not deleted.
- The fake `Matcher` in the tests had no `revision`, which broke six tests: it
  did not model the real interface. Fixed rather than worked around.
- Last validation: **124 tests passed**, as well as `python -m tests.smoke_ui`.

## Package renamed to exile_worth — 22 September 2026

- The application has been called Exile Worth from the start; the package still
  carried the working name `joy_tracker`. Every import, the module entry point,
  `run.ps1`, the VS Code task and the docs now use `exile_worth`. Git recorded 17
  renames, so per-file history survives.
- The environment variables followed: `JOY_PRICE_BASE`, `JOY_CONTACT` and
  `JOY_LOG_LEVEL` became `EXILE_*`. No fallback to the old names: this prototype
  has never been distributed, and reading both would have outlived its usefulness.
  Anyone who had set one must rename it, or the price base silently reverts to
  calling poe.ninja directly.
- `data/` is unaffected: it resolves from the project root, not from the package.
  Verified after the move — 57 stock rows and `profiles.json` still in place.
- Three files still written in French were translated while being touched: the
  `reference_tabs` and fixture READMEs, and the VS Code task label, which also
  still named the old module. The i18n pass had missed them because they are
  neither `.py` nor a root README.
- The project **directory** is still named `joy_tracker`. Nothing in the code
  depends on it; renaming it is the user's call, outside a session.
- Last validation: **124 tests passed**, smoke_ui and the margin harness unchanged.

## Guarding the $$ tab and the catalogues — 22 September 2026

- The margin harness covered two captures. Tab selection and the `$$` label,
  which OCR cannot read at all, were unguarded.
- `tests/margins.py` now measures the lit run marking the selected tab (44
  against a required 32), the sidebar arrow that confirms the active title (4
  rows against 2, 26 warm pixels against 8), and the two `$$` template scores.
- **`dollar_tab.arrow_rows` clears its floor by 2** — the narrowest absolute
  margin in the project outside the Runes separation, and it decides whether the
  side menu can confirm the active tab. Recorded as a known fragility.
- The two `symbol_*` scores are near-tautological and documented as such in the
  code: the templates were cut from that very capture, so ~1.0 means the matcher
  still recognises its own source, not that `$$` is robust. Stating that matters
  more than the number, which would otherwise read as 0.20 of comfort.
- `tests/test_i18n.py` replaces the scratch script that checked the catalogues.
  A key present in one language and missing in another falls back silently, so it
  reads as an untranslated string; a `{placeholder}` that differs raises inside
  `.format()` only for the language with the wrong name, which an
  English-speaking author never sees.
- Verified by injection rather than assumed: a key removed from the French
  catalogue, a renamed placeholder, a blank entry and a stray brace each fail the
  suite; the healthy state passes.
- Last validation: **140 tests passed**, as well as `python -m tests.smoke_ui`.

## The four unvalidated Runes views, captured — 22 September 2026

- Four of the five Runes geometries had been measured on chat screenshots. The
  user captured all five views through **Save the image**, at 1920x1080, in one
  session. They are cropped to `frame[0:765, 0:655]`, the window the earlier
  Runes fixture already used — verified pixel-identical before any file was
  written, so the crop convention is measured, not assumed.
- `stash.png` became `runes.png`, and the four new views take the view names.
  Five references pointed at the old name, not the three a first grep suggested:
  `margins.py`, `test_diagnostics.py`, `test_geometry_cache.py` and two in
  `test_rune_pages.py`.
- **All five geometries hold.** Cell counts are exact (70, 60, 47, 31, 17) and
  each view aligns on a single translation of at most 3 px, against the ±20 px
  the search allows. The coordinates read off chat screenshots were right.
- Border separation on real captures: ancient_augments 0.83, idols 0.79,
  kalguuran 0.38, soul_cores 0.32 — and runes **0.03**. The tight decision is
  confirmed as the only one, and it is now known to be **one-directional**: a
  Runes capture is nearly matched by the Kalguuran grid (0.850), while a
  Kalguuran capture reaches only 0.586 on the Runes grid. Only one of the two
  views can be misread.
- The baseline gained 12 entries and changed none. That is the check that
  mattered: adding views must not move a recorded headroom or a threshold.
- Two of the four captures had been saved while the application displayed
  `unknown`. Offline, every one of the five is recognised on both the
  borders-only and the full path, so that was the app's state at save time, not
  a recognition failure. Worth remembering when reading a sidecar: `layout` is
  what was *displayed*, not what the frame contains.
- **The view selector was found while looking for the selection indicator.**
  Five buttons above the grid, 64 px pitch from x=175, band y=130..190; the
  visible view is lit by an amber glow. On the five captures the lit button wins
  by 4.2 to 10.0 of amber excess — two orders of magnitude more comfortable than
  the 0.03 of the grid comparison, and it names the view without reading the
  grid at all. This is the robust discriminant the Runes/Kalguuran resumption
  point was asking for.
- It is **measured, not wired in**. Promoting it changes how layouts are
  resolved, which is the user's call, and the grid comparison is what every
  stored profile was registered against. `test_view_selector_lights_the_visible_view`
  pins the observation meanwhile.
- The unlit conch button reads warm on its own (20.6 against 17.1 for its
  neighbours), so a fixed threshold would pick it in three views out of five.
  Any decision built on the selector has to compare buttons against each other.
- Both new tests were verified by injection rather than assumed: a 9 px shift of
  the Idols geometry fails the alignment test, and moving the selector band off
  the buttons fails the selector test.
- Last validation: **143 tests passed**, `python -m tests.smoke_ui`, and
  `python -m tests.margins` at 27 decisions, no FAILS, the same 3 TIGHT.
