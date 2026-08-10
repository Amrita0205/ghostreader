"""Windows extras: click-through mode and a global hotkey to escape it.

Everything here degrades to a harmless no-op on Linux and macOS, so the rest
of the app never has to check the platform.

Click-through means mouse clicks pass straight through the overlay to the
window underneath, so you can keep typing in your editor while the page stays
visible on top. The catch is that you can no longer click the overlay to turn
it back off, which is why this module refuses to enable click-through unless a
global hotkey has been registered first.
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform.startswith("win")

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001

# RedrawWindow flags, used to scrub the trail a layered window leaves behind.
RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100
RDW_FRAME = 0x0400

# SetWindowPos flags. SWP_FRAMECHANGED is the one that matters: Windows caches
# window data and an extended style change is not committed until it sees it.
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

HOTKEY_ID = 0xB00C

# Tried in order. A combination can already be taken, by another application
# or simply by a second GhostRead, and RegisterHotKey then fails outright, so
# there has to be somewhere else to go.
HOTKEY_CANDIDATES = (
    (MOD_CONTROL | MOD_ALT, 0x47, "Ctrl+Alt+G"),
    (MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x47, "Ctrl+Alt+Shift+G"),
    (MOD_CONTROL | MOD_ALT, 0x4B, "Ctrl+Alt+K"),
    (MOD_CONTROL | MOD_ALT, 0x51, "Ctrl+Alt+Q"),
)


def _user32():
    if not IS_WINDOWS:
        return None
    import ctypes

    return ctypes.windll.user32


def top_level_hwnd(tk_window) -> int:
    """Walk up from the Tk window id to the real top level frame."""
    if not IS_WINDOWS:
        return 0
    user32 = _user32()
    hwnd = tk_window.winfo_id()
    for _ in range(6):
        parent = user32.GetParent(hwnd)
        if not parent:
            break
        hwnd = parent
    return hwnd


def set_click_through(tk_window, enabled: bool) -> bool:
    """Turn mouse pass-through on or off. Returns True if it took effect."""
    if not IS_WINDOWS:
        return False
    import ctypes

    from ctypes import wintypes

    try:
        user32 = _user32()
        # Without argtypes ctypes marshals the handle as a C int, which is 32
        # bit, and a 64 bit HWND would be silently truncated.
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long

        hwnd = top_level_hwnd(tk_window)
        if not hwnd:
            return False
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enabled:
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
            style |= WS_EX_LAYERED
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        # Commit the style change. SetWindowLong alone leaves it in a cache.
        user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            | SWP_FRAMECHANGED,
        )
        return True
    except Exception:
        return False


def repaint_desktop(rect=None, immediate: bool = True) -> None:
    """Force whatever sits under the overlay to repaint itself.

    A layered window, and a colour keyed one especially, does not cause the
    windows beneath it to invalidate when it moves. Nothing asks the desktop
    to redraw the area the overlay just left, so the overlay's last painted
    pixels stay on screen and it looks like a second copy of the window.

    ``rect`` is an ``(x, y, width, height)`` screen rectangle, or None for the
    whole desktop. Passing NULL as the window handle targets the desktop, and
    RDW_ALLCHILDREN carries the invalidation into the top level windows
    sitting on it.
    """
    if not IS_WINDOWS:
        return
    import ctypes
    from ctypes import wintypes

    try:
        user32 = _user32()
        user32.RedrawWindow.argtypes = [
            wintypes.HWND, ctypes.c_void_p, wintypes.HRGN, wintypes.UINT,
        ]
        user32.RedrawWindow.restype = wintypes.BOOL

        flags = RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_FRAME
        if immediate:
            flags |= RDW_UPDATENOW

        if rect is None:
            user32.RedrawWindow(None, None, None, flags)
            return

        x, y, width, height = (int(value) for value in rect)
        # A couple of pixels of slack covers any drop shadow or rounding.
        box = wintypes.RECT(x - 2, y - 2, x + width + 2, y + height + 2)
        user32.RedrawWindow(None, ctypes.byref(box), None, flags)
    except Exception:
        pass


class GlobalHotkey:
    """Ctrl+Alt+G, registered against the calling thread's message queue.

    Tk runs its main loop on the same thread that creates the window, so
    polling the queue from a Tk `after` callback picks the message up.
    """

    def __init__(self, callback, candidates=HOTKEY_CANDIDATES):
        self.callback = callback
        self.candidates = tuple(candidates)
        self.registered = False
        # What to tell the user to press. Correct only once something has
        # actually been claimed, but a sensible thing to show before that.
        self.label = self.candidates[0][2]
        self._msg = None

    def register(self) -> bool:
        """Claim the first combination nothing else is holding."""
        if not IS_WINDOWS:
            return False
        import ctypes
        from ctypes import wintypes

        try:
            user32 = _user32()
            for modifiers, vk, label in self.candidates:
                ok = user32.RegisterHotKey(
                    None, HOTKEY_ID, modifiers | MOD_NOREPEAT, vk
                )
                if ok:
                    self.label = label
                    self._msg = wintypes.MSG()
                    self.registered = True
                    return True
            return False
        except Exception:
            return False

    def poll(self) -> None:
        """Take any pending hotkey presses off the queue.

        The filter arguments matter. Peeking with a range of 0 to 0 asks for
        *every* message on the thread, and PM_REMOVE then throws away ones Tk
        needed. It also never terminates if the window has an invalid region,
        because WM_PAINT is regenerated for as long as that region stays
        invalid and discarding the message does nothing to validate it. Asking
        only for WM_HOTKEY leaves everything else where Tk can still find it.
        """
        if not self.registered:
            return
        import ctypes

        try:
            user32 = _user32()
            while user32.PeekMessageW(
                ctypes.byref(self._msg), None, WM_HOTKEY, WM_HOTKEY, PM_REMOVE
            ):
                if self._msg.message == WM_HOTKEY and self._msg.wParam == HOTKEY_ID:
                    self.callback()
        except Exception:
            pass

    def unregister(self) -> None:
        if not self.registered:
            return
        try:
            _user32().UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            pass
        self.registered = False


def hide_from_taskbar(tk_window) -> None:
    """Mark the overlay as a tool window so it stays out of Alt+Tab."""
    if not IS_WINDOWS:
        return
    try:
        user32 = _user32()
        hwnd = top_level_hwnd(tk_window)
        if not hwnd:
            return
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW)
    except Exception:
        pass
