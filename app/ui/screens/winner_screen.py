"""
Winner Screen - Game End Celebration
Compact centered popup dialog.
"""

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QGridLayout, QWidget
)


class WinnerScreen(QDialog):
    """Compact centered popup shown at game end."""

    DIALOG_W = 860
    DIALOG_H = 700

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(self.DIALOG_W, self.DIALOG_H)

        self.team_colors = {1: "#e74c3c", 2: "#3498db", 3: "#2ecc71", 4: "#f39c12"}

        self.setStyleSheet(
            "QDialog { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #0d1b2a, stop:1 #1a2a3a); "
            "border: 3px solid rgba(255,215,0,0.5); border-radius: 18px; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 22, 30, 22)
        main_layout.setSpacing(14)

        # ── Trophy + title row ────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        self.trophy = QLabel("🏆")
        self.trophy.setFixedWidth(80)
        self.trophy.setAlignment(Qt.AlignCenter)
        self.trophy.setStyleSheet("font-size: 56px; background: transparent;")
        header_row.addWidget(self.trophy)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        game_over = QLabel("GAME OVER")
        game_over.setStyleSheet(
            "font-size: 13px; font-weight: 900; color: rgba(255,255,255,0.5); "
            "background: transparent; letter-spacing: 3px;"
        )
        title_col.addWidget(game_over)

        self.winner_crown_label = QLabel("WINNER")
        self.winner_crown_label.setStyleSheet(
            "font-size: 32px; font-weight: 900; color: #ffd700; "
            "background: transparent; letter-spacing: 2px;"
        )
        title_col.addWidget(self.winner_crown_label)

        self.winner_name = QLabel("PLAYER 1")
        self.winner_name.setStyleSheet(
            "font-size: 42px; font-weight: 900; color: white; background: transparent;"
        )
        title_col.addWidget(self.winner_name)

        self.winner_score = QLabel("0 POINTS")
        self.winner_score.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #ffd700; background: transparent;"
        )
        title_col.addWidget(self.winner_score)

        header_row.addLayout(title_col, stretch=1)

        # FIX #9: give the layout a named reference so Qt does not silently
        # drop it.  Previously QHBoxLayout(winner_frame) was created and
        # immediately discarded — only accessed via winner_frame.layout() which
        # could return None if Qt's internal ref-count dropped it.
        winner_frame = QFrame()
        winner_frame.setStyleSheet(
            "QFrame { "
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, "
            "stop:0 rgba(57,255,20,0.15), stop:0.5 rgba(255,215,0,0.2), "
            "stop:1 rgba(57,255,20,0.15)); "
            "border: 2px solid #ffd700; border-radius: 14px; padding: 12px; }"
        )
        winner_frame_layout = QHBoxLayout(winner_frame)   # named — not anonymous
        winner_frame_layout.addLayout(header_row)
        main_layout.addWidget(winner_frame)

        # ── Final scores grid ─────────────────────────────────────────────────
        scores_frame = QFrame()
        scores_frame.setStyleSheet(
            "QFrame { background: rgba(20,30,45,0.8); "
            "border: 2px solid rgba(57,255,20,0.3); border-radius: 14px; }"
        )
        scores_layout = QVBoxLayout(scores_frame)
        scores_layout.setContentsMargins(16, 12, 16, 12)
        scores_layout.setSpacing(10)

        scores_title = QLabel("FINAL SCORES")
        scores_title.setAlignment(Qt.AlignCenter)
        scores_title.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: rgba(255,255,255,0.65); "
            "background: transparent; letter-spacing: 2px;"
        )
        scores_layout.addWidget(scores_title)

        self.scores_grid = QGridLayout()
        self.scores_grid.setSpacing(10)
        self.scores_grid.setContentsMargins(0, 0, 0, 0)

        self.player_score_widgets = {}
        for i in range(4):
            pid   = i + 1
            color = self.team_colors[pid]

            card = QFrame()
            card.setFixedHeight(66)
            card.setStyleSheet(
                f"QFrame {{ background: rgba(30,40,55,0.9); "
                f"border-left: 5px solid {color}; border-radius: 10px; padding: 8px; }}"
            )
            card_layout = QHBoxLayout(card)
            card_layout.setSpacing(12)
            card_layout.setContentsMargins(8, 4, 8, 4)

            rank_label = QLabel("#")
            rank_label.setAlignment(Qt.AlignCenter)
            rank_label.setFixedSize(42, 42)
            rank_label.setStyleSheet(
                f"font-size: 18px; font-weight: 900; color: white; "
                f"background: {color}; border-radius: 21px;"
            )
            card_layout.addWidget(rank_label)

            name_label = QLabel(f"PLAYER {pid}")
            name_label.setStyleSheet(
                "font-size: 16px; font-weight: 900; color: white; background: transparent;"
            )
            card_layout.addWidget(name_label, stretch=1)

            score_label = QLabel("0 pts")
            score_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            score_label.setStyleSheet(
                "font-size: 24px; font-weight: 900; color: #39FF14; "
                "background: transparent; padding-right: 6px;"
            )
            card_layout.addWidget(score_label)

            self.player_score_widgets[pid] = {"card": card, "rank": rank_label, "score": score_label}
            self.scores_grid.addWidget(card, i // 2, i % 2)

        scores_layout.addLayout(self.scores_grid)
        main_layout.addWidget(scores_frame, stretch=1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        self.btn_play_again = QPushButton("PLAY AGAIN")
        self.btn_play_again.setFixedHeight(52)
        self.btn_play_again.setStyleSheet(
            "QPushButton { background: rgba(57,255,20,0.22); border: 3px solid #39FF14; "
            "border-radius: 10px; font-size: 18px; font-weight: 900; color: white; }"
            "QPushButton:hover { background: rgba(57,255,20,0.42); }"
            "QPushButton:pressed { background: rgba(57,255,20,0.62); }"
        )
        btn_row.addWidget(self.btn_play_again)

        self.btn_exit = QPushButton("EXIT")
        self.btn_exit.setFixedHeight(52)
        self.btn_exit.setStyleSheet(
            "QPushButton { background: rgba(231,76,60,0.22); border: 3px solid #e74c3c; "
            "border-radius: 10px; font-size: 18px; font-weight: 900; color: white; }"
            "QPushButton:hover { background: rgba(231,76,60,0.42); }"
            "QPushButton:pressed { background: rgba(231,76,60,0.62); }"
        )
        btn_row.addWidget(self.btn_exit)

        main_layout.addLayout(btn_row)

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

    def set_results(self, scores: dict, winner_id: int):
        ranked_players = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if not ranked_players:
            self.winner_crown_label.setText("GAME OVER")
            self.winner_name.setText("No scores")
            self.winner_score.setText("0 POINTS")
            return

        top_score = ranked_players[0][1]
        winners   = [pid for pid, s in ranked_players if s == top_score] if top_score > 0 else []

        if not winners:
            self.winner_crown_label.setText("GAME OVER")
            self.winner_crown_label.setStyleSheet(
                "font-size: 32px; font-weight: 900; color: rgba(255,255,255,0.5); background: transparent;"
            )
            self.winner_name.setText("No winner")
            self.winner_name.setStyleSheet(
                "font-size: 42px; font-weight: 900; color: rgba(255,255,255,0.4); background: transparent;"
            )
        elif len(winners) > 1:
            self.winner_crown_label.setText("IT'S A TIE!")
            self.winner_crown_label.setStyleSheet(
                "font-size: 32px; font-weight: 900; color: #5ddbff; background: transparent;"
            )
            self.winner_name.setText(" & ".join(f"P{w}" for w in winners))
            self.winner_name.setStyleSheet(
                "font-size: 38px; font-weight: 900; color: #5ddbff; background: transparent;"
            )
        else:
            color = self.team_colors.get(winner_id, "#fff")
            self.winner_crown_label.setText("WINNER")
            self.winner_crown_label.setStyleSheet(
                "font-size: 32px; font-weight: 900; color: #ffd700; background: transparent;"
            )
            self.winner_name.setText(f"PLAYER {winner_id}")
            self.winner_name.setStyleSheet(
                f"font-size: 42px; font-weight: 900; color: {color}; background: transparent;"
            )

        self.winner_score.setText(f"{top_score} POINTS")

        rank_medals    = {1: "🥇", 2: "🥈", 3: "🥉", 4: "🎖️"}
        grid_positions = [(0,0),(0,1),(1,0),(1,1)]

        for rank, (pid, score) in enumerate(ranked_players, start=1):
            if pid not in self.player_score_widgets:
                continue
            w          = self.player_score_widgets[pid]
            row, col   = grid_positions[rank - 1]
            self.scores_grid.addWidget(w["card"], row, col)
            w["rank"].setText(rank_medals[rank])
            w["score"].setText(f"{score} pts")

            color    = self.team_colors.get(pid, "#888")
            is_winner = pid in winners

            if is_winner and len(winners) == 1:
                wc = self.team_colors.get(winner_id, color)
                w["card"].setStyleSheet(
                    f"QFrame {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                    f"stop:0 rgba(255,215,0,0.25),stop:1 {wc}30); "
                    f"border-left: 5px solid {wc}; border: 2px solid #ffd700; "
                    f"border-radius: 10px; padding: 8px; }}"
                )
                w["score"].setStyleSheet(
                    "font-size: 24px; font-weight: 900; color: #ffd700; "
                    "background: transparent; padding-right: 6px;"
                )
            elif is_winner:
                w["card"].setStyleSheet(
                    "QFrame { background: rgba(93,219,255,0.15); "
                    "border: 2px solid #5ddbff; border-radius: 10px; padding: 8px; }"
                )
                w["score"].setStyleSheet(
                    "font-size: 24px; font-weight: 900; color: #5ddbff; "
                    "background: transparent; padding-right: 6px;"
                )
            else:
                w["card"].setStyleSheet(
                    f"QFrame {{ background: rgba(30,40,55,0.9); "
                    f"border-left: 5px solid {color}; border-radius: 10px; padding: 8px; }}"
                )
                w["score"].setStyleSheet(
                    "font-size: 24px; font-weight: 900; color: #39FF14; "
                    "background: transparent; padding-right: 6px;"
                )

        self._animate_trophy()

    # ── Trophy pulse ──────────────────────────────────────────────────────────

    def _animate_trophy(self):
        if hasattr(self, "pulse_timer"):
            self.pulse_timer.stop()    # FIX: always stop prior timer, not just when isActive()
        self.pulse_state  = 0
        self._pulse_count = 0
        self.pulse_timer  = QTimer(self)
        self.pulse_timer.timeout.connect(self._pulse_trophy)
        self.pulse_timer.start(500)

    def _pulse_trophy(self):
        self._pulse_count += 1
        if self._pulse_count > 12:
            self.pulse_timer.stop()
            self.trophy.setStyleSheet("font-size: 56px; background: transparent;")
            return
        size = "68px" if self.pulse_state == 0 else "56px"
        self.trophy.setStyleSheet(f"font-size: {size}; background: transparent;")
        self.pulse_state ^= 1

    # ── Fade ──────────────────────────────────────────────────────────────────

    def fade_in(self, duration_ms: int = 500, callback=None):
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

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        if hasattr(self, "pulse_timer"):
            self.pulse_timer.stop()