# Exile Worth — PoE 2 prototype

Local Windows application: captures the Currencies, Expedition and Runes stash tabs,
reads the quantities, keeps an inventory per tab and per league, values it with
poe.ninja prices and stores the history in SQLite.

The interface is available in **English and French**; pick the language in the
toolbar. English is the default.

## Running

Python **3.11** is required by the bundled RapidOCR build. On this machine it is
available through `py -3.11`.

```powershell
.\run.ps1
```

Once installed, start without reinstalling the dependencies:

```powershell
.\.venv311\Scripts\python.exe -m exile_worth
```

## First use

1. Prices and icons load at startup. Pick another league and click **Load prices**
   if needed. Icons are cached locally.
2. Open the currency stash in game at 1920 × 1080. Click **Capture in 5 s** and go
   back to the game, or import a full PNG screenshot. No tooltip may cover the
   cells used as references.
3. **Analysis starts automatically**: the application recognises the currencies
   from the catalogue icons and reads the white numbers in the top-left corner.
   No manual cell mapping is required. Check that the rectangles follow the cells.
   This profile was measured on one specific screenshot; another interface scale
   requires adapting the coordinates in `exile_worth/layouts.py`.
4. If a detection is uncertain, select the cell and its exact currency, then
   **Correct the icon**. This local reference is optional and takes priority when
   it matches the image. The quantity is read even when the icon is unknown; an
   unknown item does not enter the valuation.
5. A cell visually confirmed empty three times removes its previous stock.
   An unreadable icon or quantity keeps the last known quantity.
6. **Start** reads the stash continuously and automatically adds every new tab
   whose selection and title are readable. The application recognises the bright
   frame of the active tab in the top bar; when the side tab list is open, its
   arrow confirms the selected title. It then keeps a UUID and the stash structure
   to find the same inventory again. No "register this tab" button is needed.
   The badge shows "Waiting for the game" while Path of Exile is not in the
   foreground. An unreadable or contradictory title leaves a preview without
   synchronisation, to avoid associating two inventories by mistake.
   The symbolic `$$` label of the Currencies stash is recognised visually even
   when OCR cannot read its signs; its grid stays distinct from the Expedition one.
7. **Analyse** shows a control reading without saving it automatically.
   An explicit correction can be saved with **Correct a quantity**.
8. **Start / Pause**, then go back to the game. Three matching readings per cell
   are required to synchronise. A change within the same tab also triggers a new
   reading.

## Dashboard and value history

**My stash** shows one card per registered tab. The current preview stays separate
from the saved total. Clicking a card opens its inventory in **Detail & reading**;
live readings keep updating the right tab. The Currencies/Expedition/Runes type is
distinct from the customisable tab name. The Runes stash keeps its five views under
a single card: Runes, Kalguuran Runes, Soul Cores, Idols and Ancient Augments. Each
has its own grid and quantities. The coordinates of the five views come from chat
screenshots and still need in-game verification. The selector lets you pick a view
when detection hesitates. The Expedition coordinates still need validation against
real screenshots.

Automatic detection examines the borders first, then the icons. When it cannot
determine the type, no grid is applied: the application does not fall back to the
last tab's type. Selecting the type or the view re-runs the analysis of the
screenshot; a choice that differs from the registered profile stays a preview and
does not replace that profile's inventory.

**Value & history** keeps snapshots in divines: quantities, rates, conversion rate,
value per tab, observation dates and partial or approximate reading indicators.
Points are created on inventory changes, reading-quality changes or price-data
changes, after the league prices have been loaded. Plain previews are not saved as
inventories. Older quantity histories are preserved; the new curve starts with this
version, without retroactively fabricating valuations.

- **Historical rates**: each point uses its own saved prices.
- **Fixed prices of the first displayed point**: successive quantities are valued
  against a single price basis; that basis depends on the displayed 500-point window.
- Clicking a point shows its historical values per tab and their dates.
- **Session start / Session end** records two persistent boundaries and compares the
  values at historical rates and at the starting prices. Go through every tab before
  each boundary; readings are not simultaneous and a transfer may be counted twice
  for a while. A change is not farming profit.
- **Export this history to CSV** exports the 500 displayed points. All points stay
  in SQLite, separated per league.

Snapshots are immutable: refreshing the prices does not modify older values.
Repeated observations without a change do not create duplicates.

## Reading changes

Tracking compares images cell by cell. A cell confirmed unchanged skips OCR and the
icon search. When only the counter changes, only its quantity is re-read; a modified
icon is identified again. Three fresh matching readings confirm each change; an
unstable cell does not reset the others. An unknown reading keeps the old stock and
flags it as uncertain.

Geometry work is shared within a frame: the gradient maps are built once for all
layouts instead of once per layout, over the 700x800 window that contains every
stash grid rather than the whole screen, and the alignment fitted during detection
is reused when reading. That halves the per-frame geometry cost, from about 63 ms
to about 30 ms, roughly 9 % of the 330 ms loop. The cache is keyed on the frame
object itself, so a new frame is always re-fitted.

A full check runs again after 30 seconds. Changing tab or structure, coming back
after a focus loss, or refreshing the references invalidates the cache and requires
new confirmations. The pixel-by-pixel comparison is conservative: an animation can
trigger extra work. In-game timings and accuracy still need to be measured; the
cache tests use synthetic images.

A renamed title or a moved tab can become ambiguous: safe re-association after those
changes still needs validation. Check the cards when titles change, since a new
inventory could temporarily count the same stock twice. The side menu is not
required, but its arrow provides an extra verification when it is open.

## Automatic recognition

The PNG assets come from the `image` URLs of the poe.ninja catalogue, resolved
against `web.poecdn.com`. The comparison tries several sizes and offsets, masks the
counter area and accounts for transparency. An insufficient score or two families
that are too similar produce "Icon to confirm" rather than an arbitrary price.

The five families Transmutation, Augmentation, Regal, Exalted and Chaos each share
the same CDN image across their normal / Greater / Perfect variants. The icon
identifies the family first; the three columns of the standard profile then identify
the tier. Outside the expected row, a visually identical variant stays "Variant to
confirm". This is not an OCR reading of the II/III marks.

The counter is handled independently of the icon: upscaling, isolation of the white
glyphs aligned in the top-left corner, and OCR on two renderings. A disagreement
between renderings yields an unknown quantity. The tracking consensus requires three
identical readings; it does not protect against a systematic visual error.

## What is measured

- **Immediate estimate in divines**: after an import or a capture, the total of the
  identified and quantified cells appears, even without a registered tab. The
  "Value (div)" column details each line. An incomplete total is marked "partial";
  unreadable cells and missing rates are counted separately.
- **Tracked stash**: as soon as an inventory is synchronised, the grand total is the
  sum of the last states of the league's tabs. The screenshot estimate stays visible
  separately and is never added a second time. Plain previews do not modify the saved
  inventory; continuous tracking confirms the readings.
- Known quantities only, per slot: revisiting replaces, it does not add.
- Uncertain reading: the previous quantity is kept and flagged in the inventory.
- A cell that is not identified, or has no first reading, does not enter the total.
  The status shows the number of confirmed cells; a partial total is not the full value.
- During tracking, a quantity read only once can appear as "provisional" in the list.
  It enters the total and the inventory only after three matching readings while the
  game stays in the foreground. Visually empty cells are omitted from the list; no
  zero quantity is assumed.
- A cell confirmed empty is **recorded as read and holding nothing**, not forgotten.
  It carries no item and no quantity, so it is still never a stored zero, but it no
  longer counts as unread. Without that distinction a fully scanned tab claimed to
  be partial forever: the Expedition tab has 25 occupied cells out of 32, and its
  card used to report "Partial - 7 to check" even though those 7 had been confirmed
  empty three times each.
- Tabs that are not revisited keep their last state. A move between tabs can be
  counted twice for a while until both have been seen again.
- The value is not farming profit: purchases, sales, transfers and rate changes all
  affect the stock. The history keeps the quantities and the rates that were used.
- The weapon slot in the middle and the free grid at the bottom of the Currencies tab
  are excluded. The profiles cover 37 Currencies cells and 32 Expedition areas.
  Ambiguous variants without a certain identity do not receive an invented price.
  K/M counters are approximate.

## Capture and storage

Capture reads only the client area of a foreground window whose title contains
"Path of Exile". Use borderless windowed mode. Capture stops reading when the game
loses focus; no key or click is ever sent to the game. Another program covering the
stash can prevent recognition. Reference thumbnails and tab identities are stored
locally in `data/profiles.json`, quantities and historical prices in
`data/inventory.sqlite3`. No screenshot is ever sent over the network.

The frames are a first estimate from one visible screenshot. A real Expedition
capture at 1920×1080 is now covered by a test: its 25 occupied stacks are identified
and quantified, including the abbreviated Verisium. The seven dark cells remain
unknown; other resolutions and scales still need validation. The tests combine this
capture with synthetic images. A local Transmutation reference saved in this
workspace also made it possible to verify the match against the CDN images, without
serving as a model for the automatic matcher.

## Prices

Identification also uses a PoE 2 visual catalogue kept in the project, completed from
[PoE2DB Expedition](https://poe2db.tw/us/Economy_Expedition). It includes Verisium,
the alloys, the crests and the sagas, even when absent from the league price
catalogue. A recognised item without a rate keeps its name and stays excluded from
the valuation. Fluxes sharing an icon are shown as variants to confirm. The
references are reused on subsequent launches.

After updating the software, restart the application and load the prices so that
these references are loaded too. Downloaded icons are cached locally. Maintainers can
refresh the names and URLs with
`.\.venv311\Scripts\python.exe tools/update_item_catalog.py`, then check the JSON and
the tests. That script imports no rate from PoE2DB.

Source: [public poe.ninja API](https://poe.ninja/docs/api).
Leagues: `/poe2/api/economy/leagues`. Currencies:
`/poe2/api/economy/exchange/current/overview?league=…&type=Currency`.
The parser uses `lines[].primaryValue`, `core.primary` and the `items` + `core.items`
metadata. It never assumes the primary currency is exalted.

Responses are kept for an hour and revalidated with ETag. The price button respects
that cache. Prices are loaded on demand, then re-checked every hour during tracking;
their date stays visible. On a network failure, an existing cache is used with a
staleness note. A currency without a rate is excluded, with the number of unpriced
cells shown. The divine/exalted/chaos conversions use the same rates.

For local use, the prototype calls poe.ninja directly. **Before distributing to
other users**, point `EXILE_PRICE_BASE` at a caching backend, as poe.ninja requests,
and set `EXILE_CONTACT` to a real contact. The backend must expose the same paths.
Do not multiply direct clients against the site.

## Margin harness

A pass/fail suite cannot tell a decision that barely held from one that held
comfortably, and that distinction is what keeps breaking this project. Every
recognition decision is measured against its threshold, with the **headroom**
between them:

```powershell
.\.venv311\Scripts\python.exe -m tests.margins
```

```
decision                          measured  threshold   headroom  detail
expedition_real.border_margin       0.7333     0.1200     0.6133  expedition over kalguuran
expedition_real.icon_score_min      0.9341     0.9200     0.0141  weakest cell E22  <-- TIGHT
runes_real.border_margin            0.1500     0.1200     0.0300  runes over kalguuran  <-- TIGHT
```

The last line is the most fragile decision in the project: Runes separates from
Kalguuran by 0.15 against a required 0.12, so 0.03 of headroom. That threshold
was already lowered once, from 18 to 12 points, to make Runes detect at all.

Four captures are guarded: the Expedition stash, the Runes stash, and the `$$`
tab selection and label. `tests/test_margins.py` compares the measurements
against `tests/margin_baseline.json` and fails on:

- **shrinking headroom** — a code change degraded a measurement;
- **a relaxed threshold** — lowering a threshold *raises* headroom, so it would
  otherwise hide itself; the thresholds are pinned separately;
- **a changed count** — fewer identified cells, even when the margins hold.

After a deliberate change, re-measure every fixture and refresh the baseline:

```powershell
.\.venv311\Scripts\python.exe -m tests.margins --update
```

## Session log

Recognition failures are diagnosed from `data/session.log` (rotating, 2 MB × 4,
local only, never uploaded). It records the numbers behind every decision, which
is what a screenshot alone cannot tell you:

```
layout: borders accepted expedition (score 1.000 >= .55, margin 0.733 >= .12)
        | borders expedition=1.000, kalguuran=0.267, ancient_augments=0.235
recognition expedition: 25 identified, 7 empty, 0 unidentified
  R06  unidentified reason=unknown_icon  best=uhtreds-saga  score=0.9097 margin=0.0008
```

The third line is the useful one: the cell was refused because its margin over the
runner-up was 0.0008, far below the required 0.015, while its score sat just under
the 0.92 threshold. That distinguishes "raise the threshold" from "add a catalogue
entry", which was previously guesswork.

- `INFO` (default) logs lifecycle events and every **decision change**. The live
  loop runs three times a second, so repeated identical verdicts are suppressed;
  a line means something actually changed.
- `EXILE_LOG_LEVEL=DEBUG` adds per-frame metrics (cells, re-reads, icon searches,
  milliseconds) and per-cell detail.
- Exceptions are recorded with their full traceback. The interface keeps showing
  its own short message.

After a failure report, read this file together with the PNG saved by
**Save the image**: the PNG shows what was seen, the log shows why it was refused.

## Language

The interface language is chosen in the toolbar and stored in `data/settings.json`.
Adding a language means adding one entry to `LANGUAGES` and one catalogue to
`CATALOG` in `exile_worth/i18n.py`; both catalogues must share the same keys and the
same `{placeholders}`.

Translation keys are stable ASCII identifiers. Some of them are also stored values:
`Reading.reason` drives logic (an empty cell clears its stock) and `valuations.reason`
is written to SQLite. Never translate those keys — only their labels.

## Checking

```powershell
.\.venv311\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover unreadable and null quantities, league/tab isolation, revisits,
missing prices, the cache, signatures and temporal consensus, as well as recognition
without calibration, images shared between tiers, size variations, dark backgrounds
and counters read independently of the icons.
