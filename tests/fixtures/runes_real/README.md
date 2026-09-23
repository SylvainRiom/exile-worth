Real captures of the Runes stash tab, provided by the user through the Save the
image button. One file per view: `runes.png`, `kalguuran.png`, `soul_cores.png`,
`idols.png`, `ancient_augments.png`.

Each file keeps only the stash pixels, `frame[0:765, 0:655]` of the original
1920x1080 client, without gear, inventory, minimap or the rest of the desktop.
The pixels are unmodified and the coordinates match the original client, so a
test places the crop back at the origin before reading it. That window holds
every one of the five grids: the widest reaches x=631, the lowest y=738.

`runes.png` is the 21 September 2026 capture, previously named `stash.png`; the
crop is pixel-identical, so its recorded margins carry over unchanged. The other
four were captured in a single session on 22 September 2026 and replace the chat
screenshots the four geometries had been measured from until then.

The tests check that each capture is recognised as its own view, that the
declared cells land on the real borders within 3 px, and that the view selector
above the grid lights the visible view. Cell counts are 70, 60, 47, 31 and 17.
Artwork belongs to Grinding Gear Games.

This validation concerns these captures and this resolution, not every interface
scale. No capture carries an item catalogue: these files validate geometry and
view selection, not icon identification.
