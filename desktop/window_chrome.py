"""Borderless rounded window frame for OmniStream Pro on Windows."""

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_WNDPROC = -4
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
WM_NCHITTEST = 0x0084
SW_MINIMIZE = 6
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SPI_GETWORKAREA = 0x0030

HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

user32.GetWindowLongPtrW.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
user32.CallWindowProcW.restype = LRESULT
user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
user32.SetWindowRgn.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
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
        self._old_proc = None
        self._proc_ref = None
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
        self._hook_hit_test()
        self.apply_region()
        self.window.bind("<Configure>", self._on_configure, add="+")

    def _show_on_taskbar(self):
        style = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE) or 0
        style = (int(style) & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ctypes.c_void_p(style))
        user32.SetWindowPos(
            self.hwnd, 0, 0, 0, 0, 0,
            SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
        )

    def _hook_hit_test(self):
        old = user32.GetWindowLongPtrW(self.hwnd, GWL_WNDPROC)
        if not old:
            return
        self._old_proc = ctypes.c_void_p(old)

        def _proc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_NCHITTEST and not self.maximized:
                    hit = self._edge_hit(lparam)
                    if hit:
                        return hit
            except Exception:
                pass
            return user32.CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)

        self._proc_ref = WNDPROC(_proc)
        user32.SetWindowLongPtrW(self.hwnd, GWL_WNDPROC, ctypes.cast(self._proc_ref, ctypes.c_void_p))

    def _edge_hit(self, lparam):
        try:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            rect = RECT()
            if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
                return 0
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            local_x = x - rect.left
            local_y = y - rect.top
            edge = self.edge
            left = local_x <= edge
            right = local_x >= width - edge
            top = local_y <= edge
            bottom = local_y >= height - edge
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        except Exception:
            pass
        return 0

    def apply_region(self):
        if not self.hwnd:
            return
        if self.maximized:
            # When maximized, remove rounded region so window fills screen corners without gaps
            if self._region_key == "maximized":
                return
            self._region_key = "maximized"
            user32.SetWindowRgn(self.hwnd, 0, True)
            return

        width = max(self.window.winfo_width(), 1)
        height = max(self.window.winfo_height(), 1)
        key = (width, height, self.radius)
        if key == self._region_key:
            return
        self._region_key = key
        region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, self.radius * 2, self.radius * 2)
        if region:
            user32.SetWindowRgn(self.hwnd, region, True)

    def _on_configure(self, event):
        if event.widget is not self.window:
            return
        if getattr(self, "_in_configure", False):
            return
        self._in_configure = True
        try:
            self.apply_region()
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
        if self.maximized:
            self.maximized = False
            self.apply_region()
            if self._restore_geom:
                self.window.geometry(self._restore_geom)
        else:
            self._restore_geom = self.window.geometry()
            area = RECT()
            user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(area), 0)
            width = area.right - area.left
            height = area.bottom - area.top
            self.maximized = True
            self.apply_region()
            self.window.geometry(f"{width}x{height}+{area.left}+{area.top}")

    def close(self):
        self.window.event_generate("<<WindowClose>>")
