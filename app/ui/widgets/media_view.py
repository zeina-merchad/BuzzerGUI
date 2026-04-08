from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class MediaView(QWidget):
    """Enhanced media view with video/audio playback support + Fit/Fill video mode"""

    def __init__(self):
        super().__init__()

        self.current_media_type = None
        self._video_mode = "fill"  # "fit" | "fill"
        self._current_pixmap = None
        self._current_image_path = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # Image label
        self.image_box = QLabel()
        self.image_box.setAlignment(Qt.AlignCenter)
        self.image_box.setScaledContents(False)
        self.image_box.setStyleSheet(
            "border: 4px solid #39FF14; border-radius: 16px; padding: 8px; "
            "background: rgba(15, 25, 40, 0.6);"
        )
        self.image_box.setMinimumHeight(0)
        self.image_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.image_box)

        # Video widget
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet(
            "border: 4px solid #39FF14; border-radius: 16px; background: rgba(15, 25, 40, 0.9);"
        )
        self.video_widget.setMinimumHeight(250)
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_video_aspect_mode()
        main_layout.addWidget(self.video_widget)
        self.video_widget.hide()

        # Media player
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        # Controls
        self.controls_widget = QWidget()
        self.controls_widget.setStyleSheet("background: transparent;")
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)

        button_style = (
            "QPushButton { background: rgba(57,255,20,0.2); border: 2px solid #39FF14; "
            "border-radius: 8px; padding: 8px 16px; font-size: 14px; font-weight: 900; "
            "color: white; min-width: 80px; }"
            "QPushButton:hover { background: rgba(57,255,20,0.4); }"
            "QPushButton:pressed { background: rgba(57,255,20,0.6); }"
        )

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setStyleSheet(button_style)

        self.btn_stop = QPushButton("■ Stop")
        self.btn_stop.setStyleSheet(button_style)

        self.btn_fitfill = QPushButton("⛶ Fill")
        self.btn_fitfill.setStyleSheet(button_style)

        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._stop_media)
        self.btn_fitfill.clicked.connect(self._toggle_fit_fill)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.7);"
        )
        self.status_label.setAlignment(Qt.AlignCenter)

        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addWidget(self.btn_fitfill)
        controls_layout.addStretch()
        controls_layout.addWidget(self.status_label)

        main_layout.addWidget(self.controls_widget)
        self.controls_widget.hide()

        main_layout.setStretchFactor(self.image_box, 1)
        main_layout.setStretchFactor(self.video_widget, 1)
        main_layout.setStretchFactor(self.controls_widget, 0)

        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.media_player.errorOccurred.connect(self._on_error)

        self.hide()

    def clear(self):
        self._stop_media()
        self.current_media_type = None
        self._current_pixmap = None
        self._current_image_path = None
        self.image_box.setPixmap(QPixmap())
        self.image_box.setText("")
        self.image_box.setMinimumHeight(250)
        self.image_box.setMaximumHeight(16777215)
        self._hide_video()
        self.hide()

    def set_media(self, media, pack_dir):
        from pathlib import Path

        if media is None or media.type.value == "none":
            self.clear()
            return

        media_path = (Path(pack_dir) / (media.path or "")).resolve()
        if not media_path.exists():
            self.show_path(media.type.value, media.path or "")
            return

        if media.type.value == "image":
            self.show_image(str(media_path))
        elif media.type.value == "video":
            self.show_video(str(media_path))
        elif media.type.value == "audio":
            self.show_audio(str(media_path))
        else:
            self.show_path(media.type.value, media.path or "")

    def show_path(self, media_type: str, rel_path: str):
        self.show()
        self._stop_media()
        self._hide_video()

        self.image_box.setPixmap(QPixmap())
        icons = {"image": "🖼️", "audio": "🔊", "video": "🎬"}
        icon = icons.get(media_type.lower(), "📄")

        self.image_box.setMinimumHeight(200)
        self.image_box.setMaximumHeight(250)
        self.image_box.setStyleSheet(
            "border: 4px solid #39FF14; border-radius: 16px; padding: 20px; "
            "min-height: 200px; max-height: 250px; background: rgba(15,25,40,0.6); "
            "font-size: 16px; font-weight: 700; color: white;"
        )
        self.image_box.setText(f"{icon}\n\n{media_type.upper()}\n{rel_path}")
        self.image_box.show()
        self.controls_widget.hide()

    def show_image(self, image_path: str):
        self.show()
        self._stop_media()
        self._hide_video()

        self.current_media_type = "image"
        self.image_box.setText("")

        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.image_box.setMinimumHeight(0)
            self.image_box.setMaximumHeight(16777215)
            self._current_pixmap = pixmap
            self._current_image_path = image_path
            self._scale_pixmap_to_box()
            self.image_box.setStyleSheet(
                "border: 4px solid #39FF14; border-radius: 16px; "
                "padding: 15px; background: rgba(15,25,40,0.6);"
            )
            self.image_box.show()
            self.controls_widget.hide()
            self.updateGeometry()
            self.update()
        else:
            self._current_pixmap = None
            self._current_image_path = None
            self._show_error(f"IMAGE NOT FOUND\n\n{image_path}")

    def _scale_pixmap_to_box(self):
        if self._current_pixmap is None:
            return

        box_size = self.image_box.size()
        w = max(box_size.width() - 8, 400)
        h = max(box_size.height() - 8, 300)
        scaled = self._current_pixmap.scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_box.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_media_type == "image":
            self._scale_pixmap_to_box()

    def show_video(self, video_path: str):
        self.show()
        self._stop_media()

        self.current_media_type = "video"

        self.image_box.setPixmap(QPixmap())
        self.image_box.setText("")
        self.image_box.setMinimumHeight(0)
        self.image_box.setMaximumHeight(16777215)
        self.image_box.hide()

        self.video_widget.setMinimumHeight(250)
        self.video_widget.show()
        self.controls_widget.show()
        self.btn_fitfill.show()
        self._sync_fitfill_button()

        self.video_widget.updateGeometry()
        self.updateGeometry()
        self.update()

        try:
            from pathlib import Path

            path = Path(video_path)

            if not path.exists():
                self._show_error(f"Video not found: {video_path}")
                return

            url = QUrl.fromLocalFile(str(path.absolute()))
            self.media_player.setSource(url)
            self.media_player.setVideoOutput(self.video_widget)
            self.status_label.setText(f"Loaded: {path.name}")
            self.media_player.play()

        except Exception as e:
            self._show_error(f"Error loading video: {e}")

    def show_audio(self, audio_path: str):
        self.show()
        self._stop_media()

        self.current_media_type = "audio"
        self.image_box.show()
        self.video_widget.hide()
        self.controls_widget.show()
        self.btn_fitfill.hide()

        from pathlib import Path

        path = Path(audio_path)

        self.image_box.setMinimumHeight(200)
        self.image_box.setMaximumHeight(250)
        self.image_box.setStyleSheet(
            "border: 4px solid #39FF14; border-radius: 16px; padding: 20px; "
            "min-height: 200px; max-height: 250px; background: rgba(15,25,40,0.6); "
            "font-size: 18px; font-weight: 700; color: white;"
        )
        self.image_box.setText(f"🔊\n\nAUDIO\n\n{path.name}")

        try:
            if not path.exists():
                self._show_error(f"Audio not found: {audio_path}")
                return

            url = QUrl.fromLocalFile(str(path.absolute()))
            self.media_player.setSource(url)
            self.status_label.setText(f"Loaded: {path.name}")
            self.media_player.play()

        except Exception as e:
            self._show_error(f"Error loading audio: {e}")

    def _toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _stop_media(self):
        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.media_player.stop()

    def _toggle_fit_fill(self):
        if self.current_media_type != "video":
            return

        self._video_mode = "fit" if self._video_mode == "fill" else "fill"
        self._apply_video_aspect_mode()
        self._sync_fitfill_button()

    def _apply_video_aspect_mode(self):
        mode = (
            Qt.AspectRatioMode.KeepAspectRatioByExpanding
            if self._video_mode == "fill"
            else Qt.AspectRatioMode.KeepAspectRatio
        )
        try:
            self.video_widget.setAspectRatioMode(mode)
        except Exception:
            self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)

    def _sync_fitfill_button(self):
        base = self.status_label.text().split(" | ")[0]
        if self._video_mode == "fill":
            self.btn_fitfill.setText("⛶ Fill")
            self.status_label.setText(base + " | Mode: Fill")
        else:
            self.btn_fitfill.setText("▭ Fit")
            self.status_label.setText(base + " | Mode: Fit")

    def _hide_video(self):
        self.video_widget.hide()
        self.controls_widget.hide()

    def _show_error(self, message: str):
        self.image_box.show()
        self.video_widget.hide()
        self.controls_widget.hide()
        self.image_box.setPixmap(QPixmap())
        self.image_box.setMinimumHeight(200)
        self.image_box.setMaximumHeight(250)
        self.image_box.setStyleSheet(
            "border: 4px solid #e74c3c; border-radius: 16px; padding: 20px; "
            "min-height: 200px; max-height: 250px; background: rgba(231,76,60,0.2); "
            "font-size: 14px; font-weight: 700; color: #e74c3c;"
        )
        self.image_box.setText(f"⚠️ ERROR\n\n{message}")

    def _on_playback_state_changed(self, state):
        mode_suffix = ""
        if " | Mode:" in self.status_label.text():
            mode_suffix = " | " + self.status_label.text().split(" | ", 1)[1]

        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸ Pause")
            self.status_label.setText("Playing..." + mode_suffix)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.btn_play.setText("▶ Play")
            self.status_label.setText("Paused" + mode_suffix)
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            self.btn_play.setText("▶ Play")
            self.status_label.setText("Stopped" + mode_suffix)

    def _on_error(self, error, error_string: str):
        self._show_error(f"Playback error: {error_string}")

    def cleanup(self):
        self._stop_media()
        self.media_player.setSource(QUrl())
        self.current_media_type = None
        self._current_pixmap = None
        self._current_image_path = None
        self._hide_video()
