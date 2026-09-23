"""Draws the application icon: a golden orb in one cell of a 2x2 stash grid.

Original artwork in the dashboard's colours, not the game's Divine Orb. Writes
`exile_worth/assets/app.ico` (16 to 256 px) and `app.png` (256 px).

    .\\.venv311\\Scripts\\python.exe tools\\make_app_icon.py

Below 32 px the grid would blur into noise, so the small sizes show the orb alone
on the same background.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / 'exile_worth' / 'assets'
CANVAS = 1024
BACKGROUND = (16, 21, 30)
CELL = (25, 35, 50)
CELL_EDGE = (48, 65, 87)
MINT = (126, 226, 192)
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def rounded_square(size, radius, fill, outline=None, width=0):
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, size - 1, size - 1), radius, fill=fill,
                                            outline=outline, width=width)
    return image


def orb(diameter):
    """A lit golden sphere: radial gradient, a rim, a specular highlight."""
    scale = 4
    big = diameter * scale
    sphere = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    pixels = sphere.load()
    cx, cy = big * 0.40, big * 0.36  # light from the top left
    radius = big / 2
    stops = [(0.0, (255, 246, 214)), (0.25, (255, 214, 110)), (0.62, (226, 158, 42)),
             (0.88, (150, 88, 18)), (1.0, (92, 50, 10))]
    for y in range(big):
        for x in range(big):
            dx, dy = x - radius, y - radius
            if dx * dx + dy * dy > radius * radius:
                continue
            t = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / (radius * 1.25))
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t <= t1:
                    k = (t - t0) / (t1 - t0)
                    pixels[x, y] = tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)) + (255,)
                    break
    draw = ImageDraw.Draw(sphere)
    # Thin mint rim on the shadow side ties the orb to the interface accent.
    draw.arc((big * 0.03, big * 0.03, big * 0.97, big * 0.97), 20, 150, fill=MINT + (170,),
             width=max(2, big // 45))
    highlight = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(highlight).ellipse((big * 0.24, big * 0.17, big * 0.46, big * 0.33),
                                      fill=(255, 255, 245, 210))
    sphere = Image.alpha_composite(sphere, highlight.filter(ImageFilter.GaussianBlur(big / 40)))
    return sphere.resize((diameter, diameter), Image.LANCZOS)


def glow(size, centre, radius, colour, strength):
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    x, y = centre
    ImageDraw.Draw(layer).ellipse((x - radius, y - radius, x + radius, y + radius),
                                  fill=colour + (strength,))
    return layer.filter(ImageFilter.GaussianBlur(radius / 2.2))


def clip_to(image, mask_source):
    alpha = ImageChops.multiply(image.getchannel('A'), mask_source.getchannel('A'))
    image.putalpha(alpha)
    return image


def full_icon():
    size = CANVAS
    base = rounded_square(size, size * 0.22, BACKGROUND + (255,), CELL_EDGE + (255,), size // 64)
    margin, gap = size * 0.15, size * 0.06
    cell = (size - 2 * margin - gap) / 2
    draw = ImageDraw.Draw(base)
    boxes = []
    for row in range(2):
        for column in range(2):
            x0, y0 = margin + column * (cell + gap), margin + row * (cell + gap)
            boxes.append((x0, y0, x0 + cell, y0 + cell))
            draw.rounded_rectangle(boxes[-1], cell * 0.14, fill=CELL + (255,),
                                   outline=CELL_EDGE + (255,), width=size // 90)
    # The orb sits in the bottom-right cell and lights it.
    x0, y0, x1, y1 = boxes[3]
    centre = ((x0 + x1) / 2, (y0 + y1) / 2)
    draw.rounded_rectangle(boxes[3], cell * 0.14, outline=(214, 160, 60, 255), width=size // 70)
    base = Image.alpha_composite(base, glow(size, centre, cell * 0.62, (255, 190, 70), 150))
    diameter = int(cell * 0.80)
    base.alpha_composite(orb(diameter), (int(centre[0] - diameter / 2), int(centre[1] - diameter / 2)))
    # A faint mint dot in the opposite cell: the rest of the stash, still counted.
    cx, cy = (boxes[0][0] + boxes[0][2]) / 2, (boxes[0][1] + boxes[0][3]) / 2
    dot = cell * 0.10
    ImageDraw.Draw(base).ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=MINT + (110,))
    return clip_to(base, rounded_square(size, size * 0.22, (255, 255, 255, 255)))


def small_icon():
    size = CANVAS
    base = rounded_square(size, size * 0.22, BACKGROUND + (255,), CELL_EDGE + (255,), size // 40)
    centre = (size / 2, size / 2)
    base = Image.alpha_composite(base, glow(size, centre, size * 0.40, (255, 190, 70), 120))
    diameter = int(size * 0.70)
    base.alpha_composite(orb(diameter), (int(centre[0] - diameter / 2), int(centre[1] - diameter / 2)))
    return clip_to(base, rounded_square(size, size * 0.22, (255, 255, 255, 255)))


def main():
    full, small = full_icon(), small_icon()
    frames = [(small if size < 32 else full).resize((size, size), Image.LANCZOS) for size in SIZES]
    ASSETS.mkdir(parents=True, exist_ok=True)
    frames[-1].save(ASSETS / 'app.png')
    # Pillow writes each requested size from the first image; give it the frames.
    frames[-1].save(ASSETS / 'app.ico', format='ICO', sizes=[(s, s) for s in SIZES],
                    append_images=frames[:-1])
    print('wrote', ASSETS / 'app.ico', ASSETS / 'app.png')


if __name__ == '__main__':
    main()
