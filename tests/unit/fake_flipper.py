"""A scripted stand-in for the Flipper CLI, for OFFLINE orchestration tests only.

It speaks the same wire protocol (echo, ``>: `` prompt, Ctrl+C) and passes "signals"
between two fakes through a shared ``Air`` object. It proves the harness sends the right
commands in the right order and parses the replies. It proves nothing about radios, and
results from it are never reported as hardware passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PROMPT = b"\r\n>: "


@dataclass
class Air:
    subghz: list[str] = field(default_factory=list)
    ir: list[str] = field(default_factory=list)
    presented: dict[str, str] = field(default_factory=dict)  # ibutton/rfid/nfc -> line
    wires: dict[str, int] = field(default_factory=dict)
    log: list[tuple[str, str]] = field(default_factory=list)  # (device, command), both sides


class FakeFlipper:
    def __init__(
        self,
        name: str,
        air: Air,
        fw: str = "1.4.0",
        commands: set[str] | None = None,
        region_blocked_hz: set[int] | None = None,
    ):
        self.name, self.air, self.fw = name, air, fw
        self.cli_commands = commands or {
            "help", "device_info", "info", "subghz", "ir", "ikey", "rfid",
            "nfc", "gpio", "storage", "loader", "input", "update",
        }  # fmt: skip
        self.region_blocked_hz = region_blocked_hz or set()
        self.out = bytearray()
        self.line = bytearray()
        self.stream: str | None = None
        self.stream_start = 0
        self.commands: list[str] = []
        self.files: dict[str, bytes] = {}
        self.pending_upload: tuple[str, int] | None = None
        self.pins: dict[str, str] = {}

    # pyserial surface ------------------------------------------------------------
    def __call__(self, *_: Any, **__: Any) -> FakeFlipper:  # used as serial_factory
        return self

    @property
    def in_waiting(self) -> int:
        return len(self.out)

    def read(self, n: int = 1) -> bytes:
        data, self.out = bytes(self.out[:n]), self.out[n:]
        return data

    def reset_input_buffer(self) -> None:
        self.out.clear()

    def close(self) -> None:
        pass

    def write(self, data: bytes) -> int:
        if self.pending_upload:
            path, size = self.pending_upload
            self.files[path] = self.files.get(path, b"") + data
            if len(self.files[path]) >= size:
                self.pending_upload = None
                self.out += PROMPT
            return len(data)
        for b in data:
            if b == 0x03:
                self._ctrl_c()
            elif b == 0x0D:
                cmd = self.line.decode()
                self.line.clear()
                self._command(cmd)
            else:
                self.line.append(b)
        return len(data)

    # behaviour -------------------------------------------------------------------
    def _ctrl_c(self) -> None:
        if self.stream == "subghz rx":
            self.out += "".join(self.air.subghz[self.stream_start :]).encode()
            self.out += b"\r\nPackets received 1\r\n"
        elif self.stream == "ir rx":
            self.out += "".join(self.air.ir[self.stream_start :]).encode()
        elif self.stream and self.stream.startswith("present:"):
            self.air.presented.pop(self.stream.split(":", 1)[1], None)
        if self.stream is not None:
            self.stream = None
            self.out += PROMPT
        # a bare Ctrl+C at the prompt prints nothing

    def _command(self, cmd: str) -> None:
        self.out += cmd.encode() + b"\r\n"
        if not cmd:
            self.out += b">: "
            return
        self.commands.append(cmd)
        self.air.log.append((self.name, cmd))
        reply = self._reply(cmd)
        if reply is not None:
            self.out += reply.encode() + PROMPT

    def _reply(self, cmd: str) -> str | None:  # noqa: C901 - a flat dispatch table
        if cmd == "help":
            names = "".join(f"{c:<30}" for c in sorted(self.cli_commands))
            return f"Available commands:\r\n{names}\r\nFind out more: https://docs.flipper.net"
        if cmd == "info power":
            return f"{'charge.level':<30}: 87\r\n{'battery.voltage':<30}: 4012"
        if cmd.split()[0] not in self.cli_commands:
            return f"`{cmd.split()[0]}` command not found"
        if cmd == "device_info":
            return f"{'hardware_name':<30}: {self.name}\r\n{'firmware_version':<30}: {self.fw}"
        if m := re.fullmatch(r"subghz tx ([0-9A-F]{6}) (\d+) \d+ \d+ \d", cmd):
            self.air.subghz.append(f"Princeton 24bit\r\nKey:0x00{m.group(1)}\r\n")
            return f"Transmitting at {m.group(2)}, key {m.group(1).lower()}..."
        if cmd.startswith("subghz rx "):
            self.stream, self.stream_start = "subghz rx", len(self.air.subghz)
            self.out += b"Listening at frequency: 433920000 device: 0. Press CTRL+C to stop\r\n"
            return None
        if m := re.fullmatch(r"subghz tx_from_file (\S+) \d+ \d", cmd):
            body = self.files[m.group(1)].decode()
            proto = re.search(r"Protocol: (.+)", body).group(1).strip()  # type: ignore[union-attr]
            bits = int(re.search(r"Bit: (\d+)", body).group(1))  # type: ignore[union-attr]
            key = int(re.search(r"Key: ([0-9A-F ]+)", body).group(1).replace(" ", ""), 16)  # type: ignore[union-attr]
            freq = int(re.search(r"Frequency: (\d+)", body).group(1))  # type: ignore[union-attr]
            if freq in self.region_blocked_hz:
                return "Transmission on this frequency is restricted in your region"
            if proto == "Linear":  # lib/subghz/protocols/linear.c displays ~data
                key = ~key & 0x3FF
            self.air.subghz.append(f"{proto} {bits}bit\r\nKey:0x{key:08X}\r\n")
            return f"Listening at x. Frequency={freq}, Protocol={proto}\r\n\r\n."
        if m := re.fullmatch(r"ir tx (\S+) ([0-9A-F]+) ([0-9A-F]+)", cmd):
            self.air.ir.append(f"{m.group(1)}, A:0x{m.group(2)}, C:0x{m.group(3)}\r\n")
            return ""
        if cmd == "ir rx":
            self.stream, self.stream_start = "ir rx", len(self.air.ir)
            self.out += b"Receiving  INFRARED...\r\nPress Ctrl+C to abort\r\n"
            return None
        if m := re.fullmatch(r"(ikey|rfid) emulate (\S+) ([0-9A-F]+)", cmd):
            kind = "ibutton" if m.group(1) == "ikey" else "rfid"
            self.air.presented[kind] = f"{m.group(2)} {m.group(3)}"
            self.stream = f"present:{kind}"
            self.out += b"Emulating ...\r\nPress Ctrl+C to abort\r\n"
            return None
        if cmd in ("ikey read", "rfid read normal", "rfid read indala"):
            kind = "ibutton" if cmd.startswith("ikey") else "rfid"
            line = self.air.presented.get(kind)
            head = "Reading...\r\nPress Ctrl+C to abort\r\n"
            if line is None:
                self.stream = "blocked-read"
                self.out += head.encode()
                return None
            return head + line + ("\r\nReading stopped" if kind == "rfid" else "")
        if m := re.fullmatch(r"gpio mode (\S+) ([01])", cmd):
            self.pins[m.group(1)] = "out" if m.group(2) == "1" else "in"
            return f"Pin {m.group(1)} is now an " + (
                "output (low)" if m.group(2) == "1" else "input"
            )
        if m := re.fullmatch(r"gpio set (\S+) ([01])", cmd):
            self.air.wires[m.group(1)] = int(m.group(2))
            return f"Pin {m.group(1)} => {m.group(2)}"
        if m := re.fullmatch(r"gpio read (\S+)", cmd):
            return f"Pin {m.group(1)} <= {self.air.wires.get(m.group(1), 0)}"
        if cmd.startswith("storage mkdir") or cmd.startswith("storage remove"):
            return ""
        if m := re.fullmatch(r"storage write_chunk (\S+) (\d+)", cmd):
            self.files[m.group(1)] = b""
            self.pending_upload = (m.group(1), int(m.group(2)))
            self.out += b"Ready\r\n"
            return None
        if m := re.fullmatch(r"storage md5 (\S+)", cmd):
            import hashlib

            return hashlib.md5(self.files.get(m.group(1), b"")).hexdigest()
        return f"`{cmd}` command not found"
