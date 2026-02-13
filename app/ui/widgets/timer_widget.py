from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class TimerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(150, 150)

        self.label = QLabel("07s")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            "font-size: 42px; font-weight: 900; "
            "color: white; "
            "background: transparent; "
            "border: 6px solid #39FF14; "
            "border-radius: 60px; "
            "min-width: 120px; min-height: 120px; "
            "max-width: 120px; max-height: 120px;"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.addWidget(self.label, alignment=Qt.AlignCenter)

        # Pulse timer for critical state (≤3s)
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._tick_critical_pulse)
        self._pulse_state: int = 0
        self._is_critical: bool = False

    def _tick_critical_pulse(self):
        self._pulse_state = 1 - self._pulse_state
        border_px = 9 if self._pulse_state == 0 else 5
        self.label.setStyleSheet(
            f"font-size: 42px; font-weight: 900; "
            f"color: white; "
            f"background: rgba(231, 76, 60, 0.3); "
            f"border: {border_px}px solid #ff4444; "
            f"border-radius: 60px; "
            f"min-width: 120px; min-height: 120px; "
            f"max-width: 120px; max-height: 120px;"
        )

    def set_remaining_ms(self, remaining_ms: int):
        sec = max(0, remaining_ms) / 1000.0
        self.label.setText(f"{int(sec):02d}s")

        if sec <= 3.0:
            if not self._is_critical:
                self._is_critical = True
                self._pulse_state = 0
                self._pulse_timer.start(300)  # pulse every 300ms
        else:
            if self._is_critical:
                self._is_critical = False
                self._pulse_timer.stop()

            if sec <= 7.0:
                # Orange - Warning
                self.label.setStyleSheet(
                    "font-size: 42px; font-weight: 900; "
                    "color: white; "
                    "background: rgba(243, 156, 18, 0.3); "
                    "border: 6px solid #ffa500; "
                    "border-radius: 60px; "
                    "min-width: 120px; min-height: 120px; "
                    "max-width: 120px; max-height: 120px;"
                )
            else:
                # Green - Normal
                self.label.setStyleSheet(
                    "font-size: 42px; font-weight: 900; "
                    "color: white; "
                    "background: transparent; "
                    "border: 6px solid #39FF14; "
                    "border-radius: 60px; "
                    "min-width: 120px; min-height: 120px; "
                    "max-width: 120px; max-height: 120px;"
                )