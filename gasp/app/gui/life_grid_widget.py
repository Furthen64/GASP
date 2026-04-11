from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont
from gasp.app.sim.constants import CellType
from gasp.app.util.math_helpers import rect_cells

CELL_COLORS = {
    CellType.GROUND: QColor(220, 220, 220),
    CellType.WALL: QColor(80, 80, 80),
    CellType.BORDER: QColor(20, 20, 20),
    CellType.FOOD: QColor(50, 200, 50),
    CellType.TOXIC: QColor(200, 50, 50),
}

class LifeGridWidget(QWidget):
    selected_creature_changed = Signal(int)

    def __init__(self, world, parent=None):
        super().__init__(parent)
        self.world = world
        self.setMinimumSize(400, 300)

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()
        cell_w = w / self.world.width
        cell_h = h / self.world.height

        # Draw terrain + food + toxic
        for x in range(self.world.width):
            for y in range(self.world.height):
                ct = self.world.get_cell_type(x, y)
                color = CELL_COLORS.get(ct, QColor(220, 220, 220))
                painter.fillRect(int(x * cell_w), int(y * cell_h),
                                 max(1, int(cell_w)), max(1, int(cell_h)), color)

        # Draw creatures
        for creature in self.world.creatures.values():
            if not creature.alive:
                continue
            r, g, b = creature.debug_color
            color = QColor(r, g, b)
            cx = int(creature.x * cell_w)
            cy = int(creature.y * cell_h)
            cw = max(1, int(creature.width * cell_w))
            ch = max(1, int(creature.height * cell_h))
            painter.fillRect(cx, cy, cw, ch, color)
            if creature.selected:
                painter.setPen(QColor(255, 255, 0))
                painter.drawRect(cx, cy, cw - 1, ch - 1)

        # Step overlay
        painter.setPen(QColor(0, 0, 0))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(5, 15, f"Step: {self.world.step}")

    def mousePressEvent(self, event):
        w = self.width()
        h = self.height()
        cell_w = w / self.world.width
        cell_h = h / self.world.height
        gx = int(event.x() / cell_w)
        gy = int(event.y() / cell_h)
        # Deselect all
        for c in self.world.creatures.values():
            c.selected = False
        # Find creature at click
        c = self.world.get_creature_at(gx, gy)
        if c:
            c.selected = True
            self.selected_creature_changed.emit(c.id)
        self.update()
