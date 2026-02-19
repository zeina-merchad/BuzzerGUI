from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QMessageBox
from PySide6.QtCore import QTimer

from app.core.engine import GameEngine
from app.core.models import GameConfig
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend
from app.ui.screens.host_screen import HostScreen
from app.ui.screens.admin_dashboard import AdminDashboard


class AppWindow(QMainWindow):
    """Main application window with MQTT hardware integration"""

    def __init__(self, engine: GameEngine, mqtt_backend: MQTTBuzzerBackend):
        super().__init__()
        self.setWindowTitle("Football Buzzer - Hardware Mode")
        self.setMinimumSize(1000, 600)

        self.engine = engine
        self.mqtt_backend = mqtt_backend

        # Admin dashboard — created once, lazily, via the property
        self._admin_window: AdminDashboard | None = None

        # ── Host screen ──────────────────────────────────────────────────────
        # HostScreen registers its own MQTT callbacks internally; AppWindow
        # must NOT re-register them here — doing so would overwrite
        # HostScreen's handlers and silently break buzz/answer processing.
        # FIX #2: Removed the duplicate on_buzz_callback / on_answer_callback
        # assignments that previously lived here.
        self.host = HostScreen(engine=self.engine, mqtt_backend=self.mqtt_backend)
        self.host.help_btn.clicked.disconnect()
        self.host.help_btn.clicked.connect(self._show_admin_dashboard)
        self.setCentralWidget(self.host)

        # FIX #7: Removed the duplicate connection_monitor QTimer that was
        # polling _check_connections() every 2 s alongside the identical timer
        # already running inside HostScreen._update_connection_status().
        # HostScreen's timer is the single source of truth for connection state.

    # =========================================================================
    # ADMIN DASHBOARD — single instance, lazy creation
    # =========================================================================

    @property
    def admin_dashboard(self) -> AdminDashboard:
        """
        Lazy-create the AdminDashboard once and wire its signals to the engine.
        Always returns the same instance so state (loaded Excel, etc.) is preserved.
        """
        if self._admin_window is None:
            self._admin_window = AdminDashboard(
                config=self.engine.cfg,
                questions=[],           # start empty — admin loads Excel
            )
            self._admin_window.setWindowTitle("Admin Dashboard — Football Buzzer")
            self._admin_window.resize(1200, 850)

            # Wire signals
            self._admin_window.questions_changed.connect(self._on_questions_changed)
            self._admin_window.config_changed.connect(self._on_config_changed)

            # FIX L: keep AdminDashboard informed of game-active state so that
            # question-checkbox toggles don't fire load_questions() mid-game.
            self.engine.phase_changed.connect(self._on_phase_changed_for_admin)

        return self._admin_window

    def _show_admin_dashboard(self):
        """Open or raise the admin dashboard window."""
        dash = self.admin_dashboard          # creates if needed
        if dash.isVisible():
            dash.raise_()
            dash.activateWindow()
        else:
            dash.show()
        print("[ADMIN] 🛠️  Admin Dashboard opened")

    # ── signal handlers ──────────────────────────────────────────────────────

    def _on_questions_changed(self, new_questions: list):
        """Push new question list into engine (hot-swap + full reset).
        
        FIX #1 / #3: Call load_questions (the real method name on GameEngine).
        Previously app_window called the non-existent reload_questions which
        would raise AttributeError silently at runtime.  The engine now also
        exposes reload_questions as an alias, but this call uses the canonical
        name directly.
        """
        self.engine.load_questions(new_questions)
        print(f"[OK] Questions updated: {len(new_questions)} loaded into engine")

    def _on_config_changed(self, new_config: GameConfig):
        """Update engine config live (no score/question reset)."""
        self.engine.update_config(new_config)
        print(f"[OK] Config updated: {new_config.name}")

    def _on_phase_changed_for_admin(self, phase: str) -> None:
        # FIX L: keep AdminDashboard informed of whether a game is running.
        # GAME_END and IDLE (pre-game) mean not active; anything else is active.
        # This prevents _tog() calling load_questions() mid-game, which would
        # silently wipe scores and reset current_q_idx.
        if self._admin_window is None:
            return
        active = phase not in ("IDLE", "GAME_END")
        self._admin_window.set_game_active(active)

    def apply_config(self, new_config: GameConfig):
        """Public alias — called from main.py wiring."""
        self._on_config_changed(new_config)

    # =========================================================================
    # CLEANUP
    # =========================================================================

    def closeEvent(self, event):
        print("\n[INFO] Shutting down application...")
        try:
            if self.mqtt_backend:
                self.mqtt_backend.disconnect()
                print("[OK] MQTT backend disconnected")
        except Exception as e:
            print(f"[WARNING] Error disconnecting MQTT: {e}")
        if self._admin_window:
            self._admin_window.close()
        super().closeEvent(event)