from enum import Enum


class Phase(str, Enum):
    """
    Game-engine phase names.

    BUZZED is the engine-side name for the state where a player has locked in
    and the answer timer is running.  The MQTT backend calls the same state
    BuzzerState.LOCKED.  LOCKED is kept here as an alias so any code that
    cross-references the two enums by name does not silently use the wrong value.

    IMPORTANT — Python enum alias behaviour:
      * Phase.LOCKED is Phase.BUZZED  →  True  (they are the same member)
      * list(Phase)                   →  does NOT include LOCKED (aliases are excluded)
      * Phase("LOCKED")               →  raises ValueError — use Phase.from_value()
    """
    IDLE          = "IDLE"
    SHOW_QUESTION = "SHOW_QUESTION"
    BUZZED        = "BUZZED"
    GAME_END      = "GAME_END"

    # Alias: LOCKED == BUZZED — matches BuzzerState.LOCKED in mqtt_buzzer.py.
    # Python enums allow aliases when the value is identical to an existing member.
    LOCKED        = "BUZZED"

    @classmethod
    def from_value(cls, value: str) -> "Phase":
        """Safe constructor that accepts both canonical values and alias names.

        Phase.from_value("BUZZED")  →  Phase.BUZZED
        Phase.from_value("LOCKED")  →  Phase.BUZZED  (alias resolved)
        Phase("LOCKED")             →  ValueError  ← use this method instead
        """
        # First try the normal enum lookup (works for canonical values)
        try:
            return cls(value)
        except ValueError:
            pass
        # Fall back to name lookup (handles "LOCKED" → Phase.BUZZED)
        try:
            return cls[value]
        except KeyError:
            raise ValueError(f"{value!r} is not a valid Phase value or name")