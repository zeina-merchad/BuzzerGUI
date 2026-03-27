from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QHBoxLayout


class OptionsView(QWidget):
    def __init__(self):
        super().__init__()
        self._labels = []
        self._letter_labels = []
        self._containers = []
        self._eliminated = set()

        grid = QGridLayout(self)
        grid.setSpacing(20)
        grid.setContentsMargins(0, 0, 0, 0)

        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        letters = ["A", "B", "C", "D"]
        border_colors = ["#39FF14", "#39FF14", "#39FF14", "#39FF14"]

        for i, (row, col) in enumerate(positions):
            container = QWidget()
            container.setMinimumHeight(130)
            container.setMaximumHeight(200)

            container.setStyleSheet(
                f"QWidget {{ "
                f"background: rgba(20, 30, 45, 0.9); "
                f"border-left: 8px solid {border_colors[i]}; "
                f"border-top: 3px solid rgba(100, 100, 100, 0.3); "
                f"border-right: 3px solid rgba(100, 100, 100, 0.3); "
                f"border-bottom: 3px solid rgba(100, 100, 100, 0.3); "
                f"border-radius: 12px; "
                f"}}"
            )

            layout = QHBoxLayout(container)
            layout.setContentsMargins(24, 18, 24, 18)
            layout.setSpacing(18)

            letter_label = QLabel(f"{letters[i]}:")
            letter_label.setStyleSheet(
                "font-size: 32px; font-weight: 900; color: white; "
                "background: transparent; border: none;"
            )
            letter_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            letter_label.setFixedWidth(52)

            text_label = QLabel("")
            text_label.setWordWrap(True)
            text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            text_label.setStyleSheet(
                "font-size: 28px; font-weight: 700; color: white; "
                "background: transparent; border: none;"
            )

            layout.addWidget(letter_label)
            layout.addWidget(text_label, stretch=1)

            self._letter_labels.append(letter_label)
            self._labels.append(text_label)
            self._containers.append(container)
            grid.addWidget(container, row, col)

    def set_options(self, options: list[str]):
        self.reset_eliminated()

        opts = list(options[:])
        while len(opts) < 4:
            opts.append("")

        for i, lab in enumerate(self._labels):
            lab.setText(opts[i] if opts[i] else "")

    def mark_option_eliminated(self, answer: str):
        """Strike through a wrong answer in red."""
        answer_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        if answer not in answer_map:
            return

        index = answer_map[answer]
        self._eliminated.add(index)

        self._containers[index].setStyleSheet(
            "QWidget { "
            "background: rgba(231, 76, 60, 0.2); "
            "border-left: 8px solid #e74c3c; "
            "border-top: 3px solid #e74c3c; "
            "border-right: 3px solid #e74c3c; "
            "border-bottom: 3px solid #e74c3c; "
            "border-radius: 12px; "
            "}"
        )
        self._letter_labels[index].setStyleSheet(
            "font-size: 32px; font-weight: 900; "
            "color: rgba(231, 76, 60, 0.7); "
            "background: transparent; border: none; "
            "text-decoration: line-through;"
        )
        self._labels[index].setStyleSheet(
            "font-size: 28px; font-weight: 700; "
            "color: rgba(231, 76, 60, 0.7); "
            "background: transparent; border: none; "
            "text-decoration: line-through;"
        )

    def mark_option_correct(self, answer: str):
        """Highlight the correct answer in green."""
        answer_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        if answer not in answer_map:
            return

        index = answer_map[answer]

        self._containers[index].setStyleSheet(
            "QWidget { "
            "background: rgba(57, 255, 20, 0.25); "
            "border-left: 8px solid #39FF14; "
            "border-top: 3px solid #39FF14; "
            "border-right: 3px solid #39FF14; "
            "border-bottom: 3px solid #39FF14; "
            "border-radius: 12px; "
            "}"
        )
        self._letter_labels[index].setStyleSheet(
            "font-size: 32px; font-weight: 900; "
            "color: #39FF14; "
            "background: transparent; border: none;"
        )
        self._labels[index].setStyleSheet(
            "font-size: 28px; font-weight: 900; "
            "color: #39FF14; "
            "background: transparent; border: none;"
        )

    def reset_eliminated(self):
        self._eliminated.clear()

        border_colors = ["#39FF14", "#39FF14", "#39FF14", "#39FF14"]
        for i, container in enumerate(self._containers):
            container.setStyleSheet(
                f"QWidget {{ "
                f"background: rgba(20, 30, 45, 0.9); "
                f"border-left: 8px solid {border_colors[i]}; "
                f"border-top: 3px solid rgba(100, 100, 100, 0.3); "
                f"border-right: 3px solid rgba(100, 100, 100, 0.3); "
                f"border-bottom: 3px solid rgba(100, 100, 100, 0.3); "
                f"border-radius: 12px; "
                f"}}"
            )
            self._letter_labels[i].setStyleSheet(
                "font-size: 32px; font-weight: 900; color: white; "
                "background: transparent; border: none;"
            )
            self._labels[i].setStyleSheet(
                "font-size: 28px; font-weight: 700; color: white; "
                "background: transparent; border: none;"
            )

    def clear(self):
        self.reset_eliminated()
        for lab in self._labels:
            lab.setText("")