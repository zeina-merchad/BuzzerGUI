import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import get_config
from app.core.engine import GameEngine
from app.core.models import GameConfig
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend


def resource_path(rel: str) -> str:
    """Resolve a resource path that works both in dev and PyInstaller --onedir bundles."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        internal = os.path.join(base, "_internal")
        path = os.path.join(internal, rel)
        if os.path.exists(path):
            return path
        path = os.path.join(base, rel)
        if os.path.exists(path):
            return path
        return os.path.join(internal, rel)
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


def create_desktop_shortcut() -> None:
    """Create a .desktop shortcut on Linux/Raspberry Pi. Silent no-op on Windows."""
    if sys.platform == "win32":
        return

    # Only create shortcut when running as a packaged bundle, not in dev
    if not getattr(sys, "frozen", False):
        return

    exe_path = os.path.abspath(sys.executable)
    base = os.path.dirname(exe_path)
    internal = os.path.join(base, "_internal")

    # Find the icon next to the exe or inside _internal/
    icon_path = ""
    for candidate in [
        os.path.join(internal, "assets", "logo.png"),
        os.path.join(base, "assets", "logo.png"),
    ]:
        if os.path.exists(candidate):
            icon_path = candidate
            break

    desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(desktop_dir, exist_ok=True)
    shortcut_path = os.path.join(desktop_dir, "FootballQuiz.desktop")

    # Don't overwrite if it already points to the right executable
    if os.path.exists(shortcut_path):
        try:
            with open(shortcut_path, "r") as f:
                if exe_path in f.read():
                    return  # already up to date
        except Exception:
            pass

    content = f"""[Desktop Entry]
    Name=Football Quiz
    Comment=Buzzer Quiz Game
    Exec=env QT_QPA_PLATFORM=xcb {exe_path}
    Icon={icon_path}
    Terminal=false
    Type=Application
    Categories=Game;
    StartupNotify=true
    """
    try:
        with open(shortcut_path, "w") as f:
            f.write(content)
        os.chmod(shortcut_path, 0o755)
        print(f"[OK] Desktop shortcut created: {shortcut_path}")
    except Exception as e:
        print(f"[WARNING] Could not create desktop shortcut: {e}")


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
    """Stub backend used in --no-mqtt / demo mode."""

    connected = False
    state = None

    class _Bridge:
        class _Sig:
            def connect(self, *a, **kw):
                pass

            def emit(self, *a, **kw):
                pass

        heartbeat_resolved = _Sig()

    bridge = _Bridge()

    on_buzz_callback = None
    on_answer_callback = None
    on_player_connected_callback = None
    on_player_disconnected_callback = None
    on_state_change_callback = None
    on_player_unresponsive_callback = None

    def connect(self):
        return True

    def disconnect(self):
        pass

    def unlock_buzzers(self):
        pass

    def lock_player(self, player_id):
        pass

    def start_question(self, question_id, max_attempts=1):
        pass

    def end_question(self):
        pass

    def mark_answer_wrong(self, player_id):
        pass

    def mark_answer_correct(self, player_id):
        pass

    def send_heartbeat(self, player_id):
        pass

    def send_heartbeat_to_all(self, timeout_seconds=10):
        pass

    def get_connected_players(self, timeout_seconds=60):
        return []

    def check_all_players_liveliness(self):
        return {1: False, 2: False, 3: False, 4: False}

    def check_player_liveliness(self, player_id):
        return False

    def all_pings_resolved(self, timeout_seconds=10):
        return True

    def get_status(self):
        return {"connected": False, "state": "demo"}


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from PySide6.QtGui import QColor, QPalette

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(13, 27, 42))
    dark_palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.Base, QColor(15, 25, 40))
    dark_palette.setColor(QPalette.AlternateBase, QColor(20, 30, 45))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.Text, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.Button, QColor(20, 30, 45))
    dark_palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.BrightText, QColor(57, 255, 20))
    dark_palette.setColor(QPalette.Highlight, QColor(57, 255, 20))
    dark_palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setPalette(dark_palette)

    app.setApplicationName("Football Trivia Game")
    app.setOrganizationName("Football Trivia Game")

    # ── Display mode selection ────────────────────────────────────────────────
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout
    from PySide6.QtWidgets import QLabel as _QLabel

    from app.ui.display_config import set_scale

    class _DisplayDialog(QDialog):
        def __init__(self):
            super().__init__()
            self.tv_mode = False
            self.setWindowTitle("Display Mode")
            self.setFixedSize(480, 260)
            self.setWindowFlags(_Qt.Dialog | _Qt.FramelessWindowHint)
            self.setStyleSheet(
                "QDialog { background: #0d1b2a; border: 2px solid #39FF14; border-radius: 14px; }"
            )
            lay = QVBoxLayout(self)
            lay.setSpacing(20)
            lay.setContentsMargins(36, 32, 36, 32)

            title = _QLabel("Select Display Mode")
            title.setAlignment(_Qt.AlignCenter)
            title.setStyleSheet(
                "font-size: 22px; font-weight: 900; color: #39FF14; background: transparent;"
            )
            lay.addWidget(title)

            sub = _QLabel("Choose how the UI should be scaled for your screen.")
            sub.setAlignment(_Qt.AlignCenter)
            sub.setWordWrap(True)
            sub.setStyleSheet(
                "font-size: 13px; color: rgba(255,255,255,0.6); background: transparent;"
            )
            lay.addWidget(sub)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(16)

            std_btn = QPushButton("🖥️  Standard\n(Monitor / Laptop)")
            std_btn.setFixedHeight(64)
            std_btn.setStyleSheet(
                "QPushButton { background: rgba(57,255,20,0.15); border: 2px solid #39FF14; "
                "border-radius: 10px; font-size: 14px; font-weight: 900; color: white; }"
                "QPushButton:hover { background: rgba(57,255,20,0.35); }"
            )
            std_btn.clicked.connect(
                lambda: (setattr(self, "tv_mode", False), self.accept())
            )

            tv_btn = QPushButton('📺  4K TV Mode\n(50"+ screen)')
            tv_btn.setFixedHeight(64)
            tv_btn.setStyleSheet(
                "QPushButton { background: rgba(255,215,0,0.15); border: 2px solid #ffd700; "
                "border-radius: 10px; font-size: 14px; font-weight: 900; color: #ffd700; }"
                "QPushButton:hover { background: rgba(255,215,0,0.35); }"
            )
            tv_btn.clicked.connect(
                lambda: (setattr(self, "tv_mode", True), self.accept())
            )

            btn_row.addWidget(std_btn)
            btn_row.addWidget(tv_btn)
            lay.addLayout(btn_row)

    dlg = _DisplayDialog()
    # Centre on primary screen
    from PySide6.QtGui import QGuiApplication as _QGA

    sg = _QGA.primaryScreen().geometry()
    dlg.move((sg.width() - dlg.width()) // 2, (sg.height() - dlg.height()) // 2)
    dlg.exec()
    set_scale(dlg.tv_mode)
    # ─────────────────────────────────────────────────────────────────────────

    # ── Icon loading ──────────────────────────────────────────────────────────
    # .ico for Windows, .png for Linux / Raspberry Pi
    icon = QIcon()
    icon_candidates = [
        "assets/logo.png",  # Linux / Raspberry Pi packaged
        "logo.png",  # Linux / Raspberry Pi flat layout
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

    # ── Desktop shortcut (Pi / Linux only, packaged builds only) ─────────────
    create_desktop_shortcut()

    # FIX #6: --no-mqtt flag (or NO_MQTT=1 env var) enables demo/offline mode
    no_mqtt = "--no-mqtt" in sys.argv or os.environ.get("NO_MQTT", "0") == "1"

    # ── ENGINE ────────────────────────────────────────────────────────────────
    try:
        engine = GameEngine(_make_empty_config(), questions=[])
    except Exception as e:
        QMessageBox.critical(
            None, "Initialisation Error", f"Failed to initialise game engine:\n{e}"
        )
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
                print(
                    "[WARNING] Continuing without MQTT connection — hardware will not work"
                )
            else:
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

        # Start maximized. Swap for showFullScreen() for kiosk/no-title-bar mode.
        window.showMaximized()

    except Exception as e:
        QMessageBox.critical(
            None, "Window Error", f"Failed to create application window:\n{e}"
        )
        mqtt_backend.disconnect()
        sys.exit(1)

    try:
        dashboard = window.admin_dashboard
        print("[OK] AdminDashboard wired ✓")
    except AttributeError as exc:
        print(f"[WARNING] Could not wire AdminDashboard: {exc}")

    # ── READY ─────────────────────────────────────────────────────────────────
    mode_str = (
        "DEMO (no hardware)"
        if isinstance(mqtt_backend, _NoOpMQTTBackend)
        else f"HARDWARE ({MQTT_BROKER_HOST}:{MQTT_BROKER_PORT})"
    )
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
