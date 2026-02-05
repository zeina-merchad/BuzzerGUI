from enum import Enum

class Phase(str, Enum):
    IDLE = "IDLE"
    SHOW_QUESTION = "SHOW_QUESTION"
    BUZZED = "BUZZED"
    JUDGING = "JUDGING"
    ROUND_END = "ROUND_END"
    GAME_END = "GAME_END"
