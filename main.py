"""
Football Buzzer - Main Entry Point
MQTT Hardware Backend Only - No Simulations
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import get_config
from app.core.loaders import load_pack, create_demo_pack, PackError
from app.core.engine import GameEngine
from app.hardware.mqtt_buzzer import MQTTBuzzerBackend
from app.ui.screens.host_screen import HostScreen


def main():
    """Main entry point - MQTT Hardware Only"""
    cfg_app = get_config()
    pack_dir = cfg_app.packs_dir / cfg_app.default_pack_name

    app = QApplication(sys.argv)
    app.setApplicationName("Football Trivia Game")
    app.setOrganizationName("Football Trivia Game")

    # =========================================================================
    # LOAD QUESTION PACK
    # =========================================================================
    try:
        cfg, questions = load_pack(pack_dir)
        print("[OK] Loaded pack: {} ({} questions)".format(cfg.name, len(questions)))
    except PackError as e:
        print("[WARNING] Could not load pack: {}".format(e))
        print("[INFO] Creating demo pack...")
        
        demo_dir = cfg_app.packs_dir / "demo_pack"
        try:
            cfg, questions = create_demo_pack(demo_dir)
            print("[OK] Demo pack created with {} questions".format(len(questions)))
        except Exception as ex:
            print("[ERROR] Failed to create demo pack: {}".format(ex))
            
            # Emergency fallback
            from app.core.models import GameConfig, Question, Media
            from app.constants import MediaType
            
            cfg = GameConfig(
                name="Emergency Demo Pack",
                version=1,
                rounds=1,
                questions_per_round=3,
                timer_seconds=20,
                answer_seconds=8,
                shuffle_questions=False,
                question_files=[],
                pack_dir=Path.cwd(),
            )
            
            questions = [
                Question(
                    id="demo1",
                    round=1,
                    text="Who won the 2014 FIFA World Cup?",
                    options=["Germany", "Argentina", "Brazil", "France"],
                    correct_index=0,
                    media=Media(type=MediaType.NONE, path=None),
                ),
                Question(
                    id="demo2",
                    round=1,
                    text="Which player is known as 'CR7'?",
                    options=["Messi", "Ronaldo", "Neymar", "Mbappe"],
                    correct_index=1,
                    media=Media(type=MediaType.NONE, path=None),
                ),
                Question(
                    id="demo3",
                    round=1,
                    text="How many players per team in football?",
                    options=["9", "10", "11", "12"],
                    correct_index=2,
                    media=Media(type=MediaType.NONE, path=None),
                ),
            ]
        
        QMessageBox.information(
            None,
            "Demo Mode",
            "Could not load pack from:\n{}\n\n"
            "Reason:\n{}\n\n"
            "Starting with DEMO questions.\n"
            "Open Admin Dashboard (info button) to create your pack!".format(pack_dir, e),
        )

    # =========================================================================
    # INITIALIZE GAME ENGINE
    # =========================================================================
    try:
        engine = GameEngine(cfg, questions)
        print("[OK] Game engine initialized")
    except Exception as e:
        print("[ERROR] Failed to initialize game engine: {}".format(e))
        QMessageBox.critical(
            None,
            "Initialization Error",
            "Failed to initialize game engine:\n{}".format(e)
        )
        sys.exit(1)
    
    # =========================================================================
    # MQTT HARDWARE BACKEND - WAIT FOR BUZZER CONNECTIONS
    # =========================================================================
    print("\n" + "="*60)
    print("MQTT HARDWARE BACKEND INITIALIZATION")
    print("="*60)
    
    # Get broker configuration (you can make this configurable)
    MQTT_BROKER_HOST = "192.168.10.10"  # Change to your broker IP
    MQTT_BROKER_PORT = 1883
    
    print(f"Broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    print("Waiting for ESP32 buzzers to connect...")
    print("="*60 + "\n")
    
    # Create MQTT backend
    mqtt_backend = MQTTBuzzerBackend(
        broker_host=MQTT_BROKER_HOST,
        broker_port=MQTT_BROKER_PORT
    )
    
    # Try to connect to broker
    if not mqtt_backend.connect():
        QMessageBox.critical(
            None,
            "MQTT Connection Failed",
            f"Failed to connect to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}\n\n"
            "Please ensure:\n"
            "• MQTT broker is running\n"
            "• Network connection is active\n"
            "• Broker address is correct\n\n"
            "The application will now exit."
        )
        sys.exit(1)
    
    print("[OK] Connected to MQTT broker")
    
    # =========================================================================
    # CREATE APPLICATION WINDOW
    # =========================================================================
    try:
        from app.ui.app_window import AppWindow
        window = AppWindow(engine, mqtt_backend)
        window.show()
        print("[OK] Application window created and shown")
    except Exception as e:
        print("[ERROR] Failed to create window: {}".format(e))
        QMessageBox.critical(
            None,
            "Window Error",
            "Failed to create application window:\n{}".format(e)
        )
        mqtt_backend.disconnect()
        sys.exit(1)

    # =========================================================================
    # DISPLAY STARTUP STATUS
    # =========================================================================
    print("\n" + "="*60)
    print("APPLICATION READY")
    print("="*60)
    print("Waiting for ESP32 buzzers to connect...")
    print("Connect up to 4 buzzers (Player 1-4)")
    print("Each buzzer will light up with its color when connected")
    print("="*60 + "\n")

    # Start Qt event loop
    print("[INFO] Starting application event loop...")
    exit_code = app.exec()
    
    # Cleanup on exit
    print("[INFO] Shutting down...")
    mqtt_backend.disconnect()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[FATAL ERROR] Unhandled exception: {}".format(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)