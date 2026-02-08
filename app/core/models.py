from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from app.constants import MediaType


@dataclass(frozen=True)
class Media:
    """Media attachment for a question"""
    type: MediaType
    path: Optional[str] = None  # relative to pack dir
    
    def validate(self, pack_dir: Path) -> tuple[bool, str]:
        """Validate media file exists"""
        if self.type == MediaType.NONE:
            return True, ""
        
        if not self.path:
            return False, f"Media path required for type {self.type.value}"
        
        abs_path = (pack_dir / self.path).resolve()
        if not abs_path.exists():
            return False, f"Media file not found: {self.path}"
        
        return True, ""


@dataclass
class Question:
    """Mutable question class with cascading points support"""
    id: str
    round: int
    text: str
    options: List[str]
    correct_index: int
    media: Media
    
    # Scoring configuration
    difficulty: str = "medium"  # easy, medium, hard
    tags: List[str] = field(default_factory=list)
    
    # NEW: Cascading points for multiple attempts
    points_first_attempt: int = 3      # Points if answered correctly on 1st try
    points_second_attempt: int = 2     # Points if answered correctly on 2nd try
    points_third_attempt: int = 1      # Points if answered correctly on 3rd try
    points_fourth_attempt: int = 0
    
    max_attempts: int = 3            # Maximum number of attempts allowed
    
    def __post_init__(self):
        """Validate question data"""
        if not self.text or not self.text.strip():
            raise ValueError("Question text cannot be empty")
        
        if len(self.options) < 2:
            raise ValueError("Question must have at least 2 options")
        
        if not (0 <= self.correct_index < len(self.options)):
            raise ValueError(f"correct_index {self.correct_index} out of range")
        
        if self.round < 1:
            raise ValueError("Round must be >= 1")
        
        if self.max_attempts < 1 or self.max_attempts > 3:
            raise ValueError("max_attempts must be between 1 and 3")
        
        # Validate points are non-negative
        if any(p < 0 for p in [self.points_first_attempt, self.points_second_attempt,
                                self.points_third_attempt]):
            raise ValueError("Points cannot be negative")
    
    def get_points_for_attempt(self, attempt_number: int) -> int:
        """Get points for a specific attempt number (1-indexed)"""
        if attempt_number <= 0 or attempt_number > self.max_attempts:
            return 0
        
        points_map = {
            1: self.points_first_attempt,
            2: self.points_second_attempt,
            3: self.points_third_attempt,
            4: self.points_fourth_attempt
        }
        
        return points_map.get(attempt_number, 0)
    
    def validate_media(self, pack_dir: Path) -> tuple[bool, str]:
        """Validate associated media"""
        return self.media.validate(pack_dir)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "round": self.round,
            "text": self.text,
            "options": self.options,
            "correct_index": self.correct_index,
            "media": {
                "type": self.media.type.value,
                "path": self.media.path
            },
            "difficulty": self.difficulty,
            "tags": self.tags,
            "points_first_attempt": self.points_first_attempt,
            "points_second_attempt": self.points_second_attempt,
            "points_third_attempt": self.points_third_attempt,
            "points_fourth_attempt": self.points_fourth_attempt,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True)
class GameConfig:
    """Game configuration with cascading attempts support"""
    name: str
    version: int
    rounds: int
    questions_per_round: int
    timer_seconds: int
    answer_seconds: int
    shuffle_questions: bool
    question_files: List[str]   # relative paths inside pack
    pack_dir: Path              # absolute path to pack root
    
    # Game modes
    enable_cascading_attempts: bool = True   # NEW: Enable multiple attempts with decreasing points
    penalty_for_wrong: int = 0               # Points deducted for wrong answer
    bonus_for_speed: bool = False            # Bonus points for fast answers
    
    # Timer behavior during cascading attempts
    reset_timer_each_attempt: bool = False   # If True, timer resets for each new attempt
    
    def validate(self) -> tuple[bool, str]:
        """Validate configuration"""
        if self.rounds <= 0:
            return False, "rounds must be >= 1"
        if self.questions_per_round <= 0:
            return False, "questions_per_round must be >= 1"
        if self.timer_seconds <= 0:
            return False, "timer_seconds must be >= 1"
        if self.answer_seconds <= 0:
            return False, "answer_seconds must be >= 1"
        if not self.question_files:
            return False, "question_files cannot be empty"
        if self.penalty_for_wrong < 0:
            return False, "penalty_for_wrong cannot be negative"
        
        return True, ""


@dataclass
class Player:
    """Player information"""
    player_id: int              # 1..4
    name: str
    buzzer_id: int              # 1..4 (same as device ID)
    color: str = "#888888"      # Display color
    
    def __post_init__(self):
        if not (1 <= self.player_id <= 4):
            raise ValueError("player_id must be between 1 and 4")
        if not (1 <= self.buzzer_id <= 4):
            raise ValueError("buzzer_id must be between 1 and 4")


@dataclass
class AttemptRecord:
    """Record of a single attempt on a question"""
    player_id: int
    is_correct: bool
    points_awarded: int
    attempt_number: int
    buzz_time_ms: int


@dataclass
class Scoreboard:
    """Track player scores with detailed history"""
    scores: dict[int, int]      # player_id -> score
    history: List[tuple[int, int, str]] = field(default_factory=list)  # (player_id, delta, reason)
    
    def __post_init__(self):
        # Ensure all scores are integers
        for pid in list(self.scores.keys()):
            self.scores[pid] = int(self.scores[pid])
    
    def add(self, player_id: int, delta: int, reason: str = "") -> None:
        """Add points to a player's score"""
        if player_id not in self.scores:
            self.scores[player_id] = 0
        
        self.scores[player_id] += delta
        self.history.append((player_id, delta, reason))
    
    def reset(self) -> None:
        """Reset all scores"""
        for pid in self.scores:
            self.scores[pid] = 0
        self.history.clear()
    
    def get_ranking(self) -> List[tuple[int, int]]:
        """Get sorted ranking (player_id, score)"""
        return sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
    
    def get_winner(self) -> Optional[int]:
        """Get the player with highest score"""
        if not self.scores:
            return None
        return max(self.scores.items(), key=lambda x: x[1])[0]


@dataclass
class GameStats:
    """Track game statistics including attempts"""
    questions_answered: int = 0
    correct_answers: int = 0
    wrong_answers: int = 0
    total_buzz_time_ms: int = 0
    fastest_buzz_ms: int = 999999
    player_buzz_counts: dict[int, int] = field(default_factory=dict)
    
    # NEW: Cascading attempts statistics
    questions_by_attempt: dict[int, int] = field(default_factory=dict)  # attempt_number -> count
    total_attempts: int = 0
    
    def record_answer(self, is_correct: bool, player_id: int, buzz_time_ms: int, attempt_number: int = 1):
        """Record an answer attempt"""
        self.total_attempts += 1
        
        if is_correct:
            self.correct_answers += 1
            self.questions_answered += 1
            
            # Track which attempt number got it right
            if attempt_number not in self.questions_by_attempt:
                self.questions_by_attempt[attempt_number] = 0
            self.questions_by_attempt[attempt_number] += 1
        else:
            self.wrong_answers += 1
        
        self.total_buzz_time_ms += buzz_time_ms
        self.fastest_buzz_ms = min(self.fastest_buzz_ms, buzz_time_ms)
        
        if player_id not in self.player_buzz_counts:
            self.player_buzz_counts[player_id] = 0
        self.player_buzz_counts[player_id] += 1
    
    def get_average_buzz_time(self) -> float:
        """Get average buzz time in ms"""
        if self.total_attempts == 0:
            return 0.0
        return self.total_buzz_time_ms / self.total_attempts
    
    def get_accuracy(self) -> float:
        """Get answer accuracy percentage"""
        if self.total_attempts == 0:
            return 0.0
        return (self.correct_answers / self.total_attempts) * 100
    
    def get_first_attempt_success_rate(self) -> float:
        """Get percentage of questions answered correctly on first attempt"""
        if self.questions_answered == 0:
            return 0.0
        first_attempt_correct = self.questions_by_attempt.get(1, 0)
        return (first_attempt_correct / self.questions_answered) * 100