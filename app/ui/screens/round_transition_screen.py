"""
Round Transition Screen
Compact popup dialog shown between rounds with current scores and next round info.
"""

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QGridLayout, QWidget
)


class RoundTransitionScreen(QDialog):
    """Compact centered popup shown between rounds."""

    DIALOG_W = 920
    DIALOG_H = 640

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setFixedSize(self.DIALOG_W, self.DIALOG_H)

        self.team_colors = {
            1: "#e74c3c",
            2: "#3498db",
            3: "#2ecc71",
            4: "#f39c12",
        }

        self.setStyleSheet(
            "QDialog { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #0d1b2a, stop:1 #1a2a3a); "
            "border: 3px solid rgba(57,255,20,0.5); "
            "border-radius: 18px; "
            "}"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 28)
        main_layout.setSpacing(18)

        # ── Round complete header
        self.round_complete_label = QLabel("ROUND 1 COMPLETE!")
        self.round_complete_label.setAlignment(Qt.AlignCenter)
        self.round_complete_label.setStyleSheet(
            "font-size: 36px; font-weight: 900; color: #39FF14; "
            "background: transparent; letter-spacing: 2px; padding: 8px;"
        )
        main_layout.addWidget(self.round_complete_label)

        # ── Standings frame
        standings_frame = QFrame()
        standings_frame.setStyleSheet(
            "QFrame { "
            "background: rgba(20, 30, 45, 0.85); "
            "border: 2px solid rgba(57, 255, 20, 0.35); "
            "border-radius: 14px; "
            "}"
        )
        standings_layout = QVBoxLayout(standings_frame)
        standings_layout.setContentsMargins(16, 12, 16, 12)
        standings_layout.setSpacing(10)

        standings_title = QLabel("CURRENT STANDINGS")
        standings_title.setAlignment(Qt.AlignCenter)
        standings_title.setStyleSheet(
            "font-size: 15px; font-weight: 900; color: rgba(255,255,255,0.7); "
            "background: transparent; letter-spacing: 2px;"
        )
        standings_layout.addWidget(standings_title)

        self.standings_grid = QGridLayout()
        self.standings_grid.setSpacing(10)
        self.standings_grid.setContentsMargins(0, 0, 0, 0)

        self.player_standing_widgets = {}

        for i in range(4):
            player_id = i + 1
            color = self.team_colors[player_id]

            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background: rgba(30,40,55,0.9); "
                f"border-left: 5px solid {color}; "
                f"border-radius: 10px; padding: 10px; }}"
            )
            card.setFixedHeight(72)

            card_layout = QHBoxLayout(card)
            card_layout.setSpacing(12)
            card_layout.setContentsMargins(8, 4, 8, 4)

            position_label = QLabel("#")
            position_label.setAlignment(Qt.AlignCenter)
            position_label.setFixedSize(44, 44)
            position_label.setStyleSheet(
                f"font-size: 20px; font-weight: 900; color: white; "
                f"background: {color}; border-radius: 22px;"
            )
            card_layout.addWidget(position_label)

            info_widget = QWidget()
            info_widget.setStyleSheet("QWidget { background: transparent; }")
            info_layout = QVBoxLayout(info_widget)
            info_layout.setSpacing(2)
            info_layout.setContentsMargins(0, 0, 0, 0)

            name_label = QLabel(f"PLAYER {player_id}")
            name_label.setStyleSheet(
                "font-size: 15px; font-weight: 900; color: white; background: transparent;"
            )
            info_layout.addWidget(name_label)

            score_label = QLabel("0 points")
            score_label.setStyleSheet(
                "font-size: 12px; font-weight: 700; "
                "color: rgba(255,255,255,0.6); background: transparent;"
            )
            info_layout.addWidget(score_label)

            card_layout.addWidget(info_widget, stretch=1)

            big_score_label = QLabel("0")
            big_score_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            big_score_label.setStyleSheet(
                "font-size: 30px; font-weight: 900; color: #39FF14; "
                "background: transparent; padding-right: 6px;"
            )
            card_layout.addWidget(big_score_label)

            self.player_standing_widgets[player_id] = {
                'card': card,
                'position': position_label,
                'score_text': score_label,
                'big_score': big_score_label,
            }

            self.standings_grid.addWidget(card, i // 2, i % 2)

        standings_layout.addLayout(self.standings_grid)
        main_layout.addWidget(standings_frame, stretch=1)

        # ── Next round row
        next_frame = QFrame()
        next_frame.setStyleSheet(
            "QFrame { background: rgba(57,255,20,0.10); "
            "border: 2px solid #39FF14; border-radius: 12px; padding: 10px; }"
        )
        next_layout = QHBoxLayout(next_frame)
        next_layout.setSpacing(16)

        up_next = QLabel("UP NEXT")
        up_next.setStyleSheet(
            "font-size: 13px; font-weight: 900; color: rgba(255,255,255,0.55); "
            "background: transparent; letter-spacing: 2px;"
        )
        next_layout.addWidget(up_next)

        self.next_round_label = QLabel("ROUND 2")
        self.next_round_label.setStyleSheet(
            "font-size: 26px; font-weight: 900; color: #39FF14; background: transparent;"
        )
        next_layout.addWidget(self.next_round_label)

        next_layout.addStretch()

        self.questions_info_label = QLabel("5 Questions")
        self.questions_info_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; "
            "color: rgba(255,255,255,0.6); background: transparent;"
        )
        next_layout.addWidget(self.questions_info_label)

        main_layout.addWidget(next_frame)

        # ── Continue button
        self.btn_continue = QPushButton("START NEXT ROUND")
        self.btn_continue.setFixedHeight(56)
        self.btn_continue.setStyleSheet(
            "QPushButton { "
            "background: rgba(57,255,20,0.22); "
            "border: 3px solid #39FF14; border-radius: 10px; "
            "font-size: 20px; font-weight: 900; color: white; }"
            "QPushButton:hover { background: rgba(57,255,20,0.42); }"
            "QPushButton:pressed { background: rgba(57,255,20,0.62); }"
            "QPushButton:disabled { background: rgba(80,80,80,0.2); "
            "border-color: #555; color: #666; }"
        )
        main_layout.addWidget(self.btn_continue)

        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet(
            "font-size: 13px; color: rgba(255,255,255,0.4); background: transparent;"
        )
        self.countdown_label.hide()
        main_layout.addWidget(self.countdown_label)

    # ── Centering ─────────────────────────────────────────────────────────────

    def center_on_parent(self):
        if self.parent():
            pg = self.parent().geometry()
            self.move(
                pg.x() + (pg.width()  - self.width())  // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )
        else:
            from PySide6.QtGui import QGuiApplication
            sg = QGuiApplication.primaryScreen().geometry()
            self.move(
                (sg.width()  - self.width())  // 2,
                (sg.height() - self.height()) // 2,
            )

    # ── Data ──────────────────────────────────────────────────────────────────

    def set_round_info(self, completed_round: int, next_round: int,
                       scores: dict, questions_in_next: int):
        self.round_complete_label.setText(f"ROUND {completed_round} COMPLETE!")
        self.next_round_label.setText(f"ROUND {next_round}")
        self.questions_info_label.setText(
            "1 Question" if questions_in_next == 1 else f"{questions_in_next} Questions"
        )

        ranked_players = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        position_emojis = {1: "🥇", 2: "🥈", 3: "🥉", 4: "🎖️"}
        grid_positions  = [(0, 0), (0, 1), (1, 0), (1, 1)]

        for position, (player_id, score) in enumerate(ranked_players, start=1):
            if player_id not in self.player_standing_widgets:
                continue
            w = self.player_standing_widgets[player_id]

            row, col = grid_positions[position - 1]
            self.standings_grid.addWidget(w['card'], row, col)

            w['position'].setText(position_emojis[position])
            w['score_text'].setText(f"{score} points")
            w['big_score'].setText(str(score))

            color = self.team_colors.get(player_id, "#888")
            if position == 1:
                w['card'].setStyleSheet(
                    f"QFrame {{ "
                    f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                    f"stop:0 rgba(255,215,0,0.18),stop:1 {color}30); "
                    f"border-left: 5px solid {color}; border: 2px solid #ffd700; "
                    f"border-radius: 10px; padding: 10px; }}"
                )
                w['big_score'].setStyleSheet(
                    "font-size: 30px; font-weight: 900; color: #ffd700; "
                    "background: transparent; padding-right: 6px;"
                )
            else:
                w['card'].setStyleSheet(
                    f"QFrame {{ background: rgba(30,40,55,0.9); "
                    f"border-left: 5px solid {color}; "
                    f"border-radius: 10px; padding: 10px; }}"
                )
                w['big_score'].setStyleSheet(
                    "font-size: 30px; font-weight: 900; color: #39FF14; "
                    "background: transparent; padding-right: 6px;"
                )

    # ── Fade ──────────────────────────────────────────────────────────────────

    def fade_in(self, duration_ms: int = 400, callback=None):
        self.center_on_parent()
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(duration_ms)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if callback:
            self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    def fade_out(self, duration_ms: int = 300, callback=None):
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(duration_ms)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        if callback:
            self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    # ── Countdown ─────────────────────────────────────────────────────────────

    def start_auto_countdown(self, seconds: int = 10):
        if hasattr(self, 'countdown_timer') and self.countdown_timer.isActive():
            self.countdown_timer.stop()
        self.countdown_label.show()
        self.countdown_seconds = seconds
        self._update_countdown()
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._countdown_tick)
        self.countdown_timer.start(1000)

    def stop_auto_countdown(self):
        if hasattr(self, 'countdown_timer') and self.countdown_timer.isActive():
            self.countdown_timer.stop()
        self.countdown_label.hide()

    def _countdown_tick(self):
        self.countdown_seconds -= 1
        if self.countdown_seconds <= 0:
            self.countdown_timer.stop()
            self.btn_continue.click()
        else:
            self._update_countdown()

    def _update_countdown(self):
        s = self.countdown_seconds
        self.countdown_label.setText(
            f"Auto-starting in {s} second{'s' if s != 1 else ''}..."
        )

    def cleanup(self):
        self.stop_auto_countdown()