"""
key_discovery.py
================
Run this script BEFORE configuring remote_config.py.

    python key_discovery.py

A small window will appear.  Press each button on your Rii i7 remote and
the terminal will print exactly which Qt.Key value was emitted.
Copy those values into remote_config.py.

Press Ctrl+C in the terminal or close the window to quit.
"""

import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class KeySniffer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rii i7 Key Discovery — press remote buttons")
        self.setMinimumSize(520, 260)
        self.setStyleSheet(
            "QWidget { background: #0d1b2a; }"
            "QLabel  { color: white; font-family: monospace; }"
        )

        self._last = QLabel("Press a button on the remote…")
        self._last.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #39FF14; padding: 10px;"
        )

        self._log = QLabel("")
        self._log.setStyleSheet(
            "font-size: 13px; color: rgba(255,255,255,0.7); padding: 6px;"
        )
        self._log.setWordWrap(True)

        hint = QLabel(
            "ℹ  Copy the Qt.Key_* values into remote_config.py\n"
            "   Close window or Ctrl+C to quit."
        )
        hint.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.4); padding: 6px;")

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.addWidget(hint)
        lay.addStretch()
        lay.addWidget(self._last)
        lay.addWidget(self._log)
        lay.addStretch()

        self._history: list[str] = []
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        text = event.text()

        # Try to find a human-readable Qt.Key name
        key_name = "UNKNOWN"
        for attr in dir(Qt.Key):
            if attr.startswith("Key_"):
                try:
                    if Qt.Key[attr].value == key:
                        key_name = f"Qt.Key.{attr}"
                        break
                except Exception:
                    pass

        mod_str = ""
        if mods != Qt.KeyboardModifier.NoModifier:
            mod_str = f"  modifiers={int(mods):#010x}"

        text_str = f'  text={text!r}' if text.strip() else ""
        line = f"key={key:#010x}  {key_name}{mod_str}{text_str}"

        print(f"[KEY] {line}")
        self._last.setText(f"Last: {key_name}")

        self._history.append(line)
        if len(self._history) > 8:
            self._history.pop(0)
        self._log.setText("\n".join(self._history))

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Rii i7 Key Discovery")
    w = KeySniffer()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()