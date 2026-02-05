from enum import Enum

MAX_PLAYERS = 4

# BLE contract (must match ESP32)
BLE_SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab"
BLE_BUZZ_UUID    = "12345678-1234-1234-1234-1234567890ac"  # Notify
BLE_CMD_UUID     = "12345678-1234-1234-1234-1234567890ad"  # Write

BLE_NAME_PREFIX = "FBZ_"   # devices advertise as FBZ_1 .. FBZ_4

class MediaType(str, Enum):
    NONE = "none"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"