from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class TimerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(150, 150)  # Larger container to prevent cropping
        
        # Circular timer exactly like reference
        self.label = QLabel("07s")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            "font-size: 42px; font-weight: 900; "
            "color: white; "
            "background: transparent; "
            "border: 6px solid #39FF14; "
            "border-radius: 60px; "
            "min-width: 120px; min-height: 120px; "
            "max-width: 120px; max-height: 120px;"
        )
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 15, 15, 15)  # Larger margins to prevent cropping
        lay.addWidget(self.label, alignment=Qt.AlignCenter)

    def set_remaining_ms(self, remaining_ms: int):
        sec = max(0, remaining_ms) / 1000.0
        self.label.setText(f"{int(sec):02d}s")
        
        # Color changes exactly like reference
        if sec <= 3.0:
            # Red - Critical
            self.label.setStyleSheet(
                "font-size: 42px; font-weight: 900; "
                "color: white; "
                "background: rgba(231, 76, 60, 0.3); "
                "border: 6px solid #ff4444; "
                "border-radius: 60px; "
                "min-width: 120px; min-height: 120px; "
                "max-width: 120px; max-height: 120px;"
            )
        elif sec <= 7.0:
            # Orange - Warning
            self.label.setStyleSheet(
                "font-size: 42px; font-weight: 900; "
                "color: white; "
                "background: rgba(243, 156, 18, 0.3); "
                "border: 6px solid #ffa500; "
                "border-radius: 60px; "
                "min-width: 120px; min-height: 120px; "
                "max-width: 120px; max-height: 120px;"
            )
        else:
            # Green - Normal (like reference)
            self.label.setStyleSheet(
                "font-size: 42px; font-weight: 900; "
                "color: white; "
                "background: transparent; "
                "border: 6px solid #39FF14; "
                "border-radius: 60px; "
                "min-width: 120px; min-height: 120px; "
                "max-width: 120px; max-height: 120px;"
            )