import random
import time
from collections import deque
from typing import List, Optional, Set

from PySide6.QtCore import QObject, Signal

from app.core.models import AttemptRecord, GameConfig, GameStats, Question, Scoreboard
from app.core.state import Phase


class CountdownTimer(QObject):
    changed = Signal(int)  # remaining_ms
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
        self._timer.stop()
        self._remaining_ms = max(0, int(total_ms))
        self.changed.emit(self._remaining_ms)
        self._timer.start()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if self._remaining_ms > 0:
            self._timer.start()

    def stop(self) -> None:
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
    """Game engine with cascading attempts - External MQTT backend.

    Active player model
    -------------------
    Players are registered once at game-start via register_game_players().
    Any buzzer that fires during the game is automatically added to the active
    set (self._active_player_ids) so late-joining hardware still participates.
    There is no heartbeat, timeout, or disconnect tracking — once a player is
    part of the active set for the current game they stay there for the whole
    game.  The only way a player leaves the active set is an explicit call to
    remove_player() (e.g. from a host-initiated kick), which is not exposed in
    the current UI but left as a hook for future use.
    """

    phase_changed = Signal(str)
    question_changed = Signal()
    timer_changed = Signal(int)  # remaining_ms
    lock_changed = Signal(object)  # locked_buzzer_id or None
    scores_changed = Signal()
    stats_changed = Signal()
    error_occurred = Signal(str)

    attempt_changed = Signal(int)  # current_attempt_number (1-4)
    attempt_failed = Signal(int, int)  # (player_id, attempt_number)
    # Fired when the question timer expires with nobody buzzed in;
    # carries the new attempt number so the host can re-unlock buzzers.
    nobody_buzzed = Signal(int)

    question_advanced = Signal()

    def __init__(self, cfg: GameConfig, questions: List[Question]):
        super().__init__()

        if questions:
            valid, error = cfg.validate()
            if not valid:
                raise ValueError(f"Invalid configuration: {error}")

        self.cfg = cfg
        self.original_questions = [q for q in questions if getattr(q, "enabled", True)]
        self.questions = self.original_questions[:]

        if cfg.shuffle_questions and self.questions:
            random.shuffle(self.questions)

        self.phase: Phase = Phase.IDLE
        self.current_q_idx: int = 0
        self.locked_buzzer_id: Optional[int] = None
        self.question_start_time_ms: int = 0
        self.buzz_unlock_time_ms: int = 0

        self._question_remaining_ms: int = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms: int = 0

        self.current_attempt_number: int = 0
        self.players_attempted: Set[int] = set()
        self.attempt_records: List[AttemptRecord] = []

        self.scores = Scoreboard(scores={1: 0, 2: 0, 3: 0, 4: 0})
        self.stats = GameStats()

        self._undo_stack: deque = deque(maxlen=50)
        self._redo_stack: deque = deque(maxlen=50)

        self.question_timer = CountdownTimer(tick_ms=100)
        self.answer_timer = CountdownTimer(tick_ms=100)

        self.question_timer.changed.connect(self._on_question_timer_changed)
        self.question_timer.ended.connect(self._on_question_timer_ended)
        self.answer_timer.changed.connect(self._on_answer_timer_changed)
        self.answer_timer.ended.connect(self._on_answer_timer_ended)

        self.answered_questions: set[int] = set()

        # Active players: populated by register_game_players() at game start.
        # Any subsequent buzz from an unknown player auto-adds them (see on_buzz).
        # Empty set means all buzzes are accepted (pre-game / no-MQTT fallback).
        self._active_player_ids: Set[int] = set()

    # =========================================================================
    # ACTIVE PLAYER MANAGEMENT
    # =========================================================================

    def register_game_players(self, player_ids) -> None:
        """Freeze the set of active players for this game.

        Called once when the game starts, with the list of buzzer IDs that are
        currently connected.  Any player that buzzes in later (even if they
        weren't in the original list) is auto-added in on_buzz() so late
        hardware still participates.
        """
        self._active_player_ids = set(int(p) for p in player_ids)
        print(f"[ENGINE] Game players registered: {sorted(self._active_player_ids)}")

    def add_active_player(self, player_id: int) -> None:
        """Add a single player to the active set (e.g. on first buzz)."""
        pid = int(player_id)
        if pid not in self._active_player_ids:
            self._active_player_ids.add(pid)
            print(f"[ENGINE] Player {pid} auto-added to active set on first buzz")

    def remove_player(self, player_id: int) -> None:
        """Explicitly remove a player from the active set (host kick).

        Not currently called from the UI but provided as a hook.
        """
        pid = int(player_id)
        self._active_player_ids.discard(pid)
        print(f"[ENGINE] Player {pid} removed from active set")

    def start_or_resume_question_timer(self) -> None:
        if self.phase != Phase.SHOW_QUESTION:
            return

        full_ms = int(self.cfg.timer_seconds * 1000)

        if self.cfg.reset_timer_each_attempt:
            self._question_remaining_ms = full_ms
        elif self._question_remaining_ms <= 0:
            self._question_remaining_ms = full_ms

        self.answer_timer.stop()
        self.question_timer.start(self._question_remaining_ms)

    def _stop_all_timers(self) -> None:
        self.question_timer.stop()
        self.answer_timer.stop()

    def on_buzz(self, buzzer_id: int, t_ms: int, received_ms: int) -> bool:
        if self.phase != Phase.SHOW_QUESTION:
            print(f"[ENGINE] ✗ Buzz rejected - wrong phase ({self.phase.value})")
            return False

        # Auto-register any buzzing player so late hardware still participates.
        # If the active set is empty (no-MQTT / pre-game), all players are allowed.
        if self._active_player_ids:
            self.add_active_player(buzzer_id)
        # (if set is empty, skip the check — open floor)

        if buzzer_id in self.players_attempted:
            self.error_occurred.emit(
                f"Player {buzzer_id} already attempted this question"
            )
            print(f"[ENGINE] ✗ Player {buzzer_id} already attempted")
            return False

        if self.locked_buzzer_id is not None:
            print(
                f"[ENGINE] ✗ Buzz rejected - Player {self.locked_buzzer_id} already locked"
            )
            return False

        if self.question_timer.remaining_ms <= 0 and self._question_remaining_ms <= 0:
            print(f"[ENGINE] ✗ Buzz rejected - question timer already expired")
            return False

        self.locked_buzzer_id = buzzer_id
        self.lock_changed.emit(buzzer_id)

        self.phase = Phase.BUZZED
        self.phase_changed.emit(self.phase.value)

        remaining = int(self.question_timer.remaining_ms)
        if remaining > 0:
            self._question_remaining_ms = remaining
        self.question_timer.stop()

        answer_time_ms = max(500, int(self.cfg.answer_seconds * 1000))
        self._answer_remaining_ms = answer_time_ms
        self.answer_timer.start(answer_time_ms)

        print(
            f"[ENGINE] ✓ Player {buzzer_id} BUZZED IN (Attempt {self.current_attempt_number})"
        )
        print(f"[ENGINE]   Answer timer started: {self.cfg.answer_seconds}s")
        return True

    # =========================================================================
    # TIMER BOOKKEEPING
    # =========================================================================

    def _on_question_timer_changed(self, remaining_ms: int) -> None:
        self._question_remaining_ms = int(remaining_ms)
        if self.phase == Phase.SHOW_QUESTION:
            self.timer_changed.emit(int(remaining_ms))

    def _on_answer_timer_changed(self, remaining_ms: int) -> None:
        self._answer_remaining_ms = int(remaining_ms)
        if self.phase == Phase.BUZZED:
            self.timer_changed.emit(int(remaining_ms))

    def _on_question_timer_ended(self) -> None:
        if self.phase != Phase.SHOW_QUESTION:
            return

        print("[ENGINE] ⏰ Question timer expired — nobody buzzed")

        question = self.current_question()
        remaining_players = self.get_players_remaining()
        max_attempts = max(1, int(getattr(question, "max_attempts", 1)))

        if not remaining_players:
            self._on_all_attempts_exhausted()
            return

        if (
            self.cfg.enable_cascading_attempts
            and self.current_attempt_number < max_attempts
        ):
            self.current_attempt_number += 1
            self.attempt_changed.emit(self.current_attempt_number)

            self.locked_buzzer_id = None
            self.lock_changed.emit(None)

            # FIX: respect reset_timer_each_attempt (was always resetting before)
            if self.cfg.reset_timer_each_attempt or self._question_remaining_ms <= 0:
                self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)

            self.phase = Phase.SHOW_QUESTION
            self.phase_changed.emit(self.phase.value)

            self.question_timer.start(self._question_remaining_ms)
            self.timer_changed.emit(self._question_remaining_ms)

            # Dedicated signal so host_screen can re-unlock buzzers cleanly.
            # The host must NOT restart the timer — the engine already did.
            self.nobody_buzzed.emit(self.current_attempt_number)

            print(
                f"[ENGINE] Nobody buzzed — attempt {self.current_attempt_number}, timer restarted"
            )
            return

        self._on_all_attempts_exhausted()

    def _on_answer_timer_ended(self) -> None:
        """Answer countdown reached zero — treat as a wrong answer / timeout."""
        if self.phase != Phase.BUZZED:
            return

        print("[ENGINE] ⏰ Answer timer expired")

        if self.locked_buzzer_id is None:
            self._on_all_attempts_exhausted()
            return

        pid = self.locked_buzzer_id
        self.players_attempted.add(pid)
        self.stats.record_answer(
            False, pid, self.cfg.answer_seconds * 1000, self.current_attempt_number
        )
        self.stats_changed.emit()
        # Emit attempt_failed so the UI marks the player eliminated.
        # The host_screen handler must check _answer_timed_out to skip its own
        # MQTT/SFX calls — those are handled by _on_nobody_buzzed below.
        self._answer_timed_out = True
        try:
            self.attempt_failed.emit(pid, self.current_attempt_number)
        finally:
            self._answer_timed_out = False

        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        self.answer_timer.stop()
        self._answer_remaining_ms = 0

        question = self.current_question()
        remaining_players = self.get_players_remaining()
        max_attempts = max(1, int(getattr(question, "max_attempts", 1)))

        print(
            f"[ENGINE] Timeout cascading check: enabled={self.cfg.enable_cascading_attempts}, "
            f"attempt={self.current_attempt_number}, max_attempts={max_attempts}, "
            f"remaining_players={remaining_players}"
        )

        if (
            self.cfg.enable_cascading_attempts
            and self.current_attempt_number < max_attempts
            and remaining_players
        ):
            self.current_attempt_number += 1
            self.attempt_changed.emit(self.current_attempt_number)

            if self.cfg.reset_timer_each_attempt or self._question_remaining_ms <= 0:
                self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)

            self.phase = Phase.SHOW_QUESTION
            self.phase_changed.emit(self.phase.value)

            self.question_timer.start(self._question_remaining_ms)
            self.timer_changed.emit(self._question_remaining_ms)

            # Re-use nobody_buzzed to tell host_screen to unlock buzzers.
            # The timer has already been started above; host must NOT restart it.
            self.nobody_buzzed.emit(self.current_attempt_number)

            print(
                f"[ENGINE] Answer timeout on P{pid}; continuing with players {remaining_players}"
            )
            return

        self._on_all_attempts_exhausted()

    def _on_all_attempts_exhausted(self) -> None:
        """Handle end of question when no more valid attempts remain."""
        print("[ENGINE] No more attempts available for this question")

        self._stop_all_timers()

        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        self._question_remaining_ms = 0
        self._answer_remaining_ms = 0

        self.phase = Phase.IDLE
        self.phase_changed.emit(self.phase.value)

        self.answered_questions.add(self.current_q_idx)

        print("[ENGINE] ⏸️ Attempts exhausted - waiting for admin to advance")

    # =========================================================================
    # GETTERS
    # =========================================================================

    def current_question(self) -> Question:
        if not self.questions:
            raise IndexError(
                "No questions loaded — load an Excel pack via the Admin Dashboard"
            )
        return self.questions[self.current_q_idx]

    def get_progress(self) -> tuple[int, int]:
        return (self.current_q_idx + 1, len(self.questions))

    def get_remaining_questions(self) -> int:
        return len(self.questions) - len(self.answered_questions)

    def get_current_attempt_number(self) -> int:
        return self.current_attempt_number

    def get_players_remaining(self) -> List[int]:
        """Return active players who haven't attempted this question yet."""
        if not self._active_player_ids:
            # No players registered yet (pre-game / no MQTT) — nobody is
            # "remaining" in the cascading sense so return empty.
            return []
        return sorted(list(self._active_player_ids - self.players_attempted))

    def get_points_for_current_attempt(self) -> int:
        question = self.current_question()
        return question.get_points_for_attempt(self.current_attempt_number)

    def has_questions(self) -> bool:
        return len(self.questions) > 0

    def get_question_remaining_ms(self) -> int:
        return int(self._question_remaining_ms)

    def get_answer_remaining_ms(self) -> int:
        return int(self._answer_remaining_ms)

    # =========================================================================
    # GAME CONTROL
    # =========================================================================

    def start_question(self) -> None:
        if not self.questions:
            self.error_occurred.emit(
                "No questions loaded — load an Excel pack via the Admin Dashboard"
            )
            print("[ENGINE] ⚠️ start_question called with no questions loaded")
            return

        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        self.question_start_time_ms = int(time.time() * 1000)
        self.buzz_unlock_time_ms = 0

        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.answered_questions.discard(self.current_q_idx)
        self.attempt_changed.emit(self.current_attempt_number)

        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)

        self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms = 0
        self._stop_all_timers()
        self.question_changed.emit()
        self.question_advanced.emit()

        print(f"[ENGINE] Question started: {self.current_question().text[:50]}...")
        print("[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")

    def prev_question(self) -> None:
        if self.current_q_idx < 1:
            print("[ENGINE] ⚠️ Already at the first question — cannot go back")
            return

        self._stop_all_timers()
        self.current_q_idx -= 1
        self.answered_questions.discard(self.current_q_idx)

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
        if self.phase == Phase.GAME_END:
            return

        self.answered_questions.add(self.current_q_idx)

        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        next_idx = self.current_q_idx + 1
        if next_idx >= len(self.questions):
            self.end_game()
            return

        self.current_q_idx = next_idx

        self.question_start_time_ms = int(time.time() * 1000)
        self.buzz_unlock_time_ms = 0

        self.current_attempt_number = 1
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.attempt_changed.emit(self.current_attempt_number)

        self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)
        self._answer_remaining_ms = 0
        self._stop_all_timers()

        self.phase = Phase.SHOW_QUESTION
        self.phase_changed.emit(self.phase.value)
        self.question_changed.emit()
        self.question_advanced.emit()

        print(f"[ENGINE] Next question ready: Q{self.current_q_idx + 1}")
        print("[ENGINE] ⏸️ Timer paused - waiting for admin to unlock")

    def skip_question(self) -> None:
        self.next_question()

    def reset_game(self) -> None:
        self.scores.reset()
        self.stats = GameStats()
        self.answered_questions.clear()
        self.current_q_idx = 0

        self.locked_buzzer_id = None
        self.lock_changed.emit(None)

        self.phase = Phase.IDLE
        self.current_attempt_number = 0
        self.players_attempted.clear()
        self.attempt_records.clear()
        self.buzz_unlock_time_ms = 0
        self._active_player_ids = (
            set()
        )  # cleared; re-populated by register_game_players

        if self.cfg.shuffle_questions:
            self.questions = self.original_questions[:]
            random.shuffle(self.questions)

        self._undo_stack.clear()
        self._redo_stack.clear()

        self._stop_all_timers()

        self.phase_changed.emit(self.phase.value)
        self.scores_changed.emit()
        self.stats_changed.emit()
        self.question_changed.emit()

        print("[ENGINE] Game reset - all locks released, active players cleared")

    def end_game(self) -> None:
        self.phase = Phase.GAME_END
        self.phase_changed.emit(self.phase.value)
        self._stop_all_timers()
        print("[ENGINE] Game ended")

    def update_config(self, new_config: GameConfig) -> None:
        old_cfg = self.cfg
        self.cfg = new_config

        if self.phase == Phase.SHOW_QUESTION and self.buzz_unlock_time_ms == 0:
            self._question_remaining_ms = int(new_config.timer_seconds * 1000)

        changes = []
        if old_cfg.timer_seconds != new_config.timer_seconds:
            changes.append(
                f"timer {old_cfg.timer_seconds}s→{new_config.timer_seconds}s"
            )
        if old_cfg.answer_seconds != new_config.answer_seconds:
            changes.append(
                f"answer_time {old_cfg.answer_seconds}s→{new_config.answer_seconds}s"
            )
        if old_cfg.penalty_for_wrong != new_config.penalty_for_wrong:
            changes.append(
                f"penalty {old_cfg.penalty_for_wrong}→{new_config.penalty_for_wrong}"
            )
        if old_cfg.enable_cascading_attempts != new_config.enable_cascading_attempts:
            changes.append(
                f"cascading {old_cfg.enable_cascading_attempts}→{new_config.enable_cascading_attempts}"
            )
        if old_cfg.bonus_for_speed != new_config.bonus_for_speed:
            changes.append(
                f"speed_bonus {old_cfg.bonus_for_speed}→{new_config.bonus_for_speed}"
            )
        if old_cfg.rounds != new_config.rounds:
            changes.append(f"rounds {old_cfg.rounds}→{new_config.rounds}")

        change_str = ", ".join(changes) if changes else "no functional changes"
        print(f"[ENGINE] Config updated: '{new_config.name}' ({change_str})")

    def load_questions(self, questions: List[Question]) -> None:
        if not questions:
            print(
                "[ENGINE] ⚠️ load_questions: empty list — resetting engine to IDLE (no questions)"
            )
            self._stop_all_timers()
            self.original_questions = []
            self.questions = []
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
            self._active_player_ids = set()
            self._undo_stack.clear()
            self._redo_stack.clear()
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)
            self.lock_changed.emit(None)
            self.scores_changed.emit()
            self.stats_changed.emit()
            self.question_changed.emit()
            return

        print(f"[ENGINE] 🔄 Loading {len(questions)} questions from Admin Dashboard")

        self._stop_all_timers()

        self.original_questions = questions[:]
        self.questions = questions[:]
        if self.cfg.shuffle_questions:
            random.shuffle(self.questions)

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
        self._active_player_ids = set()
        self._undo_stack.clear()
        self._redo_stack.clear()

        self.phase = Phase.IDLE
        self.phase_changed.emit(self.phase.value)
        self.lock_changed.emit(None)
        self.scores_changed.emit()
        self.stats_changed.emit()
        self.question_changed.emit()

        print(f"[ENGINE] ✅ Ready — {len(self.questions)} questions loaded, game reset")

    def award_bonus(
        self, player_id: int, points: int = 1, reason: str = "Bonus point"
    ) -> None:
        if player_id not in self.scores.scores:
            print(f"[ENGINE] ⚠️ award_bonus: unknown player_id {player_id}")
            return

        self._save_state_for_undo(
            player_id=player_id,
            points=points,
            is_correct=True,
            question_idx=self.current_q_idx,
        )

        self.scores.add(player_id, points, reason)
        self._finalise_undo_state()
        self.scores_changed.emit()

        print(f"[ENGINE] ⭐ Bonus +{points} awarded to Player {player_id} ({reason})")

    def reload_questions(self, questions: List[Question]) -> None:
        self.load_questions(questions)

    # =========================================================================
    # STATE SNAPSHOTS / RESTORE
    # =========================================================================

    def get_state_snapshot(self) -> dict:
        return {
            "scores": self.scores.scores.copy(),
            "score_history": list(self.scores.history),
            "answered_questions": set(self.answered_questions),
            "current_q_idx": self.current_q_idx,
            "phase": self.phase.value,
            "locked_buzzer_id": self.locked_buzzer_id,
            "current_attempt_number": self.current_attempt_number,
            "players_attempted": set(self.players_attempted),
            "attempt_records": [AttemptRecord(**vars(r)) for r in self.attempt_records],
            "question_remaining_ms": int(self._question_remaining_ms),
            "answer_remaining_ms": int(self._answer_remaining_ms),
            "active_player_ids": set(self._active_player_ids),
            "stats": {
                "questions_answered": self.stats.questions_answered,
                "correct_answers": self.stats.correct_answers,
                "wrong_answers": self.stats.wrong_answers,
                "total_buzz_time_ms": self.stats.total_buzz_time_ms,
                "fastest_buzz_ms": self.stats.fastest_buzz_ms,
                "player_buzz_counts": dict(self.stats.player_buzz_counts),
                "questions_by_attempt": dict(self.stats.questions_by_attempt),
                "total_attempts": self.stats.total_attempts,
            },
        }

    def _restore_state_snapshot(self, snapshot: dict) -> None:
        self._stop_all_timers()
        self.scores.scores = snapshot["scores"].copy()
        self.scores.history = list(snapshot.get("score_history", []))
        self.answered_questions = set(snapshot["answered_questions"])
        self.current_q_idx = int(snapshot["current_q_idx"])
        self.phase = Phase.from_value(snapshot["phase"])
        self.locked_buzzer_id = snapshot["locked_buzzer_id"]
        self.current_attempt_number = int(snapshot["current_attempt_number"])
        self.players_attempted = set(snapshot["players_attempted"])
        self.attempt_records = [
            AttemptRecord(**vars(r))
            if isinstance(r, AttemptRecord)
            else AttemptRecord(**r)
            for r in snapshot.get("attempt_records", [])
        ]
        self._question_remaining_ms = int(
            snapshot.get("question_remaining_ms", int(self.cfg.timer_seconds * 1000))
        )
        self._answer_remaining_ms = int(snapshot.get("answer_remaining_ms", 0))
        self._active_player_ids = set(snapshot.get("active_player_ids", set()))

        stats_data = snapshot.get("stats", {})
        self.stats = GameStats(
            questions_answered=int(stats_data.get("questions_answered", 0)),
            correct_answers=int(stats_data.get("correct_answers", 0)),
            wrong_answers=int(stats_data.get("wrong_answers", 0)),
            total_buzz_time_ms=int(stats_data.get("total_buzz_time_ms", 0)),
            fastest_buzz_ms=stats_data.get("fastest_buzz_ms"),
            player_buzz_counts=dict(stats_data.get("player_buzz_counts", {})),
            questions_by_attempt=dict(stats_data.get("questions_by_attempt", {})),
            total_attempts=int(stats_data.get("total_attempts", 0)),
        )

        self.phase_changed.emit(self.phase.value)
        self.lock_changed.emit(self.locked_buzzer_id)
        self.scores_changed.emit()
        self.stats_changed.emit()
        self.question_changed.emit()
        self.attempt_changed.emit(self.current_attempt_number)

    # =========================================================================
    # ANSWER HANDLING WITH CASCADING ATTEMPTS
    # =========================================================================

    def apply_answer(
        self, is_correct: bool, answering_player_id: Optional[int] = None
    ) -> None:
        if self.locked_buzzer_id is None:
            self.error_occurred.emit("No player has buzzed in")
            return

        if (
            answering_player_id is not None
            and answering_player_id != self.locked_buzzer_id
        ):
            print(
                f"[ENGINE] 🚫 Ignored answer from Player {answering_player_id} "
                f"(locked player is {self.locked_buzzer_id})"
            )
            return

        pid = self.locked_buzzer_id
        question = self.current_question()

        current_time_ms = int(time.time() * 1000)
        ref_time = (
            self.buzz_unlock_time_ms
            if self.buzz_unlock_time_ms
            else self.question_start_time_ms
        )
        buzz_time_ms = current_time_ms - ref_time

        points_for_attempt = question.get_points_for_attempt(
            self.current_attempt_number
        )

        if is_correct:
            points = points_for_attempt

            if (
                self.cfg.bonus_for_speed
                and self.current_attempt_number == 1
                and buzz_time_ms < 3000
            ):
                points += 1

            reason = f"Correct on attempt {self.current_attempt_number} - Q{self.current_q_idx + 1}"

            self._save_state_for_undo(pid, points, is_correct, self.current_q_idx)
            self.scores.add(pid, points, reason)
            self._finalise_undo_state()
            self.scores_changed.emit()

            self.stats.record_answer(
                True, pid, buzz_time_ms, self.current_attempt_number
            )
            self.stats_changed.emit()

            self.attempt_records.append(
                AttemptRecord(
                    player_id=pid,
                    is_correct=True,
                    points_awarded=points,
                    attempt_number=self.current_attempt_number,
                    buzz_time_ms=buzz_time_ms,
                )
            )

            self.answered_questions.add(self.current_q_idx)

            print(
                f"[ENGINE] ✓ Player {pid} correct! +{points} pts (Attempt {self.current_attempt_number})"
            )

            self.locked_buzzer_id = None
            self.lock_changed.emit(None)
            self.answer_timer.stop()
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)

            print("[ENGINE] ⏸️ Question complete - waiting for admin to advance")
            return

        # WRONG ANSWER
        if self.cfg.penalty_for_wrong > 0:
            penalty = -self.cfg.penalty_for_wrong
            reason = f"Wrong answer - Q{self.current_q_idx + 1}"
            self._save_state_for_undo(pid, penalty, False, self.current_q_idx)
            self.scores.add(pid, penalty, reason)
            self._finalise_undo_state()
            self.scores_changed.emit()

        self.stats.record_answer(False, pid, buzz_time_ms, self.current_attempt_number)
        self.stats_changed.emit()

        self.attempt_records.append(
            AttemptRecord(
                player_id=pid,
                is_correct=False,
                points_awarded=-self.cfg.penalty_for_wrong
                if self.cfg.penalty_for_wrong > 0
                else 0,
                attempt_number=self.current_attempt_number,
                buzz_time_ms=buzz_time_ms,
            )
        )

        self.players_attempted.add(pid)
        self.attempt_failed.emit(pid, self.current_attempt_number)

        max_attempts = max(1, int(getattr(question, "max_attempts", 1)))
        remaining_players = self.get_players_remaining()

        print(f"[ENGINE] ✗ Player {pid} wrong (Attempt {self.current_attempt_number})")
        print(
            f"[ENGINE] Cascading check: enabled={self.cfg.enable_cascading_attempts}, "
            f"attempt={self.current_attempt_number}, max_attempts={max_attempts}, "
            f"remaining_players={remaining_players}"
        )

        if (
            self.cfg.enable_cascading_attempts
            and self.current_attempt_number < max_attempts
            and remaining_players
        ):
            self.current_attempt_number += 1
            self.attempt_changed.emit(self.current_attempt_number)

            self.locked_buzzer_id = None
            self.lock_changed.emit(None)

            if self.cfg.reset_timer_each_attempt:
                self._question_remaining_ms = int(self.cfg.timer_seconds * 1000)

            self.answer_timer.stop()

            self.phase = Phase.SHOW_QUESTION
            self.phase_changed.emit(self.phase.value)

            print(
                f"[ENGINE] → Next attempt available ({self.current_attempt_number}/{max_attempts})"
            )
            print(f"[ENGINE] → Remaining players: {remaining_players}")
            return

        self._on_all_attempts_exhausted()

    def notify_buzzers_unlocked(self) -> None:
        self.buzz_unlock_time_ms = int(time.time() * 1000)

    # =========================================================================
    # UNDO / REDO
    # =========================================================================

    def _save_state_for_undo(
        self, player_id: int, points: int, is_correct: bool, question_idx: int
    ):
        state = {
            "player_id": player_id,
            "points": points,
            "is_correct": is_correct,
            "question_idx": question_idx,
            "scores_before": self.scores.scores.copy(),
        }
        self._undo_stack.append(state)
        self._redo_stack.clear()

    def _finalise_undo_state(self) -> None:
        if self._undo_stack:
            self._undo_stack[-1] = dict(
                self._undo_stack[-1],
                scores_after=self.scores.scores.copy(),
            )

    def undo_last_answer(self) -> bool:
        if not self._undo_stack:
            return False
        state = self._undo_stack.pop()
        self._redo_stack.append(state)

        for pid, score in state["scores_before"].items():
            self.scores.scores[pid] = score

        if self.scores.history:
            self.scores.history.pop()

        self.answered_questions.discard(state["question_idx"])
        self.scores_changed.emit()
        print(
            f"[ENGINE] ↩ Undid answer for Player {state['player_id']} "
            f"(Q{state['question_idx'] + 1}, {state['points']} pts)"
        )
        return True

    def redo_last_answer(self) -> bool:
        if not self._redo_stack:
            return False

        state = self._redo_stack.pop()
        scores_after = state.get("scores_after")
        if scores_after is None:
            return False

        self._undo_stack.append(state)

        for pid, score in scores_after.items():
            self.scores.scores[pid] = score

        if state.get("is_correct"):
            self.answered_questions.add(state["question_idx"])

        self.scores_changed.emit()
        print(
            f"[ENGINE] ↪ Redid answer for Player {state['player_id']} "
            f"(Q{state['question_idx'] + 1}, {state['points']} pts)"
        )
        return True
