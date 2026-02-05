from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QGroupBox, QFrame, QGridLayout
)
from PySide6.QtGui import QFont

from app.core.engine import GameEngine
from app.ui.widgets.scoreboard import ScoreboardWidget
from app.ui.widgets.timer_widget import TimerWidget
from app.ui.widgets.options_view import OptionsView
from app.ui.widgets.media_view import MediaView


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
        
        # Team colors for each player
        self.team_colors = {
            1: "#e74c3c",  # Red
            2: "#3498db",  # Blue
            3: "#2ecc71",  # Green
            4: "#f39c12",  # Orange
        }
        self.color = self.team_colors.get(player_id, "#888888")
        
        self.setFixedSize(150, 180)
        self.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )
        
        # Icon circle (speedometer or hand based on state)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(100, 100)
        self._set_idle_icon()
        
        # Player label with score
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
        # Speedometer/gauge icon with team color
        self.icon.setStyleSheet(
            f"QLabel {{ "
            f"background: transparent; "
            f"border: 4px solid {self.color}; "
            f"border-radius: 50px; "
            f"color: {self.color}; "
            f"font-size: 48px; "
            f"}}"
        )
        self.icon.setText("◠")  # Gauge arc symbol
    
    def _set_buzzed_icon(self):
        # Hand icon with cyan glow for buzzed state
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
        self.label.setText(f"P{self.player_id}{buzzed_text} {int(value)}pts")
        
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
        pass  # Visual already handled by icon state
    
    def highlight_locked(self, locked: bool):
        self.is_buzzed = locked
        if locked:
            self._set_buzzed_icon()
        else:
            self._set_idle_icon()
        # Update label
        score_text = self.label.text()
        score = 0
        try:
            score = int(score_text.split("pts")[0].split()[-1])
        except:
            pass
        self.set_score(score)


class HostScreen(QWidget):
    def __init__(self, engine: GameEngine, buzzer):
        super().__init__()
        self.engine = engine
        self.buzzer = buzzer

        # Dark navy background exactly like reference
        self.setStyleSheet(
            "QWidget { background: #0d1b2a; }"
        )

        # Main layout
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # ---- Game Area Grid (3x3 with corners for players) ----
        game_grid = QGridLayout()
        game_grid.setHorizontalSpacing(20)
        game_grid.setVerticalSpacing(15)
        
        # Create 4 corner player cards
        self.player_cards = {}
        
        # Top-left (P1)
        self.player_cards[1] = CornerPlayerCard(1)
        game_grid.addWidget(self.player_cards[1], 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft)
        
        # Top-right (P2)
        self.player_cards[2] = CornerPlayerCard(2)
        game_grid.addWidget(self.player_cards[2], 0, 2, alignment=Qt.AlignTop | Qt.AlignRight)
        
        # Bottom-left (P3)
        self.player_cards[3] = CornerPlayerCard(3)
        game_grid.addWidget(self.player_cards[3], 2, 0, alignment=Qt.AlignBottom | Qt.AlignLeft)
        
        # Bottom-right (P4)
        self.player_cards[4] = CornerPlayerCard(4)
        game_grid.addWidget(self.player_cards[4], 2, 2, alignment=Qt.AlignBottom | Qt.AlignRight)
        
        # ---- Center Column (Timer + Media + Question + Options) ----
        center_widget = QWidget()
        center_widget.setStyleSheet("QWidget { background: transparent; }")
        center_widget.setMaximumWidth(900)  # Constrain max width
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(20)
        center_layout.setContentsMargins(120, 0, 120, 0)  # Much larger margins
        
        # Timer at the very top (circular, centered)
        self.timer = TimerWidget()
        center_layout.addWidget(self.timer, alignment=Qt.AlignCenter)
        
        # Media display (16:9 rounded rectangle with green border)
        self.media = MediaView()
        center_layout.addWidget(self.media)
        
        # Question text box (dark with green border)
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
        
        # Options grid (2x2)
        self.options = OptionsView()
        center_layout.addWidget(self.options)
        
        # Add center to middle of game grid
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
        
        # Phase indicator
        self.phase = QLabel("PHASE: IDLE")
        self.phase.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: white; "
            "background: rgba(57, 255, 20, 0.2); padding: 12px 20px; "
            "border: 2px solid #39FF14; border-radius: 8px;"
        )
        
        # Buttons
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
        
        # Simulator
        sim_group = QGroupBox("🎮 SIMULATE")
        sim_group.setStyleSheet(
            "QGroupBox { "
            "font-weight: 700; color: white; font-size: 12px; "
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
        self.btn_start.clicked.connect(self._start_question)
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
        
        # Buzzer connections
        if hasattr(self.buzzer, "connected"):
            self.buzzer.connected.connect(self._on_buzzer_connected)
        if hasattr(self.buzzer, "buzz"):
            self.buzzer.buzz.connect(self._on_buzz)
        
        # Initial render
        self._render_question()
        self._render_scores()
        self._on_phase(self.engine.phase.value)
    
    def _show_admin_help(self):
        QMessageBox.information(self, "Admin Dashboard", ADMIN_TOOLTIP)
    
    def _start_question(self):
        self.engine.start_question()
        if hasattr(self.buzzer, "reset_all"):
            self.buzzer.reset_all()
    
    def _next_question(self):
        if hasattr(self.buzzer, "reset_all"):
            self.buzzer.reset_all()
        self.engine.next_question()
    
    def _reset_buzzers(self):
        if hasattr(self.buzzer, "reset_all"):
            self.buzzer.reset_all()
        self.engine.reset_buzzers_only()
    
    def _judge(self, is_correct: bool):
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
    
    def _render_question(self):
        q = self.engine.current_question()
        
        # Dynamic display based on media presence
        if q.media.type.value == "none":
            # Question only - show question, hide media
            self.question.show()
            self.question.setText(q.text)
            self.media.hide()
        else:
            # Media question - show media, hide question text
            self.question.hide()
            self.media.show()
            self.media.show_path(q.media.type.value, q.media.path or "")
        
        # Always show options
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
        if won and hasattr(self.buzzer, "lock_all"):
            self.buzzer.lock_all()