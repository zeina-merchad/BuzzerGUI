from PySide6.QtWidgets import QMainWindow

from app.core.engine import GameEngine
from app.io.ble_buzzer import BleBuzzerService
from app.ui.screens.host_screen import HostScreen
from app.ui.screens.admin_dashboard import AdminDashboard


class AppWindow(QMainWindow):
    def __init__(self, engine: GameEngine, buzzer: BleBuzzerService):
        super().__init__()
        self.setWindowTitle("Football Buzzer")
        self.setMinimumSize(1000, 600)

        self.engine = engine
        self.buzzer = buzzer
        self.admin_window = None


        self.buzzer.start()

        self.host = HostScreen(engine=self.engine, buzzer=self.buzzer)
        

        self.host.help_btn.clicked.disconnect() 
        self.host.help_btn.clicked.connect(self._show_admin_dashboard)
        
        self.setCentralWidget(self.host)

    def _show_admin_dashboard(self):
        """Show the admin dashboard window"""
        if self.admin_window is None or not self.admin_window.isVisible():
            from app.core.models import GameConfig
            from pathlib import Path
            
            temp_config = GameConfig(
                name="Current Game Pack",
                version=1,
                rounds=1,
                questions_per_round=len(self.engine.questions),
                timer_seconds=20,  # Default
                answer_seconds=8,   # Default
                shuffle_questions=False,
                question_files=[],
                pack_dir=Path.cwd(),
            )
            

            self.admin_window = AdminDashboard(
                temp_config,
                self.engine.questions
            )
            

            self.admin_window.config_changed.connect(self._on_config_changed)
            self.admin_window.questions_changed.connect(self._on_questions_changed)
            

            self.admin_window.setWindowTitle("Admin Dashboard - Football Buzzer")
            self.admin_window.resize(1000, 800)
            self.admin_window.show()
        else:
            self.admin_window.raise_()
            self.admin_window.activateWindow()
    
    def _on_config_changed(self, new_config):
        """Handle config changes from admin dashboard"""
        self.current_config = new_config
        print(f"Config updated: {new_config.name}, {new_config.rounds} rounds")
        print(f"Timer: {new_config.timer_seconds}s, Questions per round: {new_config.questions_per_round}")
    
    def _on_questions_changed(self, new_questions):
        """Handle questions changes from admin dashboard"""
        self.engine.questions = new_questions
        
        if self.engine.current_q_idx >= len(new_questions):
            self.engine.current_q_idx = 0
        
        if hasattr(self.engine, 'question_changed'):
            self.engine.question_changed.emit()

        if hasattr(self.host, '_render_question'):
            self.host._render_question()
        
        print(f"Questions updated: {len(new_questions)} total questions")
    
    def closeEvent(self, event):
        try:
            self.buzzer.stop()
        except Exception:
            pass
        

        if self.admin_window:
            self.admin_window.close()
        
        super().closeEvent(event)