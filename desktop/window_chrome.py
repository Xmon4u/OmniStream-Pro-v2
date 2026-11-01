"""Borderless rounded window frame for OmniStream Pro on Windows with C++/C# grade smoothness."""

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SW_MINIMIZE = 6
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SPI_GETWORKAREA = 0x0030

user32.GetWindowLongPtrW.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
user32.SetWindowRgn.restype = ctypes.c_int
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.SystemParametersInfoW.restype = wintypes.BOOL
gdi32.CreateRoundRectRgn.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
]
gdi32.CreateRoundRectRgn.restype = wintypes.HRGN


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def window_hwnd(widget):
    widget.update_idletasks()
    child = widget.winfo_id()
    parent = user32.GetParent(child)
    return parent or child


class RoundedFrame:
    """Removes the system title bar and clips the window to rounded corners."""

    def __init__(self, window, radius=18, edge=8):
        self.window = window
        self.radius = radius
        self.edge = edge
        self.hwnd = None
        self.maximized = False
        self._restore_geom = None
        self._drag = None
        self._region_key = None
        self._in_configure = False

    def install(self):
        self.window.overrideredirect(True)
        self.window.update_idletasks()
        self.hwnd = window_hwnd(self.window)
        self._show_on_taskbar()
        self.apply_region()
        self.window.bind("<Configure>", self._on_configure, add="+")

    def uninstall(self):
        """Clean teardown hook before window destruction."""
        pass

    def _show_on_taskbar(self):
        if not self.hwnd:
            return
        style = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE) or 0
        style = (int(style) & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ctypes.c_void_p(style))
        user32.SetWindowPos(
            self.hwnd, 0, 0, 0, 0, 0,
            SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
        )
        try:
            dwmapi = ctypes.windll.dwmapi
            dark_mode = ctypes.c_int(1)
            if dwmapi.DwmSetWindowAttribute(self.hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode)) != 0:
                dwmapi.DwmSetWindowAttribute(self.hwnd, 19, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        except Exception:
            pass

    def apply_region(self, width=None, height=None, redraw=True):
        if not self.hwnd:
            return
        if self.maximized:
            # When maximized, remove rounded region so window fills screen corners cleanly
            if self._region_key == "maximized":
                return
            self._region_key = "maximized"
            user32.SetWindowRgn(self.hwnd, 0, redraw)
            return

        w = width if width is not None else self.window.winfo_width()
        h = height if height is not None else self.window.winfo_height()
        w = max(int(w), 1)
        h = max(int(h), 1)
        key = (w, h, self.radius)
        if key == self._region_key:
            return
        self._region_key = key
        region = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, self.radius * 2, self.radius * 2)
        if region:
            user32.SetWindowRgn(self.hwnd, region, redraw)

    def _on_configure(self, event):
        if event.widget is not self.window:
            return
        if getattr(self, "_in_configure", False):
            return
        self._in_configure = True
        try:
            self.apply_region(width=event.width, height=event.height, redraw=False)
        finally:
            self._in_configure = False

    def bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._press, add="+")
        widget.bind("<B1-Motion>", self._drag_move, add="+")
        widget.bind("<Double-Button-1>", lambda _e: self.toggle_max(), add="+")

    def _press(self, event):
        if self.maximized:
            return
        self._drag = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _drag_move(self, event):
        if self.maximized or not self._drag:
            return
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        self.window.geometry(f"+{x}+{y}")

    def minimize(self):
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_MINIMIZE)

    def toggle_max(self):
        if not self.hwnd:
            return
        self._in_configure = True
        try:
            if self.maximized:
                self.maximized = False
                if self._restore_geom:
                    self.window.geometry(self._restore_geom)
                self.window.update_idletasks()
                self.apply_region(redraw=True)
            else:
                self._restore_geom = self.window.geometry()
                area = RECT()
                user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(area), 0)
                width = area.right - area.left
                height = area.bottom - area.top
                self.maximized = True
                self.window.geometry(f"{width}x{height}+{area.left}+{area.top}")
                self.window.update_idletasks()
                self.apply_region(width=width, height=height, redraw=True)
        finally:
            self._in_configure = False
            if hasattr(self.window, "_caption_max"):
                try:
                    self.window._caption_max.configure(text="\uE923" if self.maximized else "\uE922")
                except Exception:
                    pass

    def close(self):
        self.window.event_generate("<<WindowClose>>")
