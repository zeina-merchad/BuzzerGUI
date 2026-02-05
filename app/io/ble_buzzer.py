import asyncio
import re
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set, Iterable

from PySide6.QtCore import QObject, Signal, QThread

from bleak import BleakScanner, BleakClient

from app.constants import (
    BLE_SERVICE_UUID,
    BLE_BUZZ_UUID,
    BLE_CMD_UUID,
    BLE_NAME_PREFIX,
    MAX_PLAYERS,
)

@dataclass(frozen=True)
class BleBuzzMessage:
    buzzer_id: int
    t_ms: int
    received_ms: int


class BleBuzzerService(QObject):
    """
    BLE buzzer manager:
    - Scans for devices named FBZ_1..FBZ_4
    - Connects + subscribes to BUZZ notify characteristic
    - Provides lock/reset commands via CMD write characteristic
    """
    log = Signal(str)
    connected = Signal(int, bool)      # (buzzer_id, is_connected)
    buzz = Signal(int, int, int)       # (buzzer_id, t_ms, received_ms)

    def __init__(self, wanted_ids: Optional[Iterable[int]] = None, scan_interval_s: float = 2.0):
        super().__init__()
        self.wanted_ids: Set[int] = set(wanted_ids or range(1, MAX_PLAYERS + 1))
        self.scan_interval_s = float(scan_interval_s)

        self._thread: Optional[QThread] = None
        self._worker: Optional[_BleWorker] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = QThread()
        self._worker = _BleWorker(self.wanted_ids, self.scan_interval_s)

        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        # forward worker signals
        self._worker.log.connect(self.log)
        self._worker.connected.connect(self.connected)
        self._worker.buzz.connect(self.buzz)

        self._thread.start()

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(1500)
        self._thread = None
        self._worker = None

    def lock_all(self) -> None:
        if self._worker is not None:
            self._worker.cmd_all(b"LOCK")

    def reset_all(self) -> None:
        if self._worker is not None:
            self._worker.cmd_all(b"RESET")


class _BleWorker(QObject):
    log = Signal(str)
    connected = Signal(int, bool)
    buzz = Signal(int, int, int)  # (buzzer_id, t_ms, received_ms)

    def __init__(self, wanted_ids: Set[int], scan_interval_s: float):
        super().__init__()
        self.wanted_ids = wanted_ids
        self.scan_interval_s = scan_interval_s

        self._stop = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._addr_by_id: Dict[int, str] = {}
        self._clients: Dict[int, BleakClient] = {}

        self._name_re = re.compile(rf"^{re.escape(BLE_NAME_PREFIX)}(\d+)$")  # FBZ_1 etc.

    def run(self) -> None:
        """Entry point for QThread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.create_task(self._main())
        self._loop.run_forever()

    def request_stop(self) -> None:
        self._stop = True
        if self._loop:
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._shutdown()))

    def cmd_all(self, cmd: bytes) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._send_cmd_all(cmd)))

    async def _main(self) -> None:
        self.log.emit("BLE: starting scan/connect loop...")
        while not self._stop:
            try:
                await self._scan_once(timeout=3.0)
                await self._connect_missing()
            except Exception as e:
                self.log.emit(f"BLE loop error: {e!r}")
            await asyncio.sleep(self.scan_interval_s)

    async def _scan_once(self, timeout: float) -> None:
        devices = await BleakScanner.discover(timeout=timeout)

        new_found = 0
        for d in devices:
            name = (d.name or "").strip()
            m = self._name_re.match(name)
            if not m:
                continue

            buzzer_id = int(m.group(1))
            if buzzer_id not in self.wanted_ids:
                continue

            if buzzer_id not in self._addr_by_id:
                self._addr_by_id[buzzer_id] = d.address
                self.log.emit(f"Found {name} @ {d.address}")
                new_found += 1

        if new_found == 0:
            self.log.emit("Scan: no new FBZ devices")

    async def _connect_missing(self) -> None:
        for buzzer_id, addr in list(self._addr_by_id.items()):
            if self._stop:
                return
            if buzzer_id in self._clients:
                continue

            try:
                client = BleakClient(addr)
                await client.connect(timeout=8.0)

                self._clients[buzzer_id] = client
                self.connected.emit(buzzer_id, True)
                self.log.emit(f"Connected: FBZ_{buzzer_id}")

                # Subscribe to BUZZ notifications
                await client.start_notify(BLE_BUZZ_UUID, self._make_notify_handler(buzzer_id))

                # Optional: reset on connect (enable)
                await client.write_gatt_char(BLE_CMD_UUID, b"RESET", response=False)

                # Disconnected callback
                client.set_disconnected_callback(self._make_disconnect_handler(buzzer_id))

            except Exception as e:
                self.log.emit(f"Connect failed FBZ_{buzzer_id}: {e!r}")
                await asyncio.sleep(0.3)

    def _make_disconnect_handler(self, buzzer_id: int):
        def _cb(_client):
            self.log.emit(f"Disconnected: FBZ_{buzzer_id}")
            self.connected.emit(buzzer_id, False)
            self._clients.pop(buzzer_id, None)
        return _cb

    def _make_notify_handler(self, buzzer_id: int):
        def _on_notify(_sender: int, data: bytearray):
            # ESP32 sends: "id=1,t=123456"
            received_ms = int(time.time() * 1000)
            try:
                text = data.decode("utf-8", errors="ignore")
                t_ms = 0
                for part in text.split(","):
                    p = part.strip()
                    if p.startswith("t="):
                        t_ms = int(p[2:])
                self.buzz.emit(buzzer_id, t_ms, received_ms)
            except Exception:
                return
        return _on_notify

    async def _send_cmd_all(self, cmd: bytes) -> None:
        for buzzer_id, client in list(self._clients.items()):
            try:
                if client.is_connected:
                    await client.write_gatt_char(BLE_CMD_UUID, cmd, response=False)
            except Exception as e:
                self.log.emit(f"CMD {cmd!r} failed FBZ_{buzzer_id}: {e!r}")

    async def _shutdown(self) -> None:
        self.log.emit("BLE: shutting down...")
        try:
            for buzzer_id, client in list(self._clients.items()):
                try:
                    await client.disconnect()
                except Exception:
                    pass
            self._clients.clear()
        finally:
            if self._loop:
                self._loop.stop()
