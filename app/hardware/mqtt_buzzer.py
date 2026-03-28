import paho.mqtt.client as mqtt
import json
import time
import threading
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal, Qt


class BuzzerState(Enum):
    IDLE         = "idle"
    ACTIVE       = "active"
    LOCKED       = "locked"
    ANSWERED     = "answered"
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


# =============================================================================
# SIGNAL BRIDGE
# =============================================================================

class MQTTSignalBridge(QObject):
    buzz_received       = Signal(object)   # BuzzEvent
    answer_received     = Signal(object)   # AnswerEvent
    player_connected    = Signal(int)
    player_disconnected = Signal(int)
    state_changed       = Signal(object)   # BuzzerState
    heartbeat_resolved  = Signal(object)   # dict {player_id: bool}


class MQTTBuzzerBackend:
    """
    MQTT backend for ESP32 buzzers.

    paho-mqtt callbacks run on a background thread (loop_start()).
    All Qt/engine interaction goes through Qt signals dispatched to the main thread.
    """

    TOPIC_BUZZ          = "fbz/buzzer/+/buzz"
    TOPIC_ANSWER        = "fbz/buzzer/+/answer"
    TOPIC_PONG          = "fbz/buzzer/+/pong"
    TOPIC_GAME_LOCK     = "fbz/game/lock"
    TOPIC_GAME_RESET    = "fbz/game/reset"
    TOPIC_GAME_PING_PREFIX = "fbz/game/ping"

    _CONN_CHECK_INTERVAL_S = 5.0

    def __init__(self, broker_host: str = "192.168.10.10", broker_port: int = 1883):
        self.broker_host = broker_host
        self.broker_port = broker_port

        self.bridge = MQTTSignalBridge()

        self.client = mqtt.Client()
        self.client.on_connect    = self._on_connect
        self.client.on_message    = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._state_lock = threading.RLock()

        self.connected: bool = False
        self.connection_time: Optional[float] = None

        self.state: BuzzerState = BuzzerState.IDLE
        self.current_question_id: Optional[str] = None
        self.locked_player: Optional[int] = None

        self.connected_players: Dict[int, float] = {}

        self.heartbeat_timeout = 5.0
        self.last_heartbeat_sent: Dict[int, float] = {}
        self.last_heartbeat_received: Dict[int, float] = {}
        self.awaiting_pong: Dict[int, bool] = {}
        # Generation counter — prevents stale timeout threads from emitting
        # heartbeat_resolved after a newer round has already started.
        self._heartbeat_generation: int = 0

        self._known_disconnected: Set[int] = set()
        self._last_conn_check: float = 0.0

        # Callback API (HostScreen assigns these)
        self.on_buzz_callback:                Optional[Callable] = None
        self.on_answer_callback:              Optional[Callable] = None
        self.on_player_connected_callback:    Optional[Callable] = None
        self.on_player_disconnected_callback: Optional[Callable] = None
        self.on_state_change_callback:        Optional[Callable] = None
        self.on_player_unresponsive_callback: Optional[Callable] = None

        # Wire bridge signals → dispatchers (Qt queued so they land on main thread)
        self.bridge.buzz_received.connect(self._dispatch_buzz,             Qt.QueuedConnection)
        self.bridge.answer_received.connect(self._dispatch_answer,         Qt.QueuedConnection)
        self.bridge.player_connected.connect(self._dispatch_player_connected,    Qt.QueuedConnection)
        self.bridge.player_disconnected.connect(self._dispatch_player_disconnected, Qt.QueuedConnection)
        self.bridge.state_changed.connect(self._dispatch_state_changed,    Qt.QueuedConnection)
        # heartbeat_resolved is connected directly by HostScreen

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
        """Connect to broker.

        FIX #8: the busy-wait loop blocks the calling thread.  This is
        acceptable at startup (before the Qt event loop starts) but must
        NOT be called again while the event loop is running — doing so
        freezes the UI for up to 5 seconds.  A guard is added so a second
        call while already connected returns True immediately.
        """
        if self.connected:
            return True
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
            self.client.loop_stop()
            return False
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
            self.client.disconnect()   # FIX: send DISCONNECT packet first
            self.client.loop_stop()    # then halt the background thread
        self.connected = False

    def _on_connect(self, client, userdata, flags, rc) -> None:
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

        for pid in list(self.connected_players.keys()):
            if pid not in self._known_disconnected:
                self._known_disconnected.add(pid)
                self.bridge.player_disconnected.emit(pid)

        if rc != 0:
            print(f"[MQTT] ⚠ Unexpected disconnect (rc={rc})")
        else:
            print("[MQTT] Disconnected")
    def _update_player_connection(self, player_id: int) -> None:
        now = time.time()
        was_connected = player_id in self.connected_players
        was_known_disconnected = player_id in self._known_disconnected

        self.connected_players[player_id] = now
        self._known_disconnected.discard(player_id)

        if not was_connected or was_known_disconnected:
            print(f"[MQTT] ✓ Player {player_id} connected")
            self.bridge.player_connected.emit(player_id)
    def _passive_disconnect_check(self) -> None:
        now = time.time()
        with self._state_lock:
            if now - self._last_conn_check < self._CONN_CHECK_INTERVAL_S:
                return
            self._last_conn_check = now
            items = list(self.connected_players.items())

        for pid, last_seen in items:
            if (now - last_seen) > self.heartbeat_timeout:
                should_emit = False
                with self._state_lock:
                    if pid not in self._known_disconnected:
                        self._known_disconnected.add(pid)
                        should_emit = True
                if should_emit:
                    print(f"[MQTT] ✗ Player {pid} timed out (last seen {now - last_seen:.1f}s ago)")
                    self.bridge.player_disconnected.emit(pid)
    def _on_message(self, client, userdata, msg) -> None:
        try:
            topic   = msg.topic
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
            elif topic.endswith("/pong"):
                self._handle_pong(player_id, data)

            self._passive_disconnect_check()

        except Exception as e:
            print(f"[MQTT] ❌ Error in _on_message: {e}")
            import traceback; traceback.print_exc()

    # =========================================================================
    # PLAYER CONNECTION TRACKING
    # =========================================================================

    def get_connected_players(self, timeout_seconds: int = 60) -> List[int]:
        now = time.time()
        return sorted([pid for pid, last_seen in self.connected_players.items()
                       if (now - last_seen) < timeout_seconds])

    # =========================================================================
    # HEARTBEAT
    # =========================================================================

    def send_heartbeat(self, player_id: int) -> None:
        now   = time.time()
        topic = f"{self.TOPIC_GAME_PING_PREFIX}/{player_id}"
        self.client.publish(topic, json.dumps({"timestamp": now}))
        self.last_heartbeat_sent[player_id]  = now
        self.awaiting_pong[player_id]        = True

    def _handle_pong(self, player_id: int, data: dict) -> None:
        now = time.time()
        self.last_heartbeat_received[player_id] = now
        self.awaiting_pong[player_id]           = False
        self.connected_players[player_id]       = now
        self._known_disconnected.discard(player_id)

        # FIX: use awaiting_pong.keys() as the authoritative set of pinged players.
        # Previously called _expected_player_ids() here which re-reads connected_players
        # (subject to TOCTOU) and may include late-joining players that were never pinged.
        targets       = list(self.awaiting_pong.keys())
        still_waiting = [p for p in targets if self.awaiting_pong.get(p, False)]
        if not still_waiting:
            alive_map = {pid: self.check_player_liveliness(pid) for pid in targets}
            self.bridge.heartbeat_resolved.emit(alive_map)

    def check_player_liveliness(self, player_id: int) -> bool:
        now              = time.time()
        ping_sent_at     = self.last_heartbeat_sent.get(player_id)
        pong_received_at = self.last_heartbeat_received.get(player_id)

        if ping_sent_at is not None and pong_received_at is not None:
            if pong_received_at >= ping_sent_at:
                return True

        if self.awaiting_pong.get(player_id, False):
            last_seen = self.connected_players.get(player_id)
            if last_seen is not None:
                return (now - last_seen) < (self.heartbeat_timeout * 2)
            return True

        if ping_sent_at is None:
            last_seen = self.connected_players.get(player_id)
            if last_seen is not None:
                return (now - last_seen) < self.heartbeat_timeout
            return True

        last_seen = self.connected_players.get(player_id)
        if last_seen is not None:
            return (now - last_seen) < self.heartbeat_timeout
        return False

    def send_heartbeat_to_all(self, timeout_seconds: int = 10) -> None:
        targets = self._expected_player_ids()
        if not targets:
            print("[MQTT] send_heartbeat_to_all: no players to ping")
            self.bridge.heartbeat_resolved.emit({})
            return

        self._heartbeat_generation += 1
        my_generation = self._heartbeat_generation

        self.awaiting_pong.clear()
        for player_id in targets:
            self.send_heartbeat(player_id)
        print(f"[MQTT] 📡 Pinged players: {targets} (generation {my_generation})")

        def _timeout_resolver():
            time.sleep(self.heartbeat_timeout)
            if self._heartbeat_generation != my_generation:
                print(f"[MQTT] Timeout thread gen={my_generation} superseded, skipping")
                return
            still_waiting = [p for p in targets if self.awaiting_pong.get(p, False)]
            if still_waiting:
                print(f"[MQTT] ⚠ Heartbeat timeout — no pong from {still_waiting}")
                for p in still_waiting:
                    self.awaiting_pong[p] = False
                alive_map = {pid: self.check_player_liveliness(pid) for pid in targets}
                self.bridge.heartbeat_resolved.emit(alive_map)

        t = threading.Thread(target=_timeout_resolver, daemon=True)
        t.start()

    def check_all_players_liveliness(self) -> Dict[int, bool]:
        targets = self._expected_player_ids()
        return {pid: self.check_player_liveliness(pid) for pid in targets}

    def all_pings_resolved(self, timeout_seconds: int = 10) -> bool:
        now     = time.time()
        targets = self._expected_player_ids()
        for pid in targets:
            if not self.awaiting_pong.get(pid, False):
                continue
            sent_at = self.last_heartbeat_sent.get(pid)
            if sent_at is None or (now - sent_at) > timeout_seconds:
                self.awaiting_pong[pid] = False
        return not any(self.awaiting_pong.get(pid, False) for pid in targets)

    # =========================================================================
    # LOCK PLAYER
    # =========================================================================

    def lock_player(self, player_id: int) -> None:
        self._publish_lock(int(player_id))

    # =========================================================================
    # BUZZ / ANSWER HANDLING (MQTT thread)
    # =========================================================================

    def _handle_buzz(self, player_id: int, data: dict) -> None:
        ts_ms   = int(data.get("t_ms", 0))
        recv_ms = int(time.time() * 1000)
        ev      = BuzzEvent(player_id=player_id, timestamp_ms=ts_ms, server_received_ms=recv_ms)

        with self._state_lock:
            current_state = self.state
            locked_player = self.locked_player
            if current_state != BuzzerState.ACTIVE:
                print(f"[MQTT] Buzz ignored (state={current_state.value}) from P{player_id}")
                return
            if locked_player is not None:
                print(f"[MQTT] Buzz ignored (already locked by P{locked_player})")
                return
            self.locked_player = player_id

        self._set_state(BuzzerState.LOCKED)
        self._publish_lock(player_id)
        self.bridge.buzz_received.emit(ev)

    def _handle_answer(self, player_id: int, data: dict) -> None:
        ans     = str(data.get("answer", "")).strip().upper()
        ts_ms   = int(data.get("t_ms", 0))
        recv_ms = int(time.time() * 1000)
        ev      = AnswerEvent(player_id=player_id, answer=ans, timestamp_ms=ts_ms, server_received_ms=recv_ms)

        with self._state_lock:
            current_state = self.state
            locked_player = self.locked_player
            if current_state != BuzzerState.LOCKED:
                print(f"[MQTT] Answer ignored (state={current_state.value}) from P{player_id}")
                return
            if locked_player != player_id:
                print(f"[MQTT] Answer ignored (locked=P{locked_player}) from P{player_id}")
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

    def mark_answer_wrong(self, player_id: int) -> None:
        """Clear the current hardware lock after a wrong answer.

        The GameEngine is the single authority for attempts, eliminations,
        scoring, and whether another unlock is allowed. The MQTT layer only
        mirrors the transport-facing lock state.
        """
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
            self.client.publish(f"{self.TOPIC_GAME_LOCK}/{pid}",
                                json.dumps({"id": pid, "ts": time.time()}))
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
    # INTERNAL HELPERS
    # =========================================================================

    def _expected_player_ids(self) -> List[int]:
        connected = self.get_connected_players(timeout_seconds=60)
        return sorted(set(connected)) if connected else []

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> dict:
        return {
            "connected":         self.connected,
            "state":             self.state.value,
            "current_question":  self.current_question_id,
            "locked_player":     self.locked_player,
            "connected_players": self.get_connected_players(timeout_seconds=10),
        }