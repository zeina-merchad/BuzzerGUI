from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout

DEFAULT_COLORS = {
    1: "#e74c3c",  # red
    2: "#3498db",  # blue
    3: "#2ecc71",  # green
    4: "#f39c12",  # orange/yellow
}


class PlayerCard(QFrame):
    def __init__(self, player_id: int, color_hex: str):
        super().__init__()
        self.player_id = player_id
        self.color_hex = color_hex

        self.setFrameShape(QFrame.StyledPanel)
        self._set_normal_style()


        self.badge = QLabel(str(player_id))
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setStyleSheet(
            f"font-size: 36px; font-weight: 900; color: white; "
            f"background: {color_hex}; "
            f"border-radius: 30px; min-width: 60px; min-height: 60px; "
            f"max-width: 60px; max-height: 60px;"
        )

        # Player label
        self.name = QLabel(f"PLAYER {player_id}")
        self.name.setStyleSheet(
            "font-size: 14px; font-weight: 900; letter-spacing: 1px; "
            "color: #2c3e50;"
        )
        self.name.setAlignment(Qt.AlignCenter)

        # Connection status
        self.connected = QLabel("●")
        self.connected.setStyleSheet("font-size: 16px; color: #e74c3c;")
        self.connected.setAlignment(Qt.AlignCenter)
        self.connected.setToolTip("Disconnected")

        # Score display (big and bold)
        self.score = QLabel("0")
        self.score.setAlignment(Qt.AlignCenter)
        self.score.setStyleSheet(
            "font-size: 42px; font-weight: 900; color: #2c3e50; "
            "padding: 8px;"
        )

        # Score label
        score_label = QLabel("POINTS")
        score_label.setAlignment(Qt.AlignCenter)
        score_label.setStyleSheet(
            "font-size: 10px; font-weight: 900; color: #7f8c8d; "
            "letter-spacing: 1px;"
        )

        # Layout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignCenter)
        
        lay.addWidget(self.badge, alignment=Qt.AlignCenter)
        lay.addWidget(self.name)
        lay.addWidget(self.connected)
        lay.addSpacing(4)
        lay.addWidget(self.score)
        lay.addWidget(score_label)

    def _set_normal_style(self):
        self.setStyleSheet(
            "QFrame { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #ffffff, stop:1 #f8f9fa);"
            "border: 3px solid #ecf0f1;"
            "border-radius: 16px;"
            "}"
        )

    def set_connected(self, is_connected: bool):
        if is_connected:
            self.connected.setText("●")
            self.connected.setStyleSheet("font-size: 16px; color: #2ecc71;")
            self.connected.setToolTip("Connected")
        else:
            self.connected.setText("●")
            self.connected.setStyleSheet("font-size: 16px; color: #e74c3c;")
            self.connected.setToolTip("Disconnected")

    def set_score(self, value: int):
        self.score.setText(str(int(value)))

    def highlight_locked(self, locked: bool):
        if locked:
            # Highlight with team color when player buzzes
            self.setStyleSheet(
                f"QFrame {{ "
                f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                f"stop:0 {self.color_hex}, stop:1 {self._darken_color(self.color_hex)});"
                f"border: 4px solid {self.color_hex};"
                f"border-radius: 16px;"
                f"}}"
            )
            # Make text white when highlighted
            self.name.setStyleSheet(
                "font-size: 14px; font-weight: 900; letter-spacing: 1px; "
                "color: white;"
            )
            self.score.setStyleSheet(
                "font-size: 42px; font-weight: 900; color: white; "
                "padding: 8px;"
            )
        else:
            self._set_normal_style()
            self.name.setStyleSheet(
                "font-size: 14px; font-weight: 900; letter-spacing: 1px; "
                "color: #2c3e50;"
            )
            self.score.setStyleSheet(
                "font-size: 42px; font-weight: 900; color: #2c3e50; "
                "padding: 8px;"
            )

    def _darken_color(self, hex_color: str) -> str:
        """Darken a hex color by 20% for gradient effect"""
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r, g, b = int(r * 0.8), int(g * 0.8), int(b * 0.8)
        return f"#{r:02x}{g:02x}{b:02x}"


class ScoreboardWidget(QWidget):
    def __init__(self, colors=None, layout_mode: str = "row"):

        super().__init__()
        self.colors = colors or DEFAULT_COLORS
        self.cards = {}

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        if layout_mode == "row":
            order = [(0, 0, 1), (0, 1, 2), (0, 2, 3), (0, 3, 4)]
        else:
            order = [(0, 0, 1), (0, 1, 2), (1, 0, 3), (1, 1, 4)]

        for r, c, pid in order:
            card = PlayerCard(pid, self.colors.get(pid, "#95a5a6"))
            self.cards[pid] = card
            grid.addWidget(card, r, c)

    def set_connected(self, player_id: int, is_connected: bool):
        if player_id in self.cards:
            self.cards[player_id].set_connected(is_connected)

    def set_score(self, player_id: int, score: int):
        if player_id in self.cards:
            self.cards[player_id].set_score(score)

    def set_locked(self, locked_player_id: int | None):
        for pid, card in self.cards.items():
            card.highlight_locked(locked_player_id == pid)