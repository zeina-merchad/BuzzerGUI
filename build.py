import os

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))

PyInstaller.__main__.run(
    [
        "main.py",
        "--onedir",
        "--noconsole",
        "--name=FootballQuiz",
        "--clean",
        f"--add-data={ROOT}/assets:assets",
        f"--add-data={ROOT}/app:app",
        f"--add-data={ROOT}/media:media",
        f"--add-data={ROOT}/excel:excel",
        f"--add-data={ROOT}/app/ui/screens/logo.png:app/ui/screens",
        f"--add-data={ROOT}/app/ui/screens/logo_full.png:app/ui/screens",
        "--collect-all=PySide6",
        "--collect-all=paho",
        "--hidden-import=app.ui.app_window",
        "--hidden-import=app.ui.screens.admin_dashboard",
        "--hidden-import=app.ui.screens.host_screen",
        "--hidden-import=app.ui.screens.round_transition_screen",
        "--hidden-import=app.ui.screens.winner_screen",
        "--hidden-import=app.ui.widgets",
        "--hidden-import=app.ui.key_discovery",
        "--hidden-import=app.ui.remote_config",
        "--hidden-import=app.config",
        "--hidden-import=app.core.engine",
        "--hidden-import=app.core.models",
        "--hidden-import=app.hardware.mqtt_buzzer",
        "--hidden-import=app.io",
        "--hidden-import=app.sim",
        "--hidden-import=app.constants",
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
    ]
)
