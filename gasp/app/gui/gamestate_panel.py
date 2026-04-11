from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal

class GamestatePanel(QWidget):
    save_requested = Signal()
    load_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        btn_save = QPushButton("Save State")
        btn_save.clicked.connect(self.save_requested)
        btn_load = QPushButton("Load State")
        btn_load.clicked.connect(self.load_requested)
        self._status = QLabel("Ready")
        layout.addWidget(btn_save)
        layout.addWidget(btn_load)
        layout.addWidget(self._status)
        layout.addStretch()

    def set_status(self, text: str):
        self._status.setText(text)
