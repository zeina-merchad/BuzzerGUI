"""
Winner Screen - Game End Celebration
Shows final scores, winner, and options to play again or exit
"""

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout
)
from PySide6.QtGui import QFont


class WinnerScreen(QWidget):
    """Full-screen winner celebration screen"""
    
    def __init__(self):
        super().__init__()
        
        # Team colors
        self.team_colors = {
            1: "#e74c3c",  # Red
            2: "#3498db",  # Blue
            3: "#2ecc71",  # Green
            4: "#f39c12",  # Orange
        }
        
        # Dark background with subtle gradient
        self.setStyleSheet(
            "QWidget { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #0a0e27, stop:1 #1a1f3a); "
            "}"
        )
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)
        
        # =====================================================================
        # TROPHY AND TITLE
        # =====================================================================
        
        header = QWidget()
        header.setStyleSheet("QWidget { background: transparent; }")
        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(15)
        
        # Trophy emoji (animated)
        self.trophy = QLabel("🏆")
        self.trophy.setAlignment(Qt.AlignCenter)
        self.trophy.setStyleSheet(
            "font-size: 120px; background: transparent; "
            "padding: 20px;"
        )
        header_layout.addWidget(self.trophy)
        
        # Game Over title
        title = QLabel("GAME OVER!")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 48px; font-weight: 900; color: #39FF14; "
            "background: transparent; letter-spacing: 3px;"
        )
        header_layout.addWidget(title)
        
        main_layout.addWidget(header)
        
        # =====================================================================
        # WINNER ANNOUNCEMENT
        # =====================================================================
        
        self.winner_frame = QFrame()
        self.winner_frame.setStyleSheet(
            "QFrame { "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 rgba(57, 255, 20, 0.2), "
            "stop:0.5 rgba(255, 215, 0, 0.3), "
            "stop:1 rgba(57, 255, 20, 0.2)); "
            "border: 4px solid #ffd700; "
            "border-radius: 20px; "
            "padding: 30px; "
            "}"
        )
        
        winner_layout = QVBoxLayout(self.winner_frame)
        winner_layout.setSpacing(10)
        
        winner_label = QLabel("👑 WINNER 👑")
        winner_label.setAlignment(Qt.AlignCenter)
        winner_label.setStyleSheet(
            "font-size: 24px; font-weight: 900; color: #ffd700; "
            "background: transparent; letter-spacing: 2px;"
        )
        winner_layout.addWidget(winner_label)
        
        self.winner_name = QLabel("PLAYER 1")
        self.winner_name.setAlignment(Qt.AlignCenter)
        self.winner_name.setStyleSheet(
            "font-size: 64px; font-weight: 900; color: white; "
            "background: transparent; padding: 20px;"
        )
        winner_layout.addWidget(self.winner_name)
        
        self.winner_score = QLabel("15 POINTS")
        self.winner_score.setAlignment(Qt.AlignCenter)
        self.winner_score.setStyleSheet(
            "font-size: 36px; font-weight: 700; color: #ffd700; "
            "background: transparent;"
        )
        winner_layout.addWidget(self.winner_score)
        
        main_layout.addWidget(self.winner_frame)
        
        # =====================================================================
        # FINAL SCORES - ALL PLAYERS
        # =====================================================================
        
        scores_container = QFrame()
        scores_container.setStyleSheet(
            "QFrame { "
            "background: rgba(20, 30, 45, 0.6); "
            "border: 3px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 16px; "
            "padding: 25px; "
            "}"
        )
        
        scores_layout = QVBoxLayout(scores_container)
        scores_layout.setSpacing(15)
        
        scores_title = QLabel("FINAL SCORES")
        scores_title.setAlignment(Qt.AlignCenter)
        scores_title.setStyleSheet(
            "font-size: 20px; font-weight: 900; color: white; "
            "background: transparent; letter-spacing: 2px; "
            "padding-bottom: 10px;"
        )
        scores_layout.addWidget(scores_title)
        
        # Grid for player scores
        self.scores_grid = QGridLayout()
        self.scores_grid.setSpacing(15)
        self.scores_grid.setContentsMargins(0, 0, 0, 0)
        
        self.player_score_widgets = {}
        
        for i in range(4):
            player_id = i + 1
            
            # Player card
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ "
                f"background: rgba(30, 40, 55, 0.8); "
                f"border-left: 5px solid {self.team_colors[player_id]}; "
                f"border-radius: 10px; "
                f"padding: 15px; "
                f"}}"
            )
            
            card_layout = QHBoxLayout(card)
            card_layout.setSpacing(15)
            
            # Rank badge
            rank_label = QLabel("#")
            rank_label.setAlignment(Qt.AlignCenter)
            rank_label.setFixedSize(50, 50)
            rank_label.setStyleSheet(
                f"font-size: 24px; font-weight: 900; "
                f"color: white; "
                f"background: {self.team_colors[player_id]}; "
                f"border-radius: 25px;"
            )
            card_layout.addWidget(rank_label)
            
            # Player name
            name_label = QLabel(f"PLAYER {player_id}")
            name_label.setStyleSheet(
                "font-size: 20px; font-weight: 900; color: white; "
                "background: transparent;"
            )
            card_layout.addWidget(name_label, stretch=1)
            
            # Score
            score_label = QLabel("0 pts")
            score_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            score_label.setStyleSheet(
                "font-size: 28px; font-weight: 900; color: #39FF14; "
                "background: transparent; padding-right: 10px;"
            )
            card_layout.addWidget(score_label)
            
            # Store references
            self.player_score_widgets[player_id] = {
                'card': card,
                'rank': rank_label,
                'score': score_label
            }
            
            # Add to grid (2x2)
            row = i // 2
            col = i % 2
            self.scores_grid.addWidget(card, row, col)
        
        scores_layout.addLayout(self.scores_grid)
        main_layout.addWidget(scores_container)
        
        # =====================================================================
        # ACTION BUTTONS
        # =====================================================================
        
        buttons_container = QWidget()
        buttons_container.setStyleSheet("QWidget { background: transparent; }")
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setSpacing(20)
        
        # Play Again button
        self.btn_play_again = QPushButton("🔄 PLAY AGAIN")
        self.btn_play_again.setFixedHeight(70)
        self.btn_play_again.setStyleSheet(
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.3); "
            "border: 3px solid #39FF14; "
            "border-radius: 12px; "
            "padding: 20px 40px; "
            "font-size: 24px; "
            "font-weight: 900; "
            "color: white; "
            "min-width: 250px; "
            "}"
            "QPushButton:hover { "
            "background: rgba(57, 255, 20, 0.5); "
            "border: 4px solid #39FF14; "
            "}"
            "QPushButton:pressed { background: rgba(57, 255, 20, 0.7); }"
        )
        buttons_layout.addWidget(self.btn_play_again)
        
        # Exit button
        self.btn_exit = QPushButton("🚪 EXIT")
        self.btn_exit.setFixedHeight(70)
        self.btn_exit.setStyleSheet(
            "QPushButton { "
            "background: rgba(231, 76, 60, 0.3); "
            "border: 3px solid #e74c3c; "
            "border-radius: 12px; "
            "padding: 20px 40px; "
            "font-size: 24px; "
            "font-weight: 900; "
            "color: white; "
            "min-width: 250px; "
            "}"
            "QPushButton:hover { "
            "background: rgba(231, 76, 60, 0.5); "
            "border: 4px solid #e74c3c; "
            "}"
            "QPushButton:pressed { background: rgba(231, 76, 60, 0.7); }"
        )
        buttons_layout.addWidget(self.btn_exit)
        
        main_layout.addWidget(buttons_container)
        
        # Stretch factors
        main_layout.setStretchFactor(header, 1)
        main_layout.setStretchFactor(self.winner_frame, 1)
        main_layout.setStretchFactor(scores_container, 2)
        main_layout.setStretchFactor(buttons_container, 0)
    
    def set_results(self, scores: dict, winner_id: int):
        """
        Display final results
        
        Args:
            scores: Dict of {player_id: score}
            winner_id: ID of winning player
        """
        # Sort players by score (descending)
        ranked_players = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Set winner
        winner_score = scores[winner_id]
        self.winner_name.setText(f"PLAYER {winner_id}")
        self.winner_score.setText(f"{winner_score} POINTS")
        
        # Highlight winner card with their color
        winner_color = self.team_colors[winner_id]
        self.winner_name.setStyleSheet(
            f"font-size: 64px; font-weight: 900; color: {winner_color}; "
            f"background: transparent; padding: 20px;"
        )
        
        # Update all player scores with rankings, re-ordered in the grid by rank
        rank_medals = {
            1: "🥇",
            2: "🥈", 
            3: "🥉",
            4: "4️⃣"
        }
        grid_positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

        for rank, (player_id, score) in enumerate(ranked_players, start=1):
            widgets = self.player_score_widgets[player_id]

            # Move card to rank-appropriate grid cell
            row, col = grid_positions[rank - 1]
            self.scores_grid.addWidget(widgets['card'], row, col)

            # Update rank badge
            widgets['rank'].setText(rank_medals[rank])
            
            # Update score
            widgets['score'].setText(f"{score} pts")
            
            # Highlight winner card
            if player_id == winner_id:
                widgets['card'].setStyleSheet(
                    f"QFrame {{ "
                    f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                    f"stop:0 rgba(255, 215, 0, 0.3), "
                    f"stop:1 {winner_color}40); "
                    f"border-left: 8px solid {winner_color}; "
                    f"border: 3px solid #ffd700; "
                    f"border-radius: 10px; "
                    f"padding: 15px; "
                    f"}}"
                )
                widgets['score'].setStyleSheet(
                    "font-size: 32px; font-weight: 900; color: #ffd700; "
                    "background: transparent; padding-right: 10px;"
                )
        
        # Animate trophy
        self._animate_trophy()
    
    def _animate_trophy(self):
        """Pulse animation for trophy — stops after 12 pulses."""
        self.pulse_state = 0
        self._pulse_count = 0
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self._pulse_trophy)
        self.pulse_timer.start(500)
    
    def _pulse_trophy(self):
        """Pulse the trophy between two sizes, stop after 12 pulses."""
        self._pulse_count += 1
        if self._pulse_count > 12:
            self.pulse_timer.stop()
            # Settle on the normal size
            self.trophy.setStyleSheet(
                "font-size: 120px; background: transparent; padding: 20px;"
            )
            return

        if self.pulse_state == 0:
            self.trophy.setStyleSheet(
                "font-size: 140px; background: transparent; padding: 20px;"
            )
            self.pulse_state = 1
        else:
            self.trophy.setStyleSheet(
                "font-size: 120px; background: transparent; padding: 20px;"
            )
            self.pulse_state = 0
    
    def cleanup(self):
        """Stop animations"""
        if hasattr(self, 'pulse_timer'):
            self.pulse_timer.stop()