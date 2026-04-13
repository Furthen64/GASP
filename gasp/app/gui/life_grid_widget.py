from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont
from gasp.app.sim.constants import CellType
from gasp.app.util.perf import RollingTimingWindow, TimingSnapshot
from time import perf_counter

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
        self.selected_cell = None
        self.paint_timings = RollingTimingWindow()
        self.setMinimumSize(640, 480)

    def paintEvent(self, event):
        total_start = perf_counter()
        painter = QPainter(self)
        w = self.width()
        h = self.height()
        cell_w = w / self.world.width
        cell_h = h / self.world.height

        # Draw terrain + food + toxic
        phase_start = perf_counter()
        for x in range(self.world.width):
            for y in range(self.world.height):
                ct = self.world.get_cell_type(x, y)
                color = CELL_COLORS.get(ct, QColor(220, 220, 220))
                painter.fillRect(int(x * cell_w), int(y * cell_h),
                                 max(1, int(cell_w)), max(1, int(cell_h)), color)
        terrain_ms = (perf_counter() - phase_start) * 1000.0

        # Draw creatures
        phase_start = perf_counter()
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
        creatures_ms = (perf_counter() - phase_start) * 1000.0

        # Draw selected cell outline (always visible, even without creature)
        phase_start = perf_counter()
        if self.selected_cell is not None:
            sx, sy = self.selected_cell
            painter.setPen(QColor(0, 200, 255))
            painter.drawRect(
                int(sx * cell_w),
                int(sy * cell_h),
                max(1, int(cell_w)) - 1,
                max(1, int(cell_h)) - 1,
            )

        # Step overlay
        painter.setPen(QColor(0, 0, 0))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(5, 15, f"Step: {self.world.step}")
        overlay_ms = (perf_counter() - phase_start) * 1000.0

        self.paint_timings.add(
            TimingSnapshot(
                total_ms=(perf_counter() - total_start) * 1000.0,
                phase_ms={
                    'paint_terrain': terrain_ms,
                    'paint_creatures': creatures_ms,
                    'paint_overlay': overlay_ms,
                },
                metadata={'living_creatures': sum(1 for c in self.world.creatures.values() if c.alive)},
            )
        )

    def mousePressEvent(self, event):
        w = self.width()
        h = self.height()
        cell_w = w / self.world.width
        cell_h = h / self.world.height
        pos = event.position()
        gx = int(pos.x() / cell_w)
        gy = int(pos.y() / cell_h)
        gx = max(0, min(self.world.width - 1, gx))
        gy = max(0, min(self.world.height - 1, gy))
        self.selected_cell = (gx, gy)
        # Deselect all
        for c in self.world.creatures.values():
            c.selected = False
        # Find creature at click
        c = self.world.get_creature_at(gx, gy)
        if c:
            c.selected = True
            self.selected_creature_changed.emit(c.id)
        else:
            self.selected_creature_changed.emit(-1)
        self.update()

    def clear_selection(self):
        self.selected_cell = None
        for c in self.world.creatures.values():
            c.selected = False
        self.update()

    def select_creature(self, creature):
        if creature is None:
            self.clear_selection()
            self.selected_creature_changed.emit(-1)
            return
        self.selected_cell = (creature.x, creature.y)
        for candidate in self.world.creatures.values():
            candidate.selected = candidate.id == creature.id
        self.selected_creature_changed.emit(creature.id)
        self.update()
