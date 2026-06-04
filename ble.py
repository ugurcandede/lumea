"""BLE transport for ELK-BLEDOM / MELK LED strips.

Wraps bleak so the UI never touches GATT directly. Discovery is by name prefix
(never a hardcoded MAC) so the same code works on Windows (where the address is
a MAC) and macOS (where it is a CoreBluetooth UUID).

`ElkBledom` is one connection to one strip. `DeviceManager` holds several at
once and fans a command out to a chosen subset -- each strip accepts only one
GATT client, but the app can hold connections to many different strips.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

import protocol

log = logging.getLogger(__name__)

SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
# Some variants expose the writable characteristic here instead.
FALLBACK_WRITE_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
NAME_PREFIXES = ("ELK-BLE", "MELK", "ELK-BULB")


async def scan(timeout: float = 5.0) -> list[BLEDevice]:
    """Discover nearby strips by name prefix.

    May return [] on the first WinRT call even with the device powered on --
    call again.
    """
    devices = await BleakScanner.discover(timeout=timeout)
    return [d for d in devices if d.name and d.name.startswith(NAME_PREFIXES)]


class ElkBledom:
    """A single connection to one strip.

    Writes are fire-and-forget; the device reports no state, so nothing is ever
    read back.
    """

    def __init__(self, address: str, on_disconnect: Callable[[], None] | None = None):
        self.address = address
        self._on_disconnect = on_disconnect
        self._client = BleakClient(
            address, disconnected_callback=self._handle_disconnect
        )
        self._write_char = None

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    async def connect(self) -> None:
        await self._client.connect()
        try:
            self._write_char = self._resolve_write_char()
        except Exception:
            # Link came up but the device lacks the expected char -- don't leak it.
            await self._client.disconnect()
            raise
        log.info("connected to %s via %s", self.address, self._write_char.uuid)

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def set_power(self, on: bool) -> None:
        await self._write(protocol.power(on))

    async def set_color(self, r: int, g: int, b: int) -> None:
        await self._write(protocol.color(r, g, b))

    async def _write(self, data: bytes) -> None:
        if self._write_char is None:
            raise RuntimeError("not connected")
        # response=False: the write characteristic is write-without-response (0x06).
        await self._client.write_gatt_char(self._write_char, data, response=False)

    def _resolve_write_char(self):
        for uuid in (WRITE_CHAR_UUID, FALLBACK_WRITE_CHAR_UUID):
            char = self._client.services.get_characteristic(uuid)
            if char is not None:
                return char
        raise RuntimeError("no writable characteristic (fff3/ffe1) on this device")

    def _handle_disconnect(self, _client: BleakClient) -> None:
        log.warning("disconnected from %s", self.address)
        if self._on_disconnect is not None:
            self._on_disconnect()


class DeviceManager:
    """Several `ElkBledom` connections, addressed by device address.

    `on_disconnect(address)` fires when a device drops; the caller decides
    whether that was wanted (and whether to reconnect).
    """

    def __init__(self, on_disconnect: Callable[[str], None]):
        self._on_disconnect = on_disconnect
        self._devices: dict[str, ElkBledom] = {}

    def is_connected(self, address: str) -> bool:
        return address in self._devices

    def connected_addresses(self) -> set[str]:
        return set(self._devices)

    async def connect(self, address: str) -> None:
        if address in self._devices:
            return
        device = ElkBledom(address, on_disconnect=lambda: self._fire(address))
        await device.connect()
        self._devices[address] = device

    async def disconnect(self, address: str) -> None:
        device = self._devices.pop(address, None)
        if device is not None:
            await device.disconnect()

    async def apply(
        self, addresses: list[str], action: Callable[[ElkBledom], Awaitable[None]]
    ) -> dict[str, BaseException | None]:
        """Run `action(device)` on each connected address concurrently.

        Returns {address: exception-or-None}.
        """
        targets = [a for a in addresses if a in self._devices]
        results = await asyncio.gather(
            *(action(self._devices[a]) for a in targets),
            return_exceptions=True,
        )
        return dict(zip(targets, results))

    def _fire(self, address: str) -> None:
        self._devices.pop(address, None)
        self._on_disconnect(address)
