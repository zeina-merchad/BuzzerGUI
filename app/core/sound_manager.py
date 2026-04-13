"""
Sound Manager for Football Buzzer Game
Handles all game sound effects with fallback support
"""

from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect


class SoundManager(QObject):
    """Manages game sound effects with graceful fallback"""

    def __init__(self, sounds_dir: Path = None):
        super().__init__()

        self.sounds_dir = sounds_dir or Path(__file__).parent / "sounds"
        self.enabled = True
        self.volume = 0.7  # 0.0 to 1.0

        self._sounds = {}

        # Long sounds that need QMediaPlayer (> ~1s)
        self._long_sounds = {"correct"}
        self._media_players = {}

        self._init_sounds()

    def _init_sounds(self):
        self.sound_files = {
            "buzz": "buzz.wav",
            "correct": "correct.wav",
            "wrong": "wrong.wav",
            "timer_warning": "timer_warning.wav",
            "timer_critical": "timer_critical.wav",
            "start": "start.wav",
            "next": "next.wav",
            "point": "point.wav",
        }

        for sound_id, filename in self.sound_files.items():
            if sound_id in self._long_sounds:
                self._load_long_sound(sound_id, filename)
            else:
                self._load_sound(sound_id, filename)

    def _load_long_sound(self, sound_id: str, filename: str):
        """Use QMediaPlayer for long sounds so they play fully."""
        try:
            sound_path = self.sounds_dir / filename
            player = QMediaPlayer()
            audio_out = QAudioOutput()
            audio_out.setVolume(self.volume)
            player.setAudioOutput(audio_out)
            if sound_path.exists():
                player.setSource(QUrl.fromLocalFile(str(sound_path.resolve())))
            else:
                print(f"Sound file not found: {filename}")
            # Keep audio_out alive (parent it to player)
            audio_out.setParent(player)
            self._media_players[sound_id] = player
        except Exception as e:
            print(f"Failed to load long sound {filename}: {e}")
            self._media_players[sound_id] = None

    def _load_sound(self, sound_id: str, filename: str):
        """Load a short sound effect via QSoundEffect."""
        try:
            sound_path = self.sounds_dir / filename
            effect = QSoundEffect()
            if sound_path.exists():
                effect.setSource(QUrl.fromLocalFile(str(sound_path)))
            else:
                print(f"Sound file not found: {filename}, using fallback")
            effect.setVolume(self.volume)
            if sound_path.exists():
                try:
                    effect.play()
                    effect.stop()
                except Exception:
                    pass
            self._sounds[sound_id] = effect
        except Exception as e:
            print(f"Failed to load sound {filename}: {e}")
            self._sounds[sound_id] = None

    def play(self, sound_id: str):
        if not self.enabled:
            return
        try:
            if sound_id in self._long_sounds:
                # Long sound — stop other long sounds but never stop short ones
                for sid, player in self._media_players.items():
                    if sid != sound_id and player:
                        if (
                            player.playbackState()
                            == QMediaPlayer.PlaybackState.PlayingState
                        ):
                            player.stop()
                player = self._media_players.get(sound_id)
                if player:
                    player.setPosition(0)
                    player.play()
                else:
                    print(f"🔊 {sound_id.upper()}")
            else:
                sound = self._sounds.get(sound_id)
                if sound and sound.isLoaded():
                    # Only stop other short sounds — never kill long sounds
                    for sid, s in self._sounds.items():
                        if sid != sound_id and s and s.isPlaying():
                            s.stop()
                    sound.play()
                else:
                    print(f"🔊 {sound_id.upper()}")
        except Exception as e:
            print(f"Failed to play sound {sound_id}: {e}")

    def play_buzz(self):
        self.play("buzz")

    def play_correct(self):
        self.play("correct")

    def play_wrong(self):
        self.play("wrong")

    def play_timer_warning(self):
        self.play("timer_warning")

    def play_timer_critical(self):
        self.play("timer_critical")

    def play_start(self):
        self.play("start")

    def play_next(self):
        self.play("next")

    def play_point(self):
        self.play("point")

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))
        for sound in self._sounds.values():
            if sound:
                sound.setVolume(self.volume)
        for player in self._media_players.values():
            if player and player.audioOutput():
                player.audioOutput().setVolume(self.volume)

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def stop_all(self):
        for sound in self._sounds.values():
            if sound and sound.isPlaying():
                sound.stop()
        for player in self._media_players.values():
            if (
                player
                and player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            ):
                player.stop()


class SimpleSoundManager(QObject):
    """Simplified sound manager with console-only fallback"""

    def __init__(self):
        super().__init__()
        self.enabled = True

    def play_buzz(self):
        print("🔊 BUZZ!") if self.enabled else None

    def play_correct(self):
        print("🔊 CORRECT! ✅") if self.enabled else None

    def play_wrong(self):
        print("🔊 WRONG! ❌") if self.enabled else None

    def play_timer_warning(self):
        print("🔊 ⚠️ Warning!") if self.enabled else None

    def play_timer_critical(self):
        print("🔊 🚨 CRITICAL!") if self.enabled else None

    def play_start(self):
        print("🔊 START!") if self.enabled else None

    def play_next(self):
        print("🔊 NEXT!") if self.enabled else None

    def play_point(self):
        print("🔊 +POINT!") if self.enabled else None

    def set_volume(self, volume: float):
        pass

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def stop_all(self):
        pass


def create_sound_manager(sounds_dir: Path = None) -> QObject:
    try:
        return SoundManager(sounds_dir)
    except Exception as e:
        print(f"Failed to initialize full sound manager: {e}")
        return SimpleSoundManager()
