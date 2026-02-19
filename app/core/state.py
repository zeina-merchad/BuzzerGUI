from enum import Enum


class Phase(str, Enum):
    """
    Game-engine phase names.

    BUZZED is the engine-side name for the state where a player has locked in
    and the answer timer is running.  The MQTT backend calls the same state
    BuzzerState.LOCKED.  LOCKED is kept here as an alias so any code that
    cross-references the two enums by name does not silently use the wrong value.
    """
    IDLE          = "IDLE"
    SHOW_QUESTION = "SHOW_QUESTION"
    BUZZED        = "BUZZED"
    GAME_END      = "GAME_END"

    # Alias: LOCKED == BUZZED — matches BuzzerState.LOCKED in mqtt_buzzer.py
    # Python enums allow aliases when the value is identical to an existing member.
    LOCKED        = "BUZZED"