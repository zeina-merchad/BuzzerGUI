from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QFrame, QSpinBox, QLineEdit,
    QTextEdit, QComboBox, QFileDialog, QMessageBox, QListWidget,
    QListWidgetItem, QGroupBox, QFormLayout, QCheckBox, QTabWidget,
    QSplitter,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView
)
from PySide6.QtGui import QPixmap

from openpyxl import Workbook, load_workbook

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
        """Create questions management tab (Excel-first workflow, same UI theme)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Master excel for THIS pack
        self._excel_master_path = (self.config.pack_dir / "all_questions.xlsx").resolve()

        # Top action bar (Excel controls)
        top = QFrame()
        top.setStyleSheet(
            "QFrame { "
            "background: rgba(20, 30, 45, 0.55); "
            "border: 2px solid rgba(57, 255, 20, 0.25); "
            "border-radius: 10px; "
            "padding: 10px; "
            "}"
        )
        top_lay = QHBoxLayout(top)
        top_lay.setSpacing(10)
        top_lay.setContentsMargins(12, 10, 12, 10)

        self.excel_path_label = QLabel(f"📄 Master Excel: {self._excel_master_path}")
        self.excel_path_label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.85); "
            "background: transparent;"
        )

        btn_style = (
            "QPushButton { "
            "background: rgba(57, 255, 20, 0.15); "
            "border: 2px solid #39FF14; "
            "border-radius: 8px; "
            "padding: 8px 14px; "
            "font-size: 12px; "
            "font-weight: 900; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(57, 255, 20, 0.3); }"
            "QPushButton:disabled { background: rgba(100,100,100,0.1); border-color:#666; color:#777; }"
        )

        self.btn_excel_open = QPushButton("📂 Open")
        self.btn_excel_reload = QPushButton("↻ Reload")
        self.btn_excel_import = QPushButton("⬇️ Import Excel")
        self.btn_excel_export = QPushButton("⬆️ Export Excel")
        self.btn_excel_export_selected = QPushButton("🎯 Export Selected")
        self.btn_excel_create_filtered = QPushButton("🧪 Create Excel (Filtered)")
        self.btn_row_add = QPushButton("➕ Add Row")
        self.btn_row_dup = QPushButton("📋 Duplicate")
        self.btn_row_del = QPushButton("🗑️ Delete")

        for b in (
            self.btn_excel_open, self.btn_excel_reload, self.btn_excel_import,
            self.btn_excel_export, self.btn_excel_export_selected, self.btn_excel_create_filtered,
            self.btn_row_add, self.btn_row_dup, self.btn_row_del
        ):
            b.setStyleSheet(btn_style)
            b.setMinimumHeight(38)

        self.btn_row_del.setStyleSheet(
            "QPushButton { "
            "background: rgba(231, 76, 60, 0.15); "
            "border: 2px solid #e74c3c; "
            "border-radius: 8px; "
            "padding: 8px 14px; "
            "font-size: 12px; "
            "font-weight: 900; "
            "color: white; "
            "}"
            "QPushButton:hover { background: rgba(231, 76, 60, 0.3); }"
        )

        self.btn_excel_open.clicked.connect(self._excel_open_master)
        self.btn_excel_reload.clicked.connect(self._excel_reload_master)
        self.btn_excel_import.clicked.connect(self._excel_import_into_table)
        self.btn_excel_export.clicked.connect(self._excel_export_from_table)
        self.btn_excel_export_selected.clicked.connect(self._excel_export_selected_from_table)
        self.btn_excel_create_filtered.clicked.connect(self._excel_create_filtered_excel)
        self.btn_row_add.clicked.connect(self._table_add_row)
        self.btn_row_dup.clicked.connect(self._table_duplicate_row)
        self.btn_row_del.clicked.connect(self._table_delete_selected_rows)

        top_lay.addWidget(self.excel_path_label, stretch=1)
        top_lay.addWidget(self.btn_excel_open)
        top_lay.addWidget(self.btn_excel_reload)
        top_lay.addWidget(self.btn_excel_import)
        top_lay.addWidget(self.btn_excel_export)
        top_lay.addWidget(self.btn_excel_export_selected)
        top_lay.addWidget(self.btn_excel_create_filtered)
        top_lay.addSpacing(12)
        top_lay.addWidget(self.btn_row_add)
        top_lay.addWidget(self.btn_row_dup)
        top_lay.addWidget(self.btn_row_del)

        layout.addWidget(top)

        # Quick filters (used for "Create Excel (Filtered)")
        filter_bar = QFrame()
        filter_bar.setStyleSheet(
            "QFrame { background: rgba(20, 30, 45, 0.55); border: 2px solid rgba(57, 255, 20, 0.18); "
            "border-radius: 10px; }"
        )
        fl = QHBoxLayout(filter_bar)
        fl.setContentsMargins(10, 8, 10, 8)
        fl.setSpacing(10)

        def _field_style():
            return (
                "QLineEdit, QComboBox, QSpinBox { "
                "background: rgba(10, 15, 25, 0.7); "
                "border: 2px solid rgba(93, 219, 255, 0.25); "
                "border-radius: 8px; "
                "padding: 6px 10px; "
                "color: white; "
                "font-size: 12px; "
                "}"
                "QComboBox::drop-down { border: none; width: 22px; }"
                "QComboBox QAbstractItemView { background: rgba(10,15,25,0.95); color: white; selection-background-color: rgba(57,255,20,0.22); }"
            )

        fs = _field_style()

        fl.addWidget(QLabel("🔎 Text"))
        self.filter_text = QLineEdit()
        self.filter_text.setPlaceholderText("search in question/options")
        self.filter_text.setStyleSheet(fs)
        self.filter_text.setMinimumWidth(180)
        fl.addWidget(self.filter_text)

        fl.addWidget(QLabel("🎚 Difficulty"))
        self.filter_diff = QComboBox()
        self.filter_diff.addItems(["All", "easy", "medium", "hard"])
        self.filter_diff.setStyleSheet(fs)
        self.filter_diff.setFixedWidth(120)
        fl.addWidget(self.filter_diff)

        fl.addWidget(QLabel("🏁 Round"))
        self.filter_round_min = QSpinBox()
        self.filter_round_min.setRange(0, 99)
        self.filter_round_min.setValue(0)
        self.filter_round_min.setPrefix("min ")
        self.filter_round_min.setStyleSheet(fs)
        self.filter_round_min.setFixedWidth(90)
        fl.addWidget(self.filter_round_min)

        self.filter_round_max = QSpinBox()
        self.filter_round_max.setRange(0, 99)
        self.filter_round_max.setValue(0)
        self.filter_round_max.setPrefix("max ")
        self.filter_round_max.setStyleSheet(fs)
        self.filter_round_max.setFixedWidth(90)
        fl.addWidget(self.filter_round_max)

        fl.addWidget(QLabel("🏷 Tags"))
        self.filter_tags = QLineEdit()
        self.filter_tags.setPlaceholderText("comma tags (any match)")
        self.filter_tags.setStyleSheet(fs)
        self.filter_tags.setMinimumWidth(160)
        fl.addWidget(self.filter_tags)

        self.filter_enabled_only = QCheckBox("Enabled only")
        self.filter_enabled_only.setStyleSheet("color: rgba(255,255,255,0.85); font-weight: 800;")
        fl.addWidget(self.filter_enabled_only)

        self.btn_filter_clear = QPushButton("🧹 Clear")
        self.btn_filter_clear.setStyleSheet(btn_style)
        self.btn_filter_clear.setMinimumHeight(34)
        self.btn_filter_clear.clicked.connect(self._filter_clear)
        fl.addWidget(self.btn_filter_clear)

        fl.addStretch(1)
        layout.addWidget(filter_bar)

        # Table (Excel-like)
        self.questions_table = QTableWidget()
        self.questions_table.setStyleSheet(
            "QTableWidget { "
            "background: rgba(10, 15, 25, 0.55); "
            "border: 2px solid rgba(57, 255, 20, 0.25); "
            "border-radius: 10px; "
            "gridline-color: rgba(57, 255, 20, 0.15); "
            "color: white; "
            "font-size: 12px; "
            "}"
            "QHeaderView::section { "
            "background: rgba(20, 30, 45, 0.85); "
            "color: #39FF14; "
            "font-weight: 900; "
            "border: 1px solid rgba(57, 255, 20, 0.25); "
            "padding: 6px; "
            "}"
            "QTableWidget::item:selected { "
            "background: rgba(93, 219, 255, 0.22); "
            "}"
        )
        self.questions_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.questions_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.questions_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.questions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.questions_table.verticalHeader().setVisible(False)

        self._table_columns = [
            ("Enabled", "enabled"),
            ("ID", "id"),
            ("Round", "round"),
            ("Question", "text"),
            ("A", "A"),
            ("B", "B"),
            ("C", "C"),
            ("D", "D"),
            ("Correct (A-D or 0-3)", "correct"),
            ("Difficulty", "difficulty"),
            ("Media Type", "media_type"),
            ("Media Path", "media_path"),
            ("P1", "p1"),
            ("P2", "p2"),
            ("P3", "p3"),
            ("P4", "p4"),
            ("Max Attempts", "max_attempts"),
            ("Tags (comma)", "tags"),
        ]
        self.questions_table.setColumnCount(len(self._table_columns))
        self.questions_table.setHorizontalHeaderLabels([c[0] for c in self._table_columns])

        # Create master file if missing (from current questions)
        self._ensure_master_excel()

        # Load from master if possible (otherwise from in-memory)
        self._excel_reload_master(fallback_to_memory=True)

        self.questions_table.cellChanged.connect(self._mark_unsaved)

        layout.addWidget(self.questions_table, stretch=1)

        # Small hint footer (same UI)
        hint = QLabel(
            "💡 Excel workflow: edit directly in the table • Export to share/edit in Excel • Import to merge or replace • Save All Changes to generate the pack JSON."
        )
        hint.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.6); padding: 4px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return widget

    # =====================================================================================
    # Excel ↔ Questions helpers
    # =====================================================================================

    def _ensure_master_excel(self) -> None:
        """Create master Excel (all_questions.xlsx) if it doesn't exist yet."""
        try:
            self.config.pack_dir.mkdir(parents=True, exist_ok=True)
            if self._excel_master_path.exists():
                return
            # Seed with current in-memory questions
            self._write_questions_to_excel(self._excel_master_path, self.questions, self.disabled_ids)
        except Exception as e:
            QMessageBox.warning(self, "Excel Error", f"Failed to create master Excel:\n{e}")

    def _write_questions_to_excel(self, xlsx_path: Path, questions: list, disabled_ids: set) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "Questions"

        headers = [c[0] for c in self._table_columns]
        ws.append(headers)

        def correct_to_cell(q: Question) -> str:
            return ["A", "B", "C", "D"][int(q.correct_index)]

        for q in questions:
            enabled = (q.id not in disabled_ids)
            row = [
                1 if enabled else 0,
                q.id,
                int(q.round),
                q.text,
                q.options[0] if len(q.options) > 0 else "",
                q.options[1] if len(q.options) > 1 else "",
                q.options[2] if len(q.options) > 2 else "",
                q.options[3] if len(q.options) > 3 else "",
                correct_to_cell(q),
                (q.difficulty or "medium"),
                (q.media.type.value if q.media else "none"),
                (q.media.path if q.media else ""),
                int(getattr(q, "points_first_attempt", 3)),
                int(getattr(q, "points_second_attempt", 2)),
                int(getattr(q, "points_third_attempt", 1)),
                int(getattr(q, "points_fourth_attempt", 0)),
                int(getattr(q, "max_attempts", 3)),
                ",".join(getattr(q, "tags", []) or []),
            ]
            ws.append(row)

        wb.save(str(xlsx_path))

    def _read_questions_from_excel(self, xlsx_path: Path) -> tuple[list, set]:
        wb = load_workbook(str(xlsx_path))
        ws = wb.active

        # Map header -> col idx
        header_row = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
        col_map = {name: idx for idx, name in enumerate(header_row)}

        def get_cell(row, header, default=""):
            idx = col_map.get(header, None)
            if idx is None:
                return default
            v = row[idx].value
            return default if v is None else v

        questions: list[Question] = []
        disabled_ids: set = set()

        for row in ws.iter_rows(min_row=2):
            qid = str(get_cell(row, "ID", "")).strip()
            if not qid:
                continue

            enabled_val = get_cell(row, "Enabled", 1)
            try:
                enabled = bool(int(enabled_val))
            except Exception:
                enabled = str(enabled_val).strip().lower() not in ("0", "false", "no", "")

            rnd = int(float(get_cell(row, "Round", 1)))
            text = str(get_cell(row, "Question", "")).strip()

            opts = [
                str(get_cell(row, "A", "")).strip(),
                str(get_cell(row, "B", "")).strip(),
                str(get_cell(row, "C", "")).strip(),
                str(get_cell(row, "D", "")).strip(),
            ]

            correct_raw = str(get_cell(row, "Correct (A-D or 0-3)", "A")).strip().upper()
            if correct_raw in ("A", "B", "C", "D"):
                correct_index = {"A": 0, "B": 1, "C": 2, "D": 3}[correct_raw]
            else:
                try:
                    correct_index = int(float(correct_raw))
                except Exception:
                    correct_index = 0
            correct_index = max(0, min(3, correct_index))

            difficulty = str(get_cell(row, "Difficulty", "medium")).strip().lower() or "medium"
            if difficulty not in ("easy", "medium", "hard"):
                difficulty = "medium"

            media_type_raw = str(get_cell(row, "Media Type", "none")).strip().lower() or "none"
            if media_type_raw not in ("none", "image", "audio", "video"):
                media_type_raw = "none"
            media_path = str(get_cell(row, "Media Path", "")).strip() or None

            p1 = int(float(get_cell(row, "P1", getattr(self.config, "points_first_attempt_default", 3))))
            p2 = int(float(get_cell(row, "P2", getattr(self.config, "points_second_attempt_default", 2))))
            p3 = int(float(get_cell(row, "P3", getattr(self.config, "points_third_attempt_default", 1))))
            p4 = int(float(get_cell(row, "P4", getattr(self.config, "points_fourth_attempt_default", 0))))
            max_attempts = int(float(get_cell(row, "Max Attempts", getattr(self.config, "max_attempts_default", 3))))
            max_attempts = max(1, min(4, max_attempts))

            tags_raw = str(get_cell(row, "Tags (comma)", "")).strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

            q = Question(
                id=qid,
                round=rnd,
                text=text or "(empty)",
                options=opts,
                correct_index=correct_index,
                media=Media(type=MediaType(media_type_raw), path=media_path),
                difficulty=difficulty,
                tags=tags,
                points_first_attempt=p1,
                points_second_attempt=p2,
                points_third_attempt=p3,
                points_fourth_attempt=p4,
                max_attempts=max_attempts,
            )
            questions.append(q)
            if not enabled:
                disabled_ids.add(qid)

        return questions, disabled_ids

    # =====================================================================================
    # Excel UI actions
    # =====================================================================================

    def _excel_open_master(self):
        """Open master excel file with OS default program."""
        self._ensure_master_excel()
        try:
            import os, sys, subprocess
            p = str(self._excel_master_path)
            if sys.platform.startswith("win"):
                os.startfile(p)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", p], check=False)
            else:
                subprocess.run(["xdg-open", p], check=False)
        except Exception as e:
            QMessageBox.information(self, "Open Excel", f"Master excel is at:\n{self._excel_master_path}\n\n(Unable to auto-open: {e})")

    def _excel_reload_master(self, fallback_to_memory: bool = False):
        """Reload table from master excel."""
        self.questions_table.blockSignals(True)
        try:
            self._ensure_master_excel()
            if self._excel_master_path.exists():
                qs, disabled = self._read_questions_from_excel(self._excel_master_path)
                if qs:
                    self.questions = qs
                    self.disabled_ids = disabled
                elif fallback_to_memory:
                    pass
            elif fallback_to_memory:
                pass

            self._load_table_from_questions(self.questions, self.disabled_ids)
        except Exception as e:
            if fallback_to_memory:
                self._load_table_from_questions(self.questions, self.disabled_ids)
            QMessageBox.warning(self, "Excel Error", f"Failed to reload from Excel:\n{e}")
        finally:
            self.questions_table.blockSignals(False)

    def _excel_import_into_table(self):
        """Import an Excel file and merge it into the current table."""
        path, _ = QFileDialog.getOpenFileName(self, "Import Questions Excel", str(self.config.pack_dir), "Excel Files (*.xlsx)")
        if not path:
            return

        try:
            imported_qs, imported_disabled = self._read_questions_from_excel(Path(path))
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to read Excel:\n{e}")
            return

        if not imported_qs:
            QMessageBox.information(self, "Import", "No questions found in that Excel.")
            return

        # Merge by ID (replace if same ID)
        existing_by_id = {q.id: q for q in self._collect_questions_from_table()[0]}
        disabled_ids = set(self._collect_questions_from_table()[1])

        for q in imported_qs:
            existing_by_id[q.id] = q

        # disabled merge (imported may mark enabled/disabled)
        disabled_ids |= imported_disabled

        merged = list(existing_by_id.values())
        merged.sort(key=lambda q: (q.round, q.id))

        self.questions_table.blockSignals(True)
        self._load_table_from_questions(merged, disabled_ids)
        self.questions_table.blockSignals(False)

        self._mark_unsaved()

    def _excel_export_from_table(self):
        """Export current table to a new Excel file (and also update master)."""
        qs, disabled = self._collect_questions_from_table()

        if not qs:
            QMessageBox.information(self, "Export", "No questions to export.")
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Export Questions Excel", str(self.config.pack_dir / "questions_export.xlsx"), "Excel Files (*.xlsx)")
        if not out_path:
            return

        try:
            self._write_questions_to_excel(Path(out_path), qs, disabled)
            # Also keep master in sync
            self._write_questions_to_excel(self._excel_master_path, qs, disabled)
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export:\n{e}")
            return

        QMessageBox.information(self, "Export", f"Exported Excel:\n{out_path}")


    def _excel_export_selected_from_table(self):
        """Export ONLY the currently selected rows to a new Excel file."""
        rows = sorted({idx.row() for idx in self.questions_table.selectionModel().selectedRows()})
        if not rows:
            QMessageBox.information(self, "Export Selected", "Select one or more rows first.")
            return

        qs_all, disabled_all = self._collect_questions_from_table()
        by_id = {q.id: q for q in qs_all}

        selected_qs = []
        selected_disabled = set()

        for r in rows:
            q, enabled = self._row_to_question(r)
            selected_qs.append(q)
            if not enabled:
                selected_disabled.add(q.id)

        if not selected_qs:
            QMessageBox.information(self, "Export Selected", "No valid questions in the selection.")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Selected Questions Excel",
            str(self.config.pack_dir / "questions_selected.xlsx"),
            "Excel Files (*.xlsx)"
        )
        if not out_path:
            return

        try:
            self._write_questions_to_excel(Path(out_path), selected_qs, selected_disabled)
        except Exception as e:
            QMessageBox.warning(self, "Export Selected Error", f"Failed to export:\n{e}")
            return

        QMessageBox.information(self, "Export Selected", f"Exported selected questions:\n{out_path}")

    def _excel_create_filtered_excel(self):
        """Create a new Excel from the master list using the filter bar (round/difficulty/tags/text)."""
        # Prefer filtering from the table (which mirrors master), but ensure master is synced first.
        qs, disabled = self._collect_questions_from_table()
        if not qs:
            QMessageBox.information(self, "Create Excel", "No questions available to filter.")
            return

        filtered_qs, filtered_disabled = self._apply_filters_to_questions(qs, disabled)

        if not filtered_qs:
            QMessageBox.information(self, "Create Excel", "No questions matched your filters.")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Create Filtered Excel",
            str(self.config.pack_dir / "questions_filtered.xlsx"),
            "Excel Files (*.xlsx)"
        )
        if not out_path:
            return

        try:
            self._write_questions_to_excel(Path(out_path), filtered_qs, filtered_disabled)
        except Exception as e:
            QMessageBox.warning(self, "Create Excel Error", f"Failed to create filtered Excel:\n{e}")
            return

        QMessageBox.information(self, "Create Excel", f"Created filtered Excel:\n{out_path}")

    def _filter_clear(self):
        """Clear quick filter inputs."""
        self.filter_text.setText("")
        self.filter_diff.setCurrentIndex(0)
        self.filter_round_min.setValue(0)
        self.filter_round_max.setValue(0)
        self.filter_tags.setText("")
        self.filter_enabled_only.setChecked(False)

    def _apply_filters_to_questions(self, qs: list, disabled_ids: set):
        """Return (filtered_questions, filtered_disabled_ids) based on quick filter bar."""
        text_q = (self.filter_text.text() or "").strip().lower()
        diff = self.filter_diff.currentText().strip().lower()
        rmin = int(self.filter_round_min.value())
        rmax = int(self.filter_round_max.value())
        tags_raw = (self.filter_tags.text() or "").strip().lower()
        tag_terms = [t.strip() for t in tags_raw.split(",") if t.strip()]
        enabled_only = self.filter_enabled_only.isChecked()

        def _row_text(q: Question) -> str:
            parts = [
                q.id or "",
                q.text or "",
                str(getattr(q, "A", "")),
                str(getattr(q, "B", "")),
                str(getattr(q, "C", "")),
                str(getattr(q, "D", "")),
                str(getattr(q, "difficulty", "")),
                ",".join(getattr(q, "tags", []) or []),
            ]
            return " ".join(parts).lower()

        filtered = []
        filtered_disabled = set()

        for q in qs:
            is_enabled = (q.id not in disabled_ids)
            if enabled_only and not is_enabled:
                continue

            if diff and diff != "all":
                if (q.difficulty or "").strip().lower() != diff:
                    continue

            if rmin > 0 and int(q.round) < rmin:
                continue
            if rmax > 0 and int(q.round) > rmax:
                continue

            if tag_terms:
                qtags = [t.strip().lower() for t in (getattr(q, "tags", []) or [])]
                # any match
                if not any(term in qtags for term in tag_terms):
                    continue

            if text_q:
                if text_q not in _row_text(q):
                    continue

            filtered.append(q)
            if not is_enabled:
                filtered_disabled.add(q.id)

        # keep stable order
        filtered.sort(key=lambda x: (int(getattr(x, "round", 0)), str(getattr(x, "id", ""))))
        return filtered, filtered_disabled


    # =====================================================================================
    # Table actions
    # =====================================================================================

    def _load_table_from_questions(self, questions: list, disabled_ids: set):
        self.questions_table.setRowCount(0)
        for q in questions:
            self._append_question_row(q, enabled=(q.id not in disabled_ids))
        # Make some columns wider by default
        self.questions_table.setColumnWidth(0, 70)   # Enabled
        self.questions_table.setColumnWidth(1, 170)  # ID
        self.questions_table.setColumnWidth(2, 70)   # Round
        self.questions_table.setColumnWidth(3, 420)  # Question
        for i in range(4, 8):
            self.questions_table.setColumnWidth(i, 240)  # A..D
        self.questions_table.setColumnWidth(8, 150)  # Correct
        self.questions_table.setColumnWidth(9, 110)  # Difficulty
        self.questions_table.setColumnWidth(10, 110) # Media type
        self.questions_table.setColumnWidth(11, 260) # Media path

    def _append_question_row(self, q: Question, enabled: bool = True):
        r = self.questions_table.rowCount()
        self.questions_table.insertRow(r)

        # Enabled checkbox
        it_enabled = QTableWidgetItem()
        it_enabled.setFlags(it_enabled.flags() | Qt.ItemIsUserCheckable)
        it_enabled.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
        it_enabled.setText("")
        self.questions_table.setItem(r, 0, it_enabled)

        def set_item(col, val):
            item = QTableWidgetItem("" if val is None else str(val))
            self.questions_table.setItem(r, col, item)

        set_item(1, q.id)
        set_item(2, q.round)
        set_item(3, q.text)
        set_item(4, q.options[0] if len(q.options) > 0 else "")
        set_item(5, q.options[1] if len(q.options) > 1 else "")
        set_item(6, q.options[2] if len(q.options) > 2 else "")
        set_item(7, q.options[3] if len(q.options) > 3 else "")
        set_item(8, ["A", "B", "C", "D"][int(q.correct_index)])
        set_item(9, q.difficulty)
        set_item(10, q.media.type.value if q.media else "none")
        set_item(11, q.media.path if q.media else "")
        set_item(12, getattr(q, "points_first_attempt", 3))
        set_item(13, getattr(q, "points_second_attempt", 2))
        set_item(14, getattr(q, "points_third_attempt", 1))
        set_item(15, getattr(q, "points_fourth_attempt", 0))
        set_item(16, getattr(q, "max_attempts", 3))
        set_item(17, ",".join(getattr(q, "tags", []) or []))

    def _table_add_row(self):
        """Add a blank row with sane defaults."""
        # Generate a simple unique id
        import uuid
        new_id = f"q_{uuid.uuid4().hex[:8]}"
        q = Question(
            id=new_id,
            round=1,
            text="New question...",
            options=["A", "B", "C", "D"],
            correct_index=0,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="medium",
            tags=[],
            points_first_attempt=getattr(self.config, "points_first_attempt_default", 3),
            points_second_attempt=getattr(self.config, "points_second_attempt_default", 2),
            points_third_attempt=getattr(self.config, "points_third_attempt_default", 1),
            points_fourth_attempt=getattr(self.config, "points_fourth_attempt_default", 0),
            max_attempts=getattr(self.config, "max_attempts_default", 3),
        )
        self.questions_table.blockSignals(True)
        self._append_question_row(q, enabled=True)
        self.questions_table.blockSignals(False)
        self._mark_unsaved()

    def _table_duplicate_row(self):
        rows = sorted({idx.row() for idx in self.questions_table.selectionModel().selectedRows()})
        if not rows:
            return
        src_row = rows[0]
        q, enabled = self._row_to_question(src_row)
        import uuid
        q = Question(
            id=f"{q.id}_copy_{uuid.uuid4().hex[:4]}",
            round=q.round,
            text=q.text,
            options=q.options,
            correct_index=q.correct_index,
            media=q.media,
            difficulty=q.difficulty,
            tags=q.tags,
            points_first_attempt=getattr(q, "points_first_attempt", 3),
            points_second_attempt=getattr(q, "points_second_attempt", 2),
            points_third_attempt=getattr(q, "points_third_attempt", 1),
            points_fourth_attempt=getattr(q, "points_fourth_attempt", 0),
            max_attempts=getattr(q, "max_attempts", 3),
        )
        self.questions_table.blockSignals(True)
        self._append_question_row(q, enabled=enabled)
        self.questions_table.blockSignals(False)
        self._mark_unsaved()

    def _table_delete_selected_rows(self):
        rows = sorted({idx.row() for idx in self.questions_table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        reply = QMessageBox.question(self, "Delete Rows", f"Delete {len(rows)} selected question(s)?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.questions_table.blockSignals(True)
        for r in rows:
            self.questions_table.removeRow(r)
        self.questions_table.blockSignals(False)
        self._mark_unsaved()

    def _row_to_question(self, r: int) -> tuple[Question, bool]:
        def txt(col, default=""):
            it = self.questions_table.item(r, col)
            return default if it is None else (it.text() or default)

        enabled_item = self.questions_table.item(r, 0)
        enabled = True
        if enabled_item is not None and enabled_item.flags() & Qt.ItemIsUserCheckable:
            enabled = (enabled_item.checkState() == Qt.Checked)

        qid = txt(1, f"q_row_{r+1}").strip() or f"q_row_{r+1}"
        rnd = int(float(txt(2, 1)))
        qtext = txt(3, "").strip()
        options = [txt(4, ""), txt(5, ""), txt(6, ""), txt(7, "")]
        correct_raw = txt(8, "A").strip().upper()
        if correct_raw in ("A", "B", "C", "D"):
            correct_index = {"A": 0, "B": 1, "C": 2, "D": 3}[correct_raw]
        else:
            try:
                correct_index = int(float(correct_raw))
            except Exception:
                correct_index = 0
        correct_index = max(0, min(3, correct_index))

        difficulty = txt(9, "medium").strip().lower() or "medium"
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        media_type_raw = txt(10, "none").strip().lower() or "none"
        if media_type_raw not in ("none", "image", "audio", "video"):
            media_type_raw = "none"
        media_path = txt(11, "").strip() or None

        def to_int(col, default):
            s = txt(col, default)
            try:
                return int(float(s))
            except Exception:
                return int(default)

        p1 = to_int(12, getattr(self.config, "points_first_attempt_default", 3))
        p2 = to_int(13, getattr(self.config, "points_second_attempt_default", 2))
        p3 = to_int(14, getattr(self.config, "points_third_attempt_default", 1))
        p4 = to_int(15, getattr(self.config, "points_fourth_attempt_default", 0))
        max_attempts = to_int(16, getattr(self.config, "max_attempts_default", 3))
        max_attempts = max(1, min(4, max_attempts))

        tags_raw = txt(17, "").strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        q = Question(
            id=qid,
            round=rnd,
            text=qtext or "(empty)",
            options=options,
            correct_index=correct_index,
            media=Media(type=MediaType(media_type_raw), path=media_path),
            difficulty=difficulty,
            tags=tags,
            points_first_attempt=p1,
            points_second_attempt=p2,
            points_third_attempt=p3,
            points_fourth_attempt=p4,
            max_attempts=max_attempts,
        )
        return q, enabled

    def _collect_questions_from_table(self) -> tuple[list, set]:
        questions: list[Question] = []
        disabled_ids: set = set()

        seen_ids: set = set()
        for r in range(self.questions_table.rowCount()):
            q, enabled = self._row_to_question(r)

            # Ensure unique IDs (avoid save_pack collisions)
            base = q.id
            if base in seen_ids:
                i = 2
                new_id = f"{base}_{i}"
                while new_id in seen_ids:
                    i += 1
                    new_id = f"{base}_{i}"
                q = Question(
                    id=new_id,
                    round=q.round,
                    text=q.text,
                    options=q.options,
                    correct_index=q.correct_index,
                    media=q.media,
                    difficulty=q.difficulty,
                    tags=q.tags,
                    points_first_attempt=getattr(q, "points_first_attempt", 3),
                    points_second_attempt=getattr(q, "points_second_attempt", 2),
                    points_third_attempt=getattr(q, "points_third_attempt", 1),
                    points_fourth_attempt=getattr(q, "points_fourth_attempt", 0),
                    max_attempts=getattr(q, "max_attempts", 3),
                )
            seen_ids.add(q.id)

            questions.append(q)
            if not enabled:
                disabled_ids.add(q.id)

        return questions, disabled_ids

    def _sync_table_to_memory_and_master_excel(self) -> None:
        qs, disabled = self._collect_questions_from_table()
        self.questions = qs
        self.disabled_ids = disabled
        self._write_questions_to_excel(self._excel_master_path, qs, disabled)

    # =====================================================================================
    # Stats tab remains the same
    # =====================================================================================

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
        # Keep Excel/table as source of truth for questions
        if hasattr(self, "questions_table"):
            try:
                self._sync_table_to_memory_and_master_excel()
            except Exception as e:
                QMessageBox.warning(self, "Save Error", f"Failed to sync questions from table/Excel:\n{e}")
                return
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
        # If using Excel/table, sync first
        if hasattr(self, "questions_table"):
            try:
                self._sync_table_to_memory_and_master_excel()
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Failed to sync table/Excel:\n{e}")
                return

        folder = QFileDialog.getExistingDirectory(
            self, "Select Export Location"
        )
        
        if folder:
            try:
                export_path = Path(folder)
                enabled_questions = [q for q in self.questions if q.id not in self.disabled_ids]
                save_pack(export_path, self.config, enabled_questions)
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
                self.disabled_ids = set()

                # If Excel/table UI exists, sync master excel for this pack
                if hasattr(self, "questions_table"):
                    try:
                        self._excel_master_path = (self.config.pack_dir / "all_questions.xlsx").resolve()
                        self.excel_path_label.setText(f"📄 Master Excel: {self._excel_master_path}")
                        self._write_questions_to_excel(self._excel_master_path, self.questions, self.disabled_ids)
                        self._excel_reload_master(fallback_to_memory=True)
                    except Exception:
                        # Non-fatal; UI will still have questions in memory
                        pass
                
                # Refresh UI
                self.pack_name.setText(cfg.name)
                self.rounds_spin.setValue(cfg.rounds)
                self.questions_per_round.setValue(cfg.questions_per_round)
                self.timer_seconds.setValue(cfg.timer_seconds)
                self.answer_seconds.setValue(cfg.answer_seconds)
                self.shuffle_questions.setChecked(cfg.shuffle_questions)
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
        # If using Excel/table, validate what is currently in the table
        if hasattr(self, "questions_table"):
            try:
                self._sync_table_to_memory_and_master_excel()
            except Exception as e:
                QMessageBox.warning(self, "Validate", f"Failed to read table/Excel:\n{e}")
                return

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