"""Capture keystrokes from a USB HID keyboard on the host (Linux, via evdev).

Used as the "counterpart" for BadUSB: the DUT types, the host is the target. The device is
grabbed exclusively so its keystrokes never reach the runner's own terminal or desktop.
"""

from __future__ import annotations

import sys
import time
from typing import Any

# US layout, evdev KEY_* name -> (unshifted, shifted)
_US = {
    **{f"KEY_{c}": (c.lower(), c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    **dict(
        zip(
            [f"KEY_{d}" for d in "1234567890"],
            zip("1234567890", "!@#$%^&*()", strict=True),
            strict=True,
        )
    ),
    "KEY_SPACE": (" ", " "),
    "KEY_ENTER": ("\n", "\n"),
    "KEY_TAB": ("\t", "\t"),
    "KEY_MINUS": ("-", "_"),
    "KEY_EQUAL": ("=", "+"),
    "KEY_LEFTBRACE": ("[", "{"),
    "KEY_RIGHTBRACE": ("]", "}"),
    "KEY_BACKSLASH": ("\\", "|"),
    "KEY_SEMICOLON": (";", ":"),
    "KEY_APOSTROPHE": ("'", '"'),
    "KEY_GRAVE": ("`", "~"),
    "KEY_COMMA": (",", "<"),
    "KEY_DOT": (".", ">"),
    "KEY_SLASH": ("/", "?"),
}
_SHIFT = {"KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"}


class HidCaptureUnavailable(RuntimeError):
    pass


def _evdev() -> Any:
    if not sys.platform.startswith("linux"):
        raise HidCaptureUnavailable("HID capture needs Linux evdev")
    try:
        import evdev
    except ImportError as e:  # pragma: no cover - depends on host
        raise HidCaptureUnavailable("pip install 'flipper-loopback[badusb]' (evdev)") from e
    return evdev


def find_keyboard(vid: int, pid: int, timeout_s: float = 30.0) -> Any:
    evdev = _evdev()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for path in evdev.list_devices():
            dev = evdev.InputDevice(path)
            if dev.info.vendor == vid and dev.info.product == pid:
                return dev
            dev.close()
        time.sleep(0.25)
    raise TimeoutError(f"no HID keyboard {vid:04X}:{pid:04X} appeared within {timeout_s}s")


def capture_text(dev: Any, first_key_timeout_s: float = 60.0, idle_s: float = 3.0) -> str:
    """Read keys until ``idle_s`` of silence after the first key. Returns the typed text."""
    evdev = _evdev()
    ecodes = evdev.ecodes
    dev.grab()
    out: list[str] = []
    shift = False
    started = time.monotonic()
    last = None
    try:
        while True:
            now = time.monotonic()
            if last is None and now - started > first_key_timeout_s:
                break
            if last is not None and now - last > idle_s:
                break
            event = dev.read_one()
            if event is None:
                time.sleep(0.01)
                continue
            if event.type != ecodes.EV_KEY:
                continue
            name = ecodes.KEY.get(event.code)
            name = name[0] if isinstance(name, list) else name
            if name in _SHIFT:
                shift = event.value != 0
                continue
            if event.value == 1 and name in _US:  # key down only
                out.append(_US[name][1 if shift else 0])
                last = time.monotonic()
    finally:
        dev.ungrab()
    return "".join(out)
