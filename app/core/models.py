from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from app.constants import MediaType


@dataclass(frozen=True)
class Media:
    """Media attachment for a question"""
    type: MediaType
    path: Optional[str] = None

    def validate(self, pack_dir: Path) -> tuple[bool, str]:
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

    difficulty: str = "medium"
    tags: List[str] = field(default_factory=list)

    points_first_attempt:  int = 3
    points_second_attempt: int = 2
    points_third_attempt:  int = 1
    points_fourth_attempt: int = 0
    max_attempts: int = 3

    def __post_init__(self):
        if not self.text or not self.text.strip():
            raise ValueError("Question text cannot be empty")
        if len(self.options) < 2:
            raise ValueError("Question must have at least 2 options")
        if not (0 <= self.correct_index < len(self.options)):
            raise ValueError(f"correct_index {self.correct_index} out of range")
        if self.round < 1:
            raise ValueError("Round must be >= 1")
        if self.max_attempts < 1 or self.max_attempts > 4:
            raise ValueError("max_attempts must be between 1 and 4")
        if any(p < 0 for p in [self.points_first_attempt, self.points_second_attempt,
                                self.points_third_attempt, self.points_fourth_attempt]):
            raise ValueError("Points cannot be negative")

    def get_points_for_attempt(self, attempt_number: int) -> int:
        if attempt_number <= 0 or attempt_number > self.max_attempts:
            return 0
        points_map = {
            1: self.points_first_attempt,
            2: self.points_second_attempt,
            3: self.points_third_attempt,
            4: self.points_fourth_attempt,
        }
        return points_map.get(attempt_number, 0)

    def validate_media(self, pack_dir: Path) -> tuple[bool, str]:
        return self.media.validate(pack_dir)

    def to_dict(self) -> dict:
        return {
            "id":    self.id,
            "round": self.round,
            "text":  self.text,
            "options":       self.options,
            "correct_index": self.correct_index,
            "media": {"type": self.media.type.value, "path": self.media.path},
            "difficulty": self.difficulty,
            "tags":        self.tags,
            "points_first_attempt":  self.points_first_attempt,
            "points_second_attempt": self.points_second_attempt,
            "points_third_attempt":  self.points_third_attempt,
            "points_fourth_attempt": self.points_fourth_attempt,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True)
class GameConfig:
    """Game configuration — frozen so all fields are immutable after creation."""
    name: str
    version: int
    rounds: int
    questions_per_round: int
    timer_seconds: int
    answer_seconds: int
    shuffle_questions: bool
    question_files: Tuple[str, ...]
    pack_dir: Path

    enable_cascading_attempts: bool = True
    penalty_for_wrong: int = 0
    bonus_for_speed: bool = False
    reset_timer_each_attempt: bool = False

    points_first_attempt_default:  int = 3
    points_second_attempt_default: int = 2
    points_third_attempt_default:  int = 1
    points_fourth_attempt_default: int = 0
    max_attempts_default: int = 3

    def validate(self) -> tuple[bool, str]:
        if self.rounds <= 0:
            return False, "rounds must be >= 1"
        if self.questions_per_round <= 0:
            return False, "questions_per_round must be >= 1"
        if self.timer_seconds <= 0:
            return False, "timer_seconds must be >= 1"
        if self.answer_seconds <= 0:
            return False, "answer_seconds must be >= 1"
        if self.penalty_for_wrong < 0:
            return False, "penalty_for_wrong cannot be negative"
        return True, ""


@dataclass
class Player:
    player_id: int
    name: str
    buzzer_id: int
    color: str = "#888888"

    def __post_init__(self):
        if not (1 <= self.player_id <= 4):
            raise ValueError("player_id must be between 1 and 4")
        if not (1 <= self.buzzer_id <= 4):
            raise ValueError("buzzer_id must be between 1 and 4")


@dataclass
class AttemptRecord:
    player_id: int
    is_correct: bool
    points_awarded: int
    attempt_number: int
    buzz_time_ms: int


@dataclass
class Scoreboard:
    """Track player scores with detailed history.

    FIX #19: __post_init__ now makes a defensive copy of the scores dict so
    that a single dict literal passed by the caller cannot be mutated from
    outside (or accidentally shared between two Scoreboard instances).
    """
    scores: dict  # player_id -> score  (type annotation only, not enforced by dataclass)
    history: List[tuple] = field(default_factory=list)  # (player_id, delta, reason)

    def __post_init__(self):
        # FIX #19: defensive copy — ensures we own our dict, not a reference
        # to whatever the caller passed in.
        self.scores = {int(pid): int(score) for pid, score in self.scores.items()}

    def add(self, player_id: int, delta: int, reason: str = "") -> None:
        if player_id not in self.scores:
            self.scores[player_id] = 0
        self.scores[player_id] += delta
        self.history.append((player_id, delta, reason))

    def reset(self) -> None:
        for pid in self.scores:
            self.scores[pid] = 0
        self.history.clear()

    def get_ranking(self) -> List[tuple]:
        return sorted(self.scores.items(), key=lambda x: x[1], reverse=True)

    def get_winner(self) -> Optional[int]:
        """Return the highest-scoring player, or None on tie/empty.

        Returns None for a tie so callers must handle it explicitly rather
        than silently picking the wrong player.
        """
        if not self.scores:
            return None
        top_score = max(self.scores.values())
        winners   = [pid for pid, s in self.scores.items() if s == top_score]
        return winners[0] if len(winners) == 1 else None


@dataclass
class GameStats:
    questions_answered: int = 0
    correct_answers:    int = 0
    wrong_answers:      int = 0
    total_buzz_time_ms: int = 0
    fastest_buzz_ms: Optional[int] = None
    player_buzz_counts: dict = field(default_factory=dict)
    questions_by_attempt: dict = field(default_factory=dict)
    total_attempts: int = 0

    def record_answer(self, is_correct: bool, player_id: int, buzz_time_ms: int, attempt_number: int = 1):
        self.total_attempts += 1
        if is_correct:
            self.correct_answers += 1
            self.questions_answered += 1
            self.questions_by_attempt[attempt_number] = self.questions_by_attempt.get(attempt_number, 0) + 1
        else:
            self.wrong_answers += 1

        self.total_buzz_time_ms += buzz_time_ms
        if self.fastest_buzz_ms is None or buzz_time_ms < self.fastest_buzz_ms:
            self.fastest_buzz_ms = buzz_time_ms

        self.player_buzz_counts[player_id] = self.player_buzz_counts.get(player_id, 0) + 1

    def get_average_buzz_time(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.total_buzz_time_ms / self.total_attempts

    def get_accuracy(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return (self.correct_answers / self.total_attempts) * 100

    def get_first_attempt_success_rate(self) -> float:
        if self.questions_answered == 0:
            return 0.0
        return (self.questions_by_attempt.get(1, 0) / self.questions_answered) * 100