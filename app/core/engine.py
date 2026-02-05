import random
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from app.core.state import Phase
from app.core.models import GameConfig, Question, Scoreboard
from app.core.timer import CountdownTimer
from app.core.events import BuzzEvent


class GameEngine(QObject):
    # UI signals
    phase_changed = Signal(str)
    question_changed = Signal()
    timer_changed = Signal(int)          # remaining_ms
    lock_changed = Signal(object)        # locked_buzzer_id or None
    scores_changed = Signal()

    def __init__(self, cfg: GameConfig, questions: List[Question]):
        super().__init__()
        self.cfg = cfg
        self.questions = questions[:]
        if cfg.shuffle_questions:
            random.shuffle(self.questions)

        self.phase: Phase = Phase.IDLE
        self.q_index: int = 0
        self.locked_buzzer_id: Optional[int] = None

        # simple scoreboard: player_id == buzzer_id (1..4)
        self.scores = Scoreboard(scores={1: 0, 2: 0, 3: 0, 4: 0})

        self.timer = CountdownTimer(tick_ms=100)
        self.timer.changed.connect(self.timer_changed)
        self.timer.ended.connect(self._on_timer_ended)

    # ----- getters -----
    def current_question(self) -> Question:
        return self.questions[self.q_index]

    # ----- game actions -----
    def start_question(self) -> None:
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)

        self.timer.start(self.cfg.timer_seconds * 1000)
        self.question_changed.emit()

    def next_question(self) -> None:
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        self.q_index = (self.q_index + 1) % len(self.questions)
        self.start_question()

    def reset_buzzers_only(self) -> None:
        # does NOT change timer; just clears local lock
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

    def apply_answer(self, is_correct: bool) -> None:
        """
        Called by admin buttons (Correct/Wrong).
        Only meaningful when someone is locked.
        """
        if self.locked_buzzer_id is None:
            return

        pid = self.locked_buzzer_id
        delta = 1 if is_correct else 0  # change later if you want penalties
        self.scores.add(pid, delta)
        self.scores_changed.emit()

        # Move on after judging (simple MVP)
        self.next_question()

    # ----- buzzer input -----
    def on_buzz(self, buzzer_id: int, t_ms: int, received_ms: int) -> bool:
        """
        Returns True if this buzz wins and locks the question.
        """
        if self.phase != Phase.SHOW_QUESTION:
            return False
        if self.locked_buzzer_id is not None:
            return False

        self.locked_buzzer_id = buzzer_id
        self.lock_changed.emit(buzzer_id)

        self.phase = Phase.BUZZED
        self.phase_changed.emit(self.phase.value)

        self.timer.pause()
        return True

    # ----- internal -----
    def _on_timer_ended(self) -> None:
        self.phase = Phase.IDLE
        self.phase_changed.emit(self.phase.value)
        # You can auto-next here later if desired
