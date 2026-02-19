import random
import time
from typing import List, Optional, Set
from collections import deque

from PySide6.QtCore import QObject, Signal

from app.core.state import Phase
from app.core.models import GameConfig, Question, Scoreboard, GameStats, AttemptRecord
from app.core.timer import CountdownTimer


class GameEngine(QObject):
    """Game engine with cascading attempts - External MQTT backend"""

    # UI signals
    phase_changed = Signal(str)
    question_changed = Signal()
    timer_changed = Signal(int)          # remaining_ms
    lock_changed = Signal(object)        # locked_buzzer_id or None
    scores_changed = Signal()
    stats_changed = Signal()
    error_occurred = Signal(str)

    # Cascading attempts signals
    attempt_changed = Signal(int)        # current_attempt_number (1-3)
    attempt_failed = Signal(int, int)    # (player_id, attempt_number)

    # ✅ NEW: fired whenever engine advances to a NEW question
    # HostScreen uses this to reset UI + forgive eliminated players + reset MQTT question state
    question_advanced = Signal()

    def __init__(self, cfg: GameConfig, questions: List[Question]):
        super().__init__()

        # Validate configuration
        valid, error = cfg.validate()
        if not valid:
            raise ValueError(f"Invalid configuration: {error}")

        self.cfg = cfg
        # Filter out disabled questions before storing
        self.original_questions = [q for q in questions if getattr(q, 'enabled', True)]
        self.questions = self.original_questions[:]

        if cfg.shuffle_questions:
            random.shuffle(self.questions)

        # Game state
        self.phase: Phase = Phase.IDLE
        self.current_q_idx: int = 0
        self.locked_buzzer_id: Optional[int] = None
        self.question_start_time_ms: int = 0

        # Cascading attempts tracking
        self.current_attempt_number: int = 0
        self.players_attempted: Set[int] = set()
        self.attempt_records: List[AttemptRecord] = []

        # Scoreboard
        self.scores = Scoreboard(scores={1: 0, 2: 0, 3: 0, 4: 0})

        # Statistics
        self.stats = GameStats()

        # Undo/Redo stacks
        self._undo_stack: deque = deque(maxlen=50)
        self._redo_stack: deque = deque(maxlen=50)

        # Timer
        self.timer = CountdownTimer(tick_ms=100)
        self.timer.changed.connect(self.timer_changed)
        self.timer.ended.connect(self._on_timer_ended)

        # Track answered questions
        self.answered_questions: set[int] = set()

    # =========================================================================
    # GETTERS
    # =========================================================================

    def current_question(self) -> Question:
        """Get current question"""
        if not self.questions:
            raise IndexError("No questions available")
        return self.questions[self.current_q_idx]

    def get_progress(self) -> tuple[int, int]:
        """Get (current_index, total_questions)"""
        return (self.current_q_idx + 1, len(self.questions))

    def get_remaining_questions(self) -> int:
        """Get number of unanswered questions"""
        return len(self.questions) - len(self.answered_questions)

    def get_current_attempt_number(self) -> int:
        """Get current attempt number for this question"""
        return self.current_attempt_number

    def get_players_remaining(self) -> List[int]:
        """Get list of players who haven't attempted yet"""
        all_players = {1, 2, 3, 4}
        return sorted(list(all_players - self.players_attempted))

    def get_points_for_current_attempt(self) -> int:
        """Get points available for current attempt"""
        question = self.current_question()
        return question.get_points_for_attempt(self.current_attempt_number)

    # =========================================================================
    # GAME CONTROL
    # =========================================================================

    def start_question(self) -> None:
        """Start showing current question - timer will start when admin unlocks"""
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        self.question_start_time_ms = int(time.time() * 1000)

        # Reset attempt tracking
        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.attempt_changed.emit(self.current_attempt_number)

        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)

        # Keep timer stopped until admin unlocks
        self.timer.stop()

        self.question_changed.emit()

        print(f"[ENGINE] Question started: {self.current_question().text[:50]}...")
        print(f"[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")

    def next_question(self) -> None:
        """
        Move to next question.

        ✅ FIX #1:
        After sliding to next question, engine MUST be in SHOW_QUESTION so admin can UNLOCK.

        ✅ FIX #2:
        Emit question_advanced so HostScreen can do per-question reset:
        - forgive eliminated players (UI)
        - reset cascading widget
        - call mqtt_backend.start_question(...) to clear MQTT eliminated_players
        """
        # Clear any lock
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        # Move index
        self.current_q_idx = (self.current_q_idx + 1) % len(self.questions)

        # If all questions are answered -> end game
        if len(self.answered_questions) >= len(self.questions):
            self.end_game()
            return

        # Prepare next question state (WAITING FOR ADMIN)
        self.question_start_time_ms = int(time.time() * 1000)

        # Reset attempt tracking for the new question
        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.attempt_changed.emit(self.current_attempt_number)

        # Keep timer stopped until admin unlocks
        self.timer.stop()

        # IMPORTANT: Put engine in SHOW_QUESTION (not IDLE)
        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)

        # Trigger UI to render the new question
        self.question_changed.emit()

        # ✅ Let HostScreen reset UI + MQTT per-question state
        self.question_advanced.emit()

        print(f"[ENGINE] Next question ready: Q{self.current_q_idx + 1}")
        print(f"[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")

    def skip_question(self) -> None:
        """Skip current question without scoring"""
        self.answered_questions.add(self.current_q_idx)
        self.next_question()

    def reset_game(self) -> None:
        """Reset entire game"""
        self.scores.reset()
        self.stats = GameStats()
        self.answered_questions.clear()
        self.current_q_idx = 0
        
        # Release any locked buzzers
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        
        self.phase = Phase.IDLE
        self.current_attempt_number = 0
        self.players_attempted.clear()
        self.attempt_records.clear()

        if self.cfg.shuffle_questions:
            self.questions = self.original_questions[:]
            random.shuffle(self.questions)

        self._undo_stack.clear()
        self._redo_stack.clear()

        self.timer.stop()

        self.phase_changed.emit(self.phase.value)
        self.scores_changed.emit()
        self.stats_changed.emit()
        self.question_changed.emit()

        print("[ENGINE] Game reset - all locks released")

    def end_game(self) -> None:
        """End the game"""
        self.phase = Phase.GAME_END
        self.phase_changed.emit(self.phase.value)
        self.timer.stop()
        print("[ENGINE] Game ended")

    # =========================================================================
    # ANSWER HANDLING WITH CASCADING ATTEMPTS
    # =========================================================================

    def apply_answer(self, is_correct: bool) -> None:
        """Apply answer judgement with cascading attempts support"""
        if self.locked_buzzer_id is None:
            self.error_occurred.emit("No player has buzzed in")
            return

        pid = self.locked_buzzer_id
        question = self.current_question()

        # Calculate buzz time
        current_time_ms = int(time.time() * 1000)
        buzz_time_ms = current_time_ms - self.question_start_time_ms

        # Get points for this attempt
        points_for_attempt = question.get_points_for_attempt(self.current_attempt_number)

        if is_correct:
            # CORRECT ANSWER
            points = points_for_attempt

            # Bonus for speed (if enabled and first attempt)
            if self.cfg.bonus_for_speed and self.current_attempt_number == 1 and buzz_time_ms < 3000:
                points += 1

            reason = f"Correct on attempt {self.current_attempt_number} - Q{self.current_q_idx + 1}"

            # Save state for undo
            self._save_state_for_undo(pid, points, is_correct, self.current_q_idx)

            # Apply score
            self.scores.add(pid, points, reason)
            self.scores_changed.emit()

            # Update statistics
            self.stats.record_answer(True, pid, buzz_time_ms, self.current_attempt_number)
            self.stats_changed.emit()

            # Record attempt
            self.attempt_records.append(AttemptRecord(
                player_id=pid,
                is_correct=True,
                points_awarded=points,
                attempt_number=self.current_attempt_number,
                buzz_time_ms=buzz_time_ms
            ))

            # Mark question as answered
            self.answered_questions.add(self.current_q_idx)

            print(f"[ENGINE] ✓ Player {pid} correct! +{points} pts (Attempt {self.current_attempt_number})")
            
            # ✅ FIX: Do NOT auto-advance to next question
            # Admin should always control question advancement via NEXT button
            # Just put engine in IDLE state and wait for admin
            self.locked_buzzer_id = None
            self.lock_changed.emit(None)
            self.timer.stop()
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)
            
            print(f"[ENGINE] ⏸️ Question complete - waiting for admin to advance")

        else:
            # WRONG ANSWER
            if self.cfg.penalty_for_wrong > 0:
                penalty = -self.cfg.penalty_for_wrong
                reason = f"Wrong answer - Q{self.current_q_idx + 1}"
                self.scores.add(pid, penalty, reason)
                self.scores_changed.emit()

            self.stats.record_answer(False, pid, buzz_time_ms, self.current_attempt_number)
            self.stats_changed.emit()

            self.attempt_records.append(AttemptRecord(
                player_id=pid,
                is_correct=False,
                points_awarded=-self.cfg.penalty_for_wrong if self.cfg.penalty_for_wrong > 0 else 0,
                attempt_number=self.current_attempt_number,
                buzz_time_ms=buzz_time_ms
            ))

            # Mark this player as attempted
            self.players_attempted.add(pid)

            # Emit attempt failed signal
            self.attempt_failed.emit(pid, self.current_attempt_number)

            print(f"[ENGINE]  Player {pid} wrong (Attempt {self.current_attempt_number})")

            # Cascading attempts logic
            if self.cfg.enable_cascading_attempts and self.current_attempt_number < question.max_attempts:
                remaining_players = self.get_players_remaining()
                if remaining_players:
                    self.current_attempt_number += 1
                    self.attempt_changed.emit(self.current_attempt_number)

                    self.locked_buzzer_id = None
                    self.lock_changed.emit(None)

                    self.timer.stop()

                    self.phase = Phase.SHOW_QUESTION
                    self.phase_changed.emit(self.phase.value)

                    print(f"[ENGINE] → Next attempt available ({self.current_attempt_number}/{question.max_attempts})")
                    print(f"[ENGINE] → Remaining players: {remaining_players}")
                    return

            # No more attempts
            print(f"[ENGINE] → No more attempts available")
            self.answered_questions.add(self.current_q_idx)
            
            # ✅ FIX: Do NOT auto-advance to next question
            # Admin should always control question advancement via NEXT button
            # Just put engine in IDLE state and wait for admin
            self.locked_buzzer_id = None
            self.lock_changed.emit(None)
            self.timer.stop()
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)
            
            print(f"[ENGINE] ⏸️ All attempts exhausted - waiting for admin to advance")

    # =========================================================================
    # BUZZER INPUT
    # =========================================================================

    def on_buzz(self, buzzer_id: int, t_ms: int, received_ms: int) -> bool:
        """Handle buzz event with cascading attempts support"""
        if self.phase != Phase.SHOW_QUESTION:
            print(f"[ENGINE]   Buzz rejected - wrong phase ({self.phase.value})")
            return False

        if buzzer_id in self.players_attempted:
            self.error_occurred.emit(f"Player {buzzer_id} already attempted this question")
            print(f"[ENGINE]   Player {buzzer_id} already attempted")
            return False

        if self.locked_buzzer_id is not None:
            print(f"[ENGINE]   Buzz rejected - Player {self.locked_buzzer_id} already locked")
            return False

        self.locked_buzzer_id = buzzer_id
        self.lock_changed.emit(buzzer_id)

        self.phase = Phase.BUZZED
        self.phase_changed.emit(self.phase.value)

        # Stop question timer and start answer timer
        self.timer.stop()
        answer_time_ms = self.cfg.answer_seconds * 1000
        self.timer.start(answer_time_ms)

        print(f"[ENGINE]  Player {buzzer_id} BUZZED IN (Attempt {self.current_attempt_number})")
        print(f"[ENGINE]  Answer timer started: {self.cfg.answer_seconds}s to answer")
        return True

    # =========================================================================
    # UNDO/REDO
    # =========================================================================

    def _save_state_for_undo(self, player_id: int, points: int, is_correct: bool, question_idx: int):
        state = {
            'player_id': player_id,
            'points': points,
            'is_correct': is_correct,
            'question_idx': question_idx,
            'scores_snapshot': self.scores.scores.copy()
        }
        self._undo_stack.append(state)
        self._redo_stack.clear()

    # =========================================================================
    # INTERNAL CALLBACKS
    # =========================================================================

    def _on_timer_ended(self) -> None:
        """Handle timer expiration"""
        if self.phase == Phase.SHOW_QUESTION:
            # Question timer expired - no one buzzed in time
            self.answered_questions.add(self.current_q_idx)
            print("[ENGINE] ⏰ Question time's up! No one buzzed.")
            
            # Don't auto-advance - admin controls progression
            self.locked_buzzer_id = None
            self.lock_changed.emit(None)
            self.timer.stop()
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)
            
            print(f"[ENGINE] ⏸️ Waiting for admin to advance")
            
        elif self.phase == Phase.BUZZED:
            # Answer timer expired - player didn't answer in time
            pid = self.locked_buzzer_id
            print(f"[ENGINE] ⏰ Answer time's up! Player {pid} didn't answer in time.")
            
            # Treat as wrong answer
            if pid:
                # Apply penalty if configured
                if self.cfg.penalty_for_wrong > 0:
                    penalty = -self.cfg.penalty_for_wrong
                    reason = f"Timeout - Q{self.current_q_idx + 1}"
                    self.scores.add(pid, penalty, reason)
                    self.scores_changed.emit()
                
                # Mark player as attempted
                self.players_attempted.add(pid)
                
                # Emit attempt failed signal
                self.attempt_failed.emit(pid, self.current_attempt_number)
                
                # Cascading attempts logic
                question = self.current_question()
                if self.cfg.enable_cascading_attempts and self.current_attempt_number < question.max_attempts:
                    remaining_players = self.get_players_remaining()
                    if remaining_players:
                        self.current_attempt_number += 1
                        self.attempt_changed.emit(self.current_attempt_number)
                        
                        self.locked_buzzer_id = None
                        self.lock_changed.emit(None)
                        
                        self.timer.stop()
                        
                        self.phase = Phase.SHOW_QUESTION
                        self.phase_changed.emit(self.phase.value)
                        
                        print(f"[ENGINE] → Next attempt available ({self.current_attempt_number}/{question.max_attempts})")
                        print(f"[ENGINE] → Remaining players: {remaining_players}")
                        return
                
                # No more attempts
                print(f"[ENGINE] → No more attempts available")
                self.answered_questions.add(self.current_q_idx)
                
                # Don't auto-advance - admin controls progression
                self.locked_buzzer_id = None
                self.lock_changed.emit(None)
                self.timer.stop()
                self.phase = Phase.IDLE
                self.phase_changed.emit(self.phase.value)
                
                print(f"[ENGINE] ⏸️ All attempts exhausted - waiting for admin to advance")