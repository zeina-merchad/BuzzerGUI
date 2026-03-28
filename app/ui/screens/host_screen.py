# app/ui/screens/host_screen.py
from typing import Optional
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QFrame, QGridLayout, QDialog
)
import sys, os
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

        elif action == "prev_question":
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
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self.hide)
        QTimer.singleShot(0, self.resize_to_parent)

    def resize_to_parent(self):
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())

    def flash_green(self, text: str = "✅ CORRECT!", ms: int = 650):
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
    """Player card with hardware connection indicator.

    Visual rule:
    - WAITING  -> neutral grey
    - READY    -> neutral grey
    - BUZZED   -> team color
    - ELIMINATED -> red
    """

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

        self.setFixedSize(280, 320)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(200, 200)
        self._set_neutral_icon()

        self.label = QLabel(f"P{player_id}: WAITING")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(self._neutral_label_style())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon, alignment=Qt.AlignCenter)
        lay.addWidget(self.label)

    # ---------------------------------------------------------------------
    # Styles
    # ---------------------------------------------------------------------

    def _icon_style(self, bg: str, border: str, color: str, font: int) -> str:
        return (
            f"QLabel {{ "
            f"background: {bg}; "
            f"border: {border}; "
            f"border-radius: 100px; "
            f"color: {color}; "
            f"font-size: {font}px; "
            f"font-weight: 900; "
            f"}}"
        )

    def _label_style(self, bg: str) -> str:
        return (
            f"font-size: 22px; font-weight: 900; color: white; "
            f"background: {bg}; "
            f"padding: 12px 18px; border-radius: 10px;"
        )

    def _neutral_label_style(self) -> str:
        return self._label_style("rgba(100, 100, 100, 0.7)")

    def _buzzed_label_style(self) -> str:
        return self._label_style(self.color)

    def _eliminated_label_style(self) -> str:
        return self._label_style("rgba(231, 76, 60, 0.8)")

    # ---------------------------------------------------------------------
    # Icon states
    # ---------------------------------------------------------------------

    def _set_neutral_icon(self):
        self.icon.setStyleSheet(
            self._icon_style(
                bg="rgba(85, 85, 85, 0.6)",
                border="none",
                color="#cccccc",
                font=70,
            )
        )
        self.icon.setText(str(self._score))

    def _set_buzzed_icon(self):
        self.icon.setStyleSheet(
            self._icon_style(
                bg=self.color,
                border="none",
                color="white",
                font=70,
            )
        )
        self.icon.setText(str(self._score))

    def _set_eliminated_icon(self):
        self.icon.setStyleSheet(
            self._icon_style(
                bg="rgba(231, 76, 60, 0.4)",
                border="none",
                color="#e74c3c",
                font=70,
            )
        )
        self.icon.setText(str(self._score))

    # ---------------------------------------------------------------------
    # Public state updates
    # ---------------------------------------------------------------------

    def set_connected(self, is_connected: bool):
        self.is_hardware_connected = is_connected

        # Elimination always wins visually
        if self.is_eliminated:
            self._set_eliminated_icon()
            self.label.setText(f"P{self.player_id}: ELIMINATED")
            self.label.setStyleSheet(self._eliminated_label_style())
            return

        # Buzzed always wins visually
        if self.is_buzzed:
            self._set_buzzed_icon()
            self.label.setText(f"P{self.player_id}: BUZZED! ({self._score}pts)")
            self.label.setStyleSheet(self._buzzed_label_style())
            return

        # Connected/ready should STILL be neutral
        self._set_neutral_icon()
        if is_connected:
            self.label.setText(f"P{self.player_id}: READY ({self._score}pts)")
        else:
            self.label.setText(f"P{self.player_id}: WAITING ({self._score}pts)")
        self.label.setStyleSheet(self._neutral_label_style())

    def set_eliminated(self, is_eliminated: bool):
        self.is_eliminated = is_eliminated

        if is_eliminated:
            self.is_buzzed = False
            self._set_eliminated_icon()
            self.label.setText(f"P{self.player_id}: ELIMINATED ({self._score}pts)")
            self.label.setStyleSheet(self._eliminated_label_style())
            return

        # When elimination is removed, return to the correct non-colored state
        if self.is_buzzed:
            self._set_buzzed_icon()
            self.label.setText(f"P{self.player_id}: BUZZED! ({self._score}pts)")
            self.label.setStyleSheet(self._buzzed_label_style())
        else:
            self._set_neutral_icon()
            if self.is_hardware_connected:
                self.label.setText(f"P{self.player_id}: READY ({self._score}pts)")
            else:
                self.label.setText(f"P{self.player_id}: WAITING ({self._score}pts)")
            self.label.setStyleSheet(self._neutral_label_style())

    def set_score(self, value: int):
        self._score = int(value)

        if self.is_eliminated:
            self._set_eliminated_icon()
            self.label.setText(f"P{self.player_id}: ELIMINATED ({self._score}pts)")
            self.label.setStyleSheet(self._eliminated_label_style())
        elif self.is_buzzed:
            self._set_buzzed_icon()
            self.label.setText(f"P{self.player_id}: BUZZED! ({self._score}pts)")
            self.label.setStyleSheet(self._buzzed_label_style())
        else:
            # Even if connected, stay neutral unless buzzed
            self._set_neutral_icon()
            if self.is_hardware_connected:
                self.label.setText(f"P{self.player_id}: READY ({self._score}pts)")
            else:
                self.label.setText(f"P{self.player_id}: WAITING ({self._score}pts)")
            self.label.setStyleSheet(self._neutral_label_style())

    def highlight_locked(self, locked: bool):
        if self.is_eliminated:
            return

        self.is_buzzed = locked

        if locked:
            self._set_buzzed_icon()
            self.label.setText(f"P{self.player_id}: BUZZED! ({self._score}pts)")
            self.label.setStyleSheet(self._buzzed_label_style())
        else:
            # Always return to neutral after answer lock ends
            self._set_neutral_icon()
            if self.is_hardware_connected:
                self.label.setText(f"P{self.player_id}: READY ({self._score}pts)")
            else:
                self.label.setText(f"P{self.player_id}: WAITING ({self._score}pts)")
            self.label.setStyleSheet(self._neutral_label_style())

class HostScreen(RemoteKeyHandler, QWidget):
    """Main game screen with auto-judging from ESP32 answer buttons."""

    def __init__(self, engine: GameEngine, mqtt_backend: MQTTBuzzerBackend):
        super().__init__()
        self.engine = engine
        self.mqtt_backend = mqtt_backend

        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1

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

        self._build_ui()
        self._connect_engine_signals()
        self._connect_mqtt_callbacks()

        self.connection_timer = QTimer(self)
        self.connection_timer.timeout.connect(self._update_connection_status)
        self.connection_timer.start(2000)

        self._render_scores()

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        game_grid = QGridLayout()
        game_grid.setHorizontalSpacing(20)
        game_grid.setVerticalSpacing(15)

        self.player_cards = {}
        self._create_logo_label()

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

        self.correct_flash = FlashOverlay(self)
        self.correct_flash.hide()

    def _create_logo_label(self):
        self.logo_label = QLabel()
        self.logo_label.setPixmap(
            QPixmap(self.resource_path("app/ui/screens/logo_full.png")).scaled(
                320, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(320, 320)
        self.logo_label.setStyleSheet("QLabel { background: transparent; border: none; }")

    def _build_player_columns(self):
        left_column = QWidget()
        left_column.setStyleSheet("QWidget { background: transparent; }")
        left_layout = QVBoxLayout(left_column)
        left_layout.setSpacing(20)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.player_cards[1] = CornerPlayerCard(1)
        left_layout.addWidget(self.player_cards[1], alignment=Qt.AlignCenter)
        left_layout.addStretch(1)

        self.cascading_widget = CascadingAttemptsWidget()
        left_layout.addWidget(self.cascading_widget, alignment=Qt.AlignCenter)
        left_layout.addStretch(1)

        self.player_cards[3] = CornerPlayerCard(3)
        left_layout.addWidget(self.player_cards[3], alignment=Qt.AlignCenter)

        right_column = QWidget()
        right_column.setStyleSheet("QWidget { background: transparent; }")
        right_layout = QVBoxLayout(right_column)
        right_layout.setSpacing(20)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.player_cards[2] = CornerPlayerCard(2)
        right_layout.addWidget(self.player_cards[2], alignment=Qt.AlignCenter)
        right_layout.addStretch(1)
        right_layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)
        right_layout.addStretch(1)

        self.player_cards[4] = CornerPlayerCard(4)
        right_layout.addWidget(self.player_cards[4], alignment=Qt.AlignCenter)

        return left_column, right_column

    def _build_center_area(self):
        center_widget = QWidget()
        center_widget.setStyleSheet("QWidget { background: transparent; }")
        center_widget.setMaximumWidth(1000)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(15)
        center_layout.setContentsMargins(60, 0, 60, 0)

        timer_row = QWidget()
        timer_row.setStyleSheet("QWidget { background: transparent; }")
        timer_row_layout = QHBoxLayout(timer_row)
        timer_row_layout.setContentsMargins(0, 0, 0, 0)
        timer_row_layout.setSpacing(16)

        self.timer = TimerWidget()
        timer_row_layout.addWidget(self.timer, alignment=Qt.AlignVCenter)

        self.round_badge = QLabel("ROUND 1")
        self.round_badge.setAlignment(Qt.AlignCenter)
        self.round_badge.setStyleSheet(
            "font-size: 18px; font-weight: 900; color: #ffd700; "
            "background: rgba(255, 215, 0, 0.15); "
            "border: 2px solid #ffd700; border-radius: 10px; "
            "padding: 8px 18px; letter-spacing: 2px;"
        )
        self.round_badge.hide()
        timer_row_layout.addWidget(self.round_badge, alignment=Qt.AlignVCenter)
        timer_row_layout.addStretch()

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

    # =========================================================================
    # PATH / WIRING
    # =========================================================================

    def resource_path(self, rel: str) -> str:
        if getattr(sys, "frozen", False):
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
            root = os.path.dirname(os.path.abspath(__file__))
            root = os.path.dirname(root)
            root = os.path.dirname(root)
            root = os.path.dirname(root)
            return os.path.join(root, rel)

    def _connect_engine_signals(self):
        self.engine.phase_changed.connect(self._on_phase)
        self.engine.question_changed.connect(self._render_question)
        self.engine.timer_changed.connect(self._on_timer_changed_ui)
        self.engine.timer_changed.connect(self._sfx_on_timer_changed)
        self.engine.lock_changed.connect(self._on_lock)
        self.engine.scores_changed.connect(self._render_scores)
        self.engine.attempt_changed.connect(self._on_attempt_changed)
        self.engine.attempt_failed.connect(self._on_attempt_failed)

        if hasattr(self.engine, "question_advanced"):
            self.engine.question_advanced.connect(self._on_engine_question_advanced)

    def _connect_mqtt_callbacks(self):
        if not self.mqtt_backend:
            return
        self.mqtt_backend.on_buzz_callback = self._on_mqtt_buzz
        self.mqtt_backend.on_answer_callback = self._on_mqtt_answer
        self.mqtt_backend.on_player_connected_callback = self._on_player_connected
        self.mqtt_backend.on_player_disconnected_callback = self._on_player_disconnected

        self.mqtt_backend.bridge.heartbeat_resolved.connect(
            self._apply_heartbeat_results, Qt.QueuedConnection
        )

    # =========================================================================
    # QT EVENTS
    # =========================================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "correct_flash"):
            self.correct_flash.resize_to_parent()

    def keyPressEvent(self, event):
        if not self._handle_remote_key(event):
            super().keyPressEvent(event)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _neutralize_all_cards(self):
        for pid, card in self.player_cards.items():
            card.highlight_locked(False)
            if pid in getattr(self.engine, "_active_player_ids", set()):
                card.set_connected(True)
            else:
                card.set_connected(False)
            if pid in self.engine.players_attempted:
                card.set_eliminated(True)
            else:
                card.set_eliminated(False)

    def _set_status(self, text: str, level: str = "neutral"):
        if level == "good":
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(57, 255, 20, 1.0); "
                "background: rgba(57, 255, 20, 0.2); "
                "padding: 12px 20px; border: 2px solid #39FF14; border-radius: 8px;"
            )
        elif level == "warn":
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
                "background: rgba(255, 193, 7, 0.2); "
                "padding: 12px 20px; border: 2px solid #ffc107; border-radius: 8px;"
            )
        elif level == "bad":
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; border-radius: 8px;"
            )
        else:
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(255, 255, 255, 0.7); "
                "background: rgba(57, 255, 20, 0.15); "
                "padding: 12px 20px; border: 2px solid rgba(57, 255, 20, 0.3); "
                "border-radius: 8px;"
            )
        self.status_label.setText(text)
        self.status_label.show()

    def _current_round_from_index(self) -> int:
        qpr = max(1, int(getattr(self.engine.cfg, "questions_per_round", 1)))
        return (self.engine.current_q_idx // qpr) + 1

    def _prepare_current_question_ui(self):
        self._warned_7 = False
        self._warned_3 = False
        self._render_question()
        self._neutralize_all_cards()
        self._on_attempt_changed(self.engine.get_current_attempt_number())

        self.btn_unlock.setEnabled(True)
        self.btn_unlock.setText("🔓 UNLOCK BUZZERS")
        self.btn_next.setEnabled(False)
        self.buzzers_unlocked = False

        self.current_round = self._current_round_from_index()
        self.round_badge.setText(f"ROUND {self.current_round}")
        self.round_badge.show()

        if self.mqtt_backend and self.engine.has_questions():
            q = self.engine.current_question()
            self.mqtt_backend.start_question(q.id, getattr(q, "max_attempts", 1))

    def _show_round_transition_if_needed(self) -> bool:
        qpr = max(1, int(getattr(self.engine.cfg, "questions_per_round", 1)))
        next_idx = self.engine.current_q_idx + 1
        total_questions = len(getattr(self.engine, "questions", []))

        if next_idx <= 0 or next_idx >= total_questions:
            return False

        if next_idx % qpr != 0:
            return False

        ranking = self.engine.scores.get_ranking()
        self.round_transition_screen.set_round_info(
            completed_round=self._current_round_from_index(),
            scores=ranking,
        )
        self.round_transition_screen.show()
        self._round_transition_ping_pending = True
        self._heartbeat_in_progress = True

        if self.mqtt_backend:
            self.mqtt_backend.send_heartbeat_to_all()

        return True

    # =========================================================================
    # GAME CONTROL
    # =========================================================================

    def _start_game(self):
        q_list = getattr(self.engine, "questions", None) or getattr(self.engine, "_questions", None)
        if not q_list:
            QMessageBox.warning(
                self,
                "No Questions Loaded",
                "No questions are loaded.\n\nOpen the Admin Dashboard (ℹ️), load an Excel pack, then try again.",
            )
            return

        self.game_started = True
        self.engine.reset_game()
        self.btn_start_game.hide()
        self.btn_unlock.show()
        self.btn_next.show()
        self.phase_label.show()
        self.status_label.show()
        self.round_badge.show()

        self.engine.start_question()
        self._prepare_current_question_ui()
        self._set_status("Game started. Press UNLOCK BUZZERS when ready.", "good")
        self.sfx.play_start()

    def _load_next_question(self):
        if not self.game_started:
            return

        if self._show_round_transition_if_needed():
            return

        self.engine.next_question()

        if self.engine.phase == Phase.GAME_END:
            self._show_winner_screen()
            return

        self._prepare_current_question_ui()
        self.sfx.play_next()

    def _load_prev_question(self):
        if not self.game_started:
            return

        self.engine.prev_question()
        self._prepare_current_question_ui()

    def _continue_to_next_round(self):
        self._round_transition_ping_pending = False
        self.round_transition_screen.hide()

        self.engine.next_question()

        if self.engine.phase == Phase.GAME_END:
            self._show_winner_screen()
            return

        self._prepare_current_question_ui()
        self.sfx.play_next()

    def _play_again(self):
        self.winner_screen.hide()
        self._reset_game()
        self._start_game()

    def _exit_game(self):
        self.window().close()

    def _reset_game(self):
        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1
        self._heartbeat_in_progress = False
        self._round_transition_ping_pending = False

        self.engine.reset_game()

        if self.mqtt_backend:
            self.mqtt_backend.end_question()

        self.question.setText("Press START GAME to begin")
        self.options.set_options([])
        self.media.clear() if hasattr(self.media, "clear") else None
        self.timer.set_remaining_ms(0)

        self.btn_start_game.show()
        self.btn_unlock.hide()
        self.btn_unlock.setEnabled(False)
        self.btn_unlock.setText("🔓 UNLOCK BUZZERS")
        self.btn_next.hide()
        self.btn_next.setEnabled(False)
        self.round_badge.hide()

        self._neutralize_all_cards()
        self._render_scores()
        self._set_status("Game reset. Waiting for players...", "neutral")

        self.winner_screen.hide()
        self.round_transition_screen.hide()

    # =========================================================================
    # RENDERING
    # =========================================================================

    def _render_question(self):
        if not self.engine.has_questions():
            self.question.setText("No questions loaded")
            self.options.set_options([])
            if hasattr(self.media, "clear"):
                self.media.clear()
            return

        q = self.engine.current_question()
        self.question.setText(q.text)
        self.options.set_options(q.options)

        if hasattr(self.media, "set_media"):
            self.media.set_media(q.media)

        self.current_round = self._current_round_from_index()
        self.round_badge.setText(f"ROUND {self.current_round}")

    def _render_scores(self):
        for pid, card in self.player_cards.items():
            score = self.engine.scores.scores.get(pid, 0)
            card.set_score(score)

    def _show_winner_screen(self):
        ranking = self.engine.scores.get_ranking()
        winner = self.engine.scores.get_winner()
        self.winner_screen.set_winner_info(winner, ranking)
        self.winner_screen.show()

    # =========================================================================
    # ENGINE SIGNAL HANDLERS
    # =========================================================================

    def _on_engine_question_advanced(self):
        self._prepare_current_question_ui()

    def _on_phase(self, phase_name: str):
        self.phase_label.setText(f"PHASE: {phase_name}")

        if phase_name == Phase.IDLE.value:
            if self.game_started:
                self.btn_unlock.setEnabled(False)
                self.btn_next.setEnabled(True)

        elif phase_name == Phase.SHOW_QUESTION.value:
            self.btn_unlock.setEnabled(True)
            self.btn_next.setEnabled(False)

        elif phase_name == Phase.BUZZED.value:
            self.btn_unlock.setEnabled(False)
            self.btn_next.setEnabled(False)

        elif phase_name == Phase.GAME_END.value:
            self.btn_unlock.setEnabled(False)
            self.btn_next.setEnabled(False)

    def _on_timer_changed_ui(self, remaining_ms: int):
        self.timer.set_remaining_ms(remaining_ms)

    def _sfx_on_timer_changed(self, remaining_ms: int):
        secs = int((remaining_ms + 999) / 1000)
        if secs <= 7 and not self._warned_7 and secs > 3:
            self._warned_7 = True
            self.sfx.play_timer_warning()
        if secs <= 3 and not self._warned_3 and secs > 0:
            self._warned_3 = True
            self.sfx.play_timer_critical()

    def _on_lock(self, locked_player_id):
        for pid, card in self.player_cards.items():
            card.highlight_locked(pid == locked_player_id)

        if locked_player_id is None:
            # When lock is cleared, all non-eliminated players go back neutral.
            self._neutralize_all_cards()
            return

        self._set_status(f"Player {locked_player_id} buzzed first. Waiting for answer...", "warn")
        self.sfx.play_buzz()

    def _on_attempt_changed(self, attempt_number: int):
        remaining = self.engine.get_players_remaining()
        active_players = sorted(getattr(self.engine, "_active_player_ids", set()))

        self.cascading_widget.update_attempt(
            attempt_number,
            self.engine.get_points_for_current_attempt(),
            remaining,
            active_players=active_players,
        )

        if attempt_number > 1:
            self._set_status(f"Attempt {attempt_number} - Remaining players: {remaining}", "warn")

    def _on_attempt_failed(self, player_id: int, attempt_number: int):
        if player_id in self.player_cards:
            self.player_cards[player_id].highlight_locked(False)
            self.player_cards[player_id].set_eliminated(True)

        self.options.reset_eliminated() if hasattr(self.options, "reset_eliminated") else None
        self.sfx.play_wrong()

    # =========================================================================
    # MQTT CALLBACKS
    # =========================================================================

    def _on_player_connected(self, player_id: int):
        self.engine.register_active_player(player_id)
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(True)

    def _on_player_disconnected(self, player_id: int):
        self.engine.unregister_active_player(player_id)

        if player_id in self.player_cards:
            card = self.player_cards[player_id]
            card.highlight_locked(False)
            card.set_connected(False)
            if player_id not in self.engine.players_attempted:
                card.set_eliminated(False)

        if self.engine.phase == Phase.SHOW_QUESTION and not self.engine.get_players_remaining():
            self._set_status("No active players remaining for this question.", "bad")

    def _apply_heartbeat_results(self, alive_map: dict):
        self._heartbeat_in_progress = False

        if not self.mqtt_backend:
            return

        alive_players = sorted(pid for pid, alive in alive_map.items() if alive)
        self.engine.set_active_players(alive_players)

        for pid, card in self.player_cards.items():
            card.set_connected(pid in alive_players)

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
                players_str = ", ".join(f"P{p}" for p in alive_players)
                btn.setText(f"✅ {players_str} ready — START NEXT ROUND")
                btn.setStyleSheet(
                    "QPushButton { "
                    "background: rgba(57, 255, 20, 0.3); "
                    "border: 4px solid #39FF14; border-radius: 12px; "
                    "padding: 25px 50px; font-size: 22px; font-weight: 900; color: white; }"
                    "QPushButton:hover { background: rgba(57, 255, 20, 0.5); }"
                    "QPushButton:pressed { background: rgba(57, 255, 20, 0.7); }"
                )
            btn.setEnabled(True)

    def _on_mqtt_buzz(self, event):
        accepted = self.engine.on_buzz(
            event.player_id,
            event.timestamp_ms,
            event.server_received_ms,
        )
        if not accepted:
            return

        if self.mqtt_backend:
            self.mqtt_backend.lock_player(event.player_id)

    def _on_mqtt_answer(self, event):
        if self.engine.locked_buzzer_id is None:
            return
        if event.player_id != self.engine.locked_buzzer_id:
            return

        q = self.engine.current_question()
        answer_letter = (event.answer or "").strip().upper()
        answer_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        selected_index = answer_map.get(answer_letter, -1)
        is_correct = selected_index == q.correct_index

        if not is_correct and hasattr(self.options, "mark_option_eliminated"):
            self.options.mark_option_eliminated(answer_letter)

        self.engine.apply_answer(is_correct, event.player_id)

        if self.mqtt_backend:
            if is_correct:
                self.mqtt_backend.mark_answer_correct(event.player_id)
            else:
                self.mqtt_backend.mark_answer_wrong(event.player_id)

        if is_correct:
            self.correct_flash.flash_green()
            self.sfx.play_correct()
            self._set_status(f"✅ Player {event.player_id} answered correctly.", "good")
            self.btn_next.setEnabled(True)
            self.btn_unlock.setEnabled(False)
        else:
            self.sfx.play_wrong()
            remaining = self.engine.get_players_remaining()
            if remaining and self.engine.phase == Phase.SHOW_QUESTION:
                self._set_status(
                    f"❌ Wrong answer by P{event.player_id}. Unlock for next attempt.",
                    "bad",
                )
                self.btn_unlock.setEnabled(True)
                self.btn_unlock.setText("🔓 UNLOCK BUZZERS")
            else:
                self._set_status("❌ Wrong answer. No more attempts.", "bad")
                self.btn_next.setEnabled(True)
                self.btn_unlock.setEnabled(False)

    # =========================================================================
    # CONTROL ACTIONS
    # =========================================================================

    def _unlock_buzzers(self):
        if not self.game_started:
            return

        if self.engine.phase != Phase.SHOW_QUESTION:
            return

        remaining_players = self.engine.get_players_remaining()
        if not remaining_players:
            self._set_status("Cannot unlock: no active players remaining.", "bad")
            return

        self.buzzers_unlocked = True
        self.btn_unlock.setEnabled(False)
        self.btn_unlock.setText("🔓 BUZZERS LIVE")

        for pid, card in self.player_cards.items():
            card.highlight_locked(False)
            card.set_connected(pid in getattr(self.engine, "_active_player_ids", set()))
            if pid in self.engine.players_attempted:
                card.set_eliminated(True)
            else:
                card.set_eliminated(False)

        self._set_status("Buzzers unlocked - waiting for fastest player.", "good")

        if self.mqtt_backend:
            self.mqtt_backend.unlock_buzzers()

        self.engine.notify_buzzers_unlocked()
        self.engine.start_or_resume_question_timer()

    def _award_bonus_point(self):
        if not self.game_started:
            return

        ranking = self.engine.scores.get_ranking()
        if not ranking:
            return

        leader_id = ranking[0][0]
        self.engine.award_bonus(leader_id, 1, "Manual bonus point")
        self.sfx.play_point()
        self._set_status(f"⭐ Bonus point awarded to Player {leader_id}.", "good")

    def _show_help(self):
        QMessageBox.information(
            self,
            "Help",
            "START GAME: begin quiz\n"
            "UNLOCK BUZZERS: allow buzz-in\n"
            "NEXT QUESTION: advance\n"
            "RESET GAME: reset everything\n"
            "BONUS POINT: add 1 point to current leader",
        )

    def _update_connection_status(self):
        if not self.mqtt_backend:
            return

        connected = set(self.mqtt_backend.get_connected_players(timeout_seconds=10))
        for pid, card in self.player_cards.items():
            if not card.is_buzzed and not card.is_eliminated:
                card.set_connected(pid in connected)