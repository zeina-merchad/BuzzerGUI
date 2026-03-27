"""
Cascading Attempts Display Widget — scaled for 4K 55" display.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame


class CascadingAttemptsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QWidget { background: transparent; }")
        self.setMinimumWidth(520)

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
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("ATTEMPT\nSTATUS")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 900; color: #39FF14; "
            "letter-spacing: 1px; background: transparent; border: none;"
        )
        layout.addWidget(title)

        self.attempt_label = QLabel("1ST\nATTEMPT")
        self.attempt_label.setAlignment(Qt.AlignCenter)
        self.attempt_label.setWordWrap(True)
        self.attempt_label.setStyleSheet(
            "font-size: 60px; font-weight: 900; color: white; "
            "background: transparent; border: none; padding: 8px;"
        )
        layout.addWidget(self.attempt_label)

        self.points_label = QLabel("3 POINTS\nAVAILABLE")
        self.points_label.setAlignment(Qt.AlignCenter)
        self.points_label.setWordWrap(True)
        self.points_label.setStyleSheet(
            "font-size: 32px; font-weight: 700; color: #ffd700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.points_label)

        self.players_label = QLabel("4 PLAYERS\nCAN ATTEMPT")
        self.players_label.setAlignment(Qt.AlignCenter)
        self.players_label.setWordWrap(True)
        self.players_label.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
            "background: transparent; border: none; padding-top: 4px;"
        )
        layout.addWidget(self.players_label)

        # Player indicators row
        indicators_widget = QWidget()
        indicators_widget.setStyleSheet("QWidget { background: transparent; }")
        ind_layout = QHBoxLayout(indicators_widget)
        ind_layout.setContentsMargins(0, 14, 0, 0)
        ind_layout.setSpacing(18)
        ind_layout.setAlignment(Qt.AlignCenter)

        self.player_indicators = {}
        for i in range(1, 5):
            ind = QLabel(f"P{i}")
            ind.setAlignment(Qt.AlignCenter)
            ind.setFixedSize(80, 80)
            ind.setStyleSheet(self._idle_indicator_style())
            self.player_indicators[i] = ind
            ind_layout.addWidget(ind)

        layout.addWidget(indicators_widget)
        main_layout.addWidget(container)
        self.hide()

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    def _idle_indicator_style(self):
        return (
            "QLabel { "
            "background: rgba(255, 255, 255, 0.1); "
            "border: 3px solid rgba(255, 255, 255, 0.3); "
            "border-radius: 40px; "
            "color: rgba(255, 255, 255, 0.5); "
            "font-size: 28px; font-weight: 900; "
            "}"
        )

    def _failed_indicator_style(self):
        return (
            "QLabel { "
            "background: rgba(231, 76, 60, 0.3); "
            "border: 3px solid #e74c3c; "
            "border-radius: 40px; "
            "color: #e74c3c; "
            "font-size: 28px; font-weight: 900; "
            "}"
        )

    def _available_indicator_style(self):
        return (
            "QLabel { "
            "background: rgba(57, 255, 20, 0.2); "
            "border: 3px solid #39FF14; "
            "border-radius: 40px; "
            "color: #39FF14; "
            "font-size: 28px; font-weight: 900; "
            "}"
        )

    def _attempt_label_style(self, color: str):
        return (
            f"font-size: 60px; font-weight: 900; color: {color}; "
            f"background: transparent; border: none; padding: 4px;"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_attempt(self, attempt_number: int, points_available: int,
                       players_remaining: list, active_players: list = None):
        if active_players is None:
            all_players = {1, 2, 3, 4}
        else:
            all_players = set(active_players)

        self.show()

        self.attempt_label.setText(f"{self._ordinal(attempt_number)}\nATTEMPT")

        pts = points_available
        self.points_label.setText(f"{pts} POINT{'S' if pts != 1 else ''}\nAVAILABLE")

        num = len(players_remaining)
        if num == 0:
            self.players_label.setText("NO PLAYERS\nREMAINING")
        elif num == 1:
            self.players_label.setText(f"1 PLAYER\nCAN ATTEMPT\n(P{players_remaining[0]})")
        else:
            plist = ", ".join(f"P{p}" for p in players_remaining)
            self.players_label.setText(f"{num} PLAYERS\nCAN ATTEMPT\n({plist})")

        attempted_players = all_players - set(players_remaining)
        for pid, ind in self.player_indicators.items():
            if pid in attempted_players:
                ind.setStyleSheet(self._failed_indicator_style())
                ind.setText("✗")
            else:
                ind.setStyleSheet(self._available_indicator_style())
                ind.setText(f"P{pid}")

        color_map = {1: "#39FF14", 2: "#ffd700", 3: "#ffa500"}
        color = color_map.get(attempt_number, "#ff6b6b")
        self.attempt_label.setStyleSheet(self._attempt_label_style(color))

    def reset(self):
        self.hide()
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