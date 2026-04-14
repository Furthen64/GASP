from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QTextEdit,
    QCheckBox, QHBoxLayout, QSlider, QDoubleSpinBox, QSizePolicy
    , QScrollArea
)


class TransitionPanel(QWidget):
    lifespan_enabled_changed = Signal(bool)
    lifespan_seconds_changed = Signal(int)
    elite_mutation_rate_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        content_layout = QVBoxLayout(container)

        settings_group = QGroupBox("Transition Settings")
        settings_layout = QVBoxLayout(settings_group)

        plan_label = QLabel(
            "Next epoch plan:\n"
            "1. Clone the best creature\n"
            "2. Crossover child from the top two\n"
            "3. Second crossover child from the top two\n"
            "4-N. Mutated children from the best creature"
        )
        plan_label.setWordWrap(True)
        settings_layout.addWidget(plan_label)

        self._lifespan_enabled = QCheckBox("Enable epoch lifespan")
        self._lifespan_enabled.toggled.connect(self.lifespan_enabled_changed)
        settings_layout.addWidget(self._lifespan_enabled)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Seconds"))
        self._lifespan_slider = QSlider(Qt.Orientation.Horizontal)
        self._lifespan_slider.setRange(0, 120)
        self._lifespan_slider.setValue(0)
        self._lifespan_slider.valueChanged.connect(self._on_lifespan_changed)
        slider_row.addWidget(self._lifespan_slider)
        self._lifespan_value = QLabel("0 s")
        slider_row.addWidget(self._lifespan_value)
        settings_layout.addLayout(slider_row)

        mutation_form = QFormLayout()
        mutation_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        mutation_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        mutation_form.setHorizontalSpacing(14)
        mutation_form.setVerticalSpacing(10)
        mutation_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._elite_mutation_rate = QDoubleSpinBox()
        self._elite_mutation_rate.setRange(0.0, 10000.0)
        self._elite_mutation_rate.setDecimals(4)
        self._elite_mutation_rate.setSingleStep(0.01)
        self._elite_mutation_rate.valueChanged.connect(self.elite_mutation_rate_changed)
        mutation_form.addRow(self._make_row_label("Best-child mutation rate:"), self._elite_mutation_rate)
        settings_layout.addLayout(mutation_form)
        content_layout.addWidget(settings_group)

        current_group = QGroupBox("Current Epoch")
        current_form = QFormLayout(current_group)
        current_form.setHorizontalSpacing(14)
        current_form.setVerticalSpacing(8)
        current_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._current_labels = {}
        for field in ['Epoch', 'Seed', 'Step', 'Living', 'Total Creatures', 'Elapsed', 'Lifespan', 'Mutation Rate']:
            label = QLabel('-')
            label.setWordWrap(True)
            current_form.addRow(self._make_row_label(f"{field}:"), label)
            self._current_labels[field] = label
        content_layout.addWidget(current_group)

        last_group = QGroupBox("Last Transition")
        last_form = QFormLayout(last_group)
        last_form.setHorizontalSpacing(14)
        last_form.setVerticalSpacing(8)
        last_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._last_labels = {}
        for field in ['Epoch', 'Seed', 'Steps Survived', 'Best Creature', 'Best Selection Score', 'Best Distance', 'Best Unique Positions', 'Best Food', 'Best Pregnancies', 'Selection Breakdown', 'Parents Used', 'Mutation Rate']:
            label = QLabel('-')
            label.setWordWrap(True)
            last_form.addRow(self._make_row_label(f"{field}:"), label)
            self._last_labels[field] = label
        content_layout.addWidget(last_group)

        history_group = QGroupBox("Recent Transitions")
        history_layout = QVBoxLayout(history_group)
        self._history_text = QTextEdit()
        self._history_text.setReadOnly(True)
        self._history_text.setMaximumHeight(160)
        history_layout.addWidget(self._history_text)
        content_layout.addWidget(history_group)
        content_layout.addStretch()

    def _make_row_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        return label

    def _on_lifespan_changed(self, value):
        self._lifespan_value.setText(f"{value} s")
        self.lifespan_seconds_changed.emit(value)

    def set_transition_settings(self, lifespan_enabled: bool, lifespan_seconds: int, elite_mutation_rate: float):
        self._lifespan_enabled.blockSignals(True)
        self._lifespan_slider.blockSignals(True)
        self._elite_mutation_rate.blockSignals(True)
        self._lifespan_enabled.setChecked(lifespan_enabled)
        self._lifespan_slider.setValue(lifespan_seconds)
        self._lifespan_value.setText(f"{lifespan_seconds} s")
        self._elite_mutation_rate.setValue(float(elite_mutation_rate))
        self._lifespan_enabled.blockSignals(False)
        self._lifespan_slider.blockSignals(False)
        self._elite_mutation_rate.blockSignals(False)

    def update_world(self, world, elapsed_seconds: float = 0.0, lifespan_enabled: bool = False, lifespan_seconds: int = 0):
        self._current_labels['Epoch'].setText(str(getattr(world, 'epoch', 1)))
        self._current_labels['Seed'].setText(str(getattr(world, 'seed', '-')))
        self._current_labels['Step'].setText(str(world.step))
        self._current_labels['Living'].setText(str(world.living_creature_count()))
        self._current_labels['Total Creatures'].setText(str(len(world.creatures)))
        self._current_labels['Elapsed'].setText(f"{elapsed_seconds:.1f} s")
        self._current_labels['Mutation Rate'].setText(f"{world.params.epoch_elite_mutation_rate:.2f}")
        if lifespan_enabled:
            self._current_labels['Lifespan'].setText(f"{lifespan_seconds} s")
        else:
            self._current_labels['Lifespan'].setText("Disabled")

        summary = getattr(world, 'last_epoch_summary', None) or {}
        self._last_labels['Epoch'].setText(str(summary.get('epoch', '-')))
        self._last_labels['Seed'].setText(str(summary.get('seed', '-')))
        self._last_labels['Steps Survived'].setText(str(summary.get('steps', '-')))
        self._last_labels['Best Creature'].setText(str(summary.get('best_creature_id', '-')))
        best_score = summary.get('best_selection_score', summary.get('best_fitness'))
        self._last_labels['Best Selection Score'].setText('-' if best_score is None else f"{best_score:.2f}")
        best_distance = summary.get('best_distance')
        self._last_labels['Best Distance'].setText('-' if best_distance is None else f"{best_distance:.2f}")
        self._last_labels['Best Unique Positions'].setText(str(summary.get('best_unique_positions', '-')))
        self._last_labels['Best Food'].setText(str(summary.get('best_food_eaten', '-')))
        self._last_labels['Best Pregnancies'].setText(str(summary.get('best_pregnancies', '-')))
        breakdown = summary.get('best_selection_breakdown') or summary.get('best_fitness_breakdown') or {}
        if breakdown:
            breakdown_text = (
                f"rep {breakdown.get('reproduction', 0.0):.2f}, "
                f"surv {breakdown.get('survival', 0.0):.2f}, "
                f"explore {breakdown.get('exploration', 0.0):.2f}, "
                f"distance {breakdown.get('distance', 0.0):.2f}, "
                f"energy {breakdown.get('efficiency', 0.0):.2f}, "
                f"food {breakdown.get('food', 0.0):.2f}, "
                f"idle -{breakdown.get('idle_penalty', 0.0):.2f}, "
                f"toxic -{breakdown.get('toxic_penalty', 0.0):.2f}"
            )
        else:
            breakdown_text = '-'
        self._last_labels['Selection Breakdown'].setText(breakdown_text)
        self._last_labels['Parents Used'].setText(str(summary.get('elite_count', '-')))
        elite_mutation = summary.get('elite_mutation_rate')
        self._last_labels['Mutation Rate'].setText('-' if elite_mutation is None else f"{elite_mutation:.2f}")

        history_lines = []
        for item in reversed(getattr(world, 'epoch_history', [])[-8:]):
            history_lines.append(
                f"Epoch {item.get('epoch', '?')}: best #{item.get('best_creature_id', '?')} "
                f"score {item.get('best_selection_score', item.get('best_fitness', 0.0)):.2f}, "
                f"carried {item.get('elite_count', 0)}, mutation {item.get('elite_mutation_rate', 0.0):.2f}"
            )
        self._history_text.setText("\n".join(history_lines) if history_lines else "No completed transitions yet")