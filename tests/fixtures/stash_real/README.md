Real captures of four single-view stash tabs, provided by the user through the
Save the image button on 23 September 2026 at 1920x1080: `abyss.png`,
`delirium.png`, `essences.png`, `ritual.png`.

Each keeps only the stash pixels, `frame[0:765, 0:655]` of the original client,
unmodified, so a test places it back at the origin. The tab bar is included
(coloured tabs, the tab of the capture selected); the side menu is not.

`readings.json` holds, per tab, the ground truth checked by eye against the
reference artwork, cell by cell, not copied from the recogniser:
- `read`: item and count of every cell read in full;
- `count_unreadable`: cells whose item is right but whose count cannot be read
  (`ES47`, `RI25` behind a Ritual emblem);
- `unnamed`: bright ghosts of empty cells, which must stay unidentified.
Every other cell is empty.

`icons/` holds the poe.ninja artwork of the Abyss, Delirium, Essences and Ritual
categories (192 images from web.poecdn.com; three idol images were unavailable
and are not needed). Tests add the Expedition fixture's icons as rivals.
Artwork belongs to Grinding Gear Games.
