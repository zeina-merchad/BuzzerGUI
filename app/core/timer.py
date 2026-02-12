from PySide6.QtCore import QObject, Signal, QTimer


class CountdownTimer(QObject):
    changed = Signal(int)   # remaining_ms
    ended = Signal()

    def __init__(self, tick_ms: int = 100):
        super().__init__()
        self._tick_ms = int(tick_ms)
        self._remaining_ms = 0
        self._timer = QTimer()
        self._timer.setInterval(self._tick_ms)
        self._timer.timeout.connect(self._on_tick)

    @property
    def remaining_ms(self) -> int:
        return self._remaining_ms

    def start(self, total_ms: int) -> None:
        self._remaining_ms = max(0, int(total_ms))
        self.changed.emit(self._remaining_ms)
        self._timer.start()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if self._remaining_ms > 0:
            self._timer.start()

    def stop(self) -> None:
        """
        Stop the timer and reset the remaining time.

        FIX #8: The previous version emitted changed(0) here, which caused
        the TimerWidget to briefly flash "00s" whenever a player buzzed in
        (because the engine calls timer.stop() on buzz before starting the
        answer timer).  We no longer emit on stop() — the widget tracks the
        last value from tick-based changed signals and therefore stays on the
        last displayed second rather than jumping to zero.
        """
        self._timer.stop()
        self._remaining_ms = 0

    def _on_tick(self) -> None:
        self._remaining_ms -= self._tick_ms
        if self._remaining_ms <= 0:
            self._remaining_ms = 0
            self._timer.stop()
            self.changed.emit(self._remaining_ms)
            self.ended.emit()
        else:
            self.changed.emit(self._remaining_ms)