import paho.mqtt.client as mqtt
import json
import time
from typing import Optional, Callable, Dict, List, Set
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal, Qt


class BuzzerState(Enum):
    """Buzzer system states"""
    IDLE = "idle"                    # Waiting for question / locked
    ACTIVE = "active"                # Accepting buzzes
    LOCKED = "locked"                # Someone buzzed, waiting for answer
    ANSWERED = "answered"            # Answer received
    RESULT_SHOWN = "result_shown"    # Result displayed / question over


@dataclass
class BuzzEvent:
    """Represents a buzzer press"""
    player_id: int
    timestamp_ms: int
    server_received_ms: int

    @property
    def latency_ms(self) -> int:
        return self.server_received_ms - self.timestamp_ms


@dataclass
class AnswerEvent:
    """Represents an answer submission"""
    player_id: int
    answer: str
    timestamp_ms: int
    server_received_ms: int


# =============================================================================
# SIGNAL BRIDGE (MQTT thread -> Qt main thread)
# =============================================================================

class MQTTSignalBridge(QObject):
    """Marshals events from paho-mqtt thread to Qt main thread."""
    buzz_received = Signal(object)      # BuzzEvent
    answer_received = Signal(object)    # AnswerEvent
    player_connected = Signal(int)      # player_id
    player_disconnected = Signal(int)   # player_id
    state_changed = Signal(object)      # BuzzerState


class MQTTBuzzerBackend:
    """
    MQTT backend for ESP32 buzzers.

    IMPORTANT:
    - paho-mqtt callbacks run on a background thread (loop_start()).
    - The GameEngine and Qt widgets/timers MUST be touched only on the Qt main thread.
    - We therefore emit Qt signals from the MQTT thread and dispatch callbacks on the main thread.
    """

    # Topics (keep legacy ones because your ESP firmware may depend on them)
    TOPIC_BUZZ = "fbz/buzzer/+/buzz"
    TOPIC_ANSWER = "fbz/buzzer/+/answer"
    TOPIC_PONG = "fbz/buzzer/+/pong"

    TOPIC_GAME_LOCK = "fbz/game/lock"       # payload: "<player_id>"
    TOPIC_GAME_RESET = "fbz/game/reset"     # payload: ""
    TOPIC_GAME_PING_PREFIX = "fbz/game/ping"  # ping/<player_id>

    def __init__(self, broker_host: str = "192.168.10.10", broker_port: int = 1883):
        self.broker_host = broker_host
        self.broker_port = broker_port

        # Bridge must be created on the main thread BEFORE loop_start()
        self.bridge = MQTTSignalBridge()

        # MQTT client
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        # Connection state
        self.connected: bool = False
        self.connection_time: Optional[float] = None

        # Game state
        self.state: BuzzerState = BuzzerState.IDLE
        self.current_question_id: Optional[str] = None
        self.max_attempts: int = 1
        self.attempt_count: int = 0
        self.locked_player: Optional[int] = None
        self.eliminated_players: Set[int] = set()

        # Player connection tracking
        self.connected_players: Dict[int, float] = {}       # player_id -> last_seen_time

        # Heartbeat / ping
        self.heartbeat_timeout = 15.0
        self.last_heartbeat_sent: Dict[int, float] = {}
        self.last_heartbeat_received: Dict[int, float] = {}
        self.awaiting_pong: Dict[int, bool] = {}

        # Legacy callback API (HostScreen assigns these)
        self.on_buzz_callback: Optional[Callable[[BuzzEvent], None]] = None
        self.on_answer_callback: Optional[Callable[[AnswerEvent], None]] = None
        self.on_player_connected_callback: Optional[Callable[[int], None]] = None
        self.on_player_disconnected_callback: Optional[Callable[[int], None]] = None
        self.on_state_change_callback: Optional[Callable[[BuzzerState], None]] = None
        self.on_player_unresponsive_callback: Optional[Callable[[int], None]] = None

        # Dispatch bridge signals on the Qt main thread
        self.bridge.buzz_received.connect(self._dispatch_buzz, Qt.QueuedConnection)
        self.bridge.answer_received.connect(self._dispatch_answer, Qt.QueuedConnection)
        self.bridge.player_connected.connect(self._dispatch_player_connected, Qt.QueuedConnection)
        self.bridge.player_disconnected.connect(self._dispatch_player_disconnected, Qt.QueuedConnection)
        self.bridge.state_changed.connect(self._dispatch_state_changed, Qt.QueuedConnection)

    # =====================================================================
    # MAIN-THREAD DISPATCHERS
    # =====================================================================

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

    # =====================================================================
    # CONNECTION MANAGEMENT
    # =====================================================================

    def connect(self) -> bool:
        try:
            print(f"[MQTT] Connecting to {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()

            timeout = time.time() + 5
            while not self.connected and time.time() < timeout:
                time.sleep(0.05)

            if self.connected:
                print("[MQTT] ✅ Connected")
                return True

            print("[MQTT] ❌ Connection timeout")
            return False
        except Exception as e:
            print(f"[MQTT] ❌ Connection failed: {e}")
            return False

    def disconnect(self) -> None:
        if self.connected:
            print("[MQTT] Disconnecting...")
            self.client.loop_stop()
            self.client.disconnect()
        self.connected = False

    def _on_connect(self, client, userdata, flags, rc) -> None:
        # MQTT thread
        if rc == 0:
            self.connected = True
            self.connection_time = time.time()
            print("[MQTT] ✅ Broker connected")

            client.subscribe(self.TOPIC_BUZZ)
            client.subscribe(self.TOPIC_ANSWER)
            client.subscribe(self.TOPIC_PONG)
            print("[MQTT] ✅ Subscribed: buzz/answer/pong")
        else:
            self.connected = False
            print(f"[MQTT] ❌ Broker connect failed (rc={rc})")

    def _on_disconnect(self, client, userdata, rc) -> None:
        self.connected = False
        if rc != 0:
            print(f"[MQTT] ⚠ Unexpected disconnect (rc={rc})")
        else:
            print("[MQTT] Disconnected")

    def _on_message(self, client, userdata, msg) -> None:
        # MQTT thread
        try:
            topic = msg.topic
            payload = msg.payload.decode(errors="replace")

            data = json.loads(payload)
            player_id = int(data.get("id", 0))
            if player_id <= 0:
                print(f"[MQTT] ⚠ Missing/invalid player id on topic {topic}")
                return

            # update last seen
            self._update_player_connection(player_id)

            if topic.endswith("/buzz"):
                self._handle_buzz(player_id, data)
            elif topic.endswith("/answer"):
                self._handle_answer(player_id, data)
            elif topic.endswith("/pong"):
                self._handle_pong(player_id, data)

        except json.JSONDecodeError:
            print(f"[MQTT] ⚠ Invalid JSON: {msg.payload!r}")
        except Exception as e:
            print(f"[MQTT] ❌ Error in _on_message: {e}")
            import traceback
            traceback.print_exc()

    # =====================================================================
    # PLAYER CONNECTION TRACKING
    # =====================================================================

    def _update_player_connection(self, player_id: int) -> None:
        now = time.time()
        was_connected = player_id in self.connected_players
        self.connected_players[player_id] = now
        if not was_connected:
            print(f"[MQTT] ✓ Player {player_id} connected")
            self.bridge.player_connected.emit(player_id)

    def get_connected_players(self, timeout_seconds: int = 60) -> List[int]:
        now = time.time()
        return sorted([pid for pid, last_seen in self.connected_players.items() if (now - last_seen) < timeout_seconds])

    # =====================================================================
    # HEARTBEAT
    # =====================================================================

    def send_heartbeat(self, player_id: int) -> None:
        now = time.time()
        topic = f"{self.TOPIC_GAME_PING_PREFIX}/{player_id}"
        self.client.publish(topic, json.dumps({"timestamp": now}))
        self.last_heartbeat_sent[player_id] = now
        self.awaiting_pong[player_id] = True

    def _handle_pong(self, player_id: int, data: dict) -> None:
        now = time.time()
        self.last_heartbeat_received[player_id] = now
        self.awaiting_pong[player_id] = False
        # Also refresh connected_players so the fallback path sees this too
        self.connected_players[player_id] = now

    def check_player_liveliness(self, player_id: int) -> bool:
        """
        Return True if the player is considered alive.

        Priority order:
        1. If a pong arrived after the most recent ping → alive.
        2. If we are still awaiting a pong for this cycle (sent but not yet
           received) → fall back to last_seen time in connected_players.
           The device may simply be slow to respond (e.g. waking from sleep);
           if it was seen recently it is treated as alive so we don't
           incorrectly block the UNLOCK button.
        3. If a ping was sent long ago with no pong and no recent activity
           → dead.
        """
        now = time.time()
        ping_sent_at = self.last_heartbeat_sent.get(player_id)
        pong_received_at = self.last_heartbeat_received.get(player_id)

        # Case 1: pong arrived after the most recent ping → definitively alive
        if ping_sent_at is not None and pong_received_at is not None:
            if pong_received_at >= ping_sent_at:
                return True

        # Case 2: still awaiting pong → fall back to last-seen time
        if self.awaiting_pong.get(player_id, False):
            last_seen = self.connected_players.get(player_id)
            if last_seen is not None:
                # Consider alive if seen within 2× heartbeat_timeout
                return (now - last_seen) < (self.heartbeat_timeout * 2)
            # Never seen at all — unknown, assume alive so we don't block unlock
            return True

        # Case 3: no ping sent yet for this player
        if ping_sent_at is None:
            last_seen = self.connected_players.get(player_id)
            if last_seen is not None:
                return (now - last_seen) < self.heartbeat_timeout
            return True  # never pinged → don't penalise

        # Case 4: ping sent, pong never arrived, not currently awaiting
        # (awaiting_pong was cleared without a real pong — shouldn't happen,
        # but treat as a stale ping: use last-seen as fallback)
        last_seen = self.connected_players.get(player_id)
        if last_seen is not None:
            return (now - last_seen) < self.heartbeat_timeout
        return False

    def send_heartbeat_to_all(self, timeout_seconds: int = 10) -> None:
        """Ping only the players that are already connected (have been seen recently).
        Players that have never connected are skipped entirely.
        """
        connected = self.get_connected_players(timeout_seconds=timeout_seconds)
        if not connected:
            print("[MQTT] send_heartbeat_to_all: no connected players to ping")
            return
        for player_id in connected:
            self.send_heartbeat(player_id)
        print(f"[MQTT] 📡 Pinged connected players: {connected}")

    def check_all_players_liveliness(self) -> Dict[int, bool]:
        """Return a dict of {player_id: is_alive} for all known connected players."""
        connected = self.get_connected_players(timeout_seconds=60)
        return {pid: self.check_player_liveliness(pid) for pid in connected}

    def all_pings_resolved(self, timeout_seconds: int = 10) -> bool:
        """
        Return True when every recently-connected player has either:
        - responded with a pong, OR
        - been waiting long enough that we've fallen back to last-seen logic.
        Used by HostScreen to know when it can stop retrying.
        """
        connected = self.get_connected_players(timeout_seconds=timeout_seconds)
        if not connected:
            return True  # nothing to wait for
        return not any(self.awaiting_pong.get(pid, False) for pid in connected)

    # =====================================================================
    # BUZZ / ANSWER HANDLING (MQTT thread)
    # =====================================================================

    def _handle_buzz(self, player_id: int, data: dict) -> None:
        # MQTT thread
        ts_ms = int(data.get("t_ms", 0))
        recv_ms = int(time.time() * 1000)
        ev = BuzzEvent(player_id=player_id, timestamp_ms=ts_ms, server_received_ms=recv_ms)

        if self.state != BuzzerState.ACTIVE:
            print(f"[MQTT] Buzz ignored (state={self.state.value}) from P{player_id}")
            return

        if self.locked_player is not None:
            print(f"[MQTT] Buzz ignored (already locked by P{self.locked_player})")
            return

        if player_id in self.eliminated_players:
            print(f"[MQTT] Buzz ignored (eliminated) P{player_id}")
            return

        if self.attempt_count >= self.max_attempts:
            print(f"[MQTT] Buzz ignored (attempts exhausted {self.attempt_count}/{self.max_attempts})")
            return

        # Accept
        self.attempt_count += 1
        self.locked_player = player_id
        self._set_state(BuzzerState.LOCKED)

        # IMPORTANT FIX: publish lock to hardware (ESP often enables answer buttons only after lock)
        self._publish_lock(player_id)

        # Send event to Qt main thread (engine will stop timers there)
        self.bridge.buzz_received.emit(ev)

    def _handle_answer(self, player_id: int, data: dict) -> None:
        # MQTT thread
        ans = str(data.get("answer", "")).strip().upper()
        ts_ms = int(data.get("t_ms", 0))
        recv_ms = int(time.time() * 1000)
        ev = AnswerEvent(player_id=player_id, answer=ans, timestamp_ms=ts_ms, server_received_ms=recv_ms)

        # Only accept answers when LOCKED and from the locked player
        if self.state != BuzzerState.LOCKED:
            print(f"[MQTT] Answer ignored (state={self.state.value}) from P{player_id}")
            return
        if self.locked_player != player_id:
            print(f"[MQTT] Answer ignored (locked=P{self.locked_player}) from P{player_id}")
            return

        self._set_state(BuzzerState.ANSWERED)
        self.bridge.answer_received.emit(ev)

    # =====================================================================
    # GAME CONTROL (called from Qt main thread)
    # =====================================================================

    def start_question(self, question_id: str, max_attempts: int = 1) -> None:
        """Prepare for a new question. Stay IDLE until admin unlocks."""
        self.current_question_id = question_id
        self.max_attempts = max(1, int(max_attempts))
        self.attempt_count = 0
        self.eliminated_players.clear()
        self.locked_player = None

        # IMPORTANT FIX: keep backend locked until admin calls unlock_buzzers()
        self._set_state(BuzzerState.IDLE)

        # Also reset hardware so no stale lock remains
        self._publish_reset()

    def unlock_buzzers(self) -> None:
        """Admin unlock: allow buzzes."""
        self.locked_player = None
        self._publish_reset()
        self._set_state(BuzzerState.ACTIVE)

    def mark_answer_wrong(self, player_id: int) -> None:
        """Eliminate player for this question and allow next attempt (if any)."""
        self.eliminated_players.add(int(player_id))
        self.locked_player = None

        # Release hardware lock so next player can buzz
        self._publish_reset()

        # If attempts remain, go back to ACTIVE; otherwise show result
        if self.attempt_count < self.max_attempts:
            self._set_state(BuzzerState.ACTIVE)
        else:
            self._set_state(BuzzerState.RESULT_SHOWN)

    def mark_answer_correct(self, player_id: int) -> None:
        self._set_state(BuzzerState.RESULT_SHOWN)

    def end_question(self) -> None:
        self.current_question_id = None
        self.locked_player = None
        self.eliminated_players.clear()
        self._publish_reset()
        self._set_state(BuzzerState.IDLE)

    # =====================================================================
    # MQTT PUBLISHING
    # =====================================================================

    def _publish_lock(self, player_id: int) -> None:
        """
        Publish lock in a backward-compatible way:
        - fbz/game/lock : payload is just the player id (string)  (legacy)
        - fbz/game/lock/<id> : JSON payload  (optional newer firmware)
        """
        pid = int(player_id)
        try:
            self.client.publish(self.TOPIC_GAME_LOCK, str(pid))
            self.client.publish(f"{self.TOPIC_GAME_LOCK}/{pid}", json.dumps({"id": pid, "ts": time.time()}))
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
        old = self.state
        self.state = new_state
        if old != new_state:
            print(f"[MQTT] State: {old.value} -> {new_state.value}")
            self.bridge.state_changed.emit(new_state)

    # =====================================================================
    # STATUS
    # =====================================================================

    def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "state": self.state.value,
            "current_question": self.current_question_id,
            "locked_player": self.locked_player,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "eliminated_players": sorted(list(self.eliminated_players)),
            "connected_players": self.get_connected_players(timeout_seconds=10),
        }