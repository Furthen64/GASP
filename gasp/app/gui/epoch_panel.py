from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QTextEdit,
    QCheckBox, QHBoxLayout, QSlider
)


class EpochPanel(QWidget):
    lifespan_enabled_changed = Signal(bool)
    lifespan_seconds_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.setMaximumHeight(320)

        settings_group = QGroupBox("Epoch Settings")
        settings_layout = QVBoxLayout(settings_group)
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
        layout.addWidget(settings_group)

        current_group = QGroupBox("Current Epoch")
        current_form = QFormLayout(current_group)
        self._current_labels = {}
        for field in ['Epoch', 'Seed', 'Step', 'Living', 'Total Creatures', 'Elapsed', 'Lifespan']:
            label = QLabel('-')
            current_form.addRow(f"{field}:", label)
            self._current_labels[field] = label
        layout.addWidget(current_group)

        last_group = QGroupBox("Last Extinction")
        last_form = QFormLayout(last_group)
        self._last_labels = {}
        for field in ['Epoch', 'Seed', 'Steps Survived', 'Best Creature', 'Best Fitness', 'Best Distance', 'Best Unique Positions', 'Best Food', 'Best Pregnancies', 'Fitness Breakdown', 'Elite Count']:
            label = QLabel('-')
            label.setWordWrap(True)
            last_form.addRow(f"{field}:", label)
            self._last_labels[field] = label
        layout.addWidget(last_group)

        history_group = QGroupBox("Recent Epochs")
        history_layout = QVBoxLayout(history_group)
        self._history_text = QTextEdit()
        self._history_text.setReadOnly(True)
        self._history_text.setMaximumHeight(160)
        history_layout.addWidget(self._history_text)
        layout.addWidget(history_group)
        layout.addStretch()

    def _on_lifespan_changed(self, value):
        self._lifespan_value.setText(f"{value} s")
        self.lifespan_seconds_changed.emit(value)

    def set_lifespan_settings(self, enabled: bool, seconds: int):
        self._lifespan_enabled.blockSignals(True)
        self._lifespan_slider.blockSignals(True)
        self._lifespan_enabled.setChecked(enabled)
        self._lifespan_slider.setValue(seconds)
        self._lifespan_value.setText(f"{seconds} s")
        self._lifespan_enabled.blockSignals(False)
        self._lifespan_slider.blockSignals(False)

    def update_world(self, world, elapsed_seconds: float = 0.0, lifespan_enabled: bool = False, lifespan_seconds: int = 0):
        self._current_labels['Epoch'].setText(str(getattr(world, 'epoch', 1)))
        self._current_labels['Seed'].setText(str(getattr(world, 'seed', '-')))
        self._current_labels['Step'].setText(str(world.step))
        self._current_labels['Living'].setText(str(world.living_creature_count()))
        self._current_labels['Total Creatures'].setText(str(len(world.creatures)))
        self._current_labels['Elapsed'].setText(f"{elapsed_seconds:.1f} s")
        if lifespan_enabled:
            self._current_labels['Lifespan'].setText(f"{lifespan_seconds} s")
        else:
            self._current_labels['Lifespan'].setText("Disabled")

        summary = getattr(world, 'last_epoch_summary', None) or {}
        self._last_labels['Epoch'].setText(str(summary.get('epoch', '-')))
        self._last_labels['Seed'].setText(str(summary.get('seed', '-')))
        self._last_labels['Steps Survived'].setText(str(summary.get('steps', '-')))
        self._last_labels['Best Creature'].setText(str(summary.get('best_creature_id', '-')))
        best_fitness = summary.get('best_fitness')
        self._last_labels['Best Fitness'].setText('-' if best_fitness is None else f"{best_fitness:.2f}")
        best_distance = summary.get('best_distance')
        self._last_labels['Best Distance'].setText('-' if best_distance is None else f"{best_distance:.2f}")
        self._last_labels['Best Unique Positions'].setText(str(summary.get('best_unique_positions', '-')))
        self._last_labels['Best Food'].setText(str(summary.get('best_food_eaten', '-')))
        self._last_labels['Best Pregnancies'].setText(str(summary.get('best_pregnancies', '-')))
        breakdown = summary.get('best_fitness_breakdown') or {}
        if breakdown:
            breakdown_text = (
                f"rep {breakdown.get('reproduction', 0.0):.2f}, "
                f"surv {breakdown.get('survival', 0.0):.2f}, "
                f"explore {breakdown.get('exploration', 0.0):.2f}, "
                f"energy {breakdown.get('efficiency', 0.0):.2f}, "
                f"food {breakdown.get('food', 0.0):.2f}, "
                f"toxic -{breakdown.get('toxic_penalty', 0.0):.2f}, "
                f"move -{breakdown.get('move_penalty', 0.0):.2f}"
            )
        else:
            breakdown_text = '-'
        self._last_labels['Fitness Breakdown'].setText(breakdown_text)
        self._last_labels['Elite Count'].setText(str(summary.get('elite_count', '-')))

        history_lines = []
        for item in reversed(getattr(world, 'epoch_history', [])[-8:]):
            history_lines.append(
                f"Epoch {item.get('epoch', '?')}: best #{item.get('best_creature_id', '?')} "
                f"fitness {item.get('best_fitness', 0.0):.2f}, pregnancies {item.get('best_pregnancies', 0)}, carried {item.get('elite_count', 0)}"
            )
        self._history_text.setText("\n".join(history_lines) if history_lines else "No completed epochs yet")