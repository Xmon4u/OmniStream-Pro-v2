"""Crisp line icons for the OmniStream Pro window. No emoji."""

import os
from PIL import Image, ImageDraw, ImageTk

_STROKE = (226, 232, 240, 255)


def _new(size, scale=4):
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image), canvas, max(2, scale)


def _down(image, size):
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _round_rect(draw, box, radius, width, color):
    draw.rounded_rectangle(box, radius=radius, outline=color, width=width)


def icon_chrome(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    pad = int(s * 0.14)
    _round_rect(draw, [pad, pad, s - pad, s - pad], int(s * 0.16), w, color)
    draw.line([(pad, int(s * 0.36)), (s - pad, int(s * 0.36))], fill=color, width=w)
    draw.ellipse([int(s * 0.62), int(s * 0.16), int(s * 0.74), int(s * 0.28)], fill=color)
    return _down(image, size)


def icon_extension(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    a, b = int(s * 0.16), int(s * 0.46)
    c, d = int(s * 0.54), int(s * 0.84)
    r = int(s * 0.08)
    _round_rect(draw, [a, a, b, b], r, w, color)
    _round_rect(draw, [c, a, d, b], r, w, color)
    _round_rect(draw, [a, c, b, d], r, w, color)
    _round_rect(draw, [c, c, d, d], r, w, color)
    return _down(image, size)


def icon_folder(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    pad = int(s * 0.14)
    _round_rect(draw, [pad, int(s * 0.34), s - pad, s - pad], int(s * 0.1), w, color)
    draw.polygon(
        [
            (pad, int(s * 0.38)),
            (pad, int(s * 0.24)),
            (int(s * 0.42), int(s * 0.24)),
            (int(s * 0.52), int(s * 0.36)),
        ],
        outline=color,
    )
    draw.line(
        [(pad + w, int(s * 0.36)), (int(s * 0.5), int(s * 0.36))],
        fill=color,
        width=w,
    )
    return _down(image, size)


def icon_download(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    mid = s // 2
    draw.line([(mid, int(s * 0.16)), (mid, int(s * 0.62))], fill=color, width=w)
    draw.line([(int(s * 0.30), int(s * 0.46)), (mid, int(s * 0.64)), (int(s * 0.70), int(s * 0.46))], fill=color, width=w, joint="curve")
    draw.line([(int(s * 0.22), int(s * 0.78)), (int(s * 0.78), int(s * 0.78))], fill=color, width=w)
    return _down(image, size)


def icon_play(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    draw.polygon(
        [(int(s * 0.30), int(s * 0.18)), (int(s * 0.30), int(s * 0.82)), (int(s * 0.78), s // 2)],
        outline=color,
    )
    draw.line([(int(s * 0.32), int(s * 0.24)), (int(s * 0.72), s // 2), (int(s * 0.32), int(s * 0.76)), (int(s * 0.32), int(s * 0.24))], fill=color, width=w)
    return _down(image, size)


def icon_stop(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    pad = int(s * 0.26)
    _round_rect(draw, [pad, pad, s - pad, s - pad], int(s * 0.08), w, color)
    return _down(image, size)


def icon_paste(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    _round_rect(draw, [int(s * 0.28), int(s * 0.22), int(s * 0.84), int(s * 0.86)], int(s * 0.08), w, color)
    _round_rect(draw, [int(s * 0.38), int(s * 0.12), int(s * 0.74), int(s * 0.30)], int(s * 0.06), w, color)
    return _down(image, size)


def icon_terminal(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    pad = int(s * 0.14)
    _round_rect(draw, [pad, pad, s - pad, s - pad], int(s * 0.12), w, color)
    draw.line([(int(s * 0.28), int(s * 0.42)), (int(s * 0.42), int(s * 0.54)), (int(s * 0.28), int(s * 0.66))], fill=color, width=w)
    draw.line([(int(s * 0.50), int(s * 0.66)), (int(s * 0.72), int(s * 0.66))], fill=color, width=w)
    return _down(image, size)


def icon_stream(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    bars = (0.28, 0.46, 0.64)
    heights = (0.55, 0.78, 0.42)
    for x, h in zip(bars, heights):
        left = int(s * x)
        top = int(s * (0.86 - h))
        draw.rounded_rectangle([left, top, left + int(s * 0.1), int(s * 0.82)], radius=int(s * 0.05), outline=color, width=w)
    return _down(image, size)


def icon_check(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    draw.line(
        [(int(s * 0.18), int(s * 0.52)), (int(s * 0.40), int(s * 0.74)), (int(s * 0.82), int(s * 0.28))],
        fill=color,
        width=w + 1,
    )
    return _down(image, size)


def icon_queue(size=18, color=_STROKE):
    image, draw, s, w = _new(size)
    for y in (0.28, 0.48, 0.68):
        draw.ellipse([int(s * 0.16), int(s * y), int(s * 0.28), int(s * y) + int(s * 0.12)], outline=color, width=w)
        draw.line([(int(s * 0.38), int(s * y) + int(s * 0.06)), (int(s * 0.82), int(s * y) + int(s * 0.06))], fill=color, width=w)
    return _down(image, size)


def icon_close(size=16, color=_STROKE):
    image, draw, s, w = _new(size)
    draw.line([(int(s * 0.28), int(s * 0.28)), (int(s * 0.72), int(s * 0.72))], fill=color, width=w)
    draw.line([(int(s * 0.72), int(s * 0.28)), (int(s * 0.28), int(s * 0.72))], fill=color, width=w)
    return _down(image, size)


def icon_globe(size=16, color=_STROKE):
    image, draw, s, w = _new(size)
    pad = int(s * 0.16)
    draw.ellipse([pad, pad, s - pad, s - pad], outline=color, width=w)
    draw.arc([int(s * 0.34), pad, int(s * 0.66), s - pad], 0, 360, fill=color, width=w)
    draw.line([(pad, s // 2), (s - pad, s // 2)], fill=color, width=w)
    return _down(image, size)


def _ctk(image, size):
    import customtkinter as ctk
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


def build_icon_set(base_dir):
    """Return named CTkImage icons. Keep the returned dict alive on the window."""
    specs = {
        "chrome": (icon_chrome, 16),
        "extension": (icon_extension, 16),
        "folder": (icon_folder, 16),
        "folder_sm": (icon_folder, 14),
        "download": (icon_download, 16),
        "play": (icon_play, 16),
        "stop": (icon_stop, 15),
        "paste": (icon_paste, 15),
        "terminal": (icon_terminal, 15),
        "stream": (icon_stream, 16),
        "check": (icon_check, 16),
        "queue": (icon_queue, 15),
        "close": (icon_close, 14),
        "globe": (icon_globe, 15),
    }
    icons = {name: _ctk(fn(size), size) for name, (fn, size) in specs.items()}

    logo_path = os.path.join(base_dir, "app_icon.png")
    if os.path.isfile(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        icons["logo"] = _ctk(logo, 48)
        icons["logo_sm"] = _ctk(logo, 36)
    return icons


def apply_window_icon(window, base_dir):
    """Show the OmniStream mark on the title bar and taskbar."""
    ico = os.path.join(base_dir, "app_icon.ico")
    png = os.path.join(base_dir, "app_icon.png")
    if os.path.isfile(ico):
        try:
            window.iconbitmap(ico)
        except Exception:
            pass
    if os.path.isfile(png):
        try:
            photo = ImageTk.PhotoImage(Image.open(png).resize((64, 64), Image.Resampling.LANCZOS))
            window.iconphoto(True, photo)
            window._omni_icon_photo = photo
        except Exception:
            pass
