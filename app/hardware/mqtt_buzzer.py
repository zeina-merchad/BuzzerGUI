import json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional

import paho.mqtt.client as mqtt
from PySide6.QtCore import QObject, Qt, Signal


class BuzzerState(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    LOCKED = "locked"
    ANSWERED = "answered"
    RESULT_SHOWN = "result_shown"


@dataclass
class BuzzEvent:
    player_id: int
    timestamp_ms: int
    server_received_ms: int

    @property
    def latency_ms(self) -> int:
        return self.server_received_ms - self.timestamp_ms


@dataclass
class AnswerEvent:
    player_id: int
    answer: str
    timestamp_ms: int
    server_received_ms: int


class MQTTSignalBridge(QObject):
    buzz_received = Signal(object)  # BuzzEvent
    answer_received = Signal(object)  # AnswerEvent
    player_connected = Signal(int)
    player_disconnected = Signal(int)
    state_changed = Signal(object)  # BuzzerState


class MQTTBuzzerBackend:
    """
    MQTT backend for ESP32 buzzers.

    Connection model
    ----------------
    Players are tracked purely by activity: any buzzer that sends a message
    is considered connected.  There is no heartbeat, ping/pong, or passive
    timeout — once a buzzer appears it stays in connected_players for the life
    of the MQTT session.  The host screen calls get_connected_players() at game
    start to seed the engine's active player set.

    paho-mqtt callbacks run on a background thread (loop_start()).
    All Qt/engine interaction goes through Qt signals dispatched to the main
    thread via QueuedConnection.
    """

    TOPIC_BUZZ = "fbz/buzzer/+/buzz"
    TOPIC_ANSWER = "fbz/buzzer/+/answer"
    TOPIC_GAME_LOCK = "fbz/game/lock"
    TOPIC_GAME_RESET = "fbz/game/reset"

    def __init__(self, broker_host: str = "192.168.10.10", broker_port: int = 1883):
        self.broker_host = broker_host
        self.broker_port = broker_port

        self.bridge = MQTTSignalBridge()

        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._state_lock = threading.RLock()

        self.connected: bool = False
        self.connection_time: Optional[float] = None

        self.state: BuzzerState = BuzzerState.IDLE
        self.current_question_id: Optional[str] = None
        self.locked_player: Optional[int] = None

        # player_id → timestamp of last received message (for informational purposes)
        self.connected_players: Dict[int, float] = {}

        self.on_buzz_callback: Optional[Callable] = None
        self.on_answer_callback: Optional[Callable] = None
        self.on_player_connected_callback: Optional[Callable] = None
        self.on_player_disconnected_callback: Optional[Callable] = None
        self.on_state_change_callback: Optional[Callable] = None

        self.bridge.buzz_received.connect(self._dispatch_buzz, Qt.QueuedConnection)
        self.bridge.answer_received.connect(self._dispatch_answer, Qt.QueuedConnection)
        self.bridge.player_connected.connect(
            self._dispatch_player_connected, Qt.QueuedConnection
        )
        self.bridge.player_disconnected.connect(
            self._dispatch_player_disconnected, Qt.QueuedConnection
        )
        self.bridge.state_changed.connect(
            self._dispatch_state_changed, Qt.QueuedConnection
        )

    # =========================================================================
    # MAIN-THREAD DISPATCHERS
    # =========================================================================

    def _dispatch_buzz(self, event: BuzzEvent) -> None:
        if self.on_buzz_callback:
            self.on_buzz_callback(event)

    def _dispatch_answer(self, event: AnswerEvent) -> None:
        if self.on_answer_callback:
            self.on_answer_callback(event)

    def _dispatch_player_connected(self, player_id: int) -> None:
        if self.on_player_connected_callback:
            self.on_player_connected_callback(player_id)

    def _dispatch_player_disconnected(self, player_id: int) -> None:
        if self.on_player_disconnected_callback:
            self.on_player_disconnected_callback(player_id)

    def _dispatch_state_changed(self, state: BuzzerState) -> None:
        if self.on_state_change_callback:
            self.on_state_change_callback(state)

    # =========================================================================
    # CONNECTION MANAGEMENT
    # =========================================================================

    def connect(self) -> bool:
        if self.connected:
            return True
        try:
            print(f"[MQTT] Connecting to {self.broker_host}:{self.broker_port}...")
            self.client.connect_async(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"[MQTT] ❌ Connection failed: {e}")
            try:
                self.client.loop_stop()
            except Exception:
                pass
            return False

    def disconnect(self) -> None:
        if self.connected:
            print("[MQTT] Disconnecting...")
            self.client.disconnect()
            self.client.loop_stop()
        self.connected = False

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self.connected = True
            self.connection_time = time.time()
            print("[MQTT] ✅ Broker connected")
            client.subscribe(self.TOPIC_BUZZ)
            client.subscribe(self.TOPIC_ANSWER)
            print("[MQTT] ✅ Subscribed: buzz / answer")
        else:
            self.connected = False
            print(f"[MQTT] ❌ Broker connect failed (rc={rc})")

    def _on_disconnect(self, client, userdata, rc) -> None:
        self.connected = False
        if rc != 0:
            print(f"[MQTT] ⚠ Unexpected disconnect (rc={rc})")
        else:
            print("[MQTT] Disconnected")

    # =========================================================================
    # PLAYER TRACKING (activity-based, no timeout)
    # =========================================================================

    def _update_player_connection(self, player_id: int) -> None:
        """Record that player_id sent a message; emit connected on first sight."""
        now = time.time()
        first_time = player_id not in self.connected_players
        self.connected_players[player_id] = now
        if first_time:
            print(f"[MQTT] ✓ Player {player_id} seen for the first time")
            self.bridge.player_connected.emit(player_id)

    def get_connected_players(self) -> List[int]:
        """Return all players that have ever sent a message this session."""
        return sorted(self.connected_players.keys())

    # =========================================================================
    # MESSAGE HANDLING (MQTT thread)
    # =========================================================================

    def _on_message(self, client, userdata, msg) -> None:
        try:
            topic = msg.topic
            payload = msg.payload.decode(errors="replace")
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                print(f"[MQTT] ⚠ Invalid JSON on {topic}: {msg.payload!r}")
                return

            player_id = int(data.get("id", 0))
            if player_id <= 0:
                print(f"[MQTT] ⚠ Missing/invalid player id on {topic}: {payload!r}")
                return

            self._update_player_connection(player_id)

            if topic.endswith("/buzz"):
                self._handle_buzz(player_id, data)
            elif topic.endswith("/answer"):
                self._handle_answer(player_id, data)

        except Exception as e:
            print(f"[MQTT] ❌ Error in _on_message: {e}")
            import traceback

            traceback.print_exc()

    def _handle_buzz(self, player_id: int, data: dict) -> None:
        ts_ms = int(data.get("t_ms", 0))
        recv_ms = int(time.time() * 1000)
        ev = BuzzEvent(
            player_id=player_id, timestamp_ms=ts_ms, server_received_ms=recv_ms
        )

        with self._state_lock:
            current_state = self.state
            locked_player = self.locked_player

            if current_state != BuzzerState.ACTIVE:
                print(
                    f"[MQTT] Buzz ignored (state={current_state.value}) from P{player_id}"
                )
                return

            if locked_player is not None:
                print(f"[MQTT] Buzz ignored (already locked by P{locked_player})")
                return

        # Let HostScreen → GameEngine decide whether the buzz is valid.
        self.bridge.buzz_received.emit(ev)

    def _handle_answer(self, player_id: int, data: dict) -> None:
        ans = str(data.get("answer", "")).strip().upper()
        ts_ms = int(data.get("t_ms", 0))
        recv_ms = int(time.time() * 1000)
        ev = AnswerEvent(
            player_id=player_id,
            answer=ans,
            timestamp_ms=ts_ms,
            server_received_ms=recv_ms,
        )

        with self._state_lock:
            current_state = self.state
            locked_player = self.locked_player
            if current_state != BuzzerState.LOCKED:
                print(
                    f"[MQTT] Answer ignored (state={current_state.value}) from P{player_id}"
                )
                return
            if locked_player != player_id:
                print(
                    f"[MQTT] Answer ignored (locked=P{locked_player}) from P{player_id}"
                )
                return

        self._set_state(BuzzerState.ANSWERED)
        self.bridge.answer_received.emit(ev)

    # =========================================================================
    # GAME CONTROL (main thread)
    # =========================================================================

    def start_question(self, question_id: str, max_attempts: int = 1) -> None:
        with self._state_lock:
            self.current_question_id = question_id
            self.locked_player = None
        self._set_state(BuzzerState.IDLE)
        self._publish_reset()

    def unlock_buzzers(self) -> None:
        with self._state_lock:
            self.locked_player = None
        self._publish_reset()
        self._set_state(BuzzerState.ACTIVE)

    def lock_player(self, player_id: int) -> None:
        pid = int(player_id)
        with self._state_lock:
            self.locked_player = pid
        self._set_state(BuzzerState.LOCKED)
        self._publish_lock(pid)

    def mark_answer_wrong(self, player_id: int) -> None:
        with self._state_lock:
            self.locked_player = None
        self._set_state(BuzzerState.IDLE)

    def mark_answer_correct(self, player_id: int) -> None:
        with self._state_lock:
            self.locked_player = None
        self._set_state(BuzzerState.RESULT_SHOWN)

    def end_question(self) -> None:
        with self._state_lock:
            self.current_question_id = None
            self.locked_player = None
        self._publish_reset()
        self._set_state(BuzzerState.IDLE)

    # =========================================================================
    # MQTT PUBLISHING
    # =========================================================================

    def _publish_lock(self, player_id: int) -> None:
        pid = int(player_id)
        try:
            self.client.publish(self.TOPIC_GAME_LOCK, str(pid))
            self.client.publish(
                f"{self.TOPIC_GAME_LOCK}/{pid}",
                json.dumps({"id": pid, "ts": time.time()}),
            )
            print(f"[MQTT] 🔒 LOCK published for P{pid}")
        except Exception as e:
            print(f"[MQTT] ❌ Failed to publish lock: {e}")

    def _publish_reset(self) -> None:
        try:
            self.client.publish(self.TOPIC_GAME_RESET, "")
            print("[MQTT] 🔓 RESET published")
        except Exception as e:
            print(f"[MQTT] ❌ Failed to publish reset: {e}")

    def _set_state(self, new_state: BuzzerState) -> None:
        with self._state_lock:
            old = self.state
            self.state = new_state
        if old != new_state:
            print(f"[MQTT] State: {old.value} -> {new_state.value}")
            self.bridge.state_changed.emit(new_state)

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "state": self.state.value,
            "current_question": self.current_question_id,
            "locked_player": self.locked_player,
            "connected_players": self.get_connected_players(),
        }
