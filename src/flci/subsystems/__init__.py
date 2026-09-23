from flci.subsystems.base import Subsystem
from flci.subsystems.subghz import SubGhz

REGISTRY: dict[str, type[Subsystem]] = {"subghz": SubGhz}

__all__ = ["Subsystem", "SubGhz", "REGISTRY"]
