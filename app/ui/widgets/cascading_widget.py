"""
Cascading Attempts Display Widget — scaled for 4K 55" display.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class CascadingAttemptsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QWidget { background: transparent; }")

        from app.ui.display_config import SCALE as _S

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        container = QFrame()
        container.setStyleSheet(
            "QFrame { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(57, 255, 20, 0.15), stop:1 rgba(57, 255, 20, 0.05)); "
            "border: 4px solid #39FF14; "
            "border-radius: 16px; "
            "}"
        )

        layout = QVBoxLayout(container)
        layout.setSpacing(_S.cascade_spacing)
        layout.setContentsMargins(
            _S.cascade_margin_h,
            _S.cascade_margin_v,
            _S.cascade_margin_h,
            _S.cascade_margin_v,
        )

        title = QLabel("ATTEMPT\nSTATUS")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"font-size: {_S.cascade_title_font}px; font-weight: 900; color: #39FF14; "
            "letter-spacing: 1px; background: transparent; border: none;"
        )
        title.hide()

        self.attempt_label = QLabel("1ST\nATTEMPT")
        self.attempt_label.hide()

        self.points_label = QLabel("3 POINTS\nAVAILABLE")
        self.points_label.setAlignment(Qt.AlignCenter)
        self.points_label.setWordWrap(True)
        self.points_label.setStyleSheet(
            f"font-size: {_S.cascade_points_font}px; font-weight: 700; color: #ffd700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.points_label)

        # Player indicators row
        indicators_widget = QWidget()
        indicators_widget.setStyleSheet("QWidget { background: transparent; }")
        ind_layout = QHBoxLayout(indicators_widget)
        ind_layout.setContentsMargins(0, 6, 0, 0)
        ind_layout.setSpacing(max(4, _S.cascade_indicator_size // 10))
        ind_layout.setAlignment(Qt.AlignCenter)

        self.player_indicators = {}
        for i in range(1, 5):
            ind = QLabel(f"P{i}")
            ind.setAlignment(Qt.AlignCenter)
            ind.setFixedSize(_S.cascade_indicator_size, _S.cascade_indicator_size)
            ind.setStyleSheet(self._idle_indicator_style())
            self.player_indicators[i] = ind
            ind_layout.addWidget(ind)

        layout.addWidget(indicators_widget)
        main_layout.addWidget(container)
        self.container = container
        self.container.hide()  # hide content but outer widget keeps its space

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    def _idle_indicator_style(self):
        from app.ui.display_config import SCALE as _S

        return (
            "QLabel { "
            "background: rgba(255, 255, 255, 0.1); "
            "border: 2px solid rgba(255, 255, 255, 0.3); "
            f"border-radius: {_S.cascade_indicator_radius}px; "
            "color: rgba(255, 255, 255, 0.5); "
            f"font-size: {_S.cascade_indicator_font}px; font-weight: 900; "
            "}"
        )

    def _failed_indicator_style(self):
        from app.ui.display_config import SCALE as _S

        return (
            "QLabel { "
            "background: rgba(231, 76, 60, 0.3); "
            "border: 2px solid #e74c3c; "
            f"border-radius: {_S.cascade_indicator_radius}px; "
            "color: #e74c3c; "
            f"font-size: {_S.cascade_indicator_font}px; font-weight: 900; "
            "}"
        )

    def _available_indicator_style(self):
        from app.ui.display_config import SCALE as _S

        return (
            "QLabel { "
            "background: rgba(57, 255, 20, 0.2); "
            "border: 2px solid #39FF14; "
            f"border-radius: {_S.cascade_indicator_radius}px; "
            "color: #39FF14; "
            f"font-size: {_S.cascade_indicator_font}px; font-weight: 900; "
            "}"
        )

    def _attempt_label_style(self, color: str):
        from app.ui.display_config import SCALE as _S

        return (
            f"font-size: {_S.cascade_attempt_font}px; font-weight: 900; color: {color}; "
            f"background: transparent; border: none; padding: 2px;"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_attempt(
        self,
        attempt_number: int,
        points_available: int,
        players_remaining: list,
        active_players: list = None,
    ):
        if active_players is None:
            all_players = {1, 2, 3, 4}
        else:
            all_players = set(active_players)

        self.container.show()

        pts = points_available
        self.points_label.setText(f"{pts} POINT{'S' if pts != 1 else ''}\nAVAILABLE")

        attempted_players = all_players - set(players_remaining)
        for pid, ind in self.player_indicators.items():
            if pid in attempted_players:
                ind.setStyleSheet(self._failed_indicator_style())
                ind.setText("✗")
            else:
                ind.setStyleSheet(self._available_indicator_style())
                ind.setText(f"P{pid}")

    def reset(self):
        self.container.hide()
        for pid, ind in self.player_indicators.items():
            ind.setText(f"P{pid}")
            ind.setStyleSheet(self._idle_indicator_style())

    def show_attempt_failed(self, player_id: int):
        if player_id in self.player_indicators:
            ind = self.player_indicators[player_id]
            ind.setStyleSheet(self._failed_indicator_style())
            ind.setText("✗")

    @staticmethod
    def _ordinal(n: int) -> str:
        return {1: "1ST", 2: "2ND", 3: "3RD"}.get(n, f"{n}TH")
