from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

# Sizes tuned for 4K 55" display
_SIZE       = 280   # widget fixed size
_LABEL_SIZE = 220   # label min/max width+height
_RADIUS     = 110   # border-radius (half of _LABEL_SIZE)
_FONT       = 80    # font-size px
_BORDER     = 10    # normal border width
_BORDER_HI  = 16    # pulse border width (thicker state)
_BORDER_LO  = 9     # pulse border width (thinner state)


class TimerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(_SIZE, _SIZE)

        self.label = QLabel("--")
        self.label.setAlignment(Qt.AlignCenter)
        self._apply_style_normal()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.addWidget(self.label, alignment=Qt.AlignCenter)

        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._tick_critical_pulse)
        self._pulse_state: int = 0
        self._is_critical: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _css(self, font, bg, border_color, border_px):
        return (
            f"font-size: {font}px; font-weight: 900; color: white; "
            f"background: {bg}; "
            f"border: {border_px}px solid {border_color}; "
            f"border-radius: {_RADIUS}px; "
            f"min-width: {_LABEL_SIZE}px; min-height: {_LABEL_SIZE}px; "
            f"max-width: {_LABEL_SIZE}px; max-height: {_LABEL_SIZE}px;"
        )

    def _apply_style_normal(self):
        self.label.setStyleSheet(self._css(_FONT, "transparent", "#39FF14", _BORDER))

    def _apply_style_warning(self):
        self.label.setStyleSheet(self._css(_FONT, "rgba(243, 156, 18, 0.3)", "#ffa500", _BORDER))

    def _apply_style_idle(self):
        self.label.setStyleSheet(
            f"font-size: {_FONT}px; font-weight: 900; "
            f"color: rgba(255,255,255,0.4); "
            f"background: transparent; "
            f"border: {_BORDER}px solid rgba(57,255,20,0.3); "
            f"border-radius: {_RADIUS}px; "
            f"min-width: {_LABEL_SIZE}px; min-height: {_LABEL_SIZE}px; "
            f"max-width: {_LABEL_SIZE}px; max-height: {_LABEL_SIZE}px;"
        )

    # ------------------------------------------------------------------
    # Pulse
    # ------------------------------------------------------------------

    def _tick_critical_pulse(self):
        self._pulse_state = 1 - self._pulse_state
        border_px = _BORDER_HI if self._pulse_state == 0 else _BORDER_LO
        self.label.setStyleSheet(
            self._css(_FONT, "rgba(231, 76, 60, 0.3)", "#ff4444", border_px)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_remaining_ms(self, remaining_ms: int):
        sec = max(0, remaining_ms) / 1000.0
        self.label.setText(f"{int(sec):02d}s")

        if sec <= 3.0:
            if not self._is_critical:
                self._is_critical = True
                self._pulse_state = 0
                self._pulse_timer.start(300)
        else:
            if self._is_critical:
                self._is_critical = False
                self._pulse_timer.stop()

            if sec <= 7.0:
                self._apply_style_warning()
            else:
                self._apply_style_normal()

    def reset(self):
        """Stop pulse and show idle placeholder (no active question)."""
        self._pulse_timer.stop()
        self._is_critical = False
        self._pulse_state = 0
        self.label.setText("--")
        self._apply_style_idle()