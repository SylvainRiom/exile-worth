Real capture of the Breach stash tab, Catalysts view, provided by the user through
the Save the image button on 23 September 2026 at 1920x1080.

`catalysts.png` keeps only the stash pixels, `frame[0:765, 0:655]` of the
original client, unmodified, so a test places it back at the origin. It holds
the tab bar (BREACH selected, red; several other tabs coloured green) and all 29
cells of the view.

`readings.json` is the ground truth: 13 filled cells, item and count. It was
checked by eye against the reference artwork, cell by cell, not copied from the
recogniser's output. The other 16 cells are empty; `B02` is the Breachlord Sac
ghost, which the emptiness filter does not yet accept as empty.

`icons/` holds the 29 Breach reference images from web.poecdn.com, as listed by
PoE2DB, plus `carved-mischief.png`: a dark, sparse Ritual icon that used to match
the empty ghosts of refined catalysts at 0.92 and above. Tests add the Expedition
fixture's icons so the matcher has rivals.

No refined catalyst is present, and the Wombgifts view is not captured: this
validates the normal catalysts, the splinters and the geometry, not the rest.
Artwork belongs to Grinding Gear Games.
