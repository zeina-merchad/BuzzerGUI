from PySide6.QtWidgets import QMainWindow

from app.core.engine import GameEngine
from app.io.ble_buzzer import BleBuzzerService
from app.ui.screens.host_screen import HostScreen



class AppWindow(QMainWindow):
    def __init__(self, engine: GameEngine, buzzer: BleBuzzerService):
        super().__init__()
        self.setWindowTitle("Football Buzzer")
        self.setMinimumSize(1000, 600)

        self.engine = engine
        self.buzzer = buzzer

        # Start BLE scanning/connecting (fine if no devices yet)
        self.buzzer.start()

        self.host = HostScreen(engine=self.engine, buzzer=self.buzzer)
        self.setCentralWidget(self.host)

    def closeEvent(self, event):
        try:
            self.buzzer.stop()
        except Exception:
            pass
        super().closeEvent(event)
