"""
display_config.py
=================
Centralised scale presets for Standard vs 4K TV display modes.
Import SCALE anywhere in the UI to get the active values.

Usage:
    from app.ui.display_config import SCALE
    font_size = SCALE.question_font
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScalePreset:
    # ── Player cards ─────────────────────────────────────────────────
    card_min_w: int
    card_min_h: int
    card_max_w: int
    circle_size: int
    circle_radius: int
    circle_font: int
    card_label_font: int
    card_label_padding: str

    # ── Logo ─────────────────────────────────────────────────────────
    logo_size: int

    # ── Question box ─────────────────────────────────────────────────
    question_font: int
    question_min_h: int
    question_padding: str

    # ── Options ──────────────────────────────────────────────────────
    option_min_h: int
    option_max_h: int
    option_letter_font: int
    option_letter_w: int
    option_text_font: int
    option_padding: str

    # ── Cascading widget ─────────────────────────────────────────────
    cascade_title_font: int
    cascade_attempt_font: int
    cascade_points_font: int
    cascade_players_font: int
    cascade_indicator_size: int
    cascade_indicator_radius: int
    cascade_indicator_font: int
    cascade_spacing: int
    cascade_margin_v: int  # top/bottom
    cascade_margin_h: int  # left/right

    # ── Control panel buttons ────────────────────────────────────────
    btn_font: int
    btn_padding: str
    btn_min_w: int
    btn_min_h: int
    btn_radius: int
    help_btn_size: int
    help_btn_radius: int
    help_btn_font: int
    phase_font: int
    status_font: int

    # ── Root / layout ────────────────────────────────────────────────
    root_margins: int
    main_row_spacing: int
    center_spacing: int
    center_h_margins: int


STANDARD = ScalePreset(
    # cards
    card_min_w=160,
    card_min_h=220,
    card_max_w=220,
    circle_size=140,
    circle_radius=70,
    circle_font=48,
    card_label_font=15,
    card_label_padding="6px 10px",
    # logo
    logo_size=180,
    # question
    question_font=32,
    question_min_h=120,
    question_padding="12px",
    # options
    option_min_h=80,
    option_max_h=130,
    option_letter_font=22,
    option_letter_w=36,
    option_text_font=24,
    option_padding="10px 14px",
    # cascading
    cascade_title_font=16,
    cascade_attempt_font=34,
    cascade_points_font=18,
    cascade_players_font=14,
    cascade_indicator_size=44,
    cascade_indicator_radius=22,
    cascade_indicator_font=14,
    cascade_spacing=6,
    cascade_margin_v=12,
    cascade_margin_h=16,
    # buttons
    btn_font=14,
    btn_padding="8px 18px",
    btn_min_w=120,
    btn_min_h=38,
    btn_radius=8,
    help_btn_size=38,
    help_btn_radius=19,
    help_btn_font=16,
    phase_font=12,
    status_font=13,
    # layout
    root_margins=0,
    main_row_spacing=8,
    center_spacing=8,
    center_h_margins=20,
)

TV_4K = ScalePreset(
    # cards
    card_min_w=210,
    card_min_h=260,
    card_max_w=260,
    circle_size=160,
    circle_radius=80,
    circle_font=58,
    card_label_font=18,
    card_label_padding="7px 12px",
    # logo
    logo_size=220,
    # question
    question_font=42,
    question_min_h=150,
    question_padding="16px",
    # options
    option_min_h=100,
    option_max_h=155,
    option_letter_font=28,
    option_letter_w=44,
    option_text_font=30,
    option_padding="14px 18px",
    # cascading
    cascade_title_font=20,
    cascade_attempt_font=46,
    cascade_points_font=26,
    cascade_players_font=18,
    cascade_indicator_size=62,
    cascade_indicator_radius=31,
    cascade_indicator_font=20,
    cascade_spacing=12,
    cascade_margin_v=18,
    cascade_margin_h=24,
    # buttons
    btn_font=15,
    btn_padding="10px 20px",
    btn_min_w=130,
    btn_min_h=44,
    btn_radius=9,
    help_btn_size=44,
    help_btn_radius=22,
    help_btn_font=20,
    phase_font=13,
    status_font=14,
    # layout
    root_margins=0,
    main_row_spacing=12,
    center_spacing=10,
    center_h_margins=30,
)

# ── Active preset (set once at startup via set_scale()) ──────────────────────
SCALE: ScalePreset = STANDARD


def set_scale(tv_mode: bool) -> None:
    """Call once at startup before any UI is built."""
    global SCALE
    SCALE = TV_4K if tv_mode else STANDARD
    print(f"[DISPLAY] Scale mode: {'4K TV' if tv_mode else 'Standard'}")
