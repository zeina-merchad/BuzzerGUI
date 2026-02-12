import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import get_config
from app.core.engine import GameEngine
from app.core.models import GameConfig
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend


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
        # FIX: use tuple() to match the updated GameConfig field type
        question_files=(),
        pack_dir=Path.cwd(),
        enable_cascading_attempts=True,
        reset_timer_each_attempt=False,
        penalty_for_wrong=0,
        bonus_for_speed=False,
    )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Football Trivia Game")
    app.setOrganizationName("Football Trivia Game")

    # ── ENGINE: starts empty, questions injected by AdminDashboard ──────────
    try:
        engine = GameEngine(_make_empty_config(), questions=[])
    except Exception as e:
        QMessageBox.critical(None, "Initialisation Error",
                             f"Failed to initialise game engine:\n{e}")
        sys.exit(1)

    print("[OK] Engine initialised with 0 questions — load via Admin Dashboard")

    # ── MQTT BACKEND ────────────────────────────────────────────────────────
    MQTT_BROKER_HOST = "192.168.10.10"
    MQTT_BROKER_PORT = 1883

    mqtt_backend = MQTTBuzzerBackend(
        broker_host=MQTT_BROKER_HOST,
        broker_port=MQTT_BROKER_PORT,
    )

    if not mqtt_backend.connect():
        QMessageBox.critical(
            None, "MQTT Connection Failed",
            f"Failed to connect to broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}\n\n"
            "Please ensure the MQTT broker is running and the network is active.\n\n"
            "The application will now exit.",
        )
        sys.exit(1)

    print("[OK] Connected to MQTT broker")

    # ── APPLICATION WINDOW ──────────────────────────────────────────────────
    try:
        from app.ui.app_window import AppWindow
        window = AppWindow(engine, mqtt_backend)
        window.show()
    except Exception as e:
        QMessageBox.critical(None, "Window Error",
                             f"Failed to create application window:\n{e}")
        mqtt_backend.disconnect()
        sys.exit(1)

    # ── WIRE AdminDashboard → GameEngine ────────────────────────────────────
    # AppWindow.admin_dashboard is a lazy property that wires
    # questions_changed → engine.load_questions internally when first accessed.
    # We only need to expose the dashboard reference here for external use;
    # FIX #3: removed the duplicate questions_changed.connect(engine.load_questions)
    # that previously lived here alongside the one inside AppWindow, which caused
    # load_questions to be called twice every time the admin changed questions.
    try:
        dashboard = window.admin_dashboard  # triggers lazy creation + internal wiring

        # Config changes → window if it supports it
        if hasattr(window, 'apply_config'):
            dashboard.config_changed.connect(window.apply_config)

        print("[OK] AdminDashboard wired ✓")

    except AttributeError as exc:
        print(f"[WARNING] Could not wire AdminDashboard: {exc}")
        print("          Ensure AppWindow exposes self.admin_dashboard")

    # ── READY ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("READY — no questions loaded yet")
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