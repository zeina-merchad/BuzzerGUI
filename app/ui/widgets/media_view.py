from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QPixmap

class MediaView(QWidget):
    def __init__(self):
        super().__init__()
        
        self.box = QLabel()
        self.box.setAlignment(Qt.AlignCenter)
        self.box.setScaledContents(False)
        self.box.setStyleSheet(
            "border: 4px solid #39FF14; "
            "border-radius: 16px; "
            "padding: 8px; "
            "min-height: 200px; "
            "max-height: 300px; "
            "background: rgba(15, 25, 40, 0.6);"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.box)
        
        self.hide()

    def show_path(self, media_type: str, rel_path: str):
        """Show media placeholder"""
        self.show()
        
        if media_type.lower() == "image":
            icon = "🖼️"
        elif media_type.lower() == "audio":
            icon = "🔊"
        elif media_type.lower() == "video":
            icon = "🎬"
        else:
            icon = "📄"
        
        self.box.setStyleSheet(
            "border: 4px solid #39FF14; "
            "border-radius: 16px; "
            "padding: 20px; "
            "min-height: 200px; "
            "max-height: 300px; "
            "background: rgba(15, 25, 40, 0.6);"
            "font-size: 16px; font-weight: 700; color: white;"
        )
        
        self.box.setText(f"{icon}\n\n{media_type.upper()}\n{rel_path}")
    
    def show_image(self, image_path: str):
        """Load and display actual image"""
        self.show()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            # Scale to fit 16:9 aspect ratio
            scaled_pixmap = pixmap.scaled(
                600, 338,  # 16:9 ratio
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.box.setPixmap(scaled_pixmap)
            self.box.setStyleSheet(
                "border: 4px solid #39FF14; "
                "border-radius: 16px; "
                "padding: 8px; "
                "background: rgba(15, 25, 40, 0.6);"
            )