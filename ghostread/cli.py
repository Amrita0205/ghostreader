"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from . import state as state_store

DESCRIPTION = """\
GhostRead: a translucent, always on top PDF reader.

Made for reading while something else is running. The window floats over your
terminal or editor at whatever opacity you set, so a training run stays visible
behind the page you are reading.
"""

EPILOG = """\
examples:
  ghostread book.pdf
  ghostread book.pdf --opacity 0.65 --page 213
  ghostread book.pdf --invert --geometry 720x1000+1100+40
  ghostread                       (opens a file picker)
  ghostread --recent              (lists what you had open before)

Press F1 inside the window for the full key list.
"""


def opacity_type(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("opacity must be a number")
    if not 0.15 <= number <= 1.0:
        raise argparse.ArgumentTypeError("opacity must be between 0.15 and 1.0")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ghostread",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pdf", nargs="?", help="path to the PDF (omit for a picker)")
    parser.add_argument("-o", "--opacity", type=opacity_type,
                        help="window opacity, 0.15 to 1.0 (default 0.8)")
    parser.add_argument("-p", "--page", type=int,
                        help="page to open on, 1 based")
    parser.add_argument("-z", "--zoom", type=float,
                        help="fixed zoom factor, overrides fit mode")
    parser.add_argument("--fit", choices=["width", "page"],
                        help="fit the page to window width or to the whole window")
    parser.add_argument("--geometry",
                        help="window size and position, e.g. 720x1000+1100+40")
    parser.add_argument("--invert", action="store_true",
                        help="invert colours, easier to read over a dark editor")
    parser.add_argument("--framed", action="store_true",
                        help="keep the normal OS title bar instead of a bare window")
    parser.add_argument("--no-topmost", action="store_true",
                        help="do not force the window to stay on top")
    parser.add_argument("--no-remember", action="store_true",
                        help="do not save or restore page, zoom and position")
    parser.add_argument("--password", help="password for a protected PDF")
    parser.add_argument("--recent", action="store_true",
                        help="print recently opened files and exit")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    opts = parser.parse_args(argv)

    if opts.recent:
        files = state_store.recent()
        if not files:
            print("Nothing opened yet.")
        for path in files:
            print(path)
        return 0

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print(
            "ghostread: tkinter is missing.\n"
            "  Windows/macOS: reinstall Python from python.org and tick tcl/tk\n"
            "  Debian/Ubuntu: sudo apt install python3-tk\n"
            "  Fedora:        sudo dnf install python3-tkinter",
            file=sys.stderr,
        )
        return 3

    from .app import run

    return run(opts)


if __name__ == "__main__":
    sys.exit(main())
