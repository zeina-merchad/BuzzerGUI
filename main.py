import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import get_config
from app.core.loaders import load_pack, PackError
from app.core.models import GameConfig, Question, Media
from app.constants import MediaType
from app.core.engine import GameEngine
from app.io.ble_buzzer import BleBuzzerService
from app.io.fake_buzzer import FakeBuzzerService

from app.ui.app_window import AppWindow


def build_demo_pack(base_dir: Path):
    cfg = GameConfig(
        name="Demo Pack (no files found)",
        version=1,
        rounds=1,
        questions_per_round=3,
        timer_seconds=20,
        answer_seconds=8,
        shuffle_questions=False,
        question_files=[],
        pack_dir=base_dir,
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
            options=["Messi", "Cristiano Ronaldo", "Neymar", "Mbappé"],
            correct_index=1,
            media=Media(type=MediaType.NONE, path=None),
        ),
        Question(
            id="demo3",
            round=1,
            text="How many players are on the field per team in football?",
            options=["9", "10", "11", "12"],
            correct_index=2,
            media=Media(type=MediaType.NONE, path=None),
        ),
    ]
    return cfg, questions


def main():
    cfg_app = get_config()

    # Try load default pack from packs/default_pack
    pack_dir = cfg_app.packs_dir / cfg_app.default_pack_name

    app = QApplication(sys.argv)

    try:
        cfg, questions = load_pack(pack_dir)
    except Exception as e:
        # fall back to demo pack to test UI
        cfg, questions = build_demo_pack(cfg_app.base_dir)

        QMessageBox.information(
            None,
            "Demo Mode",
            f"Could not load pack from:\n{pack_dir}\n\n"
            f"Reason:\n{e}\n\n"
            "Starting in DEMO mode so you can test the UI.",
        )

    engine = GameEngine(cfg, questions)
    buzzer = FakeBuzzerService(player_ids=(1, 2, 3, 4))


    window = AppWindow(engine, buzzer)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
