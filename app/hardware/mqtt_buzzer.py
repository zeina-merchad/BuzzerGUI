"""
Enhanced MQTT Buzzer Backend with Cascading Attempts Support
Integrates ESP32 hardware buzzers with the cascading points system
"""

import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
from enum import Enum


class BuzzerState(Enum):
    """Buzzer system states"""
    IDLE = "idle"                    # Waiting for question
    ACTIVE = "active"                # Question active, accepting buzzes
    LOCKED = "locked"                # Someone buzzed, waiting for answer
    ANSWERED = "answered"            # Answer received
    RESULT_SHOWN = "result_shown"    # Result displayed


@dataclass
class BuzzEvent:
    """Represents a buzzer press"""
    player_id: int
    timestamp_ms: int
    server_received_ms: int
    
    @property
    def latency_ms(self) -> int:
        """Calculate network latency"""
        return self.server_received_ms - self.timestamp_ms


@dataclass
class AnswerEvent:
    """Represents an answer submission"""
    player_id: int
    answer: str
    timestamp_ms: int
    server_received_ms: int


class MQTTBuzzerBackend:
    """
    MQTT Backend for ESP32 Buzzers with Cascading Attempts
    
    Features:
    - Tracks multiple attempts (up to 3 players)
    - Manages buzzer locks and resets
    - Real-time connection monitoring
    - Latency tracking
    - Event callbacks for integration
    """
    
    def __init__(self, broker_host: str = "192.168.10.10", broker_port: int = 1883):
        self.broker_host = broker_host
        self.broker_port = broker_port
        
        # MQTT client
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # Connection state
        self.connected = False
        self.connection_time = None
        
        # Game state
        self.state = BuzzerState.IDLE
        self.current_question_id = None
        self.max_attempts = 3
        self.attempt_count = 0
        self.locked_player = None
        
        # Buzz tracking for cascading attempts
        self.buzz_order: List[BuzzEvent] = []  # Order players buzzed in
        self.answered_players: Dict[int, AnswerEvent] = {}  # Players who answered
        self.eliminated_players: set = set()  # Players who answered wrong
        
        # Player connection tracking
        self.connected_players: Dict[int, float] = {}  # player_id -> last_seen_time
        self.player_latency: Dict[int, List[int]] = {}  # player_id -> [latencies]
        
        # Event callbacks
        self.on_buzz_callback: Optional[Callable[[BuzzEvent], None]] = None
        self.on_answer_callback: Optional[Callable[[AnswerEvent], None]] = None
        self.on_player_connected_callback: Optional[Callable[[int], None]] = None
        self.on_player_disconnected_callback: Optional[Callable[[int], None]] = None
        self.on_state_change_callback: Optional[Callable[[BuzzerState], None]] = None
    
    # ========================================================================
    # CONNECTION MANAGEMENT
    # ========================================================================
    
    def connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            print(f"🔌 Connecting to MQTT broker at {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
            # Wait for connection (max 5 seconds)
            timeout = time.time() + 5
            while not self.connected and time.time() < timeout:
                time.sleep(0.1)
            
            if self.connected:
                print("✓ MQTT backend connected successfully!")
                return True
            else:
                print("✗ MQTT connection timeout")
                return False
                
        except Exception as e:
            print(f"✗ MQTT connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.connected:
            print("🔌 Disconnecting from MQTT broker...")
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            self.connection_time = time.time()
            print("✓ MQTT broker connected (rc=0)")
            
            # Subscribe to all buzzer topics
            client.subscribe("fbz/buzzer/+/buzz")
            client.subscribe("fbz/buzzer/+/answer")
            print("✓ Subscribed to buzzer topics")
        else:
            print(f"✗ MQTT connection failed (rc={rc})")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        if rc != 0:
            print(f"⚠ MQTT unexpected disconnect (rc={rc})")
        else:
            print("✓ MQTT disconnected cleanly")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message callback - handles all incoming messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode()
            
            print(f"\n📥 RAW MESSAGE: {topic}")
            print(f"   Payload: {payload}")
            
            # Parse JSON payload
            data = json.loads(payload)
            player_id = data.get('id')
            
            if not player_id:
                print(f"⚠ Message missing player ID: {topic}")
                return
            
            # Track player connection
            self._update_player_connection(player_id)
            
            # Handle buzz events (check for exact ending to avoid matching "buzzer")
            if topic.endswith("/buzz"):
                print(f"   → Processing as BUZZ event")
                self._handle_buzz(player_id, data)
            
            # Handle answer events
            elif topic.endswith("/answer"):
                print(f"   → Processing as ANSWER event")
                self._handle_answer(player_id, data)
            else:
                print(f"   → Unknown topic type")
                
        except json.JSONDecodeError:
            print(f"⚠ Invalid JSON in message: {msg.payload}")
        except Exception as e:
            print(f"⚠ Error processing message: {e}")
            import traceback
            traceback.print_exc()
    
    # ========================================================================
    # PLAYER CONNECTION TRACKING
    # ========================================================================
    
    def _update_player_connection(self, player_id: int):
        """Update player last-seen time"""
        current_time = time.time()
        was_connected = player_id in self.connected_players
        
        self.connected_players[player_id] = current_time
        
        if not was_connected and self.on_player_connected_callback:
            print(f"✓ Player {player_id} CONNECTED")
            self.on_player_connected_callback(player_id)
    
    def get_connected_players(self, timeout_seconds: int = 60) -> List[int]:
        """Get list of currently connected players"""
        current_time = time.time()
        connected = []
        
        for player_id, last_seen in self.connected_players.items():
            if current_time - last_seen < timeout_seconds:
                connected.append(player_id)
        
        return sorted(connected)
    
    def is_player_connected(self, player_id: int, timeout_seconds: int = 60) -> bool:
        """Check if a specific player is connected"""
        if player_id not in self.connected_players:
            return False
        
        last_seen = self.connected_players[player_id]
        return (time.time() - last_seen) < timeout_seconds
    
    def get_player_latency(self, player_id: int) -> Optional[float]:
        """Get average latency for a player (in ms)"""
        if player_id not in self.player_latency:
            return None
        
        latencies = self.player_latency[player_id]
        if not latencies:
            return None
        
        # Return average of last 10 measurements
        recent = latencies[-10:]
        return sum(recent) / len(recent)
    
    # ========================================================================
    # BUZZ HANDLING - CASCADING ATTEMPTS
    # ========================================================================
    
    def _handle_buzz(self, player_id: int, data: dict):
        """Handle buzzer press with cascading attempts logic"""
        timestamp_ms = data.get('t_ms', 0)
        server_received_ms = int(time.time() * 1000)
        
        buzz_event = BuzzEvent(
            player_id=player_id,
            timestamp_ms=timestamp_ms,
            server_received_ms=server_received_ms
        )
        
        # Latency tracking disabled - ESP32 sends millis() not Unix time
        # (Typical LAN latency is <50ms anyway)
        
        print(f"\n🔔 BUZZ from Player {player_id}")
        
        # Check if buzz is valid
        if self.state != BuzzerState.ACTIVE:
            print(f"  ⚠ Buzz rejected: State is {self.state.value}, not ACTIVE")
            return
        
        if player_id in self.eliminated_players:
            print(f"  ⚠ Buzz rejected: Player {player_id} already eliminated")
            return
        
        if self.attempt_count >= self.max_attempts:
            print(f"  ⚠ Buzz rejected: Max attempts ({self.max_attempts}) reached")
            return
        
        # Accept the buzz
        self.buzz_order.append(buzz_event)
        self.attempt_count += 1
        self.locked_player = player_id
        
        print(f"  ✓ Buzz accepted! Attempt {self.attempt_count}/{self.max_attempts}")
        print(f"  ✓ Player {player_id} locked in")
        
        # Lock the game for this player
        self._change_state(BuzzerState.LOCKED)
        self._publish_lock(player_id)
        
        # Trigger callback
        if self.on_buzz_callback:
            self.on_buzz_callback(buzz_event)
    
    def _handle_answer(self, player_id: int, data: dict):
        """Handle answer submission"""
        answer = data.get('answer', '').upper()
        timestamp_ms = data.get('t_ms', 0)
        server_received_ms = int(time.time() * 1000)
        
        answer_event = AnswerEvent(
            player_id=player_id,
            answer=answer,
            timestamp_ms=timestamp_ms,
            server_received_ms=server_received_ms
        )
        
        print(f"\n📝 ANSWER from Player {player_id}: {answer}")
        print(f"   Current state: {self.state.value}")
        print(f"   Locked player: {self.locked_player}")
        print(f"   Already answered: {player_id in self.answered_players}")
        
        # Check if answer is valid
        if self.state != BuzzerState.LOCKED:
            print(f"  ❌ REJECTED: State is {self.state.value}, need LOCKED")
            return
        
        if player_id != self.locked_player:
            print(f"  ❌ REJECTED: Player {player_id} not locked (locked player is {self.locked_player})")
            return
        
        if player_id in self.answered_players:
            print(f"  ❌ REJECTED: Player {player_id} already answered")
            return
        
        # Accept the answer
        self.answered_players[player_id] = answer_event
        self._change_state(BuzzerState.ANSWERED)
        
        print(f"  ✅ ANSWER ACCEPTED from Player {player_id}: {answer}")
        
        # Trigger callback
        if self.on_answer_callback:
            self.on_answer_callback(answer_event)
    
    # ========================================================================
    # GAME CONTROL - PUBLIC API
    # ========================================================================
    
    def start_question(self, question_id: str, max_attempts: int = 3):
        """Start a new question - unlock buzzers"""
        print(f"\n{'='*50}")
        print(f"🎯 NEW QUESTION: {question_id}")
        print(f"   Max attempts: {max_attempts}")
        print(f"{'='*50}\n")
        
        self.current_question_id = question_id
        self.max_attempts = max_attempts
        self.attempt_count = 0
        self.locked_player = None
        
        # Clear tracking
        self.buzz_order.clear()
        self.answered_players.clear()
        self.eliminated_players.clear()
        
        # Unlock all buzzers
        self._publish_reset()
        self._change_state(BuzzerState.ACTIVE)
    
    def mark_answer_wrong(self, player_id: int):
        """Mark a player's answer as wrong - allow next attempt"""
        print(f"✗ Player {player_id} answered WRONG")
        
        self.eliminated_players.add(player_id)
        self.locked_player = None
        
        if self.attempt_count < self.max_attempts:
            print(f"  → Unlocking for next attempt ({self.attempt_count}/{self.max_attempts})")
            self._publish_reset()
            self._change_state(BuzzerState.ACTIVE)
        else:
            print(f"  → Max attempts reached, question ends")
            self._change_state(BuzzerState.RESULT_SHOWN)
    
    def mark_answer_correct(self, player_id: int):
        """Mark a player's answer as correct - question ends"""
        print(f"✓ Player {player_id} answered CORRECT!")
        self._change_state(BuzzerState.RESULT_SHOWN)
    
    def end_question(self):
        """End the current question"""
        print(f"\n🏁 Question ended")
        print(f"   Total attempts: {self.attempt_count}")
        print(f"   Players answered: {len(self.answered_players)}")
        
        self._change_state(BuzzerState.IDLE)
        self.current_question_id = None
    
    def get_buzz_order(self) -> List[int]:
        """Get the order players buzzed in"""
        return [buzz.player_id for buzz in self.buzz_order]
    
    def get_attempt_info(self) -> dict:
        """Get current attempt information"""
        return {
            'attempt_count': self.attempt_count,
            'max_attempts': self.max_attempts,
            'buzz_order': self.get_buzz_order(),
            'eliminated_players': list(self.eliminated_players),
            'locked_player': self.locked_player,
            'state': self.state.value
        }
    
    # ========================================================================
    # MQTT PUBLISHING
    # ========================================================================
    
    def _publish_lock(self, player_id: int):
        """Lock game for specific player"""
        self.client.publish("fbz/game/lock", str(player_id))
        print(f"  📤 Published lock for Player {player_id}")
    
    def _publish_reset(self):
        """Reset/unlock game for new question or next attempt"""
        self.client.publish("fbz/game/reset", "")
        print(f"  📤 Published reset (unlock)")
    
    def _change_state(self, new_state: BuzzerState):
        """Change backend state"""
        old_state = self.state
        self.state = new_state
        print(f"  🔄 State: {old_state.value} → {new_state.value}")
        
        if self.on_state_change_callback:
            self.on_state_change_callback(new_state)
    
    # ========================================================================
    # STATUS & UTILITIES
    # ========================================================================
    
    def get_status(self) -> dict:
        """Get complete backend status"""
        return {
            'connected': self.connected,
            'connection_time': self.connection_time,
            'state': self.state.value,
            'current_question': self.current_question_id,
            'connected_players': self.get_connected_players(),
            'attempt_info': self.get_attempt_info(),
            'player_latencies': {
                pid: self.get_player_latency(pid) 
                for pid in self.get_connected_players()
            }
        }
    
    def print_status(self):
        """Print formatted status"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print("MQTT BUZZER BACKEND STATUS")
        print("="*60)
        print(f"Connected:        {status['connected']}")
        print(f"State:            {status['state']}")
        print(f"Current Question: {status['current_question']}")
        print(f"Attempt:          {status['attempt_info']['attempt_count']}/{status['attempt_info']['max_attempts']}")
        print(f"\nConnected Players: {status['connected_players']}")
        
        if status['player_latencies']:
            print(f"\nPlayer Latencies:")
            for pid, latency in status['player_latencies'].items():
                if latency:
                    print(f"  Player {pid}: {latency:.1f}ms")
        
        print("="*60 + "\n")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Create backend
    backend = MQTTBuzzerBackend()
    
    # Set up callbacks for demonstration
    def on_buzz(event: BuzzEvent):
        print(f"  → Callback: Buzz from Player {event.player_id}")
    
    def on_answer(event: AnswerEvent):
        print(f"  → Callback: Answer '{event.answer}' from Player {event.player_id}")
    
    backend.on_buzz_callback = on_buzz
    backend.on_answer_callback = on_answer
    
    # Connect
    if not backend.connect():
        print("Failed to connect!")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("MQTT BACKEND READY - Real ESP32 Hardware")
    print("="*60)
    print("Commands:")
    print("  start     - Start new question")
    print("  wrong <N> - Mark player N wrong")
    print("  correct <N> - Mark player N correct")
    print("  end       - End current question")
    print("  status    - Show status")
    print("  quit      - Exit")
    print("\nPhysical ESP32 buzzers will send buzz/answer events")
    print("="*60 + "\n")
    
    try:
        while True:
            cmd = input("> ").strip().lower().split()
            
            if not cmd:
                continue
            
            if cmd[0] == "start":
                qid = input("Question ID (or press Enter for 'Q1'): ").strip() or "Q1"
                max_att = input("Max attempts (or press Enter for 3): ").strip() or "3"
                backend.start_question(qid, max_attempts=int(max_att))
            
            elif cmd[0] == "wrong" and len(cmd) > 1:
                backend.mark_answer_wrong(int(cmd[1]))
            
            elif cmd[0] == "correct" and len(cmd) > 1:
                backend.mark_answer_correct(int(cmd[1]))
            
            elif cmd[0] == "end":
                backend.end_question()
            
            elif cmd[0] == "status":
                backend.print_status()
            
            elif cmd[0] in ("quit", "exit", "q"):
                break
            
            else:
                print(f"Unknown command: {cmd[0]}")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted!")
    
    finally:
        backend.disconnect()
        print("Goodbye!")