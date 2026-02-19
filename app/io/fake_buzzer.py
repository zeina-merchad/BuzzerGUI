import time
from PySide6.QtCore import QObject, Signal


class FakeBuzzerService(QObject):
    """
    UI-only buzzer simulator.
    Emits the same signals as BleBuzzerService.
    """
    log = Signal(str)
    connected = Signal(int, bool)        # (buzzer_id, connected)
    buzz = Signal(int, int, int)         # (buzzer_id, t_ms, received_ms)

    def __init__(self, player_ids=(1, 2, 3, 4)):
        super().__init__()
        self.player_ids = player_ids

    def start(self):
        # Immediately mark all as connected
        for pid in self.player_ids:
            self.connected.emit(pid, True)
        self.log.emit("FakeBuzzer: all players connected")

    def stop(self):
        pass

    def lock_all(self):
        self.log.emit("FakeBuzzer: LOCK")

    def reset_all(self):
        self.log.emit("FakeBuzzer: RESET")

    # ---- manual trigger from UI ----
    def simulate_buzz(self, buzzer_id: int):
        now_ms = int(time.time() * 1000)
        self.buzz.emit(buzzer_id, now_ms, now_ms)
