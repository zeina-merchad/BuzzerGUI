# app/ui/screens/host_screen.py
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QFrame, QGridLayout, QDialog
)

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

# Remote control key bindings (Rii i7 via USB dongle)
try:
    from app.ui.remote_config import REMOTE_KEYS, REQUIRE_MODIFIER, MODIFIER_KEY
except ImportError:
    # Fallback defaults if remote_config.py is not yet present
    REMOTE_KEYS = {
        "start_game":     Qt.Key.Key_MediaPlay,
        "unlock_buzzers": Qt.Key.Key_Return,
        "next_question":  Qt.Key.Key_MediaNext,
        "reset_game":     Qt.Key.Key_MediaStop,
        "bonus_point":    Qt.Key.Key_HomePage,
    }
    REQUIRE_MODIFIER = False
    MODIFIER_KEY = Qt.KeyboardModifier.NoModifier


class RemoteKeyHandler:
    """
    Mixin that adds Rii i7 remote control support to HostScreen.

    Reads key bindings from remote_config.py (or the fallback dict above).
    Call _handle_remote_key(event) from keyPressEvent.

    Button -> method mapping:
      start_game      -> _start_game()
      unlock_buzzers  -> _unlock_buzzers()
      next_question   -> _load_next_question()
      reset_game      -> (double-press guarded to prevent accidents)
      bonus_point     -> _award_bonus_point()
    """

    def _handle_remote_key(self, event) -> bool:
        """
        Handle a key event from the remote.
        Returns True if the key was consumed, False otherwise.
        """
        if REQUIRE_MODIFIER and not (event.modifiers() & MODIFIER_KEY):
            return False

        key = event.key()

        action = None
        for action_name, bound_key in REMOTE_KEYS.items():
            if key == bound_key:
                action = action_name
                break

        if action is None:
            return False

        print(f"[REMOTE] key={key:#010x} -> action='{action}'")

        if action == "start_game":
            if self.btn_start_game.isVisible() and self.btn_start_game.isEnabled():
                self._start_game()

        elif action == "unlock_buzzers":
            if self.btn_unlock.isVisible() and self.btn_unlock.isEnabled():
                self._unlock_buzzers()

        elif action == "next_question":
            if self.btn_next.isVisible() and self.btn_next.isEnabled():
                self._load_next_question()

        elif action == "reset_game":
            # Double-press within 2s required to prevent accidental resets
            if not hasattr(self, "_remote_reset_armed"):
                self._remote_reset_armed = False
            if not self._remote_reset_armed:
                self._remote_reset_armed = True
                self.status_label.setText("Press RESET again within 2s to confirm")
                self.status_label.setStyleSheet(
                    "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
                    "background: rgba(255, 193, 7, 0.2); "
                    "padding: 12px 20px; border: 2px solid #ffc107; "
                    "border-radius: 8px;"
                )
                QTimer.singleShot(2000, self._disarm_remote_reset)
            else:
                self._remote_reset_armed = False
                self._reset_game()

        elif action == "bonus_point":
            if self.game_started:
                self._award_bonus_point()

        return True

    def _disarm_remote_reset(self):
        """Cancel the double-press reset guard after timeout."""
        self._remote_reset_armed = False


class FlashOverlay(QLabel):
    """Full-screen overlay label for quick feedback flashes (CORRECT / WRONG)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWordWrap(True)
        self.hide()

    def resize_to_parent(self):
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())

    def flash_green(self, text: str = "✅ CORRECT!", ms: int = 650):
        self.setText(text)
        self.resize_to_parent()
        self.setStyleSheet(
            "QLabel {"
            "background: rgba(57, 255, 20, 0.22);"
            "border: 5px solid #39FF14;"
            "border-radius: 20px;"
            "color: #39FF14;"
            "font-size: 64px;"
            "font-weight: 900;"
            "letter-spacing: 2px;"
            "}"
        )
        self.show()
        self.raise_()
        QTimer.singleShot(ms, self.hide)


class CornerPlayerCard(QFrame):
    """Player card with hardware connection indicator"""

    def __init__(self, player_id: int):
        super().__init__()
        self.player_id = player_id
        self.is_buzzed = False
        self.is_hardware_connected = False
        self.is_eliminated = False
        self._score: int = 0

        self.team_colors = {
            1: "#e74c3c",  # Red
            2: "#3498db",  # Blue
            3: "#2ecc71",  # Green
            4: "#f39c12",  # Orange
        }
        self.color = self.team_colors.get(player_id, "#888888")

        self.setFixedSize(150, 180)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(100, 100)
        self._set_disconnected_icon()

        self.label = QLabel(f"P{player_id}: WAITING")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: white; "
            "background: rgba(100, 100, 100, 0.7); "
            "padding: 8px 12px; border-radius: 8px;"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon, alignment=Qt.AlignCenter)
        lay.addWidget(self.label)

    def _set_disconnected_icon(self):
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
        self.icon.setText(str(self._score))

    def _set_connected_icon(self):
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
        self.icon.setText(str(self._score))

    def _set_buzzed_icon(self):
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
        self.icon.setText("✋")

    def _set_eliminated_icon(self):
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
        self.icon.setText(str(self._score))

    def set_connected(self, is_connected: bool):
        """Update connection status"""
        self.is_hardware_connected = is_connected
        if is_connected:
            if not self.is_buzzed and not self.is_eliminated:
                self._set_connected_icon()
            self.label.setText(f"P{self.player_id}: READY")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                f"background: {self.color}; "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            if not self.is_buzzed and not self.is_eliminated:
                self._set_disconnected_icon()
            self.label.setText(f"P{self.player_id}: WAITING")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                "background: rgba(100, 100, 100, 0.7); "
                "padding: 8px 12px; border-radius: 8px;"
            )

    def set_eliminated(self, is_eliminated: bool):
        """Set elimination status"""
        self.is_eliminated = is_eliminated
        if is_eliminated:
            self._set_eliminated_icon()
            self.label.setText(f"P{self.player_id}: ELIMINATED")
            self.label.setStyleSheet(
                "font-size: 13px; font-weight: 900; color: white; "
                "background: rgba(231, 76, 60, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            if self.is_hardware_connected:
                self._set_connected_icon()
                self.label.setText(f"P{self.player_id}: {self._score}pts")
                self.label.setStyleSheet(
                    "font-size: 14px; font-weight: 900; color: white; "
                    f"background: {self.color}; "
                    "padding: 8px 12px; border-radius: 8px;"
                )
            else:
                self._set_disconnected_icon()
                self.label.setText(f"P{self.player_id}: WAITING")
                self.label.setStyleSheet(
                    "font-size: 14px; font-weight: 900; color: white; "
                    "background: rgba(100, 100, 100, 0.7); "
                    "padding: 8px 12px; border-radius: 8px;"
                )

    def set_score(self, value: int):
        """Update score display — always reads from self._score."""
        self._score = int(value)

        if self.is_eliminated:
            self._set_eliminated_icon()
            self.label.setText(f"P{self.player_id}: ELIMINATED ({self._score}pts)")
            self.label.setStyleSheet(
                "font-size: 13px; font-weight: 900; color: white; "
                "background: rgba(231, 76, 60, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        elif self.is_buzzed:
            self._set_buzzed_icon()
            self.label.setText(f"P{self.player_id}: BUZZED! ({self._score}pts)")
            self.label.setStyleSheet(
                "font-size: 13px; font-weight: 900; color: white; "
                "background: rgba(93, 219, 255, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        elif self.is_hardware_connected:
            self._set_connected_icon()
            self.label.setText(f"P{self.player_id}: {self._score}pts")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                f"background: {self.color}; "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            self._set_disconnected_icon()
            self.label.setText(f"P{self.player_id}: WAITING ({self._score}pts)")
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                "background: rgba(100, 100, 100, 0.7); "
                "padding: 8px 12px; border-radius: 8px;"
            )

    def highlight_locked(self, locked: bool):
        """Highlight when player is locked in"""
        if self.is_eliminated:
            return

        self.is_buzzed = locked

        if locked:
            self._set_buzzed_icon()
        elif self.is_hardware_connected:
            self._set_connected_icon()
        else:
            self._set_disconnected_icon()

        self.set_score(self._score)


class HostScreen(RemoteKeyHandler, QWidget):
    """Main game screen with auto-judging from ESP32 answer buttons"""

    def __init__(self, engine: GameEngine, mqtt_backend: MQTTBuzzerBackend):
        super().__init__()
        self.engine = engine
        self.mqtt_backend = mqtt_backend

        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1

        self.winner_screen = WinnerScreen()
        self.winner_screen.hide()
        self.winner_screen.btn_play_again.clicked.connect(self._play_again)
        self.winner_screen.btn_exit.clicked.connect(self._exit_game)

        self.round_transition_screen = RoundTransitionScreen()
        self.round_transition_screen.hide()
        self.round_transition_screen.btn_continue.clicked.connect(self._continue_to_next_round)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QWidget { background: #0d1b2a; }")

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

        self.player_cards = {}

        # Left column (Player 1, cascading widget, Player 3)
        left_column = QWidget()
        left_column.setStyleSheet("QWidget { background: transparent; }")
        left_layout = QVBoxLayout(left_column)
        left_layout.setSpacing(20)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.player_cards[1] = CornerPlayerCard(1)
        left_layout.addWidget(self.player_cards[1], alignment=Qt.AlignTop | Qt.AlignCenter)

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

        # Center content
        center_widget = QWidget()
        center_widget.setStyleSheet("QWidget { background: transparent; }")
        center_widget.setMaximumWidth(1000)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(15)
        center_layout.setContentsMargins(60, 0, 60, 0)

        self.timer = TimerWidget()
        center_layout.addWidget(self.timer, alignment=Qt.AlignCenter)

        self.media = MediaView()
        center_layout.addWidget(self.media, stretch=1)

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

        self.options = OptionsView()
        center_layout.addWidget(self.options)

        game_grid.addWidget(center_widget, 0, 1, 3, 1)

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

        self.phase = QLabel("PHASE: IDLE")
        self.phase.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: white; "
            "background: rgba(57, 255, 20, 0.2); "
            "padding: 12px 20px; border: 2px solid #39FF14; border-radius: 8px;"
        )

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

        self.btn_next = QPushButton("▶️ NEXT QUESTION")
        self.btn_next.setStyleSheet(button_style)
        self.btn_next.clicked.connect(self._load_next_question)
        self.btn_next.setEnabled(False)
        self.btn_next.hide()

        self.status_label = QLabel("Waiting for players...")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
            "background: rgba(57, 255, 20, 0.15); "
            "padding: 12px 20px; border: 2px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 8px;"
        )
        self.status_label.hide()

        self.btn_reset = QPushButton("🔄 RESET GAME")
        self.btn_reset.setStyleSheet(button_style)
        self.btn_reset.clicked.connect(self._reset_game)

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

        # ✅ Green "Correct!" flash overlay (on top of everything)
        self.correct_flash = FlashOverlay(self)
        self.correct_flash.hide()

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

        if hasattr(self.engine, 'question_advanced'):
            self.engine.question_advanced.connect(self._on_engine_question_advanced)

        # MQTT backend callbacks — HostScreen owns these exclusively.
        if self.mqtt_backend:
            self.mqtt_backend.on_buzz_callback = self._on_mqtt_buzz
            self.mqtt_backend.on_answer_callback = self._on_mqtt_answer
            self.mqtt_backend.on_player_connected_callback = self._on_player_connected
            self.mqtt_backend.on_player_disconnected_callback = self._on_player_disconnected

        # Passive connection poll (no blocking I/O)
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self._update_connection_status)
        self.connection_timer.start(2000)

        self._render_scores()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "correct_flash"):
            self.correct_flash.resize_to_parent()

    def keyPressEvent(self, event):
        """Route remote control key presses; fall back to Qt default."""
        if not self._handle_remote_key(event):
            super().keyPressEvent(event)

    def _on_engine_question_advanced(self):
        self._prepare_current_question_ui()

    # =========================================================================
    # GAME CONTROL
    # =========================================================================

    def _start_game(self):
        """Start the game — always from a clean state"""
        self.engine.reset_game()
        self.current_round = 1
        self._warned_7 = False
        self._warned_3 = False

        for player_card in self.player_cards.values():
            player_card.set_eliminated(False)
            player_card.highlight_locked(False)

        self.game_started = True

        self.btn_start_game.hide()
        self.btn_unlock.show()
        self.btn_next.show()
        self.status_label.show()

        self.engine.start_question()
        self._prepare_current_question_ui()

        print("🎮 GAME STARTED (Q1)!")

    def _load_next_question(self):
        """Admin NEXT button: advance to next question"""
        if not self.game_started:
            return

        if self.engine.phase == Phase.GAME_END:
            self._show_winner_screen()
            return

        # Round transition check BEFORE advancing
        if self.engine.cfg.rounds > 1:
            questions_per_round = self.engine.cfg.questions_per_round
            questions_answered = len(self.engine.answered_questions)

            if questions_answered > 0 and questions_answered % questions_per_round == 0:
                round_just_completed = questions_answered // questions_per_round
                if round_just_completed < self.engine.cfg.rounds:
                    self._show_round_transition(round_just_completed, round_just_completed + 1)
                    return

        if self.engine.current_q_idx not in self.engine.answered_questions:
            self.engine.answered_questions.add(self.engine.current_q_idx)

        self.engine.next_question()

    def _unlock_buzzers(self):
        """Manually unlock buzzers to accept input"""
        if not self.game_started or self.buzzers_unlocked:
            return

        self.buzzers_unlocked = True

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

        self.status_label.setText("🔊 Buzzers active - Players can buzz now!")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(57, 255, 20, 1.0); "
            "background: rgba(57, 255, 20, 0.2); "
            "padding: 12px 20px; border: 2px solid #39FF14; "
            "border-radius: 8px;"
        )

        if self.mqtt_backend:
            self.mqtt_backend.unlock_buzzers()

        self.engine.notify_buzzers_unlocked()

        # If we're in cascading attempts, resume remaining question time instead of restarting full time
        remaining_ms = self.engine.get_question_remaining_ms() if hasattr(self.engine, 'get_question_remaining_ms') else (self.engine.cfg.timer_seconds * 1000)
        if self.engine.current_attempt_number > 0 and remaining_ms > 0:
            self.engine.timer.start(remaining_ms)
        else:
            self.engine.timer.start(self.engine.cfg.timer_seconds * 1000)
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

        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1

        self.engine.reset_game()

        if self.mqtt_backend:
            self.mqtt_backend.end_question()
            if hasattr(self.mqtt_backend, "reset_all"):
                self.mqtt_backend.reset_all()
            else:
                try:
                    self.mqtt_backend._publish_reset()  # fallback
                except Exception:
                    pass
            print("[RESET] Released all buzzer locks via MQTT")

        self.btn_start_game.setEnabled(True)
        self.btn_start_game.show()
        self.btn_unlock.hide()
        self.btn_next.hide()
        self.status_label.hide()

        self.question.setText("Press START GAME to begin")
        self.options.clear()
        self.media.clear()

        for player_card in self.player_cards.values():
            player_card.set_eliminated(False)
            player_card.highlight_locked(False)
            player_card.set_score(0)

        self.cascading_widget.reset()
        self.timer.set_remaining_ms(0)

    # =========================================================================
    # ENGINE EVENT HANDLERS
    # =========================================================================

    def _on_phase(self, phase: str):
        """Handle phase changes"""
        self.phase.setText(f"PHASE: {phase}")

        if phase == Phase.GAME_END.value:
            self.btn_unlock.setEnabled(False)
            self.btn_next.setEnabled(False)

        elif phase == Phase.IDLE.value:
            if self.game_started and self.engine.current_q_idx in self.engine.answered_questions:
                remaining = self.engine.get_players_remaining()
                if len(remaining) == 4:
                    self.status_label.setText("⏰ Time's up! No one buzzed. Click NEXT to continue.")
                else:
                    self.status_label.setText("⏰ Time's up! Click NEXT to continue.")

                self.status_label.setStyleSheet(
                    "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
                    "background: rgba(255, 193, 7, 0.2); "
                    "padding: 12px 20px; border: 2px solid #ffc107; "
                    "border-radius: 8px;"
                )

                self.btn_next.setEnabled(True)
                self.btn_next.setText("▶️ NEXT QUESTION")
                self.btn_unlock.setEnabled(False)

    def _render_question(self):
        """Render current question"""
        try:
            q = self.engine.current_question()
        except IndexError:
            return

        progress = self.engine.get_progress()
        current_idx, total = progress

        round_info = ""
        if self.engine.cfg.rounds > 1:
            round_info = f"ROUND {self.current_round}/{self.engine.cfg.rounds} • "

        self.question.setText(f"{round_info}QUESTION {current_idx}/{total}\n\n{q.text}")

        self.options.set_options(q.options)

        pack_dir = self.engine.cfg.pack_dir
        self.media.set_media(q.media, pack_dir)

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
        for card in self.player_cards.values():
            card.highlight_locked(False)

        if buzzer_id is not None and buzzer_id in self.player_cards:
            # UI lock highlight
            self.player_cards[buzzer_id].highlight_locked(True)

            # Local UI state: buzzers are no longer free once someone buzzes
            self.buzzers_unlocked = False
            self.btn_unlock.setEnabled(False)

            self.status_label.setText(f"🛑 Player {buzzer_id} buzzed! Waiting for answer...")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(93, 219, 255, 1.0); "
                "background: rgba(93, 219, 255, 0.2); "
                "padding: 12px 20px; border: 2px solid #5ddbff; "
                "border-radius: 8px;"
            )

            # ✅ Hardware lock broadcast (so other ESP buzzers can't answer/buzz)
            if self.mqtt_backend and hasattr(self.mqtt_backend, 'lock_player'):
                self.mqtt_backend.lock_player(buzzer_id)

        else:
            # Unlocked (engine cleared lock) — host may choose to unlock again for next attempt
            for card in self.player_cards.values():
                card.highlight_locked(False)


    def _on_attempt_changed(self, attempt_number: int):
        """Handle attempt number change"""
        remaining = self.engine.get_players_remaining()
        self.cascading_widget.update_attempt(
            attempt_number,
            self.engine.get_points_for_current_attempt(),
            remaining
        )

        if attempt_number > 1:
            self.status_label.setText(f"⚡ Attempt {attempt_number} - Remaining players: {remaining}")

    def _on_attempt_failed(self, player_id: int, attempt_number: int):
        """Handle failed attempt (wrong answer OR timeout)"""
        if player_id in self.player_cards:
            self.player_cards[player_id].set_eliminated(True)

        # Keep MQTT backend elimination in sync (important for real ESP buzzers)
        if self.mqtt_backend:
            self.mqtt_backend.mark_answer_wrong(player_id)

        self.sfx.play_wrong()

        # Update UI to guide the host to unlock next attempt (if any)
        try:
            remaining_players = self.engine.get_players_remaining()
            question = self.engine.current_question()
            can_continue = (self.engine.current_attempt_number < question.max_attempts and len(remaining_players) > 0)
        except Exception:
            can_continue = False

        if can_continue:
            self.status_label.setText(f"⏰ Player {player_id} TIMEOUT / WRONG! Unlock for next attempt.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; "
                "border-radius: 8px;"
            )

            self.buzzers_unlocked = False
            self.btn_unlock.setEnabled(True)
            self.btn_unlock.setText("🔓 UNLOCK NEXT ATTEMPT")
        else:
            self.status_label.setText("⏰ No attempts left! Click NEXT to continue.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; "
                "border-radius: 8px;"
            )
            self.btn_next.setEnabled(True)
            self.btn_next.setText("▶️ NEXT QUESTION")
            self.btn_unlock.setEnabled(False)

    # =========================================================================
    # MQTT EVENT HANDLERS
    # =========================================================================

    def _on_mqtt_buzz(self, buzz_event):
        """Handle MQTT buzz event"""
        if not self.buzzers_unlocked:
            print("🚫 Buzz ignored - buzzers not unlocked")
            return

        player_id = buzz_event.player_id
        accepted = self.engine.on_buzz(player_id, buzz_event.timestamp_ms, buzz_event.server_received_ms)

        if accepted:
            print(f"✅ Buzz accepted from Player {player_id}")
            self.sfx.play_buzz()
        else:
            print(f"🚫 Buzz rejected from Player {player_id}")

    def _on_mqtt_answer(self, answer_event):
        """Handle MQTT answer event — AUTO JUDGE"""
        if not self.game_started:
            return

        player_id = answer_event.player_id
        answer = answer_event.answer

        print(f"\n🎯 AUTO JUDGING: Player {player_id} answered {answer}")
        self._auto_judge_answer(player_id, answer)

    def _on_player_connected(self, player_id: int):
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(True)

    def _on_player_disconnected(self, player_id: int):
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(False)

    def _update_connection_status(self):
        """Update player connection status (passive check only)"""
        if not self.mqtt_backend:
            return

        connected_players = self.mqtt_backend.get_connected_players(timeout_seconds=10)
        for pid, card in self.player_cards.items():
            card.set_connected(pid in connected_players)

    # =========================================================================
    # QUESTION SETUP (called after each next_question / start_game)
    # =========================================================================

    def _prepare_current_question_ui(self):
        """
        Reset per-question UI + reset MQTT backend question state.
        Also pings connected buzzers (heartbeat) BEFORE each question (non-blocking).
        """
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

        self.status_label.setText("⏸️ Buzzers locked - Click UNLOCK when ready")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
            "background: rgba(255, 193, 7, 0.2); "
            "padding: 12px 20px; border: 2px solid #ffc107; "
            "border-radius: 8px;"
        )

        # Reset cascading widget and forgive eliminated players
        self.cascading_widget.reset()
        for card in self.player_cards.values():
            card.set_eliminated(False)
            card.highlight_locked(False)

        # Reset timer display (do NOT start countdown yet)
        self.timer.set_remaining_ms(self.engine.cfg.timer_seconds * 1000)

        # Reset MQTT backend question state (clears eliminated_players there)
        if self.mqtt_backend:
            q = self.engine.current_question()
            self.mqtt_backend.start_question(question_id=q.id, max_attempts=q.max_attempts)

            # ✅ HEARTBEAT BEFORE QUESTION — retry loop instead of fixed 800ms wait
            # Pings all connected buzzers, then polls up to MAX_PING_RETRIES times
            # at PING_POLL_INTERVAL_MS each, stopping as soon as all pongs are back
            # (or retries run out). Prevents false "no response" on slow-waking devices.
            self._ping_retry_count = 0
            self._ping_max_retries = 5
            self._ping_poll_ms = 500

            self.status_label.setText("📡 Pinging connected buzzers...")
            self.mqtt_backend.send_heartbeat_to_all(timeout_seconds=10)
            QTimer.singleShot(self._ping_poll_ms, self._poll_heartbeat_results)

        self._render_question()
        self._render_scores()
        self.btn_next.setEnabled(True)

    def _poll_heartbeat_results(self):
        """
        Called repeatedly (up to _ping_max_retries times) after pings are sent.
        Stops early as soon as all known players have responded.
        Falls through to _apply_heartbeat_results once done.
        """
        if not self.mqtt_backend:
            return

        self._ping_retry_count += 1
        all_resolved = self.mqtt_backend.all_pings_resolved(timeout_seconds=10)

        if all_resolved or self._ping_retry_count >= self._ping_max_retries:
            # All pongs in, or we've waited long enough — apply final result
            if not all_resolved:
                print(f"[PING] ⚠ {self._ping_retry_count} polls elapsed, some pongs still pending — applying anyway")
            self._apply_heartbeat_results()
        else:
            # Still waiting on at least one pong — try again shortly
            print(f"[PING] Waiting for pongs... (poll {self._ping_retry_count}/{self._ping_max_retries})")
            self.status_label.setText(f"📡 Waiting for buzzers... ({self._ping_retry_count}/{self._ping_max_retries})")
            QTimer.singleShot(self._ping_poll_ms, self._poll_heartbeat_results)

    def _apply_heartbeat_results(self):
        """Apply final heartbeat results to the UI once polling is complete."""
        if not self.mqtt_backend:
            return

        alive_map = self.mqtt_backend.check_all_players_liveliness()
        alive_players = [pid for pid, alive in alive_map.items() if alive]

        # Update player cards
        for pid, card in self.player_cards.items():
            card.set_connected(pid in alive_players)

        if len(alive_players) == 0:
            self.status_label.setText("🚫 No buzzers responding. Check power/WiFi.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: #ff4c4c; "
                "background: rgba(255, 0, 0, 0.2); "
                "padding: 12px 20px; border: 2px solid #ff4c4c; "
                "border-radius: 8px;"
            )
            self.btn_unlock.setEnabled(False)
        else:
            self.status_label.setText(f"✅ Alive buzzers: {sorted(alive_players)} — Click UNLOCK when ready")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
                "background: rgba(255, 193, 7, 0.2); "
                "padding: 12px 20px; border: 2px solid #ffc107; "
                "border-radius: 8px;"
            )
            self.btn_unlock.setEnabled(True)

    # =========================================================================
    # AUTO JUDGING
    # =========================================================================

    def _auto_judge_answer(self, player_id: int, answer: str):
        answer_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        if answer not in answer_map:
            print(f"⚠️ Invalid answer: {answer}")
            return

        try:
            question = self.engine.current_question()
        except IndexError:
            return

        selected_index = answer_map[answer]
        is_correct = (selected_index == question.correct_index)

        print(f"   Selected: {selected_index} ({question.options[selected_index]})")
        print(f"   Correct:  {question.correct_index} ({question.options[question.correct_index]})")
        print(f"   Result:   {'✅ CORRECT' if is_correct else '❌ WRONG'}")

        self.engine.apply_answer(is_correct)

        if is_correct:
            self.sfx.play_correct()
            self.sfx.play_point()

            # ✅ GREEN FLASH
            self.correct_flash.flash_green("✅ CORRECT!")

            self.status_label.setText(f"✅ Player {player_id} CORRECT! Click NEXT to continue.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(57, 255, 20, 1.0); "
                "background: rgba(57, 255, 20, 0.2); "
                "padding: 12px 20px; border: 2px solid #39FF14; "
                "border-radius: 8px;"
            )

            if self.mqtt_backend:
                self.mqtt_backend.mark_answer_correct(player_id)

            self.btn_next.setEnabled(True)
            self.btn_next.setText("▶️ NEXT QUESTION")
            self.btn_unlock.setEnabled(False)
            return

        # WRONG answer
        self.sfx.play_wrong()
        self.options.mark_option_eliminated(answer)

        if self.mqtt_backend:
            self.mqtt_backend.mark_answer_wrong(player_id)

        remaining_players = self.engine.get_players_remaining()
        question = self.engine.current_question()
        can_continue = (self.engine.current_attempt_number < question.max_attempts and len(remaining_players) > 0)

        if can_continue:
            self.status_label.setText(f"❌ Player {player_id} WRONG! Unlock for next attempt...")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; "
                "border-radius: 8px;"
            )

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
            self.status_label.setText("❌ All attempts exhausted! Click NEXT to continue.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; "
                "border-radius: 8px;"
            )
            self.btn_next.setEnabled(True)
            self.btn_next.setText("▶️ NEXT QUESTION")
            self.btn_unlock.setEnabled(False)

    # =========================================================================
    # ROUND / GAME END SCREENS
    # =========================================================================

    def _show_round_transition(self, completed_round: int, next_round: int):
        self.round_transition_screen.set_round_info(
            completed_round=completed_round,
            next_round=next_round,
            scores=self.engine.scores.scores,
            questions_in_next=self.engine.cfg.questions_per_round,
        )
        self.round_transition_screen.show()
        self.hide()

    def _continue_to_next_round(self):
        self.round_transition_screen.hide()
        self.round_transition_screen.cleanup()
        self.show()
        self._load_next_question()

    def _show_winner_screen(self):
        ranking = self.engine.scores.get_ranking()
        winner_id = ranking[0][0] if ranking else 1
        self.winner_screen.set_results(scores=dict(ranking), winner_id=winner_id)
        self.winner_screen.show()
        self.hide()

    def _play_again(self):
        self.winner_screen.cleanup()
        self.winner_screen.hide()
        self.show()
        self._reset_game()

    def _exit_game(self):
        self.winner_screen.cleanup()
        self.window().close()

    # =========================================================================
    # BONUS POINTS
    # =========================================================================

    def _award_bonus_point(self):
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

        title = QLabel("Select Player to Award Bonus Point")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 18px; font-weight: 900; color: #ffd700; "
            "background: transparent; padding: 10px;"
        )
        layout.addWidget(title)

        player_colors = {
            1: "#e74c3c",
            2: "#3498db",
            3: "#2ecc71",
            4: "#f39c12",
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
                f"QPushButton:pressed {{ background: {color}80; }}"
            )
            btn.clicked.connect(lambda checked, pid=player_id: self._apply_bonus_point(pid, dialog))
            buttons_layout.addWidget(btn)

        layout.addLayout(buttons_layout)

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
        self.engine.scores.add(player_id, 1, "Bonus point (admin awarded)")
        self.engine.scores_changed.emit()
        self.sfx.play_point()

        self.status_label.setText(f"⭐ Bonus point awarded to Player {player_id}!")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(255, 215, 0, 1.0); "
            "background: rgba(255, 215, 0, 0.2); "
            "padding: 12px 20px; border: 2px solid #ffd700; "
            "border-radius: 8px;"
        )
        self.status_label.show()

        if player_id in self.player_cards:
            card = self.player_cards[player_id]
            card.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                "background: rgba(255, 215, 0, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
            QTimer.singleShot(1000, lambda: card.set_score(self.engine.scores.scores.get(player_id, 0)))

        dialog.accept()
        print(f"[BONUS] ⭐ Admin awarded bonus point to Player {player_id}")

    # =========================================================================
    # TIMER SOUND EFFECTS
    # =========================================================================

    def _sfx_on_timer_changed(self, remaining_ms: int):
        remaining_sec = remaining_ms // 1000

        if remaining_sec <= 7 and not self._warned_7 and remaining_sec > 3:
            self._warned_7 = True
            self.sfx.play_timer_warning()

        if remaining_sec <= 3 and not self._warned_3 and remaining_sec > 0:
            self._warned_3 = True
            self.sfx.play_timer_critical()

    # =========================================================================
    # HELP
    # =========================================================================

    def _show_help(self):
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