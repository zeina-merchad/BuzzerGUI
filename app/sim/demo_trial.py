import json
import random
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, List

import paho.mqtt.client as mqtt


# ----------------------------
# Config
# ----------------------------
BROKER_HOST = "192.168.10.10"
BROKER_PORT = 1883

N_PLAYERS = 4                # how many ESP32 clients to simulate
MAX_ATTEMPTS = 3             # cascading attempts
QUESTION_ID = "SIM_Q1"

# Behavior tuning
BUZZ_DELAY_RANGE = (0.10, 0.80)     # players will buzz after reset within this delay range (seconds)
ANSWER_DELAY_RANGE = (0.20, 0.80)   # locked player answers after this delay range (seconds)

# Choose correctness pattern:
# - Set CORRECT_ON_ATTEMPT = 1..MAX_ATTEMPTS to force a correct answer on that attempt
# - Or set to None for random correctness
CORRECT_ON_ATTEMPT: Optional[int] = 2


# ----------------------------
# MQTT Topics
# ----------------------------
def topic_buzz(pid: int) -> str:
    return f"fbz/buzzer/{pid}/buzz"

def topic_answer(pid: int) -> str:
    return f"fbz/buzzer/{pid}/answer"

TOPIC_RESET = "fbz/game/reset"
TOPIC_LOCK = "fbz/game/lock"


# ----------------------------
# ESP32 Simulator
# ----------------------------
@dataclass
class ESP32SimState:
    locked: bool = False
    winner: bool = False
    last_reset_ts: float = 0.0


class ESP32Sim:
    """
    Simulates an ESP32 buzzer:
      - subscribes to fbz/game/reset + fbz/game/lock
      - after reset, waits random delay then publishes buzz (if not locked)
      - if it becomes winner, publishes an answer after random delay
    """
    def __init__(self, player_id: int, host: str, port: int):
        self.player_id = player_id
        self.host = host
        self.port = port
        self.state = ESP32SimState()
        self.client = mqtt.Client(client_id=f"esp32_sim_{player_id}", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()
        self._thread = threading.Thread(target=self._run_logic, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    # MQTT callbacks
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[ESP{self.player_id}] connected ✅")
            client.subscribe(TOPIC_RESET)
            client.subscribe(TOPIC_LOCK)
        else:
            print(f"[ESP{self.player_id}] connect failed rc={rc} ❌")

    def _on_disconnect(self, client, userdata, rc):
        print(f"[ESP{self.player_id}] disconnected (rc={rc})")

    def _on_message(self, client, userdata, msg):
        if msg.topic == TOPIC_RESET:
            # unlock on reset
            self.state.locked = False
            self.state.winner = False
            self.state.last_reset_ts = time.time()
            print(f"[ESP{self.player_id}] <- RESET (unlock)")
        elif msg.topic == TOPIC_LOCK:
            # payload is player_id as text
            try:
                winner_id = int(msg.payload.decode().strip() or "0")
            except Exception:
                winner_id = 0
            self.state.locked = True
            self.state.winner = (winner_id == self.player_id)
            if self.state.winner:
                print(f"[ESP{self.player_id}] <- LOCK (I WON 🟢)")
            else:
                print(f"[ESP{self.player_id}] <- LOCK (locked 🔒) winner=P{winner_id}")

    # Behavior loop
    def _run_logic(self):
        # Keep reacting after reset events
        last_handled_reset = 0.0
        while not self._stop.is_set():
            time.sleep(0.02)

            # After a reset, each ESP tries to buzz once (if not already locked)
            if self.state.last_reset_ts > last_handled_reset:
                last_handled_reset = self.state.last_reset_ts

                # schedule a buzz attempt
                delay = random.uniform(*BUZZ_DELAY_RANGE)
                threading.Thread(target=self._delayed_buzz, args=(delay,), daemon=True).start()

            # If winner, schedule answer
            if self.state.winner:
                # winner answers once per lock
                self.state.winner = False
                delay = random.uniform(*ANSWER_DELAY_RANGE)
                threading.Thread(target=self._delayed_answer, args=(delay,), daemon=True).start()

    def _delayed_buzz(self, delay_s: float):
        time.sleep(delay_s)
        if self._stop.is_set():
            return
        # If locked, ignore
        if self.state.locked:
            return
        payload = {
            "id": self.player_id,
            "t_ms": int(time.time() * 1000)
        }
        self.client.publish(topic_buzz(self.player_id), json.dumps(payload))
        print(f"[ESP{self.player_id}] -> BUZZ (after {delay_s:.2f}s)")

    def _delayed_answer(self, delay_s: float):
        time.sleep(delay_s)
        if self._stop.is_set():
            return
        # send random answer
        ans = random.choice(["A", "B", "C", "D"])
        payload = {
            "id": self.player_id,
            "answer": ans,
            "t_ms": int(time.time() * 1000)
        }
        self.client.publish(topic_answer(self.player_id), json.dumps(payload))
        print(f"[ESP{self.player_id}] -> ANSWER {ans} (after {delay_s:.2f}s)")


# ----------------------------
# Host (Pi) Simulator
# ----------------------------
class HostSim:
    """
    Subscribes to buzz & answer topics.
    Enforces cascading attempts (MAX_ATTEMPTS).
    Publishes lock/reset just like backend.
    Marks answers wrong/correct based on CORRECT_ON_ATTEMPT.
    """
    def __init__(self, host: str, port: int, n_players: int):
        self.host = host
        self.port = port
        self.n_players = n_players

        self.client = mqtt.Client(client_id="host_sim", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self.attempt = 0
        self.locked_player: Optional[int] = None
        self.eliminated: set[int] = set()
        self.running = False

        self._stop = threading.Event()

    def start(self):
        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()

    def stop(self):
        self._stop.set()
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def start_question(self):
        print("\n" + "=" * 60)
        print(f"[HOST] START QUESTION {QUESTION_ID} | max_attempts={MAX_ATTEMPTS}")
        print("=" * 60)
        self.attempt = 0
        self.locked_player = None
        self.eliminated.clear()
        self.running = True
        self.client.publish(TOPIC_RESET, "")
        print("[HOST] -> RESET (unlock all)")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[HOST] connected ✅")
            client.subscribe("fbz/buzzer/+/buzz")
            client.subscribe("fbz/buzzer/+/answer")
        else:
            print(f"[HOST] connect failed rc={rc} ❌")

    def _on_message(self, client, userdata, msg):
        if self._stop.is_set():
            return

        if msg.topic.endswith("/buzz"):
            self._handle_buzz(msg)
        elif msg.topic.endswith("/answer"):
            self._handle_answer(msg)

    def _handle_buzz(self, msg):
        if not self.running:
            return

        try:
            data = json.loads(msg.payload.decode())
            pid = int(data.get("id", 0))
            t_ms = int(data.get("t_ms", 0))
        except Exception:
            return

        # Only accept if not locked
        if self.locked_player is not None:
            return

        # Enforce eliminated
        if pid in self.eliminated:
            print(f"[HOST] buzz ignored: P{pid} eliminated")
            return

        # Enforce attempt limit
        if self.attempt >= MAX_ATTEMPTS:
            print("[HOST] buzz ignored: max attempts reached")
            return

        # Accept buzz
        self.attempt += 1
        self.locked_player = pid
        recv_ms = int(time.time() * 1000)
        latency = recv_ms - t_ms
        print(f"[HOST] <- BUZZ P{pid} | attempt {self.attempt}/{MAX_ATTEMPTS} | latency={latency}ms")

        # Publish lock
        self.client.publish(TOPIC_LOCK, str(pid))
        print(f"[HOST] -> LOCK P{pid}")

    def _handle_answer(self, msg):
        if not self.running:
            return

        try:
            data = json.loads(msg.payload.decode())
            pid = int(data.get("id", 0))
            ans = str(data.get("answer", "")).upper()
        except Exception:
            return

        # Only locked player can answer
        if pid != self.locked_player:
            return

        print(f"[HOST] <- ANSWER from P{pid}: {ans}")

        # Decide correctness
        is_correct = False
        if CORRECT_ON_ATTEMPT is None:
            is_correct = random.random() < 0.35
        else:
            is_correct = (self.attempt == CORRECT_ON_ATTEMPT)

        if is_correct:
            print(f"[HOST] ✅ CORRECT on attempt {self.attempt} (P{pid}) — END")
            self.running = False
            # (backend usually goes to RESULT_SHOWN; we just stop)
            return

        # Wrong answer
        print(f"[HOST] ❌ WRONG (P{pid}) — eliminate and unlock next attempt")
        self.eliminated.add(pid)
        self.locked_player = None

        if self.attempt < MAX_ATTEMPTS:
            self.client.publish(TOPIC_RESET, "")
            print("[HOST] -> RESET (next attempt)")
        else:
            print("[HOST] 🏁 max attempts reached — END")
            self.running = False


# ----------------------------
# Main
# ----------------------------
def main():
    print(f"Broker: {BROKER_HOST}:{BROKER_PORT}")
    print(f"Sim players: {N_PLAYERS} | max_attempts={MAX_ATTEMPTS}")

    # Start host simulator
    host = HostSim(BROKER_HOST, BROKER_PORT, N_PLAYERS)
    host.start()

    # Start ESP32 simulators
    esps: List[ESP32Sim] = []
    for pid in range(1, N_PLAYERS + 1):
        e = ESP32Sim(pid, BROKER_HOST, BROKER_PORT)
        e.start()
        esps.append(e)

    # Give everything a moment to connect
    time.sleep(1.0)

    # Start the question
    host.start_question()

    # Run until question ends
    try:
        while True:
            time.sleep(0.2)
            if not host.running:
                print("\n[SIM] finished ✅")
                break
    except KeyboardInterrupt:
        print("\n[SIM] interrupted")

    # Cleanup
    for e in esps:
        e.stop()
    host.stop()


if __name__ == "__main__":
    main()
