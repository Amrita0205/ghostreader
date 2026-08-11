"""Draw the application icon.

Kept as code rather than a binary blob so the icon can be adjusted without a
drawing program, and so anyone can see how it was made.

    python packaging/make_icon.py

Writes assets/ghostread.ico with every size Windows asks for. The design is a
page that fades out towards the bottom, which is the one idea the whole app is
about: a document you can see through.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# Supersample, then shrink. Far cheaper than trying to draw anti aliased edges.
S = 1024

BG = (22, 22, 29, 255)        # the dark chip the page sits on
PAGE = (245, 246, 252, 255)   # paper
ACCENT = (122, 162, 247, 255)  # the same blue the app uses for its controls

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def draw() -> Image.Image:
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_on = ImageDraw.Draw(icon)

    # Rounded chip, so the icon still reads as one object at 16 pixels rather
    # than a pale rectangle floating on nothing.
    draw_on.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22),
                              fill=BG)

    page_box = [S * 0.24, S * 0.15, S * 0.76, S * 0.85]

    # The page, on its own layer so it can be faded independently.
    page = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    page_draw = ImageDraw.Draw(page)
    page_draw.rounded_rectangle(page_box, radius=int(S * 0.035), fill=PAGE)

    # Lines of text. Short last line, so it reads as prose and not a barcode.
    left, top = page_box[0] + S * 0.06, page_box[1] + S * 0.13
    width = (page_box[2] - page_box[0]) - S * 0.12
    for row in range(5):
        y = top + row * S * 0.105
        run = width * (0.55 if row == 4 else 1.0)
        page_draw.rounded_rectangle(
            [left, y, left + run, y + S * 0.038],
            radius=int(S * 0.019), fill=ACCENT if row == 0 else BG)

    # The whole point: transparent at the bottom, solid at the top.
    fade = Image.new("L", (S, S), 255)
    fade_draw = ImageDraw.Draw(fade)
    span_top, span_bottom = S * 0.44, S * 0.86
    for y in range(int(span_top), S):
        ratio = min(1.0, (y - span_top) / (span_bottom - span_top))
        fade_draw.line([(0, y), (S, y)], fill=int(255 * (1.0 - ratio) ** 1.25))

    # Fade the page out by multiplying its own alpha with the gradient.
    page.putalpha(_multiply(page.getchannel("A"), fade))

    icon.alpha_composite(page)

    # A soft glow underneath sells "floating over something" at large sizes and
    # disappears harmlessly at small ones.
    glow = icon.filter(ImageFilter.GaussianBlur(S * 0.02))
    return Image.alpha_composite(glow, icon)


def _multiply(a: Image.Image, b: Image.Image) -> Image.Image:
    return Image.frombytes(
        "L", a.size,
        bytes((x * y) // 255 for x, y in zip(a.tobytes(), b.tobytes())),
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    assets.mkdir(exist_ok=True)

    art = draw()
    target = assets / "ghostread.ico"
    art.resize((256, 256), Image.LANCZOS).save(
        target, sizes=[(n, n) for n in SIZES])
    art.resize((512, 512), Image.LANCZOS).save(assets / "ghostread.png")
    print("wrote {} and {}".format(target, assets / "ghostread.png"))


if __name__ == "__main__":
    main()
