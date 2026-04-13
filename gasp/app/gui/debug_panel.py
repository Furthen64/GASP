from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QLabel,
    QTextEdit, QGroupBox, QFormLayout, QGridLayout, QHBoxLayout
)
from PySide6.QtCore import Qt
from gasp.app.sim.actions import move_energy_cost
from gasp.app.sim.fitness import compute_fitness
from gasp.app.util.math_helpers import rect_cells

try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False


GENOME_SIGNATURE_COLORS = {
    0: "#3a3a3a",
    1: "#bfbfbf",
    2: "#d84a4a",
    3: "#4cb45b",
    4: "#3e73d9",
    5: "#f08cc0",
    6: "#d6cb44",
    7: "#7d56c2",
    8: "#1d3f91",
    9: "#44c9d6",
}


SENSE_CELL_STYLES = {
    'ground': ('#2f2f2f', '#f0f0f0'),
    'food': ('#4cb45b', '#101010'),
    'toxic': ('#d84a4a', '#f8f8f8'),
    'wall': ('#1d3f91', '#f8f8f8'),
    'border': ('#7d56c2', '#f8f8f8'),
    'creature': ('#d6cb44', '#101010'),
    'self': ('#44c9d6', '#101010'),
    'focus': ('#f08cc0', '#101010'),
}


class GenomeSignatureWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        caption = QLabel("Top row: promoter signal | Bottom row: target/state")
        caption.setWordWrap(True)
        layout.addWidget(caption)

        grid_row = QHBoxLayout()
        grid_row.setContentsMargins(0, 0, 0, 0)
        grid_row.setSpacing(6)
        layout.addLayout(grid_row)

        row_labels = QVBoxLayout()
        row_labels.setContentsMargins(0, 18, 0, 0)
        row_labels.setSpacing(2)
        promoter_label = QLabel("P")
        promoter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target_label = QLabel("T")
        target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_labels.addWidget(promoter_label)
        row_labels.addWidget(target_label)
        grid_row.addLayout(row_labels)

        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(2)
        grid_row.addLayout(grid)

        for row in range(2):
            for column in range(20):
                label = QLabel("0")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setMinimumSize(18, 18)
                label.setMaximumSize(18, 18)
                label.setStyleSheet(self._cell_style(0))
                grid.addWidget(label, row, column)
                self._cells.append(label)

    def _cell_style(self, digit: int) -> str:
        text_color = "#111111" if digit in (1, 5, 6, 9) else "#f5f5f5"
        return (
            f"background-color: {GENOME_SIGNATURE_COLORS[digit]};"
            f"color: {text_color};"
            "border: 1px solid #202020;"
            "font-size: 10px;"
            "font-weight: 600;"
        )

    def clear_signature(self):
        for index, cell in enumerate(self._cells):
            cell.setText("0")
            cell.setToolTip(f"Slot {index % 20 + 1}: empty")
            cell.setStyleSheet(self._cell_style(0))

    def update_signature(self, creature):
        promoter_digits = [0] * 20
        target_digits = [0] * 20
        promoter_tips = [f"Gene {index}: empty" for index in range(20)]
        target_tips = [f"Gene {index}: empty" for index in range(20)]

        for index, unit in enumerate(creature.chromosome[:20]):
            promoter_digit = unit.promoter.signal_id.value % 10
            promoter_digits[index] = promoter_digit
            promoter_tips[index] = (
                f"Gene {index}: signal={unit.promoter.signal_id.name}, "
                f"compare={unit.promoter.compare_op.name}, "
                f"threshold={unit.promoter.threshold:.1f}, "
                f"strength={unit.promoter.base_strength:.1f}"
            )

            if unit.target_type == 'gene' and unit.gene is not None:
                target_base = unit.gene.value
                target_name = unit.gene.name
            elif unit.target_type == 'module' and unit.module_id is not None:
                target_base = unit.module_id
                target_name = f"MOD{unit.module_id}"
            else:
                target_base = 0
                target_name = "NONE"
            source_state = unit.source_state or 0
            next_state = unit.next_state or 0
            target_digit = (target_base + (source_state * 3) + (next_state * 5)) % 10
            target_digits[index] = target_digit
            target_tips[index] = (
                f"Gene {index}: target={target_name}, source_state={unit.source_state}, "
                f"next_state={unit.next_state}"
            )

        for column in range(20):
            promoter_cell = self._cells[column]
            target_cell = self._cells[20 + column]
            promoter_digit = promoter_digits[column]
            target_digit = target_digits[column]
            promoter_cell.setText(str(promoter_digit))
            target_cell.setText(str(target_digit))
            promoter_cell.setToolTip(promoter_tips[column])
            target_cell.setToolTip(target_tips[column])
            promoter_cell.setStyleSheet(self._cell_style(promoter_digit))
            target_cell.setStyleSheet(self._cell_style(target_digit))


class SensedNeighborhoodWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        caption = QLabel("5x5 neighborhood centered on the creature. Pink marks the focus cell in front.")
        caption.setWordWrap(True)
        layout.addWidget(caption)

        self._direction_label = QLabel("Facing: - | Front/Left/Right: -, -, -")
        self._direction_label.setWordWrap(True)
        layout.addWidget(self._direction_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(2)
        layout.addLayout(grid)

        for row in range(5):
            for column in range(5):
                label = QLabel(".")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setMinimumSize(22, 22)
                label.setMaximumSize(22, 22)
                label.setStyleSheet(self._cell_style('ground'))
                grid.addWidget(label, row, column)
                self._cells.append(label)

    def _cell_style(self, key: str) -> str:
        background, foreground = SENSE_CELL_STYLES[key]
        return (
            f"background-color: {background};"
            f"color: {foreground};"
            "border: 1px solid #202020;"
            "font-size: 10px;"
            "font-weight: 600;"
        )

    def clear_view(self):
        self._direction_label.setText("Facing: - | Front/Left/Right: -, -, -")
        for row in range(5):
            for column in range(5):
                cell = self._cells[(row * 5) + column]
                cell.setText('.')
                cell.setToolTip("No creature selected")
                cell.setStyleSheet(self._cell_style('ground'))

    def update_view(self, creature, world):
        center_x = creature.x + (creature.width - 1) // 2
        center_y = creature.y + (creature.height - 1) // 2
        own_cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
        front_lookup = {
            'N': (center_x, creature.y - 1),
            'S': (center_x, creature.y + creature.height),
            'E': (creature.x + creature.width, center_y),
            'W': (creature.x - 1, center_y),
        }
        left_right_lookup = {
            'N': ((creature.x - 1, center_y), (creature.x + creature.width, center_y)),
            'S': ((creature.x + creature.width, center_y), (creature.x - 1, center_y)),
            'E': ((center_x, creature.y - 1), (center_x, creature.y + creature.height)),
            'W': ((center_x, creature.y + creature.height), (center_x, creature.y - 1)),
        }
        front_cell = front_lookup[creature.facing.name]
        left_cell, right_cell = left_right_lookup[creature.facing.name]
        self._direction_label.setText(
            f"Facing: {creature.facing.name} | Front/Left/Right: {front_cell}, {left_cell}, {right_cell}"
        )

        for row_offset in range(-2, 3):
            for column_offset in range(-2, 3):
                world_x = center_x + column_offset
                world_y = center_y + row_offset
                grid_index = ((row_offset + 2) * 5) + (column_offset + 2)
                cell = self._cells[grid_index]
                cell_kind = 'ground'
                cell_char = '.'
                tooltip = f"({world_x}, {world_y}) "

                if (world_x, world_y) in own_cells:
                    cell_kind = 'self'
                    cell_char = 'S'
                    tooltip += 'self'
                else:
                    occupant = world.get_creature_at(world_x, world_y)
                    if occupant is not None:
                        cell_kind = 'creature'
                        cell_char = 'C'
                        tooltip += f"creature {occupant.id}"
                    else:
                        cell_type = world.get_cell_type(world_x, world_y)
                        if cell_type.name == 'FOOD':
                            cell_kind = 'food'
                            cell_char = 'F'
                        elif cell_type.name == 'TOXIC':
                            cell_kind = 'toxic'
                            cell_char = 'X'
                        elif cell_type.name == 'WALL':
                            cell_kind = 'wall'
                            cell_char = 'W'
                        elif cell_type.name == 'BORDER':
                            cell_kind = 'border'
                            cell_char = 'B'
                        tooltip += cell_type.name.lower()

                if (world_x, world_y) == front_cell and cell_kind == 'ground':
                    cell_kind = 'focus'
                cell.setText(cell_char)
                cell.setToolTip(tooltip)
                cell.setStyleSheet(self._cell_style(cell_kind))

class DebugPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        self._layout = QVBoxLayout(container)

        # Basic info
        info_group = QGroupBox("Creature Info")
        info_form = QFormLayout(info_group)
        self._labels = {}
        for field in ['ID', 'Generation', 'Age', 'Position', 'Size', 'Facing',
                      'Energy', 'Pregnancies', 'Epoch Score', 'Distance', 'Food Eaten',
                      'Unique Positions', 'Toxic Ticks', 'Move Cost', 'Move Energy', 'Action']:
            lbl = QLabel("-")
            info_form.addRow(f"{field}:", lbl)
            self._labels[field] = lbl
        self._layout.addWidget(info_group)

        # Sensed info
        sense_group = QGroupBox("Sensed")
        sense_form = QFormLayout(sense_group)
        self._sense_labels = {}
        for field in ['Food', 'Toxic', 'Wall', 'Free', 'Partners', 'CanGrow',
                      'CanMove', 'CanReproduce']:
            lbl = QLabel("-")
            sense_form.addRow(f"{field}:", lbl)
            self._sense_labels[field] = lbl
        self._layout.addWidget(sense_group)

        neighborhood_group = QGroupBox("Sensed Neighborhood")
        neighborhood_layout = QVBoxLayout(neighborhood_group)
        self._neighborhood_widget = SensedNeighborhoodWidget()
        neighborhood_layout.addWidget(self._neighborhood_widget)
        self._layout.addWidget(neighborhood_group)

        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout(perf_group)
        self._perf_label = QLabel("No timing data yet")
        self._perf_label.setWordWrap(True)
        perf_layout.addWidget(self._perf_label)
        self._layout.addWidget(perf_group)

        # Action log
        log_group = QGroupBox("Action Log")
        log_layout = QVBoxLayout(log_group)
        self._action_log = QTextEdit()
        self._action_log.setReadOnly(True)
        self._action_log.setMaximumHeight(100)
        log_layout.addWidget(self._action_log)
        self._layout.addWidget(log_group)

        # Chromosome
        chrom_group = QGroupBox("Chromosome")
        chrom_layout = QVBoxLayout(chrom_group)
        self._genome_signature = GenomeSignatureWidget()
        chrom_layout.addWidget(self._genome_signature)
        self._chrom_text = QTextEdit()
        self._chrom_text.setReadOnly(True)
        self._chrom_text.setMaximumHeight(120)
        chrom_layout.addWidget(self._chrom_text)
        self._layout.addWidget(chrom_group)

        # Epoch score graph
        if HAS_PYQTGRAPH:
            graph_group = QGroupBox("Epoch Score Trend")
            graph_layout = QVBoxLayout(graph_group)
            self._plot_widget = pg.PlotWidget()
            self._plot_widget.setMaximumHeight(150)
            graph_layout.addWidget(self._plot_widget)
            self._layout.addWidget(graph_group)
        else:
            self._plot_widget = None

        self._layout.addStretch()

    def clear_creature(self, message="No creature selected"):
        for lbl in self._labels.values():
            lbl.setText("-")
        for lbl in self._sense_labels.values():
            lbl.setText("-")
        self._action_log.setText(message)
        self._neighborhood_widget.clear_view()
        self._genome_signature.clear_signature()
        self._chrom_text.clear()
        if self._plot_widget:
            self._plot_widget.clear()

    def update_performance(self, simulation_summary, ui_summary, paint_summary):
        self._perf_label.setText(
            f"Simulation: {simulation_summary}\n"
            f"UI: {ui_summary}\n"
            f"Paint: {paint_summary}"
        )

    def update_creature(self, creature, world):
        if creature is None:
            return
        self._labels['ID'].setText(str(creature.id))
        self._labels['Generation'].setText(str(creature.generation))
        self._labels['Age'].setText(str(creature.age))
        self._labels['Position'].setText(f"({creature.x}, {creature.y})")
        self._labels['Size'].setText(f"{creature.width}x{creature.height}")
        self._labels['Facing'].setText(creature.facing.name)
        self._labels['Energy'].setText(f"{creature.energy:.1f}")
        self._labels['Pregnancies'].setText(str(creature.pregnancies_completed))
        self._labels['Epoch Score'].setText(f"{compute_fitness(creature, world.params):.2f} (estimate)")
        self._labels['Distance'].setText(f"{creature.distance_traveled:.2f}")
        self._labels['Food Eaten'].setText(str(creature.food_eaten))
        self._labels['Unique Positions'].setText(str(len({tuple(pos) for pos in creature.visited_positions})))
        self._labels['Toxic Ticks'].setText(str(creature.toxic_ticks))
        self._labels['Move Cost'].setText(f"{move_energy_cost(creature, world.params):.2f}")
        self._labels['Move Energy'].setText(f"{creature.move_energy_spent:.2f}")
        self._labels['Action'].setText(
            creature.last_action.name if creature.last_action else "-"
        )

        sensed = creature.sensed
        self._sense_labels['Food'].setText(str(sensed.get('food_count', 0)))
        self._sense_labels['Toxic'].setText(str(sensed.get('toxic_count', 0)))
        self._sense_labels['Wall'].setText(str(sensed.get('wall_count', 0)))
        self._sense_labels['Free'].setText(str(sensed.get('free_count', 0)))
        self._sense_labels['Partners'].setText(str(sensed.get('partner_count', 0)))
        self._sense_labels['CanGrow'].setText(str(sensed.get('can_grow', 0)))
        self._sense_labels['CanMove'].setText(str(sensed.get('can_move_forward', 0)))
        self._sense_labels['CanReproduce'].setText(str(sensed.get('can_reproduce', 0)))
        self._neighborhood_widget.update_view(creature, world)

        # Action log
        log_text = "\n".join(
            f"Step {e['step']}: {e['action']} ({'OK' if e['success'] else 'FAIL'})"
            for e in reversed(creature.action_log[-10:])
        )
        self._action_log.setText(log_text)

        # Chromosome summary
        self._genome_signature.update_signature(creature)
        chrom_lines = []
        for i, unit in enumerate(creature.chromosome[:10]):
            if unit.target_type == 'gene':
                target = unit.gene.name if unit.gene else "?"
            else:
                target = f"MOD{unit.module_id}"
            chrom_lines.append(
                f"[{i}] {unit.promoter.signal_id.name} "
                f"{unit.promoter.compare_op.name} "
                f"{unit.promoter.threshold:.1f} -> {target} "
                f"(S:{unit.source_state}, N:{unit.next_state})"
            )
        self._chrom_text.setText("\n".join(chrom_lines))

        # Epoch score graph
        if self._plot_widget and creature.fitness_history:
            self._plot_widget.clear()
            self._plot_widget.plot(creature.fitness_history, pen='b')
