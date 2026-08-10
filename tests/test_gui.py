"""Drives the real Tk window under a virtual display.

This catches the mistakes unit tests cannot: widget names, pack order, bad
option values, and exceptions inside callbacks.

Run with:  xvfb-run -a python -m tests.test_gui
"""

import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_core import make_pdf  # noqa: E402

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("  ok   {}".format(name))
    else:
        FAILED.append(name)
        print("  FAIL {} {}".format(name, detail))


def attempt(name, function):
    """Call something and record whether it blew up."""
    try:
        function()
        check(name, True)
    except Exception as exc:
        check(name, False, "{}: {}".format(type(exc).__name__, exc))
        traceback.print_exc()


def run():
    import tkinter as tk
    from ghostread.app import GhostReader
    from ghostread.cli import build_parser
    from ghostread.document import PdfDocument

    tmpdir = tempfile.mkdtemp(prefix="ghostread-gui-")
    pdf_path = os.path.join(tmpdir, "sample.pdf")
    make_pdf(pdf_path, pages=8)
    os.environ["GHOSTREAD_HOME"] = os.path.join(tmpdir, "state")

    opts = build_parser().parse_args([pdf_path])
    doc = PdfDocument(pdf_path)

    root = tk.Tk()
    reader = GhostReader(root, doc, opts, {"page": 0, "opacity": 0.8, "fit": "width"})

    def pump(cycles=6):
        for _ in range(cycles):
            root.update()

    root.geometry("700x900+0+0")
    pump(10)

    print("\nstartup")
    attempt("first render runs", lambda: reader.render(anchor="top"))
    check("a page image exists", reader.photo is not None)
    check("scrollregion is set", root.nametowidget(reader.canvas).cget("scrollregion")
          not in ("", None), reader.canvas.cget("scrollregion"))
    check("status bar shows the page", "1/8" in reader.status.cget("text"),
          reader.status.cget("text"))

    print("\nnavigation")
    attempt("next page", reader.next_page)
    pump()
    check("page advanced", reader.page == 1, reader.page)
    attempt("previous page", reader.prev_page)
    pump()
    check("page went back", reader.page == 0, reader.page)
    attempt("jump to the end", lambda: reader.goto(999))
    pump()
    check("clamped to the last page", reader.page == 7, reader.page)
    attempt("previous page at the start does not crash", reader.prev_page)
    pump()
    attempt("go home", lambda: reader.goto(0))
    pump()
    attempt("previous page at page one is a no-op", reader.prev_page)
    check("still on page one", reader.page == 0, reader.page)

    print("\nscrolling rolls between pages")
    reader.goto(0)
    pump()
    reader.canvas.yview_moveto(1.0)
    pump()
    attempt("scrolling past the bottom", lambda: reader.scroll_by(1))
    pump()
    check("rolled into the next page", reader.page == 1, reader.page)
    reader.canvas.yview_moveto(0.0)
    pump()
    attempt("scrolling above the top", lambda: reader.scroll_by(-1))
    pump()
    check("rolled back a page", reader.page == 0, reader.page)

    print("\nzoom and fit")
    before = reader.current_zoom
    attempt("zoom in", lambda: reader.zoom_by(1.5))
    pump()
    check("zoom increased", reader.current_zoom > before,
          (before, reader.current_zoom))
    check("fit mode released", reader.fit == "free", reader.fit)
    attempt("fit width", lambda: reader.set_fit("width"))
    pump()
    attempt("fit page", lambda: reader.set_fit("page"))
    pump()
    check("fit page is not taller than the window",
          reader.photo.height() <= reader.canvas.winfo_height() + 4,
          (reader.photo.height(), reader.canvas.winfo_height()))

    print("\nopacity")
    attempt("less opaque", lambda: reader.nudge_opacity(-0.2))
    check("opacity dropped", abs(reader.opacity - 0.6) < 1e-6, reader.opacity)
    for _ in range(30):
        reader.nudge_opacity(-0.05)
    check("opacity never reaches invisible", reader.opacity >= 0.15, reader.opacity)
    for _ in range(30):
        reader.nudge_opacity(0.05)
    check("opacity never exceeds solid", reader.opacity <= 1.0, reader.opacity)

    print("\ntoggles")
    attempt("invert on", reader.toggle_invert)
    pump()
    check("invert flag set", reader.invert is True)
    attempt("invert off", reader.toggle_invert)
    pump()
    attempt("always on top toggles", reader.toggle_topmost)
    attempt("click through is refused off Windows", reader.toggle_click_through)
    check("click through stayed off", reader.click_through is False)
    attempt("roll up", reader.toggle_roll)
    pump()
    check("window rolled up", reader.rolled_up is True)
    attempt("roll down", reader.toggle_roll)
    pump()
    check("window restored", reader.rolled_up is False)

    print("\nsearch")
    attempt("search for a phrase", lambda: reader.run_search("needle in a haystack"))
    pump()
    check("jumped to the match", reader.page == 3, reader.page)
    check("recorded the hit", len(reader.hits) == 1, reader.hits)
    attempt("search with many hits",
            lambda: reader.run_search("Continuous random variables"))
    pump()
    check("found every page", len(reader.hits) == 8, len(reader.hits))
    start = reader.page
    attempt("next hit", reader.next_hit)
    pump()
    check("moved to another hit", reader.page != start, (start, reader.page))
    attempt("search with no match", lambda: reader.run_search("zzz-nothing"))
    pump()
    attempt("highlights redraw on re-render", lambda: reader.render(anchor="keep"))

    print("\nprompt")
    attempt("open goto prompt", lambda: reader.open_prompt("goto"))
    pump()
    reader.prompt_entry.delete(0, "end")
    reader.prompt_entry.insert(0, "5")
    attempt("submit page number", reader._submit_prompt)
    pump()
    check("went to the typed page", reader.page == 4, reader.page)
    attempt("open search prompt", lambda: reader.open_prompt("search"))
    reader.prompt_entry.delete(0, "end")
    reader.prompt_entry.insert(0, "not a number")
    attempt("garbage in the goto box is handled", lambda: (
        reader.open_prompt("goto"),
        reader.prompt_entry.delete(0, "end"),
        reader.prompt_entry.insert(0, "banana"),
        reader._submit_prompt(),
    ))
    pump()
    check("page unchanged after bad input", reader.page == 4, reader.page)
    attempt("escape closes the prompt", reader.close_prompt)

    # Regression: pressing Enter in the prompt used to submit and then also
    # fire the global "find next" binding, jumping away from the page you
    # just asked for. Drive it with a real key event, not a direct call.
    reader.run_search("Continuous random variables")
    pump()
    reader.open_prompt("goto")
    pump()
    reader.prompt_entry.delete(0, "end")
    reader.prompt_entry.insert(0, "2")
    reader.prompt_entry.focus_set()
    pump()
    reader.prompt_entry.event_generate("<Return>")
    pump(10)
    check("Enter in the goto box lands on that page and stays",
          reader.page == 1, reader.page)

    print("\npopups")
    attempt("help window opens", reader.show_help)
    pump()
    attempt("outline window opens", reader.show_outline)
    pump()
    for child in root.winfo_children():
        if isinstance(child, tk.Toplevel):
            child.destroy()
    pump()

    print("\nkeyboard")

    class FakeEvent:
        def __init__(self, keysym="", char="", state=0, delta=0):
            self.keysym = keysym
            self.char = char
            self.state = state
            self.delta = delta

    reader.goto(0)
    pump()
    attempt("n key", lambda: reader._on_key(FakeEvent(keysym="n", char="n")))
    pump()
    check("n advanced the page", reader.page == 1, reader.page)
    attempt("p key", lambda: reader._on_key(FakeEvent(keysym="p", char="p")))
    pump()
    attempt("plus key", lambda: reader._on_key(FakeEvent(keysym="plus", char="+")))
    attempt("minus key", lambda: reader._on_key(FakeEvent(keysym="minus", char="-")))
    attempt("bracket keys", lambda: (
        reader._on_key(FakeEvent(keysym="bracketleft", char="[")),
        reader._on_key(FakeEvent(keysym="bracketright", char="]")),
    ))
    attempt("zero key fits width", lambda: reader._on_key(FakeEvent(keysym="0", char="0")))
    check("fit is width again", reader.fit == "width", reader.fit)
    attempt("unbound key is ignored",
            lambda: reader._on_key(FakeEvent(keysym="z", char="z")))
    attempt("wheel scroll", lambda: reader._on_wheel(FakeEvent(delta=120)))
    attempt("ctrl wheel zooms", lambda: reader._on_wheel(FakeEvent(delta=120, state=0x0004)))
    pump()

    print("\ndrag and resize")
    attempt("drag the bar", lambda: (
        reader._drag_start(FakeDrag(100, 100)),
        reader._drag_move(FakeDrag(140, 130)),
    ))
    attempt("resize from the grip", lambda: (
        reader._resize_start(FakeDrag(500, 700)),
        reader._resize_move(FakeDrag(560, 760)),
    ))
    attempt("resize cannot go below the minimum", lambda: (
        reader._resize_start(FakeDrag(500, 700)),
        reader._resize_move(FakeDrag(0, 0)),
    ))
    pump()
    check("width stayed sane", root.winfo_width() >= 280, root.winfo_width())

    print("\ncontrol bar")
    reader.goto(2)
    pump()
    check("page box shows the current page",
          reader.page_entry.get() == "3", reader.page_entry.get())
    check("total pages shown", "8" in reader.page_total.cget("text"),
          reader.page_total.cget("text"))
    check("zoom label filled", "%" in reader.zoom_label.cget("text"),
          reader.zoom_label.cget("text"))
    check("opacity label filled", "%" in reader.opacity_label.cget("text"),
          reader.opacity_label.cget("text"))

    attempt("next button updates the page box", lambda: (
        reader.next_page(), pump()))
    check("page box followed the page", reader.page_entry.get() == "4",
          reader.page_entry.get())

    reader.page_entry.delete(0, "end")
    reader.page_entry.insert(0, "7")
    attempt("typing a page and pressing Enter", reader._page_entry_submit)
    pump()
    check("jumped to the typed page", reader.page == 6, reader.page)
    reader.page_entry.delete(0, "end")
    reader.page_entry.insert(0, "banana")
    attempt("rubbish in the page box is handled", reader._page_entry_submit)
    pump()
    check("page did not move", reader.page == 6, reader.page)
    check("page box was put back", reader.page_entry.get() == "7",
          reader.page_entry.get())

    print("\nopacity slider")
    attempt("dragging the slider", lambda: reader.opacity_scale.set(45))
    pump()
    check("slider drives the window opacity",
          abs(reader.opacity - 0.45) < 0.02, reader.opacity)
    attempt("keyboard opacity moves the slider", lambda: reader.nudge_opacity(0.10))
    pump()
    check("slider followed the keyboard",
          abs(reader.opacity_scale.get() - 55) <= 1, reader.opacity_scale.get())
    attempt("menu preset sets opacity", lambda: reader.set_opacity(0.8))
    check("preset applied", abs(reader.opacity - 0.8) < 1e-6, reader.opacity)

    # Programmatic sets are not proof the widget works under the mouse.
    # Drag it for real: press near the left end, move right, release.
    reader.set_opacity(1.0)
    pump()
    scale_width = reader.opacity_scale.winfo_width()
    reader.opacity_scale.event_generate("<Button-1>", x=6, y=6)
    pump()
    dragged_low = reader.opacity
    reader.opacity_scale.event_generate("<B1-Motion>", x=scale_width - 6, y=6)
    reader.opacity_scale.event_generate("<ButtonRelease-1>", x=scale_width - 6, y=6)
    pump()
    check("clicking the left end of the bar jumps there, not one step",
          dragged_low < 0.35, dragged_low)
    check("dragging right raises it again",
          reader.opacity > dragged_low, (dragged_low, reader.opacity))
    check("the label tracks the drag",
          "{:.0f}%".format(reader.opacity * 100) ==
          reader.opacity_label.cget("text"),
          (reader.opacity, reader.opacity_label.cget("text")))

    # A render landing mid drag must not snap the slider back.
    reader.set_opacity(0.5)
    pump()
    reader.opacity_var.set(35)
    reader.render(anchor="keep")
    reader._update_controls()
    pump()
    check("a re-render does not fight the slider",
          abs(reader.opacity - 0.35) < 0.02, reader.opacity)
    reader.set_opacity(0.8)

    print("\ntoggle buttons latch")
    reader.toggle_invert()
    pump()
    check("invert button looks pressed in",
          reader.invert_button.cget("bg") != "#16161d",
          reader.invert_button.cget("bg"))
    reader.toggle_invert()
    pump()
    check("invert button released",
          reader.invert_button.cget("bg") == "#16161d",
          reader.invert_button.cget("bg"))

    print("\nmenu")
    attempt("menu builds without error", lambda: _build_menu_only(reader))

    print("\nghost mode")
    attempt("ghost mode declines off Windows", reader.toggle_ghost)
    check("ghost stayed off", reader.ghost is False)

    print("\nopening another file")
    second = os.path.join(tmpdir, "second.pdf")
    make_pdf(second, pages=3)
    attempt("swap in another document", lambda: reader.load_document(second))
    pump()
    check("new document loaded", reader.doc.page_count == 3, reader.doc.page_count)
    check("page reset for the new file", reader.page == 0, reader.page)
    check("title bar updated", "second" in reader.title_label.cget("text"),
          reader.title_label.cget("text"))
    attempt("opening a broken path is reported", lambda: reader.load_document(
        os.path.join(tmpdir, "not-real.pdf")))
    check("still on the good document", reader.doc.page_count == 3,
          reader.doc.page_count)
    attempt("swap back", lambda: reader.load_document(pdf_path))
    pump()
    check("back on the first document", reader.doc.page_count == 8,
          reader.doc.page_count)

    print("\npopups are opaque")
    reader.set_opacity(0.4)
    reader.show_help()
    pump()
    tops = [c for c in reader.root.winfo_children() if isinstance(c, tk.Toplevel)]
    check("a help window opened", len(tops) >= 1, len(tops))
    if tops:
        alpha = tops[-1].attributes("-alpha")
        check("help window is fully opaque, not see through",
              abs(float(alpha) - 1.0) < 1e-6, alpha)
    for child in tops:
        child.destroy()
    pump()
    reader.set_opacity(0.8)

    print("\nautosave")
    from ghostread import state as state_store
    reader.goto(5)
    pump()
    attempt("autosave runs", reader._autosave)
    check("autosave wrote the page", state_store.load(pdf_path)["page"] == 5,
          state_store.load(pdf_path))
    attempt("autosave is a no-op when nothing changed", reader._autosave)

    print("\nshutdown")
    reader.goto(6)
    pump()
    attempt("quit saves and closes", reader.quit)

    from ghostread import state as state_store
    saved = state_store.load(pdf_path)
    check("resumes on the page you left", saved["page"] == 6, saved)
    check("remembers the geometry", saved.get("geometry"), saved.get("geometry"))

    print("\n{} passed, {} failed".format(len(PASSED), len(FAILED)))
    return 1 if FAILED else 0


def _build_menu_only(reader):
    """Build the menu without popping it up, which would block the test."""
    import tkinter as tk
    calls = []
    original = tk.Menu.tk_popup
    tk.Menu.tk_popup = lambda self, x, y, *a, **k: calls.append((x, y))
    try:
        reader.show_menu()
    finally:
        tk.Menu.tk_popup = original
    assert calls, "menu never tried to post itself"


class FakeDrag:
    def __init__(self, x_root, y_root):
        self.x_root = x_root
        self.y_root = y_root
        self.x = x_root
        self.y = y_root


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
