from dataclasses import dataclass

@dataclass(frozen=True)
class BuzzEvent:
    buzzer_id: int      # 1..4
    t_ms: int           # timestamp from device (millis)
    received_ms: int    # timestamp on pi when received

@dataclass(frozen=True)
class AnswerEvent:
    buzzer_id: int
    is_correct: bool
