from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from app.constants import MediaType

@dataclass(frozen=True)
class Media:
    type: MediaType
    path: Optional[str] = None  # relative to pack dir (e.g. media/images/q1.png)

@dataclass(frozen=True)
class Question:
    id: str
    round: int
    text: str
    options: List[str]
    correct_index: int
    media: Media

@dataclass(frozen=True)
class GameConfig:
    name: str
    version: int
    rounds: int
    questions_per_round: int
    timer_seconds: int
    answer_seconds: int
    shuffle_questions: bool
    question_files: List[str]   # relative paths inside pack
    pack_dir: Path              # absolute path to pack root

@dataclass
class Player:
    player_id: int              # 1..4
    name: str
    buzzer_id: int              # 1..4 (same as device ID)

@dataclass
class Scoreboard:
    scores: dict[int, int]      # player_id -> score

    def __post_init__(self):
        for pid in list(self.scores.keys()):
            self.scores[pid] = int(self.scores[pid])

    def add(self, player_id: int, delta: int) -> None:
        self.scores[player_id] = int(self.scores.get(player_id, 0) + delta)
