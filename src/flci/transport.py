"""Serial transport for the Flipper Zero USB CLI.

Knows nothing about Flipper commands; it only knows how to talk to a line-oriented
shell whose prompt ends in ``>: `` (verified: lib/toolbox/cli/shell/cli_shell_line.c
formats the prompt as ``"%s>: "``). Every read has a deadline and raises FlciTimeout.
"""

from __future__ import annotations

import logging
import re
import time
from types import TracebackType

import serial

from flci.errors import FlciTimeout

log = logging.getLogger(__name__)

PROMPT = ">: "
CTRL_C = b"\x03"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


class SerialTransport:
    """One open serial connection to one Flipper."""

    def __init__(self, port: str, name: str | None = None, baudrate: int = 230400):
        # Baud rate is ignored by USB CDC but pyserial wants one.
        self.port = port
        self.name = name or port
        self.baudrate = baudrate
        self._ser: serial.Serial | None = None
        self._streaming_cmd: str | None = None

    # -- lifecycle ---------------------------------------------------------------

    def open(self, timeout_s: float = 5.0) -> None:
        self._ser = serial.Serial(self.port, self.baudrate, timeout=0.05, write_timeout=2.0)
        self.reset(timeout_s)

    def close(self) -> None:
        if self._ser is not None:
            try:
                if self._streaming_cmd is not None:
                    self._ser.write(CTRL_C)
            finally:
                self._ser.close()
                self._ser = None
                self._streaming_cmd = None

    def __enter__(self) -> SerialTransport:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def ser(self) -> serial.Serial:
        if self._ser is None:
            raise RuntimeError(f"[{self.name}] transport is not open")
        return self._ser

    # -- primitives --------------------------------------------------------------

    def reset(self, timeout_s: float = 5.0) -> None:
        """Get back to a clean prompt: interrupt anything running, drain, re-prompt."""
        self.ser.write(CTRL_C)
        time.sleep(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\r")
        self._read_until(PROMPT, timeout_s, command="<reset>")
        self._streaming_cmd = None

    def _read_until(self, marker: str, timeout_s: float, command: str) -> str:
        deadline = time.monotonic() + timeout_s
        buf = bytearray()
        needle = marker.encode()
        while time.monotonic() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if needle in buf:
                    return buf.decode("utf-8", errors="replace")
        raise FlciTimeout(self.name, command, marker, timeout_s, buf.decode(errors="replace"))

    def _send_line(self, command: str) -> None:
        log.debug("[%s] >> %s", self.name, command)
        self.ser.write(command.encode() + b"\r")

    @staticmethod
    def _clean(raw: str, command: str) -> str:
        """Drop the echoed command line and the trailing prompt; normalise newlines."""
        text = strip_ansi(raw).replace("\r\n", "\n").replace("\r", "\n")
        if PROMPT in text:
            text = text[: text.rfind(PROMPT)]
            # the prompt prefix (e.g. a subshell name) sits on the last line; drop it
            text = text[: text.rfind("\n") + 1] if "\n" in text else ""
        lines = text.split("\n")
        if lines and lines[0].strip() == command.strip():
            lines = lines[1:]
        return "\n".join(lines).strip("\n")

    # -- public API --------------------------------------------------------------

    def run(self, command: str, timeout_s: float = 5.0) -> str:
        """Run a command that returns on its own; return its output without echo/prompt."""
        if self._streaming_cmd is not None:
            raise RuntimeError(f"[{self.name}] still streaming {self._streaming_cmd!r}")
        self._send_line(command)
        raw = self._read_until(PROMPT, timeout_s, command)
        out = self._clean(raw, command)
        log.debug("[%s] << %s", self.name, out)
        return out

    def start_stream(self, command: str, ready_marker: str, timeout_s: float = 5.0) -> str:
        """Start a long-running command (e.g. a receiver) and wait until it says it's ready."""
        self._send_line(command)
        head = self._read_until(ready_marker, timeout_s, command)
        self._streaming_cmd = command
        return strip_ansi(head)

    def stop_stream(self, timeout_s: float = 5.0) -> str:
        """Send Ctrl+C to the running command and return everything it printed."""
        command = self._streaming_cmd or "<stream>"
        self.ser.write(CTRL_C)
        raw = self._read_until(PROMPT, timeout_s, command + " (Ctrl+C)")
        self._streaming_cmd = None
        return self._clean(raw, command)
