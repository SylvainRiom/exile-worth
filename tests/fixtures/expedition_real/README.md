Real capture provided by the user on 20 September 2026 through the Save the image
button. `stash.png` keeps only the stash pixels (645x765), without gear, inventory,
minimap or the rest of the desktop. The stash pixels are unmodified. The
coordinates match the original 1920x1080 client.

`items.json` is the catalogue the application was using when the failure was
reported. `selection.png` keeps only the selected row of the side menu, to check
that its arrow and title confirm the active tab in the top bar. `icons/` holds its
99 CDN references so the comparisons can be reproduced offline, including the
wrong contenders. The URLs are in `items.json`. Artwork belongs to Grinding Gear
Games.

The test checks the 25 visible stacks and their counters, including the
approximate 38.3K. The 7 dark cells stay unknown, with no invented zero quantity.
The sagas use the recognised image and then their fixed position to resolve the
ambiguity. This validation concerns this capture and this resolution, not every
interface scale.
