from flci.subsystems.badusb import BadUsb
from flci.subsystems.base import EmitterFirst, Exchange, ReceiverFirst, Subsystem
from flci.subsystems.gpio import Gpio
from flci.subsystems.ibutton import IButton
from flci.subsystems.infrared import Infrared
from flci.subsystems.nfc import Nfc
from flci.subsystems.rfid import Rfid
from flci.subsystems.subghz import SubGhz

REGISTRY: dict[str, type[Subsystem]] = {
    cls.name: cls for cls in (SubGhz, Infrared, IButton, Rfid, Nfc, Gpio, BadUsb)
}

__all__ = ["Subsystem", "ReceiverFirst", "EmitterFirst", "Exchange", "REGISTRY"]
