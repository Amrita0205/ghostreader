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

HOTKEY_ID = 0xB00C


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

    try:
        user32 = _user32()
        user32.GetWindowLongW.restype = ctypes.c_long
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
        return True
    except Exception:
        return False


class GlobalHotkey:
    """Ctrl+Alt+G, registered against the calling thread's message queue.

    Tk runs its main loop on the same thread that creates the window, so
    polling the queue from a Tk `after` callback picks the message up.
    """

    def __init__(self, callback, modifiers=MOD_CONTROL | MOD_ALT, vk=0x47):
        self.callback = callback
        self.modifiers = modifiers
        self.vk = vk
        self.registered = False
        self._msg = None

    def register(self) -> bool:
        if not IS_WINDOWS:
            return False
        import ctypes
        from ctypes import wintypes

        try:
            user32 = _user32()
            ok = user32.RegisterHotKey(
                None, HOTKEY_ID, self.modifiers | MOD_NOREPEAT, self.vk
            )
            if not ok:
                return False
            self._msg = wintypes.MSG()
            self.registered = True
            return True
        except Exception:
            return False

    def poll(self) -> None:
        """Drain any pending hotkey messages. Cheap enough to call often."""
        if not self.registered:
            return
        import ctypes

        try:
            user32 = _user32()
            while user32.PeekMessageW(
                ctypes.byref(self._msg), None, 0, 0, PM_REMOVE
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
