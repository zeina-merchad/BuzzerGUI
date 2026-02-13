"""
remote_config.py
================
Key bindings for the Rii i7 (2.4GHz USB dongle) remote control.
Key codes confirmed via key_discovery.py on this specific unit.

ACTUAL Rii i7 BUTTON → Qt.Key MAP
────────────────────────────────────────────────────────────────────
Button              Qt.Key constant               hex
────────────────────────────────────────────────────────────────────
OK  / Enter       → Key_Return                    0x01000004
↑ D-pad           → Key_Up                        0x01000013
→ D-pad           → Key_Right                     0x01000014
← D-pad           → Key_Left                      0x01000012
↓ D-pad           → Key_Down                      0x01000015
Home              → Key_Home                      0x01000010
Home (media)      → Key_HomePage                  0x01000090
Menu  ☰           → Key_Menu                      0x01000055
Play/Pause  ⏯     → Key_MediaTogglePlayPause       0x01000086
Vol+              → Key_VolumeUp                  0x01000072
Page▲             → Key_PageUp                    0x01000016
Page▼             → Key_PageDown                  0x01000017
Vol-              → Key_VolumeDown                0x01000070
────────────────────────────────────────────────────────────────────

To remap a button, change the Qt.Key value on the right-hand side of
the REMOTE_KEYS dict below.  All 13 buttons are documented as comments
so you can freely reassign any spare one.
"""

from PySide6.QtCore import Qt

# ─────────────────────────────────────────────────────────────────────────────
# Edit these mappings to match what your Rii i7 actually sends.
# Each value is a Qt.Key enum member.
# ─────────────────────────────────────────────────────────────────────────────
REMOTE_KEYS: dict[str, Qt.Key] = {
    # ── Confirmed Rii i7 key codes (from key_discovery.py) ──────────────────
    #
    # Button on remote         Qt.Key constant                  hex
    # ─────────────────────────────────────────────────────────────────────────
    "start_game":      Qt.Key.Key_MediaTogglePlayPause,  # ⏯  Play/Pause   0x01000086
    "unlock_buzzers":  Qt.Key.Key_Return,                # OK / Enter      0x01000004
    "next_question":   Qt.Key.Key_PageDown,              # Page▼           0x01000017
    "reset_game":      Qt.Key.Key_Menu,                  # ☰  Menu         0x01000055
    "bonus_point":     Qt.Key.Key_VolumeUp,              # Vol+            0x01000072

    # ── Spare buttons (uncomment to assign) ─────────────────────────────────
    # "...":  Qt.Key.Key_Up,          # ↑  D-pad        0x01000013
    # "...":  Qt.Key.Key_Down,        # ↓  D-pad        0x01000015
    # "...":  Qt.Key.Key_Left,        # ←  D-pad        0x01000012
    # "...":  Qt.Key.Key_Right,       # →  D-pad        0x01000014
    # "...":  Qt.Key.Key_Home,        # Home            0x01000010
    # "...":  Qt.Key.Key_HomePage,    # Home (media)    0x01000090
    # "...":  Qt.Key.Key_PageUp,      # Page▲           0x01000016
    # "...":  Qt.Key.Key_VolumeDown,  # Vol-            0x01000070
}

# ─────────────────────────────────────────────────────────────────────────────
# MODIFIER GUARD
# Set to True to require the remote's Fn / Shift held for game actions.
# Useful if the remote shares keys with a keyboard so accidental presses
# from typing don't trigger game events.
# ─────────────────────────────────────────────────────────────────────────────
REQUIRE_MODIFIER: bool = False
MODIFIER_KEY: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier  # e.g. Qt.AltModifier