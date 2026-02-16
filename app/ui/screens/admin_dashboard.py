"""
Admin Dashboard — Pure Excel Question Management
All questions loaded from/saved to Excel files ONLY.
NO JSON. Excel is the single source of truth.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QFrame, QSpinBox, QLineEdit,
    QTextEdit, QComboBox, QFileDialog, QMessageBox, QGroupBox,
    QFormLayout, QCheckBox, QSplitter
)
from PySide6.QtGui import QPixmap

from app.core.models import Question, Media, GameConfig
from app.constants import MediaType


# ═══════════════════════════════════════════════════════════════
# EXCEL FORMAT
# ═══════════════════════════════════════════════════════════════

XLSX_COLUMNS = [
    "id", "round", "text",
    "option_a", "option_b", "option_c", "option_d",
    "correct_index", "difficulty",
    "points_first_attempt", "points_second_attempt",
    "points_third_attempt", "points_fourth_attempt",
    "max_attempts", "media_type", "media_path", "tags",
    "enabled",  # NEW: track if question is selected/enabled
]

XLSX_HEADERS = [
    "ID", "Round", "Question Text",
    "Option A", "Option B", "Option C", "Option D",
    "Correct (0-3)", "Difficulty",
    "Pts 1st", "Pts 2nd", "Pts 3rd", "Pts 4th",
    "Max Attempts", "Media Type", "Media Path", "Tags",
    "Enabled",  # NEW: YES/NO
]

XLSX_WIDTHS = [18, 8, 55, 28, 28, 28, 28, 14, 12, 9, 9, 9, 9, 13, 12, 35, 25, 10]


def question_to_row(q: Question, enabled: bool = True) -> list:
    """Convert Question to Excel row."""
    return [
        q.id, q.round, q.text,
        q.options[0] if len(q.options) > 0 else "",
        q.options[1] if len(q.options) > 1 else "",
        q.options[2] if len(q.options) > 2 else "",
        q.options[3] if len(q.options) > 3 else "",
        q.correct_index, q.difficulty,
        getattr(q, "points_first_attempt", 3),
        getattr(q, "points_second_attempt", 2),
        getattr(q, "points_third_attempt", 1),
        getattr(q, "points_fourth_attempt", 0),
        getattr(q, "max_attempts", 3),
        q.media.type.value,
        q.media.path or "",
        ",".join(getattr(q, "tags", [])),
        "YES" if enabled else "NO",
    ]


def row_to_question(row: dict, row_num: int) -> tuple[Question, bool]:
    """Convert Excel row to Question. Returns (Question, is_enabled)."""
    def _str(key, default=""):
        v = row.get(key, default)
        return str(v).strip() if v is not None else default

    def _int(key, default=0):
        try:
            return int(row.get(key, default))
        except (ValueError, TypeError):
            return default

    qid = _str("id") or f"q_{uuid.uuid4().hex[:8]}"
    rnd = _int("round", 1) or 1
    text = _str("text")
    if not text:
        raise ValueError(f"Row {row_num}: empty question text")

    options = [_str("option_a"), _str("option_b"), _str("option_c"), _str("option_d")]
    options = [o for o in options if o]
    if len(options) < 2:
        raise ValueError(f"Row {row_num}: need 2+ options")

    correct_index = _int("correct_index", 0)
    if not (0 <= correct_index < len(options)):
        raise ValueError(f"Row {row_num}: correct_index out of range")

    difficulty = _str("difficulty", "medium").lower()
    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"

    media_type_str = _str("media_type", "none").lower()
    if media_type_str not in ("none", "image", "audio", "video"):
        media_type_str = "none"
    media_type = MediaType(media_type_str)
    media_path = _str("media_path") or None

    tags_raw = _str("tags")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
    
    # Read enabled status (default to YES if missing)
    enabled_str = _str("enabled", "YES").upper()
    is_enabled = enabled_str in ("YES", "Y", "TRUE", "1", "ENABLED")

    q = Question(
        id=qid, round=rnd, text=text, options=options, correct_index=correct_index,
        media=Media(type=media_type, path=media_path),
        difficulty=difficulty, tags=tags,
        points_first_attempt=_int("points_first_attempt", 3),
        points_second_attempt=_int("points_second_attempt", 2),
        points_third_attempt=_int("points_third_attempt", 1),
        points_fourth_attempt=_int("points_fourth_attempt", 0),
        max_attempts=max(1, min(4, _int("max_attempts", 3))),
    )
    
    return q, is_enabled


def export_to_excel(questions: List[Question], path: Path, disabled_ids: set = None, config: "GameConfig | None" = None) -> None:
    """Save questions to Excel — clean white/light theme."""
    if disabled_ids is None:
        disabled_ids = set()

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"

    # ── Palette (white mode) ─────────────────────────────────────────────────
    HDR_BG     = "1F4E79"   # dark blue header
    HDR_FG     = "FFFFFF"   # white header text
    ROW_EVEN   = "FFFFFF"   # white
    ROW_ODD    = "EBF3FB"   # very light blue tint
    BORDER_CLR = "BDD7EE"   # soft blue-grey border

    DIFF_COLORS = {
        "easy":   "1E8449",   # dark green  — readable on white
        "medium": "B7770D",   # dark amber
        "hard":   "C0392B",   # dark red
    }
    CORRECT_COLOR  = "1F4E79"   # dark blue for correct-index col
    DISABLED_COLOR = "C0392B"   # red for NO
    ENABLED_COLOR  = "1E8449"   # green for YES

    thin   = Side(border_style="thin",   color=BORDER_CLR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # ── Header row ───────────────────────────────────────────────────────────
    hdr_font  = Font(name="Calibri", bold=True, color=HDR_FG, size=11)
    hdr_fill  = PatternFill("solid", fgColor=HDR_BG)
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 36

    for col_idx, header in enumerate(XLSX_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font      = hdr_font
        cell.fill      = hdr_fill
        cell.alignment = hdr_align
        cell.border    = border

    # ── Data rows ────────────────────────────────────────────────────────────
    for row_idx, q in enumerate(questions, start=2):
        is_enabled = q.id not in disabled_ids
        row_data   = question_to_row(q, is_enabled)
        bg_hex     = ROW_EVEN if row_idx % 2 == 0 else ROW_ODD
        row_fill   = PatternFill("solid", fgColor=bg_hex)
        ws.row_dimensions[row_idx].height = 22

        for col_idx, value in enumerate(row_data, start=1):
            cell           = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill      = row_fill
            cell.border    = border
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=(col_idx == 3),
                horizontal="left" if col_idx == 3 else "center",
            )

            if col_idx == 8:    # Correct (0-3)
                cell.font = Font(name="Calibri", bold=True, color=CORRECT_COLOR, size=11)
            elif col_idx == 9:  # Difficulty
                color = DIFF_COLORS.get(str(value).lower(), "555555")
                cell.font = Font(name="Calibri", bold=True, color=color, size=11)
            elif col_idx == 3:  # Question text
                cell.font = Font(name="Calibri", bold=True, color="1A1A1A", size=11)
            elif col_idx == 18: # Enabled
                color = ENABLED_COLOR if value == "YES" else DISABLED_COLOR
                cell.font = Font(name="Calibri", bold=True, color=color, size=11)
            elif col_idx == 1:  # ID (smaller, grey)
                cell.font = Font(name="Calibri", color="888888", size=10, italic=True)
            else:
                cell.font = Font(name="Calibri", color="333333", size=11)

    # ── Column widths ────────────────────────────────────────────────────────
    for col_idx, width in enumerate(XLSX_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.freeze_panes = "A2"

    # ── Instructions sheet ───────────────────────────────────────────────────
    ws2 = wb.create_sheet("📖 Instructions")
    ws2.column_dimensions["A"].width = 80
    ws2.sheet_view.showGridLines = False

    instructions = [
        ("Football Trivia — Excel Format Guide", True),
        ("", False),
        ("COLUMNS", True),
        ("• ID: unique ID (auto-generated if empty)", False),
        ("• Round: 1-10", False),
        ("• Question Text: the question (required for all types)", False),
        ("• Options A-D: answer choices (min 2)", False),
        ("• Correct (0-3): 0=A, 1=B, 2=C, 3=D", False),
        ("• Difficulty: easy | medium | hard", False),
        ("• Pts 1st-4th: points awarded per attempt", False),
        ("• Max Attempts: 1-4", False),
        ("• Media Type: none | image | audio | video", False),
        ("• Media Path: relative file path", False),
        ("• Tags: comma-separated", False),
        ("• Enabled: YES = active in game,  NO = disabled but kept", False),
        ("", False),
        ("WORKFLOW", True),
        ("1. Load this file in the Admin Dashboard", False),
        ("2. Enable/disable questions with checkboxes", False),
        ("3. Save — selection state is preserved in the Enabled column", False),
        ("4. Export Selected to create a filtered sub-pack", False),
    ]

    for r, (text, bold) in enumerate(instructions, start=1):
        cell = ws2.cell(row=r, column=1, value=text)
        if bold:
            cell.font = Font(name="Calibri", bold=True, color="1F4E79", size=13)
        else:
            cell.font = Font(name="Calibri", color="333333", size=11)

    # ── Config sheet ─────────────────────────────────────────────────────────
    if config is not None:
        ws_cfg = wb.create_sheet("Config")
        ws_cfg.column_dimensions["A"].width = 30
        ws_cfg.column_dimensions["B"].width = 30
        ws_cfg.sheet_view.showGridLines = False

        cfg_hdr_font  = Font(name="Calibri", bold=True, color=HDR_FG, size=11)
        cfg_hdr_fill  = PatternFill("solid", fgColor=HDR_BG)
        cfg_val_font  = Font(name="Calibri", color="333333", size=11)

        # Header row
        for col, txt in enumerate(["Setting", "Value"], start=1):
            c = ws_cfg.cell(row=1, column=col, value=txt)
            c.font  = cfg_hdr_font
            c.fill  = cfg_hdr_fill
            c.alignment = Alignment(horizontal="center", vertical="center")

        cfg_rows = [
            ("name",                       config.name),
            ("rounds",                     config.rounds),
            ("questions_per_round",        config.questions_per_round),
            ("timer_seconds",              config.timer_seconds),
            ("answer_seconds",             config.answer_seconds),
            ("shuffle_questions",          config.shuffle_questions),
            ("enable_cascading_attempts",  getattr(config, "enable_cascading_attempts", True)),
            ("penalty_for_wrong",          getattr(config, "penalty_for_wrong", 0)),
        ]

        for row_idx, (key, val) in enumerate(cfg_rows, start=2):
            ka = ws_cfg.cell(row=row_idx, column=1, value=key)
            va = ws_cfg.cell(row=row_idx, column=2, value=str(val))
            ka.font = Font(name="Calibri", bold=True, color="1F4E79", size=11)
            va.font = cfg_val_font
            bg = PatternFill("solid", fgColor="FFFFFF" if row_idx % 2 == 0 else "EBF3FB")
            ka.fill = va.fill = bg

    wb.save(path)


def import_from_excel(path: Path) -> tuple[List[Question], set, dict]:
    """Load questions from Excel. Returns (questions, disabled_ids, config_dict).
    config_dict is empty if no Config sheet exists (backwards-compatible).
    """
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    ws = wb["Questions"] if "Questions" in wb.sheetnames else wb.active

    header_map = {}
    for col in ws.iter_cols(min_row=1, max_row=1):
        for cell in col:
            if cell.value:
                header_val = str(cell.value).strip()
                for idx, hdr in enumerate(XLSX_HEADERS):
                    if hdr.lower() == header_val.lower():
                        header_map[XLSX_COLUMNS[idx]] = cell.column
                        break
                else:
                    for key in XLSX_COLUMNS:
                        if key.lower() == header_val.lower():
                            header_map[key] = cell.column
                            break

    if not header_map:
        raise ValueError("No recognized headers in Excel file")

    questions = []
    disabled_ids = set()
    errors = []

    for row_idx in range(2, ws.max_row + 1):
        row_dict = {}
        is_empty = True
        for key, col_num in header_map.items():
            val = ws.cell(row=row_idx, column=col_num).value
            row_dict[key] = val
            if val is not None and str(val).strip():
                is_empty = False

        if is_empty:
            continue

        try:
            q, is_enabled = row_to_question(row_dict, row_idx)
            questions.append(q)
            if not is_enabled:
                disabled_ids.add(q.id)
        except ValueError as e:
            errors.append(str(e))

    if errors:
        raise ValueError("Import errors:\n" + "\n".join(errors))

    if not questions:
        raise ValueError("No valid questions in Excel")

    # ── Config sheet (optional — older files won't have it) ───────────────────
    config_dict = {}
    if "Config" in wb.sheetnames:
        ws_cfg = wb["Config"]
        for row in ws_cfg.iter_rows(min_row=2, values_only=True):
            if row[0] and row[1] is not None:
                config_dict[str(row[0]).strip()] = str(row[1]).strip()

    return questions, disabled_ids, config_dict


# ═══════════════════════════════════════════════════════════════
# QUESTION LIST ITEM
# ═══════════════════════════════════════════════════════════════

class QuestionListItem(QFrame):
    edit_clicked = Signal(str)
    delete_clicked = Signal(str)
    duplicate_clicked = Signal(str)
    toggle_clicked = Signal(str, bool)

    def __init__(self, question: Question, index: int, enabled: bool = True):
        super().__init__()
        self.question = question
        self.index = index
        self._enabled = enabled
        self._apply_frame_style()

        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 10, 12, 10)

        self.chk = QCheckBox()
        self.chk.setChecked(self._enabled)
        self.chk.setFixedWidth(24)
        self.chk.setStyleSheet(
            "QCheckBox { background: transparent; border: none; }"
            "QCheckBox::indicator { width: 22px; height: 22px; border-radius: 4px; }"
            "QCheckBox::indicator:unchecked { background: rgba(80,80,80,0.4); border: 2px solid #666; }"
            "QCheckBox::indicator:checked { background: #39FF14; border: 2px solid #39FF14; }"
        )
        self.chk.stateChanged.connect(self._on_toggle)

        num = QLabel(f"#{index + 1}")
        num.setFixedWidth(45)
        num.setStyleSheet("font-size: 16px; font-weight: 900; color: #39FF14;")

        info = QVBoxLayout()
        info.setSpacing(6)

        txt = QLabel(question.text[:70] + "…" if len(question.text) > 70 else question.text)
        txt.setWordWrap(False)
        txt.setStyleSheet("font-size: 14px; font-weight: 700; color: white;")

        meta = QHBoxLayout()
        meta.setSpacing(12)

        # Media type badge if not none
        media_type = getattr(question.media, 'type', None)
        if media_type and media_type.value != 'none':
            media_icons = {'image': ('🖼️', '#5ddbff'), 'audio': ('🔊', '#a855f7'), 'video': ('🎬', '#f97316')}
            icon, col = media_icons.get(media_type.value, ('📎', '#888'))
            ml = QLabel(f"{icon} {media_type.value.upper()}")
            ml.setStyleSheet(
                f"font-size: 10px; font-weight: 900; color: {col}; "
                f"background: rgba(0,0,0,0.3); border: 1px solid {col}; "
                f"border-radius: 4px; padding: 2px 6px;"
            )
            meta.addWidget(ml)

        for t, c in [
            (f"Round {question.round}", "rgba(255,255,255,0.6)"),
            (f"● {question.difficulty.upper()}", {"easy": "#2ecc71", "medium": "#f39c12", "hard": "#e74c3c"}.get(question.difficulty, "#888")),
            (f"⭐ {getattr(question,'points_first_attempt',3)} pts", "#ffd700"),
        ]:
            l = QLabel(t)
            l.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {c};")
            meta.addWidget(l)
        
        # Enabled/disabled badge (store reference for updates)
        self.status_badge = QLabel()
        self._update_badge()
        meta.addWidget(self.status_badge)
        
        meta.addStretch()

        info.addWidget(txt)
        info.addLayout(meta)

        btns = QHBoxLayout()
        btns.setSpacing(6)

        be = QPushButton("✏️")
        bd = QPushButton("📋")
        bx = QPushButton("🗑️")

        for b in (be, bd):
            b.setFixedSize(38, 38)
            b.setStyleSheet(
                "QPushButton { background: rgba(57,255,20,0.15); border: 1px solid #39FF14; "
                "border-radius: 6px; color: white; font-size: 16px; } "
                "QPushButton:hover { background: rgba(57,255,20,0.3); }"
            )

        bx.setFixedSize(38, 38)
        bx.setStyleSheet(
            "QPushButton { background: rgba(231,76,60,0.15); border: 1px solid #e74c3c; "
            "border-radius: 6px; color: white; font-size: 16px; } "
            "QPushButton:hover { background: rgba(231,76,60,0.3); }"
        )

        be.clicked.connect(lambda: self.edit_clicked.emit(question.id))
        bd.clicked.connect(lambda: self.duplicate_clicked.emit(question.id))
        bx.clicked.connect(lambda: self.delete_clicked.emit(question.id))

        btns.addWidget(be)
        btns.addWidget(bd)
        btns.addWidget(bx)

        layout.addWidget(self.chk)
        layout.addWidget(num)
        layout.addLayout(info, stretch=1)
        layout.addLayout(btns)
    
    def _update_badge(self):
        """Update the status badge appearance"""
        if self._enabled:
            self.status_badge.setText("✓ ENABLED")
            self.status_badge.setStyleSheet(
                "font-size: 10px; font-weight: 900; color: #39FF14; "
                "background: rgba(57,255,20,0.2); border: 1px solid #39FF14; "
                "border-radius: 4px; padding: 3px 8px;"
            )
        else:
            self.status_badge.setText("✗ DISABLED")
            self.status_badge.setStyleSheet(
                "font-size: 10px; font-weight: 900; color: #e74c3c; "
                "background: rgba(231,76,60,0.2); border: 1px solid #e74c3c; "
                "border-radius: 4px; padding: 3px 8px;"
            )

    def _apply_frame_style(self):
        if self._enabled:
            self.setStyleSheet(
                "QFrame { background: rgba(20,35,50,0.95); border-left: 5px solid #39FF14; "
                "border-radius: 10px; padding: 0px; margin: 4px 2px; }"
                "QFrame:hover { background: rgba(25,40,60,1.0); border-left: 5px solid #5ddbff; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: rgba(15,20,30,0.8); border-left: 5px solid #e74c3c; "
                "border-radius: 10px; padding: 0px; margin: 4px 2px; }"
                "QFrame:hover { background: rgba(20,25,35,0.9); border-left: 5px solid #ff6b6b; }"
            )

    def _on_toggle(self, state: int):
        self._enabled = bool(state)
        self._apply_frame_style()
        self._update_badge()  # Update badge when toggled
        self.toggle_clicked.emit(self.question.id, self._enabled)

    def update_enabled(self, enabled: bool):
        """Update enabled state without emitting toggle_clicked.

        Called by AdminDashboard._ref() fast path when disabled_ids changes
        externally (e.g. Select All / Deselect All) so the widget's visual
        state stays in sync without triggering another _sync_to_engine call.

        Previously this method was missing, so _ref()'s ``hasattr`` guard
        always returned False, the fast path silently did nothing, and item
        styling was left stale after programmatic enable/disable operations.
        """
        if self._enabled == enabled:
            return
        # Block checkbox signal so we don't re-emit toggle_clicked
        self.chk.blockSignals(True)
        self._enabled = enabled
        self.chk.setChecked(enabled)
        self.chk.blockSignals(False)
        self._apply_frame_style()
        self._update_badge()


# ═══════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ═══════════════════════════════════════════════════════════════

class AdminDashboard(QWidget):
    config_changed = Signal(GameConfig)
    questions_changed = Signal(list)
    pack_saved = Signal(str)  # Emitted when Excel file is saved
    
    def __init__(self, config: GameConfig, questions: list):
        super().__init__()
        self.config = config
        self.questions: List[Question] = questions.copy()
        self.current_question_id: Optional[str] = None
        self.disabled_ids: set = set()
        self.current_excel_path: Optional[Path] = None
        self.has_unsaved_changes: bool = False
        # FIX L: track whether a game is actively running so _tog() does not
        # push question-list changes to the engine mid-game and silently reset
        # scores / current question.
        self._game_active: bool = False

        # ── Build UI once (FIX BUG-1: was incorrectly inside set_game_active) ─
        self._build_ui()

    def _build_ui(self):
        """Build the entire dashboard UI. Called once from __init__."""
        self.setStyleSheet("QWidget { background: #0d1b2a; }")
        self.setMinimumSize(1400, 900)

        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(15)

        # Header
        hdr_lay = QHBoxLayout()
        hdr = QLabel("⚙️ EXCEL QUESTION MANAGER")
        hdr.setStyleSheet("font-size: 24px; font-weight: 900; color: #39FF14; letter-spacing: 2px; padding: 10px;")

        bl = QPushButton("📂 Load Excel")
        bs = QPushButton("💾 Save Excel")
        ba = QPushButton("💾 Save As")
        bx = QPushButton("📤 Export Selected")

        for b in (bl, bs, ba, bx):
            b.setStyleSheet(self._btn())
            b.setMinimumHeight(45)

        bl.clicked.connect(self._load)
        bs.clicked.connect(self._save)
        ba.clicked.connect(self._save_as)
        bx.clicked.connect(self._export)

        hdr_lay.addWidget(hdr)
        hdr_lay.addStretch()
        hdr_lay.addWidget(bl)
        hdr_lay.addWidget(bs)
        hdr_lay.addWidget(ba)
        hdr_lay.addWidget(bx)

        root.addLayout(hdr_lay)

        self.file_lbl = QLabel("📂 Click '📂 Load Excel' to get started • No file loaded")
        self.file_lbl.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,0.5); "
            "background: rgba(20,30,45,0.3); border: 1px solid rgba(255,255,255,0.1); "
            "border-radius: 6px; padding: 8px 12px; text-align: center;"
        )
        root.addWidget(self.file_lbl)

        from PySide6.QtWidgets import QTabWidget
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane { border: 2px solid rgba(57,255,20,0.3); "
            "border-radius: 8px; background: rgba(20,30,45,0.3); }"
            "QTabBar::tab { background: rgba(20,30,45,0.5); "
            "border: 2px solid rgba(57,255,20,0.3); border-bottom: none; "
            "border-radius: 6px 6px 0 0; padding: 10px 20px; margin-right: 3px; "
            "color: white; font-weight: 700; }"
            "QTabBar::tab:selected { background: rgba(57,255,20,0.2); border-color: #39FF14; }"
        )

        tabs.addTab(self._create_questions_tab(), "📝 Questions")
        tabs.addTab(self._create_settings_tab(), "⚙️ Settings")

        root.addWidget(tabs, stretch=1)

        bot = QHBoxLayout()
        self.status = QLabel("Ready")
        self.status.setStyleSheet("font-size: 11px; color: #39FF14; font-weight: 700;")

        bc = QPushButton("✖️ Close")
        bc.setMinimumHeight(45)
        bc.setStyleSheet(self._btn())
        bc.clicked.connect(self.close)

        bot.addWidget(self.status)
        bot.addStretch()
        bot.addWidget(bc)

        root.addLayout(bot)

    def set_game_active(self, active: bool) -> None:
        """FIX BUG-1: UI is now built in __init__. This method only toggles
        the flag so that checkbox toggles don't push changes to the engine
        mid-game and silently reset scores / current question index.
        """
        self._game_active = active

    def _mark_unsaved_changes(self):
        """Mark that there are unsaved changes"""
        self.has_unsaved_changes = True
        if self.current_excel_path:
            self.file_lbl.setText(f"📄 {self.current_excel_path.name} ● UNSAVED CHANGES")
            self.file_lbl.setStyleSheet(
                "font-size: 12px; color: #f39c12; "
                "background: rgba(243,156,18,0.15); border: 1px solid #f39c12; "
                "border-radius: 6px; padding: 8px 12px;"
            )
    
    def _clear_unsaved_changes(self):
        """Clear unsaved changes flag"""
        self.has_unsaved_changes = False
        if self.current_excel_path:
            self.file_lbl.setText(f"📄 {self.current_excel_path.name}")
            self.file_lbl.setStyleSheet(
                "font-size: 12px; color: rgba(255,255,255,0.7); "
                "background: rgba(20,30,45,0.6); border: 1px solid rgba(57,255,20,0.2); "
                "border-radius: 6px; padding: 8px 12px;"
            )
    
    def closeEvent(self, event):
        """Auto-save selection state to Excel before closing"""
        # Only prompt if we have unsaved changes
        if self.current_excel_path and self.questions and self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "💾 Unsaved Changes",
                f"<b>You have unsaved changes!</b><br><br>"
                f"File: {self.current_excel_path.name}<br>"
                f"Enabled: {len(self.questions) - len(self.disabled_ids)}<br>"
                f"Disabled: {len(self.disabled_ids)}<br><br>"
                f"Save changes before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Yes:
                try:
                    export_to_excel(self.questions, self.current_excel_path, self.disabled_ids)
                    self.pack_saved.emit(str(self.current_excel_path))
                    self._sync_to_engine()
                    self._clear_unsaved_changes()
                    print(f"[AUTO-SAVE] Selection state saved to {self.current_excel_path.name}")
                    event.accept()
                except Exception as e:
                    QMessageBox.critical(self, "Save Failed", f"Could not save:\n{e}")
                    event.ignore()
            elif reply == QMessageBox.No:
                # Close without saving
                event.accept()
            else:
                # Cancel close
                event.ignore()
        else:
            # No unsaved changes, just close
            event.accept()
    
    # ═══════════════════════════════════════════════════════════
    # TAB 1: QUESTIONS LIST & EDITOR
    # ═══════════════════════════════════════════════════════════
    
    def _create_questions_tab(self):
        """Questions management tab with list and editor"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)
        
        # Stats bar at top
        stats_frame = QFrame()
        stats_frame.setStyleSheet(
            "QFrame { background: rgba(20,30,45,0.5); border: 1px solid rgba(57,255,20,0.2); "
            "border-radius: 8px; padding: 10px; }"
        )
        stats_lay = QHBoxLayout(stats_frame)
        stats_lay.setSpacing(10)
        
        self.c_tot = self._mini_card("Total", "0", "#3498db")
        self.c_sel = self._mini_card("Enabled", "0", "#2ecc71")
        self.c_easy = self._mini_card("Easy", "0", "#2ecc71")
        self.c_med = self._mini_card("Medium", "0", "#f39c12")
        self.c_hard = self._mini_card("Hard", "0", "#e74c3c")
        
        for c in (self.c_tot, self.c_sel, self.c_easy, self.c_med, self.c_hard):
            stats_lay.addWidget(c)
        
        stats_lay.addStretch()
        lay.addWidget(stats_frame)
        self._upd_stats()
        
        split = QSplitter(Qt.Horizontal)
        split.setStyleSheet("QSplitter::handle { background: rgba(57,255,20,0.2); width: 3px; }")
        
        split.addWidget(self._qlist())
        split.addWidget(self._editor())
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        
        lay.addWidget(split)
        return w
    
    # ═══════════════════════════════════════════════════════════
    # TAB 3: GAME SETTINGS
    # ═══════════════════════════════════════════════════════════
    
    def _create_settings_tab(self):
        """Game settings configuration"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(20)
        
        settings_lbl = QLabel("⚙️ GAME CONFIGURATION")
        settings_lbl.setStyleSheet("font-size: 18px; font-weight: 900; color: #39FF14;")
        lay.addWidget(settings_lbl)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        form = QFormLayout(content)
        form.setSpacing(15)
        form.setHorizontalSpacing(20)
        
        # Pack name
        self.pack_name = QLineEdit(self.config.name)
        self.pack_name.setStyleSheet(self._inp())
        form.addRow(self._l("Pack Name:"), self.pack_name)
        
        # Rounds
        self.rounds_spin = self._sp(1, 10, self.config.rounds)
        form.addRow(self._l("Number of Rounds:"), self.rounds_spin)
        
        # Questions per round
        self.qpr_spin = self._sp(1, 100, self.config.questions_per_round)
        form.addRow(self._l("Questions per Round:"), self.qpr_spin)
        
        # Timer
        self.timer_spin = self._sp(5, 120, self.config.timer_seconds)
        form.addRow(self._l("Timer (seconds):"), self.timer_spin)
        
        # Answer time
        self.answer_spin = self._sp(3, 60, self.config.answer_seconds)
        form.addRow(self._l("Answer Time (seconds):"), self.answer_spin)
        
        # Shuffle
        self.shuffle_chk = QCheckBox("Shuffle question order")
        self.shuffle_chk.setChecked(self.config.shuffle_questions)
        self.shuffle_chk.setStyleSheet("color: white; font-size: 13px;")
        form.addRow(self._l("Shuffle:"), self.shuffle_chk)
        
        # Cascading attempts
        sep = QLabel("── Cascading Attempts ──")
        sep.setStyleSheet("font-size: 13px; font-weight: 900; color: #39FF14; padding-top: 10px;")
        form.addRow("", sep)
        
        self.cascade_chk = QCheckBox("Enable cascading attempts")
        self.cascade_chk.setChecked(getattr(self.config, "enable_cascading_attempts", True))
        self.cascade_chk.setStyleSheet("color: white; font-size: 13px;")
        form.addRow(self._l("Mode:"), self.cascade_chk)
        
        self.penalty_spin = self._sp(0, 10, getattr(self.config, "penalty_for_wrong", 0))
        form.addRow(self._l("Penalty (wrong):"), self.penalty_spin)
        
        # Save settings button
        save_btn = QPushButton("💾 Save Settings")
        save_btn.setMinimumHeight(45)
        save_btn.setStyleSheet(self._btn())
        save_btn.clicked.connect(self._save_settings)
        form.addRow("", save_btn)
        
        scroll.setWidget(content)
        lay.addWidget(scroll)
        
        return w
    
    def _save_settings(self):
        """Save game settings to config.

        FIX: GameConfig is a frozen=True dataclass, so direct attribute
        assignment raises FrozenInstanceError at runtime.  Use dataclasses.replace()
        to produce a new config object, then emit config_changed so the engine's
        update_config() receives the new values.  Previously config_changed was
        never emitted from here, making the Settings tab completely non-functional.
        """
        import dataclasses
        kwargs = dict(
            name=self.pack_name.text().strip() or self.config.name,
            rounds=self.rounds_spin.value(),
            questions_per_round=self.qpr_spin.value(),
            timer_seconds=self.timer_spin.value(),
            answer_seconds=self.answer_spin.value(),
            shuffle_questions=self.shuffle_chk.isChecked(),
        )
        if hasattr(self.config, 'enable_cascading_attempts'):
            kwargs['enable_cascading_attempts'] = self.cascade_chk.isChecked()
        if hasattr(self.config, 'penalty_for_wrong'):
            kwargs['penalty_for_wrong'] = self.penalty_spin.value()

        self.config = dataclasses.replace(self.config, **kwargs)

        # FIX: emit so engine.update_config() receives the new values
        self.config_changed.emit(self.config)

        # Also persist config to the Excel file immediately if one is loaded,
        # so the user doesn't need to click Save separately just to store settings.
        if self.current_excel_path and self.current_excel_path.exists():
            try:
                export_to_excel(self.questions, self.current_excel_path, self.disabled_ids, config=self.config)
                self.status.setText("✅ Settings saved to Excel")
            except Exception as e:
                self.status.setText(f"⚠️ Settings applied but Excel write failed: {e}")
        else:
            self.status.setText("✅ Settings saved (load an Excel file to persist)")

        QMessageBox.information(self, "Success", "Game settings saved!")
    
    def _qlist(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        
        h = QHBoxLayout()
        self.lbl = QLabel(f"📝 Questions ({len(self.questions)})")
        self.lbl.setStyleSheet("font-size: 16px; font-weight: 900; color: white;")
        
        # Filter dropdown
        filter_label = QLabel("Show:")
        filter_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.7);")
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Questions", "Enabled Only", "Disabled Only"])
        self.filter_combo.setCurrentIndex(0)
        self.filter_combo.setStyleSheet(self._inp())
        self.filter_combo.currentIndexChanged.connect(self._ref)
        
        ba = QPushButton("☑️ Select All")
        bn = QPushButton("☐ Deselect All")
        bw = QPushButton("➕ New")
        
        for b in (ba, bn, bw):
            b.setStyleSheet(self._sbtn())
        
        ba.clicked.connect(self._sel_all)
        bn.clicked.connect(self._desel_all)
        bw.clicked.connect(self._new)
        
        h.addWidget(self.lbl)
        h.addStretch()
        h.addWidget(filter_label)
        h.addWidget(self.filter_combo)
        h.addWidget(ba)
        h.addWidget(bn)
        h.addWidget(bw)
        
        lay.addLayout(h)
        
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setStyleSheet(
            "QScrollArea { border: 2px solid rgba(57,255,20,0.3); "
            "border-radius: 10px; background: rgba(10,15,25,0.6); }"
            "QScrollBar:vertical { background: rgba(20,30,45,0.5); width: 12px; border-radius: 6px; }"
            "QScrollBar::handle:vertical { background: rgba(57,255,20,0.3); border-radius: 6px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(57,255,20,0.5); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        
        list_container = QWidget()
        self.qlay = QVBoxLayout(list_container)
        self.qlay.setSpacing(2)
        self.qlay.setContentsMargins(8, 8, 8, 8)
        
        # Add placeholder if no questions loaded
        if not self.questions:
            placeholder = QLabel(
                "📂 No Excel file loaded yet\n\n"
                "Click '📂 Load Excel' button at the top\n"
                "to import questions from an .xlsx file"
            )
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(
                "color: rgba(255,255,255,0.5); font-size: 14px; "
                "padding: 50px; background: transparent;"
            )
            self.qlay.addWidget(placeholder)
        
        sc.setWidget(list_container)
        lay.addWidget(sc, stretch=1)
        
        self._ref()
        return w
    
    def _editor(self):
        self.eg = QGroupBox("✏️ QUESTION EDITOR")
        self.eg.setEnabled(False)
        self.eg.setStyleSheet(
            "QGroupBox { font-size: 16px; font-weight: 900; color: #39FF14; "
            "border: 2px solid rgba(57,255,20,0.3); border-radius: 10px; "
            "margin-top: 12px; padding: 15px; background: rgba(20,30,45,0.3); }"
            "QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 8px; }"
            "QGroupBox:disabled { color: #666; border-color: #444; }"
        )
        
        lay = QVBoxLayout(self.eg)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        cnt = QWidget()
        fm = QFormLayout(cnt)
        fm.setSpacing(12)
        fm.setHorizontalSpacing(15)
        
        self.er = self._sp(1, 10, 1)
        fm.addRow(self._l("Round:"), self.er)
        
        self.et = QTextEdit()
        self.et.setPlaceholderText("Enter question text... (required for all question types)")
        self.et.setMaximumHeight(100)
        self.et.setStyleSheet(self._inp())
        
        # Label that updates based on media type to guide the user
        self.question_label = QLabel("Question Text:")
        self.question_label.setStyleSheet("font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.8);")
        fm.addRow(self.question_label, self.et)
        
        self.eo = []
        for i in range(4):
            o = QLineEdit()
            o.setPlaceholderText(f"Option {chr(65+i)}...")
            o.setStyleSheet(self._inp())
            self.eo.append(o)
            fm.addRow(self._l(f"Option {chr(65+i)}:"), o)
        
        self.ec = QComboBox()
        self.ec.addItems(["A", "B", "C", "D"])
        self.ec.setStyleSheet(self._inp())
        fm.addRow(self._l("Correct:"), self.ec)
        
        self.ed = QComboBox()
        self.ed.addItems(["Easy", "Medium", "Hard"])
        self.ed.setCurrentIndex(1)
        self.ed.setStyleSheet(self._inp())
        fm.addRow(self._l("Difficulty:"), self.ed)
        
        s = QLabel("⭐ SCORING")
        s.setStyleSheet("font-size: 14px; font-weight: 900; color: #39FF14; padding-top: 10px;")
        fm.addRow("", s)
        
        self.ep1 = self._sp(0, 20, 3)
        self.ep2 = self._sp(0, 20, 2)
        self.ep3 = self._sp(0, 20, 1)
        self.ep4 = self._sp(0, 20, 0)
        self.ema = self._sp(1, 4, 3)
        
        fm.addRow(self._l("Pts - 1st:"), self.ep1)
        fm.addRow(self._l("Pts - 2nd:"), self.ep2)
        fm.addRow(self._l("Pts - 3rd:"), self.ep3)
        fm.addRow(self._l("Pts - 4th:"), self.ep4)
        fm.addRow(self._l("Max Att:"), self.ema)
        
        s2 = QLabel("📎 MEDIA")
        s2.setStyleSheet("font-size: 14px; font-weight: 900; color: #39FF14; padding-top: 10px;")
        fm.addRow("", s2)
        
        mr = QHBoxLayout()
        self.emt = QComboBox()
        self.emt.addItems(["None", "Image", "Audio", "Video"])
        self.emt.currentTextChanged.connect(self._mt_ch)
        self.emt.setStyleSheet(self._inp())
        
        self.bb = QPushButton("📁 Browse")
        self.bb.setEnabled(False)
        self.bb.clicked.connect(self._br)
        self.bb.setStyleSheet(self._sbtn())
        
        mr.addWidget(self.emt, stretch=1)
        mr.addWidget(self.bb)
        fm.addRow(self._l("Type:"), mr)
        
        self.emp = QLineEdit()
        self.emp.setPlaceholderText("No media")
        self.emp.setReadOnly(True)
        self.emp.setStyleSheet(self._inp())
        fm.addRow(self._l("Path:"), self.emp)
        
        br = QHBoxLayout()
        bsv = QPushButton("💾 Save")
        bcn = QPushButton("✖️ Cancel")
        
        for b in (bsv, bcn):
            b.setMinimumHeight(40)
            b.setStyleSheet(self._btn())
        
        bsv.clicked.connect(self._sv_q)
        bcn.clicked.connect(self._cn)
        
        br.addWidget(bsv)
        br.addWidget(bcn)
        fm.addRow("", br)
        
        sc.setWidget(cnt)
        lay.addWidget(sc)
        return self.eg
    
    def _apply_config_dict(self, cfg: dict):
        """Apply a config dict (loaded from Excel Config sheet) to the UI spinboxes
        and emit config_changed so the engine receives the values immediately."""
        import dataclasses

        def _int(key, fallback):
            try:
                return int(cfg[key])
            except (KeyError, ValueError):
                return fallback

        def _bool(key, fallback):
            try:
                return cfg[key].lower() in ("true", "1", "yes")
            except (KeyError, AttributeError):
                return fallback

        def _str(key, fallback):
            return cfg.get(key, fallback) or fallback

        name       = _str("name",  self.config.name)
        rounds     = _int("rounds", self.config.rounds)
        qpr        = _int("questions_per_round", self.config.questions_per_round)
        timer      = _int("timer_seconds", self.config.timer_seconds)
        answer     = _int("answer_seconds", self.config.answer_seconds)
        shuffle    = _bool("shuffle_questions", self.config.shuffle_questions)
        cascade    = _bool("enable_cascading_attempts", getattr(self.config, "enable_cascading_attempts", True))
        penalty    = _int("penalty_for_wrong", getattr(self.config, "penalty_for_wrong", 0))

        # Update the Settings tab widgets so the user sees the loaded values
        self.pack_name.setText(name)
        self.rounds_spin.setValue(rounds)
        self.qpr_spin.setValue(qpr)
        self.timer_spin.setValue(timer)
        self.answer_spin.setValue(answer)
        self.shuffle_chk.setChecked(shuffle)
        if hasattr(self, "cascade_chk"):
            self.cascade_chk.setChecked(cascade)
        if hasattr(self, "penalty_spin"):
            self.penalty_spin.setValue(penalty)

        # Build and store the new config, emit to engine
        kwargs = dict(
            name=name, rounds=rounds, questions_per_round=qpr,
            timer_seconds=timer, answer_seconds=answer, shuffle_questions=shuffle,
        )
        if hasattr(self.config, "enable_cascading_attempts"):
            kwargs["enable_cascading_attempts"] = cascade
        if hasattr(self.config, "penalty_for_wrong"):
            kwargs["penalty_for_wrong"] = penalty

        self.config = dataclasses.replace(self.config, **kwargs)
        self.config_changed.emit(self.config)
        print(f"[CONFIG] Loaded from Excel: rounds={rounds}, qpr={qpr}, timer={timer}s")

    def _load(self):
        """Load questions from Excel file with detailed feedback"""
        p, _ = QFileDialog.getOpenFileName(
            self, 
            "Load Questions from Excel", 
            "", 
            "Excel Files (*.xlsx *.xls)"
        )
        if not p:
            return
        
        try:
            # Show loading status
            self.status.setText("⏳ Loading Excel file...")
            
            ld, disabled, config_dict = import_from_excel(Path(p))
            self.questions = ld
            self.disabled_ids = disabled  # Load saved selection state
            self.current_excel_path = Path(p)
            
            enabled_count = len(ld) - len(disabled)
            
            # ── Apply saved config if the file has a Config sheet ─────────────
            if config_dict:
                self._apply_config_dict(config_dict)
            
            # Update UI
            self.file_lbl.setText(f"📄 Loaded: {Path(p).name}")
            self._clear_unsaved_changes()  # Clear flag on fresh load
            self.status.setText(f"✅ Loaded {len(ld)} questions ({enabled_count} enabled)")
            
            self._ref()
            self._upd_stats()
            
            # **SYNC WITH GAME ENGINE**
            self._sync_to_engine()
            
            # Show detailed success message
            QMessageBox.information(
                self, 
                "✅ Excel Loaded Successfully",
                f"<b>File:</b> {Path(p).name}<br><br>"
                f"<b>Questions loaded:</b> {len(ld)}<br>"
                f"<b>Enabled:</b> {enabled_count}<br>"
                f"<b>Disabled:</b> {len(disabled)}<br>"
                f"<b>Game engine:</b> Updated with {enabled_count} enabled questions<br><br>"
                f"➡️ Go to the <b>'📝 Questions'</b> tab to view and edit them."
            )
            
        except Exception as e:
            self.status.setText("❌ Load failed")
            QMessageBox.critical(
                self, 
                "❌ Load Failed", 
                f"<b>Could not load Excel file:</b><br><br>"
                f"{str(e)}<br><br>"
                f"<b>Common issues:</b><br>"
                f"• File is not a valid .xlsx format<br>"
                f"• Missing required columns (ID, Round, Question Text, etc.)<br>"
                f"• Empty question text or invalid data<br><br>"
                f"Check the Excel Format Guide for correct structure."
            )
    
    def _save(self):
        if not self.current_excel_path:
            self._save_as()
            return
        try:
            export_to_excel(self.questions, self.current_excel_path, self.disabled_ids, config=self.config)
            self.status.setText(f"✅ Saved {len(self.questions)} questions")
            self.pack_saved.emit(str(self.current_excel_path))
            
            # **SYNC WITH GAME ENGINE**
            self._sync_to_engine()
            
            # Clear unsaved changes flag
            self._clear_unsaved_changes()
            
            enabled_count = len(self.questions) - len(self.disabled_ids)
            QMessageBox.information(
                self, "Success", 
                f"Saved {len(self.questions)} questions to:\n{self.current_excel_path.name}\n\n"
                f"Enabled: {enabled_count}\nDisabled: {len(self.disabled_ids)}\n\n"
                f"Game engine updated with {enabled_count} enabled questions."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed:\n{e}")
    
    def _save_as(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save As", "questions.xlsx", "Excel (*.xlsx)")
        if not p:
            return
        try:
            export_to_excel(self.questions, Path(p), self.disabled_ids, config=self.config)
            self.current_excel_path = Path(p)
            self.file_lbl.setText(f"📄 {Path(p).name}")
            self.status.setText(f"✅ Saved {len(self.questions)}")
            self.pack_saved.emit(str(Path(p)))
            
            # **SYNC WITH GAME ENGINE**
            self._sync_to_engine()
            
            # Clear unsaved changes flag
            self._clear_unsaved_changes()
            
            enabled_count = len(self.questions) - len(self.disabled_ids)
            QMessageBox.information(
                self, "Success", 
                f"Saved {len(self.questions)} questions to:\n{Path(p).name}\n\n"
                f"Enabled: {enabled_count}\nDisabled: {len(self.disabled_ids)}\n\n"
                f"Game engine updated with {enabled_count} enabled questions."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed:\n{e}")
    
    def _sync_to_engine(self):
        """Sync the *selected* question list to the game engine.

        BUG FIXED: the previous version also emitted config_changed here,
        which caused every checkbox toggle and every Excel load to overwrite
        engine.cfg with self.config — which is the value that was current when
        the AdminDashboard was first opened (or last saved via "Save Settings").

        Concrete failure scenario:
          1. User sets penalty_spin = 2 in the Settings tab.
          2. User clicks "Save Settings" → self.config updated, engine.cfg.penalty = 2 ✓
          3. User then loads an Excel file (or toggles a question checkbox).
          4. _sync_to_engine() was called, emitting config_changed(self.config).
             If self.config was already updated (step 2) this was harmless, but
             if the user had only changed the spinbox WITHOUT clicking Save yet,
             self.config still had penalty=0, silently resetting the engine.
          5. engine.cfg.penalty_for_wrong → 0 again, penalty silently dropped.

        Fix: _sync_to_engine only syncs questions. Config is the exclusive
        responsibility of _save_settings, which uses dataclasses.replace() to
        build a new config and emits config_changed only when the user
        explicitly saves.  The two concerns must not be mixed.
        """
        enabled_questions = [q for q in self.questions if q.id not in self.disabled_ids]
        self.questions_changed.emit(enabled_questions)
        print(f"[SYNC] Updated game engine: {len(enabled_questions)}/{len(self.questions)} questions")
    
    def _export(self):
        sel = [q for q in self.questions if q.id not in self.disabled_ids]
        if not sel:
            QMessageBox.warning(self, "No Selection", "No questions selected")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export Selected", "selected.xlsx", "Excel (*.xlsx)")
        if not p:
            return
        try:
            # Export only enabled questions - all marked as enabled
            export_to_excel(sel, Path(p), disabled_ids=set())
            QMessageBox.information(self, "Success", f"Exported {len(sel)} enabled questions")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{e}")
    
    def _ref(self):
        """Refresh the question list view.

        FIX: the original implementation deleted and recreated ALL QuestionListItem
        widgets on every call — including every checkbox toggle.  For 100 questions
        this meant 100 widget destructions + creations + signal reconnections per
        click.  The fix caches widgets by question id and only rebuilds when the
        question list itself changes (add/delete/reorder); toggling enabled state
        now just calls update_enabled() on the existing widget in-place.

        _ref_force() is a separate helper that clears the cache and rebuilds from
        scratch — called from _new(), _del(), _dup(), _load() etc.
        """
        # Initialise cache on first call
        if not hasattr(self, '_item_cache'):
            self._item_cache: dict = {}

        # Get filter selection
        filter_mode = 0
        if hasattr(self, 'filter_combo'):
            filter_mode = self.filter_combo.currentIndex()

        # Determine which questions to show
        filtered_questions = []
        for i, q in enumerate(self.questions):
            is_enabled = q.id not in self.disabled_ids
            if filter_mode == 1 and not is_enabled:
                continue
            elif filter_mode == 2 and is_enabled:
                continue
            filtered_questions.append((i, q, is_enabled))

        # Check whether the visible set has changed (different ids or order)
        visible_ids = [q.id for _, q, _ in filtered_questions]
        cached_ids = list(self._item_cache.keys())

        if visible_ids != cached_ids:
            # Full rebuild — remove all current widgets and repopulate cache
            while self.qlay.count():
                item_layout = self.qlay.takeAt(0)
                if item_layout.widget():
                    item_layout.widget().setParent(None)

            self._item_cache.clear()

            for i, q, enabled in filtered_questions:
                item = QuestionListItem(q, i, enabled=enabled)
                item.edit_clicked.connect(self._ed)
                item.delete_clicked.connect(self._del)
                item.duplicate_clicked.connect(self._dup)
                item.toggle_clicked.connect(self._tog)
                self.qlay.addWidget(item)
                self._item_cache[q.id] = item

            self.qlay.addStretch()
        else:
            # Fast path — only update the enabled badge on existing widgets
            for _, q, enabled in filtered_questions:
                item = self._item_cache.get(q.id)
                if item and hasattr(item, 'update_enabled'):
                    item.update_enabled(enabled)

        # Update label
        enabled_count = len(self.questions) - len(self.disabled_ids)
        disabled_count = len(self.disabled_ids)

        if filter_mode == 0:
            self.lbl.setText(f"📝 Questions ({len(self.questions)}) - {enabled_count} enabled, {disabled_count} disabled")
        elif filter_mode == 1:
            self.lbl.setText(f"📝 Questions ({enabled_count} enabled shown)")
        else:
            self.lbl.setText(f"📝 Questions ({disabled_count} disabled shown)")

    def _ref_force(self):
        """Force a full widget rebuild — call after add/delete/reorder operations."""
        if hasattr(self, '_item_cache'):
            self._item_cache.clear()
        self._ref()
    
    def _sel_all(self):
        self.disabled_ids.clear()
        self._ref()
        self._upd_stats()
        self._sync_to_engine()
        self._mark_unsaved_changes()
        self.status.setText("✅ All selected - Game engine updated")
    
    def _desel_all(self):
        self.disabled_ids = {q.id for q in self.questions}
        self._ref()
        self._upd_stats()
        self._sync_to_engine()
        self._mark_unsaved_changes()
        self.status.setText("⬜ All deselected - Game engine updated")
    
    def _tog(self, qid: str, en: bool):
        if en:
            self.disabled_ids.discard(qid)
        else:
            self.disabled_ids.add(qid)
        self._upd_stats()
        self._mark_unsaved_changes()  # Mark changes on every toggle

        # FIX L: do NOT sync to the engine while a game is running — calling
        # engine.load_questions() resets scores and current_q_idx mid-game.
        # Changes are staged here and applied only when the host explicitly
        # saves the Excel file (which calls _sync_to_engine after saving).
        if self._game_active:
            self.status.setText(
                "⚠️ Changes staged — save Excel to apply after current game"
            )
            return

        self._sync_to_engine()
    
    def _new(self):
        self.current_question_id = None
        self.eg.setEnabled(True)
        self.er.setValue(1)
        self.et.clear()
        for o in self.eo:
            o.clear()
        self.ec.setCurrentIndex(0)
        self.ed.setCurrentIndex(1)
        self.ep1.setValue(3)
        self.ep2.setValue(2)
        self.ep3.setValue(1)
        self.ep4.setValue(0)
        self.ema.setValue(3)
        self.emt.setCurrentIndex(0)
        self.emp.clear()
        self._mt_ch("None")  # Reset label/placeholder to defaults
    
    def _ed(self, qid: str):
        q = next((x for x in self.questions if x.id == qid), None)
        if not q:
            return
        self.current_question_id = qid
        self.eg.setEnabled(True)
        self.er.setValue(q.round)
        self.et.setPlainText(q.text)
        for i, o in enumerate(self.eo):
            o.setText(q.options[i] if i < len(q.options) else "")
        self.ec.setCurrentIndex(q.correct_index)
        di = {"easy": 0, "medium": 1, "hard": 2}.get(q.difficulty, 1)
        self.ed.setCurrentIndex(di)
        self.ep1.setValue(getattr(q, "points_first_attempt", 3))
        self.ep2.setValue(getattr(q, "points_second_attempt", 2))
        self.ep3.setValue(getattr(q, "points_third_attempt", 1))
        self.ep4.setValue(getattr(q, "points_fourth_attempt", 0))
        self.ema.setValue(getattr(q, "max_attempts", 3))
        mi = {MediaType.NONE: 0, MediaType.IMAGE: 1, MediaType.AUDIO: 2, MediaType.VIDEO: 3}.get(q.media.type, 0)
        self.emt.setCurrentIndex(mi)
        # Trigger label/placeholder update based on media type
        self._mt_ch(self.emt.currentText())
        if q.media.path:
            self.emp.setText(q.media.path)
        else:
            self.emp.clear()
    
    def _sv_q(self):
        t = self.et.toPlainText().strip()
        if not t:
            QMessageBox.warning(self, "Error", "Empty question")
            return
        opts = [o.text().strip() for o in self.eo]
        fill = [o for o in opts if o]
        if len(fill) < 2:
            QMessageBox.warning(self, "Error", "Need 2+ options")
            return
        ci = self.ec.currentIndex()
        if ci >= len(fill):
            QMessageBox.warning(self, "Error", "Correct out of range")
            return
        mts = self.emt.currentText().lower()
        if mts == "none":
            m = Media(type=MediaType.NONE, path=None)
        else:
            m = Media(type=MediaType(mts), path=self.emp.text().strip() or None)
        try:
            q = Question(
                id=self.current_question_id or f"q_{uuid.uuid4().hex[:8]}",
                round=self.er.value(), text=t, options=fill, correct_index=ci,
                media=m, difficulty=self.ed.currentText().lower(), tags=[],
                points_first_attempt=self.ep1.value(),
                points_second_attempt=self.ep2.value(),
                points_third_attempt=self.ep3.value(),
                points_fourth_attempt=self.ep4.value(),
                max_attempts=self.ema.value(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        if self.current_question_id:
            for i, x in enumerate(self.questions):
                if x.id == self.current_question_id:
                    self.questions[i] = q
                    break
        else:
            self.questions.append(q)
        self.eg.setEnabled(False)
        self.current_question_id = None
        self._ref()
        self._upd_stats()
        self._sync_to_engine()  # Sync after adding/editing
        self.status.setText("✅ Question saved - Game engine updated")
    
    def _cn(self):
        self.eg.setEnabled(False)
        self.current_question_id = None
    
    def _dup(self, qid: str):
        q = next((x for x in self.questions if x.id == qid), None)
        if not q:
            return
        nq = Question(
            id=f"q_{uuid.uuid4().hex[:8]}", round=q.round, text=f"{q.text} (Copy)",
            options=q.options.copy(), correct_index=q.correct_index,
            media=q.media, difficulty=q.difficulty, tags=getattr(q, "tags", []).copy(),
            points_first_attempt=getattr(q, "points_first_attempt", 3),
            points_second_attempt=getattr(q, "points_second_attempt", 2),
            points_third_attempt=getattr(q, "points_third_attempt", 1),
            points_fourth_attempt=getattr(q, "points_fourth_attempt", 0),
            max_attempts=getattr(q, "max_attempts", 3),
        )
        self.questions.append(nq)
        self._ref_force()
        self._upd_stats()
        self._sync_to_engine()  # Sync after duplicating
        self.status.setText("✅ Duplicated - Game engine updated")
    
    def _del(self, qid: str):
        r = QMessageBox.question(self, "Delete", "Delete?", QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            self.questions = [q for q in self.questions if q.id != qid]
            self.disabled_ids.discard(qid)
            self._ref_force()
            self._upd_stats()
            self._sync_to_engine()  # Sync after deleting
            self.status.setText("✅ Deleted - Game engine updated")
    
    def _mt_ch(self, mt: str):
        self.bb.setEnabled(mt != "None")
        if mt == "None":
            self.emp.clear()
            self.emp.setPlaceholderText("No media")
            self.et.setPlaceholderText("Enter question text... (required)")
            if hasattr(self, 'question_label'):
                self.question_label.setText("Question Text:")
                self.question_label.setStyleSheet("font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.8);")
        elif mt == "Image":
            self.emp.setPlaceholderText("e.g. images/photo.jpg")
            self.et.setPlaceholderText("Question shown alongside the image, e.g. 'Who is this player?'")
            if hasattr(self, 'question_label'):
                self.question_label.setText("Question Text 🖼️:")
                self.question_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #5ddbff;")
        elif mt == "Audio":
            self.emp.setPlaceholderText("e.g. audio/clip.mp3")
            self.et.setPlaceholderText("Question shown alongside the audio, e.g. 'Which team\\'s anthem is this?'")
            if hasattr(self, 'question_label'):
                self.question_label.setText("Question Text 🔊:")
                self.question_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #a855f7;")
        elif mt == "Video":
            self.emp.setPlaceholderText("e.g. video/clip.mp4")
            self.et.setPlaceholderText("Question shown alongside the video, e.g. 'Who scored this goal?'")
            if hasattr(self, 'question_label'):
                self.question_label.setText("Question Text 🎬:")
                self.question_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #f97316;")
    
    def _br(self):
        mt = self.emt.currentText()
        flt = {
            "Image": "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)",
            "Audio": "Audio (*.mp3 *.wav *.ogg *.m4a *.flac)",
            "Video": "Video (*.mp4 *.avi *.mkv *.mov *.webm)",
        }
        f = flt.get(mt, "*.*")

        # FIX J: open the file browser starting from the pack directory so the
        # resulting path is easy to make relative.  Fall back to home dir if no
        # pack is loaded yet.
        start_dir = str(self.current_excel_path.parent) if self.current_excel_path else ""
        p, _ = QFileDialog.getOpenFileName(self, f"Select {mt}", start_dir, f)
        if p:
            # FIX J: store a path relative to the pack directory so the media
            # reference keeps working when the pack is moved or opened on another
            # machine.  Absolute paths break portability.
            if self.current_excel_path:
                try:
                    rel = Path(p).relative_to(self.current_excel_path.parent)
                    self.emp.setText(str(rel))
                    return
                except ValueError:
                    # File is outside the pack directory — warn and store absolute
                    # as a fallback (better than silently storing a broken path).
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self,
                        "Media Outside Pack Directory",
                        f"The selected file is outside the pack directory:\n"
                        f"  {self.current_excel_path.parent}\n\n"
                        f"The absolute path will be stored, but this pack may not "
                        f"work on other machines.\n\n"
                        f"Tip: copy the media file into the pack directory first.",
                    )
            self.emp.setText(p)
    
    def _upd_stats(self):
        sel = len(self.questions) - len(self.disabled_ids)
        e = sum(1 for q in self.questions if q.difficulty == "easy")
        m = sum(1 for q in self.questions if q.difficulty == "medium")
        h = sum(1 for q in self.questions if q.difficulty == "hard")
        self._sc(self.c_tot, str(len(self.questions)))
        self._sc(self.c_sel, str(sel))
        self._sc(self.c_easy, str(e))
        self._sc(self.c_med, str(m))
        self._sc(self.c_hard, str(h))
    
    def _card(self, t: str, v: str, c: str) -> QFrame:
        ca = QFrame()
        ca.setMinimumHeight(140)
        ca.setStyleSheet(
            f"QFrame {{ background: rgba(20,30,45,0.8); "
            f"border-left: 5px solid {c}; "
            f"border-top: 1px solid rgba(255,255,255,0.1); "
            f"border-right: 1px solid rgba(255,255,255,0.1); "
            f"border-bottom: 1px solid rgba(255,255,255,0.1); "
            f"border-radius: 12px; padding: 25px 15px; }}"
        )
        vl = QVBoxLayout(ca)
        vl.setSpacing(10)
        
        vla = QLabel(v)
        vla.setObjectName("value")
        vla.setAlignment(Qt.AlignCenter)
        vla.setStyleSheet(f"font-size: 48px; font-weight: 900; color: {c}; letter-spacing: -1px;")
        
        tla = QLabel(t)
        tla.setAlignment(Qt.AlignCenter)
        tla.setWordWrap(True)
        tla.setStyleSheet("font-size: 13px; font-weight: 700; color: rgba(255,255,255,0.75);")
        
        vl.addWidget(vla)
        vl.addWidget(tla)
        return ca
    
    def _mini_card(self, t: str, v: str, c: str) -> QFrame:
        """Compact stat card for Questions tab header"""
        ca = QFrame()
        ca.setStyleSheet(
            f"QFrame {{ background: rgba(20,30,45,0.6); "
            f"border-left: 3px solid {c}; "
            f"border-radius: 6px; padding: 8px 12px; }}"
        )
        hl = QHBoxLayout(ca)
        hl.setSpacing(10)
        
        vla = QLabel(v)
        vla.setObjectName("value")
        vla.setStyleSheet(f"font-size: 24px; font-weight: 900; color: {c};")
        
        tla = QLabel(t)
        tla.setStyleSheet("font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.6);")
        
        hl.addWidget(vla)
        hl.addWidget(tla)
        return ca
    
    def _sc(self, ca: QFrame, v: str):
        l = ca.findChild(QLabel, "value")
        if l:
            l.setText(v)
    
    def _l(self, t: str) -> QLabel:
        l = QLabel(t)
        l.setStyleSheet("font-size: 13px; font-weight: 700; color: rgba(255,255,255,0.9);")
        return l
    
    def _inp(self) -> str:
        return (
            "QLineEdit, QTextEdit, QSpinBox, QComboBox { "
            "background: rgba(30,40,55,0.8); border: 2px solid rgba(57,255,20,0.3); "
            "border-radius: 6px; padding: 8px; color: white; font-size: 13px; }"
            "QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #39FF14; }"
            "QSpinBox::up-button, QSpinBox::down-button { background: rgba(57,255,20,0.2); border: 1px solid rgba(57,255,20,0.3); }"
            "QComboBox::drop-down { background: rgba(57,255,20,0.2); border-left: 1px solid rgba(57,255,20,0.3); }"
        )
    
    def _btn(self) -> str:
        return (
            "QPushButton { background: rgba(57,255,20,0.2); border: 2px solid #39FF14; "
            "border-radius: 8px; padding: 10px 20px; font-size: 13px; font-weight: 900; color: white; }"
            "QPushButton:hover { background: rgba(57,255,20,0.4); }"
        )
    
    def _sbtn(self) -> str:
        return (
            "QPushButton { background: rgba(57,255,20,0.15); border: 2px solid #39FF14; "
            "border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 900; color: white; }"
            "QPushButton:hover { background: rgba(57,255,20,0.3); }"
        )
    
    def _sp(self, lo: int, hi: int, v: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(v)
        s.setStyleSheet(self._inp())
        return s