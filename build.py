"""
Build script for FootballQuiz.

PyInstaller bundles the Python app into dist/FootballQuiz/_internal/.
This script then assembles the final distribution folder:

    dist/FootballQuiz/
        FootballQuiz          ← executable (or .exe on Windows)
        excel/
            questions.xlsx    ← user-editable; NOT inside _internal
        media/
            *.mp4  *.jpg  …   ← user-editable; NOT inside _internal
        _internal/
            app/              ← frozen Python code + sounds + logo
            …

Rules:
  • excel/ and media/ live next to the exe so users can swap content
    without touching _internal.
  • Media paths in the Excel (e.g. 'media/video.mp4') are relative to
    the folder that contains the excel/ subfolder — i.e. the dist root.
    _get_pack_root() in admin_dashboard.py detects the 'excel' folder
    name and walks up one level to find that root automatically.
"""

import os
import shutil

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "FootballQuiz")


def run_pyinstaller():
    PyInstaller.__main__.run(
        [
            "main.py",
            "--onedir",
            "--noconsole",
            "--name=FootballQuiz",
            "--clean",
            # ── Static assets baked into _internal ──────────────────────────────
            f"--add-data={ROOT}/assets:assets",
            f"--add-data={ROOT}/app:app",
            f"--add-data={ROOT}/app/ui/screens/logo.png:app/ui/screens",
            f"--add-data={ROOT}/app/ui/screens/logo_full.png:app/ui/screens",
            # NOTE: excel/ and media/ are intentionally NOT added here.
            # They are copied next to the exe in assemble_dist() below so
            # that users can update questions and media without a rebuild.
            # ── Python dependencies ──────────────────────────────────────────────
            "--collect-all=PySide6",
            "--collect-all=paho",
            "--collect-all=openpyxl",  # required for Excel import/export
            # ── Hidden imports ───────────────────────────────────────────────────
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
            # ── Exclusions ───────────────────────────────────────────────────────
            "--exclude-module=tkinter",
            "--exclude-module=matplotlib",
            "--exclude-module=PyQt5",
            "--exclude-module=PyQt6",
            "--exclude-module=PySide2",
            "--exclude-module=tensorflow",
            "--exclude-module=torch",
            "--exclude-module=numpy",
            "--exclude-module=pandas",
            "--exclude-module=scipy",
            "--exclude-module=sklearn",
            "--exclude-module=cv2",
        ]
    )


def assemble_dist():
    """Copy excel/ and media/ next to the exe (outside _internal/)."""

    # ── excel/ ───────────────────────────────────────────────────────────────
    src_excel = os.path.join(ROOT, "excel")
    dst_excel = os.path.join(DIST, "excel")

    if os.path.isdir(src_excel):
        if os.path.exists(dst_excel):
            shutil.rmtree(dst_excel)
        shutil.copytree(src_excel, dst_excel)
        print(f"[OK] Copied excel/ → {dst_excel}")
    else:
        # Create an empty excel/ folder so the app has somewhere to look.
        os.makedirs(dst_excel, exist_ok=True)
        print(f"[OK] Created empty excel/ → {dst_excel}")

    # ── media/ ───────────────────────────────────────────────────────────────
    src_media = os.path.join(ROOT, "media")
    dst_media = os.path.join(DIST, "media")

    if os.path.isdir(src_media):
        if os.path.exists(dst_media):
            shutil.rmtree(dst_media)
        shutil.copytree(src_media, dst_media)
        print(f"[OK] Copied media/ → {dst_media}")
    else:
        os.makedirs(dst_media, exist_ok=True)
        print(f"[OK] Created empty media/ → {dst_media}")

    print("\nDist layout:")
    for entry in sorted(os.listdir(DIST)):
        print(f"  {DIST}/{entry}/")


if __name__ == "__main__":
    run_pyinstaller()
    assemble_dist()
    print("\n✅ Build complete.")
    print(f"   Distribute the entire folder: {DIST}")
