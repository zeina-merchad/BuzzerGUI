# demo.py
# MQTT Quiz Buzzer GUI - ESP32 Hardware Controller
# Manages real ESP32 buzzers for quiz game with cascading attempts
import sys
import time
from dataclasses import asdict

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QSpinBox,
    QTextEdit, QHBoxLayout, QVBoxLayout, QGroupBox, QGridLayout
)


from mqtt_buzzer import MQTTBuzzerBackend, BuzzerState, BuzzEvent, AnswerEvent


# -----------------------------
# Thread-safe bridge (MQTT thread -> Qt UI thread)
# -----------------------------
class BackendBridge(QObject):
    log = Signal(str)
    state_changed = Signal(str)
    player_connected = Signal(int)
    player_disconnected = Signal(int)
    buzz = Signal(dict)    # BuzzEvent as dict
    answer = Signal(dict)  # AnswerEvent as dict


class DemoWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MQTT Quiz Buzzer - ESP32 Hardware Controller")
        self.resize(900, 600)

        self.bridge = BackendBridge()

        # Backend (created on demand)
        self.backend: MQTTBuzzerBackend | None = None

        # UI
        self.host_in = QLineEdit("192.168.10.10")
        self.port_in = QSpinBox()
        self.port_in.setRange(1, 65535)
        self.port_in.setValue(1883)

        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)

        self.state_lbl = QLabel("State: (not connected)")
        self.players_lbl = QLabel("Players: []")
        self.question_lbl = QLabel("Current Question: -")
        self.attempt_lbl = QLabel("Attempt: 0/0 | Locked: - | Eliminated: []")

        self.qid_in = QLineEdit("Q1")
        self.max_attempts_in = QSpinBox()
        self.max_attempts_in.setRange(1, 10)
        self.max_attempts_in.setValue(3)

        self.btn_start_q = QPushButton("Start Question (Unlock)")
        self.btn_end_q = QPushButton("End Question")
        self.btn_start_q.setEnabled(False)
        self.btn_end_q.setEnabled(False)

        # Answer evaluation controls (for host)
        self.btn_mark_wrong = None  # Created in _build_layout
        self.btn_mark_correct = None  # Created in _build_layout

        # Log
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        self._build_layout()
        self._wire()

        # Status poller
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(500)  # 2x / sec
        self.poll_timer.timeout.connect(self._poll_status)

        # Bridge -> UI
        self.bridge.log.connect(self._append_log)
        self.bridge.state_changed.connect(self._on_state)
        self.bridge.player_connected.connect(self._on_player_connected)
        self.bridge.player_disconnected.connect(self._on_player_disconnected)
        self.bridge.buzz.connect(self._on_buzz)
        self.bridge.answer.connect(self._on_answer)

    def _build_layout(self):
        root = QVBoxLayout(self)

        # Connection box
        conn = QGroupBox("Connection")
        g = QGridLayout(conn)
        g.addWidget(QLabel("Broker Host:"), 0, 0)
        g.addWidget(self.host_in, 0, 1)
        g.addWidget(QLabel("Port:"), 0, 2)
        g.addWidget(self.port_in, 0, 3)
        g.addWidget(self.btn_connect, 0, 4)
        g.addWidget(self.btn_disconnect, 0, 5)

        # Status box
        status = QGroupBox("Status")
        s = QVBoxLayout(status)
        s.addWidget(self.state_lbl)
        s.addWidget(self.question_lbl)
        s.addWidget(self.players_lbl)
        s.addWidget(self.attempt_lbl)

        # Question control
        qc = QGroupBox("Question Control")
        ql = QGridLayout(qc)
        ql.addWidget(QLabel("Question ID:"), 0, 0)
        ql.addWidget(self.qid_in, 0, 1)
        ql.addWidget(QLabel("Max Attempts:"), 0, 2)
        ql.addWidget(self.max_attempts_in, 0, 3)
        ql.addWidget(self.btn_start_q, 0, 4)
        ql.addWidget(self.btn_end_q, 0, 5)

        # Mark answer controls
        mark = QGroupBox("Answer Evaluation (Host Controls)")
        ml = QGridLayout(mark)
        ml.addWidget(QLabel("Player ID:"), 0, 0)
        
        self.eval_player_in = QSpinBox()
        self.eval_player_in.setRange(1, 8)
        self.eval_player_in.setValue(1)
        ml.addWidget(self.eval_player_in, 0, 1)
        
        self.btn_mark_wrong = QPushButton("❌ Mark Wrong (unlock next)")
        self.btn_mark_correct = QPushButton("✅ Mark Correct (end question)")
        ml.addWidget(self.btn_mark_wrong, 1, 0, 1, 2)
        ml.addWidget(self.btn_mark_correct, 2, 0, 1, 2)
        
        for b in (self.btn_mark_wrong, self.btn_mark_correct):
            b.setEnabled(False)

        # Log
        top = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(conn)
        left.addWidget(status)
        left.addWidget(qc)
        left.addWidget(mark)
        top.addLayout(left, 1)

        log_group = QGroupBox("Log")
        ll = QVBoxLayout(log_group)
        ll.addWidget(self.log_box)
        top.addWidget(log_group, 1)

        root.addLayout(top)

    def _wire(self):
        self.btn_connect.clicked.connect(self._connect_backend)
        self.btn_disconnect.clicked.connect(self._disconnect_backend)

        self.btn_start_q.clicked.connect(self._start_question)
        self.btn_end_q.clicked.connect(self._end_question)

        self.btn_mark_wrong.clicked.connect(self._mark_wrong)
        self.btn_mark_correct.clicked.connect(self._mark_correct)

    # -----------------------------
    # Backend control
    # -----------------------------
    def _connect_backend(self):
        host = self.host_in.text().strip()
        port = int(self.port_in.value())

        self.backend = MQTTBuzzerBackend(broker_host=host, broker_port=port)

        # Attach callbacks -> bridge signals (thread-safe)
        self.backend.on_buzz_callback = lambda ev: self.bridge.buzz.emit(asdict(ev))
        self.backend.on_answer_callback = lambda ev: self.bridge.answer.emit(asdict(ev))
        self.backend.on_player_connected_callback = lambda pid: self.bridge.player_connected.emit(pid)
        self.backend.on_state_change_callback = lambda st: self.bridge.state_changed.emit(st.value)

        ok = self.backend.connect()
        if ok:
            self.bridge.log.emit(f"✅ Connected to {host}:{port}")
            self.bridge.log.emit("📡 Waiting for ESP32 buzzers to connect...")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)

            self.btn_start_q.setEnabled(True)
            self.btn_end_q.setEnabled(True)
            self.btn_mark_wrong.setEnabled(True)
            self.btn_mark_correct.setEnabled(True)

            self.poll_timer.start()
        else:
            self.bridge.log.emit("❌ Connection failed. Check broker IP/port and mosquitto status.")
            self.backend = None

    def _disconnect_backend(self):
        if self.backend:
            self.backend.disconnect()
            self.bridge.log.emit("🧯 Disconnected")
        self.backend = None

        self.poll_timer.stop()

        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)

        self.btn_start_q.setEnabled(False)
        self.btn_end_q.setEnabled(False)
        self.btn_mark_wrong.setEnabled(False)
        self.btn_mark_correct.setEnabled(False)

        self.state_lbl.setText("State: (not connected)")
        self.players_lbl.setText("Players: []")
        self.question_lbl.setText("Current Question: -")
        self.attempt_lbl.setText("Attempt: 0/0 | Locked: - | Eliminated: []")

    def _start_question(self):
        if not self.backend:
            return
        qid = self.qid_in.text().strip() or "Q1"
        max_attempts = int(self.max_attempts_in.value())
        self.backend.start_question(question_id=qid, max_attempts=max_attempts)
        self.bridge.log.emit(f"🎯 start_question({qid}, max_attempts={max_attempts})")

    def _end_question(self):
        if not self.backend:
            return
        self.backend.end_question()
        self.bridge.log.emit("🏁 end_question()")

    def _mark_wrong(self):
        if not self.backend:
            return
        pid = int(self.eval_player_in.value())
        self.backend.mark_answer_wrong(pid)
        self.bridge.log.emit(f"❌ Marked Player {pid} WRONG")

    def _mark_correct(self):
        if not self.backend:
            return
        pid = int(self.eval_player_in.value())
        self.backend.mark_answer_correct(pid)
        self.bridge.log.emit(f"✅ Marked Player {pid} CORRECT")

    # -----------------------------
    # Poll status
    # -----------------------------
    def _poll_status(self):
        if not self.backend:
            return
        st = self.backend.get_status()

        self.state_lbl.setText(f"State: {st['state']} (connected={st['connected']})")
        self.question_lbl.setText(f"Current Question: {st['current_question']}")
        self.players_lbl.setText(f"Players: {st['connected_players']}")

        att = st.get("attempt_info", {}) or {}
        self.attempt_lbl.setText(
            f"Attempt: {att.get('attempt_count', 0)}/{att.get('max_attempts', 0)} | "
            f"Locked: {att.get('locked_player', None)} | "
            f"Eliminated: {att.get('eliminated_players', [])}"
        )

    # -----------------------------
    # Bridge slots
    # -----------------------------
    @Slot(str)
    def _append_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_box.append(f"[{ts}] {msg}")

    @Slot(str)
    def _on_state(self, st: str):
        self._append_log(f"🔄 State → {st}")

    @Slot(int)
    def _on_player_connected(self, pid: int):
        self._append_log(f"🟢 Player {pid} connected")

    @Slot(int)
    def _on_player_disconnected(self, pid: int):
        self._append_log(f"🔴 Player {pid} disconnected")

    @Slot(dict)
    def _on_buzz(self, ev: dict):
        # ev keys: player_id, timestamp_ms, server_received_ms
        # Note: Latency calculation disabled (ESP32 uses millis() not Unix time)
        self._append_log(f"🔔 BUZZ P{ev['player_id']}")

    @Slot(dict)
    def _on_answer(self, ev: dict):
        self._append_log(f"📝 ANSWER P{ev['player_id']}: {ev['answer']}")


def main():
    app = QApplication(sys.argv)
    w = DemoWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()