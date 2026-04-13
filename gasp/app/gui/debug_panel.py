from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QLabel,
    QTextEdit, QGroupBox, QFormLayout
)
from gasp.app.sim.actions import move_energy_cost
from gasp.app.sim.fitness import compute_fitness

try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

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

        # Action log
        log_text = "\n".join(
            f"Step {e['step']}: {e['action']} ({'OK' if e['success'] else 'FAIL'})"
            for e in reversed(creature.action_log[-10:])
        )
        self._action_log.setText(log_text)

        # Chromosome summary
        chrom_lines = []
        for i, unit in enumerate(creature.chromosome[:10]):
            if unit.target_type == 'gene':
                target = unit.gene.name if unit.gene else "?"
            else:
                target = f"MOD{unit.module_id}"
            chrom_lines.append(
                f"[{i}] {unit.promoter.signal_id.name} "
                f"{unit.promoter.compare_op.name} "
                f"{unit.promoter.threshold:.1f} -> {target}"
            )
        self._chrom_text.setText("\n".join(chrom_lines))

        # Epoch score graph
        if self._plot_widget and creature.fitness_history:
            self._plot_widget.clear()
            self._plot_widget.plot(creature.fitness_history, pen='b')
