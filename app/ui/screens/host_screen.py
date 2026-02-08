from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QGroupBox, QFrame, QGridLayout
)
from pathlib import Path

from app.core.engine import GameEngine
from app.core.state import Phase  # ✅ FIX: use Phase enum consistently
from app.core.sound_manager import create_sound_manager  # ✅ NEW: sound manager

from app.ui.widgets.timer_widget import TimerWidget
from app.ui.widgets.options_view import OptionsView
from app.ui.widgets.media_view import MediaView
from app.ui.widgets.cascading_widget import CascadingAttemptsWidget


ADMIN_TOOLTIP = (
    "Admin Dashboard (planned):\n"
    "• Control game rounds + questions per round\n"
    "• Select a question pack folder\n"
    "• Add/edit questions (text + image/audio/video + options)\n"
    "• Reorder questions or enable shuffle\n"
    "• Control scoring rules\n"
    "• Start/stop/reset buzzers\n"
)


class CornerPlayerCard(QFrame):
    """Player card exactly like reference image"""
    def __init__(self, player_id: int):
        super().__init__()
        self.player_id = player_id
        self.is_buzzed = False
        self.is_hardware_connected = False

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
        self._set_idle_icon()

        self.label = QLabel(f"P{player_id}: 0pts")
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

    def _set_idle_icon(self):
        border_color = self.color if not self.is_hardware_connected else "#2ecc71"
        self.icon.setStyleSheet(
            f"QLabel {{ "
            f"background: transparent; "
            f"border: 4px solid {border_color}; "
            f"border-radius: 50px; "
            f"color: {border_color}; "
            f"font-size: 48px; "
            f"}}"
        )
        self.icon.setText("◠")

    def _set_buzzed_icon(self):
        self.icon.setStyleSheet(
            "QLabel { "
            "background: rgba(100, 200, 255, 0.2); "
            "border: 5px solid #5ddbff; "
            "border-radius: 50px; "
            "color: #5ddbff; "
            "font-size: 52px; "
            "}"
        )
        self.icon.setText("✋")

    def set_score(self, value: int):
        buzzed_text = ": BUZZED IN!" if self.is_buzzed else ""
        hw_indicator = " 🟢" if self.is_hardware_connected else ""
        self.label.setText(f"P{self.player_id}{buzzed_text} {int(value)}pts{hw_indicator}")

        if self.is_buzzed:
            self.label.setStyleSheet(
                "font-size: 13px; font-weight: 900; color: white; "
                "background: rgba(93, 219, 255, 0.8); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            self.label.setStyleSheet(
                "font-size: 14px; font-weight: 900; color: white; "
                "background: rgba(100, 100, 100, 0.7); "
                "padding: 8px 12px; border-radius: 8px;"
            )

    def set_connected(self, is_connected: bool):
        self.is_hardware_connected = is_connected
        if not self.is_buzzed:
            self._set_idle_icon()

        score_text = self.label.text()
        score = 0
        try:
            parts = score_text.split("pts")[0].split()[-1]
            score = int(parts)
        except Exception:
            pass
        self.set_score(score)

    def highlight_locked(self, locked: bool):
        self.is_buzzed = locked
        if locked:
            self._set_buzzed_icon()
        else:
            self._set_idle_icon()

        score_text = self.label.text()
        score = 0
        try:
            score = int(score_text.split("pts")[0].split()[-1])
        except Exception:
            pass
        self.set_score(score)


class HostScreen(QWidget):
    def __init__(self, engine: GameEngine, buzzer):
        super().__init__()
        self.engine = engine
        self.buzzer = buzzer

        # IMPORTANT: Enable keyboard focus for remote control
        self.setFocusPolicy(Qt.StrongFocus)

        # Dark navy background
        self.setStyleSheet("QWidget { background: #0d1b2a; }")

        # =========================
        # SOUND EFFECTS (SFX)
        # =========================
        self.sfx = create_sound_manager()
        self._warned_7 = False
        self._warned_3 = False

        # Main layout
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # ---- Game Area Grid ----
        game_grid = QGridLayout()
        game_grid.setHorizontalSpacing(20)
        game_grid.setVerticalSpacing(15)

        # Player cards
        self.player_cards = {}

        # Left column (P1, Cascading, P3)
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

        # Right column (P2, P4)
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

        # Center column (Timer + Media + Question + Options)
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

        self.question = QLabel("Which player is making this run?")
        self.question.setWordWrap(True)
        self.question.setAlignment(Qt.AlignCenter)
        self.question.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: white; "
            "padding: 20px 30px; "
            "background: transparent; "
            "border: 3px solid #39FF14; "
            "border-radius: 12px; "
            "min-height: 60px;"
        )
        center_layout.addWidget(self.question)

        self.options = OptionsView()
        center_layout.addWidget(self.options)

        game_grid.addWidget(center_widget, 0, 1, 3, 1)
        game_grid.setRowStretch(0, 1)
        game_grid.setRowStretch(1, 2)
        game_grid.setRowStretch(2, 1)
        game_grid.setColumnStretch(0, 0)
        game_grid.setColumnStretch(1, 1)
        game_grid.setColumnStretch(2, 0)

        root.addLayout(game_grid, stretch=1)

        # ---- Control Panel (Bottom) ----
        controls_frame = QFrame()
        controls_frame.setFixedHeight(100)
        controls_frame.setStyleSheet(
            "QFrame { "
            "background: rgba(20, 40, 60, 0.7); "
            "border-top: 2px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 0px; "
            "}"
        )

        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(20, 20, 20, 20)
        controls_layout.setSpacing(15)

        self.phase = QLabel("PHASE: IDLE")
        self.phase.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: white; "
            "background: rgba(57, 255, 20, 0.2); padding: 12px 20px; "
            "border: 2px solid #39FF14; border-radius: 8px;"
        )

        self.btn_start = QPushButton("▶ START")
        self.btn_next = QPushButton("⏭ NEXT")
        self.btn_reset = QPushButton("🔄 RESET")
        self.btn_correct = QPushButton("✅ CORRECT")
        self.btn_wrong = QPushButton("❌ WRONG")
        self.help_btn = QPushButton("ℹ")

        button_style = (
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.15); "
            "border: 2px solid #39FF14; "
            "border-radius: 8px; "
            "padding: 12px 20px; "
            "font-weight: 900; "
            "font-size: 13px; "
            "color: white; "
            "min-width: 80px; "
            "}"
            "QPushButton:hover { background: rgba(57, 255, 20, 0.3); }"
            "QPushButton:pressed { background: rgba(57, 255, 20, 0.5); }"
        )

        for btn in (self.btn_start, self.btn_next, self.btn_reset):
            btn.setStyleSheet(button_style)
            btn.setMinimumHeight(50)

        self.btn_correct.setStyleSheet(button_style.replace("#39FF14", "#2ecc71"))
        self.btn_correct.setMinimumHeight(50)

        self.btn_wrong.setStyleSheet(button_style.replace("#39FF14", "#e74c3c"))
        self.btn_wrong.setMinimumHeight(50)

        self.help_btn.setFixedSize(50, 50)
        self.help_btn.setStyleSheet(button_style)
        self.help_btn.setToolTip(ADMIN_TOOLTIP)
        self.help_btn.clicked.connect(self._show_admin_help)

        controls_layout.addWidget(self.help_btn)
        controls_layout.addWidget(self.phase)
        controls_layout.addWidget(self.btn_start)
        controls_layout.addWidget(self.btn_next)
        controls_layout.addWidget(self.btn_reset)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.btn_correct)
        controls_layout.addWidget(self.btn_wrong)

        # Hardware control group
        hardware_group = QGroupBox("🔌 HW")
        hardware_group.setStyleSheet(
            "QGroupBox { "
            "font-weight: 900; color: white; font-size: 11px; "
            "background: transparent; border: 2px solid rgba(57, 255, 20, 0.5); "
            "border-radius: 8px; margin-top: 8px; padding-top: 12px; "
            "}"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }"
        )
        hardware_layout = QVBoxLayout(hardware_group)
        hardware_layout.setSpacing(4)
        hardware_layout.setContentsMargins(8, 8, 8, 8)

        self.btn_hardware = QPushButton("Enable")
        self.btn_hardware.setCheckable(True)
        self.btn_hardware.setFixedHeight(35)
        self.btn_hardware.setStyleSheet(
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.2); "
            "border: 2px solid #39FF14; "
            "border-radius: 6px; "
            "padding: 6px 10px; "
            "font-size: 11px; "
            "font-weight: 900; "
            "color: white; "
            "}"
            "QPushButton:checked { "
            "background: #39FF14; "
            "color: black; "
            "}"
            "QPushButton:hover { background: rgba(57, 255, 20, 0.4); }"
        )
        self.btn_hardware.clicked.connect(self._toggle_hardware)

        self.hardware_status = QLabel("●OFF")
        self.hardware_status.setStyleSheet(
            "font-size: 9px; color: rgba(255, 255, 255, 0.5); font-weight: 700;"
        )
        self.hardware_status.setAlignment(Qt.AlignCenter)

        hardware_layout.addWidget(self.btn_hardware)
        hardware_layout.addWidget(self.hardware_status)
        controls_layout.addWidget(hardware_group)

        # Simulator
        sim_group = QGroupBox("🎮 SIM")
        sim_group.setStyleSheet(
            "QGroupBox { "
            "font-weight: 900; color: white; font-size: 11px; "
            "background: transparent; border: 2px solid #39FF14; "
            "border-radius: 8px; margin-top: 8px; padding-top: 12px; "
            "}"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }"
        )
        sim_row = QHBoxLayout(sim_group)
        sim_row.setSpacing(6)

        self.sim_buttons = {}
        colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12"]
        for i, pid in enumerate((1, 2, 3, 4)):
            btn = QPushButton(f"P{pid}")
            btn.setFixedSize(50, 35)
            btn.setStyleSheet(
                f"QPushButton {{ background: {colors[i]}; border: 2px solid white; "
                f"border-radius: 6px; font-weight: 900; color: white; font-size: 12px; }}"
            )
            btn.clicked.connect(lambda _, p=pid: self._simulate_buzz(p))
            sim_row.addWidget(btn)
            self.sim_buttons[pid] = btn

        controls_layout.addWidget(sim_group)
        root.addWidget(controls_frame)

        # Wire buttons
        self.btn_start.clicked.connect(self.start_question)
        self.btn_next.clicked.connect(self._next_question)
        self.btn_reset.clicked.connect(self._reset_buzzers)
        self.btn_correct.clicked.connect(lambda: self._judge(True))
        self.btn_wrong.clicked.connect(lambda: self._judge(False))

        # Engine connections
        self.engine.phase_changed.connect(self._on_phase)
        self.engine.timer_changed.connect(self.timer.set_remaining_ms)
        self.engine.question_changed.connect(self._render_question)
        self.engine.lock_changed.connect(self._on_lock)
        self.engine.scores_changed.connect(self._render_scores)

        # Cascading attempts connections
        self.engine.attempt_changed.connect(self._on_attempt_changed)
        self.engine.attempt_failed.connect(self._on_attempt_failed)

        # ✅ Show engine errors as on-screen feedback
        if hasattr(self.engine, "error_occurred"):
            self.engine.error_occurred.connect(self._show_remote_feedback)

        # ✅ Timer warning SFX
        self.engine.timer_changed.connect(self._sfx_on_timer_changed)

        # Hardware status connection
        if hasattr(self.engine, 'hardware_status_changed'):
            self.engine.hardware_status_changed.connect(self._on_hardware_status_changed)

        # Buzzer connections
        if hasattr(self.buzzer, "connected"):
            self.buzzer.connected.connect(self._on_buzzer_connected)
        if hasattr(self.buzzer, "buzz"):
            self.buzzer.buzz.connect(self._on_buzz)

        # Timer to update hardware players
        self.hardware_timer = QTimer()
        self.hardware_timer.timeout.connect(self._update_hardware_players)
        self.hardware_timer.start(3000)

        # Initial render
        self._render_question()
        self._render_scores()
        self._on_phase(self.engine.phase.value)

    # ========================================================================
    # HARDWARE INTEGRATION
    # ========================================================================

    def _toggle_hardware(self):
        if self.btn_hardware.isChecked():
            if self.engine.enable_hardware_buzzers():
                self.btn_hardware.setText("ON")
                self.hardware_status.setText("●ON")
                self.hardware_status.setStyleSheet(
                    "font-size: 9px; color: #2ecc71; font-weight: 900;"
                )
                self._update_hardware_players()

                connected = self.engine.get_connected_hardware_players()
                if connected:
                    QMessageBox.information(
                        self, "Hardware Enabled",
                        f"✓ ESP32 buzzers connected!\n\n"
                        f"Players online: {', '.join(map(str, connected))}"
                    )
                else:
                    QMessageBox.information(
                        self, "Hardware Enabled",
                        "✓ Connected to MQTT broker\n\n"
                        "Waiting for ESP32 players to connect...\n"
                        "Press buzzer buttons to register players."
                    )
            else:
                self.btn_hardware.setChecked(False)
                QMessageBox.warning(
                    self, "Hardware Connection Failed",
                    "Could not connect to ESP32 buzzers.\n\n"
                    "Checklist:\n"
                    "✓ MQTT broker running: sudo systemctl status mosquitto\n"
                    "✓ ESP32s powered on and connected to WiFi\n"
                    "✓ Broker address: 192.168.10.10\n"
                    "✓ Python package installed: pip install paho-mqtt"
                )
        else:
            self.engine.disable_hardware_buzzers()
            self.btn_hardware.setText("Enable")
            self.hardware_status.setText("●OFF")
            self.hardware_status.setStyleSheet(
                "font-size: 9px; color: rgba(255, 255, 255, 0.5); font-weight: 700;"
            )
            self._clear_hardware_indicators()

    def _update_hardware_players(self):
        if self.engine.is_hardware_enabled():
            connected = self.engine.get_connected_hardware_players()
            for player_id in [1, 2, 3, 4]:
                if player_id in self.player_cards:
                    self.player_cards[player_id].set_connected(player_id in connected)

    def _clear_hardware_indicators(self):
        for player_id in [1, 2, 3, 4]:
            if player_id in self.player_cards:
                self.player_cards[player_id].set_connected(False)

    def _on_hardware_status_changed(self, connected: bool):
        if not connected:
            self.btn_hardware.setChecked(False)
            self.btn_hardware.setText("Enable")
            self.hardware_status.setText("●OFF")
            self.hardware_status.setStyleSheet(
                "font-size: 9px; color: rgba(255, 255, 255, 0.5); font-weight: 700;"
            )
            self._clear_hardware_indicators()
            QMessageBox.warning(
                self, "Hardware Disconnected",
                "Lost connection to MQTT broker.\n"
                "Hardware buzzers have been disabled."
            )

    # ========================================================================
    # CORE ACTIONS
    # ========================================================================

    def _show_admin_help(self):
        QMessageBox.information(self, "Admin Dashboard", ADMIN_TOOLTIP)

    def start_question(self):
        # ✅ reset warnings each question
        self._warned_7 = False
        self._warned_3 = False

        self.sfx.play_start()
        self.cascading_widget.reset()

        self.engine.start_question()
        if hasattr(self.buzzer, "reset_all"):
            self.buzzer.reset_all()

    def _next_question(self):
        self.sfx.play_next()

        if hasattr(self.media, 'cleanup'):
            self.media.cleanup()

        if hasattr(self.buzzer, "reset_all"):
            self.buzzer.reset_all()
        self.engine.next_question()

    def _reset_buzzers(self):
        if hasattr(self.buzzer, "reset_all"):
            self.buzzer.reset_all()
        self.engine.reset_buzzers_only()

    def _judge(self, is_correct: bool):
        # ✅ instant feedback sounds
        if is_correct:
            self.sfx.play_correct()
            self.sfx.play_point()
        else:
            self.sfx.play_wrong()

        self.engine.apply_answer(is_correct)
        if hasattr(self.buzzer, "reset_all"):
            self.buzzer.reset_all()

    def _simulate_buzz(self, player_id: int):
        if hasattr(self.buzzer, "simulate_buzz"):
            self.buzzer.simulate_buzz(player_id)

    def _on_phase(self, phase: str):
        self.phase.setText(f"PHASE: {phase.upper()}")

    def _on_lock(self, locked_id):
        for pid, card in self.player_cards.items():
            card.highlight_locked(locked_id == pid)

    def _on_attempt_changed(self, attempt_number: int):
        # ✅ reset warnings each attempt
        self._warned_7 = False
        self._warned_3 = False

        points = self.engine.get_points_for_current_attempt()
        remaining = self.engine.get_players_remaining()
        self.cascading_widget.update_attempt(attempt_number, points, remaining)

    def _on_attempt_failed(self, player_id: int, attempt_number: int):
        self.cascading_widget.show_attempt_failed(player_id)

    def _render_question(self):
        q = self.engine.current_question()

        if q.media.type.value == "none":
            self.question.show()
            self.question.setText(q.text)
            self.media.hide()
        else:
            self.question.hide()
            self.media.show()

            if hasattr(self.engine, 'cfg') and hasattr(self.engine.cfg, 'pack_dir'):
                media_path = self.engine.cfg.pack_dir / q.media.path
            else:
                media_path = Path(q.media.path)

            if not media_path.exists():
                self.media.show_path(q.media.type.value, q.media.path or "")
            else:
                if q.media.type.value == "image":
                    self.media.show_image(str(media_path))
                elif q.media.type.value == "video":
                    self.media.show_video(str(media_path))
                elif q.media.type.value == "audio":
                    self.media.show_audio(str(media_path))
                else:
                    self.media.show_path(q.media.type.value, q.media.path or "")

        self.options.set_options(q.options)

    def _render_scores(self):
        for pid, score in self.engine.scores.scores.items():
            if pid in self.player_cards:
                self.player_cards[pid].set_score(score)

    def _on_buzzer_connected(self, buzzer_id: int, is_connected: bool):
        if buzzer_id in self.player_cards:
            self.player_cards[buzzer_id].set_connected(is_connected)

    def _on_buzz(self, buzzer_id: int, t_ms: int, received_ms: int):
        won = self.engine.on_buzz(buzzer_id, t_ms, received_ms)
        if won:
            self.sfx.play_buzz()
            if hasattr(self.buzzer, "lock_all"):
                self.buzzer.lock_all()

    # ========================================================================
    # TIMER WARNING SFX
    # ========================================================================

    def _sfx_on_timer_changed(self, remaining_ms: int):
        # 7 seconds warning (once)
        if remaining_ms <= 7000 and not self._warned_7 and remaining_ms > 3000:
            self._warned_7 = True
            self.sfx.play_timer_warning()

        # 3 seconds critical (once)
        if remaining_ms <= 3000 and not self._warned_3 and remaining_ms > 0:
            self._warned_3 = True
            self.sfx.play_timer_critical()

    # ========================================================================
    # REMOTE CONTROL SUPPORT (✅ FIXED USING Phase ENUM)
    # ========================================================================

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._handle_remote_ok()
        elif key == Qt.Key_Right:
            self._handle_remote_next()
        elif key == Qt.Key_Left:
            self._handle_remote_previous()
        elif key == Qt.Key_Up:
            self._handle_remote_correct()
        elif key == Qt.Key_Down:
            self._handle_remote_wrong()
        elif key == Qt.Key_Space:
            self._handle_remote_reset()
        elif key == Qt.Key_Escape:
            self._toggle_hardware()
        else:
            super().keyPressEvent(event)

    def _handle_remote_ok(self):
        """
        OK/ENTER:
        - IDLE -> start question
        - SHOW_QUESTION -> reset buzzers only (re-open)
        - BUZZED -> must judge first
        """
        phase = self.engine.phase

        if phase == Phase.IDLE:
            self.start_question()
        elif phase == Phase.SHOW_QUESTION:
            self._reset_buzzers()
        elif phase == Phase.BUZZED:
            self._show_remote_feedback("Player locked — judge first")
        else:
            self._show_remote_feedback(f"Phase: {phase.value}")

    def _handle_remote_next(self):
        self.btn_next.animateClick()

    def _handle_remote_previous(self):
        # Safe previous: move index back and restart cleanly
        if hasattr(self.engine, "current_q_idx") and self.engine.current_q_idx > 0:
            self.engine.current_q_idx -= 1
            self.start_question()
        else:
            self._show_remote_feedback("Already first question")

    def _handle_remote_correct(self):
        if self.engine.phase == Phase.BUZZED:
            self.btn_correct.animateClick()
        else:
            self._show_remote_feedback("No player to judge")

    def _handle_remote_wrong(self):
        if self.engine.phase == Phase.BUZZED:
            self.btn_wrong.animateClick()
        else:
            self._show_remote_feedback("No player to judge")

    def _handle_remote_reset(self):
        self.btn_reset.animateClick()

    def _show_remote_feedback(self, message: str):
        original_text = self.phase.text()
        original_style = self.phase.styleSheet()

        self.phase.setText(message)
        self.phase.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: white; "
            "background: rgba(255, 100, 100, 0.8); padding: 12px 20px; "
            "border: 2px solid #ff6b6b; border-radius: 8px;"
        )

        QTimer.singleShot(1500, lambda: self.phase.setText(original_text))
        QTimer.singleShot(1500, lambda: self.phase.setStyleSheet(original_style))
