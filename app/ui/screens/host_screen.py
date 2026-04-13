# app/ui/screens/host_screen.py
import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.engine import GameEngine
from app.core.sound_manager import create_sound_manager
from app.core.state import Phase
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend
from app.ui.screens.round_transition_screen import RoundTransitionScreen
from app.ui.screens.winner_screen import WinnerScreen
from app.ui.widgets.cascading_widget import CascadingAttemptsWidget
from app.ui.widgets.media_view import MediaView
from app.ui.widgets.options_view import OptionsView
from app.ui.widgets.timer_widget import TimerWidget

# Remote control key bindings (Rii i7 via USB dongle)
try:
    from app.ui.remote_config import MODIFIER_KEY, REMOTE_KEYS, REQUIRE_MODIFIER
except ImportError:
    REMOTE_KEYS = {
        "start_game": Qt.Key.Key_MediaPlay,
        "unlock_buzzers": Qt.Key.Key_Return,
        "next_question": Qt.Key.Key_MediaNext,
        "prev_question": Qt.Key.Key_MediaPrevious,
        "reset_game": Qt.Key.Key_MediaStop,
        "bonus_point": Qt.Key.Key_HomePage,
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
    """Full-screen overlay for quick CORRECT / WRONG feedback flashes."""

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

    def flash_red(self, text: str = "❌ WRONG!", ms: int = 500):
        self._flash_timer.stop()
        self.setText(text)
        self.resize_to_parent()
        self.setStyleSheet(
            "QLabel {"
            "background: rgba(231, 76, 60, 0.22);"
            "border: 5px solid #e74c3c;"
            "border-radius: 20px;"
            "color: #e74c3c;"
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

        from app.ui.display_config import SCALE as _S

        self.setMinimumSize(_S.card_min_w, _S.card_min_h)
        self.setMaximumWidth(_S.card_max_w)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(_S.circle_size, _S.circle_size)
        self._set_disconnected_icon()

        self.label = QLabel(f"P{player_id}: WAITING")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            f"font-size: {_S.card_label_font}px; font-weight: 900; color: white; "
            f"background: rgba(100, 100, 100, 0.7); "
            f"padding: {_S.card_label_padding}; border-radius: 8px;"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.icon, alignment=Qt.AlignHCenter)
        lay.addWidget(self.label, alignment=Qt.AlignHCenter)

    def _icon_style(self, bg: str, border: str, color: str, font: int) -> str:
        from app.ui.display_config import SCALE as _S

        return (
            f"QLabel {{ "
            f"background: {bg}; "
            f"border: {border}; "
            f"border-radius: {_S.circle_radius}px; "
            f"color: {color}; "
            f"font-size: {font}px; "
            f"font-weight: 900; "
            f"}}"
        )

    def _label_style(self, bg: str) -> str:
        from app.ui.display_config import SCALE as _S

        return (
            f"font-size: {_S.card_label_font}px; font-weight: 900; color: white; "
            f"background: {bg}; "
            f"padding: {_S.card_label_padding}; border-radius: 8px;"
        )

    def _set_disconnected_icon(self):
        from app.ui.display_config import SCALE as _S

        self.icon.setStyleSheet(
            self._icon_style(
                bg="rgba(85,85,85,0.6)",
                border="none",
                color="#cccccc",
                font=_S.circle_font,
            )
        )
        self.icon.setText(str(self._score))

    def _set_connected_icon(self):
        from app.ui.display_config import SCALE as _S

        self.icon.setStyleSheet(
            self._icon_style(
                bg="rgba(85,85,85,0.6)",
                border="none",
                color="#cccccc",
                font=_S.circle_font,
            )
        )
        self.icon.setText(str(self._score))

    def _set_buzzed_icon(self):
        from app.ui.display_config import SCALE as _S

        self.icon.setStyleSheet(
            self._icon_style(
                bg=self.color, border="none", color="white", font=_S.circle_font
            )
        )
        self.icon.setText(str(self._score))

    def _set_eliminated_icon(self):
        from app.ui.display_config import SCALE as _S

        self.icon.setStyleSheet(
            self._icon_style(
                bg="rgba(231,76,60,0.4)",
                border="none",
                color="#e74c3c",
                font=_S.circle_font,
            )
        )
        self.icon.setText(str(self._score))

    def set_connected(self, is_connected: bool):
        self.is_hardware_connected = is_connected
        if not self.is_buzzed and not self.is_eliminated:
            self._set_disconnected_icon()
        self.label.setText(f"P{self.player_id}: WAITING")
        self.label.setStyleSheet(self._label_style("rgba(100, 100, 100, 0.7)"))

    def set_eliminated(self, is_eliminated: bool):
        self.is_eliminated = is_eliminated
        if is_eliminated:
            self._set_eliminated_icon()
            self.label.setText(f"P{self.player_id}: ELIMINATED")
            self.label.setStyleSheet(self._label_style("rgba(231, 76, 60, 0.8)"))
        else:
            self._set_disconnected_icon()
            self.label.setText(f"P{self.player_id}: WAITING")
            self.label.setStyleSheet(self._label_style("rgba(100, 100, 100, 0.7)"))

    def set_score(self, value: int):
        self._score = int(value)
        if self.is_eliminated:
            self._set_eliminated_icon()
            self.label.setText(f"P{self.player_id}: ELIMINATED ({self._score}pts)")
            self.label.setStyleSheet(self._label_style("rgba(231, 76, 60, 0.8)"))
        elif self.is_buzzed:
            self._set_buzzed_icon()
            self.label.setText(f"P{self.player_id}: BUZZED! ({self._score}pts)")
            self.label.setStyleSheet(self._label_style(self.color))
        else:
            self._set_disconnected_icon()
            self.label.setText(f"P{self.player_id}: WAITING ({self._score}pts)")
            self.label.setStyleSheet(self._label_style("rgba(100, 100, 100, 0.7)"))

    def highlight_locked(self, locked: bool):
        if self.is_eliminated:
            return
        self.is_buzzed = locked
        if locked:
            self._set_buzzed_icon()
        else:
            self._set_disconnected_icon()
        self.set_score(self._score)


class HostScreen(RemoteKeyHandler, QWidget):
    """Main game screen with auto-judging from ESP32 answer buttons.

    Active player model
    -------------------
    When the host clicks START GAME, the currently-connected MQTT players are
    captured from mqtt_backend.get_connected_players() and registered with the
    engine via engine.register_game_players().  Any player that buzzes in later
    (even if they weren't connected at start time) is auto-registered in the
    engine's on_buzz() method, so late hardware always works.

    There is no periodic heartbeat, ping/pong, or passive-disconnect check.
    Players are considered alive for the entire game session once they have
    been registered.
    """

    def __init__(self, engine: GameEngine, mqtt_backend: MQTTBuzzerBackend):
        super().__init__()
        self.engine = engine
        self.mqtt_backend = mqtt_backend

        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1

        # Guard flag: set True while _auto_judge_answer is processing an answer
        # so that _on_attempt_failed knows NOT to duplicate MQTT/SFX calls.
        self._answer_judged_by_button = False

        self.winner_screen = WinnerScreen(parent=self)
        self.winner_screen.hide()
        self.winner_screen.btn_play_again.clicked.connect(self._play_again)
        self.winner_screen.btn_exit.clicked.connect(self._exit_game)

        self.round_transition_screen = RoundTransitionScreen(parent=self)
        self.round_transition_screen.hide()
        self.round_transition_screen.btn_continue.clicked.connect(
            self._continue_to_next_round
        )

        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QWidget { background: #0d1b2a; }")

        self.sfx = create_sound_manager()
        self._warned_7 = False
        self._warned_3 = False

        self._build_ui()
        self._connect_engine_signals()
        self._connect_mqtt_callbacks()

        self._render_scores()

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        from app.ui.display_config import SCALE

        root = QVBoxLayout(self)
        root.setContentsMargins(
            SCALE.root_margins,
            SCALE.root_margins,
            SCALE.root_margins,
            SCALE.root_margins,
        )
        root.setSpacing(0)

        self.player_cards = {}
        self._create_logo_label()

        left_column, right_column = self._build_player_columns()
        center_widget = self._build_center_area()

        main_row = QHBoxLayout()
        main_row.setSpacing(SCALE.main_row_spacing)
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.addWidget(left_column, stretch=1)
        main_row.addWidget(center_widget, stretch=3)
        main_row.addWidget(right_column, stretch=1)

        root.addLayout(main_row, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 6, 0, 6)
        bottom_row.addWidget(self._build_control_panel())
        root.addLayout(bottom_row)

        self.correct_flash = FlashOverlay(self)
        self.correct_flash.hide()

    def _create_logo_label(self):
        from app.ui.display_config import SCALE

        self.logo_label = QLabel()
        self.logo_label.setPixmap(
            QPixmap(self.resource_path("app/ui/screens/logo_full.png")).scaled(
                SCALE.logo_size,
                SCALE.logo_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(SCALE.logo_size, SCALE.logo_size)
        self.logo_label.setStyleSheet(
            "QLabel { background: transparent; border: none; }"
        )

    def _build_player_columns(self):
        from PySide6.QtWidgets import QSizePolicy as QSP

        left_column = QWidget()
        left_column.setStyleSheet("QWidget { background: transparent; }")
        left_column.setSizePolicy(QSP.Policy.Preferred, QSP.Policy.Expanding)
        left_layout = QVBoxLayout(left_column)
        left_layout.setSpacing(0)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.player_cards[1] = CornerPlayerCard(1)
        left_layout.addWidget(self.player_cards[1], 0, Qt.AlignHCenter)
        left_layout.addStretch(1)

        self.cascading_widget = CascadingAttemptsWidget()
        left_layout.addWidget(self.cascading_widget, 0, Qt.AlignHCenter)
        left_layout.addStretch(1)

        self.player_cards[3] = CornerPlayerCard(3)
        left_layout.addWidget(self.player_cards[3], 0, Qt.AlignHCenter)

        right_column = QWidget()
        right_column.setStyleSheet("QWidget { background: transparent; }")
        right_column.setSizePolicy(QSP.Policy.Preferred, QSP.Policy.Expanding)
        right_layout = QVBoxLayout(right_column)
        right_layout.setSpacing(0)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.player_cards[2] = CornerPlayerCard(2)
        right_layout.addWidget(self.player_cards[2], 0, Qt.AlignHCenter)
        right_layout.addStretch(1)

        right_layout.addWidget(self.logo_label, 0, Qt.AlignHCenter)
        right_layout.addStretch(1)

        self.player_cards[4] = CornerPlayerCard(4)
        right_layout.addWidget(self.player_cards[4], 0, Qt.AlignHCenter)

        return left_column, right_column

    def _build_center_area(self):
        from app.ui.display_config import SCALE

        center_widget = QWidget()
        center_widget.setStyleSheet("QWidget { background: transparent; }")
        center_widget.setMaximumWidth(1200)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(SCALE.center_spacing)
        center_layout.setContentsMargins(
            SCALE.center_h_margins, 0, SCALE.center_h_margins, 0
        )

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
            f"font-size: {SCALE.question_font}px; font-weight: 900; color: white; "
            f"padding: {SCALE.question_padding}; background: rgba(20, 30, 45, 0.8); "
            f"border: 3px solid #39FF14; border-radius: 16px; "
            f"min-height: {SCALE.question_min_h}px;"
        )
        center_layout.addWidget(self.question)

        self.options = OptionsView()
        center_layout.addWidget(self.options)

        return center_widget

    def _build_control_panel(self):
        from app.ui.display_config import SCALE

        control_panel = QFrame()
        control_panel.setStyleSheet(
            f"QFrame {{ "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(20, 30, 45, 0.95), stop:1 rgba(15, 25, 40, 0.95)); "
            "border: 2px solid rgba(57, 255, 20, 0.3); "
            f"border-radius: {SCALE.btn_radius + 4}px; "
            "}"
        )

        control_layout = QHBoxLayout(control_panel)
        control_layout.setSpacing(10)
        control_layout.setContentsMargins(20, 8, 20, 8)

        S = SCALE
        btn_base = (
            f"border-radius: {S.btn_radius}px; "
            f"padding: {S.btn_padding}; "
            f"font-size: {S.btn_font}px; font-weight: 900; "
            f"min-width: {S.btn_min_w}px; min-height: {S.btn_min_h}px; "
        )
        btn_disabled = "QPushButton:disabled { background: rgba(100,100,100,0.2); border-color: #666; color: #666; }"

        button_style = (
            f"QPushButton {{ background: rgba(57,255,20,0.15); border: 2px solid #39FF14; "
            f"color: white; {btn_base}}}"
            "QPushButton:hover { background: rgba(57,255,20,0.3); }"
            "QPushButton:pressed { background: rgba(57,255,20,0.5); }" + btn_disabled
        )

        self.phase_label = QLabel("PHASE: IDLE")
        self.phase_label.setStyleSheet(
            f"font-size: {S.phase_font}px; font-weight: 900; color: white; "
            "background: rgba(57,255,20,0.2); "
            f"padding: {S.btn_padding}; border: 2px solid #39FF14; "
            f"border-radius: {S.btn_radius}px;"
        )

        self.btn_start_game = QPushButton("\U0001f3ae START GAME")
        self.btn_start_game.setStyleSheet(
            f"QPushButton {{ background: rgba(57,255,20,0.3); border: 2px solid #39FF14; "
            f"color: white; {btn_base} min-width: {S.btn_min_w + 20}px; }}"
            "QPushButton:hover { background: rgba(57,255,20,0.5); }"
            "QPushButton:pressed { background: rgba(57,255,20,0.7); }" + btn_disabled
        )
        self.btn_start_game.clicked.connect(self._start_game)

        self.btn_unlock = QPushButton("\U0001f513 UNLOCK BUZZERS")
        self.btn_unlock.setStyleSheet(
            f"QPushButton {{ background: rgba(255,193,7,0.2); border: 2px solid #ffc107; "
            f"color: white; {btn_base} min-width: {S.btn_min_w + 20}px; }}"
            "QPushButton:hover { background: rgba(255,193,7,0.4); }"
            "QPushButton:pressed { background: rgba(255,193,7,0.6); }" + btn_disabled
        )
        self.btn_unlock.clicked.connect(self._unlock_buzzers)
        self.btn_unlock.setEnabled(False)
        self.btn_unlock.hide()

        self.btn_next = QPushButton("\u25b6\ufe0f NEXT QUESTION")
        self.btn_next.setStyleSheet(button_style)
        self.btn_next.clicked.connect(self._load_next_question)
        self.btn_next.setEnabled(False)
        self.btn_next.hide()

        self.btn_bonus = QPushButton("\u2b50 BONUS POINT")
        self.btn_bonus.setStyleSheet(
            f"QPushButton {{ background: rgba(255,215,0,0.2); border: 2px solid #ffd700; "
            f"color: #ffd700; {btn_base}}}"
            "QPushButton:hover { background: rgba(255,215,0,0.4); }"
            "QPushButton:pressed { background: rgba(255,215,0,0.6); }" + btn_disabled
        )
        self.btn_bonus.clicked.connect(self._award_bonus_point)

        self.btn_reset = QPushButton("\U0001f504 RESET GAME")
        self.btn_reset.setStyleSheet(button_style)
        self.btn_reset.clicked.connect(self._reset_game)

        self.help_btn = QPushButton("\u2139\ufe0f")
        self.help_btn.setFixedSize(S.help_btn_size, S.help_btn_size)
        self.help_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(52,152,219,0.3); border: 2px solid #3498db; "
            f"border-radius: {S.help_btn_radius}px; font-size: {S.help_btn_font}px; color: white; }}"
            "QPushButton:hover { background: rgba(52,152,219,0.5); }"
        )
        self.help_btn.clicked.connect(self._show_help)

        self.status_label = QLabel("Waiting for players...")
        self.status_label.setStyleSheet(
            f"font-size: {S.status_font}px; font-weight: 700; color: rgba(255,255,255,0.7); "
            "background: rgba(57,255,20,0.15); "
            f"padding: {S.btn_padding}; border: 2px solid rgba(57,255,20,0.3); "
            f"border-radius: {S.btn_radius}px;"
        )
        self.status_label.hide()

        control_layout.addWidget(self.phase_label)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch(1)
        control_layout.addWidget(self.btn_start_game)
        control_layout.addWidget(self.btn_unlock)
        control_layout.addWidget(self.btn_next)
        control_layout.addWidget(self.btn_bonus)
        control_layout.addWidget(self.btn_reset)
        control_layout.addWidget(self.help_btn)
        control_layout.addStretch(1)

        return control_panel

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
            root = os.path.dirname(root)  # ui
            root = os.path.dirname(root)  # app
            root = os.path.dirname(root)  # project root
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
        self.engine.nobody_buzzed.connect(self._on_nobody_buzzed)

        if hasattr(self.engine, "question_advanced"):
            self.engine.question_advanced.connect(self._on_engine_question_advanced)

    def _grey_out_all_cards(self):
        for card in self.player_cards.values():
            card.is_hardware_connected = False
            card.is_buzzed = False
            card.is_eliminated = False
            card._set_disconnected_icon()
            card.label.setText(f"P{card.player_id}: WAITING")
            card.label.setStyleSheet(card._label_style("rgba(100, 100, 100, 0.7)"))

    def _on_timer_changed_ui(self, remaining_ms: int):
        # Update timer widget for both question and answer phases.
        self.timer.set_remaining_ms(remaining_ms)

    def _connect_mqtt_callbacks(self):
        if not self.mqtt_backend:
            return
        self.mqtt_backend.on_buzz_callback = self._on_mqtt_buzz
        self.mqtt_backend.on_answer_callback = self._on_mqtt_answer
        self.mqtt_backend.on_player_connected_callback = self._on_player_connected
        self.mqtt_backend.on_player_disconnected_callback = self._on_player_disconnected

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
        q_list = getattr(self.engine, "questions", None) or getattr(
            self.engine, "_questions", None
        )
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

        # Seed the engine with whichever buzzers are already known to the MQTT
        # backend.  Any player that buzzes later will be auto-added in on_buzz().
        if self.mqtt_backend:
            known = self.mqtt_backend.get_connected_players()
            self.engine.register_game_players(known)
            print(f"[HOST] Game started with known players: {known}")
        else:
            # No MQTT — treat all four slots as active so cascading works in
            # local/demo mode.
            self.engine.register_game_players([1, 2, 3, 4])

        for player_card in self.player_cards.values():
            player_card.set_eliminated(False)
            player_card.highlight_locked(False)

        self.game_started = True

        self.btn_start_game.hide()
        self.btn_unlock.show()
        self.btn_next.show()
        self.status_label.show()

        self._update_round_badge()

        self.engine.start_question()
        self._prepare_current_question_ui()

        print("🎮 GAME STARTED (Q1)!")

    def _update_round_badge(self):
        if self.engine.cfg.rounds > 1:
            self.round_badge.setText(
                f"ROUND {self.current_round} / {self.engine.cfg.rounds}"
            )
            self.round_badge.show()
        else:
            self.round_badge.hide()

    def _load_prev_question(self):
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

        if self.engine.cfg.rounds > 1:
            qpr = self.engine.cfg.questions_per_round
            questions_answered = self.engine.current_q_idx + 1
            if questions_answered % qpr == 0 and questions_answered < len(
                self.engine.questions
            ):
                round_just_completed = questions_answered // qpr
                if round_just_completed < self.engine.cfg.rounds:
                    self._show_round_transition(
                        round_just_completed, round_just_completed + 1
                    )
                    return

        self.engine.next_question()

    def _reset_game(self):
        reply = QMessageBox.question(
            self,
            "Reset Game",
            "Are you sure you want to reset the game? All scores will be lost.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        if self.round_transition_screen.isVisible():
            self.round_transition_screen.fade_out(duration_ms=0)
        self.round_transition_screen.cleanup()
        self.round_transition_screen.hide()
        self.round_transition_screen.setWindowOpacity(1.0)

        if self.winner_screen.isVisible():
            self.winner_screen.fade_out(duration_ms=0)
        self.winner_screen.cleanup()
        self.winner_screen.hide()
        self.winner_screen.setWindowOpacity(1.0)

        self.game_started = False
        self.buzzers_unlocked = False
        self.current_round = 1

        self.engine.reset_game()

        if self.mqtt_backend:
            self.mqtt_backend.end_question()
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
        self.phase_label.setText(f"PHASE: {phase}")

        if phase == Phase.GAME_END.value:
            self.btn_unlock.setEnabled(False)
            self.btn_next.setEnabled(False)

        elif phase == Phase.SHOW_QUESTION.value:
            if self.game_started:
                self.btn_next.setEnabled(False)
                self.btn_next.setText("▶️ NEXT QUESTION")

        elif phase == Phase.BUZZED.value:
            if self.game_started:
                self.btn_unlock.setEnabled(False)
                self.btn_next.setEnabled(False)

        elif phase == Phase.IDLE.value:
            if self.game_started:
                attempted = set(getattr(self.engine, "players_attempted", set()))
                q_idx = self.engine.current_q_idx
                q_answered = q_idx in self.engine.answered_questions
                attempt_records = getattr(self.engine, "attempt_records", [])

                if len(attempted) == 0 and q_answered:
                    self.status_label.setText(
                        "⏰ Time's up! No one buzzed. Click NEXT to continue."
                    )
                elif q_answered and any(r.is_correct for r in attempt_records):
                    self.status_label.setText(
                        "✅ Question complete. Click NEXT to continue."
                    )
                else:
                    self.status_label.setText(
                        "❌ All attempts exhausted! Click NEXT to continue."
                    )

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

            self.status_label.setText(
                f"🛑 Player {buzzer_id} buzzed! Waiting for answer..."
            )
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(93, 219, 255, 1.0); "
                "background: rgba(93, 219, 255, 0.2); "
                "padding: 12px 20px; border: 2px solid #5ddbff; "
                "border-radius: 8px;"
            )

            if self.mqtt_backend and hasattr(self.mqtt_backend, "lock_player"):
                self.mqtt_backend.lock_player(buzzer_id)

        else:
            for card in self.player_cards.values():
                card.highlight_locked(False)

    def _on_attempt_failed(self, player_id: int, attempt_number: int):
        """Engine signals that an attempt ended in failure.

        This fires in two situations:
        1. _auto_judge_answer determined the answer was wrong  → guarded by
           _answer_judged_by_button so we only mark the card, no MQTT/SFX.
        2. The answer timer expired  → guarded by engine._answer_timed_out so
           we only mark the card; _on_nobody_buzzed (fired next) handles MQTT
           unlock and SFX.
        """
        if player_id in self.player_cards:
            self.player_cards[player_id].set_eliminated(True)

        # Both guard paths skip MQTT/SFX here to avoid double-firing.
        if self._answer_judged_by_button:
            return
        if getattr(self.engine, "_answer_timed_out", False):
            return

        # Fallback: shouldn't normally reach here, but handle safely.
        if self.mqtt_backend:
            self.mqtt_backend.mark_answer_wrong(player_id)
        self.sfx.play_wrong()

    # =========================================================================
    # MQTT EVENT HANDLERS
    # =========================================================================

    def _on_mqtt_buzz(self, buzz_event):
        if self.engine.phase != Phase.SHOW_QUESTION:
            print(f"🚫 Buzz ignored - engine phase is {self.engine.phase.value}")
            return

        player_id = buzz_event.player_id
        accepted = self.engine.on_buzz(
            player_id, buzz_event.timestamp_ms, buzz_event.server_received_ms
        )

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
        """A buzzer sent its first message — record it on the player card."""
        if player_id in self.player_cards:
            self.player_cards[player_id].set_connected(True)
        # If the game is already running, auto-add this player to the active set
        # so they can participate immediately (e.g. reconnected hardware).
        if self.game_started:
            self.engine.add_active_player(player_id)

    def _on_player_disconnected(self, player_id: int):
        """Visual-only: update card.  Active set is unchanged — player stays in game."""
        if player_id in self.player_cards:
            card = self.player_cards[player_id]
            card.highlight_locked(False)
            card.set_connected(False)

    def _on_nobody_buzzed(self, attempt_number: int):
        """Engine timer expired with no buzz — re-unlock buzzers for the new attempt.

        The engine has already restarted the question timer before emitting this
        signal, so we must NOT call start_or_resume_question_timer() here.
        """
        if self.mqtt_backend:
            self.mqtt_backend.unlock_buzzers()
        self.engine.notify_buzzers_unlocked()
        self.buzzers_unlocked = True
        self.btn_unlock.setEnabled(False)
        self.btn_unlock.setText("🔓 BUZZERS LIVE")
        self._warned_7 = False
        self._warned_3 = False
        self.status_label.setText(
            f"⏰ Nobody buzzed — Attempt {attempt_number} — buzzers re-unlocked!"
        )
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(255, 193, 7, 1.0); "
            "background: rgba(255, 193, 7, 0.2); "
            "padding: 12px 20px; border: 2px solid #ffc107; border-radius: 8px;"
        )

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
            self.status_label.setText(
                f"⚡ Attempt {attempt_number} - Remaining players: {remaining}"
            )

    def _unlock_buzzers(self):
        if not self.game_started:
            return

        if self.engine.phase != Phase.SHOW_QUESTION:
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

        self.status_label.setText("✅ Buzzers unlocked - waiting for fastest player.")
        self.status_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: rgba(57, 255, 20, 1.0); "
            "background: rgba(57, 255, 20, 0.2); "
            "padding: 12px 20px; border: 2px solid #39FF14; border-radius: 8px;"
        )

        if self.mqtt_backend:
            self.mqtt_backend.unlock_buzzers()

        self.engine.notify_buzzers_unlocked()
        self.engine.start_or_resume_question_timer()

    # =========================================================================
    # QUESTION SETUP
    # =========================================================================

    def _prepare_current_question_ui(self):
        self._warned_7 = False
        self._warned_3 = False
        self._grey_out_all_cards()

        self.buzzers_unlocked = False
        # btn_next is disabled here — only re-enabled once the question reaches
        # IDLE (all attempts exhausted / correct answer given).  This prevents
        # the host from accidentally skipping a question during setup.
        self.btn_next.setEnabled(False)
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

        self.status_label.setText("⏸️ Buzzers locked — click UNLOCK when ready")
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

        self.timer.reset()
        self._update_round_badge()

        if self.mqtt_backend:
            q = self.engine.current_question()
            self.mqtt_backend.start_question(
                question_id=q.id, max_attempts=q.max_attempts
            )

        self._render_question()
        self._render_scores()

    # =========================================================================
    # SHARED WRONG-ANSWER UI HELPER
    # =========================================================================

    def _handle_wrong_answer_ui(self, player_id: int) -> None:
        """Update UI after a wrong answer judged by the hardware button.

        Called only from _auto_judge_answer (button-judged path).
        Timer-expiry wrong answers go through _on_nobody_buzzed instead.
        """
        remaining_players = self.engine.get_players_remaining()
        try:
            question = self.engine.current_question()
            can_continue = (
                self.engine.current_attempt_number <= question.max_attempts
                and len(remaining_players) > 0
            )
        except Exception:
            can_continue = False

        if can_continue:
            self.buzzers_unlocked = True
            self._warned_7 = False
            self._warned_3 = False
            self.btn_unlock.setText("✅ BUZZERS ACTIVE")
            self.btn_unlock.setEnabled(False)
            self.btn_unlock.setStyleSheet(
                "QPushButton { "
                "background: rgba(255, 193, 7, 0.2); "
                "border: 3px solid #ffc107; border-radius: 8px; "
                "padding: 12px 20px; font-size: 14px; font-weight: 900; "
                "color: white; min-width: 150px; }"
                "QPushButton:hover { background: rgba(255, 193, 7, 0.4); }"
                "QPushButton:pressed { background: rgba(255, 193, 7, 0.6); }"
            )
            self.status_label.setText(
                f"❌ Player {player_id} WRONG! Next player can buzz now!"
            )
            self.status_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 18px 28px; border: 3px solid #e74c3c; border-radius: 10px;"
            )
            if self.mqtt_backend:
                self.mqtt_backend.unlock_buzzers()
            self.engine.notify_buzzers_unlocked()
            # The engine has already transitioned to SHOW_QUESTION and left the
            # timer wherever it was (or reset it if reset_timer_each_attempt).
            # We just restart it from whatever _question_remaining_ms holds.
            self.engine.start_or_resume_question_timer()
            self.sfx.play_start()
        else:
            self.buzzers_unlocked = False
            self.btn_next.setEnabled(True)
            self.btn_next.setText("▶️ NEXT QUESTION")
            self.btn_unlock.setEnabled(False)
            self.status_label.setText(
                "❌ All attempts exhausted! Click NEXT to continue."
            )
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(231, 76, 60, 1.0); "
                "background: rgba(231, 76, 60, 0.2); "
                "padding: 12px 20px; border: 2px solid #e74c3c; border-radius: 8px;"
            )

    # =========================================================================
    # AUTO JUDGING
    # =========================================================================

    def _auto_judge_answer(self, player_id: int, answer: str):
        answer_map = {"A": 0, "B": 1, "C": 2, "D": 3}
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
        is_correct = selected_index == question.correct_index

        print(f"   Selected: {selected_index} ({question.options[selected_index]})")
        print(
            f"   Correct:  {question.correct_index} ({question.options[question.correct_index]})"
        )
        print(f"   Result:   {'✅ CORRECT' if is_correct else '❌ WRONG'}")

        # Guard prevents _on_attempt_failed from duplicating MQTT/SFX calls.
        self._answer_judged_by_button = True
        try:
            self.engine.apply_answer(is_correct, player_id)
        finally:
            self._answer_judged_by_button = False

        if is_correct:
            self.sfx.play_correct()
            self.sfx.play_point()
            self.correct_flash.flash_green("✅ CORRECT!")
            self.options.mark_option_correct(answer)

            self.status_label.setText(
                f"✅ Player {player_id} CORRECT! Click NEXT to continue."
            )
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: rgba(57, 255, 20, 1.0); "
                "background: rgba(57, 255, 20, 0.2); "
                "padding: 12px 20px; border: 2px solid #39FF14; border-radius: 8px;"
            )

            if self.mqtt_backend:
                self.mqtt_backend.mark_answer_correct(player_id)

            self.btn_next.setEnabled(True)
            self.btn_next.setText("▶️ NEXT QUESTION")
            self.btn_unlock.setEnabled(False)
            return

        # WRONG answer ─────────────────────────────────────────────────────
        self.sfx.play_wrong()
        self.correct_flash.flash_red(f"❌ P{player_id} WRONG!")
        self.options.mark_option_eliminated(answer)

        # MQTT wrong-mark happens here (single call site for hardware-judged
        # answers).  _on_attempt_failed is guarded and will not duplicate.
        if self.mqtt_backend:
            self.mqtt_backend.mark_answer_wrong(player_id)

        self._handle_wrong_answer_ui(player_id)

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
        self.round_transition_screen.btn_continue.setEnabled(True)
        self.round_transition_screen.show()
        self.round_transition_screen.fade_in(duration_ms=400)
        self.round_transition_screen.start_auto_countdown(seconds=15)

    def _finish_show_round_transition(self):
        pass  # no longer used — kept as no-op for safety

    def _continue_to_next_round(self):
        self.round_transition_screen.btn_continue.setEnabled(False)
        self.round_transition_screen.stop_auto_countdown()
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
        winner_id = self.engine.scores.get_winner()

        if winner_id is None:
            # Tie — show the winner screen in "tie" mode; let WinnerScreen decide
            # how to display it.  Fall back to the top-ranked player only if the
            # ranking is somehow empty (shouldn't happen in practice).
            winner_id = ranking[0][0] if ranking else 1
            is_tie = True
        else:
            is_tie = False

        scores_dict = dict(ranking)

        # Pass is_tie if WinnerScreen supports it; otherwise fall back gracefully.
        if hasattr(self.winner_screen, "set_results"):
            try:
                self.winner_screen.set_results(
                    scores=scores_dict, winner_id=winner_id, is_tie=is_tie
                )
            except TypeError:
                # Older WinnerScreen without is_tie parameter
                self.winner_screen.set_results(scores=scores_dict, winner_id=winner_id)

        self.winner_screen.show()
        self.winner_screen.fade_in(duration_ms=500)

    def _finish_show_winner_screen(self):
        pass  # no longer used

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
        if not self.game_started:
            return

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
            btn = QPushButton(
                f"Player {player_id} - Current Score: {current_score} pts"
            )
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
            btn.clicked.connect(
                lambda checked, pid=player_id: self._apply_bonus_point(pid, dialog)
            )
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
        if hasattr(self.engine, "award_bonus"):
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
