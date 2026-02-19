from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QFrame, QSpinBox, QLineEdit,
    QTextEdit, QComboBox, QFileDialog, QMessageBox, QListWidget,
    QListWidgetItem, QGroupBox, QFormLayout, QCheckBox, QTabWidget,
    QSplitter
)
from PySide6.QtGui import QPixmap

from app.core.models import Question, Media, GameConfig
from app.core.loaders import save_pack, validate_pack
from app.constants import MediaType


class QuestionListItem(QFrame):
    """Question list item with enabled/disabled checkbox"""
    edit_clicked      = Signal(str)
    delete_clicked    = Signal(str)
    duplicate_clicked = Signal(str)
    toggle_clicked    = Signal(str, bool)   # (question_id, is_enabled)

    def __init__(self, question: Question, index: int, enabled: bool = True):
        super().__init__()
        self.question = question
        self.index    = index
        self._enabled = enabled
        self._apply_frame_style()

        layout = QHBoxLayout(self)
        layout.setSpacing(10)

        # ── Include checkbox ─────────────────────────────────────
        self.chk_include = QCheckBox()
        self.chk_include.setChecked(self._enabled)
        self.chk_include.setToolTip("Include this question in the game")
        self.chk_include.setFixedWidth(24)
        self.chk_include.setStyleSheet(
            "QCheckBox { background: transparent; border: none; }"
            "QCheckBox::indicator { width: 20px; height: 20px; border-radius: 4px; }"
            "QCheckBox::indicator:unchecked {"
            "  background: rgba(80,80,80,0.4); border: 2px solid #666; }"
            "QCheckBox::indicator:checked {"
            "  background: #39FF14; border: 2px solid #39FF14; image: none; }"
        )
        self.chk_include.stateChanged.connect(self._on_toggle)

        # Question number
        num_label = QLabel(f"#{index + 1}")
        num_label.setFixedWidth(40)
        num_label.setStyleSheet(
            "font-size: 16px; font-weight: 900; color: #39FF14; "
            "background: transparent; border: none;"
        )
        
        # Question info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        # Question text (truncated)
        text_label = QLabel(question.text[:60] + "..." if len(question.text) > 60 else question.text)
        text_label.setWordWrap(False)
        text_label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: white; "
            "background: transparent; border: none;"
        )
        
        # Metadata row
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(15)
        
        round_label = QLabel(f"Round {question.round}")
        round_label.setStyleSheet(
            "font-size: 10px; color: rgba(255, 255, 255, 0.6); "
            "background: transparent; border: none;"
        )
        
        media_label = QLabel(f"📎 {question.media.type.value.upper()}")
        media_label.setStyleSheet(
            "font-size: 10px; color: rgba(255, 255, 255, 0.6); "
            "background: transparent; border: none;"
        )
        
        difficulty_color = {
            "easy": "#2ecc71",
            "medium": "#f39c12",
            "hard": "#e74c3c"
        }.get(question.difficulty, "#888")
        
        diff_label = QLabel(f"● {question.difficulty.upper()}")
        diff_label.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {difficulty_color}; "
            f"background: transparent; border: none;"
        )
        
        # FIXED: Use first attempt points
        points = getattr(question, 'points_first_attempt', getattr(question, 'points', 1))
        points_label = QLabel(f"⭐ {points} pts")
        points_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #ffd700; "
            "background: transparent; border: none;"
        )
        
        meta_layout.addWidget(round_label)
        meta_layout.addWidget(media_label)
        meta_layout.addWidget(diff_label)
        meta_layout.addWidget(points_label)
        meta_layout.addStretch()
        
        info_layout.addWidget(text_label)
        info_layout.addLayout(meta_layout)
        
        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(5)
        
        btn_edit = QPushButton("✏️")
        btn_duplicate = QPushButton("📋")
        btn_delete = QPushButton("🗑️")
        
        for btn in (btn_edit, btn_duplicate, btn_delete):
            btn.setFixedSize(35, 35)
            btn.setStyleSheet(
                "QPushButton { "
                "background: rgba(57, 255, 20, 0.15); "
                "border: 1px solid #39FF14; "
                "border-radius: 6px; "
                "font-size: 14px; "
                "color: white; "
                "}"
                "QPushButton:hover { background: rgba(57, 255, 20, 0.3); }"
            )
        
        btn_delete.setStyleSheet(
            "QPushButton { "
            "background: rgba(231, 76, 60, 0.15); "
            "border: 1px solid #e74c3c; "
            "border-radius: 6px; "
            "font-size: 14px; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(231, 76, 60, 0.3); }"
        )
        
        btn_edit.setToolTip("Edit question")
        btn_duplicate.setToolTip("Duplicate question")
        btn_delete.setToolTip("Delete question")
        
        btn_edit.clicked.connect(lambda: self.edit_clicked.emit(question.id))
        btn_duplicate.clicked.connect(lambda: self.duplicate_clicked.emit(question.id))
        btn_delete.clicked.connect(lambda: self.delete_clicked.emit(question.id))
        
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_duplicate)
        btn_row.addWidget(btn_delete)
        
        btn_layout.addLayout(btn_row)
        btn_layout.addStretch()
        
        layout.addWidget(self.chk_include)
        layout.addWidget(num_label)
        layout.addLayout(info_layout, stretch=1)
        layout.addLayout(btn_layout)

    # ── helpers ──────────────────────────────────────────────────

    def _apply_frame_style(self):
        if self._enabled:
            self.setStyleSheet(
                "QFrame {"
                "  background: rgba(20, 30, 45, 0.9);"
                "  border-left: 4px solid #39FF14;"
                "  border-top: 1px solid rgba(57,255,20,0.2);"
                "  border-right: 1px solid rgba(57,255,20,0.2);"
                "  border-bottom: 1px solid rgba(57,255,20,0.2);"
                "  border-radius: 8px; padding: 10px; margin: 3px;"
                "}"
                "QFrame:hover { background: rgba(30,40,55,0.9);"
                "  border-left: 4px solid #5ddbff; }"
            )
            self.setGraphicsEffect(None)
        else:
            self.setStyleSheet(
                "QFrame {"
                "  background: rgba(10, 12, 18, 0.7);"
                "  border-left: 4px solid #444;"
                "  border-top: 1px solid rgba(80,80,80,0.15);"
                "  border-right: 1px solid rgba(80,80,80,0.15);"
                "  border-bottom: 1px solid rgba(80,80,80,0.15);"
                "  border-radius: 8px; padding: 10px; margin: 3px;"
                "}"
            )
            # Dim the whole row with opacity
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(0.45)
            self.setGraphicsEffect(effect)

    def _on_toggle(self, state: int):
        self._enabled = bool(state)
        self._apply_frame_style()
        self.toggle_clicked.emit(self.question.id, self._enabled)


class AdminDashboard(QWidget):
    """Enhanced admin dashboard with import/export and better UX"""
    
    config_changed = Signal(GameConfig)
    questions_changed = Signal(list)
    pack_saved = Signal(str)  # path to saved pack
    
    def __init__(self, config: GameConfig, questions: list):
        super().__init__()
        self.config = config
        self.questions = questions.copy()
        self.current_question_id = None
        self.has_unsaved_changes = False
        # Set of question IDs that are disabled (unchecked)
        self.disabled_ids: set = set()
        
        self.setStyleSheet("QWidget { background: #0d1b2a; }")
        self.setMinimumSize(1200, 800)
        
        # Main layout
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(15)
        
        # Header with actions
        header_layout = QHBoxLayout()
        
        header = QLabel("⚙️ ADMIN DASHBOARD")
        header.setStyleSheet(
            "font-size: 24px; font-weight: 900; color: #39FF14; "
            "letter-spacing: 2px; padding: 10px;"
        )
        
        # Quick action buttons
        self.btn_import = QPushButton("📥 Import Pack")
        self.btn_export = QPushButton("📤 Export Pack")
        self.btn_validate = QPushButton("✓ Validate")
        
        for btn in (self.btn_import, self.btn_export, self.btn_validate):
            btn.setStyleSheet(
                "QPushButton { "
                "background: rgba(57, 255, 20, 0.15); "
                "border: 2px solid #39FF14; "
                "border-radius: 8px; "
                "padding: 8px 15px; "
                "font-size: 12px; "
                "font-weight: 900; "
                "color: white; "
                "}"
                "QPushButton:hover { background: rgba(57, 255, 20, 0.3); }"
            )
        
        self.btn_import.clicked.connect(self._import_pack)
        self.btn_export.clicked.connect(self._export_pack)
        self.btn_validate.clicked.connect(self._validate_pack)
        
        header_layout.addWidget(header)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_validate)
        header_layout.addWidget(self.btn_import)
        header_layout.addWidget(self.btn_export)
        
        root.addLayout(header_layout)
        
        # Tab widget for different sections
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane { "
            "border: 2px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 8px; "
            "background: rgba(20, 30, 45, 0.3); "
            "}"
            "QTabBar::tab { "
            "background: rgba(20, 30, 45, 0.5); "
            "border: 2px solid rgba(57, 255, 20, 0.3); "
            "border-bottom: none; "
            "border-radius: 6px 6px 0 0; "
            "padding: 10px 20px; "
            "margin-right: 3px; "
            "color: white; "
            "font-weight: 700; "
            "}"
            "QTabBar::tab:selected { "
            "background: rgba(57, 255, 20, 0.2); "
            "border-color: #39FF14; "
            "}"
        )
        
        # Settings tab
        settings_tab = self._create_settings_tab()
        tabs.addTab(settings_tab, "🎮 Game Settings")
        
        # Questions tab (split view)
        questions_tab = self._create_questions_tab()
        tabs.addTab(questions_tab, "📝 Questions")
        
        # Statistics tab
        stats_tab = self._create_stats_tab()
        tabs.addTab(stats_tab, "📊 Statistics")
        
        root.addWidget(tabs, stretch=1)
        
        # Bottom action bar
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)
        
        self.changes_label = QLabel("● No unsaved changes")
        self.changes_label.setStyleSheet(
            "font-size: 11px; color: #2ecc71; font-weight: 700;"
        )
        
        self.btn_save = QPushButton("💾 Save All Changes")
        self.btn_discard = QPushButton("↶ Discard Changes")
        self.btn_close = QPushButton("✖️ Close")
        
        for btn in (self.btn_save, self.btn_discard, self.btn_close):
            btn.setMinimumHeight(45)
            btn.setStyleSheet(
                "QPushButton { "
                "background: rgba(57, 255, 20, 0.2); "
                "border: 2px solid #39FF14; "
                "border-radius: 8px; "
                "padding: 10px 25px; "
                "font-size: 14px; "
                "font-weight: 900; "
                "color: white; "
                "}"
                "QPushButton:hover { background: rgba(57, 255, 20, 0.4); }"
            )
        
        self.btn_discard.setStyleSheet(
            "QPushButton { "
            "background: rgba(231, 76, 60, 0.2); "
            "border: 2px solid #e74c3c; "
            "border-radius: 8px; "
            "padding: 10px 25px; "
            "font-size: 14px; "
            "font-weight: 900; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(231, 76, 60, 0.4); }"
        )
        
        self.btn_save.clicked.connect(self._save_all)
        self.btn_discard.clicked.connect(self._discard_changes)
        self.btn_close.clicked.connect(self._close_with_confirmation)
        
        bottom_layout.addWidget(self.changes_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_discard)
        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_close)
        
        root.addLayout(bottom_layout)
    
    def _create_settings_tab(self):
        """Create game settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        content_layout = QFormLayout(content)
        content_layout.setSpacing(15)
        content_layout.setHorizontalSpacing(20)
        
        # Pack name
        self.pack_name = QLineEdit(self.config.name)
        self.pack_name.textChanged.connect(self._mark_unsaved)
        self.pack_name.setStyleSheet(self._input_style())
        content_layout.addRow(self._create_label("Pack Name:"), self.pack_name)
        
        # Rounds
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(1, 10)
        self.rounds_spin.setValue(self.config.rounds)
        self.rounds_spin.valueChanged.connect(self._mark_unsaved)
        self.rounds_spin.setStyleSheet(self._input_style())
        content_layout.addRow(self._create_label("Number of Rounds:"), self.rounds_spin)
        
        # Questions per round
        self.questions_per_round = QSpinBox()
        self.questions_per_round.setRange(1, 100)
        self.questions_per_round.setValue(self.config.questions_per_round)
        self.questions_per_round.valueChanged.connect(self._mark_unsaved)
        self.questions_per_round.setStyleSheet(self._input_style())
        content_layout.addRow(self._create_label("Questions per Round:"), self.questions_per_round)
        
        # Timer settings
        self.timer_seconds = QSpinBox()
        self.timer_seconds.setRange(5, 120)
        self.timer_seconds.setValue(self.config.timer_seconds)
        self.timer_seconds.valueChanged.connect(self._mark_unsaved)
        self.timer_seconds.setStyleSheet(self._input_style())
        content_layout.addRow(self._create_label("Timer (seconds):"), self.timer_seconds)
        
        self.answer_seconds = QSpinBox()
        self.answer_seconds.setRange(3, 60)
        self.answer_seconds.setValue(self.config.answer_seconds)
        self.answer_seconds.valueChanged.connect(self._mark_unsaved)
        self.answer_seconds.setStyleSheet(self._input_style())
        content_layout.addRow(self._create_label("Answer Time (seconds):"), self.answer_seconds)
        
        # Game options
        self.shuffle_questions = QCheckBox("Shuffle questions in random order")
        self.shuffle_questions.setChecked(self.config.shuffle_questions)
        self.shuffle_questions.stateChanged.connect(self._mark_unsaved)
        self.shuffle_questions.setStyleSheet(
            "QCheckBox { color: white; font-size: 13px; font-weight: 700; }"
        )
        content_layout.addRow("", self.shuffle_questions)
        
        # FIXED: Use new field name
        self.enable_cascading_global = QCheckBox("Enable cascading attempts globally")
        self.enable_cascading_global.setChecked(
            getattr(self.config, 'enable_cascading_attempts', True)
        )
        self.enable_cascading_global.stateChanged.connect(self._mark_unsaved)
        self.enable_cascading_global.setStyleSheet(
            "QCheckBox { color: white; font-size: 13px; font-weight: 700; }"
        )
        content_layout.addRow("", self.enable_cascading_global)
        
        self.bonus_for_speed = QCheckBox("Award bonus points for fast answers (< 3s)")
        self.bonus_for_speed.setChecked(self.config.bonus_for_speed)
        self.bonus_for_speed.stateChanged.connect(self._mark_unsaved)
        self.bonus_for_speed.setStyleSheet(
            "QCheckBox { color: white; font-size: 13px; font-weight: 700; }"
        )
        content_layout.addRow("", self.bonus_for_speed)
        
        # ===================================================================
        # NEW: SCORING CONFIGURATION
        # ===================================================================
        
        # Section header
        scoring_header = QLabel("⭐ SCORING CONFIGURATION")
        scoring_header.setStyleSheet(
            "font-size: 16px; font-weight: 900; color: #39FF14; "
            "padding-top: 20px; padding-bottom: 10px; background: transparent;"
        )
        content_layout.addRow("", scoring_header)
        
        # Points for 1st attempt (default)
        self.points_first_default = QSpinBox()
        self.points_first_default.setRange(0, 20)
        self.points_first_default.setValue(
            getattr(self.config, 'points_first_attempt_default', 3)
        )
        self.points_first_default.valueChanged.connect(self._mark_unsaved)
        self.points_first_default.setStyleSheet(self._input_style())
        self.points_first_default.setToolTip("Default points for 1st attempt")
        content_layout.addRow(
            self._create_label("Points - 1st Attempt (Default):"), 
            self.points_first_default
        )
        
        # Points for 2nd attempt (default)
        self.points_second_default = QSpinBox()
        self.points_second_default.setRange(0, 20)
        self.points_second_default.setValue(
            getattr(self.config, 'points_second_attempt_default', 2)
        )
        self.points_second_default.valueChanged.connect(self._mark_unsaved)
        self.points_second_default.setStyleSheet(self._input_style())
        self.points_second_default.setToolTip("Default points for 2nd attempt")
        content_layout.addRow(
            self._create_label("Points - 2nd Attempt (Default):"), 
            self.points_second_default
        )
        
        # Points for 3rd attempt (default)
        self.points_third_default = QSpinBox()
        self.points_third_default.setRange(0, 20)
        self.points_third_default.setValue(
            getattr(self.config, 'points_third_attempt_default', 1)
        )
        self.points_third_default.valueChanged.connect(self._mark_unsaved)
        self.points_third_default.setStyleSheet(self._input_style())
        self.points_third_default.setToolTip("Default points for 3rd attempt")
        content_layout.addRow(
            self._create_label("Points - 3rd Attempt (Default):"), 
            self.points_third_default
        )
        
        # Points for 4th attempt (default)
        self.points_fourth_default = QSpinBox()
        self.points_fourth_default.setRange(0, 20)
        self.points_fourth_default.setValue(
            getattr(self.config, 'points_fourth_attempt_default', 0)
        )
        self.points_fourth_default.valueChanged.connect(self._mark_unsaved)
        self.points_fourth_default.setStyleSheet(self._input_style())
        self.points_fourth_default.setToolTip("Default points for 4th attempt")
        content_layout.addRow(
            self._create_label("Points - 4th Attempt (Default):"), 
            self.points_fourth_default
        )
        
        # Max attempts (default)
        self.max_attempts_default = QSpinBox()
        self.max_attempts_default.setRange(1, 4)
        self.max_attempts_default.setValue(
            getattr(self.config, 'max_attempts_default', 3)
        )
        self.max_attempts_default.valueChanged.connect(self._mark_unsaved)
        self.max_attempts_default.setStyleSheet(self._input_style())
        self.max_attempts_default.setToolTip("Maximum attempts allowed (1-4)")
        content_layout.addRow(
            self._create_label("Max Attempts Allowed (Default):"), 
            self.max_attempts_default
        )
        
        # Penalty
        self.penalty_for_wrong = QSpinBox()
        self.penalty_for_wrong.setRange(0, 10)
        self.penalty_for_wrong.setValue(self.config.penalty_for_wrong)
        self.penalty_for_wrong.valueChanged.connect(self._mark_unsaved)
        self.penalty_for_wrong.setStyleSheet(self._input_style())
        self.penalty_for_wrong.setToolTip("Points deducted for each wrong answer")
        content_layout.addRow(
            self._create_label("Penalty for Wrong Answer:"), 
            self.penalty_for_wrong
        )
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return widget
    
    def _create_questions_tab(self):
        """Create questions management tab with split view"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Splitter for list and editor
        splitter = QSplitter(Qt.Horizontal)
        
        # Left: Questions list
        list_widget = self._create_questions_list()
        
        # Right: Question editor
        editor_widget = self._create_question_editor()
        
        splitter.addWidget(list_widget)
        splitter.addWidget(editor_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
        
        return widget
    
    def _create_questions_list(self):
        """Create questions list panel"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        
        list_label = QLabel(f"📝 Questions ({len(self.questions)})")
        list_label.setStyleSheet(
            "font-size: 16px; font-weight: 900; color: white;"
        )

        self.enabled_count_label = QLabel()
        self._update_enabled_count_label()
        self.enabled_count_label.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #39FF14;"
            "background: rgba(57,255,20,0.1);"
            "border: 1px solid rgba(57,255,20,0.3);"
            "border-radius: 4px; padding: 3px 8px;"
        )

        self.btn_new_question = QPushButton("➕ New")
        self.btn_new_question.setStyleSheet(
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.2); "
            "border: 2px solid #39FF14; "
            "border-radius: 6px; "
            "padding: 8px 15px; "
            "font-size: 12px; "
            "font-weight: 900; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(57, 255, 20, 0.4); }"
        )
        self.btn_new_question.clicked.connect(self._new_question)
        
        header_layout.addWidget(list_label)
        header_layout.addWidget(self.enabled_count_label)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_new_question)
        
        layout.addLayout(header_layout)
        
        # Questions scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 2px solid rgba(57, 255, 20, 0.2); "
            "border-radius: 8px; background: rgba(10, 15, 25, 0.5); }"
        )
        
        list_container = QWidget()
        self.questions_layout = QVBoxLayout(list_container)
        self.questions_layout.setSpacing(3)
        self.questions_layout.setContentsMargins(5, 5, 5, 5)
        
        scroll.setWidget(list_container)
        layout.addWidget(scroll, stretch=1)
        
        self._refresh_questions_list()
        
        return widget
    
    def _create_question_editor(self):
        """Create question editor panel"""
        self.editor_group = QGroupBox("✏️ QUESTION EDITOR")
        self.editor_group.setEnabled(False)
        self.editor_group.setStyleSheet(
            "QGroupBox { "
            "font-size: 16px; font-weight: 900; color: #39FF14; "
            "border: 2px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 10px; "
            "margin-top: 12px; "
            "padding: 15px; "
            "background: rgba(20, 30, 45, 0.3); "
            "}"
            "QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 8px; }"
            "QGroupBox:disabled { "
            "color: #666; "
            "border-color: #444; "
            "}"
        )
        
        layout = QVBoxLayout(self.editor_group)
        layout.setSpacing(15)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        form = QFormLayout(content)
        form.setSpacing(12)
        form.setHorizontalSpacing(15)
        
        # Round
        self.edit_round = QSpinBox()
        self.edit_round.setRange(1, 10)
        self.edit_round.setValue(1)
        self.edit_round.setStyleSheet(self._input_style())
        form.addRow(self._create_label("Round:"), self.edit_round)
        
        # Question text
        self.edit_question_text = QTextEdit()
        self.edit_question_text.setPlaceholderText("Enter your question here...")
        self.edit_question_text.setMaximumHeight(100)
        self.edit_question_text.setStyleSheet(self._input_style())
        form.addRow(self._create_label("Question Text:"), self.edit_question_text)
        
        # Options
        self.edit_options = []
        for i in range(4):
            option_input = QLineEdit()
            option_input.setPlaceholderText(f"Option {chr(65+i)}...")
            option_input.setStyleSheet(self._input_style())
            self.edit_options.append(option_input)
            form.addRow(self._create_label(f"Option {chr(65+i)}:"), option_input)
        
        # Correct answer
        self.edit_correct = QComboBox()
        self.edit_correct.addItems(["A", "B", "C", "D"])
        self.edit_correct.setStyleSheet(self._input_style())
        form.addRow(self._create_label("Correct Answer:"), self.edit_correct)
        
        # Difficulty
        self.edit_difficulty = QComboBox()
        self.edit_difficulty.addItems(["Easy", "Medium", "Hard"])
        self.edit_difficulty.setCurrentIndex(1)
        self.edit_difficulty.setStyleSheet(self._input_style())
        form.addRow(self._create_label("Difficulty:"), self.edit_difficulty)
        
        # ===================================================================
        # NEW: COMPREHENSIVE SCORING SECTION
        # ===================================================================
        
        # Scoring section header
        scoring_header = QLabel("⭐ QUESTION SCORING")
        scoring_header.setStyleSheet(
            "font-size: 14px; font-weight: 900; color: #39FF14; "
            "padding-top: 15px; padding-bottom: 8px; background: transparent;"
        )
        form.addRow("", scoring_header)
        
        # Points for each attempt
        self.edit_points_first = QSpinBox()
        self.edit_points_first.setRange(0, 20)
        self.edit_points_first.setValue(3)
        self.edit_points_first.setStyleSheet(self._input_style())
        self.edit_points_first.setToolTip("Points awarded if answered correctly on 1st attempt")
        form.addRow(self._create_label("Points - 1st Attempt:"), self.edit_points_first)
        
        self.edit_points_second = QSpinBox()
        self.edit_points_second.setRange(0, 20)
        self.edit_points_second.setValue(2)
        self.edit_points_second.setStyleSheet(self._input_style())
        self.edit_points_second.setToolTip("Points awarded if answered correctly on 2nd attempt")
        form.addRow(self._create_label("Points - 2nd Attempt:"), self.edit_points_second)
        
        self.edit_points_third = QSpinBox()
        self.edit_points_third.setRange(0, 20)
        self.edit_points_third.setValue(1)
        self.edit_points_third.setStyleSheet(self._input_style())
        self.edit_points_third.setToolTip("Points awarded if answered correctly on 3rd attempt")
        form.addRow(self._create_label("Points - 3rd Attempt:"), self.edit_points_third)
        
        self.edit_points_fourth = QSpinBox()
        self.edit_points_fourth.setRange(0, 20)
        self.edit_points_fourth.setValue(0)
        self.edit_points_fourth.setStyleSheet(self._input_style())
        self.edit_points_fourth.setToolTip("Points awarded if answered correctly on 4th attempt")
        form.addRow(self._create_label("Points - 4th Attempt:"), self.edit_points_fourth)
        
        # Max attempts for this question
        self.edit_max_attempts = QSpinBox()
        self.edit_max_attempts.setRange(1, 4)
        self.edit_max_attempts.setValue(3)
        self.edit_max_attempts.setStyleSheet(self._input_style())
        self.edit_max_attempts.setToolTip("Maximum number of attempts allowed for this question (1-4)")
        form.addRow(self._create_label("Max Attempts:"), self.edit_max_attempts)
        
        # Help text
        scoring_help = QLabel("💡 Tip: Higher difficulty questions can have more points on 1st attempt")
        scoring_help.setWordWrap(True)
        scoring_help.setStyleSheet(
            "font-size: 11px; color: rgba(255, 255, 255, 0.6); "
            "background: transparent; padding: 5px;"
        )
        form.addRow("", scoring_help)
        
        # Media type
        media_layout = QHBoxLayout()
        self.edit_media_type = QComboBox()
        self.edit_media_type.addItems(["None", "Image", "Audio", "Video"])
        self.edit_media_type.currentTextChanged.connect(self._media_type_changed)
        self.edit_media_type.setStyleSheet(self._input_style())
        
        self.btn_browse_media = QPushButton("📁 Browse...")
        self.btn_browse_media.setEnabled(False)
        self.btn_browse_media.clicked.connect(self._browse_media)
        self.btn_browse_media.setStyleSheet(
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.15); "
            "border: 2px solid #39FF14; "
            "border-radius: 6px; "
            "padding: 6px 12px; "
            "font-size: 12px; "
            "font-weight: 900; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(57, 255, 20, 0.3); }"
            "QPushButton:disabled { "
            "background: rgba(100, 100, 100, 0.1); "
            "border-color: #666; "
            "color: #666; "
            "}"
        )
        
        media_layout.addWidget(self.edit_media_type, stretch=1)
        media_layout.addWidget(self.btn_browse_media)
        form.addRow(self._create_label("Media Type:"), media_layout)
        
        # Media path
        self.edit_media_path = QLineEdit()
        self.edit_media_path.setPlaceholderText("No media file selected")
        self.edit_media_path.setReadOnly(True)
        self.edit_media_path.setStyleSheet(self._input_style())
        form.addRow(self._create_label("Media Path:"), self.edit_media_path)
        
        # Media preview
        self.media_preview = QLabel("No media")
        self.media_preview.setAlignment(Qt.AlignCenter)
        self.media_preview.setMinimumHeight(150)
        self.media_preview.setMaximumHeight(200)
        self.media_preview.setStyleSheet(
            "QLabel { "
            "background: rgba(0, 0, 0, 0.3); "
            "border: 2px dashed rgba(57, 255, 20, 0.3); "
            "border-radius: 8px; "
            "color: rgba(255, 255, 255, 0.5); "
            "font-size: 12px; "
            "padding: 10px; "
            "}"
        )
        form.addRow("", self.media_preview)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        
        self.btn_save_question = QPushButton("💾 Save Question")
        self.btn_cancel_edit = QPushButton("✖️ Cancel")
        
        for btn in (self.btn_save_question, self.btn_cancel_edit):
            btn.setMinimumHeight(40)
            btn.setStyleSheet(
                "QPushButton { "
                "background: rgba(57, 255, 20, 0.2); "
                "border: 2px solid #39FF14; "
                "border-radius: 8px; "
                "padding: 8px 20px; "
                "font-size: 13px; "
                "font-weight: 900; "
                "color: white; "
                "}"
                "QPushButton:hover { background: rgba(57, 255, 20, 0.4); }"
            )
        
        self.btn_save_question.clicked.connect(self._save_question)
        self.btn_cancel_edit.clicked.connect(self._cancel_edit)
        
        btn_layout.addWidget(self.btn_save_question)
        btn_layout.addWidget(self.btn_cancel_edit)
        form.addRow("", btn_layout)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return self.editor_group
    
    def _create_stats_tab(self):
        """Create statistics tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        stats_label = QLabel("📊 PACK STATISTICS")
        stats_label.setStyleSheet(
            "font-size: 18px; font-weight: 900; color: #39FF14;"
        )
        layout.addWidget(stats_label)
        
        # Stats grid
        stats_grid = QGridLayout()
        stats_grid.setSpacing(15)
        
        # Total questions
        total_card = self._create_stat_card("Total Questions", str(len(self.questions)), "#3498db")
        stats_grid.addWidget(total_card, 0, 0)
        
        # Questions by difficulty
        easy = sum(1 for q in self.questions if q.difficulty == "easy")
        medium = sum(1 for q in self.questions if q.difficulty == "medium")
        hard = sum(1 for q in self.questions if q.difficulty == "hard")
        
        easy_card = self._create_stat_card("Easy", str(easy), "#2ecc71")
        medium_card = self._create_stat_card("Medium", str(medium), "#f39c12")
        hard_card = self._create_stat_card("Hard", str(hard), "#e74c3c")
        
        stats_grid.addWidget(easy_card, 0, 1)
        stats_grid.addWidget(medium_card, 0, 2)
        stats_grid.addWidget(hard_card, 0, 3)
        
        # Media stats
        with_media = sum(1 for q in self.questions if q.media.type != MediaType.NONE)
        media_card = self._create_stat_card("With Media", str(with_media), "#9b59b6")
        stats_grid.addWidget(media_card, 1, 0)
        
        # FIXED: Total points using first attempt
        total_points = sum(
            getattr(q, 'points_first_attempt', getattr(q, 'points', 1)) 
            for q in self.questions
        )
        points_card = self._create_stat_card("Total Points", str(total_points), "#ffd700")
        stats_grid.addWidget(points_card, 1, 1)
        
        layout.addLayout(stats_grid)
        layout.addStretch()
        
        return widget
    
    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        """Create a statistics card"""
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ "
            f"background: rgba(20, 30, 45, 0.6); "
            f"border-left: 4px solid {color}; "
            f"border-top: 1px solid rgba(255, 255, 255, 0.1); "
            f"border-right: 1px solid rgba(255, 255, 255, 0.1); "
            f"border-bottom: 1px solid rgba(255, 255, 255, 0.1); "
            f"border-radius: 10px; "
            f"padding: 20px; "
            f"}}"
        )
        
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        
        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(
            f"font-size: 36px; font-weight: 900; color: {color};"
        )
        
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: rgba(255, 255, 255, 0.7);"
        )
        
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        
        return card
    
    def _refresh_questions_list(self):
        """Refresh the questions list display"""
        # Clear existing items
        while self.questions_layout.count():
            item = self.questions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add question items
        for i, question in enumerate(self.questions):
            is_enabled = question.id not in self.disabled_ids
            item = QuestionListItem(question, i, enabled=is_enabled)
            item.edit_clicked.connect(self._edit_question)
            item.delete_clicked.connect(self._delete_question)
            item.duplicate_clicked.connect(self._duplicate_question)
            item.toggle_clicked.connect(self._on_question_toggled)
            self.questions_layout.addWidget(item)
        
        self.questions_layout.addStretch()
    
    def _new_question(self):
        """Start creating a new question"""
        self.current_question_id = None
        self.editor_group.setEnabled(True)
        
        # Load defaults from global settings
        default_first = self.points_first_default.value()
        default_second = self.points_second_default.value()
        default_third = self.points_third_default.value()
        default_fourth = self.points_fourth_default.value()
        default_max = self.max_attempts_default.value()
        
        # Clear form
        self.edit_round.setValue(1)
        self.edit_question_text.clear()
        for option in self.edit_options:
            option.clear()
        self.edit_correct.setCurrentIndex(0)
        self.edit_difficulty.setCurrentIndex(1)
        
        # Set scoring to global defaults
        self.edit_points_first.setValue(default_first)
        self.edit_points_second.setValue(default_second)
        self.edit_points_third.setValue(default_third)
        self.edit_points_fourth.setValue(default_fourth)
        self.edit_max_attempts.setValue(default_max)
        
        self.edit_media_type.setCurrentIndex(0)
        self.edit_media_path.clear()
        self.media_preview.setText("No media")
        self.media_preview.setPixmap(QPixmap())
    
    def _edit_question(self, question_id: str):
        """Load question for editing"""
        question = next((q for q in self.questions if q.id == question_id), None)
        if not question:
            return
        
        self.current_question_id = question_id
        self.editor_group.setEnabled(True)
        
        # Load question data
        self.edit_round.setValue(question.round)
        self.edit_question_text.setPlainText(question.text)
        
        for i, option in enumerate(self.edit_options):
            if i < len(question.options):
                option.setText(question.options[i])
            else:
                option.clear()
        
        self.edit_correct.setCurrentIndex(question.correct_index)
        
        # Difficulty
        diff_index = {"easy": 0, "medium": 1, "hard": 2}.get(question.difficulty, 1)
        self.edit_difficulty.setCurrentIndex(diff_index)
        
        # Load all scoring fields
        self.edit_points_first.setValue(
            getattr(question, 'points_first_attempt', 3)
        )
        self.edit_points_second.setValue(
            getattr(question, 'points_second_attempt', 2)
        )
        self.edit_points_third.setValue(
            getattr(question, 'points_third_attempt', 1)
        )
        self.edit_points_fourth.setValue(
            getattr(question, 'points_fourth_attempt', 0)
        )
        self.edit_max_attempts.setValue(
            getattr(question, 'max_attempts', 3)
        )
        
        # Load media
        media_index = {
            MediaType.NONE: 0,
            MediaType.IMAGE: 1,
            MediaType.AUDIO: 2,
            MediaType.VIDEO: 3
        }.get(question.media.type, 0)
        self.edit_media_type.setCurrentIndex(media_index)
        
        if question.media.path:
            self.edit_media_path.setText(question.media.path)
            self._update_media_preview()
    
    def _duplicate_question(self, question_id: str):
        """Duplicate a question"""
        question = next((q for q in self.questions if q.id == question_id), None)
        if not question:
            return
        
        import uuid
        
        # FIXED: Create a copy with cascading points
        new_question = Question(
            id=f"q_{uuid.uuid4().hex[:8]}",
            round=question.round,
            text=f"{question.text} (Copy)",
            options=question.options.copy(),
            correct_index=question.correct_index,
            media=question.media,
            difficulty=question.difficulty,
            tags=question.tags.copy(),
            # NEW: Cascading points
            points_first_attempt=getattr(question, 'points_first_attempt', 3),
            points_second_attempt=getattr(question, 'points_second_attempt', 2),
            points_third_attempt=getattr(question, 'points_third_attempt', 1),
            max_attempts=3,
        )
        
        self.questions.append(new_question)
        self._refresh_questions_list()
        self._mark_unsaved()
        
        QMessageBox.information(self, "Success", "Question duplicated successfully!")
    
    def _delete_question(self, question_id: str):
        """Delete a question"""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Are you sure you want to delete this question?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.questions = [q for q in self.questions if q.id != question_id]
            self._refresh_questions_list()
            self._mark_unsaved()
    
    def _media_type_changed(self, media_type: str):
        """Enable/disable media browser based on type"""
        self.btn_browse_media.setEnabled(media_type != "None")
        if media_type == "None":
            self.edit_media_path.clear()
            self.media_preview.setText("No media")
            self.media_preview.setPixmap(QPixmap())
    
    def _browse_media(self):
        """Browse for media file"""
        media_type = self.edit_media_type.currentText()
        
        if media_type == "Image":
            file_filter = "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        elif media_type == "Audio":
            file_filter = "Audio (*.mp3 *.wav *.ogg *.m4a *.flac)"
        elif media_type == "Video":
            file_filter = "Video (*.mp4 *.avi *.mov *.mkv *.webm)"
        else:
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Select {media_type} File", "", file_filter
        )
        
        if file_path:
            self.edit_media_path.setText(file_path)
            self._update_media_preview()
    
    def _update_media_preview(self):
        """Update media preview"""
        path = self.edit_media_path.text()
        media_type = self.edit_media_type.currentText()
        
        if not path:
            self.media_preview.setText("No media")
            self.media_preview.setPixmap(QPixmap())
            return
        
        if media_type == "Image":
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(400, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.media_preview.setPixmap(scaled)
            else:
                self.media_preview.setText("⚠️ Could not load image")
        elif media_type == "Audio":
            self.media_preview.setText(f"🔊 Audio file:\n{Path(path).name}")
        elif media_type == "Video":
            self.media_preview.setText(f"🎬 Video file:\n{Path(path).name}")
    
    def _save_question(self):
        """Save current question (new or edited)"""
        # Validate
        question_text = self.edit_question_text.toPlainText().strip()
        if not question_text:
            QMessageBox.warning(self, "Validation Error", "Please enter a question text.")
            return
        
        options = [opt.text().strip() for opt in self.edit_options]
        if not all(options):
            QMessageBox.warning(self, "Validation Error", "Please fill in all 4 options.")
            return
        
        # Create media object
        media_type_str = self.edit_media_type.currentText().lower()
        if media_type_str == "none":
            media = Media(type=MediaType.NONE, path=None)
        else:
            media_path = self.edit_media_path.text()
            if not media_path:
                QMessageBox.warning(self, "Validation Error", f"Please select a {media_type_str} file.")
                return
            
            media = Media(
                type=MediaType[media_type_str.upper()],
                path=media_path
            )
        
        difficulty = self.edit_difficulty.currentText().lower()
        
        # Get all scoring values from form
        points_1st = self.edit_points_first.value()
        points_2nd = self.edit_points_second.value()
        points_3rd = self.edit_points_third.value()
        points_4th = self.edit_points_fourth.value()
        max_attempts = self.edit_max_attempts.value()
        
        # Create/update question with all cascading points
        if self.current_question_id:
            # Update existing
            for i, q in enumerate(self.questions):
                if q.id == self.current_question_id:
                    self.questions[i] = Question(
                        id=self.current_question_id,
                        round=self.edit_round.value(),
                        text=question_text,
                        options=options,
                        correct_index=self.edit_correct.currentIndex(),
                        media=media,
                        difficulty=difficulty,
                        tags=q.tags,
                        # Use all scoring fields from form
                        points_first_attempt=points_1st,
                        points_second_attempt=points_2nd,
                        points_third_attempt=points_3rd,
                        points_fourth_attempt=points_4th,
                        max_attempts=max_attempts,
                    )
                    break
        else:
            # Create new
            import uuid
            new_question = Question(
                id=f"q_{uuid.uuid4().hex[:8]}",
                round=self.edit_round.value(),
                text=question_text,
                options=options,
                correct_index=self.edit_correct.currentIndex(),
                media=media,
                difficulty=difficulty,
                tags=[],
                # Use all scoring fields from form
                points_first_attempt=points_1st,
                points_second_attempt=points_2nd,
                points_third_attempt=points_3rd,
                points_fourth_attempt=points_4th,
                max_attempts=max_attempts,
            )
            self.questions.append(new_question)
        
        self._refresh_questions_list()
        self._cancel_edit()
        self._mark_unsaved()
        
        QMessageBox.information(self, "Success", "Question saved successfully!")
    
    def _on_question_toggled(self, question_id: str, is_enabled: bool):
        """Handle checkbox toggle on a question row."""
        if is_enabled:
            self.disabled_ids.discard(question_id)
        else:
            self.disabled_ids.add(question_id)
        self._update_enabled_count_label()
        self._mark_unsaved()

    def _update_enabled_count_label(self):
        """Refresh the 'X / Y active' badge in the list header."""
        total   = len(self.questions)
        enabled = total - len(self.disabled_ids)
        self.enabled_count_label.setText(f"✅ {enabled} / {total} active")
        if enabled == 0:
            self.enabled_count_label.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #e74c3c;"
                "background: rgba(231,76,60,0.1);"
                "border: 1px solid rgba(231,76,60,0.4);"
                "border-radius: 4px; padding: 3px 8px;"
            )
        elif enabled < total:
            self.enabled_count_label.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #f39c12;"
                "background: rgba(243,156,18,0.1);"
                "border: 1px solid rgba(243,156,18,0.4);"
                "border-radius: 4px; padding: 3px 8px;"
            )
        else:
            self.enabled_count_label.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #39FF14;"
                "background: rgba(57,255,20,0.1);"
                "border: 1px solid rgba(57,255,20,0.3);"
                "border-radius: 4px; padding: 3px 8px;"
            )

    def _cancel_edit(self):
        """Cancel editing"""
        self.current_question_id = None
        self.editor_group.setEnabled(False)
    
    def _mark_unsaved(self):
        """Mark that there are unsaved changes"""
        self.has_unsaved_changes = True
        self.changes_label.setText("● Unsaved changes")
        self.changes_label.setStyleSheet(
            "font-size: 11px; color: #f39c12; font-weight: 700;"
        )
    
    def _save_all(self):
        """Save all changes and emit signals"""
        # Update config with all new scoring defaults
        updated_config = GameConfig(
            name=self.pack_name.text(),
            version=self.config.version,
            rounds=self.rounds_spin.value(),
            questions_per_round=self.questions_per_round.value(),
            timer_seconds=self.timer_seconds.value(),
            answer_seconds=self.answer_seconds.value(),
            shuffle_questions=self.shuffle_questions.isChecked(),
            question_files=self.config.question_files,
            pack_dir=self.config.pack_dir,
            # Cascading attempts settings
            enable_cascading_attempts=self.enable_cascading_global.isChecked(),
            reset_timer_each_attempt=getattr(self.config, 'reset_timer_each_attempt', False),
            penalty_for_wrong=self.penalty_for_wrong.value(),
            bonus_for_speed=self.bonus_for_speed.isChecked(),
            # NEW: Global scoring defaults
            points_first_attempt_default=self.points_first_default.value(),
            points_second_attempt_default=self.points_second_default.value(),
            points_third_attempt_default=self.points_third_default.value(),
            points_fourth_attempt_default=self.points_fourth_default.value(),
            max_attempts_default=self.max_attempts_default.value(),
        )
        
        # Emit signals — only pass enabled questions to the engine
        enabled_questions = [q for q in self.questions if q.id not in self.disabled_ids]
        self.config_changed.emit(updated_config)
        self.questions_changed.emit(enabled_questions)
        
        self.has_unsaved_changes = False
        self.changes_label.setText("● No unsaved changes")
        self.changes_label.setStyleSheet(
            "font-size: 11px; color: #2ecc71; font-weight: 700;"
        )
        
        QMessageBox.information(
            self, "Success",
            "All changes saved successfully!"
        )
    
    def _discard_changes(self):
        """Discard all unsaved changes"""
        if not self.has_unsaved_changes:
            return
        
        reply = QMessageBox.question(
            self, "Discard Changes",
            "Are you sure you want to discard all unsaved changes?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Would need to reload from disk here
            self.has_unsaved_changes = False
            self.changes_label.setText("● No unsaved changes")
            self.changes_label.setStyleSheet(
                "font-size: 11px; color: #2ecc71; font-weight: 700;"
            )
    
    def _close_with_confirmation(self):
        """Close with confirmation if there are unsaved changes"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Save:
                self._save_all()
                self.close()
            elif reply == QMessageBox.Discard:
                self.close()
        else:
            self.close()
    
    def _export_pack(self):
        """Export pack to a folder"""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Export Location"
        )
        
        if folder:
            try:
                export_path = Path(folder)
                save_pack(export_path, self.config, self.questions)
                self.pack_saved.emit(str(export_path))
                QMessageBox.information(
                    self, "Export Successful",
                    f"Pack exported successfully to:\n{export_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Failed",
                    f"Failed to export pack:\n{str(e)}"
                )
    
    def _import_pack(self):
        """Import pack from a folder"""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Pack Folder to Import"
        )
        
        if folder:
            try:
                from app.core.loaders import load_pack
                
                pack_path = Path(folder)
                cfg, questions = load_pack(pack_path)
                
                # Update current data
                self.config = cfg
                self.questions = questions
                
                # Refresh UI
                self.pack_name.setText(cfg.name)
                self.rounds_spin.setValue(cfg.rounds)
                self.questions_per_round.setValue(cfg.questions_per_round)
                self.timer_seconds.setValue(cfg.timer_seconds)
                self.answer_seconds.setValue(cfg.answer_seconds)
                self.shuffle_questions.setChecked(cfg.shuffle_questions)
                self._refresh_questions_list()
                self._mark_unsaved()
                
                QMessageBox.information(
                    self, "Import Successful",
                    f"Pack '{cfg.name}' imported successfully!\n"
                    f"Loaded {len(questions)} questions."
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Import Failed",
                    f"Failed to import pack:\n{str(e)}"
                )
    
    def _validate_pack(self):
        """Validate current pack configuration"""
        errors = []
        
        # Validate config
        if not self.pack_name.text().strip():
            errors.append("Pack name cannot be empty")
        
        # Validate questions
        if not self.questions:
            errors.append("Pack must have at least one question")
        
        for i, q in enumerate(self.questions):
            try:
                Question(
                    id=q.id,
                    round=q.round,
                    text=q.text,
                    options=q.options,
                    correct_index=q.correct_index,
                    media=q.media,
                    difficulty=q.difficulty,
                    tags=q.tags,
                    # NEW: Cascading points with defaults
                    points_first_attempt=getattr(q, 'points_first_attempt', 3),
                    points_second_attempt=getattr(q, 'points_second_attempt', 2),
                    points_third_attempt=getattr(q, 'points_third_attempt', 1),
                    max_attempts=getattr(q, 'max_attempts', 3),
                )
            except ValueError as e:
                errors.append(f"Question {i+1}: {str(e)}")
        
        if errors:
            QMessageBox.warning(
                self, "Validation Failed",
                "Pack validation failed:\n\n" + "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self, "Validation Successful",
                f"✓ Pack is valid!\n\n"
                f"• {len(self.questions)} questions\n"
                f"• {self.rounds_spin.value()} rounds\n"
                f"• {self.timer_seconds.value()}s timer"
            )
    
    def _create_label(self, text: str) -> QLabel:
        """Create styled form label"""
        label = QLabel(text)
        label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: rgba(255, 255, 255, 0.9);"
        )
        return label
    
    def _input_style(self) -> str:
        """Get standard input widget stylesheet"""
        return (
            "QLineEdit, QTextEdit, QSpinBox, QComboBox { "
            "background: rgba(30, 40, 55, 0.8); "
            "border: 2px solid rgba(57, 255, 20, 0.3); "
            "border-radius: 6px; "
            "padding: 8px; "
            "color: white; "
            "font-size: 13px; "
            "selection-background-color: #39FF14; "
            "selection-color: black; "
            "}"
            "QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus { "
            "border-color: #39FF14; "
            "}"
            "QSpinBox::up-button, QSpinBox::down-button { "
            "background: rgba(57, 255, 20, 0.2); "
            "border: 1px solid rgba(57, 255, 20, 0.3); "
            "}"
            "QComboBox::drop-down { "
            "background: rgba(57, 255, 20, 0.2); "
            "border-left: 1px solid rgba(57, 255, 20, 0.3); "
            "}"
        )
    
    def closeEvent(self, event):
        """Handle close event"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Save:
                self._save_all()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()