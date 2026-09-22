"""Capture only the visible foreground PoE client area, without game input."""
import ctypes
import sys
from ctypes import wintypes

import mss
import numpy as np

from .i18n import t


def enable_dpi_awareness():
    if sys.platform == 'win32':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except OSError:
            pass


def capture_game():
    if sys.platform != 'win32':
        raise RuntimeError(t('error.windows_only'))
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    hwnd = user.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    user.GetWindowTextW(hwnd, title, 512)
    if 'path of exile' not in title.value.lower():
        return None
    rect, origin = wintypes.RECT(), wintypes.POINT()
    if not user.GetClientRect(hwnd, ctypes.byref(rect)) or not user.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    if rect.right < 800 or rect.bottom < 600:
        return None
    with mss.mss() as screen:
        shot = screen.grab(dict(left=origin.x, top=origin.y, width=rect.right, height=rect.bottom))
    return np.asarray(shot)[:, :, :3].copy()
