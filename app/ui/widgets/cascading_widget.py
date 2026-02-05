"""
Cascading Attempts Display Widget for Host Screen
Shows current attempt number and available points
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame


class CascadingAttemptsWidget(QWidget):
    """Widget to display current attempt status during cascading attempts"""
    
    def __init__(self):
        super().__init__()
        
        # Main container with gradient background
        self.setStyleSheet(
            "QWidget { background: transparent; }"
        )
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Container frame
        container = QFrame()
        container.setStyleSheet(
            "QFrame { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(57, 255, 20, 0.15), stop:1 rgba(57, 255, 20, 0.05)); "
            "border: 3px solid #39FF14; "
            "border-radius: 12px; "
            "padding: 12px; "
            "}"
        )
        
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(15, 12, 15, 12)
        
        # Title
        title = QLabel("ATTEMPT STATUS")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 12px; font-weight: 900; color: #39FF14; "
            "letter-spacing: 2px; background: transparent; border: none;"
        )
        layout.addWidget(title)
        
        # Attempt number display (large)
        self.attempt_label = QLabel("ATTEMPT 1")
        self.attempt_label.setAlignment(Qt.AlignCenter)
        self.attempt_label.setStyleSheet(
            "font-size: 32px; font-weight: 900; color: white; "
            "background: transparent; border: none; padding: 4px;"
        )
        layout.addWidget(self.attempt_label)
        
        # Points available
        self.points_label = QLabel("3 POINTS AVAILABLE")
        self.points_label.setAlignment(Qt.AlignCenter)
        self.points_label.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #ffd700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.points_label)
        
        # Players remaining indicator
        self.players_label = QLabel("4 PLAYERS CAN ATTEMPT")
        self.players_label.setAlignment(Qt.AlignCenter)
        self.players_label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
            "background: transparent; border: none; padding-top: 4px;"
        )
        layout.addWidget(self.players_label)
        
        # Already attempted players (crosses)
        self.attempted_widget = QWidget()
        attempted_layout = QHBoxLayout(self.attempted_widget)
        attempted_layout.setContentsMargins(0, 4, 0, 0)
        attempted_layout.setSpacing(4)
        attempted_layout.setAlignment(Qt.AlignCenter)
        
        self.player_indicators = {}
        for i in range(1, 5):
            indicator = QLabel(f"P{i}")
            indicator.setAlignment(Qt.AlignCenter)
            indicator.setFixedSize(30, 30)
            indicator.setStyleSheet(
                "QLabel { "
                "background: rgba(255, 255, 255, 0.1); "
                "border: 2px solid rgba(255, 255, 255, 0.3); "
                "border-radius: 15px; "
                "color: rgba(255, 255, 255, 0.5); "
                "font-size: 11px; font-weight: 900; "
                "}"
            )
            self.player_indicators[i] = indicator
            attempted_layout.addWidget(indicator)
        
        layout.addWidget(self.attempted_widget)
        
        main_layout.addWidget(container)
        
        # Start hidden
        self.hide()
    
    def update_attempt(self, attempt_number: int, points_available: int, players_remaining: list):
        """Update display with current attempt information"""
        self.show()
        
        # Update attempt number
        attempt_text = self._get_ordinal(attempt_number)
        self.attempt_label.setText(f"{attempt_text} ATTEMPT")
        
        # Update points
        if points_available == 1:
            self.points_label.setText("1 POINT AVAILABLE")
        else:
            self.points_label.setText(f"{points_available} POINTS AVAILABLE")
        
        # Update players remaining
        num_remaining = len(players_remaining)
        if num_remaining == 0:
            self.players_label.setText("NO PLAYERS REMAINING")
        elif num_remaining == 1:
            self.players_label.setText(f"1 PLAYER CAN STILL ATTEMPT (P{players_remaining[0]})")
        else:
            player_list = ", ".join([f"P{p}" for p in players_remaining])
            self.players_label.setText(f"{num_remaining} PLAYERS CAN ATTEMPT ({player_list})")
        
        # Update player indicators
        all_players = {1, 2, 3, 4}
        attempted_players = all_players - set(players_remaining)
        
        for player_id, indicator in self.player_indicators.items():
            if player_id in attempted_players:

                indicator.setStyleSheet(
                    "QLabel { "
                    "background: rgba(231, 76, 60, 0.3); "
                    "border: 2px solid #e74c3c; "
                    "border-radius: 15px; "
                    "color: #e74c3c; "
                    "font-size: 14px; font-weight: 900; "
                    "}"
                )
                indicator.setText("✗")
            else:

                indicator.setStyleSheet(
                    "QLabel { "
                    "background: rgba(57, 255, 20, 0.2); "
                    "border: 2px solid #39FF14; "
                    "border-radius: 15px; "
                    "color: #39FF14; "
                    "font-size: 11px; font-weight: 900; "
                    "}"
                )
                indicator.setText(f"P{player_id}")
        
        if attempt_number == 1:
            color = "#39FF14"  # Green
        elif attempt_number == 2:
            color = "#ffd700"  # Gold
        elif attempt_number == 3:
            color = "#ffa500"  # Orange
        else:
            color = "#ff6b6b"  # Red
        
        # Update attempt label color
        self.attempt_label.setStyleSheet(
            f"font-size: 32px; font-weight: 900; color: {color}; "
            f"background: transparent; border: none; padding: 4px;"
        )
    
    def reset(self):
        """Reset to initial state"""
        self.hide()
        for indicator in self.player_indicators.values():
            indicator.setStyleSheet(
                "QLabel { "
                "background: rgba(255, 255, 255, 0.1); "
                "border: 2px solid rgba(255, 255, 255, 0.3); "
                "border-radius: 15px; "
                "color: rgba(255, 255, 255, 0.5); "
                "font-size: 11px; font-weight: 900; "
                "}"
            )
    
    def show_attempt_failed(self, player_id: int):
        """Briefly highlight failed attempt"""
        if player_id in self.player_indicators:
            indicator = self.player_indicators[player_id]
            # Flash red
            indicator.setStyleSheet(
                "QLabel { "
                "background: rgba(231, 76, 60, 0.5); "
                "border: 3px solid #e74c3c; "
                "border-radius: 15px; "
                "color: white; "
                "font-size: 16px; font-weight: 900; "
                "}"
            )
            indicator.setText("✗")
    
    def _get_ordinal(self, n: int) -> str:
        """Convert number to ordinal string"""
        if n == 1:
            return "1ST"
        elif n == 2:
            return "2ND"
        elif n == 3:
            return "3RD"
        else:
            return f"{n}TH"