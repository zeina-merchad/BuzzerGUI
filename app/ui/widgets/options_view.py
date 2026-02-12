from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QHBoxLayout


class OptionsView(QWidget):
    def __init__(self):
        super().__init__()
        self._labels = []
        self._containers = []
        self._eliminated = set()

        grid = QGridLayout(self)
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)

        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        letters = ["A", "B", "C", "D"]
        border_colors = ["#39FF14", "#39FF14", "#39FF14", "#39FF14"]

        for i, (row, col) in enumerate(positions):
            container = QWidget()
            container.setMinimumHeight(80)
            container.setMaximumHeight(120)

            container.setStyleSheet(
                f"QWidget {{ "
                f"background: rgba(20, 30, 45, 0.9); "
                f"border-left: 5px solid {border_colors[i]}; "
                f"border-top: 2px solid rgba(100, 100, 100, 0.3); "
                f"border-right: 2px solid rgba(100, 100, 100, 0.3); "
                f"border-bottom: 2px solid rgba(100, 100, 100, 0.3); "
                f"border-radius: 8px; "
                f"}}"
            )

            layout = QHBoxLayout(container)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(12)

            letter_label = QLabel(f"{letters[i]}:")
            letter_label.setStyleSheet(
                "font-size: 18px; font-weight: 900; color: white; "
                "background: transparent; border: none;"
            )
            letter_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            letter_label.setFixedWidth(30)

            text_label = QLabel("")
            text_label.setWordWrap(True)
            text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            text_label.setStyleSheet(
                "font-size: 16px; font-weight: 700; color: white; "
                "background: transparent; border: none;"
            )

            layout.addWidget(letter_label)
            layout.addWidget(text_label, stretch=1)

            self._labels.append(text_label)
            self._containers.append(container)
            grid.addWidget(container, row, col)

    def set_options(self, options: list[str]):
        # ✅ FIX: every new question should clear eliminated styles
        self.reset_eliminated()

        opts = list(options[:])
        while len(opts) < 4:
            opts.append("")

        for i, lab in enumerate(self._labels):
            lab.setText(opts[i].upper() if opts[i] else "")

    def mark_option_eliminated(self, answer: str):
        answer_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        if answer not in answer_map:
            return

        index = answer_map[answer]
        self._eliminated.add(index)

        container = self._containers[index]
        container.setStyleSheet(
            "QWidget { "
            "background: rgba(231, 76, 60, 0.2); "
            "border-left: 5px solid #e74c3c; "
            "border-top: 2px solid #e74c3c; "
            "border-right: 2px solid #e74c3c; "
            "border-bottom: 2px solid #e74c3c; "
            "border-radius: 8px; "
            "}"
        )

        label = self._labels[index]
        label.setStyleSheet(
            "font-size: 16px; font-weight: 700; "
            "color: rgba(231, 76, 60, 0.7); "
            "background: transparent; border: none; "
            "text-decoration: line-through;"
        )

    def reset_eliminated(self):
        self._eliminated.clear()

        border_colors = ["#39FF14", "#39FF14", "#39FF14", "#39FF14"]
        for i, container in enumerate(self._containers):
            container.setStyleSheet(
                f"QWidget {{ "
                f"background: rgba(20, 30, 45, 0.9); "
                f"border-left: 5px solid {border_colors[i]}; "
                f"border-top: 2px solid rgba(100, 100, 100, 0.3); "
                f"border-right: 2px solid rgba(100, 100, 100, 0.3); "
                f"border-bottom: 2px solid rgba(100, 100, 100, 0.3); "
                f"border-radius: 8px; "
                f"}}"
            )
            self._labels[i].setStyleSheet(
                "font-size: 16px; font-weight: 700; color: white; "
                "background: transparent; border: none;"
            )

    def clear(self):
        self.reset_eliminated()
        for lab in self._labels:
            lab.setText("")
