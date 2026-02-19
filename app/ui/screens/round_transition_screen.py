"""
Round Transition Screen
Shows between rounds with current scores and next round info
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout
)


class RoundTransitionScreen(QWidget):
    """Screen shown between rounds"""
    
    def __init__(self):
        super().__init__()
        
        # Team colors
        self.team_colors = {
            1: "#e74c3c",  # Red
            2: "#3498db",  # Blue
            3: "#2ecc71",  # Green
            4: "#f39c12",  # Orange
        }
        
        # Dark background
        self.setStyleSheet(
            "QWidget { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #0a0e27, stop:1 #1a1f3a); "
            "}"
        )
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(60, 60, 60, 60)
        main_layout.setSpacing(40)
        
        # =====================================================================
        # ROUND COMPLETE ANNOUNCEMENT
        # =====================================================================
        
        self.round_complete_label = QLabel("🎯 ROUND 1 COMPLETE!")
        self.round_complete_label.setAlignment(Qt.AlignCenter)
        self.round_complete_label.setStyleSheet(
            "font-size: 56px; font-weight: 900; color: #39FF14; "
            "background: transparent; letter-spacing: 3px; padding: 30px;"
        )
        main_layout.addWidget(self.round_complete_label)
        
        # =====================================================================
        # CURRENT STANDINGS
        # =====================================================================
        
        standings_frame = QFrame()
        standings_frame.setStyleSheet(
            "QFrame { "
            "background: rgba(20, 30, 45, 0.7); "
            "border: 4px solid rgba(57, 255, 20, 0.4); "
            "border-radius: 20px; "
            "padding: 35px; "
            "}"
        )
        
        standings_layout = QVBoxLayout(standings_frame)
        standings_layout.setSpacing(20)
        
        standings_title = QLabel("📊 CURRENT STANDINGS")
        standings_title.setAlignment(Qt.AlignCenter)
        standings_title.setStyleSheet(
            "font-size: 28px; font-weight: 900; color: white; "
            "background: transparent; letter-spacing: 2px; "
            "padding-bottom: 15px;"
        )
        standings_layout.addWidget(standings_title)
        
        # Grid for player standings (2x2)
        self.standings_grid = QGridLayout()
        self.standings_grid.setSpacing(20)
        self.standings_grid.setContentsMargins(0, 0, 0, 0)
        
        self.player_standing_widgets = {}
        
        for i in range(4):
            player_id = i + 1
            
            # Player standing card
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ "
                f"background: rgba(30, 40, 55, 0.9); "
                f"border-left: 6px solid {self.team_colors[player_id]}; "
                f"border-radius: 12px; "
                f"padding: 20px; "
                f"}}"
            )
            
            card_layout = QHBoxLayout(card)
            card_layout.setSpacing(20)
            
            # Position badge
            position_label = QLabel("#")
            position_label.setAlignment(Qt.AlignCenter)
            position_label.setFixedSize(60, 60)
            position_label.setStyleSheet(
                f"font-size: 28px; font-weight: 900; "
                f"color: white; "
                f"background: {self.team_colors[player_id]}; "
                f"border-radius: 30px;"
            )
            card_layout.addWidget(position_label)
            
            # Player info
            info_widget = QWidget()
            info_widget.setStyleSheet("QWidget { background: transparent; }")
            info_layout = QVBoxLayout(info_widget)
            info_layout.setSpacing(5)
            info_layout.setContentsMargins(0, 0, 0, 0)
            
            name_label = QLabel(f"PLAYER {player_id}")
            name_label.setStyleSheet(
                "font-size: 22px; font-weight: 900; color: white; "
                "background: transparent;"
            )
            info_layout.addWidget(name_label)
            
            score_label = QLabel("0 points")
            score_label.setStyleSheet(
                "font-size: 18px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
                "background: transparent;"
            )
            info_layout.addWidget(score_label)
            
            card_layout.addWidget(info_widget, stretch=1)
            
            # Large score display
            big_score_label = QLabel("0")
            big_score_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            big_score_label.setStyleSheet(
                "font-size: 42px; font-weight: 900; color: #39FF14; "
                "background: transparent; padding-right: 10px;"
            )
            card_layout.addWidget(big_score_label)
            
            # Store references
            self.player_standing_widgets[player_id] = {
                'card': card,
                'position': position_label,
                'score_text': score_label,
                'big_score': big_score_label
            }
            
            # Add to grid (2x2)
            row = i // 2
            col = i % 2
            self.standings_grid.addWidget(card, row, col)
        
        standings_layout.addLayout(self.standings_grid)
        main_layout.addWidget(standings_frame, stretch=1)
        
        # =====================================================================
        # NEXT ROUND INFO
        # =====================================================================
        
        next_round_frame = QFrame()
        next_round_frame.setStyleSheet(
            "QFrame { "
            "background: rgba(57, 255, 20, 0.15); "
            "border: 3px solid #39FF14; "
            "border-radius: 16px; "
            "padding: 25px; "
            "}"
        )
        
        next_round_layout = QVBoxLayout(next_round_frame)
        next_round_layout.setSpacing(10)
        
        up_next_label = QLabel("⏭️ UP NEXT")
        up_next_label.setAlignment(Qt.AlignCenter)
        up_next_label.setStyleSheet(
            "font-size: 20px; font-weight: 900; color: rgba(255, 255, 255, 0.7); "
            "background: transparent; letter-spacing: 2px;"
        )
        next_round_layout.addWidget(up_next_label)
        
        self.next_round_label = QLabel("ROUND 2")
        self.next_round_label.setAlignment(Qt.AlignCenter)
        self.next_round_label.setStyleSheet(
            "font-size: 40px; font-weight: 900; color: #39FF14; "
            "background: transparent; padding: 10px;"
        )
        next_round_layout.addWidget(self.next_round_label)
        
        self.questions_info_label = QLabel("5 Questions")
        self.questions_info_label.setAlignment(Qt.AlignCenter)
        self.questions_info_label.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
            "background: transparent;"
        )
        next_round_layout.addWidget(self.questions_info_label)
        
        main_layout.addWidget(next_round_frame)
        
        # =====================================================================
        # CONTINUE BUTTON
        # =====================================================================
        
        self.btn_continue = QPushButton("▶️ START NEXT ROUND")
        self.btn_continue.setFixedHeight(80)
        self.btn_continue.setStyleSheet(
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.3); "
            "border: 4px solid #39FF14; "
            "border-radius: 12px; "
            "padding: 25px 50px; "
            "font-size: 28px; "
            "font-weight: 900; "
            "color: white; "
            "}"
            "QPushButton:hover { "
            "background: rgba(57, 255, 20, 0.5); "
            "border: 5px solid #39FF14; "
            "}"
            "QPushButton:pressed { background: rgba(57, 255, 20, 0.7); }"
        )
        main_layout.addWidget(self.btn_continue, alignment=Qt.AlignCenter)
        
        # Auto-continue countdown (optional)
        self.countdown_label = QLabel("Auto-starting in 10 seconds...")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: rgba(255, 255, 255, 0.5); "
            "background: transparent; padding: 10px;"
        )
        self.countdown_label.hide()  # Hidden by default
        main_layout.addWidget(self.countdown_label)
        
        # Stretch factors
        main_layout.setStretchFactor(self.round_complete_label, 0)
        main_layout.setStretchFactor(standings_frame, 2)
        main_layout.setStretchFactor(next_round_frame, 0)
        main_layout.setStretchFactor(self.btn_continue, 0)
    
    def set_round_info(self, completed_round: int, next_round: int, scores: dict, questions_in_next: int):
        """
        Set round transition information
        
        Args:
            completed_round: Round number that just finished
            next_round: Next round number
            scores: Dict of {player_id: score}
            questions_in_next: Number of questions in next round
        """
        # Update round labels
        self.round_complete_label.setText(f"🎯 ROUND {completed_round} COMPLETE!")
        self.next_round_label.setText(f"ROUND {next_round}")
        
        if questions_in_next == 1:
            self.questions_info_label.setText("1 Question")
        else:
            self.questions_info_label.setText(f"{questions_in_next} Questions")
        
        # Sort players by score
        ranked_players = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Position indicators
        position_emojis = {
            1: "🥇",
            2: "🥈",
            3: "🥉",
            4:  "4️⃣"
        }
        
        # Update standings
        for position, (player_id, score) in enumerate(ranked_players, start=1):
            widgets = self.player_standing_widgets[player_id]
            
            # Update position
            widgets['position'].setText(position_emojis[position])
            
            # Update scores
            widgets['score_text'].setText(f"{score} points")
            widgets['big_score'].setText(str(score))
            
            # Highlight leader
            if position == 1:
                widgets['card'].setStyleSheet(
                    f"QFrame {{ "
                    f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                    f"stop:0 rgba(255, 215, 0, 0.2), "
                    f"stop:1 {self.team_colors[player_id]}40); "
                    f"border-left: 8px solid {self.team_colors[player_id]}; "
                    f"border: 3px solid #ffd700; "
                    f"border-radius: 12px; "
                    f"padding: 20px; "
                    f"}}"
                )
                widgets['big_score'].setStyleSheet(
                    "font-size: 48px; font-weight: 900; color: #ffd700; "
                    "background: transparent; padding-right: 10px;"
                )
            else:
                widgets['card'].setStyleSheet(
                    f"QFrame {{ "
                    f"background: rgba(30, 40, 55, 0.9); "
                    f"border-left: 6px solid {self.team_colors[player_id]}; "
                    f"border-radius: 12px; "
                    f"padding: 20px; "
                    f"}}"
                )
                widgets['big_score'].setStyleSheet(
                    "font-size: 42px; font-weight: 900; color: #39FF14; "
                    "background: transparent; padding-right: 10px;"
                )
    
    def start_auto_countdown(self, seconds: int = 10):
        """Start auto-continue countdown"""
        self.countdown_label.show()
        self.countdown_seconds = seconds
        self._update_countdown()
        
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._countdown_tick)
        self.countdown_timer.start(1000)  # 1 second intervals
    
    def stop_auto_countdown(self):
        """Stop auto-continue countdown"""
        if hasattr(self, 'countdown_timer'):
            self.countdown_timer.stop()
        self.countdown_label.hide()
    
    def _countdown_tick(self):
        """Update countdown each second"""
        self.countdown_seconds -= 1
        
        if self.countdown_seconds <= 0:
            self.countdown_timer.stop()
            self.btn_continue.click()  # Auto-click continue
        else:
            self._update_countdown()
    
    def _update_countdown(self):
        """Update countdown display"""
        if self.countdown_seconds == 1:
            self.countdown_label.setText("Auto-starting in 1 second...")
        else:
            self.countdown_label.setText(f"Auto-starting in {self.countdown_seconds} seconds...")
    
    def cleanup(self):
        """Stop any running timers"""
        self.stop_auto_countdown()