# app/ui/screens/host_screen.py
from typing import Optional
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QFrame, QGridLayout, QDialog
)
import sys,os
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
    REMOTE_KEYS = {
        "start_game":     Qt.Key.Key_MediaPlay,
        "unlock_buzzers": Qt.Key.Key_Return,
        "next_question":  Qt.Key.Key_MediaNext,
        "prev_question":  Qt.Key.Key_MediaPrevious,
        "reset_game":     Qt.Key.Key_MediaStop,
        "bonus_point":    Qt.Key.Key_HomePage,
    }
    REQUIRE_MODIFIER = False
    MODIFIER_KEY = Qt.KeyboardModifier.NoModifier


class RemoteKeyHandler:
    """
    Mixin that adds Rii i7 remote control support to HostScreen.
    Call _handle_remote_key(event) from keyPressEvent.
    """

    def _handle_remote_key(self, event) -> bool:
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
        
        elif action == "prev_question":                          # ← add this block
            if self.game_started:
                self._load_prev_question()

        elif action == "reset_game":
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
        self._remote_reset_armed = False


class FlashOverlay(QLabel):
    """Full-screen overlay for quick CORRECT/WRONG feedback flashes."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWordWrap(True)
        self.hide()
        # FIX: cancellable timer so overlapping flashes don't collide
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self.hide)
        QTimer.singleShot(0, self.resize_to_parent)

    def resize_to_parent(self):
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())

    def flash_green(self, text: str = "✅ CORRECT!", ms: int = 650):
        # FIX: stop any pending hide-timer before starting a new flash
        self._flash_timer.stop()
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
        self._flash_timer.start(ms)


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
            1: "#e74c3c",
            2: "#3498db",
            3: "#2ecc71",
            4: "#f39c12",
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
        """Update score display."""
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

        # FIX #2: track whether a heartbeat round is in progress so we don't
        # stack multiple concurrent heartbeat/poll chains.
        self._heartbeat_in_progress = False
        self._round_transition_ping_pending = False

        self.winner_screen = WinnerScreen(parent=self)
        self.winner_screen.hide()
        self.winner_screen.btn_play_again.clicked.connect(self._play_again)
        self.winner_screen.btn_exit.clicked.connect(self._exit_game)

        self.round_transition_screen = RoundTransitionScreen(parent=self)
        self.round_transition_screen.hide()
        self.round_transition_screen.btn_continue.clicked.connect(self._continue_to_next_round)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QWidget { background: #0d1b2a; }")

        self.sfx = create_sound_manager()
        self._warned_7 = False
        self._warned_3 = False

        # ── Build UI ─────────────────────────────────────────────────────────
        self._build_ui()

        # ── Connect engine signals ────────────────────────────────────────────
        self._connect_engine_signals()

        # ── Connect MQTT callbacks ────────────────────────────────────────────
        self._connect_mqtt_callbacks()

        # ── Passive connection poll (no blocking I/O) ─────────────────────────
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self._update_connection_status)
        self.connection_timer.start(2000)

        self._render_scores()

    # =========================================================================
    # UI CONSTRUCTION (split out from __init__ for readability — Fix #11)
    # =========================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        game_grid = QGridLayout()
        game_grid.setHorizontalSpacing(20)
        game_grid.setVerticalSpacing(15)

        self.player_cards = {}

        left_column, right_column = self._build_player_columns()
        game_grid.addWidget(left_column, 0, 0, 3, 1)
        game_grid.addWidget(right_column, 0, 2, 3, 1)

        center_widget = self._build_center_area()
        game_grid.addWidget(center_widget, 0, 1, 3, 1)

        game_grid.setColumnStretch(0, 1)
        game_grid.setColumnStretch(1, 3)
        game_grid.setColumnStretch(2, 1)

        root.addLayout(game_grid, stretch=1)
        root.addWidget(self._build_control_panel())

        # Flash overlay (on top of everything)
        self.correct_flash = FlashOverlay(self)
        self.correct_flash.hide()

    def _build_player_columns(self):
        """Build left (P1, cascading, P3) and right (P2, P4) columns."""
        # Left column
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

        # Right column
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

        return left_column, right_column

    def _build_center_area(self):
        """Build the center column: timer, round badge, media, question, options."""
        center_widget = QWidget()
        center_widget.setStyleSheet("QWidget { background: transparent; }")
        center_widget.setMaximumWidth(1000)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(15)
        center_layout.setContentsMargins(60, 0, 60, 0)

        # Timer + round badge in a horizontal row
        timer_row = QWidget()
        timer_row.setStyleSheet("QWidget { background: transparent; }")
        timer_row_layout = QHBoxLayout(timer_row)
        timer_row_layout.setContentsMargins(0, 0, 0, 0)
        timer_row_layout.setSpacing(16)

        self.timer = TimerWidget()
        timer_row_layout.addWidget(self.timer, alignment=Qt.AlignVCenter)

        # FIX: round badge — visible only during multi-round games
        self.round_badge = QLabel("ROUND 1")
        self.round_badge.setAlignment(Qt.AlignCenter)
        self.round_badge.setStyleSheet(
            "font-size: 18px; font-weight: 900; color: #ffd700; "
            "background: rgba(255, 215, 0, 0.15); "
            "border: 2px solid #ffd700; border-radius: 10px; "
            "padding: 8px 18px; letter-spacing: 2px;"
        )
        self.round_badge.hide()  # shown only when cfg.rounds > 1
        timer_row_layout.addWidget(self.round_badge, alignment=Qt.AlignVCenter)
        timer_row_layout.addStretch()

        # ── Company logo placeholder ─────────────────────────────────────────
        # To use a real logo: replace QLabel with a QLabel that loads a QPixmap,
        # e.g.:
        #   from PySide6.QtGui import QPixmap
        #   self.logo_label.setPixmap(
        #       QPixmap("path/to/logo.png").scaled(
        #           120, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation
        #       )
        #   )
        self.logo_label = QLabel("YOUR\nLOGO")
        self.logo_label.setPixmap(
               QPixmap(self.resource_path("app/ui/screens/logo_full.png")).scaled(
                120, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(120, 60)
        self.logo_label.setStyleSheet(
            "QLabel { "
            "color: rgba(255, 255, 255, 0.25); "
            "font-size: 13px; font-weight: 900; letter-spacing: 2px; "
            "background: rgba(255, 255, 255, 0.05); "
            "border: 2px dashed rgba(255, 255, 255, 0.15); "
            "border-radius: 8px; "
            "}"
        )
        timer_row_layout.addWidget(self.logo_label, alignment=Qt.AlignVCenter)

        center_layout.addWidget(timer_row, alignment=Qt.AlignCenter)

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

        return center_widget

    def _build_control_panel(self):
        """Build the bottom control bar."""
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

        # FIX #12: renamed from self.phase to self.phase_label to avoid
        # collision with engine.phase attribute.
        self.phase_label = QLabel("PHASE: IDLE")
        self.phase_label.setStyleSheet(
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

        control_layout.addWidget(self.phase_label)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
        control_layout.addWidget(self.btn_start_game)
        control_layout.addWidget(self.btn_unlock)
        control_layout.addWidget(self.btn_next)
        control_layout.addWidget(self.btn_bonus)
        control_layout.addWidget(self.btn_reset)
        control_layout.addWidget(self.help_btn)

        return control_panel
    


    def resource_path(self, rel: str) -> str:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
            internal = os.path.join(base, "_internal")
            path = os.path.join(internal, rel)
            if os.path.exists(path):
                return path
            path = os.path.join(base, rel)
            if os.path.exists(path):
                return path
            return os.path.join(internal, rel)
        else:
            # Go up 3 levels: screens -> ui -> app -> project root
            root = os.path.dirname(os.path.abspath(__file__))
            root = os.path.dirname(root)  # ui
            root = os.path.dirname(root)  # app
            root = os.path.dirname(root)  # project root
            return os.path.join(root, rel)

    def _connect_engine_signals(self):
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

    def _connect_mqtt_callbacks(self):
        if not self.mqtt_backend:
            return
        self.mqtt_backend.on_buzz_callback = self._on_mqtt_buzz
        self.mqtt_backend.on_answer_callback = self._on_mqtt_answer
        self.mqtt_backend.on_player_connected_callback = self._on_player_connected
        self.mqtt_backend.on_player_disconnected_callback = self._on_player_disconnected

        # FIX #2: use the signal-based heartbeat resolution instead of polling.
        # bridge.heartbeat_resolved fires on the main thread when all pongs are in
        # (or the timeout fires), replacing the QTimer.singleShot chain entirely.
        self.mqtt_backend.bridge.heartbeat_resolved.connect(
            self._apply_heartbeat_results, Qt.QueuedConnection
        )

    # =========================================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "correct_flash"):
            self.correct_flash.resize_to_parent()

    def keyPressEvent(self, event):
        if not self._handle_remote_key(event):
            super().keyPressEvent(event)

    def _on_engine_question_advanced(self):
        self._prepare_current_question_ui()

    # =========================================================================
    # GAME CONTROL
    # =========================================================================

    def _start_game(self):
        # Guard: refuse to start if no questions are loaded
        q_list = getattr(self.engine, "questions", None) or getattr(self.engine, "_questions", None)
        if not q_list:
            QMessageBox.warning(
                self,
                "No Questions Loaded",
                "No questions are loaded.\n\n"
                "Open the Admin Dashboard (ℹ️), load an Excel pack, then try again.",
            )
            return

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

        # Show round badge if this is a multi-round game
        self._update_round_badge()

        self.engine.start_question()
        self._prepare_current_question_ui()

        print("🎮 GAME STARTED (Q1)!")

    def _update_round_badge(self):
        """Update the round badge label and show/hide based on game config."""
        if self.engine.cfg.rounds > 1:
            self.round_badge.setText(f"ROUND {self.current_round} / {self.engine.cfg.rounds}")
            self.round_badge.show()
        else:
            self.round_badge.hide()

    def _load_prev_question(self):
        """Step back to the previous question (remote control / host correction)."""
        if not self.game_started:
            return
        if self.engine.current_q_idx < 1:
            self.status_label.setText("⏮️ Already at the first question.")
            return
        self.engine.prev_question()
        self._prepare_current_question_ui()
        
    def _load_next_question(self):
        if not self.game_started:
            return

        if self.engine.phase == Phase.GAME_END:
            self._show_winner_screen()
            return

        # FIX A: evaluate round boundary using the index AFTER advancing
        # (current_q_idx + 1 is the 1-based count of questions answered so far,
        # which is what we want to compare against questions_per_round).
        if self.engine.cfg.rounds > 1:
            qpr = self.engine.cfg.questions_per_round
            # current_q_idx is 0-based; questions answered so far = current_q_idx + 1
            questions_answered = self.engine.current_q_idx + 1

            if questions_answered % qpr == 0:
                round_just_completed = questions_answered // qpr
                if round_just_completed < self.engine.cfg.rounds:
                    self._show_round_transition(round_just_completed, round_just_completed + 1)
                    return

        self.engine.next_question()

    def _unlock_buzzers(self):
        """Manually unlock buzzers to accept input."""
        if self.engine.phase != Phase.SHOW_QUESTION:
            return

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
        self.engine.start_or_resume_question_timer()
        self.sfx.play_start()

    def _reset_game(self):
        reply = QMessageBox.question(
            self,
            "Reset Game",
            "Are you sure you want to reset the game? All scores will be lost.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # FIX B: dismiss overlay dialogs if open
        if self.round_transition_screen.isVisible():
            self.round_transition_screen.cleanup()
            self.round_transition_screen.hide()
            self.round_transition_screen.setWindowOpacity(1.0)
        if self.winner_screen.isVisible():
            self.winner_screen.cleanup()
            self.winner_screen.hide()
            self.winner_screen.setWindowOpacity(1.0)

        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1
        self._heartbeat_in_progress = False
        self._round_transition_ping_pending = False  # FIX F

        self.engine.reset_game()

        if self.mqtt_backend:
            self.mqtt_backend.end_question()
            # FIX #8: removed the duplicate private _publish_reset() call that
            # was redundant — end_question() already calls it internally.
            print("[RESET] Released all buzzer locks via MQTT")

        self.btn_start_game.setEnabled(True)
        self.btn_start_game.show()
        self.btn_unlock.hide()
        self.btn_next.hide()
        self.status_label.hide()
        self.round_badge.hide()

        self.question.setText("Press START GAME to begin")
        self.options.clear()

        self.media.cleanup()
        self.media.clear()

        for player_card in self.player_cards.values():
            player_card.set_eliminated(False)
            player_card.highlight_locked(False)
            player_card.set_score(0)

        self.cascading_widget.reset()
        self.timer.reset()

    # =========================================================================
    # ENGINE EVENT HANDLERS
    # =========================================================================

    def _on_phase(self, phase: str):
        # FIX #12: use self.phase_label, not self.phase
        self.phase_label.setText(f"PHASE: {phase}")

        if phase == Phase.GAME_END.value:
            self.btn_unlock.setEnabled(False)
            self.btn_next.setEnabled(False)

        elif phase == Phase.SHOW_QUESTION.value:
            if self.game_started:
                # FIX D: disable NEXT while a question is in progress so the
                # host cannot accidentally skip past a cascade back to SHOW_QUESTION.
                # NEXT is re-enabled when we reach IDLE or all attempts exhausted.
                self.btn_next.setEnabled(False)
                self.btn_next.setText("▶️ NEXT QUESTION")

        elif phase == Phase.BUZZED.value:
            if self.game_started:
                # Someone buzzed — disable both buttons while waiting for answer
                self.btn_unlock.setEnabled(False)
                self.btn_next.setEnabled(False)

        elif phase == Phase.IDLE.value:
            if self.game_started:
                # FIX #1: distinguish IDLE reasons correctly.
                # - If players_attempted is empty AND the question is now in
                #   answered_questions, the timer expired with no buzz.
                # - If current_q_idx is in answered_questions AND a player got
                #   it correct, say "Question complete".
                # - Otherwise all attempts were exhausted.
                attempted = set(getattr(self.engine, "players_attempted", set()))
                q_idx = self.engine.current_q_idx
                q_answered = q_idx in self.engine.answered_questions

                if len(attempted) == 0 and q_answered:
                    # Timer expired with no buzz
                    self.status_label.setText("⏰ Time's up! No one buzzed. Click NEXT to continue.")
                elif q_answered and any(
                    r.is_correct for r in getattr(self.engine, 'attempt_records', [])
                ):
                    # Correct answer was given
                    self.status_label.setText("✅ Question complete. Click NEXT to continue.")
                else:
                    # All attempts exhausted with no correct answer
                    self.status_label.setText("❌ All attempts exhausted! Click NEXT to continue.")

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
        try:
            q = self.engine.current_question()
        except IndexError:
            return

        progress = self.engine.get_progress()
        current_idx, total = progress

        # FIX: always show question number; include round only in multi-round games.
        # The round badge in the timer row already shows ROUND N/M, so the
        # question label only needs Q N/TOTAL for clarity.
        self.question.setText(f"QUESTION {current_idx} / {total}\n\n{q.text}")
        self.options.set_options(q.options)

        self.media.cleanup()
        pack_dir = self.engine.cfg.pack_dir
        self.media.set_media(q.media, pack_dir)

        self.cascading_widget.update_attempt(
            self.engine.get_current_attempt_number(),
            self.engine.get_points_for_current_attempt(),
            self.engine.get_players_remaining(),
            active_players=list(self.engine.scores.scores.keys()),
        )

    def _render_scores(self):
        for pid, card in self.player_cards.items():
            score = self.engine.scores.scores.get(pid, 0)
            card.set_score(score)

    def _on_lock(self, buzzer_id: Optional[int]):
        for card in self.player_cards.values():
            card.highlight_locked(False)

        if buzzer_id is not None and buzzer_id in self.player_cards:
            self.player_cards[buzzer_id].highlight_locked(True)

            self.buzzers_unlocked = False
            self.btn_unlock.setEnabled(False)

            self.status_label.setText(f"🛑 Player {buzzer_id} buzzed! Waiting for answer...")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(93, 219, 255, 1.0); "
                "background: rgba(93, 219, 255, 0.2); "
                "padding: 12px 20px; border: 2px solid #5ddbff; "
                "border-radius: 8px;"
            )

            if self.mqtt_backend and hasattr(self.mqtt_backend, 'lock_player'):
                self.mqtt_backend.lock_player(buzzer_id)

        else:
            for card in self.player_cards.values():
                card.highlight_locked(False)

    def _on_attempt_changed(self, attempt_number: int):
        remaining = self.engine.get_players_remaining()
        self.cascading_widget.update_attempt(
            attempt_number,
            self.engine.get_points_for_current_attempt(),
            remaining,
            active_players=list(self.engine.scores.scores.keys()),
        )

        if attempt_number > 1:
            self.status_label.setText(f"⚡ Attempt {attempt_number} - Remaining players: {remaining}")

    def _on_attempt_failed(self, player_id: int, attempt_number: int):
        if player_id in self.player_cards:
            self.player_cards[player_id].set_eliminated(True)

        if self.mqtt_backend:
            self.mqtt_backend.mark_answer_wrong(player_id)

        self.sfx.play_wrong()

        try:
            remaining_players = self.engine.get_players_remaining()
            question = self.engine.current_question()
            can_continue = (
                self.engine.current_attempt_number <= question.max_attempts
                and len(remaining_players) > 0
            )
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
        # FIX #4: gate on engine phase, not UI buzzers_unlocked flag, to avoid
        # the race where buzzers_unlocked is still True between the buzz being
        # accepted and _on_lock setting it to False.
        if self.engine.phase != Phase.SHOW_QUESTION:
            print(f"🚫 Buzz ignored - engine phase is {self.engine.phase.value}")
            return

        player_id = buzz_event.player_id
        accepted = self.engine.on_buzz(player_id, buzz_event.timestamp_ms, buzz_event.server_received_ms)

        if accepted:
            print(f"✅ Buzz accepted from Player {player_id}")
            self.sfx.play_buzz()
        else:
            print(f"🚫 Buzz rejected from Player {player_id}")

    def _on_mqtt_answer(self, answer_event):
        if not self.game_started:
            return

        player_id = answer_event.player_id
        answer = answer_event.answer

        print(f"\n🎯 AUTO JUDGING: Player {player_id} answered {answer}")
        self._auto_judge_answer(player_id, answer)

    def _on_player_connected(self, player_id: int):
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(True)
        # FIX: register with engine so cascading attempts use real player set
        self.engine.register_active_player(player_id)

    def _on_player_disconnected(self, player_id: int):
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(False)

    def _update_connection_status(self):
        """Passive connection poll — runs every 2s."""
        if not self.mqtt_backend:
            return
        connected_players = self.mqtt_backend.get_connected_players(timeout_seconds=10)
        for pid, card in self.player_cards.items():
            card.set_connected(pid in connected_players)

    # =========================================================================
    # QUESTION SETUP
    # =========================================================================

    def _prepare_current_question_ui(self):
        """Reset per-question UI + reset MQTT backend question state."""
        self._warned_7 = False
        self._warned_3 = False
        # FIX #2: mark that any prior heartbeat round is done before starting new one
        self._heartbeat_in_progress = False

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

        self.cascading_widget.reset()
        for card in self.player_cards.values():
            card.set_eliminated(False)
            card.highlight_locked(False)

        self.timer.set_remaining_ms(self.engine.get_question_remaining_ms())

        # Update round badge
        self._update_round_badge()

        if self.mqtt_backend:
            q = self.engine.current_question()
            self.mqtt_backend.start_question(question_id=q.id, max_attempts=q.max_attempts)

            # FIX #2: only start a new heartbeat round if one isn't already running.
            if not self._heartbeat_in_progress:
                self._heartbeat_in_progress = True
                self.status_label.setText("📡 Pinging connected buzzers...")
                self.mqtt_backend.send_heartbeat_to_all(timeout_seconds=10)
                # _apply_heartbeat_results will be called via bridge.heartbeat_resolved signal

        self._render_question()
        self._render_scores()
        self.btn_next.setEnabled(True)

    def _apply_heartbeat_results(self, alive_map: dict):
        """Called on main thread when heartbeat round resolves.

        FIX #2: replaces the polling QTimer.singleShot chain entirely.
        alive_map is {player_id: bool} emitted by bridge.heartbeat_resolved.

        Handles two contexts:
        - Round transition screen is showing: update btn_continue label/state.
        - Normal question screen: update status_label and btn_unlock as before.
        """
        self._heartbeat_in_progress = False

        if not self.mqtt_backend:
            return

        alive_players = [pid for pid, alive in alive_map.items() if alive]

        # Always update player cards (visible on host screen; harmless if hidden)
        for pid, card in self.player_cards.items():
            card.set_connected(pid in alive_players)

        # Update engine's active player set so cascading logic is accurate
        if alive_players:
            self.engine.set_active_players(alive_players)

        # ── Context: round transition screen is visible ────────────────────────
        if self.round_transition_screen.isVisible():
            btn = self.round_transition_screen.btn_continue
            if len(alive_players) == 0:
                btn.setText("⚠️ No buzzers — START NEXT ROUND anyway")
                btn.setStyleSheet(
                    "QPushButton { "
                    "background: rgba(231, 76, 60, 0.3); "
                    "border: 3px solid #e74c3c; border-radius: 12px; "
                    "padding: 25px 50px; font-size: 22px; font-weight: 900; color: white; }"
                    "QPushButton:hover { background: rgba(231, 76, 60, 0.5); }"
                )
            else:
                players_str = ", ".join(f"P{p}" for p in sorted(alive_players))
                btn.setText(f"✅ {players_str} ready — START NEXT ROUND")
                btn.setStyleSheet(
                    "QPushButton { "
                    "background: rgba(57, 255, 20, 0.3); "
                    "border: 4px solid #39FF14; border-radius: 12px; "
                    "padding: 25px 50px; font-size: 22px; font-weight: 900; color: white; }"
                    "QPushButton:hover { background: rgba(57, 255, 20, 0.5); }"
                    "QPushButton:pressed { background: rgba(57, 255, 20, 0.7); }"
                )
            btn.setEnabled(True)   # always allow host to proceed regardless of result
            return

        # ── Context: normal question screen ───────────────────────────────────
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

        locked = self.engine.locked_buzzer_id
        if locked is None:
            print(f"🚫 Ignored answer from P{player_id} (no one is locked)")
            return
        if player_id != locked:
            print(f"🚫 Ignored answer from P{player_id} (locked player is P{locked})")
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

        self.engine.apply_answer(is_correct, player_id)

        if is_correct:
            self.sfx.play_correct()
            self.sfx.play_point()
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

        remaining_players = self.engine.get_players_remaining()
        question = self.engine.current_question()
        can_continue = (
            self.engine.current_attempt_number <= question.max_attempts
            and len(remaining_players) > 0
        )

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

        # Start buzzer ping before the fade so results arrive during the animation.
        if self.mqtt_backend and not self._heartbeat_in_progress:
            self._heartbeat_in_progress = True
            self._round_transition_ping_pending = True
            self.round_transition_screen.btn_continue.setEnabled(False)
            self.round_transition_screen.btn_continue.setText("📡 Pinging buzzers...")
            self.mqtt_backend.send_heartbeat_to_all(timeout_seconds=10)
        else:
            self._round_transition_ping_pending = False

        # Show the dialog floating over the (still-visible) host screen.
        self.round_transition_screen.show()
        self.round_transition_screen.fade_in(duration_ms=400)

    def _finish_show_round_transition(self):
        pass  # no longer used — kept as a no-op for safety

    def _continue_to_next_round(self):
        """Advance to the next round after the transition screen."""
        self.round_transition_screen.btn_continue.setEnabled(False)

        if getattr(self, "_round_transition_ping_pending", False):
            self._heartbeat_in_progress = True
            self._round_transition_ping_pending = False

        self.round_transition_screen.fade_out(
            duration_ms=300,
            callback=self._finish_continue_to_next_round,
        )

    def _finish_continue_to_next_round(self):
        self.round_transition_screen.hide()
        self.round_transition_screen.cleanup()
        self.round_transition_screen.setWindowOpacity(1.0)
        self.round_transition_screen.btn_continue.setEnabled(True)

        self.current_round += 1
        self._update_round_badge()
        self.engine.next_question()

    def _show_winner_screen(self):
        ranking = self.engine.scores.get_ranking()
        winner_id = ranking[0][0] if ranking else 1
        scores_dict = dict(ranking)
        self.winner_screen.set_results(scores=scores_dict, winner_id=winner_id)
        self.winner_screen.show()
        self.winner_screen.fade_in(duration_ms=500)

    def _finish_show_winner_screen(self):
        pass  # no longer used — kept as a no-op for safety

    def _play_again(self):
        self.winner_screen.fade_out(
            duration_ms=300,
            callback=self._finish_play_again,
        )

    def _finish_play_again(self):
        self.winner_screen.cleanup()
        self.winner_screen.hide()
        self.winner_screen.setWindowOpacity(1.0)
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

        player_colors = {1: "#e74c3c", 2: "#3498db", 3: "#2ecc71", 4: "#f39c12"}

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
                f"border: 3px solid {color}; border-radius: 10px; "
                f"padding: 15px; font-size: 16px; font-weight: 900; color: white; }}"
                f"QPushButton:hover {{ background: {color}60; }}"
                f"QPushButton:pressed {{ background: {color}80; }}"
            )
            btn.clicked.connect(lambda checked, pid=player_id: self._apply_bonus_point(pid, dialog))
            buttons_layout.addWidget(btn)

        layout.addLayout(buttons_layout)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background: rgba(100,100,100,0.3); border: 2px solid #666; "
            "border-radius: 8px; padding: 12px; font-size: 14px; font-weight: 700; color: white; }"
            "QPushButton:hover { background: rgba(100,100,100,0.5); }"
        )
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn)

        dialog.exec()

    def _apply_bonus_point(self, player_id: int, dialog: QDialog):
        if hasattr(self.engine, 'award_bonus'):
            self.engine.award_bonus(player_id, 1, "Bonus point (admin awarded)")
        else:
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

        dialog.accept()
        print(f"[BONUS] ⭐ Admin awarded bonus point to Player {player_id}")

    # =========================================================================
    # TIMER SOUND EFFECTS
    # =========================================================================

    def _sfx_on_timer_changed(self, remaining_ms: int):
        if remaining_ms <= 7000 and not self._warned_7 and remaining_ms > 3000:
            self._warned_7 = True
            self.sfx.play_timer_warning()

        if remaining_ms <= 3000 and not self._warned_3 and remaining_ms > 0:
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
        </ul>
        <p><i>Admin Dashboard: Click ℹ️ to create/edit packs</i></p>
        """
        QMessageBox.information(self, "Help", help_text)