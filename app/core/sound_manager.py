"""
Sound Manager for Football Buzzer Game
Handles all game sound effects with fallback support
"""

from pathlib import Path
from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect


class SoundManager(QObject):
    """Manages game sound effects with graceful fallback"""
    
    def __init__(self, sounds_dir: Path = None):
        super().__init__()
        
        self.sounds_dir = sounds_dir or Path(__file__).parent / "sounds"
        self.enabled = True
        self.volume = 0.7  # 0.0 to 1.0
        
        # Sound effects cache
        self._sounds = {}
        
        # Initialize sound effects
        self._init_sounds()
    
    def _init_sounds(self):
        """Initialize all game sounds"""
        # Define sound files (will create beep fallbacks if missing)
        self.sound_files = {
            'buzz': 'buzz.wav',
            'correct': 'correct.wav',
            'wrong': 'wrong.wav',
            'timer_warning': 'timer_warning.wav',
            'timer_critical': 'timer_critical.wav',
            'start': 'start.wav',
            'next': 'next.wav',
            'point': 'point.wav',
        }
        
        # Try to load each sound
        for sound_id, filename in self.sound_files.items():
            self._load_sound(sound_id, filename)
    
    def _load_sound(self, sound_id: str, filename: str):
        """Load a sound effect"""
        try:
            sound_path = self.sounds_dir / filename
            
            # Create QSoundEffect for short sounds
            effect = QSoundEffect()
            
            if sound_path.exists():
                effect.setSource(QUrl.fromLocalFile(str(sound_path)))
            else:
                # Use system beep as fallback
                print(f"Sound file not found: {filename}, using fallback")

            effect.setVolume(self.volume)
            # Warm-load the effect early so the first real play is less likely
            # to be dropped while the media backend is still loading.
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
        """Play a sound effect"""
        if not self.enabled:
            return
        
        try:
            sound = self._sounds.get(sound_id)
            if sound and sound.isLoaded():
                self.stop_all()
                sound.play()
            else:
                # Fallback: print to console
                print(f"🔊 {sound_id.upper()}")
        except Exception as e:
            print(f"Failed to play sound {sound_id}: {e}")
    
    def play_buzz(self):
        """Play buzzer sound"""
        self.play('buzz')
    
    def play_correct(self):
        """Play correct answer sound"""
        self.play('correct')
    
    def play_wrong(self):
        """Play wrong answer sound"""
        self.play('wrong')
    
    def play_timer_warning(self):
        """Play timer warning sound (7 seconds left)"""
        self.play('timer_warning')
    
    def play_timer_critical(self):
        """Play timer critical sound (3 seconds left)"""
        self.play('timer_critical')
    
    def play_start(self):
        """Play question start sound"""
        self.play('start')
    
    def play_next(self):
        """Play next question sound"""
        self.play('next')
    
    def play_point(self):
        """Play point awarded sound"""
        self.play('point')
    
    def set_volume(self, volume: float):
        """Set master volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        for sound in self._sounds.values():
            if sound:
                sound.setVolume(self.volume)
    
    def set_enabled(self, enabled: bool):
        """Enable or disable all sounds"""
        self.enabled = enabled
    
    def stop_all(self):
        """Stop all currently playing sounds"""
        for sound in self._sounds.values():
            if sound and sound.isPlaying():
                sound.stop()


class SimpleSoundManager(QObject):
    """Simplified sound manager with console-only fallback"""
    
    def __init__(self):
        super().__init__()
        self.enabled = True
    
    def play_buzz(self):
        if self.enabled:
            print("🔊 BUZZ!")
    
    def play_correct(self):
        if self.enabled:
            print("🔊 CORRECT! ✅")
    
    def play_wrong(self):
        if self.enabled:
            print("🔊 WRONG! ❌")
    
    def play_timer_warning(self):
        if self.enabled:
            print("🔊 ⚠️ Warning!")
    
    def play_timer_critical(self):
        if self.enabled:
            print("🔊 🚨 CRITICAL!")
    
    def play_start(self):
        if self.enabled:
            print("🔊 START!")
    
    def play_next(self):
        if self.enabled:
            print("🔊 NEXT!")
    
    def play_point(self):
        if self.enabled:
            print("🔊 +POINT!")
    
    def set_volume(self, volume: float):
        pass
    
    def set_enabled(self, enabled: bool):
        self.enabled = enabled
    
    def stop_all(self):
        pass


# Factory function to create appropriate sound manager
def create_sound_manager(sounds_dir: Path = None) -> QObject:
    """Create sound manager with fallback to simple version"""
    try:
        # Try to create full sound manager
        manager = SoundManager(sounds_dir)
        return manager
    except Exception as e:
        print(f"Failed to initialize full sound manager: {e}")
        print("Using simplified console-only sound manager")
        return SimpleSoundManager()