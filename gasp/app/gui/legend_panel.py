from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtGui import QColor

from gasp.app.gui.life_grid_widget import CELL_COLORS
from gasp.app.sim.constants import CellType


class LegendPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Grid Legend")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self._add_entry(layout, CELL_COLORS[CellType.GROUND], "Ground")
        self._add_entry(layout, CELL_COLORS[CellType.WALL], "Wall")
        self._add_entry(layout, CELL_COLORS[CellType.BORDER], "Border")
        self._add_entry(layout, CELL_COLORS[CellType.FOOD], "Food")
        self._add_entry(layout, CELL_COLORS[CellType.TOXIC], "Toxic")
        self._add_entry(layout, QColor(120, 120, 255), "Creature (varies)")
        self._add_entry(layout, QColor(255, 255, 0), "Selected creature outline")

        layout.addStretch()

    def _add_entry(self, parent_layout, color: QColor, label_text: str):
        row = QHBoxLayout()
        swatch = QFrame()
        swatch.setFixedSize(18, 18)
        swatch.setStyleSheet(
            f"background-color: rgb({color.red()}, {color.green()}, {color.blue()});"
            "border: 1px solid #222;"
        )
        label = QLabel(label_text)
        row.addWidget(swatch)
        row.addWidget(label)
        row.addStretch()
        parent_layout.addLayout(row)
