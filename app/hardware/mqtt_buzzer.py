import paho.mqtt.client as mqtt
import json
import time
import threading
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
    # FIX: new signal fired when heartbeat results are fully resolved so
    # HostScreen can apply them without polling via QTimer.singleShot chains.
    heartbeat_resolved = Signal(object)  # dict {player_id: bool}


class MQTTBuzzerBackend:
    """
    MQTT backend for ESP32 buzzers.

    IMPORTANT:
    - paho-mqtt callbacks run on a background thread (loop_start()).
    - The GameEngine and Qt widgets/timers MUST be touched only on the Qt main thread.
    - We therefore emit Qt signals from the MQTT thread and dispatch callbacks on the main thread.

    FIX: Added heartbeat_resolved signal so HostScreen does not need to run a
    QTimer.singleShot polling chain that can stack when NEXT is clicked rapidly.
    FIX: player_disconnected is now emitted when a player times out, ensuring
    the UI connection indicators correctly go red.
    """

    # Topics (keep legacy ones because your ESP firmware may depend on them)
    TOPIC_BUZZ = "fbz/buzzer/+/buzz"
    TOPIC_ANSWER = "fbz/buzzer/+/answer"
    TOPIC_PONG = "fbz/buzzer/+/pong"

    TOPIC_GAME_LOCK = "fbz/game/lock"       # payload: "<player_id>"
    TOPIC_GAME_RESET = "fbz/game/reset"     # payload: ""
    TOPIC_GAME_PING_PREFIX = "fbz/game/ping"  # ping/<player_id>

    # How long (seconds) between passive connection-monitor checks
    _CONN_CHECK_INTERVAL_S = 5.0

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
        # player_id -> last_seen_time (float, epoch seconds)
        self.connected_players: Dict[int, float] = {}

        # Heartbeat / ping
        self.heartbeat_timeout = 15.0
        self.last_heartbeat_sent: Dict[int, float] = {}
        self.last_heartbeat_received: Dict[int, float] = {}
        self.awaiting_pong: Dict[int, bool] = {}
        # FIX C: monotonic generation counter — incremented each time a new
        # heartbeat round starts.  Timeout threads capture their generation at
        # launch and abort silently if the counter has advanced by the time
        # they wake up, preventing stale results from overwriting a newer round.
        self._heartbeat_generation: int = 0

        # Passive disconnect detection: track which players we have already
        # emitted player_disconnected for so we don't spam the signal.
        self._known_disconnected: Set[int] = set()
        # Timestamp of last passive-check so we don't check on every message.
        self._last_conn_check: float = 0.0

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
        # NOTE: bridge.heartbeat_resolved is connected directly by HostScreen
        # (_apply_heartbeat_results). Do NOT connect it here — doing so would
        # fire this dead no-op dispatch on every heartbeat_resolved emit.

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

    def _dispatch_heartbeat_resolved(self, alive_map: dict) -> None:
        """Called on main thread when a heartbeat round has resolved.

        FIX: replaces the polling QTimer.singleShot chain in HostScreen.
        HostScreen connects to bridge.heartbeat_resolved and calls
        _apply_heartbeat_results() directly from this signal.
        """
        pass  # HostScreen connects directly to bridge.heartbeat_resolved

    # =====================================================================
    # CONNECTION MANAGEMENT
    # =====================================================================

    def connect(self) -> bool:
        try:
            print(f"[MQTT] Connecting to {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()

            # Busy-wait for up to 5 s for the on_connect callback to fire.
            # This blocks the calling thread (main thread at startup — acceptable)
            # but must NOT be called after the Qt event loop has started.
            timeout = time.time() + 5
            while not self.connected and time.time() < timeout:
                time.sleep(0.05)

            if self.connected:
                print("[MQTT] ✅ Connected")
                return True

            # Timed out — clean up the background loop thread before returning.
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
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                print(f"[MQTT] ⚠ Invalid JSON on {topic}: {msg.payload!r}")
                return

            player_id = int(data.get("id", 0))
            if player_id <= 0:
                print(f"[MQTT] ⚠ Missing/invalid player id on topic {topic}: {payload!r}")
                return

            # update last seen + passive disconnect detection
            self._update_player_connection(player_id)

            if topic.endswith("/buzz"):
                self._handle_buzz(player_id, data)
            elif topic.endswith("/answer"):
                self._handle_answer(player_id, data)
            elif topic.endswith("/pong"):
                self._handle_pong(player_id, data)

            # Periodically scan for timed-out players without needing a dedicated thread
            self._passive_disconnect_check()

        except Exception as e:
            print(f"[MQTT] ❌ Error in _on_message: {e}")
            import traceback
            traceback.print_exc()

    # =====================================================================
    # PLAYER CONNECTION TRACKING
    # =====================================================================

    def _update_player_connection(self, player_id: int) -> None:
        """Record a player as seen and emit connected if this is the first time."""
        now = time.time()
        was_connected = player_id in self.connected_players
        self.connected_players[player_id] = now
        # Also clear any stale disconnect record
        self._known_disconnected.discard(player_id)

        if not was_connected:
            print(f"[MQTT] ✓ Player {player_id} connected")
            self.bridge.player_connected.emit(player_id)

    def _passive_disconnect_check(self) -> None:
        """Emit player_disconnected for players whose last-seen timestamp has
        exceeded heartbeat_timeout.  Called on the MQTT thread but rate-limited
        to once per _CONN_CHECK_INTERVAL_S to avoid hammering the signal.
        """
        now = time.time()
        if now - self._last_conn_check < self._CONN_CHECK_INTERVAL_S:
            return
        self._last_conn_check = now

        for pid, last_seen in list(self.connected_players.items()):
            if (now - last_seen) > self.heartbeat_timeout:
                if pid not in self._known_disconnected:
                    self._known_disconnected.add(pid)
                    print(f"[MQTT] ✗ Player {pid} timed out (last seen {now - last_seen:.1f}s ago)")
                    self.bridge.player_disconnected.emit(pid)

    def get_connected_players(self, timeout_seconds: int = 60) -> List[int]:
        """Return player IDs seen within timeout_seconds."""
        now = time.time()
        return sorted([pid for pid, last_seen in self.connected_players.items()
                       if (now - last_seen) < timeout_seconds])

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
        self.connected_players[player_id] = now
        self._known_disconnected.discard(player_id)

        # Determine the targets for this heartbeat round.  We avoid calling
        # _expected_player_ids() here (which can race) by using the current
        # awaiting_pong keys — these were set atomically when send_heartbeat_to_all
        # fired.  Any player that was pinged has an entry; False = pong received,
        # True = still waiting.
        targets = list(self.awaiting_pong.keys())
        still_waiting = [p for p in targets if self.awaiting_pong.get(p, False)]
        if not still_waiting:
            alive_map = {pid: self.check_player_liveliness(pid) for pid in targets}
            self.bridge.heartbeat_resolved.emit(alive_map)

    def check_player_liveliness(self, player_id: int) -> bool:
        """
        Return True if the player is considered alive.

        Priority order:
        1. Pong arrived after most recent ping → alive.
        2. Still awaiting pong → fall back to last-seen time.
        3. No ping sent → use last-seen time.
        4. Ping sent, pong never arrived → last-seen fallback.
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
                return (now - last_seen) < (self.heartbeat_timeout * 2)
            return True  # never seen — don't block unlock

        # Case 3: no ping sent yet for this player
        if ping_sent_at is None:
            last_seen = self.connected_players.get(player_id)
            if last_seen is not None:
                return (now - last_seen) < self.heartbeat_timeout
            return True  # never pinged → don't penalise

        # Case 4: ping sent, pong never arrived, not currently awaiting
        last_seen = self.connected_players.get(player_id)
        if last_seen is not None:
            return (now - last_seen) < self.heartbeat_timeout
        return False

    def send_heartbeat_to_all(self, timeout_seconds: int = 10) -> None:
        """Ping players that have been seen recently.

        FIX: after pinging, sets a global timeout so _handle_pong can emit
        heartbeat_resolved even if some devices never reply.  This replaces the
        need for a polling QTimer.singleShot chain in HostScreen.

        FIX C: generation counter prevents a stale timeout thread from an old
        heartbeat round emitting heartbeat_resolved after a new round has started.
        """
        connected = self.get_connected_players(timeout_seconds=timeout_seconds)
        targets = self._expected_player_ids()

        if not connected and not targets:
            print("[MQTT] send_heartbeat_to_all: no players to ping")
            # Emit immediately with all dead so HostScreen is not stuck waiting
            alive_map = {pid: False for pid in [1, 2, 3, 4]}
            self.bridge.heartbeat_resolved.emit(alive_map)
            return

        # FIX C: advance the generation counter for this round
        self._heartbeat_generation += 1
        my_generation = self._heartbeat_generation

        for player_id in targets:
            self.send_heartbeat(player_id)
        print(f"[MQTT] 📡 Pinged players: {targets} (generation {my_generation})")

        # Fallback: if no pongs arrive within heartbeat_timeout, emit resolved
        # with whatever state we have.  Uses a background-thread sleep rather
        # than a QTimer to avoid touching Qt from the MQTT thread.
        import threading  # already imported at module level; kept for clarity
        def _timeout_resolver():
            time.sleep(self.heartbeat_timeout)
            # FIX C: abort if a newer heartbeat round has since been launched
            if self._heartbeat_generation != my_generation:
                print(f"[MQTT] Timeout thread gen={my_generation} superseded by gen={self._heartbeat_generation}, skipping")
                return
            still_waiting = [p for p in targets if self.awaiting_pong.get(p, False)]
            if still_waiting:
                print(f"[MQTT] ⚠ Heartbeat timeout — no pong from {still_waiting}, resolving anyway")
                for p in still_waiting:
                    self.awaiting_pong[p] = False
                alive_map = {pid: self.check_player_liveliness(pid) for pid in targets}
                self.bridge.heartbeat_resolved.emit(alive_map)

        t = threading.Thread(target=_timeout_resolver, daemon=True)
        t.start()

    def check_all_players_liveliness(self) -> Dict[int, bool]:
        """Return {player_id: is_alive} for all expected players."""
        targets = self._expected_player_ids()
        return {pid: self.check_player_liveliness(pid) for pid in targets}

    def all_pings_resolved(self, timeout_seconds: int = 10) -> bool:
        """Return True once the current ping cycle has settled."""
        now = time.time()
        targets = self._expected_player_ids()

        for pid in targets:
            if not self.awaiting_pong.get(pid, False):
                continue
            sent_at = self.last_heartbeat_sent.get(pid)
            if sent_at is None:
                self.awaiting_pong[pid] = False
                continue
            if (now - sent_at) > timeout_seconds:
                self.awaiting_pong[pid] = False

        return not any(self.awaiting_pong.get(pid, False) for pid in targets)

    # =====================================================================
    # LOCK PLAYER
    # =====================================================================

    def lock_player(self, player_id: int) -> None:
        """Publish hardware lock for the given player."""
        self._publish_lock(int(player_id))

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

        self._publish_lock(player_id)
        self.bridge.buzz_received.emit(ev)

    def _handle_answer(self, player_id: int, data: dict) -> None:
        # MQTT thread
        ans = str(data.get("answer", "")).strip().upper()
        ts_ms = int(data.get("t_ms", 0))
        recv_ms = int(time.time() * 1000)
        ev = AnswerEvent(player_id=player_id, answer=ans, timestamp_ms=ts_ms, server_received_ms=recv_ms)

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
        self._set_state(BuzzerState.IDLE)
        self._publish_reset()

    def unlock_buzzers(self) -> None:
        """Admin unlock: allow buzzes."""
        self.locked_player = None
        self._publish_reset()
        self._set_state(BuzzerState.ACTIVE)

    def mark_answer_wrong(self, player_id: int) -> None:
        """Eliminate player for this question and allow next attempt (if any).

        BUG FIX: previously _publish_reset() was called unconditionally, which
        sent a hardware RESET immediately after a wrong answer — clearing the
        lock before the engine had a chance to call unlock_buzzers() for the
        next cascade attempt.  Now we only reset when all attempts are truly
        exhausted; the engine drives the unlock for mid-question cascades.
        """
        self.eliminated_players.add(int(player_id))
        self.locked_player = None

        if self.attempt_count < self.max_attempts:
            # More attempts remain — stay in ACTIVE-ready state but do NOT
            # broadcast RESET yet.  unlock_buzzers() will fire next.
            self._set_state(BuzzerState.IDLE)
        else:
            # All attempts exhausted — release hardware and close the question.
            self._publish_reset()
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
    # INTERNAL HELPERS
    # =====================================================================

    def _expected_player_ids(self) -> List[int]:
        """Return the player IDs we consider expected for heartbeat purposes."""
        connected = self.get_connected_players(timeout_seconds=self.heartbeat_timeout * 2)
        if connected:
            return sorted(set(connected))
        return [1, 2, 3, 4]

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