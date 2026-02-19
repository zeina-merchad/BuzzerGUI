import random
import time
from typing import List, Optional, Set
from collections import deque

from PySide6.QtCore import QObject, Signal

from app.core.state import Phase
from app.core.models import GameConfig, Question, Scoreboard, GameStats, AttemptRecord


class CountdownTimer(QObject):
    changed = Signal(int)   # remaining_ms
    ended = Signal()

    def __init__(self, tick_ms: int = 100):
        super().__init__()
        from PySide6.QtCore import QTimer
        self._tick_ms = int(tick_ms)
        self._remaining_ms = 0
        self._timer = QTimer()
        self._timer.setInterval(self._tick_ms)
        self._timer.timeout.connect(self._on_tick)

    @property
    def remaining_ms(self) -> int:
        return self._remaining_ms

    def start(self, total_ms: int) -> None:
        self._timer.stop()          # FIX: always stop before re-starting
        self._remaining_ms = max(0, int(total_ms))
        self.changed.emit(self._remaining_ms)
        self._timer.start()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if self._remaining_ms > 0:
            self._timer.start()

    def stop(self) -> None:
        """Stop the timer and reset remaining time.

        FIX: does NOT emit changed(0) — the widget stays on the last displayed
        second rather than flashing '00s' every time a player buzzes in.
        """
        self._timer.stop()
        self._remaining_ms = 0

    def _on_tick(self) -> None:
        self._remaining_ms -= self._tick_ms
        if self._remaining_ms <= 0:
            self._remaining_ms = 0
            self._timer.stop()
            self.changed.emit(self._remaining_ms)
            self.ended.emit()
        else:
            self.changed.emit(self._remaining_ms)


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
        # Track when buzzers were actually unlocked so speed bonus is meaningful
        self.buzz_unlock_time_ms: int = 0

        # Timer bookkeeping (so we can resume question time after buzz/attempts)
        self._question_remaining_ms: int = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms: int = 0

        # Cascading attempts tracking
        self.current_attempt_number: int = 0
        self.players_attempted: Set[int] = set()
        self.attempt_records: List[AttemptRecord] = []

        # Scoreboard — initialised with only the active player set.
        # FIX #7 (review): hardcoding {1:0,2:0,3:0,4:0} meant get_players_remaining()
        # always returned up to 4 players regardless of how many buzzers are connected.
        # active_player_ids is now populated lazily as players connect.
        self.scores = Scoreboard(scores={1: 0, 2: 0, 3: 0, 4: 0})

        # Statistics
        self.stats = GameStats()

        # Undo/Redo stacks
        self._undo_stack: deque = deque(maxlen=50)
        self._redo_stack: deque = deque(maxlen=50)

        # Timer — inline so this file is self-contained
        self.timer = CountdownTimer(tick_ms=100)
        self.timer.changed.connect(self._on_timer_changed)
        self.timer.ended.connect(self._on_timer_ended)

        # Track answered questions
        self.answered_questions: set[int] = set()

        # FIX: track which players are actually active in this game session.
        # Populated by register_active_player() as buzzers connect.
        # Defaults to all four so the engine works correctly when no connection
        # tracking is in use (e.g. tests, demo mode without MQTT).
        self._active_player_ids: Set[int] = {1, 2, 3, 4}

    # =========================================================================
    # ACTIVE PLAYER MANAGEMENT
    # =========================================================================

    def register_active_player(self, player_id: int) -> None:
        """Mark a player as active (connected buzzer).  Call when a buzzer
        connects so cascading attempt logic only iterates real players.
        """
        self._active_player_ids.add(int(player_id))

    def unregister_active_player(self, player_id: int) -> None:
        """Mark a player as no longer active.  Safe to call even if the
        player is not in the set.
        """
        self._active_player_ids.discard(int(player_id))

    def set_active_players(self, player_ids) -> None:
        """Bulk-replace the active player set (e.g. from heartbeat results)."""
        self._active_player_ids = set(int(p) for p in player_ids)

    # =========================================================================
    # TIMER BOOKKEEPING
    # =========================================================================

    def _on_timer_changed(self, remaining_ms: int) -> None:
        """Internal timer tick handler."""
        if self.phase == Phase.SHOW_QUESTION:
            self._question_remaining_ms = int(remaining_ms)
        elif self.phase == Phase.BUZZED:
            self._answer_remaining_ms = int(remaining_ms)

        # Always forward to UI
        self.timer_changed.emit(int(remaining_ms))

    def start_or_resume_question_timer(self) -> None:
        """Start (or resume) the QUESTION timer for the current question."""
        if self.phase != Phase.SHOW_QUESTION:
            return

        full_ms = int(self.cfg.timer_seconds * 1000)
        if self.cfg.reset_timer_each_attempt:
            self._question_remaining_ms = full_ms
        else:
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
        """Get list of active players who haven't attempted yet.

        FIX #7 (review): was hardcoded to {1,2,3,4}.  Now uses
        self._active_player_ids so a 2-player game does not cascade through
        phantom players 3 and 4.  Defaults to all four if no players have
        been explicitly registered (backwards-compatible with tests/demo).
        """
        base = self._active_player_ids if self._active_player_ids else {1, 2, 3, 4}
        return sorted(list(base - self.players_attempted))

    def get_points_for_current_attempt(self) -> int:
        """Get points available for current attempt"""
        question = self.current_question()
        return question.get_points_for_attempt(self.current_attempt_number)

    def has_questions(self) -> bool:
        """Return True if questions have been loaded"""
        return len(self.questions) > 0

    def get_question_remaining_ms(self) -> int:
        """Remaining milliseconds for the current question timer."""
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
        print("[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")

    def prev_question(self) -> None:
        """Step back to the previous question (host correction / remote shortcut)."""
        if self.current_q_idx < 1:
            print("[ENGINE] ⚠️  Already at the first question — cannot go back")
            return

        # Stop any running timer
        self.timer.stop()

        # Remove current question from answered set (it wasn't completed)
        self.answered_questions.discard(self.current_q_idx)

        # Step back
        self.current_q_idx -= 1

        # Also unmark the previous question so it can be re-attempted fresh
        self.answered_questions.discard(self.current_q_idx)

        # Reset all per-question state
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.attempt_changed.emit(self.current_attempt_number)
        self.buzz_unlock_time_ms = 0
        self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms = 0

        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)
        self.question_changed.emit()
        self.question_advanced.emit()

        print(f"[ENGINE] ⏮ Went back to Q{self.current_q_idx + 1}")
        print("[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")
        
    def next_question(self) -> None:
        """Move to next question."""
        if self.phase == Phase.GAME_END:
            return

        # Always mark the current question answered before moving on
        self.answered_questions.add(self.current_q_idx)

        # Clear any lock
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        # If all questions are answered → end game
        if len(self.answered_questions) >= len(self.questions):
            self.end_game()
            return

        # Advance linearly — never wrap
        next_idx = self.current_q_idx + 1
        if next_idx >= len(self.questions):
            self.end_game()
            return

        self.current_q_idx = next_idx

        # Prepare next question state (WAITING FOR ADMIN)
        self.question_start_time_ms = int(time.time() * 1000)
        self.buzz_unlock_time_ms = 0

        # Reset attempt tracking for the new question
        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.attempt_changed.emit(self.current_attempt_number)

        # Reset timer bookkeeping; timer stays stopped until admin unlocks
        self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms = 0
        self.timer.stop()

        # Put engine in SHOW_QUESTION (not IDLE)
        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)

        # Trigger UI to render the new question
        self.question_changed.emit()

        # Let HostScreen reset UI + MQTT per-question state
        self.question_advanced.emit()

        print(f"[ENGINE] Next question ready: Q{self.current_q_idx + 1}")
        print("[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")

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

    def update_config(self, new_config: GameConfig) -> None:
        """Apply a new GameConfig from the Admin Dashboard Settings tab."""
        old_cfg = self.cfg
        self.cfg = new_config

        if self.phase == Phase.SHOW_QUESTION:
            self._question_remaining_ms = int(new_config.timer_seconds * 1000)

        changes = []
        if old_cfg.timer_seconds != new_config.timer_seconds:
            changes.append(f"timer {old_cfg.timer_seconds}s→{new_config.timer_seconds}s")
        if old_cfg.answer_seconds != new_config.answer_seconds:
            changes.append(f"answer_time {old_cfg.answer_seconds}s→{new_config.answer_seconds}s")
        if old_cfg.penalty_for_wrong != new_config.penalty_for_wrong:
            changes.append(f"penalty {old_cfg.penalty_for_wrong}→{new_config.penalty_for_wrong}")
        if old_cfg.enable_cascading_attempts != new_config.enable_cascading_attempts:
            changes.append(f"cascading {old_cfg.enable_cascading_attempts}→{new_config.enable_cascading_attempts}")
        if old_cfg.bonus_for_speed != new_config.bonus_for_speed:
            changes.append(f"speed_bonus {old_cfg.bonus_for_speed}→{new_config.bonus_for_speed}")
        if old_cfg.rounds != new_config.rounds:
            changes.append(f"rounds {old_cfg.rounds}→{new_config.rounds}")

        change_str = ", ".join(changes) if changes else "no functional changes"
        print(f"[ENGINE] Config updated: '{new_config.name}' ({change_str})")

    def load_questions(self, questions: List[Question]) -> None:
        """Hot-swap questions from the Admin Dashboard."""
        if not questions:
            print("[ENGINE] ⚠️  load_questions: empty list — ignoring")
            return

        print(f"[ENGINE] 🔄 Loading {len(questions)} questions from Admin Dashboard")

        self.timer.stop()

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
        self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms = 0
        self._undo_stack.clear()
        self._redo_stack.clear()

        self.phase = Phase.IDLE
        self.phase_changed.emit(self.phase.value)
        self.lock_changed.emit(None)
        self.scores_changed.emit()
        self.stats_changed.emit()
        self.question_changed.emit()

        print(f"[ENGINE] ✅ Ready — {len(self.questions)} questions loaded, game reset")

    def award_bonus(self, player_id: int, points: int = 1, reason: str = "Bonus point") -> None:
        """Award a manual bonus point to a player (admin-only action)."""
        if player_id not in self.scores.scores:
            print(f"[ENGINE] ⚠️  award_bonus: unknown player_id {player_id}")
            return

        self._save_state_for_undo(
            player_id=player_id,
            points=points,
            is_correct=True,
            question_idx=self.current_q_idx,
        )

        self.scores.add(player_id, points, reason)
        self.scores_changed.emit()

        print(f"[ENGINE] ⭐ Bonus +{points} awarded to Player {player_id} ({reason})")

    def reload_questions(self, questions: List[Question]) -> None:
        """Alias for load_questions — called from AppWindow after admin loads Excel."""
        self.load_questions(questions)

    # =========================================================================
    # ANSWER HANDLING WITH CASCADING ATTEMPTS
    # =========================================================================

    def apply_answer(self, is_correct: bool, answering_player_id: Optional[int] = None) -> None:
        """Apply answer judgement with cascading attempts support."""
        if self.locked_buzzer_id is None:
            self.error_occurred.emit("No player has buzzed in")
            return

        if answering_player_id is not None and answering_player_id != self.locked_buzzer_id:
            print(
                f"[ENGINE] 🚫 Ignored answer from Player {answering_player_id} "
                f"(locked player is {self.locked_buzzer_id})"
            )
            return

        pid = self.locked_buzzer_id
        question = self.current_question()

        current_time_ms = int(time.time() * 1000)
        ref_time = self.buzz_unlock_time_ms if self.buzz_unlock_time_ms else self.question_start_time_ms
        buzz_time_ms = current_time_ms - ref_time

        points_for_attempt = question.get_points_for_attempt(self.current_attempt_number)

        if is_correct:
            points = points_for_attempt

            if self.cfg.bonus_for_speed and self.current_attempt_number == 1 and buzz_time_ms < 3000:
                points += 1

            reason = f"Correct on attempt {self.current_attempt_number} - Q{self.current_q_idx + 1}"

            self._save_state_for_undo(pid, points, is_correct, self.current_q_idx)
            self.scores.add(pid, points, reason)
            self.scores_changed.emit()

            self.stats.record_answer(True, pid, buzz_time_ms, self.current_attempt_number)
            self.stats_changed.emit()

            self.attempt_records.append(AttemptRecord(
                player_id=pid,
                is_correct=True,
                points_awarded=points,
                attempt_number=self.current_attempt_number,
                buzz_time_ms=buzz_time_ms
            ))

            self.answered_questions.add(self.current_q_idx)

            print(f"[ENGINE] ✓ Player {pid} correct! +{points} pts (Attempt {self.current_attempt_number})")

            self.locked_buzzer_id = None
            self.lock_changed.emit(None)
            self.timer.stop()
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)

            print("[ENGINE] ⏸️ Question complete - waiting for admin to advance")
            return

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

        self.players_attempted.add(pid)
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

                self.timer.stop()

                self.phase = Phase.SHOW_QUESTION
                self.phase_changed.emit(self.phase.value)

                print(f"[ENGINE] → Next attempt available ({self.current_attempt_number}/{question.max_attempts})")
                print(f"[ENGINE] → Remaining players: {remaining_players}")
                return

        # All attempts exhausted
        self._on_all_attempts_exhausted()

    # =========================================================================
    # BUZZER INPUT
    # =========================================================================

    def on_buzz(self, buzzer_id: int, t_ms: int, received_ms: int) -> bool:
        """Handle buzz event with cascading attempts support."""
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

        self._question_remaining_ms = int(self.timer.remaining_ms)
        self.timer.stop()

        answer_time_ms = max(500, int(self.cfg.answer_seconds * 1000))
        self._answer_remaining_ms = answer_time_ms
        self.timer.start(answer_time_ms)

        print(f"[ENGINE] ✓ Player {buzzer_id} BUZZED IN (Attempt {self.current_attempt_number})")
        print(f"[ENGINE]   Answer timer started: {self.cfg.answer_seconds}s")
        return True

    def notify_buzzers_unlocked(self) -> None:
        """Called by HostScreen when the admin clicks 'Unlock Buzzers'."""
        self.buzz_unlock_time_ms = int(time.time() * 1000)

    # =========================================================================
    # UNDO / REDO
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

    def undo_last_answer(self) -> bool:
        """Revert the last scored answer. Returns True if successful."""
        if not self._undo_stack:
            return False
        state = self._undo_stack.pop()
        self._redo_stack.append(state)

        for pid, score in state['scores_snapshot'].items():
            self.scores.scores[pid] = score

        self.answered_questions.discard(state['question_idx'])

        self.scores_changed.emit()
        print(f"[ENGINE] ↩ Undid answer for Player {state['player_id']} "
              f"(Q{state['question_idx'] + 1}, {state['points']} pts)")
        return True

    def redo_last_answer(self) -> bool:
        """Re-apply the last undone answer. Returns True if successful."""
        if not self._redo_stack:
            return False
        state = self._redo_stack.pop()
        self._undo_stack.append(state)

        self.scores.add(state['player_id'], state['points'],
                        f"Redo - Q{state['question_idx'] + 1}")
        self.answered_questions.add(state['question_idx'])

        self.scores_changed.emit()
        print(f"[ENGINE] ↪ Redid answer for Player {state['player_id']} "
              f"(Q{state['question_idx'] + 1}, +{state['points']} pts)")
        return True

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _on_all_attempts_exhausted(self) -> None:
        """Single shared path for 'no more attempts left'."""
        print("[ENGINE] → No more attempts available")
        self.answered_questions.add(self.current_q_idx)

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
            self.answered_questions.add(self.current_q_idx)
            print("[ENGINE] ⏰ Question time's up! No one buzzed.")

            self.locked_buzzer_id = None
            self.lock_changed.emit(None)
            self.timer.stop()
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)

            print("[ENGINE] ⏸️ Waiting for admin to advance")

        elif self.phase == Phase.BUZZED:
            pid = self.locked_buzzer_id
            print(f"[ENGINE] ⏰ Answer time's up! Player {pid} didn't answer in time.")

            if pid:
                if self.cfg.penalty_for_wrong > 0:
                    penalty = -self.cfg.penalty_for_wrong
                    reason = f"Timeout - Q{self.current_q_idx + 1}"
                    self.scores.add(pid, penalty, reason)
                    self.scores_changed.emit()

                self.players_attempted.add(pid)
                self.attempt_failed.emit(pid, self.current_attempt_number)

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

                self._on_all_attempts_exhausted()

    