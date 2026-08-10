"""Headless tests for the parts that do not need a display.

Run with:  python -m tests.test_core     (from the project root)
"""

import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from ghostread.document import (  # noqa: E402
    HALO_COLOUR, PdfDocument, PdfError, add_halo,
)

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("  ok   {}".format(name))
    else:
        FAILED.append(name)
        print("  FAIL {} {}".format(name, detail))


def make_pdf(path, pages=6, with_toc=True):
    doc = pymupdf.open()
    for number in range(pages):
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_text((72, 100), "Chapter {}".format(number + 1), fontsize=22)
        page.insert_text((72, 160), "Continuous random variables", fontsize=13)
        page.insert_text((72, 200), "page marker {}".format(number + 1), fontsize=11)
        if number == 3:
            page.insert_text((72, 260), "needle in a haystack", fontsize=11)
    if with_toc:
        doc.set_toc([[1, "Chapter {}".format(n + 1), n + 1] for n in range(pages)])
    doc.save(path)
    doc.close()


def run():
    tmpdir = tempfile.mkdtemp(prefix="ghostread-test-")
    pdf_path = os.path.join(tmpdir, "sample.pdf")
    make_pdf(pdf_path)

    os.environ["GHOSTREAD_HOME"] = os.path.join(tmpdir, "state")
    from ghostread import state as state_store

    print("\ndocument")
    doc = PdfDocument(pdf_path)
    check("opens the file", doc.page_count == 6, doc.page_count)
    check("reports a page size", doc.page_size(0)[0] == 595, doc.page_size(0))
    check("clamps below zero", doc.clamp(-5) == 0)
    check("clamps above the end", doc.clamp(99) == 5)

    print("\nrendering")
    image = doc.render(0, 1.0)
    check("renders to an image", image.width == 595 and image.height == 842,
          (image.width, image.height))
    zoom = doc.zoom_for_width(0, 800)
    wide = doc.render(0, zoom)
    check("fit to width honours the target", abs(wide.width - 800) <= 2, wide.width)
    fitted = doc.zoom_for_page(0, 800, 400)
    check("fit to page uses the tighter axis", abs(fitted - 400 / 842) < 1e-6, fitted)

    inverted = doc.render(0, 1.0, invert=True)
    check("invert changes the pixels",
          inverted.getpixel((5, 5)) != image.getpixel((5, 5)),
          (inverted.getpixel((5, 5)), image.getpixel((5, 5))))

    print("\ntext outline for ghost mode")
    # Ghost mode keys pure black out, so the outline has to be dark enough to
    # read as a shadow but never exactly the key colour, or it vanishes too.
    haloed = doc.render(0, 1.0, invert=True, halo=2)
    # tobytes on an "L" image is one byte per pixel, and unlike getdata it
    # behaves the same on every Pillow back to the 9.x floor in requirements.
    plain_l = list(inverted.convert("L").tobytes())
    halo_l = list(haloed.convert("L").tobytes())

    check("outline leaves the glyphs untouched",
          all(a == b for a, b in zip(plain_l, halo_l) if a > 40))
    check("outline never uses the key colour itself",
          all(value != 0 for value in HALO_COLOUR), HALO_COLOUR)
    check("outline covers more than the bare page did",
          sum(1 for v in halo_l if 1 <= v <= 20)
          > sum(1 for v in plain_l if 1 <= v <= 20))
    check("outline still leaves the margins transparent",
          min(halo_l) == 0)
    check("a wider outline covers more",
          sum(1 for v in doc.render(0, 1.0, invert=True, halo=3)
              .convert("L").tobytes() if 1 <= v <= 20)
          > sum(1 for v in halo_l if 1 <= v <= 20))
    check("outline is a no-op without invert",
          doc.render(1, 1.0, invert=False, halo=2)
          .tobytes() == doc.render(1, 1.0, invert=False).tobytes())
    check("halo=0 matches an un-outlined render",
          doc.render(0, 1.0, invert=True, halo=0) is inverted)
    check("add_halo declines a zero radius",
          add_halo(inverted, 0) is inverted)

    print("\ncache")
    first = doc.render(2, 1.0)
    second = doc.render(2, 1.0)
    check("cache returns the same object", first is second)
    small = PdfDocument(pdf_path, cache_size=2)
    for index in range(5):
        small.render(index, 1.0)
    check("cache is bounded", len(small._cache) <= 2, len(small._cache))
    small.close()

    print("\nsearch")
    hits = doc.search("needle in a haystack")
    check("finds the phrase", len(hits) == 1 and hits[0][0] == 3, hits)
    check("returns rectangles", len(hits[0][1]) >= 1 and len(hits[0][1][0]) == 4)
    common = doc.search("Continuous random variables")
    check("finds it on every page", len(common) == 6, len(common))
    ordered = doc.search("Continuous random variables", start=4)
    check("search starts at the current page and wraps",
          [p for p, _ in ordered] == [4, 5, 0, 1, 2, 3], [p for p, _ in ordered])
    check("empty query returns nothing", doc.search("   ") == [])
    check("missing text returns nothing", doc.search("zzz-not-here") == [])

    print("\noutline")
    toc = doc.toc()
    check("reads the outline", len(toc) == 6, len(toc))
    check("outline pages are zero based", toc[0][2] == 0, toc[0])

    print("\nerrors")
    try:
        PdfDocument(os.path.join(tmpdir, "nope.pdf"))
        check("missing file raises PdfError", False)
    except PdfError:
        check("missing file raises PdfError", True)
    except Exception as exc:
        check("missing file raises PdfError", False, type(exc).__name__)

    protected = os.path.join(tmpdir, "locked.pdf")
    source = pymupdf.open()
    source.new_page()
    source.save(protected, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner", user_pw="secret")
    source.close()
    try:
        PdfDocument(protected)
        check("locked file without a password raises", False)
    except PdfError:
        check("locked file without a password raises", True)
    unlocked = PdfDocument(protected, password="secret")
    check("locked file opens with the password", unlocked.page_count == 1)
    unlocked.close()

    print("\nstate")
    state_store.save(pdf_path, {"page": 42, "opacity": 0.6, "invert": True})
    loaded = state_store.load(pdf_path)
    check("saves and loads the page", loaded["page"] == 42, loaded)
    check("saves opacity", abs(loaded["opacity"] - 0.6) < 1e-9)
    check("fills in defaults", loaded["fit"] == "width", loaded["fit"])
    fresh = state_store.load(os.path.join(tmpdir, "never-opened.pdf"))
    check("unknown file falls back to defaults", fresh["page"] == 0)
    check("recent list includes the file",
          pdf_path in [os.path.realpath(p) for p in state_store.recent()]
          or str(Path(pdf_path).resolve()) in state_store.recent(),
          state_store.recent())

    with open(state_store.state_path(), "w") as handle:
        handle.write("{ this is not json")
    check("corrupt state file does not crash",
          state_store.load(pdf_path)["page"] == 0)

    print("\ncli")
    from ghostread.cli import build_parser
    parser = build_parser()
    opts = parser.parse_args(["book.pdf", "-o", "0.65", "-p", "213", "--invert"])
    check("parses arguments", opts.pdf == "book.pdf" and opts.page == 213
          and abs(opts.opacity - 0.65) < 1e-9 and opts.invert is True, vars(opts))
    bare = parser.parse_args([])
    check("pdf argument is optional", bare.pdf is None)
    try:
        parser.parse_args(["book.pdf", "-o", "5"])
        check("rejects a silly opacity", False)
    except SystemExit:
        check("rejects a silly opacity", True)

    doc.close()

    print("\n{} passed, {} failed".format(len(PASSED), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
