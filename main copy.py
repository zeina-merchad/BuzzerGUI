"""
Football Buzzer - UI Preview Mode (No Backend Required)
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtCore import QTimer

from app.core.models import GameConfig, Question, Media
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
        # Return all 4 players as connected
        return [1, 2, 3, 4]
    
    def disconnect(self):
        print("[FAKE MQTT] Disconnected")


class AppWindow(QMainWindow):
    """Main application window with admin dashboard support"""
    
    def __init__(self, engine: GameEngine, fake_mqtt: FakeMQTT):
        super().__init__()
        self.setWindowTitle("Football Buzzer - UI Preview Mode")
        self.setMinimumSize(1400, 900)

        self.engine = engine
        self.mqtt_backend = fake_mqtt
        self.admin_window = None

        # Create host screen
        self.host = HostScreen(engine=self.engine, mqtt_backend=self.mqtt_backend)
        
        # Replace help button with admin dashboard opener
        self.host.help_btn.setText("⚙️ ADMIN")
        self.host.help_btn.clicked.disconnect() 
        self.host.help_btn.clicked.connect(self._open_admin_dashboard)
        
        self.setCentralWidget(self.host)
        
        # Simulate player connections after a short delay
        QTimer.singleShot(500, lambda: self._simulate_connection(1))
        QTimer.singleShot(700, lambda: self._simulate_connection(2))
        QTimer.singleShot(900, lambda: self._simulate_connection(3))
        QTimer.singleShot(1100, lambda: self._simulate_connection(4))
    
    def _simulate_connection(self, player_id: int):
        """Simulate player connection"""
        print(f"[FAKE] ✓ Player {player_id} connected")
        if hasattr(self.host, '_on_buzzer_connected'):
            self.host._on_buzzer_connected(player_id, True)
    
    def _open_admin_dashboard(self):
        """Open admin dashboard window"""
        # Close existing admin window if open
        if self.admin_window and self.admin_window.isVisible():
            self.admin_window.raise_()
            self.admin_window.activateWindow()
            return
        
        # Create new admin dashboard
        self.admin_window = AdminDashboard(
            config=self.engine.cfg,
            questions=self.engine.questions
        )
        
        # Connect signals to update engine when changes are saved
        self.admin_window.config_changed.connect(self._on_config_changed)
        self.admin_window.questions_changed.connect(self._on_questions_changed)
        self.admin_window.pack_saved.connect(self._on_pack_saved)
        
        # Show the dashboard
        self.admin_window.show()
        print("\n[ADMIN] 🛠️ Admin Dashboard opened")
    
    def _on_config_changed(self, new_config: GameConfig):
        """Handle config changes from admin dashboard"""
        print(f"\n[ADMIN] 💾 Config updated: {new_config.name}")
        self.engine.cfg = new_config
        
        # Update host screen with new config if needed
        if hasattr(self.host, 'engine'):
            self.host.engine.cfg = new_config
    
    def _on_questions_changed(self, new_questions: list):
        """Handle questions changes from admin dashboard"""
        print(f"\n[ADMIN] 📝 Questions updated: {len(new_questions)} questions")
        self.engine.questions = new_questions
        
        # Reset game to use new questions
        if hasattr(self.host, 'engine'):
            self.host.engine.questions = new_questions
    
    def _on_pack_saved(self, pack_path: str):
        """Handle pack save"""
        print(f"\n[ADMIN] 💾 Pack saved to: {pack_path}")
        QMessageBox.information(
            self, "Pack Saved",
            f"✓ Pack saved successfully!\n\nLocation:\n{pack_path}"
        )
    
    def closeEvent(self, event):
        """Clean shutdown"""
        # Close admin window if open
        if self.admin_window and self.admin_window.isVisible():
            self.admin_window.close()
        
        if self.mqtt_backend:
            self.mqtt_backend.disconnect()
        
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Football Buzzer - UI Preview")
    
    # Create demo questions with cascading points
    questions = [
        Question(
            id="demo1",
            round=1,
            text="Who won the 2014 FIFA World Cup?",
            options=["Germany", "Argentina", "Brazil", "France"],
            correct_index=0,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["world_cup"],
            points_first_attempt=3,
            points_second_attempt=2,
            points_third_attempt=1,
            points_fourth_attempt=0,
            max_attempts=3,
        ),
        Question(
            id="demo2",
            round=1,
            text="Which player is known as 'CR7'?",
            options=["Messi", "Ronaldo", "Neymar", "Mbappe"],
            correct_index=1,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["players"],
            points_first_attempt=3,
            points_second_attempt=2,
            points_third_attempt=1,
            points_fourth_attempt=0,
            max_attempts=3,
        ),
        Question(
            id="demo3",
            round=1,
            text="How many players per team in football?",
            options=["9", "10", "11", "12"],
            correct_index=2,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["rules"],
            points_first_attempt=2,
            points_second_attempt=1,
            points_third_attempt=1,
            points_fourth_attempt=0,
            max_attempts=2,
        ),
        Question(
            id="demo4",
            round=1,
            text="Which country hosted the 2018 World Cup?",
            options=["Brazil", "Russia", "Qatar", "France"],
            correct_index=1,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="medium",
            tags=["world_cup", "history"],
            points_first_attempt=5,
            points_second_attempt=3,
            points_third_attempt=2,
            points_fourth_attempt=1,
            max_attempts=4,
        ),
        Question(
            id="demo5",
            round=1,
            text="What color card is shown for ejection?",
            options=["Yellow", "Red", "Green", "Blue"],
            correct_index=1,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["rules"],
            points_first_attempt=3,
            points_second_attempt=2,
            points_third_attempt=1,
            points_fourth_attempt=0,
            max_attempts=3,
        ),
    ]
    
    # Create config with global scoring defaults
    cfg = GameConfig(
        name="UI Preview Pack",
        version=1,
        rounds=2,
        questions_per_round=5,
        timer_seconds=20,
        answer_seconds=8,
        shuffle_questions=False,
        question_files=["dummy.json"],  # Dummy file to pass validation
        pack_dir=Path.cwd(),
        enable_cascading_attempts=True,
        reset_timer_each_attempt=False,
        penalty_for_wrong=0,
        bonus_for_speed=False,
        # NEW: Global scoring defaults
        points_first_attempt_default=3,
        points_second_attempt_default=2,
        points_third_attempt_default=1,
        points_fourth_attempt_default=0,
        max_attempts_default=3,
    )
    
    # Create engine
    engine = GameEngine(cfg, questions)
    
    # Create fake MQTT backend
    fake_mqtt = FakeMQTT()
    
    # Create and show window
    window = AppWindow(engine, fake_mqtt)
    window.show()
    
    # Print instructions
    print("\n" + "="*60)
    print(" FOOTBALL BUZZER - UI PREVIEW MODE")
    print("="*60)
    print(" All 4 players will appear connected")
    print(" Click START to begin question")
    print(" Press U to unlock buzzers (visual only)")
    print(" Use keyboard shortcuts to test UI")
    print("")
    print(" 🛠️  ADMIN DASHBOARD:")
    print("  Click '⚙️ ADMIN' button to open dashboard")
    print("  • Edit questions and scoring")
    print("  • Configure global settings")
    print("  • Change points per attempt")
    print("  • Set max attempts and penalties")
    print("")
    print(" ⌨️  Keyboard Shortcuts:")
    print("  Enter       - Start question")
    print("  U           - Unlock buzzers")
    print("  Up Arrow    - Mark correct")
    print("  Down Arrow  - Mark wrong")
    print("  Right Arrow - Next question")
    print("  Space       - Reset game")
    print("")
    print(" 🎮 Game Flow:")
    print("  1. Press Enter to start question")
    print("  2. Timer starts (buzzers locked 🔒)")
    print("  3. Press U to unlock buzzers 🔓")
    print("  4. Players can buzz (simulated)")
    print("  5. Judge with Up/Down arrows")
    print("  6. Next question with Right arrow")
    print("="*60 + "\n")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()