from typing import List, Optional, Set
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QFrame, QGridLayout, QDialog
)
from pathlib import Path

from app.core.engine import GameEngine
from app.core.state import Phase
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend
from app.core.sound_manager import create_sound_manager

from app.ui.widgets.timer_widget import TimerWidget
from app.ui.widgets.options_view import OptionsView
from app.ui.widgets.media_view import MediaView
from app.ui.widgets.cascading_widget import CascadingAttemptsWidget
from app.ui.screens.winner_screen import WinnerScreen
from app.ui.screens.round_transition_screen import RoundTransitionScreen


class CornerPlayerCard(QFrame):
    """Player card with hardware connection indicator"""

    def __init__(self, player_id: int):
        super().__init__()
        self.player_id = player_id
        self.is_buzzed = False
        self.is_hardware_connected = False
        self.is_eliminated = False  # Track elimination status

        self.team_colors = {
            1: "#e74c3c",  # Red
            2: "#3498db",  # Blue
            3: "#2ecc71",  # Green
            4: "#f39c12",  # Orange
        }
        self.color = self.team_colors.get(player_id, "#888888")

        self.setFixedSize(150, 180)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        # Player icon (circle indicating status)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(100, 100)
        self._set_disconnected_icon()

        # Player label
        self.label = QLabel(f"P{player_id}: WAITING")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: white; "
            "background: rgba(100, 100, 100, 0.7); "
            "padding: 8px 12px; border-radius: 8px;"
        )

        # Layout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon, alignment=Qt.AlignCenter)
        lay.addWidget(self.label)

    def _set_disconnected_icon(self, score: int = 0):
        """Gray circle - disconnected - with score inside"""
        self.icon.setStyleSheet(
            "QLabel { "
            "background: rgba(85, 85, 85, 0.2); "
            "border: 4px solid #555555; "
            "border-radius: 50px; "
            "color: #999999; "
            "font-size: 36px; "
            "font-weight: 900; "
            "}"
        )
        self.icon.setText(str(score))

    def _set_connected_icon(self, score: int = 0):
        """Colored circle - connected - with score inside"""
        self.icon.setStyleSheet(
            f"QLabel {{ "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {self.color}40, stop:1 {self.color}20); "
            f"border: 4px solid {self.color}; "
            f"border-radius: 50px; "
            f"color: white; "
            f"font-size: 36px; "
            f"font-weight: 900; "
            f"}}"
        )
        self.icon.setText(str(score))

    def _set_buzzed_icon(self, score: int = 0):
        """Buzzed state - raised hand emoji (always visible when locked)"""
        self.icon.setStyleSheet(
            "QLabel { "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 rgba(93, 219, 255, 0.4), stop:1 rgba(93, 219, 255, 0.2)); "
            "border: 5px solid #5ddbff; "
            "border-radius: 50px; "
            "color: white; "
            "font-size: 52px; "
            "font-weight: 900; "
            "}"
        )
        self.icon.setText("✋")  # Raised hand - stays visible while locked

    def _set_eliminated_icon(self, score: int = 0):
        """Eliminated state - with score inside"""
        self.icon.setStyleSheet(
            "QLabel { "
            "background: rgba(231, 76, 60, 0.3); "
            "border: 5px solid #e74c3c; "
            "border-radius: 50px; "
            "color: #e74c3c; "
            "font-size: 36px; "
            "font-weight: 900; "
            "}"
        )
        self.icon.setText(str(score))

    def set_connected(self, is_connected: bool):
        """Update connection status"""
        self.is_hardware_connected = is_connected

        # Get current score to display in circle
        score = 0
        try:
            score_text = self.label.text()
            if "pts" in score_text:
                score = int(score_text.split("pts")[0].split()[-1])
            elif "(" in score_text and "pts)" in score_text:
                # Handle "ELIMINATED (5pts)" format
                score = int(score_text.split("(")[1].split("pts)")[0])
        except:
            pass

        if is_connected:
            self._set_connected_icon(score)
            self.label.setText(f"P{self.player_id}: READY")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                f"background: {self.color}; "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            self._set_disconnected_icon(score)
            self.label.setText(f"P{self.player_id}: WAITING")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                "background: rgba(100, 100, 100, 0.7); "
                "padding: 8px 12px; border-radius: 8px;"
            )

    def set_eliminated(self, is_eliminated: bool):
        """Set elimination status"""
        self.is_eliminated = is_eliminated

        # Get current score
        score = 0
        try:
            score_text = self.label.text()
            if "pts" in score_text:
                score = int(score_text.split("pts")[0].split()[-1])
            elif "(" in score_text and "pts)" in score_text:
                score = int(score_text.split("(")[1].split("pts)")[0])
        except:
            pass

        if is_eliminated:
            self._set_eliminated_icon(score)
            self.label.setText(f"P{self.player_id}: ELIMINATED")
            self.label.setStyleSheet(
                "font-size: 13px; font-weight: 900; color: white; "
                "background: rgba(231, 76, 60, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            # Restore normal state based on connection
            if self.is_hardware_connected:
                self._set_connected_icon(score)
                self.set_score(score)
            else:
                self._set_disconnected_icon(score)
                self.label.setText(f"P{self.player_id}: WAITING")

    def set_score(self, value: int):
        """Update score display - always shows in circle except when buzzed"""
        score = int(value)
        
        if self.is_eliminated:
            # Eliminated state - show score in circle with red styling
            self._set_eliminated_icon(score)
            self.label.setText(f"P{self.player_id}: ELIMINATED ({score}pts)")
            self.label.setStyleSheet(
                "font-size: 13px; font-weight: 900; color: white; "
                "background: rgba(231, 76, 60, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        elif self.is_buzzed:
            # Buzzed state - show HAND in circle, score in label
            self._set_buzzed_icon(score)
            self.label.setText(f"P{self.player_id}: BUZZED! ({score}pts)")
            self.label.setStyleSheet(
                "font-size: 13px; font-weight: 900; color: white; "
                "background: rgba(93, 219, 255, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        elif self.is_hardware_connected:
            # Connected state - show score in circle with team color
            self._set_connected_icon(score)
            self.label.setText(f"P{self.player_id}: {score}pts")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                f"background: {self.color}; "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            # Disconnected state - show score in circle with gray styling
            self._set_disconnected_icon(score)
            self.label.setText(f"P{self.player_id}: WAITING ({score}pts)")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                "background: rgba(100, 100, 100, 0.7); "
                "padding: 8px 12px; border-radius: 8px;"
            )

    def highlight_locked(self, locked: bool):
        """Highlight when player is locked in"""
        if self.is_eliminated:
            return  # Don't highlight eliminated players

        self.is_buzzed = locked

        # Get current score
        score = 0
        try:
            score_text = self.label.text()
            if "pts" in score_text:
                score = int(score_text.split("pts")[0].split()[-1])
        except:
            pass

        if locked:
            self._set_buzzed_icon(score)
        elif self.is_hardware_connected:
            self._set_connected_icon(score)
        else:
            self._set_disconnected_icon(score)

        # Update label
        self.set_score(score)


class HostScreen(QWidget):
    """Main game screen with auto-judging from ESP32 answer buttons"""

    def __init__(self, engine: GameEngine, mqtt_backend: MQTTBuzzerBackend):
        super().__init__()
        self.engine = engine
        self.mqtt_backend = mqtt_backend

        # Game state
        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1

        # Winner screen
        self.winner_screen = WinnerScreen()
        self.winner_screen.hide()
        self.winner_screen.btn_play_again.clicked.connect(self._play_again)
        self.winner_screen.btn_exit.clicked.connect(self._exit_game)

        # Round transition screen
        self.round_transition_screen = RoundTransitionScreen()
        self.round_transition_screen.hide()
        self.round_transition_screen.btn_continue.clicked.connect(self._continue_to_next_round)

        # Setup focus and styling
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QWidget { background: #0d1b2a; }")

        # Sound effects
        self.sfx = create_sound_manager()
        self._warned_7 = False
        self._warned_3 = False

        # Main layout
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # =====================================================================
        # GAME AREA GRID
        # =====================================================================
        game_grid = QGridLayout()
        game_grid.setHorizontalSpacing(20)
        game_grid.setVerticalSpacing(15)

        # Player cards dictionary
        self.player_cards = {}

        # Left column (Player 1, cascading widget, Player 3)
        left_column = QWidget()
        left_column.setStyleSheet("QWidget { background: transparent; }")
        left_layout = QVBoxLayout(left_column)
        left_layout.setSpacing(20)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.player_cards[1] = CornerPlayerCard(1)
        left_layout.addWidget(self.player_cards[1], alignment=Qt.AlignTop | Qt.AlignCenter)

        # Cascading attempts widget
        self.cascading_widget = CascadingAttemptsWidget()
        left_layout.addWidget(self.cascading_widget, alignment=Qt.AlignCenter)
        left_layout.addStretch(1)

        self.player_cards[3] = CornerPlayerCard(3)
        left_layout.addWidget(self.player_cards[3], alignment=Qt.AlignBottom | Qt.AlignCenter)

        game_grid.addWidget(left_column, 0, 0, 3, 1)

        # Right column (Player 2, Player 4)
        right_column = QWidget()
        right_column.setStyleSheet("QWidget { background: transparent; }")
        right_layout = QVBoxLayout(right_column)
        right_layout.setSpacing(20)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.player_cards[2] = CornerPlayerCard(2)
        right_layout.addWidget(self.player_cards[2], alignment=Qt.AlignTop | Qt.AlignCenter)

        right_layout.addStretch(1)

        self.player_cards[4] = CornerPlayerCard(4)
        right_layout.addWidget(self.player_cards[4], alignment=Qt.AlignBottom | Qt.AlignCenter)

        game_grid.addWidget(right_column, 0, 2, 3, 1)

        # Center content (timer, media, question, options)
        center_widget = QWidget()
        center_widget.setStyleSheet("QWidget { background: transparent; }")
        center_widget.setMaximumWidth(1000)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(15)
        center_layout.setContentsMargins(60, 0, 60, 0)

        # Timer widget
        self.timer = TimerWidget()
        center_layout.addWidget(self.timer, alignment=Qt.AlignCenter)

        # Media view
        self.media = MediaView()
        center_layout.addWidget(self.media, stretch=1)

        # Question label
        self.question = QLabel("Press START GAME to begin")
        self.question.setWordWrap(True)
        self.question.setAlignment(Qt.AlignCenter)
        self.question.setStyleSheet(
            "font-size: 24px; font-weight: 900; color: white; "
            "padding: 30px; background: rgba(20, 30, 45, 0.8); "
            "border: 3px solid #39FF14; border-radius: 16px; "
            "min-height: 120px;"
        )
        center_layout.addWidget(self.question)

        # Options view
        self.options = OptionsView()
        center_layout.addWidget(self.options)

        # Add center to grid
        game_grid.addWidget(center_widget, 0, 1, 3, 1)

        # Set grid stretching
        game_grid.setColumnStretch(0, 1)
        game_grid.setColumnStretch(1, 3)
        game_grid.setColumnStretch(2, 1)

        root.addLayout(game_grid, stretch=1)

        # =====================================================================
        # CONTROL PANEL
        # =====================================================================
        control_panel = QFrame()
        control_panel.setStyleSheet(
            "QFrame { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(20, 30, 45, 0.95), stop:1 rgba(15, 25, 40, 0.95)); "
            "border: 2px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 12px; "
            "padding: 15px; "
            "}"
        )

        control_layout = QHBoxLayout(control_panel)
        control_layout.setSpacing(10)

        button_style = (
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.15); "
            "border: 2px solid #39FF14; "
            "border-radius: 8px; "
            "padding: 12px 20px; "
            "font-size: 14px; "
            "font-weight: 900; "
            "color: white; "
            "min-width: 100px; "
            "}"
            "QPushButton:hover { background: rgba(57, 255, 20, 0.3); }"
            "QPushButton:pressed { background: rgba(57, 255, 20, 0.5); }"
            "QPushButton:disabled { "
            "background: rgba(100, 100, 100, 0.2); "
            "border-color: #666; "
            "color: #666; "
            "}"
        )

        # Phase label
        self.phase = QLabel("PHASE: IDLE")
        self.phase.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: white; "
            "background: rgba(57, 255, 20, 0.2); "
            "padding: 12px 20px; border: 2px solid #39FF14; border-radius: 8px;"
        )

        # Start game button
        self.btn_start_game = QPushButton("🎮 START GAME")
        self.btn_start_game.setStyleSheet(
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.3); "
            "border: 3px solid #39FF14; "
            "border-radius: 8px; "
            "padding: 15px 30px; "
            "font-size: 16px; "
            "font-weight: 900; "
            "color: white; "
            "min-width: 150px; "
            "}"
            "QPushButton:hover { background: rgba(57, 255, 20, 0.5); }"
            "QPushButton:pressed { background: rgba(57, 255, 20, 0.7); }"
            "QPushButton:disabled { "
            "background: rgba(100, 100, 100, 0.2); "
            "border-color: #666; "
            "color: #666; "
            "}"
        )
        self.btn_start_game.clicked.connect(self._start_game)

        # Unlock button
        self.btn_unlock = QPushButton("🔓 UNLOCK BUZZERS")
        self.btn_unlock.setStyleSheet(
            "QPushButton { "
            "background: rgba(255, 193, 7, 0.2); "
            "border: 3px solid #ffc107; "
            "border-radius: 8px; "
            "padding: 12px 20px; "
            "font-size: 14px; "
            "font-weight: 900; "
            "color: white; "
            "min-width: 150px; "
            "}"
            "QPushButton:hover { background: rgba(255, 193, 7, 0.4); }"
            "QPushButton:pressed { background: rgba(255, 193, 7, 0.6); }"
            "QPushButton:disabled { "
            "background: rgba(100, 100, 100, 0.2); "
            "border-color: #666; "
            "color: #666; "
            "}"
        )
        self.btn_unlock.clicked.connect(self._unlock_buzzers)
        self.btn_unlock.setEnabled(False)
        self.btn_unlock.hide()

        # Next question button
        self.btn_next = QPushButton("▶️ NEXT QUESTION")
        self.btn_next.setStyleSheet(button_style)
        self.btn_next.clicked.connect(self._load_next_question)
        self.btn_next.setEnabled(False)
        self.btn_next.hide()

        # Status label
        self.status_label = QLabel("Waiting for players...")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
            "background: rgba(57, 255, 20, 0.15); "
            "padding: 12px 20px; border: 2px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 8px;"
        )
        self.status_label.hide()

        # Reset game button
        self.btn_reset = QPushButton("🔄 RESET GAME")
        self.btn_reset.setStyleSheet(button_style)
        self.btn_reset.clicked.connect(self._reset_game)

        # Help button
        self.help_btn = QPushButton("ℹ️")
        self.help_btn.setFixedSize(45, 45)
        self.help_btn.setStyleSheet(
            "QPushButton { "
            "background: rgba(52, 152, 219, 0.3); "
            "border: 2px solid #3498db; "
            "border-radius: 22px; "
            "font-size: 20px; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(52, 152, 219, 0.5); }"
        )
        self.help_btn.clicked.connect(self._show_help)

        # Bonus points button
        self.btn_bonus = QPushButton("⭐ BONUS POINT")
        self.btn_bonus.setStyleSheet(
            "QPushButton { "
            "background: rgba(255, 215, 0, 0.2); "
            "border: 3px solid #ffd700; "
            "border-radius: 8px; "
            "padding: 12px 20px; "
            "font-size: 14px; "
            "font-weight: 900; "
            "color: #ffd700; "
            "min-width: 120px; "
            "}"
            "QPushButton:hover { background: rgba(255, 215, 0, 0.4); }"
            "QPushButton:pressed { background: rgba(255, 215, 0, 0.6); }"
            "QPushButton:disabled { "
            "background: rgba(100, 100, 100, 0.2); "
            "border-color: #666; "
            "color: #666; "
            "}"
        )
        self.btn_bonus.clicked.connect(self._award_bonus_point)

        # Add widgets to control panel
        control_layout.addWidget(self.phase)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
        control_layout.addWidget(self.btn_start_game)
        control_layout.addWidget(self.btn_unlock)
        control_layout.addWidget(self.btn_next)
        control_layout.addWidget(self.btn_bonus)
        control_layout.addWidget(self.btn_reset)
        control_layout.addWidget(self.help_btn)

        root.addWidget(control_panel)

        # =====================================================================
        # CONNECT ENGINE SIGNALS
        # =====================================================================
        
        self.engine.phase_changed.connect(self._on_phase)
        self.engine.question_changed.connect(self._render_question)
        self.engine.timer_changed.connect(self.timer.set_remaining_ms)
        self.engine.timer_changed.connect(self._sfx_on_timer_changed)
        self.engine.lock_changed.connect(self._on_lock)
        self.engine.scores_changed.connect(self._render_scores)
        self.engine.attempt_changed.connect(self._on_attempt_changed)
        self.engine.attempt_failed.connect(self._on_attempt_failed)

        # ✅ When engine advances automatically (e.g., correct answer / timer end),
        # reset per-question UI state (forgive eliminated players) and reset MQTT question state.
        if hasattr(self.engine, 'question_advanced'):
            self.engine.question_advanced.connect(self._on_engine_question_advanced)

        # MQTT backend callbacks
        if self.mqtt_backend:
            self.mqtt_backend.on_buzz_callback = self._on_mqtt_buzz
            self.mqtt_backend.on_answer_callback = self._on_mqtt_answer
            self.mqtt_backend.on_player_connected_callback = self._on_player_connected
            self.mqtt_backend.on_player_disconnected_callback = self._on_player_disconnected

        # Update connection status periodically
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self._update_connection_status)
        self.connection_timer.start(2000)  # every 2 seconds

        # Initial render
        self._render_scores()

    def _on_engine_question_advanced(self):
        self._prepare_current_question_ui()


    # =========================================================================
    # GAME CONTROL
    # =========================================================================

    def _start_game(self):
        """Start the game - ALWAYS start from a clean state"""
        self.engine.reset_game()
        self.current_round = 1
        self._warned_7 = False
        self._warned_3 = False

        for player_card in self.player_cards.values():
            player_card.set_eliminated(False)
            player_card.highlight_locked(False)

        self.game_started = True

        # Hide start button, show game controls
        self.btn_start_game.hide()
        self.btn_unlock.show()
        self.btn_next.show()
        self.status_label.show()

        # ✅ START FIRST QUESTION (Q1) — DO NOT SKIP
        self.engine.start_question()
        self._prepare_current_question_ui()

        print("🎮 GAME STARTED (Q1)!")


    def _load_next_question(self):
        """
        Admin NEXT button: Advance to next question
        
        Since engine no longer auto-advances, this is the ONLY way to move forward.
        Called after:
        - Correct answer is given (question complete)
        - All attempts exhausted (no one got it right)
        - Manual skip (admin wants to skip)
        """

        if not self.game_started:
            return

        # If engine ended → show winner
        if self.engine.phase == Phase.GAME_END:
            self._show_winner_screen()
            return

        # Round transition check BEFORE advancing (based on answered questions)
        if self.engine.cfg.rounds > 1:
            questions_per_round = self.engine.cfg.questions_per_round
            questions_answered = len(self.engine.answered_questions)

            if questions_answered > 0 and questions_answered % questions_per_round == 0:
                round_just_completed = questions_answered // questions_per_round
                if round_just_completed < self.engine.cfg.rounds:
                    self._show_round_transition(round_just_completed, round_just_completed + 1)
                    return

        # Check if current question was answered or should be marked as skipped
        if self.engine.current_q_idx not in self.engine.answered_questions:
            # Question not answered - mark as answered (skipped)
            self.engine.answered_questions.add(self.engine.current_q_idx)

        # Advance to next question
        self.engine.next_question()



    def _unlock_buzzers(self):
        """Manually unlock buzzers to accept input"""
        if not self.game_started:
            return
        
        if self.buzzers_unlocked:
            return
        
        self.buzzers_unlocked = True
        
        # Update button appearance
        self.btn_unlock.setText("✅ BUZZERS ACTIVE")
        self.btn_unlock.setStyleSheet(
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.3); "
            "border: 3px solid #39FF14; "
            "border-radius: 8px; "
            "padding: 12px 20px; "
            "font-size: 14px; "
            "font-weight: 900; "
            "color: white; "
            "min-width: 150px; "
            "}"
        )
        self.btn_unlock.setEnabled(False)
        
        # Update status
        self.status_label.setText("🔊 Buzzers active - Players can buzz now!")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(57, 255, 20, 1.0); "
            "background: rgba(57, 255, 20, 0.2); "
            "padding: 12px 20px; border: 2px solid #39FF14; "
            "border-radius: 8px;"
        )
        
        # Unlock MQTT buzzers
        if self.mqtt_backend:
            self.mqtt_backend.unlock_buzzers()
        
        # Start engine timer
        self.engine.timer.start(self.engine.cfg.timer_seconds * 1000)
        
        # Play sound
        self.sfx.play_start()

    def _reset_game(self):
        """Reset the game"""
        reply = QMessageBox.question(
            self,
            "Reset Game",
            "Are you sure you want to reset the game? All scores will be lost.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Reset state
        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1
        
        # Reset engine
        self.engine.reset_game()
        
        # Reset MQTT backend - release all locks and unlock buzzers
        if self.mqtt_backend:
            self.mqtt_backend.end_question()
            # Publish reset to unlock all ESP32 buzzers
            self.mqtt_backend._publish_reset()
            print("[RESET] Released all buzzer locks via MQTT")
        
        # Reset UI
        self.btn_start_game.setEnabled(True)
        self.btn_start_game.show()
        self.btn_unlock.hide()
        self.btn_next.hide()
        self.status_label.hide()
        
        self.question.setText("Press START GAME to begin")
        self.options.clear()
        self.media.clear()
        
        # Reset player cards
        for player_card in self.player_cards.values():
            player_card.set_eliminated(False)
            player_card.highlight_locked(False)
            player_card.set_score(0)
        
        # Reset cascading widget
        self.cascading_widget.reset()
        
        # Reset timer
        self.timer.set_remaining_ms(0)

    # =========================================================================
    # ENGINE EVENT HANDLERS
    # =========================================================================

    def _on_phase(self, phase: str):
        """Handle phase changes"""
        self.phase.setText(f"PHASE: {phase}")
        
        # Enable/disable controls based on phase
        if phase == Phase.GAME_END.value:
            self.btn_unlock.setEnabled(False)
            self.btn_next.setEnabled(False)
            
        elif phase == Phase.IDLE.value:
            # Check if this is due to timer expiration
            if self.game_started and self.engine.current_q_idx in self.engine.answered_questions:
                # Question timed out or all attempts exhausted
                remaining = self.engine.get_players_remaining()
                if len(remaining) == 4:
                    # No one buzzed - question timer expired
                    self.status_label.setText("⏰ Time's up! No one buzzed. Click NEXT to continue.")
                else:
                    # Answer timer expired or all attempts exhausted
                    self.status_label.setText("⏰ Time's up! Click NEXT to continue.")
                
                self.status_label.setStyleSheet(
                    "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
                    "background: rgba(255, 193, 7, 0.2); "
                    "padding: 12px 20px; border: 2px solid #ffc107; "
                    "border-radius: 8px;"
                )
                
                # Enable NEXT, disable UNLOCK
                self.btn_next.setEnabled(True)
                self.btn_next.setText("▶️ NEXT QUESTION")
                self.btn_unlock.setEnabled(False)

    def _render_question(self):
        """Render current question"""
        try:
            q = self.engine.current_question()
        except:
            return
        
        progress = self.engine.get_progress()
        current_idx, total = progress
        
        # Update question text with progress and round info
        round_info = ""
        if self.engine.cfg.rounds > 1:
            round_info = f"ROUND {self.current_round}/{self.engine.cfg.rounds} • "
        
        self.question.setText(
            f"{round_info}QUESTION {current_idx}/{total}\n\n{q.text}"
        )
        
        # Update options
        self.options.set_options(q.options)
        
        # Update media
        pack_dir = self.engine.cfg.pack_dir
        self.media.set_media(q.media, pack_dir)
        
        # Update cascading widget
        self.cascading_widget.update_attempt(
            self.engine.get_current_attempt_number(),
            self.engine.get_points_for_current_attempt(),
            self.engine.get_players_remaining()
        )

    def _render_scores(self):
        """Render player scores"""
        for pid, card in self.player_cards.items():
            score = self.engine.scores.scores.get(pid, 0)
            card.set_score(score)

    def _on_lock(self, buzzer_id: Optional[int]):
        """Handle buzzer lock change"""
        # Clear all highlights first
        for card in self.player_cards.values():
            card.highlight_locked(False)
        
        if buzzer_id is not None and buzzer_id in self.player_cards:
            self.player_cards[buzzer_id].highlight_locked(True)
            
            # Update status
            self.status_label.setText(f"🛑 Player {buzzer_id} buzzed! Waiting for answer...")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(93, 219, 255, 1.0); "
                "background: rgba(93, 219, 255, 0.2); "
                "padding: 12px 20px; border: 2px solid #5ddbff; "
                "border-radius: 8px;"
            )

    def _on_attempt_changed(self, attempt_number: int):
        """Handle attempt number change"""
        remaining = self.engine.get_players_remaining()
        self.cascading_widget.update_attempt(
            attempt_number,
            self.engine.get_points_for_current_attempt(),
            remaining
        )
        
        # Update status
        if attempt_number > 1:
            remaining = self.engine.get_players_remaining()
            self.status_label.setText(
                f"⚡ Attempt {attempt_number} - Remaining players: {remaining}"
            )

    def _on_attempt_failed(self, player_id: int, attempt_number: int):
        """Handle failed attempt"""
        # Mark player as eliminated
        if player_id in self.player_cards:
            self.player_cards[player_id].set_eliminated(True)
        
        # Play wrong sound
        self.sfx.play_wrong()

    # =========================================================================
    # MQTT EVENT HANDLERS
    # =========================================================================

    def _on_mqtt_buzz(self, buzz_event):
        """Handle MQTT buzz event"""
        # Only accept buzz if buzzers unlocked and in correct phase
        if not self.buzzers_unlocked:
            print("🚫 Buzz ignored - buzzers not unlocked")
            return
        
        player_id = buzz_event.player_id
        
        # Process buzz in engine
        accepted = self.engine.on_buzz(player_id, buzz_event.timestamp_ms, buzz_event.server_received_ms)
        
        if accepted:
            print(f"✅ Buzz accepted from Player {player_id}")
            self.sfx.play_buzz()
        else:
            print(f"🚫 Buzz rejected from Player {player_id}")

    def _on_mqtt_answer(self, answer_event):
        """Handle MQTT answer event - AUTO JUDGE"""
        if not self.game_started:
            return
        
        player_id = answer_event.player_id
        answer = answer_event.answer
        
        print(f"\n🎯 AUTO JUDGING: Player {player_id} answered {answer}")
        
        # Auto-judge answer
        self._auto_judge_answer(player_id, answer)


    def _prepare_current_question_ui(self):
        """Reset per-question UI + reset MQTT backend question state (forgive eliminated players)."""

        # ✅ PING ALL PLAYERS BEFORE QUESTION
        if self.mqtt_backend and hasattr(self.mqtt_backend, 'send_heartbeat_to_all'):
            print("\n🏓 Pinging all players before question...")
            self.mqtt_backend.send_heartbeat_to_all()
            
            # Give players 2 seconds to respond
            import time
            time.sleep(2)
            
            # Check who responded
            unresponsive = self.mqtt_backend.get_unresponsive_players()
            if unresponsive:
                # Show warning to admin with option to proceed anyway
                player_list = ", ".join([f"Player {p}" for p in unresponsive])
                
                # Use a message box to get admin decision
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.warning(
                    self,
                    "⚠️ Unresponsive Players",
                    f"{player_list} not responding to ping!\n\n"
                    f"These players may not be able to buzz in.\n\n"
                    f"Do you want to:\n"
                    f"• RETRY - Ping again and wait\n"
                    f"• PROCEED - Continue anyway (risky)\n"
                    f"• CANCEL - Fix connection issues first",
                    QMessageBox.Retry | QMessageBox.Ignore | QMessageBox.Cancel,
                    QMessageBox.Retry
                )
                
                if reply == QMessageBox.Retry:
                    # Try pinging again
                    print("🔄 Retrying ping...")
                    self.mqtt_backend.send_heartbeat_to_all()
                    time.sleep(2)
                    
                    # Check again
                    unresponsive_retry = self.mqtt_backend.get_unresponsive_players()
                    if unresponsive_retry:
                        retry_list = ", ".join([f"Player {p}" for p in unresponsive_retry])
                        self.status_label.setText(f"⚠️ Still unresponsive: {retry_list}")
                        self.status_label.setStyleSheet(
                            "font-size: 14px; font-weight: 700; color: rgba(255, 87, 34, 1.0); "
                            "background: rgba(255, 87, 34, 0.2); "
                            "padding: 12px 20px; border: 2px solid #ff5722; "
                            "border-radius: 8px;"
                        )
                        print(f"❌ Retry failed: {retry_list}")
                        return  # Stop here
                    else:
                        print("✅ All players responded on retry!")
                        
                elif reply == QMessageBox.Ignore:
                    # Admin chose to proceed anyway
                    print(f"⚠️ Admin proceeding despite unresponsive: {player_list}")
                    self.status_label.setText(f"⚠️ Proceeding with unresponsive: {player_list}")
                    self.status_label.setStyleSheet(
                        "font-size: 14px; font-weight: 700; color: rgba(255, 152, 0, 1.0); "
                        "background: rgba(255, 152, 0, 0.2); "
                        "padding: 12px 20px; border: 2px solid #ff9800; "
                        "border-radius: 8px;"
                    )
                    # Continue to question setup below
                    
                else:  # Cancel
                    print("🛑 Admin cancelled - fix connections first")
                    self.status_label.setText("🛑 Question cancelled - Fix player connections")
                    self.status_label.setStyleSheet(
                        "font-size: 14px; font-weight: 700; color: rgba(244, 67, 54, 1.0); "
                        "background: rgba(244, 67, 54, 0.2); "
                        "padding: 12px 20px; border: 2px solid #f44336; "
                        "border-radius: 8px;"
                    )
                    return  # Stop here
            else:
                print("✅ All players responded to ping")

        # Reset warnings
        self._warned_7 = False
        self._warned_3 = False

        # Reset buzzer state
        self.buzzers_unlocked = False
        self.btn_unlock.setEnabled(True)
        self.btn_unlock.setText("🔓 UNLOCK BUZZERS")
        self.btn_unlock.setStyleSheet(
            "QPushButton { "
            "background: rgba(255, 193, 7, 0.2); "
            "border: 3px solid #ffc107; "
            "border-radius: 8px; "
            "padding: 12px 20px; "
            "font-size: 14px; "
            "font-weight: 900; "
            "color: white; "
            "min-width: 150px; "
            "}"
            "QPushButton:hover { background: rgba(255, 193, 7, 0.4); }"
            "QPushButton:pressed { background: rgba(255, 193, 7, 0.6); }"
        )

        # Update status
        self.status_label.setText("⏸️ Buzzers locked - Click UNLOCK when ready")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
            "background: rgba(255, 193, 7, 0.2); "
            "padding: 12px 20px; border: 2px solid #ffc107; "
            "border-radius: 8px;"
        )

        # Reset cascading widget + forgive eliminated players (UI)
        self.cascading_widget.reset()
        for card in self.player_cards.values():
            card.set_eliminated(False)
            card.highlight_locked(False)

        # Reset timer display (do NOT start countdown)
        self.timer.set_remaining_ms(self.engine.cfg.timer_seconds * 1000)

        # Reset MQTT backend question state (clears eliminated_players there)
        if self.mqtt_backend:
            q = self.engine.current_question()
            self.mqtt_backend.start_question(question_id=q.id, max_attempts=q.max_attempts)

        # Refresh visuals
        self._render_question()
        self._render_scores()
        self.btn_next.setEnabled(True)


    def _auto_judge_answer(self, player_id: int, answer: str):
        """Automatically judge answer based on question correct_index"""

        answer_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        if answer not in answer_map:
            print(f"⚠️ Invalid answer: {answer}")
            return

        try:
            question = self.engine.current_question()
        except Exception:
            return

        selected_index = answer_map[answer]
        is_correct = (selected_index == question.correct_index)

        print(f"   Selected: {selected_index} ({question.options[selected_index]})")
        print(f"   Correct:  {question.correct_index} ({question.options[question.correct_index]})")
        print(f"   Result:   {'✅ CORRECT' if is_correct else '❌ WRONG'}")

        # Apply to engine (engine no longer auto-advances)
        self.engine.apply_answer(is_correct)

        if is_correct:
            self.sfx.play_correct()
            self.sfx.play_point()

            self.status_label.setText(f"✅ Player {player_id} CORRECT! Click NEXT to continue.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(57, 255, 20, 1.0); "
                "background: rgba(57, 255, 20, 0.2); "
                "padding: 12px 20px; border: 2px solid #39FF14; "
                "border-radius: 8px;"
            )

            # Tell MQTT backend correct (ends question in backend)
            if self.mqtt_backend:
                self.mqtt_backend.mark_answer_correct(player_id)

            # ✅ FIX: Enable NEXT button so admin can advance manually
            # Engine no longer auto-advances, admin controls all progression
            self.btn_next.setEnabled(True)
            self.btn_next.setText("▶️ NEXT QUESTION")
            self.btn_unlock.setEnabled(False)  # Disable unlock since question is complete
            
            return

        # WRONG answer
        self.sfx.play_wrong()
        
        # Mark this option as eliminated on the display
        self.options.mark_option_eliminated(answer)

        # Tell MQTT backend wrong (unlocks next attempt in backend, IF any)
        if self.mqtt_backend:
            self.mqtt_backend.mark_answer_wrong(player_id)

        # Check if there are more attempts available
        remaining_players = self.engine.get_players_remaining()
        question = self.engine.current_question()
        can_continue = (self.engine.current_attempt_number < question.max_attempts and 
                       len(remaining_players) > 0)
        
        if can_continue:
            # Still have attempts left - prepare for next attempt
            self.status_label.setText(f"❌ Player {player_id} WRONG! Unlock for next attempt...")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; "
                "border-radius: 8px;"
            )

            # Re-enable unlock for next attempt
            self.buzzers_unlocked = False
            self.btn_unlock.setEnabled(True)
            self.btn_unlock.setText("🔓 UNLOCK NEXT ATTEMPT")
            self.btn_unlock.setStyleSheet(
                "QPushButton { "
                "background: rgba(255, 193, 7, 0.2); "
                "border: 3px solid #ffc107; "
                "border-radius: 8px; "
                "padding: 12px 20px; "
                "font-size: 14px; "
                "font-weight: 900; "
                "color: white; "
                "min-width: 150px; "
                "}"
                "QPushButton:hover { background: rgba(255, 193, 7, 0.4); }"
                "QPushButton:pressed { background: rgba(255, 193, 7, 0.6); }"
            )
        else:
            # No more attempts - enable NEXT for admin to move on
            self.status_label.setText(f"❌ All attempts exhausted! Click NEXT to continue.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; "
                "border-radius: 8px;"
            )
            
            # Enable NEXT button, disable unlock
            self.btn_next.setEnabled(True)
            self.btn_next.setText("▶️ NEXT QUESTION")
            self.btn_unlock.setEnabled(False)


    def _on_player_connected(self, player_id: int):
        """Handle player connection"""
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(True)

    def _on_player_disconnected(self, player_id: int):
        """Handle player disconnection"""
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(False)

    def _update_connection_status(self):
        """Update player connection status (passive check only)"""
        if not self.mqtt_backend:
            return
        
        # Update passive connection tracking (based on last message received)
        connected_players = self.mqtt_backend.get_connected_players(timeout_seconds=10)
        
        for pid, card in self.player_cards.items():
            card.set_connected(pid in connected_players)

    # =========================================================================
    # TIMER SOUND EFFECTS
    # =========================================================================

    def _sfx_on_timer_changed(self, remaining_ms: int):
        """Play timer warning sounds"""
        remaining_sec = remaining_ms // 1000
        
        # Warning at 7 seconds
        if remaining_sec <= 7 and not self._warned_7 and remaining_sec > 3:
            self._warned_7 = True
            self.sfx.play_timer_warning()
        
        # Critical at 3 seconds
        if remaining_sec <= 3 and not self._warned_3 and remaining_sec > 0:
            self._warned_3 = True
            self.sfx.play_timer_critical()

    # =========================================================================
    # ROUND / GAME END SCREENS
    # =========================================================================

    def _show_round_transition(self, completed_round: int, next_round: int):
        """Show round transition screen"""
        self.round_transition_screen.set_round_info(completed_round, next_round)
        self.round_transition_screen.show()
        self.hide()

    def _continue_to_next_round(self):
        """Continue to next round"""
        self.round_transition_screen.hide()
        self.show()
        self._load_next_question()

    def _show_winner_screen(self):
        """Show winner screen"""
        ranking = self.engine.scores.get_ranking()
        winner_id = ranking[0][0] if ranking else 1
        winner_score = ranking[0][1] if ranking else 0
        
        self.winner_screen.set_winner(winner_id, winner_score, ranking)
        self.winner_screen.show()
        self.hide()

    def _play_again(self):
        """Play again from winner screen"""
        self.winner_screen.hide()
        self.show()
        self._reset_game()

    def _exit_game(self):
        """Exit game from winner screen"""
        self.window().close()

    # =========================================================================
    # BONUS POINTS
    # =========================================================================

    def _award_bonus_point(self):
        """Award a bonus point to a selected player"""
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("⭐ Award Bonus Point")
        dialog.setModal(True)
        dialog.setMinimumWidth(400)
        dialog.setStyleSheet(
            "QDialog { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #0a0e27, stop:1 #1a1f3a); "
            "}"
        )
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QLabel("Select Player to Award Bonus Point")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 18px; font-weight: 900; color: #ffd700; "
            "background: transparent; padding: 10px;"
        )
        layout.addWidget(title)
        
        # Player buttons
        player_colors = {
            1: "#e74c3c",  # Red
            2: "#3498db",  # Blue
            3: "#2ecc71",  # Green
            4: "#f39c12",  # Orange
        }
        
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(12)
        
        for player_id in range(1, 5):
            color = player_colors[player_id]
            current_score = self.engine.scores.scores.get(player_id, 0)
            
            btn = QPushButton(f"Player {player_id} - Current Score: {current_score} pts")
            btn.setMinimumHeight(60)
            btn.setStyleSheet(
                f"QPushButton {{ "
                f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 rgba(20, 30, 45, 0.9), stop:1 {color}40); "
                f"border: 3px solid {color}; "
                f"border-radius: 10px; "
                f"padding: 15px; "
                f"font-size: 16px; "
                f"font-weight: 900; "
                f"color: white; "
                f"}}"
                f"QPushButton:hover {{ "
                f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {color}40, stop:1 {color}60); "
                f"border: 4px solid {color}; "
                f"}}"
                f"QPushButton:pressed {{ "
                f"background: {color}80; "
                f"}}"
            )
            btn.clicked.connect(lambda checked, pid=player_id: self._apply_bonus_point(pid, dialog))
            buttons_layout.addWidget(btn)
        
        layout.addLayout(buttons_layout)
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { "
            "background: rgba(100, 100, 100, 0.3); "
            "border: 2px solid #666; "
            "border-radius: 8px; "
            "padding: 12px; "
            "font-size: 14px; "
            "font-weight: 700; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(100, 100, 100, 0.5); }"
        )
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn)
        
        dialog.exec()
    
    def _apply_bonus_point(self, player_id: int, dialog: QDialog):
        """Apply bonus point to player"""
        # Award the point
        reason = "Bonus point (admin awarded)"
        self.engine.scores.add(player_id, 1, reason)
        self.engine.scores_changed.emit()
        
        # Play sound
        self.sfx.play_point()
        
        # Show confirmation in status
        self.status_label.setText(f"⭐ Bonus point awarded to Player {player_id}!")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(255, 215, 0, 1.0); "
            "background: rgba(255, 215, 0, 0.2); "
            "padding: 12px 20px; border: 2px solid #ffd700; "
            "border-radius: 8px;"
        )
        self.status_label.show()
        
        # Flash the player card
        if player_id in self.player_cards:
            card = self.player_cards[player_id]
            # Temporarily highlight
            original_style = card.label.styleSheet()
            card.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                "background: rgba(255, 215, 0, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
            # Reset after 1 second
            QTimer.singleShot(1000, lambda: card.set_score(self.engine.scores.scores.get(player_id, 0)))
        
        # Close dialog
        dialog.accept()
        
        print(f"[BONUS] ⭐ Admin awarded bonus point to Player {player_id}")

    # =========================================================================
    # HELP
    # =========================================================================

    def _show_help(self):
        """Show help dialog"""
        help_text = """
        <h2>Football Quiz Game Help</h2>
        
        <p><b>How to Play:</b></p>
        <ol>
        <li>Click <b>START GAME</b> to begin</li>
        <li>For each question, click <b>UNLOCK BUZZERS</b> when ready</li>
        <li>Players press their BUZZ button to lock in</li>
        <li>Locked player presses A/B/C/D on their ESP32 to answer</li>
        <li>System auto-judges and awards points!</li>
        </ol>
        
        <p><b>Cascading Attempts:</b></p>
        <ul>
        <li>Wrong answer = player eliminated for this question</li>
        <li>Next player can attempt (points decrease)</li>
        <li>Eliminations reset every new question</li>
        <li>Same player CANNOT try again</li>
        </ul>
        
        <p><i>Admin Dashboard: Click ℹ️ to create/edit packs</i></p>
        """
        
        QMessageBox.information(self, "Help", help_text)