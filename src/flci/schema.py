"""Data models shared by fixtures, parsers and assertions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUBSYSTEMS = {"subghz", "infrared", "ibutton", "rfid", "nfc", "gpio", "badusb"}


def normalize_hex(value: str | int, bits: int | None = None) -> str:
    """Comparison-safe hex: uppercase, no 0x, no spaces, zero-padded to ``bits`` if known.

    ``"0x00ABCDEF"``, ``"00 AB CD EF"`` and ``0xABCDEF`` all become ``"ABCDEF"`` for 24 bits.
    """
    if isinstance(value, int):
        n = value
    else:
        cleaned = value.strip().replace(" ", "").replace(":", "")
        if cleaned.lower().startswith("0x"):
            cleaned = cleaned[2:]
        if not cleaned:
            raise ValueError("empty hex payload")
        n = int(cleaned, 16)
    width = (bits + 3) // 4 if bits else max(1, (n.bit_length() + 3) // 4)
    return format(n, "X").zfill(width)


class NormalizedDecode(BaseModel):
    """What a receiver decoded, in a shape two decodes can be compared in."""

    model_config = ConfigDict(frozen=True)

    subsystem: str
    protocol: str
    frequency_hz: int | None = None
    payload: str
    bits: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("subsystem")
    @classmethod
    def _known_subsystem(cls, v: str) -> str:
        if v not in SUBSYSTEMS:
            raise ValueError(f"unknown subsystem {v!r}; expected one of {sorted(SUBSYSTEMS)}")
        return v

    def matches(self, other: NormalizedDecode) -> bool:
        """Equal on everything that matters; ``raw`` and unset optional fields are ignored."""
        if (self.subsystem, self.protocol.lower()) != (other.subsystem, other.protocol.lower()):
            return False
        if self.bits is not None and other.bits is not None and self.bits != other.bits:
            return False
        if (
            self.frequency_hz is not None
            and other.frequency_hz is not None
            and self.frequency_hz != other.frequency_hz
        ):
            return False
        return normalize_hex(self.payload, self.bits) == normalize_hex(other.payload, other.bits)

    def short(self) -> str:
        freq = f" @{self.frequency_hz}Hz" if self.frequency_hz else ""
        bits = f" {self.bits}bit" if self.bits else ""
        return f"{self.subsystem}:{self.protocol}{bits} {self.payload}{freq}"


class Fixture(BaseModel):
    """One test case: a known stimulus and the decode we expect for it."""

    id: str
    subsystem: str
    description: str = ""
    # Phase 1 drives built-in CLI transmitters, so the stimulus is a set of parameters.
    # stimulus_path points at the equivalent .sub/.ir/... file for file-based TX (Phase 2).
    stimulus: dict[str, Any]
    stimulus_path: Path | None = None
    expected: NormalizedDecode
    tags: list[str] = Field(default_factory=list)
    source: Path | None = Field(default=None, exclude=True)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v or any(c.isspace() for c in v):
            raise ValueError("fixture id must be a non-empty slug without whitespace")
        return v
