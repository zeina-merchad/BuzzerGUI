"""
Sound Manager Test
Run from project root: python test_sounds.py
Tests each sound one by one with a keypress between each.
"""

import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Import the sound manager
sys.path.insert(0, str(Path(__file__).parent))
from app.core.sound_manager import create_sound_manager


class SoundTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sound Manager Test")
        self.setMinimumSize(600, 500)
        self.setStyleSheet("QWidget { background: #0d1b2a; color: white; }")

        self.sfx = create_sound_manager()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("🔊 Sound Manager Test")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #39FF14; padding: 10px;"
        )
        layout.addWidget(title)

        self.status = QLabel("Click a button to test each sound")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet(
            "font-size: 14px; color: rgba(255,255,255,0.7); "
            "background: rgba(255,255,255,0.05); border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(self.status)

        btn_style = (
            "QPushButton { background: rgba(57,255,20,0.15); border: 2px solid #39FF14; "
            "border-radius: 8px; padding: 12px; font-size: 15px; font-weight: 900; color: white; }"
            "QPushButton:hover { background: rgba(57,255,20,0.35); }"
            "QPushButton:pressed { background: rgba(57,255,20,0.55); }"
        )

        sounds = [
            ("🎮  buzz", self.sfx.play_buzz, "Short buzzer — should be quick"),
            (
                "✅  correct",
                self.sfx.play_correct,
                "Arpeggio + 5s applause — should play FULLY",
            ),
            ("❌  wrong", self.sfx.play_wrong, "Descending tone"),
            ("⚠️   timer_warning", self.sfx.play_timer_warning, "Double beep at 7s"),
            ("🚨  timer_critical", self.sfx.play_timer_critical, "Triple beep at 3s"),
            ("▶️   start", self.sfx.play_start, "Game start sound"),
            ("⏭️   next", self.sfx.play_next, "Next question sound"),
            ("⭐  point", self.sfx.play_point, "Point awarded"),
        ]

        for label, fn, desc in sounds:
            row = QHBoxLayout()

            btn = QPushButton(label)
            btn.setStyleSheet(btn_style)
            btn.setFixedWidth(220)
            btn.clicked.connect(self._make_handler(fn, label, desc))
            row.addWidget(btn)

            desc_label = QLabel(desc)
            desc_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.5);")
            row.addWidget(desc_label)
            row.addStretch()

            layout.addLayout(row)

        layout.addStretch()

        stop_btn = QPushButton("⏹  Stop All")
        stop_btn.setStyleSheet(
            "QPushButton { background: rgba(231,76,60,0.2); border: 2px solid #e74c3c; "
            "border-radius: 8px; padding: 12px; font-size: 15px; font-weight: 900; color: white; }"
            "QPushButton:hover { background: rgba(231,76,60,0.4); }"
        )
        stop_btn.clicked.connect(self._stop_all)
        layout.addWidget(stop_btn)

    def _make_handler(self, fn, label, desc):
        def handler():
            self.status.setText(f"Playing: {label.strip()}  —  {desc}")
            self.status.setStyleSheet(
                "font-size: 14px; color: #39FF14; "
                "background: rgba(57,255,20,0.1); border: 1px solid #39FF14; "
                "border-radius: 8px; padding: 10px;"
            )
            fn()

        return handler

    def _stop_all(self):
        self.sfx.stop_all()
        self.status.setText("Stopped all sounds.")
        self.status.setStyleSheet(
            "font-size: 14px; color: rgba(255,255,255,0.7); "
            "background: rgba(255,255,255,0.05); border-radius: 8px; padding: 10px;"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SoundTestWindow()
    window.show()
    sys.exit(app.exec())
