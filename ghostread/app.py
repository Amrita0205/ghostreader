"""The overlay window itself.

Design notes
------------
* Tkinter is used on purpose. It ships with CPython on Windows, so there is no
  heavy GUI dependency to install on a machine that is already busy running a
  training job.
* Window translucency comes from the Tk `-alpha` attribute, which makes the
  whole window see through, content included. That is exactly what is wanted
  here: the page floats over the terminal rather than covering it.
* Page rendering happens in `document.PdfDocument`, and the next page is
  pre-rendered on a background thread so paging feels instant. Only the main
  thread ever touches Tk objects.
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont

from PIL import ImageTk

from . import state as state_store
from . import winext
from .document import PdfDocument, PdfError

BG = "#0e0e12"
BAR = "#16161d"
PANEL = "#1b1b24"
HOVER = "#262633"
ACTIVE_BG = "#2b3350"
DIVIDER = "#2a2a36"
FIELD = "#22222c"
FG = "#d8d8e0"
DIM = "#7f7f92"
ACCENT = "#7aa2f7"
WARN = "#f7a27a"
KEY_COLOUR = "#000000"  # exact colour that ghost mode makes transparent

# Outline width, in pixels, for ghost mode. Two is enough to lift text off a
# busy background without the page starting to look like it has a border.
DEFAULT_HALO = 2
MAX_HALO = 4

MIN_OPACITY = 0.15
MAX_OPACITY = 1.0
OPACITY_STEP = 0.05
PAD = 8

HELP_TEXT = """\
GhostRead

Everything is on the bottom bar. Hover any button for a
hint, or right click anywhere for the full menu.

bottom bar, left to right

  arrows + page box    turn pages, or type a number + Enter
  -  %  +  fit         zoom, and fit the page to the window
  see through slider   fade the window. Click anywhere on
                       the bar to jump straight there.
  half moon            invert colours. Try this first when
                       the page is hard to read over a
                       dark screen.
  sparkle              ghost mode (Windows). The page
                       disappears and only the text stays,
                       fully sharp, floating over your
                       work. Clicks pass through the
                       empty parts. Press e if the text
                       needs a heavier outline to stand
                       out from what is behind it.
  up arrow             keep the window on top
  circle dot           click through: clicks reach the
                       window underneath (Windows). The
                       page stops taking the mouse, so a
                       small "turn it off" panel appears
                       and stays clickable. Drag it out of
                       the way if it is over something.
                       A global hotkey works too, and the
                       panel shows which one was claimed.
  find / toc           search the text, or jump by chapter
  three dots           the full menu, with Open and Recent

drag the top bar to move the window
drag /// in the corner to resize
double click the top bar to roll it up to just the bar

keys, if you prefer them

  Space / n     next page        b / p    previous page
  Up Down j k   scroll           g        go to page
  / or Ctrl+F   search           F3       next hit
  o             contents         Ctrl+O   open a file
  + / -         zoom             0 / 9    fit width/page
  [ / ]         fade less/more   i        invert
  t             keep on top      c        click through
  e             text outline     h        roll up
  F1            this help        q        quit
"""


class GhostReader:
    def __init__(self, root: tk.Tk, doc: PdfDocument, opts, saved: dict):
        self.root = root
        self.doc = doc
        self.opts = opts
        self.remember = not opts.no_remember

        self.page = doc.clamp(saved.get("page") or 0)
        self.fit = saved.get("fit") or "width"
        self.zoom = saved.get("zoom") or 1.0
        self.opacity = self._clamp_opacity(saved.get("opacity", 0.80))
        self.invert = bool(saved.get("invert", False))
        self.topmost = not opts.no_topmost
        self.click_through = False
        self._escape_panel = None
        self.ghost = False
        self.halo_width = max(0, min(int(saved.get("halo", DEFAULT_HALO)),
                                     MAX_HALO))
        self.rolled_up = False

        self.photo = None
        self.current_zoom = 1.0
        self._resize_job = None
        self._render_job = None
        self._flash_job = None
        self._prefetching = set()

        self.hits = []
        self.hit_index = -1
        self.last_query = ""

        self.hotkey = winext.GlobalHotkey(self._hotkey_fired)

        self._build_window(saved.get("geometry"))
        self._build_widgets()
        self._bind_keys()
        self._saved_signature = None
        self.root.after(60, self._first_render)
        self.root.after(150, self._poll_hotkey)
        self.root.after(20000, self._autosave)

    # ------------------------------------------------------------- window

    @staticmethod
    def _clamp_opacity(value) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.80
        return max(MIN_OPACITY, min(MAX_OPACITY, value))

    def _build_window(self, saved_geometry):
        root = self.root
        root.title("GhostRead - {}".format(self.doc.name))
        root.configure(bg=BG)

        geometry = self.opts.geometry or saved_geometry or "760x900+60+60"
        try:
            root.geometry(geometry)
        except tk.TclError:
            root.geometry("760x900+60+60")
        root.minsize(280, 200)

        if not self.opts.framed:
            root.overrideredirect(True)

        root.update_idletasks()
        self._apply_opacity()
        self._apply_topmost()

        if not self.opts.framed:
            winext.hide_from_taskbar(root)

        root.protocol("WM_DELETE_WINDOW", self.quit)

    def _apply_opacity(self):
        try:
            self.root.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass

    def _apply_topmost(self):
        try:
            self.root.attributes("-topmost", bool(self.topmost))
        except tk.TclError:
            pass

    # ------------------------------------------------------------ widgets

    def _build_widgets(self):
        root = self.root
        ui_font = tkfont.Font(family="Segoe UI", size=9)
        mono = tkfont.Font(family="Consolas", size=9)

        # Top bar: doubles as the drag handle for the frameless window.
        self.bar = tk.Frame(root, bg=BAR, height=26)
        self.bar.pack(side="top", fill="x")
        self.bar.pack_propagate(False)

        self.title_label = tk.Label(
            self.bar, text=self._short_name(), bg=BAR, fg=DIM, font=ui_font, anchor="w"
        )
        self.title_label.pack(side="left", padx=(10, 6))

        tk.Button(
            self.bar, text="x", command=self.quit, bg=BAR, fg=DIM,
            activebackground=BAR, activeforeground=WARN, relief="flat",
            font=ui_font, bd=0, padx=8, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            self.bar, text="?", command=self.show_help, bg=BAR, fg=DIM,
            activebackground=BAR, activeforeground=ACCENT, relief="flat",
            font=ui_font, bd=0, padx=8, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            self.bar, text="_", command=self.toggle_roll, bg=BAR, fg=DIM,
            activebackground=BAR, activeforeground=ACCENT, relief="flat",
            font=ui_font, bd=0, padx=8, cursor="hand2",
        ).pack(side="right")

        self.status = tk.Label(
            self.bar, text="", bg=BAR, fg=DIM, font=mono, anchor="e"
        )
        self.status.pack(side="right", padx=(6, 10))

        for widget in (self.bar, self.title_label):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)
            widget.bind("<Double-Button-1>", lambda e: self.toggle_roll())

        # Prompt row, hidden until search or goto is invoked.
        self.prompt_row = tk.Frame(root, bg=BAR)
        self.prompt_label = tk.Label(
            self.prompt_row, text="", bg=BAR, fg=ACCENT, font=mono
        )
        self.prompt_label.pack(side="left", padx=(10, 4), pady=3)
        self.prompt_entry = tk.Entry(
            self.prompt_row, bg="#22222c", fg=FG, insertbackground=FG,
            relief="flat", font=mono, highlightthickness=0,
        )
        self.prompt_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=3)
        self.prompt_mode = None

        # Body: canvas plus a thin scrollbar.
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(side="top", fill="both", expand=True)

        self.canvas = tk.Canvas(
            self.body, bg=BG, highlightthickness=0, bd=0, takefocus=True
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.scroll = tk.Scrollbar(
            self.body, orient="vertical", command=self.canvas.yview,
            width=10, bg=BAR, troughcolor=BG, activebackground=ACCENT,
            relief="flat", bd=0,
        )
        self.scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.scroll.set)

        # Bottom control bar. Everything the keyboard can do is reachable here
        # with the mouse, because nobody should have to memorise a key list to
        # use a reader.
        #
        # The `before` matters. The body is packed with expand=True, so it
        # claims the whole remaining cavity. Anything packed after it gets zero
        # height and the bar silently vanishes.
        self.controls = tk.Frame(root, bg=BAR, height=30)
        self.controls.pack(side="bottom", fill="x", before=self.body)
        self.controls.pack_propagate(False)

        def button(parent, text, command, tip, width=2, side="left", padx=1):
            widget = tk.Button(
                parent, text=text, command=command, bg=BAR, fg=FG,
                activebackground=HOVER, activeforeground=ACCENT,
                relief="flat", bd=0, font=ui_font, width=width,
                cursor="hand2", highlightthickness=0, padx=2, pady=1,
            )
            widget.pack(side=side, padx=padx, pady=3)
            widget.bind("<Enter>", lambda e: widget.configure(bg=HOVER))
            widget.bind("<Leave>", lambda e: widget.configure(
                bg=ACTIVE_BG if getattr(widget, "_latched", False) else BAR))
            self._tooltip(widget, tip)
            return widget

        # Grip first so it keeps its corner even when the window is narrow.
        self.grip = tk.Label(self.controls, text="///", bg=BAR, fg=DIM,
                             font=tkfont.Font(size=7),
                             cursor="bottom_right_corner")
        self.grip.pack(side="right", padx=(2, 6))
        self.grip.bind("<Button-1>", self._resize_start)
        self.grip.bind("<B1-Motion>", self._resize_move)
        self.grip.bind("<ButtonRelease-1>", self._resize_end)
        self._tooltip(self.grip, "drag to resize the window")

        button(self.controls, "\u22ee", self.show_menu,
               "everything, in one menu  (right click anywhere)",
               width=2, side="right")

        # Page navigation.
        button(self.controls, "\u25c0", self.prev_page, "previous page  (b)")
        self.page_entry = tk.Entry(
            self.controls, width=5, bg=FIELD, fg=FG, insertbackground=FG,
            relief="flat", font=mono, justify="center", highlightthickness=1,
            highlightbackground=BAR, highlightcolor=ACCENT,
        )
        self.page_entry.pack(side="left", pady=4)
        self.page_entry.bind("<Return>", self._page_entry_submit)
        self.page_entry.bind("<FocusIn>", lambda e: self.page_entry.select_range(0, "end"))
        self._tooltip(self.page_entry, "type a page number and press Enter")

        self.page_total = tk.Label(self.controls, text="", bg=BAR, fg=DIM, font=mono)
        self.page_total.pack(side="left", padx=(3, 4))

        button(self.controls, "\u25b6", self.next_page, "next page  (space)")

        tk.Frame(self.controls, bg=DIVIDER, width=1).pack(
            side="left", fill="y", pady=7, padx=6)

        # Zoom.
        button(self.controls, "\u2212", lambda: self.zoom_by(1 / 1.15), "zoom out  (-)")
        self.zoom_label = tk.Label(self.controls, text="", bg=BAR, fg=DIM,
                                   font=mono, width=5)
        self.zoom_label.pack(side="left")
        button(self.controls, "+", lambda: self.zoom_by(1.15), "zoom in  (+)")
        self.fit_button = button(self.controls, "fit", lambda: self.set_fit("width"),
                                 "fit the page to the window width  (0)", width=3)

        tk.Frame(self.controls, bg=DIVIDER, width=1).pack(
            side="left", fill="y", pady=7, padx=6)

        # Opacity, the whole reason this app exists, so give it a real slider.
        tk.Label(self.controls, text="see through", bg=BAR, fg=DIM,
                 font=ui_font).pack(side="left", padx=(0, 4))
        # Driven by a traced variable rather than the Scale -command option.
        # A Scale command is not reliably invoked for a programmatic set, so a
        # variable trace is the only version that behaves the same whether the
        # value came from a drag, a keypress or a menu preset.
        self.opacity_var = tk.IntVar(value=int(round(self.opacity * 100)))
        self.opacity_scale = tk.Scale(
            self.controls, from_=15, to=100, orient="horizontal",
            showvalue=False, length=96, width=9, sliderlength=14,
            bg=BAR, fg=FG, troughcolor=FIELD, activebackground=ACCENT,
            highlightthickness=0, bd=0, relief="flat",
            variable=self.opacity_var,
        )
        self.opacity_var.trace_add("write", self._opacity_var_changed)
        self.opacity_scale.pack(side="left", pady=4)
        # Click anywhere on the bar to jump there. Tk's default is to step the
        # value by one when you click the trough, which feels broken on a
        # control people expect to slam from readable to nearly gone.
        self.opacity_scale.bind("<Button-1>", self._opacity_click)
        self.opacity_scale.bind("<B1-Motion>", self._opacity_click)
        self._tooltip(self.opacity_scale,
                      "drag to fade the window  (or press [ and ])")
        self.opacity_label = tk.Label(self.controls, text="", bg=BAR, fg=DIM,
                                      font=mono, width=4)
        self.opacity_label.pack(side="left", padx=(4, 2))

        tk.Frame(self.controls, bg=DIVIDER, width=1).pack(
            side="left", fill="y", pady=7, padx=6)

        # Toggles and lookups.
        self.invert_button = button(
            self.controls, "\u25d1", self.toggle_invert,
            "invert colours, far easier to read over a dark screen  (i)")
        self.ghost_button = button(
            self.controls, "\u2727", self.toggle_ghost,
            "ghost mode: hide the page, keep only the text  (Windows)")
        self.top_button = button(
            self.controls, "\u2191", self.toggle_topmost, "keep on top  (t)")
        self.through_button = button(
            self.controls, "\u2609", self.toggle_click_through,
            "let clicks pass through to the window below. A small panel "
            "stays on screen to switch it back off  (Windows)")
        button(self.controls, "find", lambda: self.open_prompt("search"),
               "search the document  (Ctrl+F)", width=4)
        button(self.controls, "toc", self.show_outline,
               "contents / chapter list  (o)", width=3)

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set())
        self.canvas.bind("<Button-3>", self.show_menu)
        self.bar.bind("<Button-3>", self.show_menu)

        self._refresh_latches()
        self._update_controls()

    # -------------------------------------------------------- small helpers

    def _tooltip(self, widget, text: str):
        """A plain hover tooltip. Discoverability beats a memorised key list."""
        holder = {"win": None, "job": None}

        def show():
            if holder["win"] or not text:
                return
            try:
                x = widget.winfo_rootx()
                y = widget.winfo_rooty() - 26
            except tk.TclError:
                return
            tip = tk.Toplevel(self.root)
            tip.wm_overrideredirect(True)
            try:
                tip.attributes("-topmost", True)
                tip.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            tk.Label(tip, text=text, bg="#2b2b38", fg=FG, relief="flat",
                     font=tkfont.Font(family="Segoe UI", size=8),
                     padx=7, pady=3).pack()
            tip.wm_geometry("+{}+{}".format(x, max(0, y)))
            holder["win"] = tip

        def enter(_event=None):
            holder["job"] = self.root.after(550, show)

        def leave(_event=None):
            if holder["job"]:
                self.root.after_cancel(holder["job"])
                holder["job"] = None
            if holder["win"]:
                holder["win"].destroy()
                holder["win"] = None

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")
        widget.bind("<Button-1>", leave, add="+")

    def _latch(self, widget, on: bool):
        """Show a toggle button as pressed in."""
        widget._latched = on
        widget.configure(bg=ACTIVE_BG if on else BAR,
                         fg=ACCENT if on else FG)

    def _refresh_latches(self):
        self._latch(self.invert_button, self.invert)
        self._latch(self.top_button, self.topmost)
        self._latch(self.through_button, self.click_through)
        self._latch(self.ghost_button, self.ghost)
        self._latch(self.fit_button, self.fit != "free")

    def _update_controls(self):
        """Keep the bar in step with the state, whatever changed it."""
        if not getattr(self, "page_entry", None):
            return
        if self.root.focus_get() is not self.page_entry:
            self.page_entry.delete(0, "end")
            self.page_entry.insert(0, str(self.page + 1))
        self.page_total.configure(text="/ {}".format(self.doc.page_count))
        self.zoom_label.configure(text="{:.0f}%".format(self.current_zoom * 100))
        self.opacity_label.configure(text="{:.0f}%".format(self.opacity * 100))
        self.title_label.configure(text=self._short_name())
        self._refresh_latches()
        # Deliberately does not write to the opacity slider. Tk invokes a
        # Scale command on the next event loop pass rather than immediately,
        # so a render landing mid drag used to push the slider back to the old
        # value and the stale callback then won. Only the opacity setters
        # below are allowed to move it.

    def _sync_opacity_scale(self):
        percent = int(round(self.opacity * 100))
        if self.opacity_var.get() != percent:
            self.opacity_var.set(percent)

    def _page_entry_submit(self, _event=None):
        try:
            target = int(self.page_entry.get().strip()) - 1
        except ValueError:
            self._flash("that is not a page number")
            self._update_controls()
            return "break"
        self.goto(target)
        self.canvas.focus_set()
        return "break"

    def _opacity_click(self, event):
        """Map a click position straight onto a value."""
        width = self.opacity_scale.winfo_width()
        slider = 14
        usable = max(1, width - slider)
        fraction = (event.x - slider / 2.0) / usable
        fraction = max(0.0, min(1.0, fraction))
        low, high = 15, 100
        self.opacity_var.set(int(round(low + fraction * (high - low))))
        return "break"

    def _opacity_var_changed(self, *_args):
        """Fires for a drag, a keypress or a menu preset alike."""
        try:
            percent = int(self.opacity_var.get())
        except (tk.TclError, ValueError):
            return
        self.opacity = self._clamp_opacity(percent / 100.0)
        self._apply_opacity()
        if getattr(self, "opacity_label", None):
            self.opacity_label.configure(text="{:.0f}%".format(self.opacity * 100))

    def _short_name(self, width: int = 34) -> str:
        name = self.doc.name
        return name if len(name) <= width else name[: width - 3] + "..."

    # ----------------------------------------------------------- key binds

    def _bind_keys(self):
        root = self.root
        bind = root.bind_all

        bind("<Right>", lambda e: self.next_page())
        bind("<Next>", lambda e: self.next_page())
        bind("<Left>", lambda e: self.prev_page())
        bind("<Prior>", lambda e: self.prev_page())
        bind("<Home>", lambda e: self.goto(0))
        bind("<End>", lambda e: self.goto(self.doc.page_count - 1))
        bind("<Down>", lambda e: self.scroll_by(1))
        bind("<Up>", lambda e: self.scroll_by(-1))
        bind("<space>", lambda e: self._space())
        bind("<Key>", self._on_key)

        bind("<Control-f>", lambda e: self.open_prompt("search"))
        bind("<Control-q>", lambda e: self.quit())
        bind("<Control-o>", lambda e: self.open_file())
        bind("<F1>", lambda e: self.show_help())
        bind("<F3>", lambda e: self.next_hit())
        bind("<Escape>", lambda e: self.close_prompt())
        bind("<Return>", lambda e: self._on_return())

        # Mouse wheel: Windows and macOS send MouseWheel, X11 sends buttons 4/5.
        bind("<MouseWheel>", self._on_wheel)
        bind("<Button-4>", lambda e: self._wheel_step(-1, False))
        bind("<Button-5>", lambda e: self._wheel_step(1, False))
        bind("<Control-MouseWheel>", lambda e: self._wheel_step(
            -1 if e.delta > 0 else 1, True))

        # These return "break" on purpose. Widget bindings fire before the
        # bind_all ones, so without it a single Enter would submit the prompt
        # and then immediately trigger "find next" as well.
        self.prompt_entry.bind("<Return>", self._prompt_return)
        self.prompt_entry.bind("<Escape>", self._prompt_escape)

    def _prompt_return(self, _event=None):
        self._submit_prompt()
        return "break"

    def _prompt_escape(self, _event=None):
        self.close_prompt()
        return "break"

    def _typing(self) -> bool:
        """True when a text box has focus, so single key shortcuts stand down."""
        focused = self.root.focus_get()
        return focused is self.prompt_entry or focused is getattr(
            self, "page_entry", None)

    def _on_key(self, event):
        if self._typing():
            return
        key = (event.keysym or "").lower()
        char = event.char

        actions = {
            "n": self.next_page,
            "p": self.prev_page,
            "b": self.prev_page,
            "j": lambda: self.scroll_by(1),
            "k": lambda: self.scroll_by(-1),
            "g": lambda: self.open_prompt("goto"),
            "o": self.show_outline,
            "t": self.toggle_topmost,
            "i": self.toggle_invert,
            "c": self.toggle_click_through,
            "e": self.cycle_halo,
            "h": self.toggle_roll,
            "q": self.quit,
        }
        if key in actions:
            actions[key]()
            return "break"

        if char in ("+", "="):
            self.zoom_by(1.15)
        elif char == "-":
            self.zoom_by(1 / 1.15)
        elif char == "0":
            self.set_fit("width")
        elif char == "9":
            self.set_fit("page")
        elif char == "[":
            self.nudge_opacity(-OPACITY_STEP)
        elif char == "]":
            self.nudge_opacity(OPACITY_STEP)
        elif char == "/":
            self.open_prompt("search")
        elif char == "?":
            self.show_help()

    def _space(self):
        if self._typing():
            return
        self.scroll_by(6)

    def _on_return(self):
        if self.prompt_mode:
            self._submit_prompt()
        else:
            self.next_hit()

    # ------------------------------------------------------ drag / resize

    def _window_rect(self):
        """Current position and size in screen coordinates."""
        try:
            return (self.root.winfo_rootx(), self.root.winfo_rooty(),
                    self.root.winfo_width(), self.root.winfo_height())
        except tk.TclError:
            return None

    def _repaint_vacated(self, rect, immediate=False):
        """Clean up after moving, so no stale copy is left on the desktop.

        See `winext.repaint_desktop`. During a drag this only marks the region
        dirty and lets Windows coalesce the repaints, which keeps the drag
        smooth; the immediate pass is saved for when the mouse comes up.
        """
        if rect:
            winext.repaint_desktop(rect, immediate=immediate)

    def _drag_start(self, event):
        self._drag_origin = (event.x_root, event.y_root,
                             self.root.winfo_x(), self.root.winfo_y())

    def _drag_move(self, event):
        if not getattr(self, "_drag_origin", None):
            return
        ox, oy, wx, wy = self._drag_origin
        before = self._window_rect()
        self.root.geometry("+{}+{}".format(
            wx + event.x_root - ox, wy + event.y_root - oy))
        self._repaint_vacated(before)

    def _drag_end(self, _event=None):
        self._drag_origin = None
        # One full pass, to catch anything the per move repaints missed.
        winext.repaint_desktop(None, immediate=True)

    def _resize_start(self, event):
        self._resize_origin = (event.x_root, event.y_root,
                               self.root.winfo_width(), self.root.winfo_height())

    def _resize_move(self, event):
        if not getattr(self, "_resize_origin", None):
            return
        ox, oy, ww, wh = self._resize_origin
        before = self._window_rect()
        width = max(280, ww + event.x_root - ox)
        height = max(200, wh + event.y_root - oy)
        self.root.geometry("{}x{}".format(int(width), int(height)))
        self._repaint_vacated(before)

    def _resize_end(self, _event=None):
        self._resize_origin = None
        winext.repaint_desktop(None, immediate=True)

    # ---------------------------------------------------------- rendering

    def _first_render(self):
        self.canvas.focus_set()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass
        self.render(anchor="top")

    def _on_canvas_resize(self, event):
        if self.fit == "free":
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(180, lambda: self.render(anchor="keep"))

    def _effective_zoom(self) -> float:
        width = max(60, self.canvas.winfo_width() - PAD * 2)
        height = max(60, self.canvas.winfo_height() - PAD * 2)
        if self.fit == "width":
            return self.doc.zoom_for_width(self.page, width)
        if self.fit == "page":
            return self.doc.zoom_for_page(self.page, width, height)
        return self.zoom

    def render(self, anchor: str = "top"):
        if self.canvas.winfo_width() < 40:
            self.root.after(80, lambda: self.render(anchor))
            return

        fraction = self.canvas.yview()[0] if anchor == "keep" else None
        zoom = self._effective_zoom()
        self.current_zoom = zoom

        try:
            image = self.doc.render(self.page, zoom, self.invert,
                                    self._halo())
        except Exception as exc:
            self._set_status("render failed: {}".format(exc))
            return

        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")

        canvas_width = self.canvas.winfo_width()
        offset_x = max(0, (canvas_width - image.width) // 2)
        self.canvas.create_image(offset_x, 0, image=self.photo, anchor="nw")
        self.canvas.configure(
            scrollregion=(0, 0, max(canvas_width, image.width), image.height)
        )

        self._draw_hits(offset_x, zoom)

        if anchor == "top":
            self.canvas.yview_moveto(0.0)
        elif anchor == "bottom":
            self.canvas.yview_moveto(1.0)
        elif fraction is not None:
            self.canvas.yview_moveto(fraction)

        self._update_status()
        self._prefetch(self.page + 1, zoom)

    def _draw_hits(self, offset_x: int, zoom: float):
        for page_index, rects in self.hits:
            if page_index != self.page:
                continue
            for x0, y0, x1, y1 in rects:
                self.canvas.create_rectangle(
                    offset_x + x0 * zoom, y0 * zoom,
                    offset_x + x1 * zoom, y1 * zoom,
                    outline=ACCENT, width=2,
                )

    def _prefetch(self, page_index: int, zoom: float):
        if page_index >= self.doc.page_count:
            return
        key = (page_index, round(zoom, 3), self.invert)
        if key in self._prefetching:
            return
        self._prefetching.add(key)

        def work():
            try:
                self.doc.render(page_index, zoom, self.invert, self._halo())
            except Exception:
                pass
            finally:
                self._prefetching.discard(key)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------- navigation

    def goto(self, page_index: int, anchor: str = "top"):
        page_index = self.doc.clamp(page_index)
        if page_index == self.page and anchor == "top":
            self.canvas.yview_moveto(0.0)
            return
        self.page = page_index
        self.render(anchor=anchor)

    def next_page(self):
        if self.page < self.doc.page_count - 1:
            self.goto(self.page + 1)
        else:
            self._flash("last page")

    def prev_page(self):
        if self.page > 0:
            self.goto(self.page - 1, anchor="bottom")
        else:
            self._flash("first page")

    def scroll_by(self, units: int):
        """Scroll, rolling into the neighbouring page at the edges."""
        top, bottom = self.canvas.yview()
        at_bottom = bottom >= 0.999
        at_top = top <= 0.001

        if units > 0 and at_bottom:
            self.next_page()
            return
        if units < 0 and at_top:
            self.prev_page()
            return
        self.canvas.yview_scroll(units * 3, "units")

    def _on_wheel(self, event):
        if event.state & 0x0004:  # Control held
            self._wheel_step(-1 if event.delta > 0 else 1, True)
            return "break"
        self._wheel_step(-1 if event.delta > 0 else 1, False)
        return "break"

    def _wheel_step(self, direction: int, zooming: bool):
        if zooming:
            self.zoom_by(1.12 if direction < 0 else 1 / 1.12)
        else:
            self.scroll_by(direction * 2)

    # ------------------------------------------------- zoom and opacity

    def set_fit(self, mode: str):
        self.fit = mode
        self.render(anchor="keep")
        self._flash("fit {}".format(mode))

    def zoom_by(self, factor: float):
        self.zoom = max(0.15, min(6.0, self.current_zoom * factor))
        self.fit = "free"
        self.render(anchor="keep")
        self._flash("zoom {:.0f}%".format(self.zoom * 100))

    def nudge_opacity(self, delta: float):
        self.set_opacity(self.opacity + delta)

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self._apply_topmost()
        self._update_controls()
        self._flash("keep on top " + ("on" if self.topmost else "off"))

    def toggle_invert(self):
        if self.ghost:
            self._flash("ghost mode needs inverted colours")
            return
        self.invert = not self.invert
        self.render(anchor="keep")
        self._flash("invert " + ("on" if self.invert else "off"))

    def toggle_roll(self):
        before = self._window_rect()
        if self.rolled_up:
            self.root.geometry("{}x{}".format(
                self.root.winfo_width(), self._rolled_height))
            self.rolled_up = False
        else:
            self._rolled_height = self.root.winfo_height()
            self.root.geometry("{}x{}".format(self.root.winfo_width(), 28))
            self.rolled_up = True
        # Rolling up uncovers most of the window's area in one go.
        self._repaint_vacated(before, immediate=True)

    def toggle_click_through(self):
        if not winext.IS_WINDOWS:
            self._flash("click through is Windows only")
            return

        if self.click_through:
            winext.set_click_through(self.root, False)
            self.click_through = False
            self._hide_escape_panel()
            self._update_controls()
            self._flash("click through off")
            return

        # Refuse to enable it unless there is a way back.
        if not self.hotkey.registered and not self.hotkey.register():
            self._flash("no escape hotkey is free, click through disabled")
            return

        if winext.set_click_through(self.root, True):
            self.click_through = True
            self._update_controls()
            self._show_escape_panel()
            self._flash("click through on, {} to return".format(
                self.hotkey.label))
        else:
            self._flash("click through unavailable")

    # ------------------------------------------------- click through escape

    def _show_escape_panel(self):
        """A small window that stays clickable while the overlay does not.

        Click through is the one mode that can strand someone. The overlay
        stops accepting the mouse entirely, and that includes the button that
        would switch the mode off, so the way out cannot live in that window.
        This is a separate top level, and nothing ever makes it click through,
        so it keeps taking clicks after the page has stopped.
        """
        self._hide_escape_panel()
        try:
            panel = tk.Toplevel(self.root)
            panel.wm_overrideredirect(True)
            panel.attributes("-topmost", True)
            panel.configure(bg=ACCENT)
        except tk.TclError:
            return

        inner = tk.Frame(panel, bg=PANEL)
        inner.pack(padx=1, pady=1)

        label = tk.Label(
            inner, text="☉  click through is on", bg=PANEL, fg=FG,
            font=tkfont.Font(family="Segoe UI", size=9), padx=10, pady=6)
        label.pack(side="left")

        tk.Button(
            inner, text="turn it off", command=self.toggle_click_through,
            bg=ACCENT, fg="#11121a", relief="flat", bd=0, padx=10, pady=2,
            activebackground=FG, cursor="hand2",
            font=tkfont.Font(family="Segoe UI", size=9, weight="bold"),
        ).pack(side="left", padx=(0, 8))

        tk.Label(
            inner, text="or {}".format(self.hotkey.label), bg=PANEL, fg=DIM,
            font=tkfont.Font(family="Segoe UI", size=8), padx=(0), pady=6,
        ).pack(side="left", padx=(0, 10))

        # Sit just under the top bar, right aligned, and clamped on screen.
        panel.update_idletasks()
        width = panel.winfo_reqwidth()
        x = self.root.winfo_rootx() + max(0, self.root.winfo_width() - width - 12)
        y = self.root.winfo_rooty() + 34
        x = max(0, min(x, panel.winfo_screenwidth() - width))
        y = max(0, min(y, panel.winfo_screenheight() - 40))
        panel.wm_geometry("+{}+{}".format(int(x), int(y)))

        # The overlay cannot be dragged while it ignores the mouse, so this is
        # the only thing left to move if it happens to cover something.
        def start(event):
            panel._origin = (event.x_root, event.y_root,
                             panel.winfo_x(), panel.winfo_y())

        def move(event):
            origin = getattr(panel, "_origin", None)
            if not origin:
                return
            ox, oy, px, py = origin
            panel.wm_geometry("+{}+{}".format(
                px + event.x_root - ox, py + event.y_root - oy))

        for widget in (inner, label):
            widget.bind("<Button-1>", start)
            widget.bind("<B1-Motion>", move)

        self._escape_panel = panel

    def _hide_escape_panel(self):
        panel = getattr(self, "_escape_panel", None)
        if panel is not None:
            try:
                panel.destroy()
            except tk.TclError:
                pass
        self._escape_panel = None

    def _halo(self) -> int:
        """Outline width for the mode the reader is currently in.

        Only ghost mode needs one. Everywhere else the page itself is still
        behind the words, so there is already something to read them against.
        """
        return self.halo_width if self.ghost else 0

    def cycle_halo(self):
        """Step the outline through off, thin, thicker, and back."""
        if not self.ghost:
            self._flash("the outline only applies in ghost mode")
            return
        self.halo_width = (self.halo_width + 1) % (MAX_HALO + 1)
        self.doc.drop_cache()
        self.render(anchor="keep")
        if self.halo_width:
            self._flash("text outline {} px".format(self.halo_width))
        else:
            self._flash("text outline off")

    def toggle_ghost(self):
        """Hide the page itself and keep only the text.

        Windows can key out one exact colour and make it fully transparent
        while everything else stays completely opaque. Inverting a page turns
        white into pure black, so keying black out leaves crisp light text
        floating over whatever is behind, with no fading at all. Clicks pass
        through the keyed areas for free.
        """
        if not winext.IS_WINDOWS:
            self._flash("ghost mode needs Windows, try invert instead")
            return

        if self.ghost:
            try:
                self.root.attributes("-transparentcolor", "")
            except tk.TclError:
                pass
            self.ghost = False
            self.canvas.configure(bg=BG)
            self.root.configure(bg=BG)
            self.set_opacity(self._pre_ghost_opacity)
            self.render(anchor="keep")
            self._flash("ghost mode off")
            self._update_controls()
            self._repaint_vacated(self._window_rect(), immediate=True)
            return

        try:
            self.root.attributes("-transparentcolor", KEY_COLOUR)
        except tk.TclError:
            self._flash("this system will not key out a colour")
            return

        # Ghost mode only works on an inverted page, and it wants full opacity
        # because the glyphs are never blended in the first place.
        self._pre_ghost_opacity = self.opacity
        self.ghost = True
        if not self.invert:
            self.invert = True
        self.opacity = 1.0
        self._apply_opacity()
        self._sync_opacity_scale()
        self.canvas.configure(bg=KEY_COLOUR)
        self.root.configure(bg=KEY_COLOUR)
        self.render(anchor="keep")
        self._flash("ghost mode on, text only")
        self._update_controls()
        # Keying the background out uncovers whatever is behind the page, which
        # has not been asked to draw itself since the overlay first covered it.
        self._repaint_vacated(self._window_rect(), immediate=True)

    # -------------------------------------------------------------- menu

    def show_menu(self, event=None):
        """One menu with every command and its shortcut spelled out."""
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=FG,
                       activebackground=ACCENT, activeforeground="#0e0e12",
                       bd=0, relief="flat", font=("Segoe UI", 9))

        menu.add_command(label="Open a PDF...", accelerator="Ctrl+O",
                         command=self.open_file)

        recent_files = [p for p in state_store.recent(10)
                        if p != str(self.doc.path)]
        if recent_files:
            submenu = tk.Menu(menu, tearoff=0, bg=PANEL, fg=FG,
                              activebackground=ACCENT, activeforeground="#0e0e12")
            for path in recent_files:
                submenu.add_command(
                    label=os.path.basename(path),
                    command=lambda p=path: self.load_document(p))
            menu.add_cascade(label="Recent", menu=submenu)

        menu.add_separator()
        menu.add_command(label="Next page", accelerator="Space",
                         command=self.next_page)
        menu.add_command(label="Previous page", accelerator="b",
                         command=self.prev_page)
        menu.add_command(label="Go to page...", accelerator="g",
                         command=lambda: self.open_prompt("goto"))
        menu.add_command(label="Contents", accelerator="o",
                         command=self.show_outline)
        menu.add_command(label="Find...", accelerator="Ctrl+F",
                         command=lambda: self.open_prompt("search"))

        menu.add_separator()
        menu.add_command(label="Zoom in", accelerator="+",
                         command=lambda: self.zoom_by(1.15))
        menu.add_command(label="Zoom out", accelerator="-",
                         command=lambda: self.zoom_by(1 / 1.15))
        menu.add_command(label="Fit width", accelerator="0",
                         command=lambda: self.set_fit("width"))
        menu.add_command(label="Fit whole page", accelerator="9",
                         command=lambda: self.set_fit("page"))

        opacity_menu = tk.Menu(menu, tearoff=0, bg=PANEL, fg=FG,
                               activebackground=ACCENT, activeforeground="#0e0e12")
        for percent in (100, 90, 80, 70, 60, 50, 40, 30, 20):
            opacity_menu.add_command(
                label="{}%".format(percent),
                command=lambda p=percent: self.set_opacity(p / 100.0))
        menu.add_cascade(label="See through", menu=opacity_menu)

        menu.add_separator()
        menu.add_checkbutton(
            label="Invert colours", accelerator="i",
            onvalue=True, offvalue=False,
            variable=tk.BooleanVar(value=self.invert),
            command=self.toggle_invert)
        menu.add_checkbutton(
            label="Ghost mode, text only (Windows)",
            onvalue=True, offvalue=False,
            variable=tk.BooleanVar(value=self.ghost),
            command=self.toggle_ghost)
        menu.add_checkbutton(
            label="Keep on top", accelerator="t",
            onvalue=True, offvalue=False,
            variable=tk.BooleanVar(value=self.topmost),
            command=self.toggle_topmost)
        menu.add_checkbutton(
            label="Click through (Windows)", accelerator="c",
            onvalue=True, offvalue=False,
            variable=tk.BooleanVar(value=self.click_through),
            command=self.toggle_click_through)
        menu.add_command(label="Roll up to the bar", accelerator="h",
                         command=self.toggle_roll)

        menu.add_separator()
        menu.add_command(label="Keys and help", accelerator="F1",
                         command=self.show_help)
        menu.add_command(label="Quit", accelerator="q", command=self.quit)

        if event is not None and getattr(event, "x_root", None) is not None:
            x, y = event.x_root, event.y_root
        else:
            x = self.root.winfo_rootx() + self.root.winfo_width() - 200
            y = self.root.winfo_rooty() + self.root.winfo_height() - 30
        try:
            menu.tk_popup(int(x), int(y))
        finally:
            menu.grab_release()
        return "break"

    def set_opacity(self, value: float):
        """The one way opacity changes from anywhere other than the slider."""
        self.opacity = self._clamp_opacity(value)
        self._apply_opacity()
        self._sync_opacity_scale()
        self._update_controls()
        self._flash("see through {:.0f}%".format(self.opacity * 100))

    # ---------------------------------------------------- swapping files

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open a PDF",
            initialdir=str(self.doc.path.parent),
            filetypes=[("PDF and ebooks", "*.pdf *.epub *.xps *.cbz *.fb2"),
                       ("All files", "*.*")],
            parent=self.root,
        )
        if path:
            self.load_document(path)

    def load_document(self, path):
        """Swap in another document without restarting the app."""
        try:
            new_doc = PdfDocument(path, password=self.opts.password)
        except PdfError as exc:
            self._flash(str(exc), milliseconds=4000)
            return

        self.save_state()
        self.doc.close()
        self.doc = new_doc

        saved = {} if not self.remember else state_store.load(new_doc.path)
        self.page = new_doc.clamp(saved.get("page") or 0)
        self.fit = saved.get("fit") or "width"
        self.zoom = saved.get("zoom") or 1.0
        if saved.get("invert") is not None and not self.ghost:
            self.invert = bool(saved.get("invert"))

        self.hits = []
        self.hit_index = -1
        self._saved_signature = None
        self.root.title("GhostRead - {}".format(new_doc.name))
        self.render(anchor="top")
        self._flash("opened {}".format(new_doc.name))
        if self.click_through:
            winext.set_click_through(self.root, False)
            self.click_through = False
            self._hide_escape_panel()
            self._flash("click through off")
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def _hotkey_fired(self):
        """Ctrl+Alt+G, the way back out of click through mode."""
        if self.click_through:
            winext.set_click_through(self.root, False)
            self.click_through = False
            self._update_controls()
            self._flash("click through off")
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def _poll_hotkey(self):
        self.hotkey.poll()
        self.root.after(120, self._poll_hotkey)

    # ------------------------------------------------------------ prompt

    def open_prompt(self, mode: str):
        self.prompt_mode = mode
        self.prompt_label.configure(
            text="page:" if mode == "goto" else "find:")
        self.prompt_row.pack(after=self.bar, fill="x")
        self.prompt_entry.delete(0, "end")
        if mode == "search" and self.last_query:
            self.prompt_entry.insert(0, self.last_query)
            self.prompt_entry.select_range(0, "end")
        self.prompt_entry.focus_set()

    def close_prompt(self):
        self.prompt_mode = None
        self.prompt_row.pack_forget()
        self.canvas.focus_set()

    def _submit_prompt(self):
        value = self.prompt_entry.get().strip()
        mode = self.prompt_mode
        self.close_prompt()
        if not value:
            return

        if mode == "goto":
            try:
                target = int(value) - 1
            except ValueError:
                self._flash("not a page number")
                return
            self.goto(target)
        elif mode == "search":
            self.run_search(value)

    def run_search(self, query: str):
        self.last_query = query
        self._set_status("searching...")
        self.root.update_idletasks()
        self.hits = self.doc.search(query, start=self.page)
        if not self.hits:
            self.hit_index = -1
            self._flash('no match for "{}"'.format(query))
            return
        self.hit_index = -1
        self.next_hit()

    def next_hit(self):
        if not self.hits:
            if self.last_query:
                self.run_search(self.last_query)
            return
        self.hit_index = (self.hit_index + 1) % len(self.hits)
        page_index = self.hits[self.hit_index][0]
        self.goto(page_index)
        self._flash("hit {}/{}".format(self.hit_index + 1, len(self.hits)))

    # ------------------------------------------------------------ popups

    def _popup(self, title: str, width: int = 520, height: int = 460):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PANEL)
        win.geometry("{}x{}+{}+{}".format(
            width, height,
            self.root.winfo_x() + 30, self.root.winfo_y() + 40))
        try:
            win.attributes("-topmost", True)
            # Deliberately opaque. Inheriting the reader's translucency here
            # meant the page behind showed straight through the help text,
            # which made it unreadable.
            win.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        win.bind("<Escape>", lambda e: win.destroy())
        return win

    def _scrollable_text(self, parent, content: str):
        frame = tk.Frame(parent, bg=PANEL)
        frame.pack(fill="both", expand=True)
        text = tk.Text(
            frame, bg=PANEL, fg=FG, relief="flat", wrap="word",
            font=tkfont.Font(family="Consolas", size=10), padx=16, pady=14,
            highlightthickness=0, spacing1=1, spacing3=2,
        )
        bar = tk.Scrollbar(frame, orient="vertical", command=text.yview,
                           width=11, bg=PANEL, troughcolor=PANEL,
                           activebackground=ACCENT, relief="flat", bd=0)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", content)
        text.configure(state="disabled")
        return text

    def show_help(self):
        win = self._popup("GhostRead help", 600, 560)
        self._scrollable_text(win, HELP_TEXT)

    def show_outline(self):
        entries = self.doc.toc()
        if not entries:
            self._flash("this document has no outline")
            return

        win = self._popup("Contents", 580, 560)
        header = tk.Label(
            win, text="Double click a heading to jump there",
            bg=PANEL, fg=DIM, font=tkfont.Font(family="Segoe UI", size=9),
            anchor="w", padx=12, pady=6)
        header.pack(fill="x")

        frame = tk.Frame(win, bg=PANEL)
        frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(
            frame, bg=PANEL, fg=FG, relief="flat", highlightthickness=0,
            selectbackground=ACCENT, selectforeground="#0e0e12",
            font=tkfont.Font(family="Segoe UI", size=10), activestyle="none",
            bd=0,
        )
        bar = tk.Scrollbar(frame, orient="vertical", command=listbox.yview,
                           width=11, bg=PANEL, troughcolor=PANEL,
                           activebackground=ACCENT, relief="flat", bd=0)
        listbox.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        for level, title, page_index in entries:
            listbox.insert(
                "end", "{}{}   {}".format("    " * (level - 1), title, page_index + 1))

        # Highlight whichever heading covers the page you are on.
        current = 0
        for position, (_, _, page_index) in enumerate(entries):
            if page_index <= self.page:
                current = position
        listbox.selection_set(current)
        listbox.see(current)

        def jump(_event=None):
            selection = listbox.curselection()
            if selection:
                self.goto(entries[selection[0]][2])
                win.destroy()

        listbox.bind("<Double-Button-1>", jump)
        listbox.bind("<Return>", jump)
        listbox.focus_set()

    # ------------------------------------------------------------ status

    def _update_status(self):
        self._set_status("{}/{}".format(self.page + 1, self.doc.page_count))
        self._update_controls()

    def _set_status(self, text: str):
        self.status.configure(text=text, fg=DIM)

    def _flash(self, message: str, milliseconds: int = 1600):
        self.status.configure(text=message, fg=ACCENT)
        if self._flash_job:
            self.root.after_cancel(self._flash_job)
        self._flash_job = self.root.after(milliseconds, self._update_status)

    # -------------------------------------------------------------- exit

    def _autosave(self):
        """Write state periodically.

        Closing the window saves properly, but a Ctrl+C in the terminal or a
        machine that goes down mid training run would otherwise lose your
        place. Only writes when something actually changed.
        """
        signature = (self.page, round(self.opacity, 3), self.invert, self.fit)
        if signature != getattr(self, "_saved_signature", None):
            self.save_state()
            self._saved_signature = signature
        self.root.after(20000, self._autosave)

    def save_state(self):
        if not self.remember:
            return
        try:
            geometry = "{}x{}+{}+{}".format(
                self.root.winfo_width(),
                self._rolled_height if self.rolled_up else self.root.winfo_height(),
                self.root.winfo_x(), self.root.winfo_y())
        except tk.TclError:
            geometry = None
        state_store.save(self.doc.path, {
            "page": self.page,
            "zoom": self.current_zoom,
            "fit": self.fit,
            "opacity": self.opacity,
            "invert": self.invert,
            "halo": self.halo_width,
            "geometry": geometry,
        })

    def quit(self):
        self.save_state()
        last_rect = self._window_rect()
        self._hide_escape_panel()
        if self.click_through:
            winext.set_click_through(self.root, False)
        if self.ghost:
            try:
                self.root.attributes("-transparentcolor", "")
            except tk.TclError:
                pass
        self.hotkey.unregister()
        self.doc.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        # Closing uncovers the whole window area at once, and by then there is
        # no window left to ask for a repaint, so do it here.
        self._repaint_vacated(last_rect, immediate=True)


# --------------------------------------------------------------- helpers


def enable_dpi_awareness():
    """Stop Windows from scaling the window into a blurry mess."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def pick_file(initial_dir=None):
    """Show a file chooser and return the selected path, or None."""
    chooser = tk.Tk()
    chooser.withdraw()
    try:
        chooser.attributes("-topmost", True)
    except tk.TclError:
        pass
    path = filedialog.askopenfilename(
        title="Open a PDF to float on top",
        initialdir=initial_dir or os.path.expanduser("~"),
        filetypes=[("PDF and ebooks", "*.pdf *.epub *.xps *.cbz *.fb2"),
                   ("All files", "*.*")],
    )
    chooser.destroy()
    return path or None


def run(opts) -> int:
    enable_dpi_awareness()

    path = opts.pdf
    if not path:
        path = pick_file()
        if not path:
            print("No file chosen.")
            return 1

    try:
        doc = PdfDocument(path, password=opts.password)
    except PdfError as exc:
        print("ghostread: {}".format(exc), file=sys.stderr)
        return 2

    saved = {} if opts.no_remember else state_store.load(doc.path)
    if opts.page is not None:
        saved["page"] = opts.page - 1
    if opts.opacity is not None:
        saved["opacity"] = opts.opacity
    if opts.zoom is not None:
        saved["zoom"] = opts.zoom
        saved["fit"] = "free"
    if opts.fit:
        saved["fit"] = opts.fit
    if opts.invert:
        saved["invert"] = True

    root = tk.Tk()
    reader = GhostReader(root, doc, opts, saved)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        reader.quit()
    return 0
