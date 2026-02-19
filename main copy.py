import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtCore import QTimer

from app.core.models import GameConfig
from app.constants import MediaType
from app.core.engine import GameEngine
from app.ui.screens.host_screen import HostScreen
from app.ui.screens.admin_dashboard import AdminDashboard


class FakeMQTT:
    """Fake MQTT backend for UI preview"""
    def __init__(self):
        self.connected = True

    def _publish_reset(self):
        print("[FAKE MQTT] 🔓 Buzzers unlocked")

    def start_question(self, question_id, max_attempts):
        print(f"[FAKE MQTT] ❓ Question started: {question_id} (max {max_attempts} attempts)")

    def get_connected_players(self, timeout_seconds=60):
        return [1, 2, 3, 4]

    def disconnect(self):
        print("[FAKE MQTT] Disconnected")


def _make_empty_config() -> GameConfig:
    """Minimal config — no questions. Engine populated by AdminDashboard."""
    return GameConfig(
        name="No Pack Loaded",
        version=1,
        rounds=1,
        questions_per_round=10,
        timer_seconds=20,
        answer_seconds=8,
        shuffle_questions=False,
        question_files=[],
        pack_dir=Path.cwd(),
        enable_cascading_attempts=True,
        reset_timer_each_attempt=False,
        penalty_for_wrong=0,
        bonus_for_speed=False,
        points_first_attempt_default=3,
        points_second_attempt_default=2,
        points_third_attempt_default=1,
        points_fourth_attempt_default=0,
        max_attempts_default=3,
    )


class AppWindow(QMainWindow):
    """Main application window — no default pack, load via Admin Dashboard."""

    def __init__(self, engine: GameEngine, fake_mqtt: FakeMQTT):
        super().__init__()
        self.setWindowTitle("Football Buzzer - UI Preview Mode")
        self.setMinimumSize(1400, 900)

        self.engine = engine
        self.mqtt_backend = fake_mqtt
        self.admin_window = None

        # Host screen
        self.host = HostScreen(engine=self.engine, mqtt_backend=self.mqtt_backend)

        # Replace help button with admin dashboard opener
        self.host.help_btn.setText("⚙️ ADMIN")
        self.host.help_btn.clicked.disconnect()
        self.host.help_btn.clicked.connect(self._open_admin_dashboard)

        self.setCentralWidget(self.host)

        # Simulate player connections
        for delay, pid in [(500, 1), (700, 2), (900, 3), (1100, 4)]:
            QTimer.singleShot(delay, lambda p=pid: self._simulate_connection(p))

    # ── expose admin_dashboard so main.py wiring works ──────────────────────
    @property
    def admin_dashboard(self) -> AdminDashboard:
        """Lazy-create the admin dashboard and return it."""
        if self.admin_window is None:
            self.admin_window = AdminDashboard(
                config=self.engine.cfg,
                questions=[],           # always start empty
            )
            # Wire signals once
            self.admin_window.questions_changed.connect(self._on_questions_changed)
            self.admin_window.config_changed.connect(self._on_config_changed)
            self.admin_window.pack_saved.connect(self._on_pack_saved)
        return self.admin_window

    def _simulate_connection(self, player_id: int):
        print(f"[FAKE] ✓ Player {player_id} connected")
        if hasattr(self.host, '_on_buzzer_connected'):
            self.host._on_buzzer_connected(player_id, True)

    def _open_admin_dashboard(self):
        """Open (or raise) the admin dashboard window."""
        dash = self.admin_dashboard          # ensures it's created & wired
        if dash.isVisible():
            dash.raise_()
            dash.activateWindow()
        else:
            dash.show()
        print("[ADMIN] 🛠️  Admin Dashboard opened")

    # ── signal handlers ──────────────────────────────────────────────────────

    def _on_questions_changed(self, new_questions: list):
        """Push new questions into engine (hot-swap + full reset)."""
        print(f"[ADMIN] 📝 {len(new_questions)} questions → engine.load_questions()")
        self.engine.load_questions(new_questions)

    def _on_config_changed(self, new_config: GameConfig):
        """Update engine config."""
        print(f"[ADMIN] ⚙️  Config updated: {new_config.name}")
        self.engine.cfg = new_config

    def _on_pack_saved(self, pack_path: str):
        print(f"[ADMIN] 💾 Pack saved: {pack_path}")

    def apply_config(self, new_config: GameConfig):
        """Called from main.py wiring if needed."""
        self._on_config_changed(new_config)

    def closeEvent(self, event):
        if self.admin_window and self.admin_window.isVisible():
            self.admin_window.close()
        if self.mqtt_backend:
            self.mqtt_backend.disconnect()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Football Buzzer - UI Preview")

    engine = GameEngine(_make_empty_config(), questions=[])
    fake_mqtt = FakeMQTT()

    window = AppWindow(engine, fake_mqtt)
    window.show()

    # Wire dashboard → engine (same pattern as production main.py)
    dashboard = window.admin_dashboard
    dashboard.questions_changed.connect(engine.load_questions)

    print("\n" + "="*60)
    print(" FOOTBALL BUZZER - UI PREVIEW MODE")
    print("="*60)
    print(" NO questions loaded — open Admin Dashboard first!")
    print("")
    print(" 🛠️  To load questions:")
    print("  1. Click '⚙️ ADMIN' button")
    print("  2. Click '📂 Load Excel' and select your .xlsx file")
    print("  3. Enable/disable questions with checkboxes")
    print("  4. Click '💾 Save Excel' — game updates instantly")
    print("")
    print(" ⌨️  Keyboard Shortcuts (once questions are loaded):")
    print("  Enter       - Start question")
    print("  U           - Unlock buzzers")
    print("  Up Arrow    - Mark correct")
    print("  Down Arrow  - Mark wrong")
    print("  Right Arrow - Next question")
    print("  Space       - Reset game")
    print("="*60 + "\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()