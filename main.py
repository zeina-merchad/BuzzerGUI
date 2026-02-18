import sys
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

from app.config import get_config
from app.core.engine import GameEngine
from app.core.models import GameConfig
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend


def resource_path(rel: str) -> str:
    """Resolve a resource path that works both in dev and PyInstaller --onedir bundles."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle — files land in _internal/ (PyInstaller 6+)
        base = os.path.dirname(sys.executable)
        internal = os.path.join(base, "_internal")
        path = os.path.join(internal, rel)
        if os.path.exists(path):
            return path
        # Fallback: some files may sit next to the executable
        path = os.path.join(base, rel)
        if os.path.exists(path):
            return path
        return os.path.join(internal, rel)  # return best guess even if missing
    else:
        # Running in dev — relative to this file's directory
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


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
        question_files=(),
        pack_dir=Path.cwd(),
        enable_cascading_attempts=True,
        reset_timer_each_attempt=False,
        penalty_for_wrong=0,
        bonus_for_speed=False,
    )


class _NoOpMQTTBackend:
    """Stub backend used in --no-mqtt / demo mode.

    FIX #6: allows the app to run without a live MQTT broker for development
    and testing.  All methods are no-ops; callbacks are never fired so the
    engine stays in manual-only mode (admin clicks UNLOCK / NEXT manually).
    """
    connected = False
    state = None

    class _Bridge:
        """Minimal signal stub so HostScreen's bridge.heartbeat_resolved.connect() doesn't crash."""
        class _Sig:
            def connect(self, *a, **kw): pass
            def emit(self, *a, **kw): pass
        heartbeat_resolved = _Sig()

    bridge = _Bridge()

    on_buzz_callback = None
    on_answer_callback = None
    on_player_connected_callback = None
    on_player_disconnected_callback = None
    on_state_change_callback = None
    on_player_unresponsive_callback = None

    def connect(self): return True
    def disconnect(self): pass
    def unlock_buzzers(self): pass
    def lock_player(self, player_id): pass
    def start_question(self, question_id, max_attempts=1): pass
    def end_question(self): pass
    def mark_answer_wrong(self, player_id): pass
    def mark_answer_correct(self, player_id): pass
    def send_heartbeat(self, player_id): pass
    def send_heartbeat_to_all(self, timeout_seconds=10): pass
    def get_connected_players(self, timeout_seconds=60): return []
    def check_all_players_liveliness(self): return {1: False, 2: False, 3: False, 4: False}
    def check_player_liveliness(self, player_id): return False
    def all_pings_resolved(self, timeout_seconds=10): return True
    def get_status(self): return {"connected": False, "state": "demo"}


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Football Trivia Game")
    app.setOrganizationName("Football Trivia Game")

    # ── Icon loading ──────────────────────────────────────────────────────────
    # Tries .ico first (Windows), then .png (Linux / Raspberry Pi).
    # Place your icon at assets/icon.png for Pi builds,
    # or assets/icon.ico for Windows builds.
    icon = QIcon()
    icon_candidates = [
        "assets/logo.png",   # Linux / Raspberry Pi packaged
        "logo.png",          # Linux / Raspberry Pi flat layout
    ]
    for try_path in icon_candidates:
        full_path = resource_path(try_path)
        if os.path.exists(full_path):
            icon = QIcon(full_path)
            if not icon.isNull():
                app.setWindowIcon(icon)
                print(f"[OK] Icon loaded: {full_path}")
                break
    else:
        print(f"[WARNING] No icon found — tried: {', '.join(icon_candidates)}")

    # FIX #6: --no-mqtt flag (or NO_MQTT=1 env var) enables demo/offline mode
    no_mqtt = "--no-mqtt" in sys.argv or os.environ.get("NO_MQTT", "0") == "1"

    # ── ENGINE ────────────────────────────────────────────────────────────────
    try:
        engine = GameEngine(_make_empty_config(), questions=[])
    except Exception as e:
        QMessageBox.critical(None, "Initialisation Error",
                             f"Failed to initialise game engine:\n{e}")
        sys.exit(1)

    print("[OK] Engine initialised with 0 questions — load via Admin Dashboard")

    # ── MQTT BACKEND ──────────────────────────────────────────────────────────
    MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "192.168.10.10")
    MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))

    if no_mqtt:
        print("[OK] --no-mqtt flag set — running in demo/offline mode (no hardware)")
        mqtt_backend = _NoOpMQTTBackend()
    else:
        mqtt_backend = MQTTBuzzerBackend(
            broker_host=MQTT_BROKER_HOST,
            broker_port=MQTT_BROKER_PORT,
        )

        if not mqtt_backend.connect():
            reply = QMessageBox.critical(
                None,
                "MQTT Connection Failed",
                f"Failed to connect to broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}\n\n"
                "Please ensure the MQTT broker is running and the network is active.\n\n"
                "Run with --no-mqtt to start without hardware (demo mode).",
                QMessageBox.Retry | QMessageBox.Ignore | QMessageBox.Abort,
            )

            if reply == QMessageBox.Abort:
                sys.exit(1)
            elif reply == QMessageBox.Ignore:
                print("[WARNING] Continuing without MQTT connection — hardware will not work")
            else:
                # Retry once — if it fails again, fall through to offline mode
                if not mqtt_backend.connect():
                    print("[WARNING] MQTT retry failed — switching to demo mode")
                    mqtt_backend = _NoOpMQTTBackend()

    print("[OK] MQTT backend ready")

    # ── APPLICATION WINDOW ────────────────────────────────────────────────────
    try:
        from app.ui.app_window import AppWindow
        window = AppWindow(engine, mqtt_backend)

        if not icon.isNull():
            window.setWindowIcon(icon)

        # Start maximized — works on Windows, Linux, and Raspberry Pi.
        # Swap for window.showFullScreen() if you want kiosk mode (no title bar).
        window.showMaximized()

    except Exception as e:
        QMessageBox.critical(None, "Window Error",
                             f"Failed to create application window:\n{e}")
        mqtt_backend.disconnect()
        sys.exit(1)

    try:
        dashboard = window.admin_dashboard  # triggers lazy creation + internal wiring
        print("[OK] AdminDashboard wired ✓")
    except AttributeError as exc:
        print(f"[WARNING] Could not wire AdminDashboard: {exc}")
        print("          Ensure AppWindow exposes self.admin_dashboard")

    # ── READY ─────────────────────────────────────────────────────────────────
    mode_str = "DEMO (no hardware)" if isinstance(mqtt_backend, _NoOpMQTTBackend) else \
               f"HARDWARE ({MQTT_BROKER_HOST}:{MQTT_BROKER_PORT})"
    print("\n" + "=" * 55)
    print(f"READY — {mode_str}")
    print("Open Admin Dashboard → Load Excel → questions go live")
    print("=" * 55 + "\n")

    exit_code = app.exec()
    mqtt_backend.disconnect()
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)