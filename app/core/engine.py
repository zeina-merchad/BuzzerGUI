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

    # Fired whenever engine advances to a NEW question.
    # HostScreen uses this to reset UI + forgive eliminated players + reset MQTT question state.
    question_advanced = Signal()

    def __init__(self, cfg: GameConfig, questions: List[Question]):
        super().__init__()

        # Skip the normal validation that requires question_files to be non-empty
        # when starting empty (questions will arrive from AdminDashboard later)
        if questions:
            valid, error = cfg.validate()
            if not valid:
                raise ValueError(f"Invalid configuration: {error}")

        self.cfg = cfg
        self.original_questions = [q for q in questions if getattr(q, 'enabled', True)]
        self.questions = self.original_questions[:]

        if cfg.shuffle_questions and self.questions:
            random.shuffle(self.questions)

        # Game state
        self.phase: Phase = Phase.IDLE
        self.current_q_idx: int = 0
        self.locked_buzzer_id: Optional[int] = None
        self.question_start_time_ms: int = 0
        # FIX #6: track when buzzers were actually unlocked so speed bonus is meaningful
        self.buzz_unlock_time_ms: int = 0


        # Timer bookkeeping (so we can resume question time after buzz/attempts)
        self._question_remaining_ms: int = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms: int = 0
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
        # We keep our own remaining-ms bookkeeping so HostScreen can resume question time
        self.timer.changed.connect(self._on_timer_changed)
        self.timer.ended.connect(self._on_timer_ended)
        # Track answered questions
        self.answered_questions: set[int] = set()

    
    # =========================================================================
    # TIMER BOOKKEEPING
    # =========================================================================

    def _on_timer_changed(self, remaining_ms: int) -> None:
        """Internal timer tick handler.

        Keeps separate remaining-time bookkeeping for question vs answer so we can:
          - pause question time when someone buzzes
          - resume it on next attempt (if configured)
        """
        if self.phase == Phase.SHOW_QUESTION:
            self._question_remaining_ms = int(remaining_ms)
        elif self.phase == Phase.BUZZED:
            self._answer_remaining_ms = int(remaining_ms)

        # Always forward to UI
        self.timer_changed.emit(int(remaining_ms))

    def start_or_resume_question_timer(self) -> None:
        """Start (or resume) the QUESTION timer for the current question.

        HostScreen should call this after unlocking buzzers.
        - If reset_timer_each_attempt=True: always reset to full timer_seconds.
        - Else: resume from the stored remaining ms (carried across buzz/attempts).
        """
        if self.phase != Phase.SHOW_QUESTION:
            return

        full_ms = int(self.cfg.timer_seconds * 1000)
        if self.cfg.reset_timer_each_attempt:
            self._question_remaining_ms = full_ms
        else:
            # If we have no remaining stored (first unlock), default to full
            if self._question_remaining_ms <= 0:
                self._question_remaining_ms = full_ms

        self.timer.start(self._question_remaining_ms)
# =========================================================================
    # GETTERS
    # =========================================================================

    def current_question(self) -> Question:
        """Get current question"""
        if not self.questions:
            raise IndexError("No questions loaded — load an Excel pack via the Admin Dashboard")
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

    def has_questions(self) -> bool:
        """Return True if questions have been loaded"""
        return len(self.questions) > 0

    
    def get_question_remaining_ms(self) -> int:
        """Remaining milliseconds for the current question timer (used for cascading attempts)."""
        return int(self._question_remaining_ms)

    def get_answer_remaining_ms(self) -> int:
        """Remaining milliseconds for the current answer timer (if any)."""
        return int(self._answer_remaining_ms)

# =========================================================================
    # GAME CONTROL
    # =========================================================================

    def start_question(self) -> None:
        """Start showing current question - timer will start when admin unlocks"""
        if not self.questions:
            self.error_occurred.emit("No questions loaded — load an Excel pack via the Admin Dashboard")
            print("[ENGINE] ⚠️  start_question called with no questions loaded")
            return

        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        self.question_start_time_ms = int(time.time() * 1000)
        self.buzz_unlock_time_ms = 0

        # Reset attempt tracking
        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.attempt_changed.emit(self.current_attempt_number)

        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)

        # Keep timer stopped until admin unlocks
        self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms = 0
        self.timer.stop()
        self.question_changed.emit()

        print(f"[ENGINE] Question started: {self.current_question().text[:50]}...")
        print(f"[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")

    def next_question(self) -> None:
        """
        Move to next question.

        FIX #2: Guard against being called after GAME_END.
        After sliding to next question, engine is in SHOW_QUESTION so admin can UNLOCK.
        Emits question_advanced so HostScreen can do per-question reset.
        """
        # FIX #2: Don't do anything if the game is already over
        if self.phase == Phase.GAME_END:
            return

        # Clear any lock
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        # If all questions are answered -> end game (check BEFORE moving index)
        if len(self.answered_questions) >= len(self.questions):
            self.end_game()
            return

        # Move index
        self.current_q_idx = (self.current_q_idx + 1) % len(self.questions)

        # Prepare next question state (WAITING FOR ADMIN)
        self.question_start_time_ms = int(time.time() * 1000)
        self.buzz_unlock_time_ms = 0

        # Reset attempt tracking for the new question
        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.attempt_changed.emit(self.current_attempt_number)

        # Keep timer stopped until admin unlocks
        self.timer.stop()

        # Put engine in SHOW_QUESTION (not IDLE)
        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)

        # Trigger UI to render the new question
        self.question_changed.emit()

        # Let HostScreen reset UI + MQTT per-question state
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
        self.buzz_unlock_time_ms = 0

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

    def load_questions(self, questions: List[Question]) -> None:
        """
        Hot-swap questions from the Admin Dashboard.
        Resets the game state and loads the new question list.
        Called when admin loads/saves an Excel file.
        """
        if not questions:
            print("[ENGINE] ⚠️  load_questions: empty list — ignoring")
            return

        print(f"[ENGINE] 🔄 Loading {len(questions)} questions from Admin Dashboard")

        # Stop any running timer
        self.timer.stop()

        # Store and shuffle if needed
        self.original_questions = questions[:]
        self.questions = questions[:]
        if self.cfg.shuffle_questions:
            random.shuffle(self.questions)

        # Full game-state reset
        self.scores.reset()
        self.stats = GameStats()
        self.answered_questions.clear()
        self.current_q_idx = 0
        self.locked_buzzer_id = None
        self.current_attempt_number = 0
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.buzz_unlock_time_ms = 0
        self._undo_stack.clear()
        self._redo_stack.clear()

        self.phase = Phase.IDLE
        self.phase_changed.emit(self.phase.value)
        self.lock_changed.emit(None)
        self.scores_changed.emit()
        self.stats_changed.emit()
        self.question_changed.emit()

        print(f"[ENGINE] ✅ Ready — {len(self.questions)} questions loaded, game reset")

    def reload_questions(self, questions: List[Question]) -> None:
        """Alias for load_questions — called from AppWindow after admin loads Excel."""
        self.load_questions(questions)

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

        # FIX #6: measure buzz time from when buzzers were unlocked, not question load
        current_time_ms = int(time.time() * 1000)
        ref_time = self.buzz_unlock_time_ms if self.buzz_unlock_time_ms else self.question_start_time_ms
        buzz_time_ms = current_time_ms - ref_time

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

            # Do NOT auto-advance — admin controls question advancement via NEXT button
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

            print(f"[ENGINE] ✗ Player {pid} wrong (Attempt {self.current_attempt_number})")

            # Cascading attempts logic
            if self.cfg.enable_cascading_attempts and self.current_attempt_number < question.max_attempts:
                remaining_players = self.get_players_remaining()
                if remaining_players:
                    self.current_attempt_number += 1
                    self.attempt_changed.emit(self.current_attempt_number)

                    self.locked_buzzer_id = None
                    self.lock_changed.emit(None)

                    # Do not wipe question remaining time here; HostScreen will restart/resume it on unlock
                    self.timer.stop()

                    self.phase = Phase.SHOW_QUESTION
                    self.phase_changed.emit(self.phase.value)

                    print(f"[ENGINE] → Next attempt available ({self.current_attempt_number}/{question.max_attempts})")
                    print(f"[ENGINE] → Remaining players: {remaining_players}")
                    return

            # FIX #3: All attempts exhausted — delegate to shared helper
            self._on_all_attempts_exhausted()

    # =========================================================================
    # BUZZER INPUT
    # =========================================================================

    def on_buzz(self, buzzer_id: int, t_ms: int, received_ms: int) -> bool:
        """Handle buzz event with cascading attempts support"""
        if self.phase != Phase.SHOW_QUESTION:
            print(f"[ENGINE] ✗ Buzz rejected - wrong phase ({self.phase.value})")
            return False

        if buzzer_id in self.players_attempted:
            self.error_occurred.emit(f"Player {buzzer_id} already attempted this question")
            print(f"[ENGINE] ✗ Player {buzzer_id} already attempted")
            return False

        if self.locked_buzzer_id is not None:
            print(f"[ENGINE] ✗ Buzz rejected - Player {self.locked_buzzer_id} already locked")
            return False

        self.locked_buzzer_id = buzzer_id
        self.lock_changed.emit(buzzer_id)

        self.phase = Phase.BUZZED
        self.phase_changed.emit(self.phase.value)

        # Stop question timer and start answer timer
        # Preserve question remaining time so we can resume it on next attempt if needed
        self._question_remaining_ms = int(self.timer.remaining_ms)
        self.timer.stop()
        # Defensive: never start a 0ms answer timer
        answer_time_ms = max(500, int(self.cfg.answer_seconds * 1000))
        self._answer_remaining_ms = answer_time_ms
        self.timer.start(answer_time_ms)
        print(f"[ENGINE] ✓ Player {buzzer_id} BUZZED IN (Attempt {self.current_attempt_number})")
        print(f"[ENGINE]   Answer timer started: {self.cfg.answer_seconds}s to answer")
        return True

    def notify_buzzers_unlocked(self) -> None:
        """
        Called by HostScreen when the admin clicks 'Unlock Buzzers'.
        Records the unlock timestamp so buzz_time_ms in apply_answer() is
        measured from the moment players could actually buzz, not from when
        the question was loaded.
        """
        self.buzz_unlock_time_ms = int(time.time() * 1000)

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
    # INTERNAL HELPERS
    # =========================================================================

    def _on_all_attempts_exhausted(self) -> None:
        """
        FIX #3: Single shared path for 'no more attempts left'.
        Called from both apply_answer() and _on_timer_ended() to avoid
        duplicating the state-transition logic.
        """
        print("[ENGINE] → No more attempts available")
        self.answered_questions.add(self.current_q_idx)

        # Do NOT auto-advance — admin controls question advancement
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        self.timer.stop()
        self.phase = Phase.IDLE
        self.phase_changed.emit(self.phase.value)

        print("[ENGINE] ⏸️ All attempts exhausted - waiting for admin to advance")

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

            print("[ENGINE] ⏸️ Waiting for admin to advance")

        elif self.phase == Phase.BUZZED:
            # Answer timer expired - player didn't answer in time
            pid = self.locked_buzzer_id
            print(f"[ENGINE] ⏰ Answer time's up! Player {pid} didn't answer in time.")

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

                # FIX #3: Use shared helper instead of duplicating logic
                self._on_all_attempts_exhausted()