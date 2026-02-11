"""
Main Application Window
Integrates GameEngine with MQTT Hardware Backend
"""

from PySide6.QtWidgets import QMainWindow, QMessageBox
from PySide6.QtCore import QTimer

from app.core.engine import GameEngine
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend
from app.ui.screens.host_screen import HostScreen
from app.ui.screens.admin_dashboard import AdminDashboard


class AppWindow(QMainWindow):
    """Main application window with MQTT hardware integration"""
    
    def __init__(self, engine: GameEngine, mqtt_backend: MQTTBuzzerBackend):
        super().__init__()
        self.setWindowTitle("Football Buzzer - Hardware Mode")
        self.setMinimumSize(1000, 600)

        self.engine = engine
        self.mqtt_backend = mqtt_backend
        self.admin_window = None

        # =====================================================================
        # CONNECT MQTT BACKEND TO ENGINE
        # =====================================================================
        
        # Set up MQTT callbacks to trigger engine events
        self.mqtt_backend.on_buzz_callback = self._on_mqtt_buzz
        self.mqtt_backend.on_answer_callback = self._on_mqtt_answer
        self.mqtt_backend.on_player_connected_callback = self._on_mqtt_player_connected
        self.mqtt_backend.on_player_disconnected_callback = self._on_mqtt_player_disconnected
        
        print("[OK] MQTT backend callbacks connected to engine")

        # =====================================================================
        # CREATE HOST SCREEN
        # =====================================================================
        
        self.host = HostScreen(engine=self.engine, mqtt_backend=self.mqtt_backend)
        
        # Replace help button with admin dashboard
        self.host.help_btn.clicked.disconnect() 
        self.host.help_btn.clicked.connect(self._show_admin_dashboard)
        
        self.setCentralWidget(self.host)
        
        # =====================================================================
        # MONITOR BUZZER CONNECTIONS
        # =====================================================================
        
        # Periodically check for disconnected players
        self.connection_monitor = QTimer()
        self.connection_monitor.timeout.connect(self._check_connections)
        self.connection_monitor.start(2000)  # Check every 2 seconds

    # =========================================================================
    # MQTT EVENT HANDLERS
    # =========================================================================
    
    def _on_mqtt_buzz(self, event):
        """Handle buzz from ESP32 hardware"""
        print(f"🔔 MQTT Buzz from Player {event.player_id} (latency: {event.latency_ms}ms)")
        
        # Forward to engine
        self.engine.on_buzz(
            buzzer_id=event.player_id,
            t_ms=event.timestamp_ms,
            received_ms=event.server_received_ms
        )
    
    def _on_mqtt_answer(self, event):
        """Handle answer from ESP32 hardware"""
        print(f"📝 MQTT Answer from Player {event.player_id}: {event.answer}")
        
        # Convert answer letter to index (A=0, B=1, C=2, D=3)
        answer_index = ord(event.answer.upper()) - ord('A')
        
        # Check if answer is correct
        question = self.engine.current_question()
        is_correct = (answer_index == question.correct_index)
        
        # Apply answer through engine
        self.engine.apply_answer(is_correct)
    
    def _on_mqtt_player_connected(self, player_id: int):
        """Handle ESP32 player connection"""
        print(f"✅ Player {player_id} CONNECTED")
        
        # Update UI to show connection
        if hasattr(self.host, '_on_buzzer_connected'):
            self.host._on_buzzer_connected(player_id, True)
    
    def _on_mqtt_player_disconnected(self, player_id: int):
        """Handle ESP32 player disconnection"""
        print(f"⚠️  Player {player_id} DISCONNECTED")
        
        # Update UI to show disconnection
        if hasattr(self.host, '_on_buzzer_connected'):
            self.host._on_buzzer_connected(player_id, False)

    # =========================================================================
    # CONNECTION MONITORING
    # =========================================================================
    
    def _check_connections(self):
        """Periodically check and update player connections"""
        connected_players = self.mqtt_backend.get_connected_players()
        
        # Update UI for all 4 possible players
        for player_id in range(1, 5):
            is_connected = player_id in connected_players
            if hasattr(self.host, '_on_buzzer_connected'):
                self.host._on_buzzer_connected(player_id, is_connected)

    # =========================================================================
    # ADMIN DASHBOARD
    # =========================================================================
    
    def _show_admin_dashboard(self):
        """Show the admin dashboard window"""
        if self.admin_window is None or not self.admin_window.isVisible():
            from app.core.models import GameConfig
            from pathlib import Path
            
            # Create config from current engine state
            temp_config = GameConfig(
                name="Current Game Pack",
                version=1,
                rounds=1,
                questions_per_round=len(self.engine.questions),
                timer_seconds=self.engine.cfg.timer_seconds,
                answer_seconds=self.engine.cfg.answer_seconds,
                shuffle_questions=self.engine.cfg.shuffle_questions,
                question_files=[],
                pack_dir=Path.cwd(),
                enable_cascading_attempts=self.engine.cfg.enable_cascading_attempts,
                reset_timer_each_attempt=self.engine.cfg.reset_timer_each_attempt,
                penalty_for_wrong=self.engine.cfg.penalty_for_wrong,
                bonus_for_speed=self.engine.cfg.bonus_for_speed,
            )
            
            self.admin_window = AdminDashboard(
                temp_config,
                self.engine.questions
            )
            
            # Connect signals
            self.admin_window.config_changed.connect(self._on_config_changed)
            self.admin_window.questions_changed.connect(self._on_questions_changed)
            
            self.admin_window.setWindowTitle("Admin Dashboard - Football Buzzer")
            self.admin_window.resize(1000, 800)
            self.admin_window.show()
        else:
            self.admin_window.raise_()
            self.admin_window.activateWindow()
    
    def _on_config_changed(self, new_config):
        """Handle config changes from admin dashboard"""
        self.engine.update_config(new_config)
        print(f"[OK] Config updated: {new_config.name}")
    
    def _on_questions_changed(self, new_questions):
        """Handle questions changes from admin dashboard"""
        self.engine.reload_questions(new_questions)
        print(f"[OK] Questions updated: {len(new_questions)} total")

    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    def closeEvent(self, event):
        """Clean shutdown"""
        print("\n[INFO] Shutting down application...")
        
        # Stop connection monitor
        if hasattr(self, 'connection_monitor'):
            self.connection_monitor.stop()
        
        # Disconnect MQTT
        try:
            if self.mqtt_backend:
                self.mqtt_backend.disconnect()
                print("[OK] MQTT backend disconnected")
        except Exception as e:
            print(f"[WARNING] Error disconnecting MQTT: {e}")
        
        # Close admin window
        if self.admin_window:
            self.admin_window.close()
        
        super().closeEvent(event)