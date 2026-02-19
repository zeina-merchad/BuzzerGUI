from dataclasses import dataclass


@dataclass(frozen=True)
class BuzzEvent:
    """
    Represents a buzzer-press event.

    Field names now match both engine.on_buzz(buzzer_id, t_ms, received_ms)
    and mqtt_buzzer.BuzzEvent (player_id / timestamp_ms / server_received_ms).

    Previously this class used different field names than mqtt_buzzer.BuzzEvent,
    making it a maintenance trap — both mapped to engine.on_buzz() coincidentally
    but any new code reading this file would use the wrong field names.

    Backward-compat properties (buzzer_id, t_ms, received_ms) are provided so
    any existing call-site that used the old names still compiles without change.
    """
    player_id: int           # 1..4  (was: buzzer_id)
    timestamp_ms: int        # device-side timestamp ms  (was: t_ms)
    server_received_ms: int  # server-side receive timestamp ms  (was: received_ms)

    # ── backward-compat aliases ───────────────────────────────────────────
    @property
    def buzzer_id(self) -> int:
        return self.player_id

    @property
    def t_ms(self) -> int:
        return self.timestamp_ms

    @property
    def received_ms(self) -> int:
        return self.server_received_ms

    @property
    def latency_ms(self) -> int:
        return self.server_received_ms - self.timestamp_ms


@dataclass(frozen=True)
class AnswerEvent:
    """
    Represents an answer submission event.

    Previously used (buzzer_id, is_correct: bool).  Now uses player_id
    (consistent with BuzzEvent and mqtt_buzzer.AnswerEvent) and stores the raw
    answer letter so HostScreen can perform its own correctness check — matching
    the shape that mqtt_buzzer.AnswerEvent already emits on the wire.

    Backward-compat alias buzzer_id is provided.
    """
    player_id: int           # 1..4  (was: buzzer_id)
    answer: str              # 'A'|'B'|'C'|'D'  (replaces is_correct bool)
    timestamp_ms: int = 0
    server_received_ms: int = 0

    # ── backward-compat alias ─────────────────────────────────────────────
    @property
    def buzzer_id(self) -> int:
        return self.player_id