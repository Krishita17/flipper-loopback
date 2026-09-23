"""flipper-loopback: hardware-in-the-loop regression harness for Flipper Zero firmware."""

from flci.errors import (
    FlciCommandError,
    FlciEnvironmentSkip,
    FlciError,
    FlciRegionRestricted,
    FlciTimeout,
    FlciUnsupported,
)

__all__ = [
    "FlciError",
    "FlciTimeout",
    "FlciCommandError",
    "FlciEnvironmentSkip",
    "FlciUnsupported",
    "FlciRegionRestricted",
]
__version__ = "0.5.0"
