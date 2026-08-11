# GhostRead — a transparent, always on top PDF reader for Windows

[![tests](https://github.com/Amrita0205/ghostreader/actions/workflows/ci.yml/badge.svg)](https://github.com/Amrita0205/ghostreader/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ghostread)](https://pypi.org/project/ghostread/)
[![licence: MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-download%20the%20exe-0078D6?logo=windows)](https://github.com/Amrita0205/ghostreader/releases/latest)

GhostRead is a free and open source PDF reader that stays on top of every other
window and lets you see straight through it. It is built for reading while
something else is running: the page floats over your terminal or editor at
whatever opacity you set, so a training run stays visible behind the textbook.

Nothing off the shelf did this on Windows. Glassy PDF is macOS only, WindowTop is
closed source and paid, and the overlay tools on GitHub only draw blank
rectangles. So GhostRead is a free alternative to both, in under 2,000 lines of
Python you can read in an afternoon.

It also runs on Linux and macOS, minus the two features that need the Windows
compositor: click through and ghost mode.

## Install

**Windows, the easy way.** Download **[GhostRead.exe][latest]** from the latest
release and double click it. No Python, no install, no setup step. Keep it
wherever you like, or drag a PDF onto it to open that book.

Windows SmartScreen will warn you the first time, because the file is not code
signed (a signing certificate costs a few hundred a year, which this does not
justify). Click *More info*, then *Run anyway*. If you would rather not trust a
binary from a stranger, every release is built by GitHub Actions straight from
the tagged source in this repo, and you can read the whole thing in an afternoon.

[latest]: https://github.com/Amrita0205/ghostreader/releases/latest

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

Light text over a *light* window is the one case that does not work on its own,
because the glyphs disappear into it and all you see is their dark edges. So the
text is outlined: the glyphs are grown outward by a couple of pixels and that
ring is painted near black, which reads like a subtitle and stays opaque while
everything further out stays invisible. Press `e` to step the outline through
off, thin and heavier. Two pixels is the default and suits most backgrounds; go
wider over something busy like a chart or a video.

**Click through (`c`, Windows only).** Mouse clicks pass straight through the
overlay to whatever is underneath, so you can keep typing in your editor without
moving the page out of the way.

The catch is that the page stops taking the mouse *completely*, including the
button that would turn the mode back off. So switching it on puts a small
**turn it off** panel on screen. That panel is a separate window and is never
made click through, so it keeps working after the page has stopped; drag it
somewhere else if it covers something you need. A global hotkey does the same
job, and the panel tells you which one was claimed, because the first choice of
`Ctrl+Alt+G` can already be taken by another application or by a second copy of
GhostRead. If no hotkey at all is free, click through refuses to turn on rather
than trapping you.

## Where it stores things

Page, zoom, opacity and window position are saved per document in
`~/.ghostread/state.json`, so reopening a book drops you back where you were. Set
`GHOSTREAD_HOME` to move that folder, or pass `--no-remember` to skip it.

## What changed in 1.2.1

- An actual application icon, on the exe and on the window
- `packaging/make_icon.py` draws it, so it can be changed without a drawing
  program

## What changed in 1.2

- Ghost mode outlines the text, so it stays readable over a light or busy
  window instead of dissolving into it. `e` cycles the outline width.
- Click through no longer strands you: a small draggable **turn it off** panel
  stays on screen and keeps working after the page has stopped taking the
  mouse. The escape hotkey falls back through several combinations if the
  first is already taken, and the panel names the one it actually claimed.
- Moving the window in ghost mode no longer leaves a stale copy of it painted
  on the desktop.
- Fixed a hotkey poll that discarded messages Tk needed, and could spin at
  100% CPU once the window had anything left to repaint.
- Click through now commits its window style properly, which is why it had
  been intermittent.

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

## Questions people ask

**Does it work on Windows 11?** Yes, and on Windows 10. That is the setup it was
built on and the one the release binary is tested against.

**Do I need Python?** Not for the `.exe`. Everything is bundled inside it. You
only need Python if you install with `pip` or run from source.

**Can I read a PDF while coding without alt-tabbing?** That is the whole point.
Turn on click through (`c`) and the window stops accepting mouse input entirely,
so you type into your editor with the page still sitting on top of it.

**How do I make a PDF transparent on Windows?** Open it in GhostRead and drag the
*see through* slider, or start with `--opacity 0.65`. If the page washes out
against a dark background, add `--invert`, and if you want text that stays fully
sharp at any opacity, use ghost mode.

**The text is hard to read against what is behind it.** Plain opacity cannot fix
this: it blends the page and the background equally, so fading one fades the
other. Use ghost mode instead, which keeps the glyphs at full strength and makes
only the background disappear, and press `e` for a heavier outline if the window
behind is light or busy.

**Is it really free?** Yes, MIT licensed, no telemetry, no account, no paid tier.
See [Licence](#licence) for the one caveat about the bundled binary.

**Does it work on Linux or macOS?** The reader does. Click through and ghost mode
do not, because both are implemented with Windows compositor calls.

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
