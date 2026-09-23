"""Exception types. Every error names the device, the command, and expected vs got."""

from __future__ import annotations


class FlciError(Exception):
    """Base class for all harness errors."""


class FlciTimeout(FlciError):
    """A serial read did not see what it was waiting for in time."""

    def __init__(self, device: str, command: str, waiting_for: str, timeout_s: float, got: str):
        self.device = device
        self.command = command
        self.waiting_for = waiting_for
        self.timeout_s = timeout_s
        self.got = got
        tail = got[-400:] if got else "<nothing>"
        super().__init__(
            f"[{device}] timeout after {timeout_s:.1f}s running {command!r}: "
            f"expected {waiting_for!r}, got: {tail!r}"
        )


class FlciCommandError(FlciError):
    """The device answered, but not the way the command should have."""

    def __init__(self, device: str, command: str, expected: str, got: str):
        self.device = device
        self.command = command
        self.expected = expected
        self.got = got
        super().__init__(f"[{device}] {command!r} failed: expected {expected}, got: {got[-400:]!r}")
