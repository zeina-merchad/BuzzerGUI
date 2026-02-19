"""
Cascading Attempts Display Widget for Host Screen
Shows current attempt number and available points
OPTIMIZED FOR SIDE PLACEMENT
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
        
        # Set fixed width for side placement
        self.setFixedWidth(220)  # Reduced from 240
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)  # Reduced from 8
        
        # Container frame
        container = QFrame()
        container.setStyleSheet(
            "QFrame { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(57, 255, 20, 0.15), stop:1 rgba(57, 255, 20, 0.05)); "
            "border: 3px solid #39FF14; "
            "border-radius: 12px; "
            "padding: 10px; "  # Reduced from 15px
            "}"
        )
        
        layout = QVBoxLayout(container)
        layout.setSpacing(4)  # Reduced from 8
        layout.setContentsMargins(8, 8, 8, 8)  # Reduced from 12
        
        # Title (smaller, wraps better)
        title = QLabel("ATTEMPT\nSTATUS")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size: 11px; font-weight: 900; color: #39FF14; "
            "letter-spacing: 1px; background: transparent; border: none; "
            "line-height: 1.2;"
        )
        layout.addWidget(title)
        
        # Attempt number display (large, wraps if needed)
        self.attempt_label = QLabel("1ST\nATTEMPT")
        self.attempt_label.setAlignment(Qt.AlignCenter)
        self.attempt_label.setWordWrap(True)
        self.attempt_label.setStyleSheet(
            "font-size: 24px; font-weight: 900; color: white; "
            "background: transparent; border: none; padding: 4px; "
            "line-height: 1.1;"
        )
        layout.addWidget(self.attempt_label)
        
        # Points available (smaller, wraps)
        self.points_label = QLabel("3 POINTS\nAVAILABLE")
        self.points_label.setAlignment(Qt.AlignCenter)
        self.points_label.setWordWrap(True)
        self.points_label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #ffd700; "
            "background: transparent; border: none; line-height: 1.2;"
        )
        layout.addWidget(self.points_label)
        
        # Players remaining indicator (smaller text, wraps)
        self.players_label = QLabel("4 PLAYERS\nCAN ATTEMPT")
        self.players_label.setAlignment(Qt.AlignCenter)
        self.players_label.setWordWrap(True)
        self.players_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
            "background: transparent; border: none; padding-top: 4px; "
            "line-height: 1.3;"
        )
        layout.addWidget(self.players_label)
        
        # Already attempted players (crosses) - in 2x2 grid for space
        self.attempted_widget = QWidget()
        attempted_layout = QHBoxLayout(self.attempted_widget)
        attempted_layout.setContentsMargins(0, 6, 0, 0)  # Increased top margin
        attempted_layout.setSpacing(10)  # Increased from 4 to 10 for more space
        attempted_layout.setAlignment(Qt.AlignCenter)
        
        self.player_indicators = {}
        for i in range(1, 5):
            indicator = QLabel(f"P{i}")
            indicator.setAlignment(Qt.AlignCenter)
            indicator.setFixedSize(38, 38)  # Increased from 32x32
            indicator.setStyleSheet(
                "QLabel { "
                "background: rgba(255, 255, 255, 0.1); "
                "border: 2px solid rgba(255, 255, 255, 0.3); "
                "border-radius: 19px; "  # Updated for new size
                "color: rgba(255, 255, 255, 0.5); "
                "font-size: 11px; font-weight: 900; "  # Slightly bigger
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
        
        # Update attempt number (with line break for better fit)
        attempt_text = self._get_ordinal(attempt_number)
        self.attempt_label.setText(f"{attempt_text}\nATTEMPT")
        
        # Update points (with line break)
        if points_available == 1:
            self.points_label.setText("1 POINT\nAVAILABLE")
        else:
            self.points_label.setText(f"{points_available} POINTS\nAVAILABLE")
        
        # Update players remaining (with line break for better readability)
        num_remaining = len(players_remaining)
        if num_remaining == 0:
            self.players_label.setText("NO PLAYERS\nREMAINING")
        elif num_remaining == 1:
            self.players_label.setText(f"1 PLAYER\nCAN ATTEMPT\n(P{players_remaining[0]})")
        else:
            player_list = ", ".join([f"P{p}" for p in players_remaining])
            self.players_label.setText(f"{num_remaining} PLAYERS\nCAN ATTEMPT\n({player_list})")
        
        # Update player indicators
        all_players = {1, 2, 3, 4}
        attempted_players = all_players - set(players_remaining)
        
        for player_id, indicator in self.player_indicators.items():
            if player_id in attempted_players:
                # Failed attempt - red X
                indicator.setStyleSheet(
                    "QLabel { "
                    "background: rgba(231, 76, 60, 0.3); "
                    "border: 2px solid #e74c3c; "
                    "border-radius: 16px; "
                    "color: #e74c3c; "
                    "font-size: 15px; font-weight: 900; "
                    "}"
                )
                indicator.setText("✗")
            else:
                # Still available - green circle
                indicator.setStyleSheet(
                    "QLabel { "
                    "background: rgba(57, 255, 20, 0.2); "
                    "border: 2px solid #39FF14; "
                    "border-radius: 16px; "
                    "color: #39FF14; "
                    "font-size: 10px; font-weight: 900; "
                    "}"
                )
                indicator.setText(f"P{player_id}")
        
        # Color-code attempt number
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
            f"font-size: 24px; font-weight: 900; color: {color}; "
            f"background: transparent; border: none; padding: 4px; "
            f"line-height: 1.1;"
        )
    
    def reset(self):
        """Reset to initial state"""
        self.hide()
        for indicator in self.player_indicators.values():
            indicator.setStyleSheet(
                "QLabel { "
                "background: rgba(255, 255, 255, 0.1); "
                "border: 2px solid rgba(255, 255, 255, 0.3); "
                "border-radius: 16px; "
                "color: rgba(255, 255, 255, 0.5); "
                "font-size: 10px; font-weight: 900; "
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
                "border-radius: 16px; "
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