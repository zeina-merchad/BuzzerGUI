import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import get_config
from app.core.loaders import load_pack, create_demo_pack, PackError
from app.core.engine import GameEngine
from app.io.ble_buzzer import BleBuzzerService
from app.io.fake_buzzer import FakeBuzzerService
from app.ui.screens.host_screen import HostScreen
from app.ui.screens.admin_dashboard import AdminDashboard


def main():
    """Main entry point for Football Buzzer application"""
    cfg_app = get_config()

    pack_dir = cfg_app.packs_dir / cfg_app.default_pack_name

    app = QApplication(sys.argv)
    app.setApplicationName("Football Trivia Game")
    app.setOrganizationName("Football Trivia Game")

    try:
        cfg, questions = load_pack(pack_dir)
        print("[OK] Loaded pack: {} ({} questions)".format(cfg.name, len(questions)))
    except PackError as e:

        print("[WARNING] Could not load pack: {}".format(e))
        print("[INFO] Creating demo pack...")
        

        demo_dir = cfg_app.packs_dir / "demo_pack"
        try:
            cfg, questions = create_demo_pack(demo_dir)
            print("[OK] Demo pack created with {} questions".format(len(questions)))
        except Exception as ex:
            print("[ERROR] Failed to create demo pack: {}".format(ex))

            from app.core.models import GameConfig, Question, Media
            from app.constants import MediaType
            
            cfg = GameConfig(
                name="Emergency Demo Pack",
                version=1,
                rounds=1,
                questions_per_round=3,
                timer_seconds=20,
                answer_seconds=8,
                shuffle_questions=False,
                question_files=[],
                pack_dir=Path.cwd(),
            )
            
            questions = [
                Question(
                    id="demo1",
                    round=1,
                    text="Who won the 2014 FIFA World Cup?",
                    options=["Germany", "Argentina", "Brazil", "France"],
                    correct_index=0,
                    media=Media(type=MediaType.NONE, path=None),
                ),
                Question(
                    id="demo2",
                    round=1,
                    text="Which player is known as 'CR7'?",
                    options=["Messi", "Ronaldo", "Neymar", "Mbappe"],
                    correct_index=1,
                    media=Media(type=MediaType.NONE, path=None),
                ),
                Question(
                    id="demo3",
                    round=1,
                    text="How many players per team in football?",
                    options=["9", "10", "11", "12"],
                    correct_index=2,
                    media=Media(type=MediaType.NONE, path=None),
                ),
            ]
        
        QMessageBox.information(
            None,
            "Demo Mode",
            "Could not load pack from:\n{}\n\n"
            "Reason:\n{}\n\n"
            "Starting in DEMO mode with sample questions.\n"
            "Open Admin Dashboard (info button) to create your own pack!".format(pack_dir, e),
        )

    try:
        engine = GameEngine(cfg, questions)
        print("[OK] Game engine initialized")
    except Exception as e:
        print("[ERROR] Failed to initialize game engine: {}".format(e))
        QMessageBox.critical(
            None,
            "Initialization Error",
            "Failed to initialize game engine:\n{}".format(e)
        )
        sys.exit(1)
    
    buzzer = FakeBuzzerService(player_ids=(1, 2, 3, 4))
    print("[INFO] Using fake buzzer service for testing")
    
     #buzzer = BleBuzzerService()
     #print("[INFO] Using real BLE buzzer service")


    try:
        from app.ui.app_window import AppWindow
        window = AppWindow(engine, buzzer)
        window.show()
        print("[OK] Application window created and shown")
    except Exception as e:
        print("[ERROR] Failed to create window: {}".format(e))
        QMessageBox.critical(
            None,
            "Window Error",
            "Failed to create application window:\n{}".format(e)
        )
        sys.exit(1)

    print("[INFO] Starting application event loop...")
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[FATAL ERROR] Unhandled exception: {}".format(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)
