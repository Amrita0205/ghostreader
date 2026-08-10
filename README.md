# GhostRead

[![tests](https://github.com/Amrita0205/ghostread/actions/workflows/ci.yml/badge.svg)](https://github.com/Amrita0205/ghostread/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ghostread)](https://pypi.org/project/ghostread/)
[![licence: MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)

A translucent, always on top PDF reader. Built for reading while something else
is running: the page floats over your terminal at whatever opacity you set, so a
training run stays visible behind the textbook.

Nothing off the shelf did this on Windows. Glassy PDF is macOS only, WindowTop is
closed source and paid, and the overlay tools on GitHub only draw blank rectangles.

## Install

**Windows, the easy way.** Download **[GhostRead.exe][latest]** from the latest
release and double click it. No Python, no install, no setup step. Keep it
wherever you like, or drag a PDF onto it to open that book.

Windows SmartScreen will warn you the first time, because the file is not code
signed (a signing certificate costs a few hundred a year, which this does not
justify). Click *More info*, then *Run anyway*. If you would rather not trust a
binary from a stranger, every release is built by GitHub Actions straight from
the tagged source in this repo, and you can read the whole thing in an afternoon.

[latest]: https://github.com/Amrita0205/ghostread/releases/latest

**With pip**, if you already have Python 3.9 or newer and want the `ghostread`
command on your PATH:

```
pip install ghostread
ghostread book.pdf
```

**From source**, no install:

```
run.bat                                       Windows, opens a file picker
run.bat "C:\Users\you\Downloads\book.pdf"     or drag a PDF onto run.bat
./run.sh path/to/book.pdf                     Linux and macOS
```

The first `run.bat` builds a virtual environment in the folder and installs the
two dependencies, which takes about a minute. Every run after that is instant.

## Command line

```
ghostread [PDF] [options]

  -o, --opacity 0.65     window opacity, 0.15 to 1.0 (default 0.8)
  -p, --page 213         open on a page, 1 based
  -z, --zoom 1.4         fixed zoom, overrides fit mode
      --fit width|page   fit to window width, or the whole page
      --geometry 720x1000+1100+40
      --invert           invert colours, much easier over a dark editor
      --framed           keep the normal title bar
      --no-topmost       do not force it to stay on top
      --no-remember      do not save or restore page and position
      --password PW      for a protected PDF
      --recent           list what you had open before
```

With no arguments it opens a file picker.

Typical setup for reading while a job runs on the right half of the screen:

```
ghostread book.pdf --opacity 0.7 --invert --geometry 700x1000+40+40
```

## Using it

Everything lives on the bottom bar, and every button has a hover tooltip, so
nothing needs memorising:

- arrows and a page box: turn pages, or type a page number and press Enter
- zoom buttons and a `fit` button
- a **see through** slider: drag it, or click anywhere on the bar to jump
  straight to that level
- toggle buttons for invert, ghost mode, keep on top and click through, which
  stay lit while they are active
- `find` and `toc` for search and the chapter list
- the three dot button (or a right click anywhere) opens the full menu, with
  Open, Recent files, opacity presets and everything else

Drag the top bar to move the window, the `///` corner to resize, and double
click the top bar to roll the window up to just its bar. You can open another
PDF from the menu without restarting, and the Recent list remembers the last
ten.

Keyboard shortcuts still exist for all of it, listed under `F1`.

## The three features worth knowing about

**Invert (`i`).** A white page at 70% opacity over a dark terminal turns into grey
mush. Inverted, it becomes light text on dark, which stays readable much further
down the opacity scale. Try `--invert --opacity 0.6`.

**Ghost mode (the sparkle button, Windows only).** The strongest trick in the
app. Instead of fading the whole window, Windows keys out one exact colour and
makes it fully transparent while everything else stays completely opaque. The
page is inverted, its now-black background is keyed out, and what is left is
sharp light text floating directly over your terminal with no washing out at
all, because the glyphs are never blended. Clicks pass through the empty parts
for free. Press the sparkle button again to get the normal page back.

**Click through (`c`, Windows only).** Mouse clicks pass straight through the
overlay to whatever is underneath, so you can keep typing in your editor without
moving the page out of the way. Since you can no longer click the window to switch
it off, `Ctrl+Alt+G` is registered as a global hotkey to bring it back. If that
hotkey cannot be claimed, click through refuses to turn on rather than trapping you.

## Where it stores things

Page, zoom, opacity and window position are saved per document in
`~/.ghostread/state.json`, so reopening a book drops you back where you were. Set
`GHOSTREAD_HOME` to move that folder, or pass `--no-remember` to skip it.

## What changed in 1.1

- Full mouse driven control bar with tooltips; the keyboard is now optional
- Help and contents windows are fully opaque, so the page can no longer bleed
  through and make them unreadable
- Ghost mode
- Open and Recent in the menu, so switching books does not need a restart
- The contents list opens scrolled to the chapter you are in
- Clicking the opacity bar jumps to that value instead of stepping by one

## Layout

```
ghostread/
  document.py   PDF loading, rendering, search, outline. No GUI code.
  state.py      per document page and geometry memory
  app.py        the Tk overlay window
  winext.py     Windows click through and global hotkey via ctypes
  cli.py        argument parsing
tests/
  test_core.py  headless: rendering, search, cache, state, CLI
  test_gui.py   drives the real window under a virtual display
packaging/
  launcher.py   entry point for the frozen build
  ghostread.spec PyInstaller recipe for GhostRead.exe
```

`document.py` has no GUI imports on purpose, so rendering and search can be
debugged without a display.

## Running the tests

```
python -m tests.test_core
python -m tests.test_gui          # needs a display
xvfb-run -a python -m tests.test_gui   # or a virtual one on Linux
```

## Troubleshooting

**"tkinter is missing"** On Windows, reinstall Python from python.org and tick
"tcl/tk and IDLE". On Ubuntu, `sudo apt install python3-tk`.

**The window is blurry on a high DPI screen.** It should not be, DPI awareness is
set at startup, but if it is, run with `--framed` and report what you see.

**I lost the window.** It is always on top by default, so it should be visible. If
you pressed `t` and it went behind something, close it from the terminal with
`Ctrl+C` and reopen. Your page is saved.

**It opens tiny or off screen.** Pass `--geometry 760x900+60+60` once. The new
position is remembered.

**Anti-virus flags it.** It is plain Python source, nothing is compiled or bundled.
Read `winext.py` if you want to check the ctypes calls, it is the only file that
touches the Windows API and it is under 150 lines.

## Notes

- PyMuPDF also opens epub, xps, cbz and fb2, so those work too even though the
  name says PDF.
- Rendering is roughly 3 to 10 ms per page, and the next page is pre-rendered on a
  background thread. Ten rendered pages are cached, about 27 MB at fit width.
- Full text search across a 636 page book takes around 0.2 seconds.
- `GhostRead.exe` is built without a console window, so it takes the same flags
  but cannot print back to you. `--recent`, which only prints, needs the pip
  install or the source checkout.

## Contributing

Bug reports welcome, especially about window behaviour on setups I cannot test.
[CONTRIBUTING.md](CONTRIBUTING.md) covers the layout and how to run the tests.

## Licence

GhostRead is MIT licensed. See [LICENSE](LICENSE).

One caveat worth stating plainly: the prebuilt `GhostRead.exe` bundles PyMuPDF,
which is AGPL-3.0, so that **binary** is distributed under the AGPL even though
the source here is MIT. Practically this means anyone you give the exe to is
entitled to the source, which this repository provides.
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) has the details, including how
to swap in a permissive renderer if you need a build without that obligation.
