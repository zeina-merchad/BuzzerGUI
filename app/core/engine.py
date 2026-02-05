import random
import time
from typing import List, Optional, Set
from collections import deque

from PySide6.QtCore import QObject, Signal

from app.core.state import Phase
from app.core.models import GameConfig, Question, Scoreboard, GameStats, AttemptRecord
from app.core.timer import CountdownTimer


class GameEngine(QObject):
    """Enhanced game engine with cascading attempts support"""
    
    # UI signals
    phase_changed = Signal(str)
    question_changed = Signal()
    timer_changed = Signal(int)          # remaining_ms
    lock_changed = Signal(object)        # locked_buzzer_id or None
    scores_changed = Signal()
    stats_changed = Signal()
    error_occurred = Signal(str)
    
    # NEW: Cascading attempts signals
    attempt_changed = Signal(int)        # current_attempt_number (1-4)
    attempt_failed = Signal(int, int)    # (player_id, attempt_number)
    
    def __init__(self, cfg: GameConfig, questions: List[Question]):
        super().__init__()
        
        # Validate configuration
        valid, error = cfg.validate()
        if not valid:
            raise ValueError(f"Invalid configuration: {error}")
        
        self.cfg = cfg
        self.original_questions = questions[:]
        self.questions = questions[:]
        
        if cfg.shuffle_questions:
            random.shuffle(self.questions)
        
        self.phase: Phase = Phase.IDLE
        self.current_q_idx: int = 0
        self.locked_buzzer_id: Optional[int] = None
        self.question_start_time_ms: int = 0
        
        # NEW: Cascading attempts tracking
        self.current_attempt_number: int = 0
        self.players_attempted: Set[int] = set()  # Players who already tried this question
        self.attempt_records: List[AttemptRecord] = []  # All attempts for current question
        
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
    
    # ----- Getters -----
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
    
    # ----- Game Control -----
    def start_question(self) -> None:
        """Start showing current question"""
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
        
        self.timer.start(self.cfg.timer_seconds * 1000)
        self.question_changed.emit()
    
    def next_question(self) -> None:
        """Move to next question"""
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
        
        # Move to next question
        self.current_q_idx = (self.current_q_idx + 1) % len(self.questions)
        
        # Check if we've completed all questions
        if len(self.answered_questions) >= len(self.questions):
            self.end_game()
        else:
            self.start_question()
    
    def reset_buzzers_only(self) -> None:
        """Reset buzzers without changing timer"""
        self.locked_buzzer_id = None
        self.lock_changed.emit(None)
    
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
        self.locked_buzzer_id = None
        self.phase = Phase.IDLE
        self.current_attempt_number = 0
        self.players_attempted.clear()
        self.attempt_records.clear()
        
        if self.cfg.shuffle_questions:
            self.questions = self.original_questions[:]
            random.shuffle(self.questions)
        
        self._undo_stack.clear()
        self._redo_stack.clear()
        
        self.phase_changed.emit(self.phase.value)
        self.scores_changed.emit()
        self.stats_changed.emit()
        self.question_changed.emit()
    
    def end_game(self) -> None:
        """End the game"""
        self.phase = Phase.GAME_END
        self.phase_changed.emit(self.phase.value)
        self.timer.stop()
    
    # ----- Answer Handling with Cascading Attempts -----
    def apply_answer(self, is_correct: bool) -> None:
        """
        Apply answer judgement with cascading attempts support.
        If wrong and more attempts available, allow next player to try.
        """
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
            # CORRECT ANSWER - Award points and move to next question
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
            
            # Move to next question
            self.next_question()
            
        else:
            # WRONG ANSWER
            # Apply penalty if configured
            if self.cfg.penalty_for_wrong > 0:
                penalty = -self.cfg.penalty_for_wrong
                reason = f"Wrong answer - Q{self.current_q_idx + 1}"
                self.scores.add(pid, penalty, reason)
                self.scores_changed.emit()
            
            # Record statistics
            self.stats.record_answer(False, pid, buzz_time_ms, self.current_attempt_number)
            self.stats_changed.emit()
            
            # Record attempt
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
            
            # Check if cascading attempts is enabled and more attempts available
            if self.cfg.enable_cascading_attempts and self.current_attempt_number < question.max_attempts:
                # Check if there are players who haven't tried yet
                remaining_players = self.get_players_remaining()
                
                if remaining_players:
                    # Allow next attempt
                    self.current_attempt_number += 1
                    self.attempt_changed.emit(self.current_attempt_number)
                    
                    # Reset buzzer lock to allow new player
                    self.locked_buzzer_id = None
                    self.lock_changed.emit(None)
                    
                    # Optionally reset timer
                    if self.cfg.reset_timer_each_attempt:
                        self.timer.start(self.cfg.timer_seconds * 1000)
                    else:
                        # Resume existing timer
                        self.timer.resume()
                    
                    # Return to show question phase
                    self.phase = Phase.SHOW_QUESTION
                    self.phase_changed.emit(self.phase.value)
                    
                    return  # Don't move to next question yet
            
            # No more attempts available or cascading disabled
            # Mark question as answered (incorrectly)
            self.answered_questions.add(self.current_q_idx)
            
            # Move to next question
            self.next_question()
    
    # ----- Buzzer Input -----
    def on_buzz(self, buzzer_id: int, t_ms: int, received_ms: int) -> bool:
        """
        Handle buzz event with cascading attempts support.
        Returns True if this buzz wins and locks the question.
        """
        if self.phase != Phase.SHOW_QUESTION:
            return False
        
        # Check if this player already attempted
        if buzzer_id in self.players_attempted:
            self.error_occurred.emit(f"Player {buzzer_id} already attempted this question")
            return False
        
        # Check if someone else is currently locked
        if self.locked_buzzer_id is not None:
            return False
        
        # Lock this player
        self.locked_buzzer_id = buzzer_id
        self.lock_changed.emit(buzzer_id)
        
        self.phase = Phase.BUZZED
        self.phase_changed.emit(self.phase.value)
        
        # Pause timer
        self.timer.pause()
        
        return True
    
    # ----- Undo/Redo -----
    def _save_state_for_undo(self, player_id: int, points: int, is_correct: bool, question_idx: int):
        """Save state for undo operation"""
        state = {
            'player_id': player_id,
            'points': points,
            'is_correct': is_correct,
            'question_idx': question_idx,
            'scores_snapshot': self.scores.scores.copy()
        }
        self._undo_stack.append(state)
        self._redo_stack.clear()
    
    def can_undo(self) -> bool:
        """Check if undo is available"""
        return len(self._undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Check if redo is available"""
        return len(self._redo_stack) > 0
    
    def undo(self) -> None:
        """Undo last action"""
        if not self.can_undo():
            self.error_occurred.emit("Nothing to undo")
            return
        
        state = self._undo_stack.pop()
        
        # Save current state for redo
        self._redo_stack.append({
            'player_id': state['player_id'],
            'points': state['points'],
            'is_correct': state['is_correct'],
            'question_idx': state['question_idx'],
            'scores_snapshot': self.scores.scores.copy()
        })
        
        # Restore previous scores
        self.scores.scores = state['scores_snapshot'].copy()
        self.scores_changed.emit()
        
        # Go back to that question
        self.current_q_idx = state['question_idx']
        self.answered_questions.discard(state['question_idx'])
        self.start_question()
    
    def redo(self) -> None:
        """Redo last undone action"""
        if not self.can_redo():
            self.error_occurred.emit("Nothing to redo")
            return
        
        state = self._redo_stack.pop()
        
        # Restore the state
        self.scores.scores = state['scores_snapshot'].copy()
        self.scores_changed.emit()
        
        # Move back to undo stack
        self._undo_stack.append(state)
    
    # ----- Internal Callbacks -----
    def _on_timer_ended(self) -> None:
        """Handle timer expiration"""
        if self.phase == Phase.SHOW_QUESTION:
            # Time's up without correct answer
            self.phase = Phase.IDLE
            self.phase_changed.emit(self.phase.value)
            
            # Mark as answered (no one got it)
            self.answered_questions.add(self.current_q_idx)
            
            # Could auto-advance or wait for host
            # self.next_question()
    
    # ----- Question Management -----
    def reload_questions(self, new_questions: List[Question]) -> None:
        """Reload questions"""
        self.questions = new_questions[:]
        self.original_questions = new_questions[:]
        
        if self.cfg.shuffle_questions:
            random.shuffle(self.questions)
        
        if self.current_q_idx >= len(self.questions):
            self.current_q_idx = 0
        
        self.answered_questions.clear()
        self.question_changed.emit()
    
    def update_config(self, new_cfg: GameConfig) -> None:
        """Update game configuration"""
        valid, error = new_cfg.validate()
        if not valid:
            self.error_occurred.emit(f"Invalid configuration: {error}")
            return
        
        self.cfg = new_cfg
        
        if new_cfg.shuffle_questions and not self.cfg.shuffle_questions:
            self.questions = self.original_questions[:]
            random.shuffle(self.questions)